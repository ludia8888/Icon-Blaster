"""Unified Hashing Utilities

Provides consistent hashing functions using SHA-256 and BLAKE3.
Replaces duplicate hash implementations across services.
"""

import hashlib
from typing import Union
from pathlib import Path


def hash_data(data: Union[str, bytes], algorithm: str = "sha256") -> str:
    """Hash data using specified algorithm.
    
    Args:
        data: Data to hash (string or bytes)
        algorithm: Hash algorithm ("sha256" or "blake3")
    
    Returns:
        Hexadecimal hash string
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    
    if algorithm == "sha256":
        return hashlib.sha256(data).hexdigest()
    elif algorithm == "blake3":
        try:
            import blake3
            return blake3.blake3(data).hexdigest()
        except ImportError:
            # Fallback to SHA-256 if BLAKE3 not available
            return hashlib.sha256(data).hexdigest()
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")


def hash_file(file_path: Union[str, Path], algorithm: str = "sha256") -> str:
    """Hash file contents using specified algorithm.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm ("sha256" or "blake3")
    
    Returns:
        Hexadecimal hash string
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if algorithm == "sha256":
        hasher = hashlib.sha256()
    elif algorithm == "blake3":
        try:
            import blake3
            hasher = blake3.blake3()
        except ImportError:
            # Fallback to SHA-256 if BLAKE3 not available
            hasher = hashlib.sha256()
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    
    return hasher.hexdigest()


def calculate_checksum(data: Union[str, bytes]) -> str:
    """Calculate SHA-256 checksum for data integrity verification.
    
    Args:
        data: Data to checksum
    
    Returns:
        SHA-256 hexadecimal string
    """
    return hash_data(data, "sha256")