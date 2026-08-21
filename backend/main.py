import hashlib
import json
import os
import uuid

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
)

from fastapi.middleware.cors import CORSMiddleware

from langfuse import propagate_attributes

from pydantic import BaseModel

from sqlalchemy import inspect, or_, text
from sqlalchemy.orm import Session

from backend.clinical_extractor import (
    extract_clinical_data,
)

from backend.database import (
    Base,
    SessionLocal,
    engine,
)

from backend.langfuse_service import (
    flush_langfuse,
    get_langfuse_client,
    should_capture_clinical_data,
)

from backend.models import ConsultationRecord

from backend.transcription import (
    transcribe_audio,
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)


STORAGE_DIR_ENV = os.getenv(
    "STORAGE_DIR",
    "",
).strip()


if STORAGE_DIR_ENV:

    STORAGE_ROOT = Path(
        STORAGE_DIR_ENV
    )

    RECORDINGS_DIR = (
        STORAGE_ROOT
        / "recordings"
    )

else:

    RECORDINGS_DIR = (
        PROJECT_ROOT
        / "recordings"
    )


RECORDINGS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# DATABASE TABLES
# ============================================================

Base.metadata.create_all(
    bind=engine
)


# ============================================================
# DATABASE MIGRATION
# ============================================================

def ensure_database_schema():

    inspector = inspect(
        engine
    )

    if (
        "consultations"
        not in inspector.get_table_names()
    ):
        return

    existing_columns = {
        column["name"]

        for column in inspector.get_columns(
            "consultations"
        )
    }

    with engine.begin() as connection:

        if (
            "patient_name"
            not in existing_columns
        ):

            connection.execute(
                text(
                    """
                    ALTER TABLE consultations
                    ADD COLUMN patient_name VARCHAR(150)
                    DEFAULT 'Not in audio'
                    """
                )
            )

        if (
            "patient_id"
            not in existing_columns
        ):

            connection.execute(
                text(
                    """
                    ALTER TABLE consultations
                    ADD COLUMN patient_id VARCHAR(100)
                    """
                )
            )

        if (
            "audio_hash"
            not in existing_columns
        ):

            connection.execute(
                text(
                    """
                    ALTER TABLE consultations
                    ADD COLUMN audio_hash VARCHAR(64)
                    """
                )
            )


ensure_database_schema()


# ============================================================
# CONFIG
# ============================================================

INDIA_TIMEZONE = ZoneInfo(
    "Asia/Kolkata"
)


MAX_AUDIO_SIZE_MB = 25


MAX_AUDIO_SIZE_BYTES = (
    MAX_AUDIO_SIZE_MB
    * 1024
    * 1024
)


ALLOWED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".ogg",
    ".webm",
}


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Medical Scribe API",

    description=(
        "AI-powered doctor-patient "
        "conversation processing backend"
    ),

    version="1.5.0",
)


# ============================================================
# CORS
# ============================================================

ALLOWED_ORIGINS = (
    os.getenv(
        "ALLOWED_ORIGINS",
        (
            "http://localhost:8501,"
            "http://127.0.0.1:8501"
        ),
    )
    .split(",")
)


app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        origin.strip()

        for origin in ALLOWED_ORIGINS

        if origin.strip()
    ],

    allow_credentials=True,

    allow_methods=[
        "GET",
        "POST",
    ],

    allow_headers=["*"],
)


# ============================================================
# REQUEST MODELS
# ============================================================

class TranscriptRequest(
    BaseModel
):

    transcript: str


# ============================================================
# HELPERS
# ============================================================

def get_consultation_timestamp():

    now = datetime.now(
        INDIA_TIMEZONE
    )

    return {
        "consultation_date": (
            now.strftime(
                "%d-%m-%Y"
            )
        ),

        "consultation_time": (
            now.strftime(
                "%I:%M %p"
            )
        ),

        "consultation_datetime": (
            now.isoformat()
        ),
    }


def generate_patient_id():

    return (
        "PAT-"
        + uuid.uuid4()
        .hex[:8]
        .upper()
    )


def generate_audio_hash(
    audio_bytes: bytes
) -> str:

    return (
        hashlib
        .sha256(
            audio_bytes
        )
        .hexdigest()
    )


