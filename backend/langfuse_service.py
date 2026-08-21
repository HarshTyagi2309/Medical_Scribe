import os

from dotenv import load_dotenv
from langfuse import get_client


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# ENVIRONMENT VALUES
# ============================================================

LANGFUSE_PUBLIC_KEY = os.getenv(
    "LANGFUSE_PUBLIC_KEY"
)

LANGFUSE_SECRET_KEY = os.getenv(
    "LANGFUSE_SECRET_KEY"
)

LANGFUSE_BASE_URL = os.getenv(
    "LANGFUSE_BASE_URL"
)

CAPTURE_CLINICAL_DATA = (
    os.getenv(
        "LANGFUSE_CAPTURE_CLINICAL_DATA",
        "false",
    )
    .strip()
    .lower()
    == "true"
)


# ============================================================
# LANGFUSE CLIENT
# ============================================================

def get_langfuse_client():
    """
    Return configured Langfuse client.
    """

    if not LANGFUSE_PUBLIC_KEY:
        raise ValueError(
            "LANGFUSE_PUBLIC_KEY is missing from .env"
        )

    if not LANGFUSE_SECRET_KEY:
        raise ValueError(
            "LANGFUSE_SECRET_KEY is missing from .env"
        )

    return get_client()


# ============================================================
# PRIVACY SETTING
# ============================================================

def should_capture_clinical_data() -> bool:
    """
    Decide whether raw clinical transcript/data should
    be sent to Langfuse.

    Default is False for healthcare privacy.
    """

    return CAPTURE_CLINICAL_DATA


# ============================================================
# FLUSH
# ============================================================

def flush_langfuse():
    """
    Force pending Langfuse traces to be sent.
    """

    try:

        langfuse = get_langfuse_client()

        langfuse.flush()

    except Exception:
        # Langfuse must never crash Medical Scribe.
        pass