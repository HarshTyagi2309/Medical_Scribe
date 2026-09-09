import os

from cryptography.fernet import Fernet


# Test-only environment configuration.
# Never use these values for real patient/production data.
os.environ.setdefault(
    "DATA_ENCRYPTION_KEY",
    Fernet.generate_key().decode(),
)

os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-only-jwt-secret-key-not-for-production",
)
