"""Key Management and Secrets

Centralized key management supporting environment variables,
AWS KMS, and key rotation capabilities.
"""

import os
import base64
from typing import Union, Optional, Dict
from functools import lru_cache


class KeyManager:
    """Centralized key management for cryptographic operations."""
    
    def __init__(self):
        self._key_cache: Dict[str, bytes] = {}
        self._key_providers = ["env", "aws_kms", "file"]
    
    def get_key(self, key_id: str) -> bytes:
        """Get key by identifier.
        
        Args:
            key_id: Key identifier
        
        Returns:
            Key bytes
        """
        if key_id in self._key_cache:
            return self._key_cache[key_id]
        
        # Try environment variable first
        env_key = os.getenv(f"CRYPTO_KEY_{key_id.upper()}")
        if env_key:
            try:
                key_bytes = base64.b64decode(env_key)
                self._key_cache[key_id] = key_bytes
                return key_bytes
            except Exception:
                # If not base64, use as-is
                key_bytes = env_key.encode("utf-8")
                self._key_cache[key_id] = key_bytes
                return key_bytes
        
        # Try AWS KMS
        try:
            key_bytes = self._get_from_aws_kms(key_id)
            if key_bytes:
                self._key_cache[key_id] = key_bytes
                return key_bytes
        except Exception:
            pass
        
        # Try file system
        try:
            key_bytes = self._get_from_file(key_id)
            if key_bytes:
                self._key_cache[key_id] = key_bytes
                return key_bytes
        except Exception:
            pass
        
        # Default fallback key (for development only)
        if os.getenv("ENVIRONMENT") == "development":
            default_key = f"dev-key-{key_id}".encode("utf-8")
            self._key_cache[key_id] = default_key
            return default_key
        
        raise KeyError(f"Key not found: {key_id}")
    
    def _get_from_aws_kms(self, key_id: str) -> Optional[bytes]:
        """Get key from AWS KMS."""
        try:
            import boto3
            
            kms_client = boto3.client("kms")
            response = kms_client.decrypt(
                CiphertextBlob=base64.b64decode(key_id),
                EncryptionContext={"key_id": key_id}
            )
            return response["Plaintext"]
        except Exception:
            return None
    
    def _get_from_file(self, key_id: str) -> Optional[bytes]:
        """Get key from file system."""
        key_file = f"/etc/crypto-keys/{key_id}"
        if os.path.exists(key_file):
            with open(key_file, "rb") as f:
                return f.read()
        return None
    
    def rotate_key(self, key_id: str, new_key: Union[str, bytes]):
        """Rotate key in cache.
        
        Args:
            key_id: Key identifier
            new_key: New key value
        """
        if isinstance(new_key, str):
            new_key = new_key.encode("utf-8")
        
        self._key_cache[key_id] = new_key
        
        # Update environment variable if present
        env_var = f"CRYPTO_KEY_{key_id.upper()}"
        if os.getenv(env_var):
            os.environ[env_var] = base64.b64encode(new_key).decode("ascii")
    
    def clear_cache(self):
        """Clear key cache."""
        self._key_cache.clear()


# Global key manager instance
_key_manager = KeyManager()


def get_key(key_id: str) -> bytes:
    """Get key by identifier.
    
    Args:
        key_id: Key identifier
    
    Returns:
        Key bytes
    """
    return _key_manager.get_key(key_id)


def rotate_key(key_id: str, new_key: Union[str, bytes]):
    """Rotate key.
    
    Args:
        key_id: Key identifier
        new_key: New key value
    """
    _key_manager.rotate_key(key_id, new_key)


def clear_key_cache():
    """Clear key cache."""
    _key_manager.clear_cache()


@lru_cache(maxsize=128)
def get_master_key(service: str = "common") -> bytes:
    """Get master key for a service.
    
    Args:
        service: Service name ("audit", "user", "oms", "common")
    
    Returns:
        Master key bytes
    """
    return get_key(f"master_key_{service}")


def derive_service_key(service: str, purpose: str) -> str:
    """Derive service-specific key identifier.
    
    Args:
        service: Service name
        purpose: Key purpose (e.g., "encryption", "signing", "hmac")
    
    Returns:
        Service-specific key identifier
    """
    return f"{service}_{purpose}_key"