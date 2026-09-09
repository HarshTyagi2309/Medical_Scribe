from pydantic import BaseModel


class TranscriptRequest(BaseModel):
    transcript: str


class VitalsUpdate(BaseModel):
    blood_pressure: str | None = None
    heart_rate: str | None = None
    temperature: str | None = None
    oxygen_saturation: str | None = None


class RecordUpdateRequest(BaseModel):
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
