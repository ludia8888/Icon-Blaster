"""
Test JWT authentication
"""
import pytest
import jwt
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from core.integrations.user_service_client import UserServiceClient


def test_jwt_validation():
    """Test JWT validation works correctly"""
    # Create a valid JWT
    secret = "your-secret-key"
    payload = {
        "sub": "test-user",
        "user_id": "test-user", 
        "username": "testuser",
        "email": "test@example.com",
        "roles": ["admin", "developer"],
        "tenant_id": "test-tenant",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc)
    }
    
    token = jwt.encode(payload, secret, algorithm="HS256")
    
    # Test validation
    client = UserServiceClient()
    user_context = client._validate_token_locally(token)
    
    assert user_context.user_id == "test-user"
    assert user_context.username == "testuser"
    assert user_context.email == "test@example.com"
    assert "admin" in user_context.roles
    assert "developer" in user_context.roles


def test_expired_jwt():
    """Test expired JWT is rejected"""
    secret = "your-secret-key"
    payload = {
        "sub": "test-user",
        "username": "testuser",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
        "iat": datetime.now(timezone.utc) - timedelta(hours=2)
    }
    
    token = jwt.encode(payload, secret, algorithm="HS256")
    
    client = UserServiceClient()
    with pytest.raises(Exception) as exc_info:
        client._validate_token_locally(token)
    
    assert "expired" in str(exc_info.value).lower()


def test_invalid_jwt():
    """Test invalid JWT is rejected"""
    client = UserServiceClient()
    
    with pytest.raises(Exception) as exc_info:
        client._validate_token_locally("invalid.jwt.token")
    
    assert "invalid" in str(exc_info.value).lower()


def test_auth_endpoint_with_valid_jwt():
    """Test authenticated endpoint with valid JWT"""
    from main import app
    client = TestClient(app)
    
    # Create valid JWT
    secret = "your-secret-key"
    payload = {
        "sub": "test-user",
        "user_id": "test-user",
        "username": "testuser", 
        "email": "test@example.com",
        "roles": ["admin"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc)
    }
    
    token = jwt.encode(payload, secret, algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test health endpoint (public, no auth needed)
    response = client.get("/health")
    assert response.status_code == 200
    
    # Test authenticated endpoint  
    response = client.get("/api/v1/idempotent/consumers/schema_consumer/status", headers=headers)
    # Should be 200 if auth works, or 404 if consumer not found (but not 401)
    assert response.status_code in [200, 404]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])