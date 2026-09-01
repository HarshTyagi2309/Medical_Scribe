import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


# ============================================================
# PATH
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

AUDIT_DIR = (
    PROJECT_ROOT
    / "data"
    / "audit"
)

AUDIT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

AUDIT_FILE = (
    AUDIT_DIR
    / "audit.log"
)


# ============================================================
# LOGGER
# ============================================================

audit_logger = logging.getLogger(
    "medical_scribe_audit"
)

audit_logger.setLevel(
    logging.INFO
)

audit_logger.propagate = False


if not audit_logger.handlers:

    handler = logging.FileHandler(
        AUDIT_FILE,
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        "%(message)s"
    )

    handler.setFormatter(
        formatter
    )

    audit_logger.addHandler(
        handler
    )


# ============================================================
# TIMEZONE
# ============================================================

INDIA_TIMEZONE = ZoneInfo(
    "Asia/Kolkata"
)


# ============================================================
# AUDIT EVENT
# ============================================================

def audit_event(
    *,
    action: str,
    status: str,
    session_id: str | None = None,
    record_id: int | None = None,
    component: str | None = None,
    error_type: str | None = None,
    fallback_used: bool | None = None,
):

    """
    PHI-safe audit logging.

    Never log:
    - patient name
    - transcript
    - diagnosis
    - medications
    - symptoms
    - original audio filename
    """

    try:

        event = {
            "timestamp": datetime.now(
                INDIA_TIMEZONE
            ).isoformat(),

            "action": action,

            "status": status,
        }

        if session_id:
            event["session_id"] = (
                session_id
            )

        if record_id is not None:
            event["record_id"] = (
                record_id
            )

        if component:
            event["component"] = (
                component
            )

        if error_type:
            event["error_type"] = (
                error_type
            )

        if fallback_used is not None:
            event["fallback_used"] = (
                fallback_used
            )

        audit_logger.info(
            json.dumps(
                event,
                ensure_ascii=False,
            )
        )

    except Exception as error:

        # Audit logger should not crash
        # the main consultation workflow.

        print(
            "Audit logging failed:",
            type(error).__name__,
        )