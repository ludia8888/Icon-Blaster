"""
Real RBAC tests without mocks - verify actual permission enforcement
"""
import pytest
import jwt
import os
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from main import app


class TestRBACReal:
    """Test RBAC with real requests and JWT tokens"""
    
    @pytest.fixture
    def jwt_secret(self):
        """Get actual JWT secret from environment"""
        # First try to get from env, fallback to the hardcoded one
        return os.getenv("JWT_SECRET", "your-secret-key")
    
    def create_jwt_token(self, username: str, roles: list, jwt_secret: str) -> str:
        """Create a real JWT token"""
        payload = {
            "sub": f"user-{username}",
            "user_id": f"user-{username}",
            "username": username,
            "email": f"{username}@example.com",
            "roles": roles,
            "tenant_id": "test-tenant",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc)
        }
        return jwt.encode(payload, jwt_secret, algorithm="HS256")
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    def test_no_auth_returns_401(self, client):
        """Protected endpoints should return 401 without auth"""
        # Try various protected endpoints
        endpoints = [
            "/api/v1/schemas/main/object-types",
            "/api/v1/branches",
            "/api/v1/proposals",
            "/api/v1/audit"
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 401, f"Expected 401 for {endpoint}, got {response.status_code}"
            assert "Authorization header missing" in response.json()["detail"]
    
    def test_developer_permissions_real(self, client, jwt_secret):
        """Test developer role with real endpoints"""
        token = self.create_jwt_token("developer1", ["developer"], jwt_secret)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Developer CAN read object types
        response = client.get("/api/v1/schemas/main/object-types", headers=headers)
        assert response.status_code == 200, f"Developer should be able to read object types: {response.text}"
        
        # Developer CAN create object types
        response = client.post(
            "/api/v1/schemas/main/object-types",
            headers=headers,
            json={
                "type_id": "TestObject",
                "name": "Test Object",
                "properties": {}
            }
        )
        # Should be 200 or 422 (validation error) but NOT 403
        assert response.status_code != 403, f"Developer should be able to create object types: {response.text}"
        
        # Developer CANNOT approve proposals
        response = client.post(
            "/api/v1/proposals/test-proposal/approve",
            headers=headers,
            json={"comment": "Approved"}
        )
        assert response.status_code == 403, f"Developer should NOT be able to approve proposals: {response.text}"
        assert "Permission denied" in response.json()["detail"]
    
    def test_viewer_permissions_real(self, client, jwt_secret):
        """Test viewer role with real endpoints"""
        token = self.create_jwt_token("viewer1", ["viewer"], jwt_secret)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Viewer CAN read
        response = client.get("/api/v1/schemas/main/object-types", headers=headers)
        assert response.status_code == 200, f"Viewer should be able to read: {response.text}"
        
        # Viewer CANNOT create
        response = client.post(
            "/api/v1/schemas/main/object-types",
            headers=headers,
            json={
                "type_id": "TestObject",
                "name": "Test Object",
                "properties": {}
            }
        )
        assert response.status_code == 403, f"Viewer should NOT be able to create: {response.text}"
        assert "Permission denied" in response.json()["detail"]
        
        # Viewer CANNOT update
        response = client.put(
            "/api/v1/schemas/main/object-types/Person",
            headers=headers,
            json={
                "name": "Updated Person",
                "properties": {}
            }
        )
        assert response.status_code == 403, f"Viewer should NOT be able to update: {response.text}"
    
    def test_reviewer_permissions_real(self, client, jwt_secret):
        """Test reviewer role with real endpoints"""
        token = self.create_jwt_token("reviewer1", ["reviewer"], jwt_secret)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Reviewer CAN read proposals
        response = client.get("/api/v1/proposals", headers=headers)
        assert response.status_code in [200, 404], f"Reviewer should be able to read proposals: {response.text}"
        
        # Reviewer CAN approve proposals (though might get 404 if proposal doesn't exist)
        response = client.post(
            "/api/v1/proposals/test-proposal/approve",
            headers=headers,
            json={"comment": "Approved"}
        )
        # Should NOT be 403 (might be 404 if proposal doesn't exist)
        assert response.status_code != 403, f"Reviewer should be able to approve proposals: {response.text}"
        
        # Reviewer CANNOT create object types
        response = client.post(
            "/api/v1/schemas/main/object-types",
            headers=headers,
            json={
                "type_id": "TestObject",
                "name": "Test Object",
                "properties": {}
            }
        )
        assert response.status_code == 403, f"Reviewer should NOT be able to create: {response.text}"
    
    def test_admin_permissions_real(self, client, jwt_secret):
        """Test admin role with real endpoints"""
        token = self.create_jwt_token("admin1", ["admin"], jwt_secret)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Admin CAN do everything
        endpoints_and_methods = [
            ("GET", "/api/v1/schemas/main/object-types"),
            ("POST", "/api/v1/schemas/main/object-types"),
            ("GET", "/api/v1/branches"),
            ("POST", "/api/v1/branches"),
            ("GET", "/api/v1/proposals"),
            ("POST", "/api/v1/proposals/test/approve"),
            ("GET", "/api/v1/audit")
        ]
        
        for method, endpoint in endpoints_and_methods:
            if method == "GET":
                response = client.get(endpoint, headers=headers)
            else:
                response = client.post(endpoint, headers=headers, json={})
            
            # Admin should never get 403
            assert response.status_code != 403, f"Admin should have access to {method} {endpoint}: {response.text}"
    
    def test_multiple_roles_permissions(self, client, jwt_secret):
        """Test user with multiple roles"""
        # User with both developer and reviewer roles
        token = self.create_jwt_token("multi1", ["developer", "reviewer"], jwt_secret)
        headers = {"Authorization": f"Bearer {token}"}
        
        # Should have combined permissions
        # Can create (developer permission)
        response = client.post(
            "/api/v1/schemas/main/object-types",
            headers=headers,
            json={
                "type_id": "TestObject",
                "name": "Test Object",
                "properties": {}
            }
        )
        assert response.status_code != 403, "Multi-role user should be able to create"
        
        # Can approve (reviewer permission)
        response = client.post(
            "/api/v1/proposals/test-proposal/approve",
            headers=headers,
            json={"comment": "Approved"}
        )
        assert response.status_code != 403, "Multi-role user should be able to approve"
    
    def test_invalid_jwt_rejected(self, client):
        """Test that invalid JWT is rejected"""
        # Invalid token
        headers = {"Authorization": "Bearer invalid.jwt.token"}
        
        response = client.get("/api/v1/schemas/main/object-types", headers=headers)
        assert response.status_code == 401, "Invalid JWT should be rejected"
    
    def test_expired_jwt_rejected(self, client, jwt_secret):
        """Test that expired JWT is rejected"""
        # Create expired token
        payload = {
            "sub": "expired-user",
            "user_id": "expired-user",
            "username": "expired",
            "email": "expired@example.com",
            "roles": ["admin"],
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
            "iat": datetime.now(timezone.utc) - timedelta(hours=2)
        }
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.get("/api/v1/schemas/main/object-types", headers=headers)
        assert response.status_code == 401, "Expired JWT should be rejected"
        assert "expired" in response.json()["detail"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])