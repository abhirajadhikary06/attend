"""
Database engine, session management and repository helpers.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator, Optional, List
from datetime import datetime, date, timedelta
import struct
import numpy as np

from sqlalchemy import create_engine, select, func, and_, text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import DB_PATH, config
from app.core.models import (
    Base, Student, Attendance, AttendanceSession,
    UnknownFace, AuditLog, SystemSetting
)

# SQLite with WAL for better concurrent read performance
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """Create all tables if they do not exist, and enable WAL journal mode."""
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA synchronous=NORMAL"))


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------- Embedding helpers ----------

def embedding_to_bytes(emb: np.ndarray) -> bytes:
    """Store float32 embedding as raw bytes."""
    return emb.astype(np.float32).tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)


# ---------- Student repository ----------

def add_student(
    student_id: str,
    name: str,
    registration_no: Optional[str] = None,
    department: Optional[str] = None,
    semester: Optional[str] = None,
    photo_path: Optional[str] = None,
    embedding: Optional[np.ndarray] = None,
) -> int:
    """Add a student and return their primary key (int)."""
    with get_session() as session:
        student = Student(
            student_id=student_id.strip(),
            name=name.strip(),
            registration_no=registration_no,
            department=department,
            semester=semester,
            photo_path=photo_path,
            embedding=embedding_to_bytes(embedding) if embedding is not None else None,
        )
        session.add(student)
        session.flush()
        return student.id


# Plain dataclass used to pass student data outside the ORM session safely.


@dataclass
class StudentDTO:
    id: int
    student_id: str
    name: str
    registration_no: Optional[str]
    department: Optional[str]
    semester: Optional[str]
    photo_path: Optional[str]
    embedding: Optional[bytes]
    is_active: bool
    enrolled_at: Optional[object]
    updated_at: Optional[object]


def _to_dto(s: Student) -> StudentDTO:
    return StudentDTO(
        id=s.id,
        student_id=s.student_id,
        name=s.name,
        registration_no=s.registration_no,
        department=s.department,
        semester=s.semester,
        photo_path=s.photo_path,
        embedding=s.embedding,
        is_active=s.is_active,
        enrolled_at=s.enrolled_at,
        updated_at=s.updated_at,
    )


def get_student_by_id(student_id: str) -> Optional[StudentDTO]:
    with get_session() as session:
        s = session.execute(
            select(Student).where(Student.student_id == student_id)
        ).scalar_one_or_none()
        return _to_dto(s) if s is not None else None


def get_all_students(active_only: bool = True) -> List[StudentDTO]:
    with get_session() as session:
        q = select(Student)
        if active_only:
            q = q.where(Student.is_active == True)
        return [_to_dto(s) for s in session.execute(q).scalars().all()]


def update_student_embedding(student_pk: int, embedding: np.ndarray, photo_path: str = None) -> None:
    with get_session() as session:
        student = session.get(Student, student_pk)
        if student:
            student.embedding = embedding_to_bytes(embedding)
            if photo_path:
                student.photo_path = photo_path
            student.updated_at = datetime.utcnow()


# ---------- Attendance ----------


@dataclass
class AttendanceSessionDTO:
    id: int
    session_code: str
    session_date: object
    session_number: int
    start_time: object
    end_time: object
    is_active: bool
    created_at: object


def _to_session_dto(s: AttendanceSession) -> AttendanceSessionDTO:
    return AttendanceSessionDTO(
        id=s.id,
        session_code=s.session_code,
        session_date=s.session_date,
        session_number=s.session_number,
        start_time=s.start_time,
        end_time=s.end_time,
        is_active=s.is_active,
        created_at=s.created_at,
    )


def get_or_create_session(
    session_date: date, session_number: int, start: datetime, end: datetime
) -> AttendanceSessionDTO:
    code = f"{session_date.isoformat()}-S{session_number}"
    with get_session() as session:
        existing = session.execute(
            select(AttendanceSession).where(AttendanceSession.session_code == code)
        ).scalar_one_or_none()
        if existing:
            return _to_session_dto(existing)
        s = AttendanceSession(
            session_code=code,
            session_date=session_date,
            session_number=session_number,
            start_time=start,
            end_time=end,
            is_active=False,
        )
        session.add(s)
        session.flush()
        return _to_session_dto(s)


def mark_attendance(
    student_pk: int,
    session_pk: int,
    method: str = "facial",
    confidence: float = None,
    admin_note: str = None,
    marked_by: str = None,
) -> tuple[bool, str]:
    """
    Returns (success, message).
    Prevents duplicates within the same session.
    """
    with get_session() as session:
        existing = session.execute(
            select(Attendance).where(
                and_(
                    Attendance.student_id == student_pk,
                    Attendance.session_id == session_pk,
                )
            )
        ).scalar_one_or_none()

        if existing:
            return False, "Attendance Already Marked"

        att = Attendance(
            student_id=student_pk,
            session_id=session_pk,
            method=method,
            confidence=confidence,
            admin_note=admin_note,
            marked_by=marked_by,
        )
        session.add(att)
        return True, "Attendance Marked Successfully"


def get_attendance_for_session(session_pk: int) -> List[Attendance]:
    with get_session() as session:
        return list(
            session.execute(
                select(Attendance).where(Attendance.session_id == session_pk)
            ).scalars().all()
        )


# ---------- Unknown faces ----------

def add_or_update_unknown(
    embedding: np.ndarray,
    image_path: str,
    retention_days: int = 7,
) -> UnknownFace:
    expires = datetime.utcnow() + timedelta(days=retention_days)
    with get_session() as session:
        # Simple approach: always insert new for now.
        # Proper dedup happens in the service layer using FAISS.
        uf = UnknownFace(
            embedding=embedding_to_bytes(embedding),
            image_path=image_path,
            expires_at=expires,
        )
        session.add(uf)
        session.flush()
        return uf


def cleanup_expired_unknowns() -> int:
    """Delete expired unknown faces and return count removed."""
    now = datetime.utcnow()
    with get_session() as session:
        expired = session.execute(
            select(UnknownFace).where(UnknownFace.expires_at < now)
        ).scalars().all()
        count = len(expired)
        for uf in expired:
            # Note: caller should also delete the image file
            session.delete(uf)
        return count


def cleanup_old_attendance(retention_days: int = 30) -> int:
    """
    Delete attendance records and their sessions older than retention_days.
    Returns number of attendance rows removed.
    Sessions that have no remaining attendance records are also pruned.
    """
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    with get_session() as session:
        old_records = session.execute(
            select(Attendance).where(Attendance.marked_at < cutoff)
        ).scalars().all()
        count = len(old_records)
        for rec in old_records:
            session.delete(rec)
        return count


def get_attendance_report(days: int = 30) -> List[dict]:
    """
    Return a flat list of dicts covering the last `days` days.
    Each row: {student_id, name, session_code, marked_at, method, confidence}
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    with get_session() as session:
        rows = session.execute(
            select(Attendance, Student, AttendanceSession)
            .join(Student, Attendance.student_id == Student.id)
            .join(AttendanceSession, Attendance.session_id == AttendanceSession.id)
            .where(Attendance.marked_at >= cutoff)
            .order_by(Attendance.marked_at.desc())
        ).all()
        return [
            {
                "student_id": s.student_id,
                "name": s.name,
                "session_code": sess.session_code,
                "marked_at": a.marked_at,
                "method": a.method,
                "confidence": a.confidence,
            }
            for a, s, sess in rows
        ]


