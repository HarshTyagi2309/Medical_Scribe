import hashlib


def calculate_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def calculate_audio_hash(audio_bytes: bytes) -> str:
    return calculate_sha256(audio_bytes)
