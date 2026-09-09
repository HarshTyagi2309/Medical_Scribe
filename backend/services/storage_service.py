import uuid
from pathlib import Path

from backend.core.config import get_settings
from backend.security import encrypt_bytes


def save_encrypted_audio_file(
    audio_bytes: bytes,
) -> tuple[str, Path]:
    settings = get_settings()

    encrypted_audio = encrypt_bytes(
        audio_bytes
    )

    stored_filename = (
        f"{uuid.uuid4().hex}.audio.enc"
    )

    stored_path = (
        settings.recordings_dir
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
