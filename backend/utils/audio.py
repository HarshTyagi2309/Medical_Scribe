from pathlib import Path


def is_allowed_audio_file(filename: str, allowed_extensions: tuple[str, ...]) -> bool:
    extension = Path(filename).suffix.lower()
    return extension in allowed_extensions