def validate_audio(
    filename: str,
    audio_bytes: bytes,
):

    if not audio_bytes:

        raise HTTPException(
            status_code=400,
            detail=(
                "Uploaded audio file is empty."
            ),
        )

    if (
        len(audio_bytes)
        > MAX_AUDIO_SIZE_BYTES
    ):

        raise HTTPException(
            status_code=413,

            detail=(
                "Audio file is too large. "
                f"Maximum allowed size is "
                f"{MAX_AUDIO_SIZE_MB} MB."
            ),
        )

    extension = (
        Path(filename)
        .suffix
        .lower()
    )

    if (
        extension
        not in ALLOWED_EXTENSIONS
    ):

        raise HTTPException(
            status_code=400,

            detail=(
                "Unsupported audio format. "
                "Use WAV, MP3, M4A, "
                "OGG or WEBM."
            ),
        )


# ============================================================
# AUDIO STORAGE
# ============================================================

def save_audio_file(
    audio_bytes: bytes,
    original_filename: str,
):

    extension = (
        Path(
            original_filename
        )
        .suffix
        .lower()
        or ".wav"
    )

    unique_filename = (
        f"{uuid.uuid4()}"
        f"{extension}"
    )

    file_path = (
        RECORDINGS_DIR
        / unique_filename
    )

    with open(
        file_path,
        "wb",
    ) as file:

        file.write(
            audio_bytes
        )

    return (
        unique_filename,
        str(file_path),
    )


# ============================================================
# SAVE DATABASE RECORD
# ============================================================

def save_consultation_record(
    *,
    patient_name,
    patient_id,
    audio_hash,
    filename,
    stored_audio_filename,
    audio_path,
    timestamp,
    transcript,
    clinical_data,
):

    db: Session = (
        SessionLocal()
    )

    try:

        vitals = clinical_data.get(
            "vitals",
            {},
        )

        record = ConsultationRecord(

            patient_name=patient_name,

            patient_id=patient_id,

            audio_hash=audio_hash,

            consultation_date=(
                timestamp[
                    "consultation_date"
                ]
            ),

            consultation_time=(
                timestamp[
                    "consultation_time"
                ]
            ),

            consultation_datetime=(
                timestamp[
                    "consultation_datetime"
                ]
            ),

            original_audio_filename=(
                filename
            ),

            stored_audio_filename=(
                stored_audio_filename
            ),

            audio_path=(
                audio_path
            ),

            transcript=transcript,

            chief_complaint=(
                clinical_data.get(
                    "chief_complaint"
                )
            ),

            diagnosis=(
                clinical_data.get(
                    "diagnosis"
                )
            ),

            blood_pressure=(
                vitals.get(
                    "blood_pressure"
                )
            ),

            heart_rate=(
                vitals.get(
                    "heart_rate"
                )
            ),

            temperature=(
                vitals.get(
                    "temperature"
                )
            ),

            oxygen_saturation=(
                vitals.get(
                    "oxygen_saturation"
                )
            ),

            symptoms=json.dumps(
                clinical_data.get(
                    "symptoms",
                    [],
                )
            ),

            medications=json.dumps(
                clinical_data.get(
                    "medications",
                    [],
                )
            ),

            recommended_tests=json.dumps(
                clinical_data.get(
                    "recommended_tests",
                    [],
                )
            ),

            doctor_instructions=json.dumps(
                clinical_data.get(
                    "doctor_instructions",
                    [],
                )
            ),

            follow_up=(
                clinical_data.get(
                    "follow_up"
                )
            ),
        )

        db.add(
            record
        )

        db.commit()

        db.refresh(
            record
        )

        return record.id

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()


# ============================================================
# RECORD SERIALIZER
# ============================================================

def serialize_record(
    record
):

    return {
        "id": record.id,

        "patient_name": (
            record.patient_name
            or "Not in audio"
        ),

        "patient_id": (
            record.patient_id
        ),

        "consultation_date": (
            record.consultation_date
        ),

        "consultation_time": (
            record.consultation_time
        ),

        "consultation_datetime": (
            record.consultation_datetime
        ),

        "original_audio_filename": (
            record.original_audio_filename
        ),

        "stored_audio_filename": (
            record.stored_audio_filename
        ),

        "transcript": (
            record.transcript
        ),

        "chief_complaint": (
            record.chief_complaint
        ),

        "diagnosis": (
            record.diagnosis
        ),

        "vitals": {
            "blood_pressure": (
                record.blood_pressure
            ),

            "heart_rate": (
                record.heart_rate
            ),

            "temperature": (
                record.temperature
            ),

            "oxygen_saturation": (
                record.oxygen_saturation
            ),
        },

        "symptoms": json.loads(
            record.symptoms
            or "[]"
        ),

        "medications": json.loads(
            record.medications
            or "[]"
        ),

        "recommended_tests": json.loads(
            record.recommended_tests
            or "[]"
        ),

        "doctor_instructions": json.loads(
            record.doctor_instructions
            or "[]"
        ),

        "follow_up": (
            record.follow_up
        ),
    }


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "status": "success",

        "message": (
            "Medical Scribe backend is running"
        ),

        "environment": (
            "cloud"
            if STORAGE_DIR_ENV
            else "local"
        ),
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health_check():

    return {
        "status": "healthy",

        "version": "1.5.0",

        "langfuse_enabled": True,

        "storage_mode": (
            "persistent-cloud"
            if STORAGE_DIR_ENV
            else "local"
        ),
    }


