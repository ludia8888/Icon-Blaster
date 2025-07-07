"""HMAC Utilities

Standardized HMAC-SHA256 implementation replacing duplicate code
in audit-service and oms-monolith policy signing.
"""

import hmac
import hashlib
import base64
from typing import Union
from .secrets import get_key


def calculate_hmac(
    data: Union[str, bytes], 
    key: Union[str, bytes, None] = None,
    key_id: str = "hmac_key"
) -> str:
    """Calculate HMAC-SHA256 for data.
    
    Args:
        data: Data to authenticate
        key: HMAC key (if None, retrieves from key_id)
        key_id: Key identifier for key retrieval
    
    Returns:
        Base64-encoded HMAC signature
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    
    if key is None:
        key = get_key(key_id)
    
    if isinstance(key, str):
        key = key.encode("utf-8")
    
    signature = hmac.new(key, data, hashlib.sha256).digest()
    return base64.b64encode(signature).decode("ascii")


def verify_hmac(
    data: Union[str, bytes], 
    signature: str,
    key: Union[str, bytes, None] = None,
    key_id: str = "hmac_key"
) -> bool:
    """Verify HMAC-SHA256 signature.
    
    Args:
        data: Original data
        signature: Base64-encoded HMAC signature
        key: HMAC key (if None, retrieves from key_id)
        key_id: Key identifier for key retrieval
    
    Returns:
        True if signature is valid
    """
    try:
        expected_signature = calculate_hmac(data, key, key_id)
        return hmac.compare_digest(signature, expected_signature)
    except Exception:
        return False


def sign_policy(policy_content: Union[str, bytes], key_id: str = "policy_key") -> str:
    """Sign policy content with HMAC-SHA256.
    
    Replaces oms-monolith policy signing functionality.
    
    Args:
        policy_content: Policy content to sign
        key_id: Policy signing key identifier
    
    Returns:
        Base64-encoded signature
    """
    return calculate_hmac(policy_content, key_id=key_id)


def verify_policy(
    policy_content: Union[str, bytes], 
    signature: str,
    key_id: str = "policy_key"
) -> bool:
    """Verify policy signature.
    
    Args:
        policy_content: Original policy content
        signature: Base64-encoded signature
        key_id: Policy signing key identifier
    
    Returns:
        True if policy signature is valid
    """
    return verify_hmac(policy_content, signature, key_id=key_id)