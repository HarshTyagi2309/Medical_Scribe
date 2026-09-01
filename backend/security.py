import hmac
import os

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from fastapi import Header, HTTPException, status

from backend.user_auth import decode_access_token


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# API SECURITY / RBAC
# ============================================================

MEDICAL_SCRIBE_API_KEY = os.getenv(
    "MEDICAL_SCRIBE_API_KEY",
    "",
).strip()


DOCTOR_API_KEY = os.getenv(
    "DOCTOR_API_KEY",
    "",
).strip()


ADMIN_API_KEY = os.getenv(
    "ADMIN_API_KEY",
    "",
).strip()


ROLE_DOCTOR = "doctor"
ROLE_ADMIN = "admin"


# ============================================================
# CONSTANT-TIME API KEY CHECK
# ============================================================

def _secure_key_match(
    received_key: str,
    configured_key: str,
) -> bool:

    if not received_key:
        return False

    if not configured_key:
        return False

    return hmac.compare_digest(
        received_key,
        configured_key,
    )


# ============================================================
# JWT AUTHENTICATION
# ============================================================

def _authenticate_jwt(
    authorization: str | None,
):
    """
    Authenticate using:

    Authorization: Bearer <JWT>
    """

    if not authorization:
        return None


    parts = authorization.split(
        " ",
        1,
    )


    if (
        len(parts) != 2
        or parts[0].lower() != "bearer"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header.",
        )


    token = parts[1].strip()


    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is required.",
        )


    payload = decode_access_token(
        token
    )


    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        )


    username = payload.get(
        "sub"
    )


    role = payload.get(
        "role"
    )


    if not username or role not in {
        ROLE_DOCTOR,
        ROLE_ADMIN,
    }:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )


    return {
        "authenticated": True,
        "role": role,
        "actor": username,
        "auth_method": "jwt",
    }


# ============================================================
# API KEY AUTHENTICATION
# ============================================================

def _authenticate_api_key(
    x_api_key: str | None,
):
    """
    API-key fallback for backward compatibility.
    """

    if not x_api_key:
        return None


    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    if _secure_key_match(
        x_api_key,
        ADMIN_API_KEY,
    ):
        return {
            "authenticated": True,
            "role": ROLE_ADMIN,
            "actor": "admin",
            "auth_method": "api_key",
        }


    # --------------------------------------------------------
    # DOCTOR
    # --------------------------------------------------------

    if _secure_key_match(
        x_api_key,
        DOCTOR_API_KEY,
    ):
        return {
            "authenticated": True,
            "role": ROLE_DOCTOR,
            "actor": "doctor",
            "auth_method": "api_key",
        }


    # --------------------------------------------------------
    # LEGACY DOCTOR KEY
    # --------------------------------------------------------

    if _secure_key_match(
        x_api_key,
        MEDICAL_SCRIBE_API_KEY,
    ):
        return {
            "authenticated": True,
            "role": ROLE_DOCTOR,
            "actor": "doctor",
            "auth_method": "api_key",
        }


    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid API key.",
    )


# ============================================================
# MAIN AUTHENTICATION
# ============================================================

def verify_authentication(
    authorization: str | None = Header(
        default=None,
        alias="Authorization",
    ),
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key",
    ),
):
    """
    Authentication priority:

    1. JWT Bearer token
    2. API key fallback

    Frontend users should use JWT.
    API keys remain available for backward compatibility.
    """

    # --------------------------------------------------------
    # JWT FIRST
    # --------------------------------------------------------

    if authorization:

        return _authenticate_jwt(
            authorization
        )


    # --------------------------------------------------------
    # API KEY FALLBACK
    # --------------------------------------------------------

    if x_api_key:

        return _authenticate_api_key(
            x_api_key
        )


    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
    )


# ============================================================
# BACKWARD-COMPATIBLE FUNCTION
# ============================================================

def verify_api_key(
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key",
    ),
):
    """
    Kept for older code that directly uses verify_api_key().
    """

    actor = _authenticate_api_key(
        x_api_key
    )


    if actor:

        return actor


    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API key is required.",
    )


# ============================================================
# ROLE AUTHORIZATION
# ============================================================

def require_roles(
    *allowed_roles: str,
):
    """
    Allow only selected roles.

    Authentication may come from:
    - JWT Bearer token
    - API key fallback
    """

    def role_checker(
        authorization: str | None = Header(
            default=None,
            alias="Authorization",
        ),
        x_api_key: str | None = Header(
            default=None,
            alias="X-API-Key",
        ),
    ):

        actor = verify_authentication(
            authorization=authorization,
            x_api_key=x_api_key,
        )


        if (
            actor["role"]
            not in allowed_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You do not have permission "
                    "to perform this action."
                ),
            )


        return actor


    return role_checker


# ============================================================
# COMMON ROLE DEPENDENCIES
# ============================================================

require_doctor = require_roles(
    ROLE_DOCTOR,
)


require_admin = require_roles(
    ROLE_ADMIN,
)


require_doctor_or_admin = require_roles(
    ROLE_DOCTOR,
    ROLE_ADMIN,
)


# ============================================================
# DATA ENCRYPTION
# ============================================================

DATA_ENCRYPTION_KEY = os.getenv(
    "DATA_ENCRYPTION_KEY",
    "",
).strip()


def _get_fernet() -> Fernet:

    if not DATA_ENCRYPTION_KEY:
        raise RuntimeError(
            "DATA_ENCRYPTION_KEY is missing from .env"
        )


    try:

        return Fernet(
            DATA_ENCRYPTION_KEY.encode(
                "utf-8"
            )
        )


    except Exception as error:

        raise RuntimeError(
            "DATA_ENCRYPTION_KEY is invalid."
        ) from error


def encrypt_text(
    value: str | None,
) -> str | None:

    if value is None:
        return None


    value = str(
        value
    )


    if not value:
        return value


    fernet = _get_fernet()


    encrypted_value = fernet.encrypt(
        value.encode(
            "utf-8"
        )
    )


    return encrypted_value.decode(
        "utf-8"
    )


def decrypt_text(
    value: str | None,
) -> str | None:

    if value is None:
        return None


    value = str(
        value
    )


    if not value:
        return value


    try:

        fernet = _get_fernet()


        decrypted_value = fernet.decrypt(
            value.encode(
                "utf-8"
            )
        )


        return decrypted_value.decode(
            "utf-8"
        )


    except InvalidToken:

        # Backward compatibility with older plaintext records.
        return value


def encrypt_bytes(
    value: bytes,
) -> bytes:

    if not value:
        return value


    fernet = _get_fernet()


    return fernet.encrypt(
        value
    )


def decrypt_bytes(
    value: bytes,
) -> bytes:

    if not value:
        return value


    fernet = _get_fernet()


    return fernet.decrypt(
        value
    )