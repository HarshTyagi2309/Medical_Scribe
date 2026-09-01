import json
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.models import RecordAuditHistory
from backend.security import decrypt_text, encrypt_text


INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")


def get_current_timestamp() -> str:
    return datetime.now(
        INDIA_TIMEZONE
    ).strftime("%Y-%m-%d %I:%M:%S %p")


def save_edit_history(
    db: Session,
    record_id: int,
    username: str,
    role: str,
    old_values: dict,
    new_values: dict,
):
    changed_fields = []

    actual_old_values = {}
    actual_new_values = {}

    def normalize_value(value):
        if value is None or value == "":
            return ""

        if isinstance(value, list):
            return [
                normalize_value(item)
                for item in value
            ]

        if isinstance(value, dict):
            return {
                key: normalize_value(item)
                for key, item in value.items()
            }

        return value

    for field, new_value in new_values.items():

        old_value = old_values.get(field)

        if normalize_value(old_value) != normalize_value(new_value):

            changed_fields.append(field)

            actual_old_values[field] = old_value
            actual_new_values[field] = new_value

    if not changed_fields:
        return None

    old_json = json.dumps(
        actual_old_values,
        ensure_ascii=False,
        default=str,
    )

    new_json = json.dumps(
        actual_new_values,
        ensure_ascii=False,
        default=str,
    )

    history = RecordAuditHistory(
        record_id=record_id,
        action="EDIT",
        username=username,
        role=role,
        timestamp=get_current_timestamp(),
        changed_fields=json.dumps(
            changed_fields
        ),
        old_values=encrypt_text(
            old_json
        ),
        new_values=encrypt_text(
            new_json
        ),
        details="Doctor updated consultation record.",
    )

    db.add(history)
    db.commit()
    db.refresh(history)

    return history


def save_delete_history(
    db: Session,
    record_id: int,
    username: str,
    role: str,
    details: str = "Consultation record deleted.",
):

    history = RecordAuditHistory(
        record_id=record_id,
        action="DELETE",
        username=username,
        role=role,
        timestamp=get_current_timestamp(),
        changed_fields=None,
        old_values=None,
        new_values=None,
        details=details,
    )

    db.add(history)
    db.commit()
    db.refresh(history)

    return history


def get_record_history(
    db: Session,
    record_id: int,
):

    histories = (
        db.query(
            RecordAuditHistory
        )
        .filter(
            RecordAuditHistory.record_id
            == record_id
        )
        .order_by(
            RecordAuditHistory.id.desc()
        )
        .all()
    )

    result = []

    for history in histories:

        old_values = None
        new_values = None

        if history.old_values:
            try:
                old_values = json.loads(
                    decrypt_text(
                        history.old_values
                    )
                )
            except Exception:
                old_values = None

        if history.new_values:
            try:
                new_values = json.loads(
                    decrypt_text(
                        history.new_values
                    )
                )
            except Exception:
                new_values = None

        try:
            changed_fields = (
                json.loads(
                    history.changed_fields
                )
                if history.changed_fields
                else []
            )

        except Exception:
            changed_fields = []

        result.append(
            {
                "id": history.id,
                "record_id": history.record_id,
                "action": history.action,
                "username": history.username,
                "role": history.role,
                "timestamp": history.timestamp,
                "changed_fields": changed_fields,
                "old_values": old_values,
                "new_values": new_values,
                "details": history.details,
            }
        )

    return result

def get_all_record_history(
    db: Session,
):

    histories = (
        db.query(
            RecordAuditHistory
        )
        .order_by(
            RecordAuditHistory.id.desc()
        )
        .all()
    )

    result = []

    for history in histories:

        old_values = None
        new_values = None

        if history.old_values:

            try:
                old_values = json.loads(
                    decrypt_text(
                        history.old_values
                    )
                )

            except Exception:
                old_values = None

        if history.new_values:

            try:
                new_values = json.loads(
                    decrypt_text(
                        history.new_values
                    )
                )

            except Exception:
                new_values = None

        try:

            changed_fields = (
                json.loads(
                    history.changed_fields
                )
                if history.changed_fields
                else []
            )

        except Exception:

            changed_fields = []

        result.append(
            {
                "id": history.id,
                "record_id": history.record_id,
                "action": history.action,
                "username": history.username,
                "role": history.role,
                "timestamp": history.timestamp,
                "changed_fields": changed_fields,
                "old_values": old_values,
                "new_values": new_values,
                "details": history.details,
            }
        )

    return result
