import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from langfuse import propagate_attributes
from pydantic import BaseModel
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from backend.login_service import router as login_router, initialize_default_users

from backend.audit_service import audit_event
from backend.clinical_extractor import extract_clinical_data
from backend.database import Base, SessionLocal, engine
from backend.langfuse_service import (
    flush_langfuse,
    get_langfuse_client,
    should_capture_clinical_data,
)
from backend.models import ConsultationRecord
from backend.security import (
    decrypt_text,
    encrypt_bytes,
    encrypt_text,
    require_doctor,
    require_doctor_or_admin,

    require_admin,)
from backend.transcription import transcribe_audio


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

STORAGE_DIR_ENV = os.getenv(
    "STORAGE_DIR",
    "",
).strip()

if STORAGE_DIR_ENV:
    STORAGE_ROOT = Path(STORAGE_DIR_ENV)
    RECORDINGS_DIR = STORAGE_ROOT / "recordings"
else:
    RECORDINGS_DIR = PROJECT_ROOT / "recordings"

RECORDINGS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# DATABASE
# ============================================================

Base.metadata.create_all(
    bind=engine
)


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

    required_columns = {
        "patient_name": "VARCHAR(150)",
        "patient_id": "VARCHAR(100)",
        "audio_hash": "VARCHAR(64)",
    }

    with engine.begin() as connection:

        for (
            column_name,
            column_type,
        ) in required_columns.items():

            if (
                column_name
                not in existing_columns
            ):

                connection.execute(
                    text(
                        f"""
                        ALTER TABLE consultations
                        ADD COLUMN {column_name} {column_type}
                        """
                    )
                )


ensure_database_schema()


# ============================================================
# CONSTANTS
# ============================================================

INDIA_TIMEZONE = ZoneInfo(
    "Asia/Kolkata"
)

MAX_AUDIO_SIZE = (
    25
    * 1024
    * 1024
)

ALLOWED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".ogg",
    ".webm",
}


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="Medical Scribe API",
    version="2.4.0",
    description=(
        "AI-assisted clinical consultation transcription "
        "and structured data extraction."
    ),
)


# ============================================================
# SECURITY HEADERS
# ============================================================

@app.middleware("http")
async def add_security_headers(
    request: Request,
    call_next,
):

    response = await call_next(
        request
    )

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "DENY"

    response.headers[
        "Referrer-Policy"
    ] = "no-referrer"

    response.headers[
        "Permissions-Policy"
    ] = (
        "camera=(), "
        "geolocation=(), "
        "microphone=()"
    )

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return response




# ============================================================
# AUTHENTICATION ROUTER
# ============================================================

app.include_router(login_router)

# ============================================================
# CORS
# ============================================================

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8501,"
        "http://127.0.0.1:8501",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "DELETE",
    ],
    allow_headers=[
        "Content-Type",
        "X-API-Key",
        "Authorization",
    ],
)



# ============================================================
# LOGIN USERS INITIALIZATION
# ============================================================

initialize_default_users()

# ============================================================
# REQUEST MODELS
# ============================================================

class TranscriptRequest(
    BaseModel
):
    transcript: str


class VitalsUpdate(
    BaseModel
):
    blood_pressure: str | None = None
    heart_rate: str | None = None
    temperature: str | None = None
    oxygen_saturation: str | None = None


class RecordUpdateRequest(
    BaseModel
):

    patient_name: str | None = None

    transcript: str | None = None

    chief_complaint: str | None = None

    diagnosis: str | None = None

    symptoms: list | None = None

    medications: list | None = None

    recommended_tests: list | None = None

    doctor_instructions: list | None = None

    follow_up: str | None = None

    vitals: VitalsUpdate | None = None


# ============================================================
# TIME HELPERS
# ============================================================

def get_timestamp():

    now = datetime.now(
        INDIA_TIMEZONE
    )

    return {
        "date": now.strftime(
            "%d-%m-%Y"
        ),
        "time": now.strftime(
            "%I:%M %p"
        ),
        "datetime": now.isoformat(),
    }


# ============================================================
# PATIENT HELPERS
# ============================================================

def generate_patient_id():

    return (
        "PAT-"
        + uuid.uuid4().hex[
            :8
        ].upper()
    )


# ============================================================
# AUDIO HELPERS
# ============================================================

