from pathlib import Path

from fastapi import HTTPException

from backend.core.config import get_settings


def validate_audio(
    audio_bytes: bytes,
    filename: str,
) -> str:
    settings = get_settings()

    if not audio_bytes:
        raise HTTPException(
            status_code=400,
            detail="Audio file is empty.",
        )

    if len(audio_bytes) > settings.max_audio_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                "Audio file is too large. "
                f"Maximum size is {settings.max_audio_size_mb} MB."
            ),
        )

    extension = Path(filename).suffix.lower()

    if extension not in settings.allowed_audio_extensions:
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format.",
        )

    return extension
