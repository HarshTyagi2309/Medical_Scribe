import uuid


def generate_patient_id() -> str:
    return (
        "PAT-"
        + uuid.uuid4().hex[:8].upper()
    )
