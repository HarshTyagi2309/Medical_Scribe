import os
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.user_auth import (
    create_access_token,
    hash_password,
    verify_password,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


DB_PATH = os.path.join(
    "data",
    "medical_scribe.db",
)

MAX_FAILED_ATTEMPTS = int(
    os.getenv(
        "MAX_FAILED_LOGIN_ATTEMPTS",
        "5",
    )
)

LOGIN_LOCKOUT_MINUTES = int(
    os.getenv(
        "LOGIN_LOCKOUT_MINUTES",
        "15",
    )
)


class LoginRequest(BaseModel):
    username: str
    password: str


def get_connection():
    return sqlite3.connect(
        DB_PATH
    )


def ensure_users_table():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def ensure_login_security_table():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS login_security (
            username TEXT PRIMARY KEY,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def sync_default_user(
    username: str,
    password: str,
    role: str,
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            password_hash,
            role
        FROM app_users
        WHERE username = ?
        """,
        (
            username,
        ),
    )

    existing_user = cursor.fetchone()

    if existing_user is None:

        cursor.execute(
            """
            INSERT INTO app_users (
                username,
                password_hash,
                role
            )
            VALUES (?, ?, ?)
            """,
            (
                username,
                hash_password(
                    password
                ),
                role,
            ),
        )

    else:

        user_id = existing_user[0]
        stored_password_hash = (
            existing_user[1]
        )
        stored_role = existing_user[2]

        password_changed = (
            not verify_password(
                password,
                stored_password_hash,
            )
        )

        role_changed = (
            stored_role != role
        )

        if (
            password_changed
            or role_changed
        ):

            new_password_hash = (
                stored_password_hash
            )

            if password_changed:

                new_password_hash = (
                    hash_password(
                        password
                    )
                )

            cursor.execute(
                """
                UPDATE app_users
                SET
                    password_hash = ?,
                    role = ?
                WHERE id = ?
                """,
                (
                    new_password_hash,
                    role,
                    user_id,
                ),
            )

    conn.commit()
    conn.close()


def initialize_default_users():

    ensure_users_table()
    ensure_login_security_table()

    doctor_username = os.getenv(
        "DOCTOR_USERNAME",
        "",
    ).strip()

    doctor_password = os.getenv(
        "DOCTOR_PASSWORD",
        "",
    )

    admin_username = os.getenv(
        "ADMIN_USERNAME",
        "",
    ).strip()

    admin_password = os.getenv(
        "ADMIN_PASSWORD",
        "",
    )

    if (
        doctor_username
        and doctor_password
    ):

        sync_default_user(
            doctor_username,
            doctor_password,
            "doctor",
        )

    if (
        admin_username
        and admin_password
    ):

        sync_default_user(
            admin_username,
            admin_password,
            "admin",
        )


def get_login_security(
    username: str,
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            failed_attempts,
            locked_until
        FROM login_security
        WHERE username = ?
        """,
        (
            username,
        ),
    )

    row = cursor.fetchone()

    conn.close()

    if row is None:
        return 0, None

    return row[0], row[1]


def reset_login_security(
    username: str,
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO login_security (
            username,
            failed_attempts,
            locked_until
        )
        VALUES (?, 0, NULL)
        ON CONFLICT(username)
        DO UPDATE SET
            failed_attempts = 0,
            locked_until = NULL
        """,
        (
            username,
        ),
    )

    conn.commit()
    conn.close()


def check_account_lock(
    username: str,
):

    failed_attempts, locked_until = (
        get_login_security(
            username
        )
    )

    if not locked_until:
        return

    try:

        lock_time = datetime.fromisoformat(
            locked_until
        )

    except ValueError:

        reset_login_security(
            username
        )
        return

    now = datetime.now(
        timezone.utc
    )

    if lock_time > now:

        raise HTTPException(
            status_code=(
                status.HTTP_429_TOO_MANY_REQUESTS
            ),
            detail=(
                "Too many failed login attempts. "
                "Please try again later."
            ),
        )

    reset_login_security(
        username
    )


def record_failed_login(
    username: str,
):

    failed_attempts, _ = (
        get_login_security(
            username
        )
    )

    failed_attempts += 1

    locked_until = None

    if (
        failed_attempts
        >= MAX_FAILED_ATTEMPTS
    ):

        locked_until = (
            datetime.now(
                timezone.utc
            )
            + timedelta(
                minutes=LOGIN_LOCKOUT_MINUTES
            )
        ).isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO login_security (
            username,
            failed_attempts,
            locked_until
        )
        VALUES (?, ?, ?)
        ON CONFLICT(username)
        DO UPDATE SET
            failed_attempts = excluded.failed_attempts,
            locked_until = excluded.locked_until
        """,
        (
            username,
            failed_attempts,
            locked_until,
        ),
    )

    conn.commit()
    conn.close()


@router.post(
    "/login"
)
def login(
    data: LoginRequest,
):

    username_input = (
        data.username.strip()
    )

    check_account_lock(
        username_input
    )

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            username,
            password_hash,
            role
        FROM app_users
        WHERE username = ?
        """,
        (
            username_input,
        ),
    )

    user = cursor.fetchone()

    conn.close()

    if user is None:

        record_failed_login(
            username_input
        )

        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Invalid username or password."
            ),
        )

    username = user[0]
    password_hash_value = user[1]
    role = user[2]

    if not verify_password(
        data.password,
        password_hash_value,
    ):

        record_failed_login(
            username_input
        )

        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Invalid username or password."
            ),
        )

    if role not in {
        "doctor",
        "admin",
    }:

        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail=(
                "User role is not authorized."
            ),
        )

    reset_login_security(
        username_input
    )

    token = create_access_token(
        username=username,
        role=role,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "username": username,
        "role": role,
    }
