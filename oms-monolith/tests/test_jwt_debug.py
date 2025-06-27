"""
Debug JWT authentication issue
"""
import pytest
import jwt
import logging
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)


def test_auth_middleware_debug():
    """Debug auth middleware with logging"""
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
    
    print(f"\nGenerated token: {token[:50]}...")
    print(f"Token payload: {payload}")
    
    # Test authenticated endpoint with debug
    response = client.get("/api/v1/idempotent/consumers/schema_consumer/status", headers=headers)
    
    print(f"\nResponse status: {response.status_code}")
    print(f"Response body: {response.text}")
    
    if response.status_code == 401:
        # Try to decode locally to see if it works
        from core.integrations.user_service_client import UserServiceClient
        client_service = UserServiceClient()
        try:
            user = client_service._validate_token_locally(token)
            print(f"\nLocal validation succeeded: {user}")
        except Exception as e:
            print(f"\nLocal validation failed: {e}")


if __name__ == "__main__":
    test_auth_middleware_debug()