def calculate_audio_hash(
    audio_bytes: bytes,
):

    return hashlib.sha256(
        audio_bytes
    ).hexdigest()


def validate_audio(
    audio_bytes: bytes,
    filename: str,
):

    if not audio_bytes:

        raise HTTPException(
            status_code=400,
            detail="Audio file is empty.",
        )

    if (
        len(audio_bytes)
        > MAX_AUDIO_SIZE
    ):

        raise HTTPException(
            status_code=413,
            detail=(
                "Audio file is too large. "
                "Maximum size is 25 MB."
            ),
        )

    extension = Path(
        filename
    ).suffix.lower()

    if (
        extension
        not in ALLOWED_AUDIO_EXTENSIONS
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported audio format."
            ),
        )

    return extension


def save_encrypted_audio_file(
    audio_bytes: bytes,
):

    encrypted_audio = (
        encrypt_bytes(
            audio_bytes
        )
    )

    stored_filename = (
        f"{uuid.uuid4().hex}.audio.enc"
    )

    stored_path = (
        RECORDINGS_DIR
        / stored_filename
    )

    with open(
        stored_path,
        "wb",
    ) as file:

        file.write(
            encrypted_audio
        )

    return (
        stored_filename,
        stored_path,
    )


# ============================================================
# JSON HELPERS
# ============================================================

def json_dumps(
    value,
):

    return json.dumps(
        value,
        ensure_ascii=False,
    )


def json_loads_safe(
    value,
    default,
):

    if value is None:
        return default

    try:

        return json.loads(
            value
        )

    except Exception:

        return default


# ============================================================
# ENCRYPTION HELPERS
# ============================================================

def encrypt_json(
    value,
):

    return encrypt_text(
        json_dumps(
            value
        )
    )


def decrypt_json(
    value,
    default,
):

    decrypted_value = (
        decrypt_text(
            value
        )
    )

    return json_loads_safe(
        decrypted_value,
        default,
    )


