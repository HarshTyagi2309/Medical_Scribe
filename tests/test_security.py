from backend.security import encrypt_text, decrypt_text
from backend.services.secure_json_service import encrypt_json, decrypt_json


def test_text_encryption_roundtrip():
    original = "Patient has fever"

    encrypted = encrypt_text(original)

    assert encrypted != original
    assert decrypt_text(encrypted) == original


def test_secure_json_roundtrip():
    original = {
        "symptoms": ["fever", "cough"],
        "diagnosis": "viral infection"
    }

    encrypted = encrypt_json(original)

    assert isinstance(encrypted, str)
    assert "fever" not in encrypted

    decrypted = decrypt_json(encrypted, {})

    assert decrypted == original
