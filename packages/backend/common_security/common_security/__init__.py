"""Common Security Package

Unified cryptographic utilities for audit-service and oms-monolith.
Provides consistent APIs for encryption, signing, hashing, and key management.
"""

from .symmetric import encrypt, decrypt, encrypt_text, decrypt_text
from .asymmetric import sign, verify_signature, generate_signing_key
from .hmac_util import calculate_hmac, verify_hmac
from .hashing import hash_data, hash_file
from .secrets import get_key, rotate_key

__version__ = "1.0.0"
__all__ = [
    "encrypt",
    "decrypt", 
    "encrypt_text",
    "decrypt_text",
    "sign",
    "verify_signature",
    "generate_signing_key",
    "calculate_hmac",
    "verify_hmac",
    "hash_data",
    "hash_file",
    "get_key",
    "rotate_key",
]