"""
Security Module for OMS
보안 관련 기능 모듈
"""

from .pii_handler import (
    PIIHandler,
    PIIType,
    PIIMatch,
    PIIHandlingStrategy,
    create_pii_handler
)

# Re-export common_security functions for backward compatibility
from common_security import (
    encrypt,
    decrypt,
    sign,
    verify_signature,
    generate_signing_key,
    calculate_hmac,
    verify_hmac,
    hash_data,
    hash_file,
    get_key,
    rotate_key
)

__all__ = [
    'PIIHandler',
    'PIIType', 
    'PIIMatch',
    'PIIHandlingStrategy',
    'create_pii_handler',
    # Common security functions
    'encrypt',
    'decrypt',
    'sign',
    'verify_signature',
    'generate_signing_key',
    'calculate_hmac',
    'verify_hmac',
    'hash_data',
    'hash_file',
    'get_key',
    'rotate_key'
]