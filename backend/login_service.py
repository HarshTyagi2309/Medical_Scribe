import os
import sqlite3

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


# ============================================================
# REQUEST MODEL
# ============================================================

class LoginRequest(BaseModel):
    username: str
    password: str


# ============================================================
# USERS TABLE
# ============================================================

def ensure_users_table():

    conn = sqlite3.connect(
        DB_PATH
    )

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


# ============================================================
# CREATE / SYNC USER
# ============================================================

def sync_default_user(
    username: str,
    password: str,
    role: str,
):
    """
    Create the user if missing.

    If the user already exists:
    - sync role
    - sync password when .env password changes
    """

    conn = sqlite3.connect(
        DB_PATH
    )

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


    # ========================================================
    # CREATE NEW USER
    # ========================================================

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


    # ========================================================
    # SYNC EXISTING USER
    # ========================================================

    else:

        user_id = existing_user[0]
        stored_password_hash = existing_user[1]
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


# ============================================================
# INITIALIZE DEFAULT USERS
# ============================================================

def initialize_default_users():

    ensure_users_table()


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


# ============================================================
# LOGIN
# ============================================================

@router.post(
    "/login"
)
def login(
    data: LoginRequest,
):

    username_input = (
        data.username.strip()
    )


    conn = sqlite3.connect(
        DB_PATH
    )

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


    # ========================================================
    # USER NOT FOUND
    # ========================================================

    if user is None:

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


    # ========================================================
    # PASSWORD CHECK
    # ========================================================

    if not verify_password(
        data.password,
        password_hash_value,
    ):

        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Invalid username or password."
            ),
        )


    # ========================================================
    # ROLE VALIDATION
    # ========================================================

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


    # ========================================================
    # JWT TOKEN
    # ========================================================

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