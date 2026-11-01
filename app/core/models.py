"""
SQLAlchemy models for attend.
"""

from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, Boolean,
    Text, LargeBinary, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    registration_no = Column(String(50), unique=True, nullable=True)
    department = Column(String(100), nullable=True)
    semester = Column(String(20), nullable=True)
    photo_path = Column(String(500), nullable=True)
    embedding = Column(LargeBinary, nullable=True)          # encrypted or raw float32 bytes
    is_active = Column(Boolean, default=True)
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    attendances = relationship("Attendance", back_populates="student")

    def __repr__(self):
        return f"<Student {self.student_id}: {self.name}>"


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_code = Column(String(30), unique=True, nullable=False)  # e.g. 2026-11-01-S1
    session_date = Column(Date, nullable=False, index=True)
    session_number = Column(Integer, nullable=False)                # 1 or 2
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    attendances = relationship("Attendance", back_populates="session")

    def __repr__(self):
        return f"<Session {self.session_code}>"


class Attendance(Base):
    __tablename__ = "attendances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("attendance_sessions.id"), nullable=False)
    marked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    method = Column(String(20), default="facial")                   # facial / manual
    confidence = Column(Float, nullable=True)
    admin_note = Column(Text, nullable=True)
    marked_by = Column(String(100), nullable=True)                  # admin username for manual

    student = relationship("Student", back_populates="attendances")
    session = relationship("AttendanceSession", back_populates="attendances")

    __table_args__ = (
        UniqueConstraint("student_id", "session_id", name="uq_student_session"),
        Index("ix_attendance_marked_at", "marked_at"),
    )

    def __repr__(self):
        return f"<Attendance student={self.student_id} session={self.session_id}>"


class UnknownFace(Base):
    __tablename__ = "unknown_faces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    embedding = Column(LargeBinary, nullable=False)
    image_path = Column(String(500), nullable=True)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    sighting_count = Column(Integer, default=1)
    expires_at = Column(DateTime, nullable=False)
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<UnknownFace id={self.id} count={self.sighting_count}>"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    action = Column(String(100), nullable=False)
    actor = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    ip_or_host = Column(String(100), nullable=True)

    def __repr__(self):
        return f"<AuditLog {self.action} @ {self.timestamp}>"


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
