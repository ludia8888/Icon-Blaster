"""Integration tests for common_security package."""

import pytest
import os
import base64
from common_security import (
    encrypt, decrypt, encrypt_text, decrypt_text,
    sign, verify_signature, generate_signing_key,
    calculate_hmac, verify_hmac,
    hash_data, hash_file
)
from common_security.secrets import get_key, rotate_key, clear_key_cache


class TestSymmetricEncryption:
    """Test symmetric encryption functionality."""
    
    def test_encrypt_decrypt_bytes(self):
        """Test encryption and decryption with bytes."""
        data = b"Hello, World!"
        key = b"test-key-32-bytes-long-for-aes256"
        
        encrypted = encrypt(data, key)
        decrypted = decrypt(encrypted, key)
        
        assert decrypted == data
        assert encrypted != data
        assert len(encrypted) > len(data)  # Includes salt + IV + tag
    
    def test_encrypt_decrypt_text(self):
        """Test encryption and decryption with text."""
        text = "Hello, World!"
        key = "test-key-32-bytes-long-for-aes256"
        
        encrypted = encrypt_text(text, key)
        decrypted = decrypt_text(encrypted, key)
        
        assert decrypted == text
        assert encrypted != text
        assert isinstance(encrypted, str)
        
        # Verify it's valid base64
        base64.b64decode(encrypted)
    
    def test_encrypt_with_aad(self):
        """Test encryption with additional authenticated data."""
        data = b"secret data"
        key = b"test-key-32-bytes-long-for-aes256"
        aad = b"additional data"
        
        encrypted = encrypt(data, key, aad=aad)
        decrypted = decrypt(encrypted, key, aad=aad)
        
        assert decrypted == data
        
        # Should fail with wrong AAD
        with pytest.raises(Exception):
            decrypt(encrypted, key, aad=b"wrong aad")
    
    def test_encrypt_with_key_id(self):
        """Test encryption using key ID."""
        # Set up test key
        os.environ["CRYPTO_KEY_TEST"] = base64.b64encode(b"test-key-32-bytes-long-for-aes256").decode()
        
        data = "test data"
        encrypted = encrypt_text(data, key_id="test")
        decrypted = decrypt_text(encrypted, key_id="test")
        
        assert decrypted == data
        
        # Cleanup
        del os.environ["CRYPTO_KEY_TEST"]
        clear_key_cache()


class TestAsymmetricSigning:
    """Test asymmetric signing functionality."""
    
    def test_ed25519_signing(self):
        """Test Ed25519 signing and verification."""
        private_key, public_key = generate_signing_key("ed25519")
        data = "test data to sign"
        
        signature = sign(data, private_key, "ed25519")
        is_valid = verify_signature(data, signature, public_key, "ed25519")
        
        assert is_valid
        assert isinstance(signature, str)
        
        # Verify invalid signature fails
        invalid_signature = sign("different data", private_key, "ed25519")
        assert not verify_signature(data, invalid_signature, public_key, "ed25519")
    
    def test_rsa_signing(self):
        """Test RSA signing and verification."""
        private_key, public_key = generate_signing_key("rsa-pss")
        data = "test data to sign"
        
        signature = sign(data, private_key, "rsa-pss")
        is_valid = verify_signature(data, signature, public_key, "rsa-pss")
        
        assert is_valid
        assert isinstance(signature, str)
        
        # Test different RSA algorithms
        signature_pkcs1 = sign(data, private_key, "rsa-pkcs1")
        is_valid_pkcs1 = verify_signature(data, signature_pkcs1, public_key, "rsa-pkcs1")
        
        assert is_valid_pkcs1
    
    def test_signing_with_key_id(self):
        """Test signing using key ID."""
        # Generate and store test key
        private_key, public_key = generate_signing_key("ed25519")
        os.environ["CRYPTO_KEY_SIGN_TEST"] = base64.b64encode(private_key).decode()
        os.environ["CRYPTO_KEY_SIGN_TEST_PUB"] = base64.b64encode(public_key).decode()
        
        data = "test data"
        signature = sign(data, key_id="sign_test")
        is_valid = verify_signature(data, signature, key_id="sign_test_pub")
        
        assert is_valid
        
        # Cleanup
        del os.environ["CRYPTO_KEY_SIGN_TEST"]
        del os.environ["CRYPTO_KEY_SIGN_TEST_PUB"]
        clear_key_cache()


class TestHMAC:
    """Test HMAC functionality."""
    
    def test_hmac_calculation(self):
        """Test HMAC calculation and verification."""
        data = "test data"
        key = "test-hmac-key"
        
        signature = calculate_hmac(data, key)
        is_valid = verify_hmac(data, signature, key)
        
        assert is_valid
        assert isinstance(signature, str)
        
        # Verify invalid signature fails
        assert not verify_hmac(data, "invalid-signature", key)
        assert not verify_hmac("different data", signature, key)
    
    def test_hmac_with_key_id(self):
        """Test HMAC using key ID."""
        # Set up test key
        os.environ["CRYPTO_KEY_HMAC_TEST"] = base64.b64encode(b"test-hmac-key").decode()
        
        data = "test data"
        signature = calculate_hmac(data, key_id="hmac_test")
        is_valid = verify_hmac(data, signature, key_id="hmac_test")
        
        assert is_valid
        
        # Cleanup
        del os.environ["CRYPTO_KEY_HMAC_TEST"]
        clear_key_cache()