# ============================================================
# DATABASE SAVE
# ============================================================

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

    db: Session = (
        SessionLocal()
    )

    try:

        vitals = (
            clinical_data.get(
                "vitals"
            )
            or {}
        )

        record = ConsultationRecord(

            patient_name=encrypt_text(
                patient_name
            ),

            patient_id=patient_id,

            audio_hash=audio_hash,

            consultation_date=(
                timestamp["date"]
            ),

            consultation_time=(
                timestamp["time"]
            ),

            consultation_datetime=(
                timestamp["datetime"]
            ),

            original_audio_filename=None,

            stored_audio_filename=(
                stored_filename
            ),

            audio_path=str(
                stored_path
            ),

            transcript=encrypt_text(
                transcript
            ),

            chief_complaint=encrypt_text(
                clinical_data.get(
                    "chief_complaint"
                )
            ),

            diagnosis=encrypt_text(
                clinical_data.get(
                    "diagnosis"
                )
            ),

            blood_pressure=encrypt_text(
                vitals.get(
                    "blood_pressure"
                )
            ),

            heart_rate=encrypt_text(
                vitals.get(
                    "heart_rate"
                )
            ),

            temperature=encrypt_text(
                vitals.get(
                    "temperature"
                )
            ),

            oxygen_saturation=encrypt_text(
                vitals.get(
                    "oxygen_saturation"
                )
            ),

            symptoms=encrypt_json(
                clinical_data.get(
                    "symptoms",
                    [],
                )
            ),

            medications=encrypt_json(
                clinical_data.get(
                    "medications",
                    [],
                )
            ),

            recommended_tests=encrypt_json(
                clinical_data.get(
                    "recommended_tests",
                    [],
                )
            ),

            doctor_instructions=encrypt_json(
                clinical_data.get(
                    "doctor_instructions",
                    [],
                )
            ),

            follow_up=encrypt_text(
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
# SERIALIZATION
# ============================================================

def serialize_record(
    record,
):

    return {

        "id": record.id,

        "patient_name": (
            decrypt_text(
                record.patient_name
            )
            or "Not in audio"
        ),

        "patient_id": (
            record.patient_id
        ),

        "date": (
            record.consultation_date
        ),

        "time": (
            record.consultation_time
        ),

        "datetime": (
            record.consultation_datetime
        ),

        "stored_audio_filename": (
            record.stored_audio_filename
        ),

        "transcript": (
            decrypt_text(
                record.transcript
            )
            or ""
        ),

        "chief_complaint": (
            decrypt_text(
                record.chief_complaint
            )
        ),

        "diagnosis": (
            decrypt_text(
                record.diagnosis
            )
        ),

        "vitals": {

            "blood_pressure": (
                decrypt_text(
                    record.blood_pressure
                )
            ),

            "heart_rate": (
                decrypt_text(
                    record.heart_rate
                )
            ),

            "temperature": (
                decrypt_text(
                    record.temperature
                )
            ),

            "oxygen_saturation": (
                decrypt_text(
                    record.oxygen_saturation
                )
            ),
        },

        "symptoms": decrypt_json(
            record.symptoms,
            [],
        ),

        "medications": decrypt_json(
            record.medications,
            [],
        ),

        "recommended_tests": decrypt_json(
            record.recommended_tests,
            [],
        ),

        "doctor_instructions": decrypt_json(
            record.doctor_instructions,
            [],
        ),

        "follow_up": decrypt_text(
            record.follow_up
        ),
    }


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "service": (
            "Medical Scribe API"
        ),
        "status": "running",
        "version": "2.4.0",
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    langfuse_configured = bool(
        os.getenv(
            "LANGFUSE_PUBLIC_KEY"
        )
        and os.getenv(
            "LANGFUSE_SECRET_KEY"
        )
    )

    return {

        "status": "healthy",

        "version": "2.4.0",

        "langfuse_enabled": (
            langfuse_configured
        ),

        "clinical_data_logging": (
            should_capture_clinical_data()
        ),

        "storage_mode": (
            "custom"
            if STORAGE_DIR_ENV
            else "local"
        ),

        "security": {
            "api_key_required": True,
            "encrypted_storage": True,
            "audit_logging": True,
            "doctor_correction": True,
            "rbac_enabled": True,
        },
    }


# ============================================================
# TRANSCRIBE
# ============================================================

@app.post(
    "/transcribe",
    dependencies=[
        Depends(
            require_doctor
        )
    ],
)
async def transcribe(
    audio: UploadFile = File(...),
):

    try:

        audio_bytes = (
            await audio.read()
        )

        filename = (
            audio.filename
            or "audio.wav"
        )

        validate_audio(
            audio_bytes,
            filename,
        )

        transcript = (
            transcribe_audio(
                audio_bytes,
                filename,
            )
        )

        audit_event(
            action="transcription_completed",
            status="success",
            component="transcription",
        )

        return {
            "transcript": transcript
        }

    except HTTPException:
        raise

    except Exception as error:

        audit_event(
            action="transcription_failed",
            status="failed",
            component="transcription",
            error_type=(
                type(error).__name__
            ),
        )

        print(
            "Transcription error:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Audio transcription failed."
            ),
        )


# ============================================================
# EXTRACT
# ============================================================

@app.post(
    "/extract",
    dependencies=[
        Depends(
            require_doctor
        )
    ],
)
def extract(
    request: TranscriptRequest,
):

    try:

        transcript = (
            request.transcript
            or ""
        ).strip()

        if not transcript:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Transcript is required."
                ),
            )

        clinical_data = (
            extract_clinical_data(
                transcript
            )
        )

        timestamp = (
            get_timestamp()
        )

        audit_event(
            action="extraction_completed",
            status="success",
            component="clinical_extraction",
        )

        return {

            "clinical_data": (
                clinical_data
            ),

            "timestamp": (
                timestamp
            ),
        }

    except HTTPException:
        raise

    except Exception as error:

        audit_event(
            action="extraction_failed",
            status="failed",
            component="clinical_extraction",
            error_type=(
                type(error).__name__
            ),
        )

        print(
            "Clinical extraction error:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Clinical extraction failed."
            ),
        )


# ============================================================
# PROCESS CONSULTATION
# ============================================================

