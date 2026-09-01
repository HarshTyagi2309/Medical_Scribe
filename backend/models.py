from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class ConsultationRecord(Base):

    __tablename__ = "consultations"

    # ========================================================
    # PRIMARY KEY
    # ========================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    # ========================================================
    # PATIENT
    # ========================================================

    patient_name: Mapped[str] = mapped_column(
        String(150),
        default="Not in audio",
    )

    patient_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # ========================================================
    # DUPLICATE PROTECTION
    # ========================================================

    audio_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    # ========================================================
    # DATE / TIME
    # ========================================================

    consultation_date: Mapped[str] = mapped_column(
        String(20)
    )

    consultation_time: Mapped[str] = mapped_column(
        String(20)
    )

    consultation_datetime: Mapped[str] = mapped_column(
        String(100)
    )

    # ========================================================
    # AUDIO
    # ========================================================

    original_audio_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    stored_audio_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    audio_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ========================================================
    # TRANSCRIPT
    # ========================================================

    transcript: Mapped[str] = mapped_column(
        Text
    )

    # ========================================================
    # CLINICAL INFORMATION
    # ========================================================

    chief_complaint: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    diagnosis: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ========================================================
    # VITALS
    # ========================================================

    blood_pressure: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    heart_rate: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    temperature: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    oxygen_saturation: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # ========================================================
    # JSON ARRAYS STORED AS TEXT
    # ========================================================

    symptoms: Mapped[str] = mapped_column(
        Text,
        default="[]",
    )

    medications: Mapped[str] = mapped_column(
        Text,
        default="[]",
    )

    recommended_tests: Mapped[str] = mapped_column(
        Text,
        default="[]",
    )

    doctor_instructions: Mapped[str] = mapped_column(
        Text,
        default="[]",
    )

    # ========================================================
    # FOLLOW UP
    # ========================================================

    follow_up: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


# ============================================================
# RECORD AUDIT / REVISION HISTORY
# ============================================================

class RecordAuditHistory(Base):

    __tablename__ = "record_audit_history"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    # Consultation record which was edited/deleted
    record_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
    )

    # EDIT / DELETE
    action: Mapped[str] = mapped_column(
        String(20),
        index=True,
    )

    # User who performed the action
    username: Mapped[str] = mapped_column(
        String(150),
    )

    role: Mapped[str] = mapped_column(
        String(50),
    )

    # Exact date + time
    timestamp: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )

    # Which fields were changed
    changed_fields: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Old values - later encrypted before saving
    old_values: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # New values - later encrypted before saving
    new_values: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Extra information such as audio deleted
    details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )