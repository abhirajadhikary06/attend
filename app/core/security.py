"""
Simple encryption helpers for biometric data at rest.
Uses Fernet (symmetric) with a key derived from a machine-specific secret
or a user-provided passphrase stored securely.
"""

import os
import hashlib
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from app.core.config import DATA_DIR

KEY_FILE = DATA_DIR / ".attend_key"


def _generate_or_load_key() -> bytes:
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    # Restrict permissions on Unix-like systems
    try:
        os.chmod(KEY_FILE, 0o600)
    except Exception:
        pass
    return key


def get_fernet() -> Fernet:
    return Fernet(_generate_or_load_key())


def encrypt_bytes(data: bytes) -> bytes:
    return get_fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    try:
        return get_fernet().decrypt(token)
    except InvalidToken:
        raise ValueError("Failed to decrypt data – key may have changed or data is corrupted")


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
        return expected.hex() == hash_hex
    except Exception:
        return False