@app.post(
    "/process-consultation",
    dependencies=[
        Depends(
            require_doctor
        )
    ],
)
async def process_consultation(
    audio: UploadFile = File(...),
):

    langfuse = None
    consultation_session_id = None

    try:

        consultation_session_id = (
            str(
                uuid.uuid4()
            )
        )

        audit_event(
            action="consultation_started",
            status="success",
            session_id=(
                consultation_session_id
            ),
        )

        audio_bytes = (
            await audio.read()
        )

        filename = (
            audio.filename
            or "audio.wav"
        )

        validate_audio(
            audio_bytes,
            filename,
        )

        audio_hash = (
            calculate_audio_hash(
                audio_bytes
            )
        )


        # ====================================================
        # DUPLICATE CHECK
        # ====================================================

        db = SessionLocal()

        try:

            duplicate = (
                db.query(
                    ConsultationRecord
                )
                .filter(
                    ConsultationRecord.audio_hash
                    == audio_hash
                )
                .first()
            )

            if duplicate:

                audit_event(
                    action="duplicate_detected",
                    status="success",
                    session_id=(
                        consultation_session_id
                    ),
                    record_id=(
                        duplicate.id
                    ),
                )

                return {

                    "duplicate": True,

                    "record_id": (
                        duplicate.id
                    ),

                    "patient_name": (
                        decrypt_text(
                            duplicate.patient_name
                        )
                        or "Not in audio"
                    ),

                    "patient_id": (
                        duplicate.patient_id
                    ),
                }

        finally:

            db.close()


        # ====================================================
        # LANGFUSE
        # ====================================================

        try:

            langfuse = (
                get_langfuse_client()
            )

        except Exception:

            langfuse = None


        # ====================================================
        # PIPELINE
        # ====================================================

        def run_pipeline():

            transcript = (
                transcribe_audio(
                    audio_bytes,
                    filename,
                )
            )

            audit_event(
                action="transcription_completed",
                status="success",
                session_id=(
                    consultation_session_id
                ),
                component="transcription",
            )

            clinical_data = (
                extract_clinical_data(
                    transcript
                )
            )

            audit_event(
                action="extraction_completed",
                status="success",
                session_id=(
                    consultation_session_id
                ),
                component=(
                    "clinical_extraction"
                ),
            )

            patient_name = (
                clinical_data.get(
                    "patient_name"
                )
                or "Not in audio"
            )

            patient_id = (
                generate_patient_id()
            )

            timestamp = (
                get_timestamp()
            )

            (
                stored_filename,
                stored_path,
            ) = save_encrypted_audio_file(
                audio_bytes
            )

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

                    timestamp=(
                        timestamp
                    ),

                    stored_filename=(
                        stored_filename
                    ),

                    stored_path=(
                        stored_path
                    ),

                    transcript=(
                        transcript
                    ),

                    clinical_data=(
                        clinical_data
                    ),
                )
            )

            audit_event(
                action="consultation_saved",
                status="success",
                session_id=(
                    consultation_session_id
                ),
                record_id=(
                    record_id
                ),
                component="database",
            )

            return {

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

                "timestamp": (
                    timestamp
                ),

                "transcript": (
                    transcript
                ),

                "clinical_data": (
                    clinical_data
                ),
            }


        # ====================================================
        # LANGFUSE ROOT TRACE
        # ====================================================

        if langfuse:

            with (
                langfuse
                .start_as_current_observation(
                    name="medical-consultation",
                    as_type="span",
                    input={
                        "audio_size_bytes": (
                            len(
                                audio_bytes
                            )
                        ),
                        "clinical_content_logged": (
                            should_capture_clinical_data()
                        ),
                    },
                )
                as root_span
            ):

                with propagate_attributes(

                    trace_name=(
                        "medical-consultation"
                    ),

                    session_id=(
                        consultation_session_id
                    ),

                    metadata={
                        "app": (
                            "Medical Scribe AI"
                        ),
                        "backend": (
                            "FastAPI"
                        ),
                        "database": (
                            "SQLite"
                        ),
                        "encrypted_storage": (
                            True
                        ),
                        "audit_logging": (
                            True
                        ),
                        "rbac_enabled": (
                            True
                        ),
                    },

                    tags=[
                        "medical-scribe",
                        "consultation",
                        "privacy-safe",
                    ],
                ):

                    result = (
                        run_pipeline()
                    )

                    root_span.update(
                        output={
                            "success": True,
                            "record_id": (
                                result[
                                    "record_id"
                                ]
                            ),
                            "patient_name_logged": (
                                False
                            ),
                        }
                    )

        else:

            result = (
                run_pipeline()
            )

        return result

    except HTTPException:

        raise

    except Exception as error:

        audit_event(
            action="consultation_failed",
            status="failed",
            session_id=(
                consultation_session_id
            ),
            component=(
                "consultation_pipeline"
            ),
            error_type=(
                type(error).__name__
            ),
        )

        print(
            "Process consultation error:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Consultation processing failed."
            ),
        )

    finally:

        if langfuse:

            flush_langfuse()


