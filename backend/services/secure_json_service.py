from typing import Any

from backend.security import decrypt_text, encrypt_text
from backend.utils.json_utils import json_dumps, json_loads_safe


def encrypt_json(value: Any) -> str:
    return encrypt_text(
        json_dumps(value)
    )


def decrypt_json(
    value: str | None,
    default: Any,
) -> Any:
    decrypted_value = decrypt_text(
        value
    )

    return json_loads_safe(
        decrypted_value,
        default,
    )