# ============================================================
# TRANSCRIBE
# ============================================================

@app.post("/transcribe")
async def transcribe_consultation(
    audio: UploadFile = File(...)
):

    try:

        original_filename = (
            audio.filename
            or "consultation.wav"
        )

        audio_bytes = (
            await audio.read()
        )

        validate_audio(
            original_filename,
            audio_bytes,
        )

        transcript = transcribe_audio(
            audio_bytes=audio_bytes,
            filename=original_filename,
        )

        return {
            "status": "success",

            "filename": (
                original_filename
            ),

            "transcript": (
                transcript
            ),
        }

    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


# ============================================================
# EXTRACT
# ============================================================

@app.post("/extract")
def extract_consultation(
    request: TranscriptRequest
):

    try:

        transcript = (
            request.transcript
            .strip()
        )

        if not transcript:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Transcript cannot be empty."
                ),
            )

        clinical_data = (
            extract_clinical_data(
                transcript
            )
        )

        timestamp = (
            get_consultation_timestamp()
        )

        return {
            "status": "success",

            **timestamp,

            "clinical_data": (
                clinical_data
            ),
        }

    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


# ============================================================
# PROCESS CONSULTATION
# ============================================================

@app.post(
    "/process-consultation"
)
async def process_consultation(
    audio: UploadFile = File(...)
):

    langfuse = (
        get_langfuse_client()
    )

    consultation_session_id = (
        str(
            uuid.uuid4()
        )
    )

    original_filename = (
        audio.filename
        or "consultation.wav"
    )

    try:

        # ====================================================
        # READ + VALIDATE AUDIO
        # ====================================================

        audio_bytes = (
            await audio.read()
        )

        validate_audio(
            original_filename,
            audio_bytes,
        )


        # ====================================================
        # DUPLICATE CHECK
        # ====================================================

        audio_hash = (
            generate_audio_hash(
                audio_bytes
            )
        )

        db = SessionLocal()

        try:

            existing_record = (

                db.query(
                    ConsultationRecord
                )

                .filter(
                    ConsultationRecord.audio_hash
                    == audio_hash
                )

                .first()
            )

        finally:

            db.close()


        if existing_record:

            return {
                "status": "duplicate",

                "duplicate": True,

                "message": (
                    "This consultation audio "
                    "has already been processed."
                ),

                "record_id": (
                    existing_record.id
                ),

                "patient_name": (
                    existing_record.patient_name
                    or "Not in audio"
                ),

                "patient_id": (
                    existing_record.patient_id
                ),
            }


        # ====================================================
        # LANGFUSE ROOT
        # ====================================================

        with (
            langfuse
            .start_as_current_observation(

                as_type="span",

                name="medical-consultation",

                input={
                    "filename": (
                        original_filename
                    ),

                    "audio_size_bytes": (
                        len(audio_bytes)
                    ),

                    "clinical_content_logged": (
                        should_capture_clinical_data()
                    ),
                },

            )
        ) as consultation_span:


            with propagate_attributes(

                trace_name=(
                    "medical-consultation"
                ),

                session_id=(
                    consultation_session_id
                ),

                metadata={
                    "application": (
                        "Medical Scribe AI"
                    ),

                    "backend": (
                        "FastAPI"
                    ),

                    "database": (
                        "SQLite"
                    ),

                    "deployment": (
                        "cloud"
                        if STORAGE_DIR_ENV
                        else "local"
                    ),
                },

                tags=[
                    "medical-scribe",
                    "doctor-patient",
                    "consultation",
                ],
            ):


                # ============================================
                # TRANSCRIPTION
                # ============================================

                transcript = (
                    transcribe_audio(
                        audio_bytes=(
                            audio_bytes
                        ),

                        filename=(
                            original_filename
                        ),
                    )
                )


                # ============================================
                # CLINICAL EXTRACTION
                # ============================================

                clinical_data = (
                    extract_clinical_data(
                        transcript
                    )
                )


                # ============================================
                # PATIENT
                # ============================================

                patient_name = (
                    clinical_data.get(
                        "patient_name"
                    )
                    or "Not in audio"
                )

                patient_id = (
                    generate_patient_id()
                )


                # ============================================
                # DATE / TIME
                # ============================================

                timestamp = (
                    get_consultation_timestamp()
                )


                # ============================================
                # SAVE AUDIO
                # ============================================

                with (
                    langfuse
                    .start_as_current_observation(

                        as_type="span",

                        name="audio-storage",

                    )
                ) as audio_span:


                    (
                        stored_audio_filename,
                        audio_path,
                    ) = save_audio_file(

                        audio_bytes=(
                            audio_bytes
                        ),

                        original_filename=(
                            original_filename
                        ),
                    )


                    audio_span.update(
                        output={
                            "stored": True,

                            "stored_filename": (
                                stored_audio_filename
                            ),
                        }
                    )


                # ============================================
                # SAVE DATABASE
                # ============================================

                with (
                    langfuse
                    .start_as_current_observation(

                        as_type="span",

                        name="database-save",

                    )
                ) as database_span:


                    record_id = (
                        save_consultation_record(

                            patient_name=(
                                patient_name
                            ),

                            patient_id=(
                                patient_id
                            ),

                            audio_hash=(
                                audio_hash
                            ),

                            filename=(
                                original_filename
                            ),

                            stored_audio_filename=(
                                stored_audio_filename
                            ),

                            audio_path=(
                                audio_path
                            ),

                            timestamp=(
                                timestamp
                            ),

                            transcript=(
                                transcript
                            ),

                            clinical_data=(
                                clinical_data
                            ),
                        )
                    )


                    database_span.update(
                        output={
                            "database_saved": True,

                            "record_id": (
                                record_id
                            ),
                        }
                    )


                consultation_span.update(
                    output={
                        "record_id": (
                            record_id
                        ),

                        "database_saved": True,

                        "patient_name_present": (
                            patient_name
                            != "Not in audio"
                        ),
                    }
                )


                response_data = {
                    "status": "success",

                    "duplicate": False,

                    "record_id": (
                        record_id
                    ),

                    "patient_name": (
                        patient_name
                    ),

                    "patient_id": (
                        patient_id
                    ),

                    "session_id": (
                        consultation_session_id
                    ),

                    "filename": (
                        original_filename
                    ),

                    **timestamp,

                    "transcript": (
                        transcript
                    ),

                    "clinical_data": (
                        clinical_data
                    ),

                    "database_saved": True,
                }


        return response_data


    except HTTPException:

        raise


    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


    finally:

        flush_langfuse()


