"""
Test auth middleware flow
"""
import pytest
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from core.auth import UserContext
from middleware.auth_middleware import AuthMiddleware, get_current_user


def test_middleware_flow():
    """Test that middleware sets user correctly"""
    # Create a minimal app with just auth middleware
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    
    @app.get("/test")
    def test_endpoint(user: UserContext = Depends(get_current_user)):
        return {"user_id": user.user_id, "username": user.username}
    
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
    
    # Test the endpoint
    response = client.get("/test", headers=headers)
    
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.text}")
    
    # Should work
    assert response.status_code == 200
    assert response.json()["user_id"] == "test-user"


def test_middleware_with_testclient():
    """Test middleware with TestClient directly"""
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
    
    # Check if auth header is being passed correctly
    with client as c:
        # Use the internal httpx client
        headers = {"Authorization": f"Bearer {token}"}
        response = c.get("/api/v1/idempotent/consumers/schema_consumer/status", headers=headers)
        
        print(f"\nDirect client response: {response.status_code}")
        print(f"Headers sent: {headers}")
        print(f"Response: {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])