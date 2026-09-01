import os

from dotenv import load_dotenv
from langfuse import get_client


load_dotenv(".env", override=True)


LANGFUSE_PUBLIC_KEY = os.getenv(
    "LANGFUSE_PUBLIC_KEY",
    "",
).strip()

LANGFUSE_SECRET_KEY = os.getenv(
    "LANGFUSE_SECRET_KEY",
    "",
).strip()

LANGFUSE_BASE_URL = os.getenv(
    "LANGFUSE_BASE_URL",
    "https://cloud.langfuse.com",
).strip()

CAPTURE_CLINICAL_DATA = (
    os.getenv(
        "LANGFUSE_CAPTURE_CLINICAL_DATA",
        "false",
    )
    .strip()
    .lower()
    == "true"
)


def is_langfuse_configured() -> bool:

    return bool(
        LANGFUSE_PUBLIC_KEY
        and LANGFUSE_SECRET_KEY
    )


def should_capture_clinical_data() -> bool:

    return (
        CAPTURE_CLINICAL_DATA
        and is_langfuse_configured()
    )


def get_langfuse_client():

    if not is_langfuse_configured():

        return None

    try:

        return get_client()

    except Exception as error:

        print(
            "Langfuse unavailable:",
            type(error).__name__,
        )

        return None


def safe_langfuse_metadata(
    *,
    component=None,
    provider=None,
    model=None,
    status=None,
    session_id=None,
    audio_size=None,
    transcript_length=None,
    latency_ms=None,
    fallback_used=None,
    error_type=None,
):

    metadata = {}

    values = {

        "component": component,

        "provider": provider,

        "model": model,

        "status": status,

        "session_id": session_id,

        "audio_size_bytes": audio_size,

        "transcript_length": transcript_length,

        "latency_ms": latency_ms,

        "fallback_used": fallback_used,

        "error_type": error_type,
    }

    for key, value in values.items():

        if value is not None:

            metadata[key] = value

    return metadata


def flush_langfuse():

    try:

        langfuse = get_langfuse_client()

        if langfuse:

            langfuse.flush()

    except Exception:

        pass