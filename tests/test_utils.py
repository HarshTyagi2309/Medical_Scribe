from backend.utils.hashing import calculate_audio_hash
from backend.utils.id_utils import generate_patient_id
from backend.utils.json_utils import json_dumps, json_loads_safe


def test_audio_hash_is_consistent():
    audio = b"sample-audio"

    hash1 = calculate_audio_hash(audio)
    hash2 = calculate_audio_hash(audio)

    assert hash1 == hash2
    assert len(hash1) == 64


def test_patient_id_format():
    patient_id = generate_patient_id()

    assert patient_id.startswith("PAT-")
    assert len(patient_id) == 12


def test_json_roundtrip():
    original = {"symptoms": ["fever", "cough"]}

    encoded = json_dumps(original)
    decoded = json_loads_safe(encoded, {})

    assert decoded == original


def test_invalid_json_returns_default():
    result = json_loads_safe("invalid-json", {})

    assert result == {}
