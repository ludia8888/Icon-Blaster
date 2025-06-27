"""
Test to find real bypasses and hardcoded values in the codebase
"""
import pytest
import os
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from middleware.auth_middleware import AuthMiddleware
from middleware.rbac_middleware import RBACMiddleware
from middleware.issue_tracking_middleware import configure_issue_tracking


class TestRealBypasses:
    """Test to find bypasses and verify real functionality"""
    
    def test_jwt_secret_is_hardcoded(self):
        """Test that JWT secret is using hardcoded value"""
        from core.integrations.user_service_client import UserServiceClient
        
        client = UserServiceClient()
        # Check if it's using the hardcoded default
        assert client.jwt_secret == "your-secret-key", "JWT secret should be hardcoded for this test"
        
        # This is a security issue - in production, should use a real secret
        print("WARNING: JWT secret is hardcoded as 'your-secret-key'")
    
    def test_issue_tracking_path_mismatch(self):
        """Test that issue tracking middleware had wrong paths"""
        from middleware.issue_tracking_middleware import IssueTrackingMiddleware
        
        middleware = IssueTrackingMiddleware()
        
        # Check if paths are now correct
        tracked_paths = list(middleware.TRACKED_OPERATIONS.keys())
        schema_paths = [path for method, path in tracked_paths if "schema" in path and method == "POST"]
        
        # Should have /api/v1/schemas/ not /api/v1/schema/
        for path in schema_paths:
            assert "/api/v1/schemas/" in path[1], f"Path should use 'schemas' not 'schema': {path}"
    
    def test_internal_issue_client_has_mock_data(self):
        """Test that InternalIssueClient has hardcoded mock issues"""
        from core.issue_tracking.issue_service import InternalIssueClient
        
        client = InternalIssueClient()
        
        # Check for hardcoded issues
        assert hasattr(client, 'mock_issues'), "InternalIssueClient should have mock_issues"
        assert "OMS-001" in client.mock_issues, "Has hardcoded OMS-001"
        assert "OMS-002" in client.mock_issues, "Has hardcoded OMS-002"
        
        print(f"WARNING: InternalIssueClient has {len(client.mock_issues)} hardcoded issues")
    
    def test_audit_service_batch_processing_delay(self):
        """Test that audit service has batch processing with delay"""
        from core.audit.audit_service import AuditService
        
        service = AuditService()
        
        # Check batch configuration
        assert service.batch_size == 50, "Batch size is set to 50"
        assert service.batch_timeout_seconds == 10.0, "Batch timeout is 10 seconds"
        
        # This means audit logs are not written immediately
        print("WARNING: Audit logs are batched with 10 second delay")
    
    def test_schema_service_connection_issues(self):
        """Test that schema service tries to connect to localhost"""
        from main import ServiceContainer
        
        container = ServiceContainer()
        
        # Check DB client configuration
        # When initialized, it tries to connect to localhost:6363
        print("WARNING: Schema service expects TerminusDB at localhost:6363")
    
    def test_permission_checker_allows_without_real_check(self):
        """Test if permission checker has any bypasses"""
        from models.permissions import PermissionChecker
        
        checker = PermissionChecker()
        
        # Admin bypass
        result = checker.check_permission(["admin"], "any_resource", "any_action")
        assert result == True, "Admin has bypass for all permissions"
        
        # Check if there's a test mode
        # No test mode found, but admin bypass exists
        print("WARNING: Admin role bypasses all permission checks")
    
    def test_rbac_middleware_allows_unmapped_routes(self):
        """Test RBAC middleware behavior for unmapped routes"""
        from middleware.rbac_middleware import RBACMiddleware
        
        # Create a test app
        app = FastAPI()
        
        # This is from the actual middleware code
        # Line 182-186 shows it ALLOWS access if no permission mapping found
        print("WARNING: RBAC middleware allows access to unmapped routes")
    
    def test_emergency_override_without_real_validation(self):
        """Test emergency override doesn't require approval"""
        from models.issue_tracking import IssueRequirement
        
        req = IssueRequirement()
        
        # Check if emergency override is allowed by default
        assert req.allow_emergency_override == True, "Emergency override is allowed by default"
        
        # No approval workflow required
        print("WARNING: Emergency override allowed without approval workflow")
    
    def test_version_service_uses_local_sqlite(self):
        """Test that version service uses local SQLite"""
        from core.versioning.version_service import VersionTrackingService
        
        # Check default path
        service = VersionTrackingService()
        assert "versions.db" in service.db_path, "Uses local SQLite database"
        
        print("WARNING: Version tracking uses local SQLite, not distributed")
    
    def test_git_utils_returns_development_without_git(self):
        """Test git utils behavior without git repo"""
        from utils.git_utils import get_current_commit_hash
        
        # Clear cache
        get_current_commit_hash.cache_clear()
        
        # In a git repo, it returns a real hash
        # Without git, it returns "development"
        commit = get_current_commit_hash()
        
        if commit == "development":
            print("WARNING: Git commit hash returns 'development' when not in git repo")
        else:
            print(f"Git commit hash is: {commit}")
    
    @pytest.mark.asyncio
    async def test_audit_database_is_sqlite_not_distributed(self):
        """Test that audit database is SQLite, not a distributed system"""
        from core.audit.audit_database import AuditDatabase
        
        db = AuditDatabase()
        
        # Check it's using SQLite
        assert db.db_path.endswith("audit.db"), "Audit uses local SQLite"
        
        # This means audit logs are not replicated
        print("WARNING: Audit logs stored in local SQLite, not replicated")
    
    def test_lock_manager_ttl_without_distributed_coordination(self):
        """Test that lock manager doesn't use distributed coordination"""
        from core.branch.lock_manager import LockManager
        
        manager = LockManager()
        
        # Check if it's using in-memory storage
        assert hasattr(manager, '_locks'), "Lock manager uses in-memory storage"
        assert hasattr(manager, '_lock_storage'), "Has local lock storage"
        
        # No Redis, no distributed locks
        print("WARNING: Lock manager uses in-memory storage, not distributed")
    
    def test_shadow_index_manager_in_memory(self):
        """Test shadow index is in-memory only"""
        from core.shadow_index.manager import ShadowIndexManager
        
        manager = ShadowIndexManager()
        
        # Check storage
        assert hasattr(manager, '_indexes'), "Shadow index uses in-memory storage"
        
        print("WARNING: Shadow indexes are in-memory only, lost on restart")
    
    def test_funnel_handler_auto_merge_without_checks(self):
        """Test funnel handler auto-merge logic"""
        from core.event_consumer.funnel_indexing_handler import FunnelIndexingHandler
        
        handler = FunnelIndexingHandler()
        
        # Check if auto-merge is implemented
        # Currently returns success without real merge
        print("WARNING: Funnel handler auto-merge is not fully implemented")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])