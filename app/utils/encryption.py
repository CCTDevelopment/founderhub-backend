import os
import base64
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import logging

# === Logger Setup ===
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# === Load master key from .env ===
MASTER_KEY = os.getenv("ENCRYPTION_KEY")
if not MASTER_KEY:
    raise RuntimeError("🚨 ENCRYPTION_KEY is not set in environment")

# Convert master key to bytes
MASTER_KEY_BYTES = MASTER_KEY.encode("utf-8")

def get_derived_key(tenant_id: str) -> bytes:
    """
    Derives a tenant-specific encryption key using PBKDF2-HMAC.
    """
    salt = tenant_id.encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
        backend=default_backend()
    )
    derived_key = base64.urlsafe_b64encode(kdf.derive(MASTER_KEY_BYTES))
    return derived_key

def get_tenant_fernet(tenant_id: str) -> Fernet:
    """
    Returns a Fernet instance scoped to a tenant.
    """
    return Fernet(get_derived_key(tenant_id))
    
def encrypt_value(value: str, tenant_id: str) -> str:
    """
    Encrypts a string using tenant-specific encryption key.
    """
    try:
        fernet = get_tenant_fernet(tenant_id)
        return fernet.encrypt(value.encode()).decode()
    except Exception as e:
        logger.exception(f"Encryption failed for tenant_id={tenant_id}")
        raise RuntimeError("Encryption error")

def decrypt_value(value: str, tenant_id: str) -> Optional[str]:
    """
    Decrypts a string using tenant-specific key.
    Returns None if decryption fails (e.g. invalid key or data).
    """
    try:
        fernet = get_tenant_fernet(tenant_id)
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        logger.warning(f"⚠️ Invalid token for tenant_id={tenant_id}")
        return None
    except Exception as e:
        logger.exception(f"Decryption failed for tenant_id={tenant_id}")
        return None
