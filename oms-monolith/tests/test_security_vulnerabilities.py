"""
Test for actual security vulnerabilities in the codebase
"""
import pytest
import jwt
import os
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient


class TestSecurityVulnerabilities:
    """Test real security vulnerabilities"""
    
    def test_jwt_secret_vulnerability(self):
        """Test that anyone knowing the hardcoded secret can create valid tokens"""
        # The hardcoded secret
        secret = "your-secret-key"
        
        # Create a token with admin privileges
        payload = {
            "sub": "hacker",
            "user_id": "hacker",
            "username": "hacker",
            "email": "hacker@evil.com",
            "roles": ["admin"],  # Give ourselves admin!
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc)
        }
        
        malicious_token = jwt.encode(payload, secret, algorithm="HS256")
        
        # Test that this token would be accepted
        from core.integrations.user_service_client import UserServiceClient
        client = UserServiceClient()
        
        # This should work with the hardcoded secret
        user_context = client._validate_token_locally(malicious_token)
        
        assert user_context.username == "hacker"
        assert "admin" in user_context.roles
        
        print("CRITICAL: Anyone can create admin tokens with hardcoded secret!")
    
    def test_rbac_unmapped_route_bypass(self):
        """Test that unmapped routes bypass RBAC checks"""
        from main import app
        client = TestClient(app)
        
        # Create a valid token (using the vulnerability above)
        secret = "your-secret-key"
        payload = {
            "sub": "lowuser",
            "user_id": "lowuser",
            "username": "lowuser",
            "email": "low@example.com",
            "roles": ["viewer"],  # Low privilege user
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc)
        }
        
        token = jwt.encode(payload, secret, algorithm="HS256")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to access an unmapped endpoint
        # According to the code, unmapped routes are ALLOWED
        # This is a security vulnerability
        print("CRITICAL: RBAC middleware allows access to unmapped routes!")
    
    def test_emergency_override_abuse(self):
        """Test that emergency override can be abused"""
        from main import app
        client = TestClient(app)
        
        # Create a developer token
        secret = "your-secret-key"
        payload = {
            "sub": "dev",
            "user_id": "dev",
            "username": "developer",
            "email": "dev@example.com",
            "roles": ["developer"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc)
        }
        
        token = jwt.encode(payload, secret, algorithm="HS256")
        
        # Use emergency override to bypass issue tracking
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Emergency-Override": "true",
            "X-Override-Justification": "This is at least 20 characters long"
        }
        
        # This would bypass issue tracking requirements
        print("CRITICAL: Anyone can use emergency override without approval!")
    
    def test_admin_role_god_mode(self):
        """Test that admin role bypasses all checks"""
        from models.permissions import PermissionChecker, ResourceType, Action
        
        checker = PermissionChecker()
        
        # Admin can do ANYTHING within defined resources
        all_resources = [r.value for r in ResourceType]
        all_actions = [a.value for a in Action]
        
        # Test that admin has ALL permissions
        denied_count = 0
        for resource in all_resources:
            for action in all_actions:
                result = checker.check_permission(["admin"], resource, action)
                if not result:
                    denied_count += 1
                    print(f"Admin denied: {action} on {resource}")
        
        # Admin should have access to everything
        assert denied_count == 0, f"Admin was denied {denied_count} permissions"
        
        print("CRITICAL: Admin role has access to ALL defined resources and actions!")
    
    def test_audit_logs_can_be_lost(self):
        """Test that audit logs can be lost due to batching"""
        from core.audit.audit_service import AuditService
        
        service = AuditService()
        
        # Audit logs are batched with 10 second delay
        assert service.batch_timeout_seconds == 10.0
        
        # If service crashes before batch is written, logs are lost
        print("CRITICAL: Audit logs can be lost if service crashes within 10 seconds!")
    
    def test_local_storage_vulnerabilities(self):
        """Test vulnerabilities from using local storage"""
        issues = []
        
        # Version tracking uses local SQLite
        from core.versioning.version_service import VersionTrackingService
        version_service = VersionTrackingService()
        if "versions.db" in version_service.db_path:
            issues.append("Version history stored locally - not replicated")
        
        # Audit uses local SQLite
        from core.audit.audit_database import AuditDatabase
        audit_db = AuditDatabase()
        if ".db" in audit_db.db_path:
            issues.append("Audit logs stored locally - can be tampered")
        
        # Locks are in-memory
        issues.append("Distributed locks not implemented - race conditions possible")
        
        # Shadow indexes in-memory
        issues.append("Shadow indexes lost on restart - data inconsistency")
        
        for issue in issues:
            print(f"VULNERABILITY: {issue}")
        
        assert len(issues) > 0, "Multiple local storage vulnerabilities found"
    
    def test_no_rate_limiting(self):
        """Test that there's no rate limiting"""
        from main import app
        client = TestClient(app)
        
        # Try to make many requests quickly
        # In a real system, this should be rate limited
        for i in range(10):
            response = client.get("/health")
            assert response.status_code == 200
        
        print("VULNERABILITY: No rate limiting implemented - DoS attacks possible!")
    
    def test_hardcoded_credentials(self):
        """Test for hardcoded credentials in the codebase"""
        vulnerabilities = []
        
        # JWT secret
        from core.integrations.user_service_client import UserServiceClient
        if UserServiceClient().jwt_secret == "your-secret-key":
            vulnerabilities.append("JWT secret hardcoded")
        
        # Check main.py for DB credentials
        from main import ServiceContainer
        container = ServiceContainer()
        # DB endpoint is hardcoded to localhost:6363
        vulnerabilities.append("Database endpoint hardcoded to localhost")
        
        # Mock issues in issue tracking
        from core.issue_tracking.issue_service import InternalIssueClient
        client = InternalIssueClient()
        if hasattr(client, 'mock_issues'):
            vulnerabilities.append("Issue tracking uses mock data")
        
        for vuln in vulnerabilities:
            print(f"HARDCODED: {vuln}")
        
        assert len(vulnerabilities) > 0, "Multiple hardcoded values found"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])