# ============================================================
# RECORDS LIST
# ============================================================

@app.get(
    "/records",
    dependencies=[
        Depends(
            require_doctor_or_admin
        )
    ],
)
def get_records(
    q: str = Query(
        default=""
    ),
):

    db = SessionLocal()

    try:

        query = db.query(
            ConsultationRecord
        )

        search_value = (
            q.strip()
        )

        if search_value:

            query = query.filter(
                ConsultationRecord.patient_id
                .ilike(
                    f"%{search_value}%"
                )
            )

        records = (
            query
            .order_by(
                ConsultationRecord.id.desc()
            )
            .all()
        )

        audit_event(
            action="records_list_viewed",
            status="success",
            component="records",
        )

        return [
            serialize_record(
                record
            )
            for record in records
        ]

    finally:

        db.close()


# ============================================================
# RECORD DETAIL
# ============================================================

@app.get(
    "/records/{record_id}",
    dependencies=[
        Depends(
            require_doctor_or_admin
        )
    ],
)
def get_record(
    record_id: int,
):

    db = SessionLocal()

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

        if not record:

            audit_event(
                action="record_view_failed",
                status="failed",
                record_id=record_id,
                component="records",
                error_type=(
                    "RecordNotFound"
                ),
            )

            raise HTTPException(
                status_code=404,
                detail=(
                    "Consultation record not found."
                ),
            )

        audit_event(
            action="record_viewed",
            status="success",
            record_id=record.id,
            component="records",
        )

        return serialize_record(
            record
        )

    finally:

        db.close()


# ============================================================
# DOCTOR CORRECTION
# ============================================================

@app.put(
    "/records/{record_id}",
    dependencies=[
        Depends(
            require_doctor
        )
    ],
)
def update_record(
    record_id: int,
    request: RecordUpdateRequest,
):

    db = SessionLocal()

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

        if not record:

            audit_event(
                action="record_update_failed",
                status="failed",
                record_id=record_id,
                component="records",
                error_type=(
                    "RecordNotFound"
                ),
            )

            raise HTTPException(
                status_code=404,
                detail=(
                    "Consultation record not found."
                ),
            )

        provided_fields = (
            request.model_fields_set
        )


        # ====================================================
        # SIMPLE TEXT FIELDS
        # ====================================================

        if (
            "patient_name"
            in provided_fields
        ):

            record.patient_name = (
                encrypt_text(
                    request.patient_name
                )
            )

        if (
            "transcript"
            in provided_fields
        ):

            record.transcript = (
                encrypt_text(
                    request.transcript
                )
            )

        if (
            "chief_complaint"
            in provided_fields
        ):

            record.chief_complaint = (
                encrypt_text(
                    request.chief_complaint
                )
            )

        if (
            "diagnosis"
            in provided_fields
        ):

            record.diagnosis = (
                encrypt_text(
                    request.diagnosis
                )
            )

        if (
            "follow_up"
            in provided_fields
        ):

            record.follow_up = (
                encrypt_text(
                    request.follow_up
                )
            )


        # ====================================================
        # LIST / JSON FIELDS
        # ====================================================

        if (
            "symptoms"
            in provided_fields
        ):

            record.symptoms = (
                encrypt_json(
                    request.symptoms
                    or []
                )
            )

        if (
            "medications"
            in provided_fields
        ):

            record.medications = (
                encrypt_json(
                    request.medications
                    or []
                )
            )

        if (
            "recommended_tests"
            in provided_fields
        ):

            record.recommended_tests = (
                encrypt_json(
                    request.recommended_tests
                    or []
                )
            )

        if (
            "doctor_instructions"
            in provided_fields
        ):

            record.doctor_instructions = (
                encrypt_json(
                    request.doctor_instructions
                    or []
                )
            )


        # ====================================================
        # VITALS
        # ====================================================

        if (
            "vitals"
            in provided_fields
            and request.vitals
            is not None
        ):

            vital_fields = (
                request
                .vitals
                .model_fields_set
            )

            if (
                "blood_pressure"
                in vital_fields
            ):

                record.blood_pressure = (
                    encrypt_text(
                        request
                        .vitals
                        .blood_pressure
                    )
                )

            if (
                "heart_rate"
                in vital_fields
            ):

                record.heart_rate = (
                    encrypt_text(
                        request
                        .vitals
                        .heart_rate
                    )
                )

            if (
                "temperature"
                in vital_fields
            ):

                record.temperature = (
                    encrypt_text(
                        request
                        .vitals
                        .temperature
                    )
                )

            if (
                "oxygen_saturation"
                in vital_fields
            ):

                record.oxygen_saturation = (
                    encrypt_text(
                        request
                        .vitals
                        .oxygen_saturation
                    )
                )


        # ====================================================
        # SAVE UPDATE
        # ====================================================

        db.commit()

        db.refresh(
            record
        )


        # ====================================================
        # PHI-SAFE AUDIT
        # ====================================================

        audit_event(
            action="record_updated",
            status="success",
            record_id=record.id,
            component="records",
        )


        return {
            "success": True,
            "message": (
                "Consultation record updated successfully."
            ),
            "record": (
                serialize_record(
                    record
                )
            ),
        }

    except HTTPException:

        db.rollback()
        raise

    except Exception as error:

        db.rollback()

        audit_event(
            action="record_update_failed",
            status="failed",
            record_id=record_id,
            component="records",
            error_type=(
                type(error).__name__
            ),
        )

        print(
            "Record update error:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Consultation record update failed."
            ),
        )

    finally:

        db.close()


