import logging
from logging.handlers import RotatingFileHandler

from backend.core.config import get_settings


def setup_logging():
    settings = get_settings()

    logger = logging.getLogger("medical_scribe")

    if logger.handlers:
        return logger

    logger.setLevel(
        getattr(logging, settings.log_level, logging.INFO)
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        settings.logs_dir / "medical_scribe.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


logger = setup_logging()
