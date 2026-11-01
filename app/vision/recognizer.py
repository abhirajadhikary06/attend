"""
Face recognition using InsightFace (ArcFace) + FAISS index.
Runs entirely on CPU via ONNX Runtime.
"""

from __future__ import annotations
import logging
import os
import sys
from functools import partial
from importlib import import_module
from pathlib import Path
from typing import List, Optional, Tuple
from types import SimpleNamespace
import numpy as np

logger = logging.getLogger(__name__)

try:
    import insightface
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False
    logger.warning("insightface not installed – recognition disabled")

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("faiss-cpu not installed – vector search disabled")

from app.core.config import FAISS_DIR, MODELS_DIR, config
from app.core.database import (
    get_all_students, bytes_to_embedding, embedding_to_bytes
)


class FaceRecognizer:
    """
    Handles embedding extraction and similarity search.
    """

    def __init__(self, model_name: str = "buffalo_l"):
        self.model_name = model_name
        self.app: Optional[FaceAnalysis] = None
        self.index = None
        self.id_map: List[int] = []          # FAISS index position -> student.pk
        self.student_ids: List[str] = []     # parallel list of student_id strings
        self._initialized = False

    def initialize(self) -> bool:
        if not INSIGHTFACE_AVAILABLE:
            logger.error("InsightFace is required")
            return False

        try:
            # Use CPU provider only
            # In PyInstaller --windowed builds stdout/stderr are None. InsightFace
            # uses tqdm during its first-run model download, which crashes when its
            # output stream is missing. Give that download a safe stream.
            download_module = import_module("insightface.utils.download")
            original_tqdm = download_module.tqdm
            progress_stream = sys.stderr or sys.stdout
            null_stream = None
            if progress_stream is None:
                null_stream = open(os.devnull, "w", encoding="utf-8")
                progress_stream = null_stream
            try:
                download_module.tqdm = partial(original_tqdm, file=progress_stream)
                self.app = FaceAnalysis(
                    name=self.model_name,
                    root=str(MODELS_DIR),
                    providers=["CPUExecutionProvider"],
                )
            finally:
                download_module.tqdm = original_tqdm
                if null_stream is not None:
                    null_stream.close()
            # det_size reduced to 320×320 for lower CPU latency (still reliable for close faces)
            self.app.prepare(ctx_id=-1, det_size=(320, 320))
            self._initialized = True
            logger.info("InsightFace model loaded (CPU)")
            return True
        except Exception as e:
            logger.exception("Failed to initialize InsightFace: %s", e)
            return False

    def get_embedding(self, face_img: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract 512-d ArcFace embedding from a cropped face image (BGR).
        Returns L2-normalized embedding or None.
        """
        if not self._initialized or self.app is None:
            return None
        try:
            faces = self.app.get(face_img)
            if not faces:
                return None
            # Take the largest face if multiple
            face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
            emb = face.embedding
            # L2 normalize
            emb = emb / (np.linalg.norm(emb) + 1e-8)
            return emb.astype(np.float32)
        except Exception as e:
            logger.debug("Embedding extraction failed: %s", e)
            return None

    def detect_and_embed(self, frame: np.ndarray) -> List[dict]:
        """
        Detect faces and return their normalized embeddings.

        Enrollment retries at increasing detector sizes when the default live
        camera size misses the face. The larger passes are limited to enrollment
        so they do not increase the normal live-camera inference cost.
        """
        if not self._initialized or self.app is None:
            return []
        def pack_faces(faces: list) -> List[dict]:
            packed = []
            for face in faces:
                embedding = np.asarray(face.embedding, dtype=np.float32)
                embedding /= np.linalg.norm(embedding) + 1e-8
                packed.append({
                    "bbox": face.bbox.astype(int).tolist(),
                    "embedding": embedding,
                    "det_score": float(face.det_score),
                    "kps": getattr(face, "kps", None),
                    "pose": getattr(face, "pose", None),
                })
            return packed

        try:
            faces = self.app.get(frame)
            if faces:
                return pack_faces(faces)
        except Exception:
            # Still try the explicit detector path below. Some packaged runtime
            # failures occur in FaceAnalysis.get() before detector output is
            # returned; logging here preserves the reason for diagnosis.
            logger.exception("Default enrollment face pass failed")

        height, width = frame.shape[:2]
        logger.info(
            "Enrollment default detector found no faces in %dx%d image; "
            "retrying at larger sizes", width, height,
        )
        for size in (640, 960, 1280):
            try:
                bboxes, keypoints = self.app.det_model.detect(
                    frame,
                    input_size=(size, size),
                    max_num=0,
                    metric="default",
                )
                results = []
                for index, bbox in enumerate(bboxes):
                    kps = keypoints[index] if keypoints is not None else None
                    embedding = self.embed_detection(frame, kps)
                    if embedding is None:
                        continue
                    results.append({
                        "bbox": bbox[:4].astype(int).tolist(),
                        "embedding": embedding,
                        "det_score": float(bbox[4]),
                        "kps": kps,
                        "pose": None,
                    })
                logger.info(
                    "Enrollment detector pass at %dpx: %d face(s)", size, len(results)
                )
                if results:
                    return results
            except Exception:
                logger.exception("Enrollment detector pass at %dpx failed", size)
        return []

    def detect_faces(self, frame: np.ndarray) -> List[dict]:
        """Run the detector only; defer ArcFace until a track needs recognition."""
        if not self._initialized or self.app is None:
            return []
        try:
            bboxes, keypoints = self.app.det_model.detect(
                frame, max_num=0, metric="default")
            detections = []
            for i, bbox in enumerate(bboxes):
                detections.append({
                    "bbox": bbox[:4].astype(int).tolist(),
                    "embedding": None,
                    "kps": keypoints[i] if keypoints is not None else None,
                    "det_score": float(bbox[4]),
                })
            return detections
        except Exception as exc:
            logger.debug("Face detection failed: %s", exc)
            return []

    def embed_detection(self, frame: np.ndarray, keypoints: np.ndarray) -> Optional[np.ndarray]:
        """Extract one normalized embedding for the selected primary face."""
        if not self._initialized or self.app is None or keypoints is None:
            return None
        model = self.app.models.get("recognition")
        if model is None:
            return None
        try:
            face = SimpleNamespace(kps=keypoints, embedding=None)
            emb = model.get(frame, face)
            if emb is None:
                return None
            emb = np.asarray(emb, dtype=np.float32)
            return emb / (np.linalg.norm(emb) + 1e-8)
        except Exception as exc:
            logger.debug("Selected-face embedding failed: %s", exc)
            return None
    def build_index(self) -> int:
        """
        Rebuild FAISS index from all active students that have embeddings.
        Returns number of vectors added.
        """
        if not FAISS_AVAILABLE:
            logger.error("FAISS not available")
            return 0

        students = get_all_students(active_only=True)
        vectors = []
        self.id_map = []
        self.student_ids = []

        for s in students:
            if s.embedding is None:
                continue
            try:
                emb = bytes_to_embedding(s.embedding)
                if emb.shape[0] != 512:  # ArcFace buffalo_l is 512-d
                    continue
                vectors.append(emb)
                self.id_map.append(s.id)
                self.student_ids.append(s.student_id)
            except Exception:
                continue

        if not vectors:
            self.index = None
            return 0

        mat = np.vstack(vectors).astype(np.float32)
        # Inner product index (works with L2-normalized vectors = cosine similarity)
        self.index = faiss.IndexFlatIP(mat.shape[1])
        self.index.add(mat)

        # Persist
        FAISS_DIR.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(FAISS_DIR / "students.index"))
        np.save(FAISS_DIR / "id_map.npy", np.array(self.id_map, dtype=np.int64))
        np.save(FAISS_DIR / "student_ids.npy", np.array(self.student_ids))

        logger.info("FAISS index built with %d students", len(vectors))
        return len(vectors)

    def load_index(self) -> bool:
        index_path = FAISS_DIR / "students.index"
        if not index_path.exists() or not FAISS_AVAILABLE:
            return False
        try:
            self.index = faiss.read_index(str(index_path))
            self.id_map = np.load(FAISS_DIR / "id_map.npy").tolist()
            self.student_ids = np.load(FAISS_DIR / "student_ids.npy").tolist()
            return True
        except Exception as e:
            logger.warning("Could not load FAISS index: %s", e)
            return False

    def search(
        self,
        embedding: np.ndarray,
        threshold: Optional[float] = None,
    ) -> Tuple[Optional[int], Optional[str], float]:
        """
        Search for the best matching student.
        Returns (student_pk, student_id, similarity) or (None, None, 0.0)
        """
        if self.index is None or self.index.ntotal == 0:
            return None, None, 0.0

        if threshold is None:
            threshold = config.recognition.match_threshold

        emb = embedding.astype(np.float32).reshape(1, -1)
        scores, indices = self.index.search(emb, 1)
        score = float(scores[0][0])
        idx = int(indices[0][0])

        if score >= threshold and 0 <= idx < len(self.id_map):
            return self.id_map[idx], self.student_ids[idx], score
        return None, None, score
