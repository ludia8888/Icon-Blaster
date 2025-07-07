"""Asymmetric Cryptography Utilities

Unified signing and verification supporting both Ed25519 (audit-service)
and RSA (oms-monolith) algorithms.
"""

import base64
from typing import Union, Tuple, Literal
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding, ed25519
from .secrets import get_key


SigningAlgorithm = Literal["ed25519", "rsa-pss", "rsa-pkcs1"]


def generate_signing_key(algorithm: SigningAlgorithm = "ed25519") -> Tuple[bytes, bytes]:
    """Generate signing key pair.
    
    Args:
        algorithm: Signing algorithm ("ed25519", "rsa-pss", "rsa-pkcs1")
    
    Returns:
        Tuple of (private_key_bytes, public_key_bytes)
    """
    if algorithm == "ed25519":
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return private_bytes, public_bytes
    
    elif algorithm in ["rsa-pss", "rsa-pkcs1"]:
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        public_key = private_key.public_key()
        
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return private_bytes, public_bytes
    
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")


def sign(
    data: Union[str, bytes],
    private_key: Union[str, bytes, None] = None,
    algorithm: SigningAlgorithm = "ed25519",
    key_id: str = "signing_key"
) -> str:
    """Sign data using specified algorithm.
    
    Args:
        data: Data to sign
        private_key: Private key (if None, retrieves from key_id)
        algorithm: Signing algorithm
        key_id: Key identifier for key retrieval
    
    Returns:
        Base64-encoded signature
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    
    if private_key is None:
        private_key = get_key(key_id)
    
    if isinstance(private_key, str):
        private_key = private_key.encode("utf-8")
    
    if algorithm == "ed25519":
        key = serialization.load_pem_private_key(private_key, password=None)
        signature = key.sign(data)
        
    elif algorithm == "rsa-pss":
        key = serialization.load_pem_private_key(private_key, password=None)
        signature = key.sign(
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
    elif algorithm == "rsa-pkcs1":
        key = serialization.load_pem_private_key(private_key, password=None)
        signature = key.sign(
            data,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    return base64.b64encode(signature).decode("ascii")


def verify_signature(
    data: Union[str, bytes],
    signature: str,
    public_key: Union[str, bytes, None] = None,
    algorithm: SigningAlgorithm = "ed25519",
    key_id: str = "signing_key_pub"
) -> bool:
    """Verify signature using specified algorithm.
    
    Args:
        data: Original data
        signature: Base64-encoded signature
        public_key: Public key (if None, retrieves from key_id)
        algorithm: Signing algorithm
        key_id: Key identifier for key retrieval
    
    Returns:
        True if signature is valid
    """
    try:
        if isinstance(data, str):
            data = data.encode("utf-8")
        
        if public_key is None:
            public_key = get_key(key_id)
        
        if isinstance(public_key, str):
            public_key = public_key.encode("utf-8")
        
        signature_bytes = base64.b64decode(signature)
        
        if algorithm == "ed25519":
            key = serialization.load_pem_public_key(public_key)
            key.verify(signature_bytes, data)
            
        elif algorithm == "rsa-pss":
            key = serialization.load_pem_public_key(public_key)
            key.verify(
                signature_bytes,
                data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
        elif algorithm == "rsa-pkcs1":
            key = serialization.load_pem_public_key(public_key)
            key.verify(
                signature_bytes,
                data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        
        return True
        
    except Exception:
        return False


def sign_audit_data(data: Union[str, bytes], key_id: str = "audit_signing_key") -> str:
    """Sign audit data using Ed25519 (audit-service compatibility).
    
    Args:
        data: Audit data to sign
        key_id: Audit signing key identifier
    
    Returns:
        Base64-encoded signature
    """
    return sign(data, algorithm="ed25519", key_id=key_id)


def sign_policy_rsa(policy_content: Union[str, bytes], key_id: str = "policy_signing_key") -> str:
    """Sign policy using RSA-PSS (oms-monolith compatibility).
    
    Args:
        policy_content: Policy content to sign
        key_id: Policy signing key identifier
    
    Returns:
        Base64-encoded signature
    """
    return sign(policy_content, algorithm="rsa-pss", key_id=key_id)