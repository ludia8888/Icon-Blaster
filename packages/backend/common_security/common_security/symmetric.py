"""Symmetric Encryption Utilities

Unified AES-256-GCM encryption replacing audit-service AES-GCM
and oms-monolith Fernet implementations.
"""

import os
import base64
from typing import Union, Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from .secrets import get_key


def _derive_key(master_key: bytes, salt: bytes, iterations: int = 100000) -> bytes:
    """Derive AES-256 key from master key using PBKDF2.
    
    Args:
        master_key: Master key bytes
        salt: Salt for key derivation
        iterations: PBKDF2 iterations
    
    Returns:
        32-byte AES-256 key
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(master_key)


def encrypt(
    data: Union[str, bytes], 
    key: Union[str, bytes, None] = None,
    key_id: str = "encryption_key",
    aad: Optional[bytes] = None
) -> bytes:
    """Encrypt data using AES-256-GCM.
    
    Args:
        data: Data to encrypt
        key: Encryption key (if None, retrieves from key_id)
        key_id: Key identifier for key retrieval
        aad: Additional authenticated data
    
    Returns:
        Encrypted data: salt(16) + iv(12) + ciphertext + tag(16)
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    
    if key is None:
        key = get_key(key_id)
    
    if isinstance(key, str):
        key = key.encode("utf-8")
    
    # Generate random salt and IV
    salt = os.urandom(16)
    iv = os.urandom(12)
    
    # Derive encryption key
    derived_key = _derive_key(key, salt)
    
    # Create cipher
    cipher = Cipher(algorithms.AES(derived_key), modes.GCM(iv))
    encryptor = cipher.encryptor()
    
    # Add AAD if provided
    if aad:
        encryptor.authenticate_additional_data(aad)
    
    # Encrypt data
    ciphertext = encryptor.update(data) + encryptor.finalize()
    
    # Return: salt + iv + ciphertext + tag
    return salt + iv + ciphertext + encryptor.tag


def decrypt(
    encrypted_data: bytes, 
    key: Union[str, bytes, None] = None,
    key_id: str = "encryption_key",
    aad: Optional[bytes] = None
) -> bytes:
    """Decrypt data using AES-256-GCM.
    
    Args:
        encrypted_data: Encrypted data from encrypt()
        key: Decryption key (if None, retrieves from key_id)
        key_id: Key identifier for key retrieval
        aad: Additional authenticated data
    
    Returns:
        Decrypted data bytes
    """
    if key is None:
        key = get_key(key_id)
    
    if isinstance(key, str):
        key = key.encode("utf-8")
    
    # Extract components
    salt = encrypted_data[:16]
    iv = encrypted_data[16:28]
    ciphertext_and_tag = encrypted_data[28:]
    ciphertext = ciphertext_and_tag[:-16]
    tag = ciphertext_and_tag[-16:]
    
    # Derive decryption key
    derived_key = _derive_key(key, salt)
    
    # Create cipher
    cipher = Cipher(algorithms.AES(derived_key), modes.GCM(iv, tag))
    decryptor = cipher.decryptor()
    
    # Add AAD if provided
    if aad:
        decryptor.authenticate_additional_data(aad)
    
    # Decrypt data
    return decryptor.update(ciphertext) + decryptor.finalize()


def encrypt_text(
    text: str, 
    key: Union[str, bytes, None] = None,
    key_id: str = "encryption_key"
) -> str:
    """Encrypt text and return base64-encoded result.
    
    Args:
        text: Text to encrypt
        key: Encryption key (if None, retrieves from key_id)
        key_id: Key identifier for key retrieval
    
    Returns:
        Base64-encoded encrypted data
    """
    encrypted = encrypt(text, key, key_id)
    return base64.b64encode(encrypted).decode("ascii")


def decrypt_text(
    encrypted_text: str, 
    key: Union[str, bytes, None] = None,
    key_id: str = "encryption_key"
) -> str:
    """Decrypt base64-encoded encrypted text.
    
    Args:
        encrypted_text: Base64-encoded encrypted data
        key: Decryption key (if None, retrieves from key_id)
        key_id: Key identifier for key retrieval
    
    Returns:
        Decrypted text string
    """
    encrypted_data = base64.b64decode(encrypted_text)
    decrypted = decrypt(encrypted_data, key, key_id)
    return decrypted.decode("utf-8")