# ============================================================
# SEARCH / HISTORY
# ============================================================

@app.get("/records")
def get_consultation_records(

    q: str | None = Query(
        default=None
    )
):

    db: Session = (
        SessionLocal()
    )

    try:

        query = db.query(
            ConsultationRecord
        )

        if q and q.strip():

            search_term = (
                f"%{q.strip()}%"
            )

            query = query.filter(

                or_(

                    ConsultationRecord
                    .patient_name
                    .ilike(
                        search_term
                    ),

                    ConsultationRecord
                    .patient_id
                    .ilike(
                        search_term
                    ),

                    ConsultationRecord
                    .chief_complaint
                    .ilike(
                        search_term
                    ),

                    ConsultationRecord
                    .diagnosis
                    .ilike(
                        search_term
                    ),
                )
            )

        records = (

            query

            .order_by(
                ConsultationRecord
                .id
                .desc()
            )

            .all()
        )

        return {
            "status": "success",

            "total": len(
                records
            ),

            "records": [
                serialize_record(
                    record
                )

                for record in records
            ],
        }

    finally:

        db.close()


# ============================================================
# SINGLE RECORD
# ============================================================

@app.get(
    "/records/{record_id}"
)
def get_consultation_record(
    record_id: int
):

    db: Session = (
        SessionLocal()
    )

    try:

        record = (

            db.query(
                ConsultationRecord
            )

            .filter(
                ConsultationRecord.id
                == record_id
            )

            .first()
        )

        if record is None:

            raise HTTPException(
                status_code=404,

                detail=(
                    "Consultation record not found."
                ),
            )

        return {
            "status": "success",

            "record": (
                serialize_record(
                    record
                )
            ),
        }

    finally:

        db.close()