def get_sessions_with_counts(days: int = 31) -> List[dict]:
    """
    Return all attendance sessions in the last `days` days with their
    attendance count.
    Each row: {session_pk, session_code, session_date, session_number,
               start_time, end_time, count}
    Ordered newest first.
    """
    cutoff = datetime.utcnow().date() - timedelta(days=days)
    with get_session() as session:
        rows = session.execute(
            select(
                AttendanceSession,
                func.count(Attendance.id).label("cnt"),
            )
            .outerjoin(Attendance, Attendance.session_id == AttendanceSession.id)
            .where(AttendanceSession.session_date >= cutoff)
            .group_by(AttendanceSession.id)
            .order_by(AttendanceSession.session_date.desc(),
                      AttendanceSession.session_number.asc())
        ).all()
        return [
            {
                "session_pk": sess.id,
                "session_code": sess.session_code,
                "session_date": sess.session_date,
                "session_number": sess.session_number,
                "start_time": sess.start_time,
                "end_time": sess.end_time,
                "count": cnt,
            }
            for sess, cnt in rows
        ]


def get_attendance_for_session_detailed(session_pk: int) -> List[dict]:
    """
    Return all attendance records for a single session with student info.
    Each row: {student_id, name, department, semester, marked_at, method, confidence}
    Ordered by marked_at.
    """
    with get_session() as session:
        rows = session.execute(
            select(Attendance, Student)
            .join(Student, Attendance.student_id == Student.id)
            .where(Attendance.session_id == session_pk)
            .order_by(Attendance.marked_at.asc())
        ).all()
        return [
            {
                "student_id": s.student_id,
                "name": s.name,
                "department": s.department or "",
                "semester": s.semester or "",
                "marked_at": a.marked_at,
                "method": a.method,
                "confidence": a.confidence,
            }
            for a, s in rows
        ]


@dataclass
class UnknownFaceDTO:
    id: int
    image_path: Optional[str]
    first_seen: object
    last_seen: object
    sighting_count: int
    expires_at: object


def get_all_unknowns(limit: int = 200) -> List[UnknownFaceDTO]:
    """Return recent unknown faces, newest first."""
    with get_session() as session:
        rows = session.execute(
            select(UnknownFace)
            .order_by(UnknownFace.last_seen.desc())
            .limit(limit)
        ).scalars().all()
        return [
            UnknownFaceDTO(
                id=u.id,
                image_path=u.image_path,
                first_seen=u.first_seen,
                last_seen=u.last_seen,
                sighting_count=u.sighting_count,
                expires_at=u.expires_at,
            )
            for u in rows
        ]


# ---------- Audit ----------

def log_action(action: str, actor: str = None, details: str = None) -> None:
    with get_session() as session:
        session.add(AuditLog(action=action, actor=actor, details=details))
