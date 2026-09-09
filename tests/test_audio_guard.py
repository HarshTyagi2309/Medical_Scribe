import pytest
from fastapi import HTTPException

from backend.guards.audio import validate_audio


def test_valid_wav_audio():
    extension = validate_audio(b"fake-audio", "sample.wav")
    assert extension == ".wav"


def test_valid_mp3_audio():
    extension = validate_audio(b"fake-audio", "sample.mp3")
    assert extension == ".mp3"


def test_invalid_audio_extension():
    with pytest.raises(HTTPException) as exc:
        validate_audio(b"fake-audio", "virus.exe")

    assert exc.value.status_code == 400


def test_empty_audio():
    with pytest.raises(HTTPException) as exc:
        validate_audio(b"", "sample.wav")

    assert exc.value.status_code == 400