# ============================================================
# DELETE CONSULTATION RECORD
# DOCTOR ONLY
# ============================================================

@app.delete(
    "/records/{record_id}",
    dependencies=[
        Depends(
            require_doctor
        )
    ],
)
def delete_record(
    record_id: int,
):

    db = SessionLocal()

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

        if not record:

            audit_event(
                action=(
                    "record_delete_failed"
                ),
                status="failed",
                record_id=record_id,
                component="records",
                error_type=(
                    "RecordNotFound"
                ),
            )

            raise HTTPException(
                status_code=404,
                detail=(
                    "Consultation record "
                    "not found."
                ),
            )


        # ====================================================
        # REMEMBER AUDIO PATH
        # ====================================================

        stored_audio_path = (
            record.audio_path
        )


        # ====================================================
        # DELETE DATABASE RECORD
        # ====================================================

        db.delete(
            record
        )

        db.commit()


        # ====================================================
        # DELETE ENCRYPTED AUDIO
        # ====================================================

        audio_deleted = False

        if stored_audio_path:

            try:

                audio_path = Path(
                    stored_audio_path
                ).resolve()

                recordings_root = (
                    RECORDINGS_DIR
                    .resolve()
                )

                is_inside_recordings = (
                    audio_path
                    == recordings_root
                    or recordings_root
                    in audio_path.parents
                )

                if is_inside_recordings:

                    if audio_path.exists():

                        audio_path.unlink()

                        audio_deleted = True

                else:

                    print(
                        "Audio delete blocked: "
                        "path outside recordings directory."
                    )

            except Exception as audio_error:

                print(
                    "Audio cleanup failed:",
                    type(
                        audio_error
                    ).__name__,
                )


        # ====================================================
        # AUDIT
        # ====================================================

        audit_event(
            action="record_deleted",
            status="success",
            record_id=record_id,
            component="records",
        )


        return {
            "success": True,
            "message": (
                "Consultation record "
                "deleted successfully."
            ),
            "record_id": (
                record_id
            ),
            "audio_deleted": (
                audio_deleted
            ),
        }


    except HTTPException:

        raise


    except Exception as error:

        db.rollback()

        print(
            "Record deletion error:",
            type(
                error
            ).__name__,
        )

        audit_event(
            action=(
                "record_delete_failed"
            ),
            status="failed",
            record_id=record_id,
            component="records",
            error_type=(
                type(
                    error
                ).__name__
            ),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Consultation record "
                "deletion failed."
            ),
        )


    finally:

        db.close()

