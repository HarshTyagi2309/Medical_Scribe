import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)


# ============================================================
# STORAGE DIRECTORY
# ============================================================

STORAGE_DIR_ENV = os.getenv(
    "STORAGE_DIR",
    "",
).strip()


if STORAGE_DIR_ENV:

    STORAGE_DIR = Path(
        STORAGE_DIR_ENV
    )

else:

    STORAGE_DIR = (
        PROJECT_ROOT
        / "data"
    )


STORAGE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# DATABASE PATH
# ============================================================

DATABASE_PATH = (
    STORAGE_DIR
    / "medical_scribe.db"
)


DATABASE_URL = (
    f"sqlite:///"
    f"{DATABASE_PATH.as_posix()}"
)


# ============================================================
# SQLALCHEMY ENGINE
# ============================================================

engine = create_engine(
    DATABASE_URL,

    connect_args={
        "check_same_thread": False
    },
)


# ============================================================
# SESSION
# ============================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ============================================================
# BASE
# ============================================================

Base = declarative_base()


# ============================================================
# DATABASE DEPENDENCY
# ============================================================

def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()