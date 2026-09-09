from datetime import datetime
from zoneinfo import ZoneInfo

from backend.core.config import get_settings


def get_current_time() -> datetime:
    settings = get_settings()
    return datetime.now(ZoneInfo(settings.timezone))


def get_timestamp() -> dict[str, str]:
    now = get_current_time()

    return {
        "date": now.strftime("%d-%m-%Y"),
        "time": now.strftime("%I:%M %p"),
        "datetime": now.isoformat(),
    }