class TestHashing:
    """Test hashing functionality."""
    
    def test_hash_data(self):
        """Test data hashing."""
        data = "test data"
        hash_value = hash_data(data)
        
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA-256 hex length
        
        # Same data should produce same hash
        assert hash_data(data) == hash_value
        
        # Different data should produce different hash
        assert hash_data("different data") != hash_value
    
    def test_hash_file(self, tmp_path):
        """Test file hashing."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test file content")
        
        hash_value = hash_file(str(test_file))
        
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA-256 hex length
        
        # Same file should produce same hash
        assert hash_file(str(test_file)) == hash_value
        
        # Different file should produce different hash
        test_file2 = tmp_path / "test2.txt"
        test_file2.write_text("different content")
        assert hash_file(str(test_file2)) != hash_value
    
    def test_hash_algorithms(self):
        """Test different hash algorithms."""
        data = "test data"
        
        sha256_hash = hash_data(data, "sha256")
        blake3_hash = hash_data(data, "blake3")
        
        assert isinstance(sha256_hash, str)
        assert isinstance(blake3_hash, str)
        assert len(sha256_hash) == 64
        # BLAKE3 might not be available, so it falls back to SHA-256
        assert len(blake3_hash) >= 64


class TestKeyManagement:
    """Test key management functionality."""
    
    def test_environment_key_retrieval(self):
        """Test retrieving keys from environment variables."""
        # Set up test key
        test_key = "test-environment-key"
        os.environ["CRYPTO_KEY_ENV_TEST"] = base64.b64encode(test_key.encode()).decode()
        
        retrieved_key = get_key("env_test")
        assert retrieved_key == test_key.encode()
        
        # Cleanup
        del os.environ["CRYPTO_KEY_ENV_TEST"]
        clear_key_cache()
    
    def test_key_rotation(self):
        """Test key rotation functionality."""
        old_key = b"old-key"
        new_key = b"new-key"
        
        # Set initial key
        os.environ["CRYPTO_KEY_ROTATE_TEST"] = base64.b64encode(old_key).decode()
        
        # Verify old key retrieval
        assert get_key("rotate_test") == old_key
        
        # Rotate key
        rotate_key("rotate_test", new_key)
        
        # Verify new key retrieval
        assert get_key("rotate_test") == new_key
        
        # Cleanup
        if "CRYPTO_KEY_ROTATE_TEST" in os.environ:
            del os.environ["CRYPTO_KEY_ROTATE_TEST"]
        clear_key_cache()
    
    def test_development_fallback(self):
        """Test development environment fallback key."""
        # Set development environment
        os.environ["ENVIRONMENT"] = "development"
        
        # Key should be generated automatically
        key = get_key("nonexistent_key")
        assert key is not None
        assert b"dev-key-nonexistent_key" == key
        
        # Cleanup
        if "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]
        clear_key_cache()


class TestIntegration:
    """Integration tests combining multiple features."""
    
    def test_audit_service_compatibility(self):
        """Test compatibility with audit-service patterns."""
        # Simulate audit service usage
        data = "audit event data"
        
        # Test signing (audit service uses Ed25519)
        private_key, public_key = generate_signing_key("ed25519")
        signature = sign(data, private_key, "ed25519")
        assert verify_signature(data, signature, public_key, "ed25519")
        
        # Test HMAC (audit service uses HMAC)
        hmac_key = "audit-hmac-key"
        hmac_signature = calculate_hmac(data, hmac_key)
        assert verify_hmac(data, hmac_signature, hmac_key)
        
        # Test encryption (audit service uses AES-GCM)
        encryption_key = "audit-encryption-key-32-bytes"
        encrypted = encrypt(data, encryption_key)
        decrypted = decrypt(encrypted, encryption_key)
        assert decrypted.decode() == data
    
    def test_oms_monolith_compatibility(self):
        """Test compatibility with oms-monolith patterns."""
        # Simulate oms-monolith usage
        policy_content = "policy document content"
        
        # Test RSA signing (oms-monolith uses RSA)
        private_key, public_key = generate_signing_key("rsa-pss")
        signature = sign(policy_content, private_key, "rsa-pss")
        assert verify_signature(policy_content, signature, public_key, "rsa-pss")
        
        # Test hashing (oms-monolith uses SHA-256)
        hash_value = hash_data(policy_content)
        assert len(hash_value) == 64
        
        # Test PII encryption (replacing Fernet)
        pii_data = "sensitive personal information"
        encrypted = encrypt_text(pii_data, "pii-encryption-key")
        decrypted = decrypt_text(encrypted, "pii-encryption-key")
        assert decrypted == pii_data
    
    def test_end_to_end_workflow(self):
        """Test complete end-to-end cryptographic workflow."""
        # Setup keys
        encryption_key = "workflow-encryption-key-32-bytes"
        signing_private_key, signing_public_key = generate_signing_key("ed25519")
        hmac_key = "workflow-hmac-key"
        
        # Original data
        original_data = "important business data"
        
        # Step 1: Hash the data
        data_hash = hash_data(original_data)
        
        # Step 2: Sign the hash
        signature = sign(data_hash, signing_private_key, "ed25519")
        
        # Step 3: Create HMAC for integrity
        hmac_signature = calculate_hmac(original_data, hmac_key)
        
        # Step 4: Encrypt the data
        encrypted_data = encrypt_text(original_data, encryption_key)
        
        # Verification workflow
        # Step 1: Decrypt the data
        decrypted_data = decrypt_text(encrypted_data, encryption_key)
        assert decrypted_data == original_data
        
        # Step 2: Verify HMAC
        assert verify_hmac(decrypted_data, hmac_signature, hmac_key)
        
        # Step 3: Verify hash
        assert hash_data(decrypted_data) == data_hash
        
        # Step 4: Verify signature
        assert verify_signature(data_hash, signature, signing_public_key, "ed25519")