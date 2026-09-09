import json
from typing import Any


def json_dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
    )


def json_loads_safe(
    value: str | None,
    default: Any = None,
) -> Any:
    if value is None:
        return default

    try:
        return json.loads(value)
    except Exception:
        return default


def safe_json_dumps(value: Any) -> str:
    return json_dumps(value)


def safe_json_loads(
    value: str | None,
    default: Any = None,
) -> Any:
    return json_loads_safe(
        value,
        default,
    )
