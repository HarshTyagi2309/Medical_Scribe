import json
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.models import RecordAuditHistory
from backend.security import decrypt_text, encrypt_text


INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")


def get_current_timestamp():
    return datetime.now(INDIA_TIMEZONE).strftime(
        "%Y-%m-%d %I:%M:%S %p"
    )


def normalize_value(value):
    if value is None:
        return ""

    if isinstance(value, dict):
        return {
            key: normalize_value(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            normalize_value(item)
            for item in value
        ]

    return value


def decrypt_json_value(value):
    if not value:
        return None

    try:
        decrypted = decrypt_text(value)
        return json.loads(decrypted)
    except Exception:
        return None


def parse_changed_fields(value):
    if not value:
        return []

    if isinstance(value, list):
        return value

    try:
        return json.loads(value)
    except Exception:
        return []


def format_history_record(record):
    return {
        "id": record.id,
        "record_id": record.record_id,
        "action": record.action,
        "username": record.username,
        "role": record.role,
        "timestamp": record.timestamp,
        "changed_fields": parse_changed_fields(
            record.changed_fields
        ),
        "old_values": decrypt_json_value(
            record.old_values
        ),
        "new_values": decrypt_json_value(
            record.new_values
        ),
        "details": record.details,
    }


def save_edit_history(
    db,
    record_id,
    username,
    role,
    old_values,
    new_values,
):
    old_values = normalize_value(old_values)
    new_values = normalize_value(new_values)

    changed_fields = []

    all_keys = set(old_values.keys()) | set(
        new_values.keys()
    )

    for key in sorted(all_keys):
        if old_values.get(key) != new_values.get(key):
            changed_fields.append(key)

    if not changed_fields:
        return None

    old_json = json.dumps(
        old_values,
        ensure_ascii=False,
        default=str,
    )

    new_json = json.dumps(
        new_values,
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
            changed_fields,
            ensure_ascii=False,
        ),
        old_values=encrypt_text(old_json),
        new_values=encrypt_text(new_json),
        details="Doctor updated consultation record.",
    )

    db.add(history)
    db.commit()
    db.refresh(history)

    return format_history_record(history)


def save_delete_history(
    db,
    record_id,
    username,
    role,
    details="Doctor deleted consultation record.",
):
    history = RecordAuditHistory(
        record_id=record_id,
        action="DELETE",
        username=username,
        role=role,
        timestamp=get_current_timestamp(),
        changed_fields=json.dumps([]),
        old_values=None,
        new_values=None,
        details=details,
    )

    db.add(history)
    db.commit()
    db.refresh(history)

    return format_history_record(history)


def get_record_history(
    db,
    record_id,
):
    records = (
        db.query(RecordAuditHistory)
        .filter(
            RecordAuditHistory.record_id == record_id
        )
        .order_by(
            RecordAuditHistory.id.desc()
        )
        .all()
    )

    return [
        format_history_record(record)
        for record in records
    ]


def get_all_record_history(
    db,
):
    records = (
        db.query(RecordAuditHistory)
        .order_by(
            RecordAuditHistory.id.desc()
        )
        .all()
    )

    return [
        format_history_record(record)
        for record in records
    ]
