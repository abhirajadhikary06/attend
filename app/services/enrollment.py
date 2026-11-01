"""
Student enrollment: single and bulk photo processing.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import List, Tuple, Optional
import shutil
import cv2
import numpy as np

from app.core.config import FACES_DIR
from app.core.database import add_student, update_student_embedding, get_student_by_id, log_action
from app.vision.recognizer import FaceRecognizer

logger = logging.getLogger(__name__)


class EnrollmentService:
    def __init__(self, recognizer: FaceRecognizer):
        self.recognizer = recognizer

    def enroll_from_image(
        self,
        image_path: str | Path,
        student_id: str,
        name: str,
        registration_no: str = None,
        department: str = None,
        semester: str = None,
    ) -> Tuple[bool, str]:
        """
        Process one student photo and create/update the record + embedding.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            return False, f"Image not found: {image_path}"

        img = cv2.imread(str(image_path))
        if img is None:
            return False, "Could not read image"

        faces = self.recognizer.detect_and_embed(img)
        if not faces:
            return False, "No face detected in the image"
        if len(faces) > 1:
            # Prefer the largest face
            faces = sorted(
                faces,
                key=lambda f: (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]),
                reverse=True,
            )

        emb = faces[0]["embedding"]

        # Copy photo into data/faces/
        dest = FACES_DIR / f"{student_id}.jpg"
        shutil.copy2(image_path, dest)

        existing = get_student_by_id(student_id)
        if existing:
            update_student_embedding(existing.id, emb, str(dest))
            log_action("student_updated", details=f"student_id={student_id}")
            return True, f"Updated existing student {student_id}"
        else:
            add_student(
                student_id=student_id,
                name=name,
                registration_no=registration_no,
                department=department,
                semester=semester,
                photo_path=str(dest),
                embedding=emb,
            )
            log_action("student_enrolled", details=f"student_id={student_id}")
            return True, f"Enrolled {student_id} successfully"

    def bulk_enroll_from_folder(
        self,
        folder: str | Path,
        default_department: str = None,
        default_semester: str = None,
    ) -> List[Tuple[str, bool, str]]:
        """
        Expects files named like: STUDENTID_Name.jpg or STUDENTID.jpg
        Returns list of (filename, success, message)
        """
        folder = Path(folder)
        results = []
        for p in sorted(folder.glob("*.*")):
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
                continue
            stem = p.stem
            parts = stem.split("_", 1)
            student_id = parts[0].strip()
            name = parts[1].replace("_", " ").strip() if len(parts) > 1 else student_id

            ok, msg = self.enroll_from_image(
                p, student_id, name,
                department=default_department,
                semester=default_semester,
            )
            results.append((p.name, ok, msg))
        return results
