from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import ConsultationRecord
from backend.security import encrypt_text
from backend.services.secure_json_service import encrypt_json


def save_consultation_record(
    *,
    patient_name,
    patient_id,
    audio_hash,
    timestamp,
    stored_filename,
    stored_path,
    transcript,
    clinical_data,
):
    db: Session = SessionLocal()

    try:
        vitals = clinical_data.get("vitals") or {}

        record = ConsultationRecord(
            patient_name=encrypt_text(patient_name),
            patient_id=patient_id,
            audio_hash=audio_hash,
            consultation_date=timestamp["date"],
            consultation_time=timestamp["time"],
            consultation_datetime=timestamp["datetime"],
            original_audio_filename=None,
            stored_audio_filename=stored_filename,
            audio_path=str(stored_path),
            transcript=encrypt_text(transcript),
            chief_complaint=encrypt_text(
                clinical_data.get("chief_complaint")
            ),
            diagnosis=encrypt_text(
                clinical_data.get("diagnosis")
            ),
            blood_pressure=encrypt_text(
                vitals.get("blood_pressure")
            ),
            heart_rate=encrypt_text(
                vitals.get("heart_rate")
            ),
            temperature=encrypt_text(
                vitals.get("temperature")
            ),
            oxygen_saturation=encrypt_text(
                vitals.get("oxygen_saturation")
            ),
            symptoms=encrypt_json(
                clinical_data.get("symptoms", [])
            ),
            medications=encrypt_json(
                clinical_data.get("medications", [])
            ),
            recommended_tests=encrypt_json(
                clinical_data.get("recommended_tests", [])
            ),
            doctor_instructions=encrypt_json(
                clinical_data.get("doctor_instructions", [])
            ),
            follow_up=encrypt_text(
                clinical_data.get("follow_up")
            ),
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return record.id

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
