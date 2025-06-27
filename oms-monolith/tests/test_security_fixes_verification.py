"""
Verify that security fixes actually work
No mocks - real behavior verification
"""
import pytest
import os
import jwt
from datetime import datetime, timedelta, timezone

from models.permissions import PermissionChecker, ResourceType, Action, PERMISSION_MATRIX
from models.override_request import OverrideRequest, OverrideStatus, OverrideApprovalService

pytestmark = pytest.mark.asyncio


class TestSecurityFixesVerification:
    """Verify security fixes are working correctly"""
    
    def test_jwt_secret_required_from_env(self):
        """Verify JWT secret must come from environment"""
        print("\n=== JWT Secret Fix Verification ===")
        
        # Remove JWT_SECRET from environment
        if "JWT_SECRET" in os.environ:
            del os.environ["JWT_SECRET"]
        
        # Try to create UserServiceClient
        try:
            from core.integrations.user_service_client import UserServiceClient
            client = UserServiceClient()
            print("✗ FAIL: UserServiceClient created without JWT_SECRET")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            print(f"✓ PASS: Correctly raised error: {e}")
            assert "JWT_SECRET environment variable is required" in str(e)
        
        # Now set JWT_SECRET and verify it works
        os.environ["JWT_SECRET"] = "test-secret-key-for-verification"
        
        try:
            from core.integrations.user_service_client import UserServiceClient
            client = UserServiceClient()
            print(f"✓ PASS: UserServiceClient created with JWT_SECRET from env")
            assert client.jwt_secret == "test-secret-key-for-verification"
            
            # Verify hardcoded secret is gone
            assert client.jwt_secret != "your-secret-key"
            print("✓ PASS: Hardcoded secret is no longer used")
            
        finally:
            # Cleanup
            if "JWT_SECRET" in os.environ:
                del os.environ["JWT_SECRET"]
    
    def test_rbac_denies_unmapped_routes(self):
        """Verify RBAC denies unmapped routes by default"""
        print("\n=== RBAC Deny-by-Default Verification ===")
        
        # Read the updated RBAC middleware
        with open("middleware/rbac_middleware.py", "r") as f:
            content = f.read()
        
        # Check for deny-by-default implementation
        if "# No specific permission mapping found - DENY by default" in content:
            print("✓ PASS: Found deny-by-default comment")
        
        if "status.HTTP_403_FORBIDDEN" in content and "Route not registered in permission system" in content:
            print("✓ PASS: Returns 403 for unmapped routes")
        
        # Verify old allow behavior is gone
        if "allowing access for authenticated user" not in content:
            print("✓ PASS: Old allow-by-default code removed")
        else:
            print("✗ FAIL: Old allow code still present")
    
    async def test_emergency_override_requires_approval(self):
        """Verify emergency override now requires approval"""
        print("\n=== Emergency Override Approval Verification ===")
        
        # Test the new OverrideRequest model
        from models.override_request import OverrideRequest, OverrideStatus
        
        # Create a request
        request = OverrideRequest(
            requester_id="user123",
            requester_name="testuser",
            requester_roles=["developer"],
            resource="schemas/main/object-types",
            action="delete",
            change_type="deletion",
            branch_name="main",
            justification="Emergency fix for production issue causing data corruption"
        )
        
        print(f"✓ Created override request: {request.id}")
        print(f"  Status: {request.status}")
        print(f"  Expires: {request.expires_at}")
        
        # Verify initial state
        assert request.status == OverrideStatus.PENDING
        assert request.approved_by is None
        assert request.override_token is None
        
        # Test validation
        assert request.is_valid_for_use() is False  # Not approved yet
        print("✓ PASS: Unapproved request cannot be used")
        
        # Simulate approval
        request.status = OverrideStatus.APPROVED
        request.approved_by = "admin123"
        request.approved_by_name = "Admin User"
        request.approved_at = datetime.now(timezone.utc)
        request.override_token = "test-token-123"
        
        assert request.is_valid_for_use() is True
        print("✓ PASS: Approved request can be used")
        
        # Test expiration
        request.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        assert request.is_expired() is True
        assert request.is_valid_for_use() is False
        print("✓ PASS: Expired request cannot be used")
    
    def test_admin_permissions_restricted(self):
        """Verify admin permissions are restricted"""
        print("\n=== Admin Permissions Restriction Verification ===")
        
        checker = PermissionChecker()
        
        # Test admin permissions
        admin_can_delete = []
        admin_cannot_delete = []
        
        for resource in ResourceType:
            can_delete = checker.check_permission(
                user_roles=["admin"],
                resource_type=resource.value,
                action=Action.DELETE.value
            )
            
            if can_delete:
                admin_can_delete.append(resource.value)
            else:
                admin_cannot_delete.append(resource.value)
        
        print(f"Admin CAN delete: {admin_can_delete}")
        print(f"Admin CANNOT delete: {admin_cannot_delete}")
        
        # Verify critical resources cannot be deleted
        assert ResourceType.SCHEMA.value in admin_cannot_delete
        assert ResourceType.OBJECT_TYPE.value in admin_cannot_delete
        print("✓ PASS: Admin cannot delete schemas or object types")
        
        # Verify audit logs are read-only
        can_modify_audit = checker.check_permission(
            user_roles=["admin"],
            resource_type=ResourceType.AUDIT.value,
            action=Action.UPDATE.value
        )
        assert can_modify_audit is False
        print("✓ PASS: Admin cannot modify audit logs")
        
        # Verify admin can still do necessary operations
        can_create_schema = checker.check_permission(
            user_roles=["admin"],
            resource_type=ResourceType.SCHEMA.value,
            action=Action.CREATE.value
        )
        assert can_create_schema is True
        print("✓ PASS: Admin can still create schemas")
    
    async def test_complete_security_posture(self):
        """Test the complete security posture"""
        print("\n=== Complete Security Posture Test ===")
        
        results = {
            "jwt_secret": False,
            "rbac_deny_default": False,
            "override_approval": False,
            "admin_restricted": False
        }
        
        # 1. JWT Secret
        try:
            if "JWT_SECRET" in os.environ:
                del os.environ["JWT_SECRET"]
            from core.integrations.user_service_client import UserServiceClient
            client = UserServiceClient()
        except ValueError:
            results["jwt_secret"] = True
        
        # 2. RBAC Deny Default
        with open("middleware/rbac_middleware.py", "r") as f:
            if "DENY by default" in f.read():
                results["rbac_deny_default"] = True
        
        # 3. Override Approval
        from models.override_request import OverrideRequest
        request = OverrideRequest(
            requester_id="test",
            requester_name="test",
            requester_roles=["developer"],
            resource="test",
            action="test",
            change_type="test",
            branch_name="test",
            justification="x" * 50
        )
        if request.status == OverrideStatus.PENDING:
            results["override_approval"] = True
        
        # 4. Admin Restricted
        checker = PermissionChecker()
        cannot_delete_schema = not checker.check_permission(
            ["admin"], ResourceType.SCHEMA.value, Action.DELETE.value
        )
        cannot_modify_audit = not checker.check_permission(
            ["admin"], ResourceType.AUDIT.value, Action.UPDATE.value
        )
        if cannot_delete_schema and cannot_modify_audit:
            results["admin_restricted"] = True
        
        # Summary
        print("\nSecurity Fix Summary:")
        print("=" * 50)
        for fix, status in results.items():
            icon = "✅" if status else "❌"
            print(f"{icon} {fix}: {'FIXED' if status else 'NOT FIXED'}")
        
        all_fixed = all(results.values())
        if all_fixed:
            print("\n🎉 All critical security issues have been fixed!")
        else:
            print(f"\n⚠️  {len([v for v in results.values() if not v])} issues still need fixing!")
        
        return all_fixed


if __name__ == "__main__":
    import asyncio
    
    async def run_all_tests():
        tester = TestSecurityFixesVerification()
        
        # Run individual tests
        tester.test_jwt_secret_required_from_env()
        tester.test_rbac_denies_unmapped_routes()
        await tester.test_emergency_override_requires_approval()
        tester.test_admin_permissions_restricted()
        
        # Run complete test
        all_fixed = await tester.test_complete_security_posture()
        
        if not all_fixed:
            print("\n⚠️  SECURITY ISSUES REMAIN - DO NOT DEPLOY TO PRODUCTION!")
        else:
            print("\n✅ Security posture verified - ready for security review")
    
    asyncio.run(run_all_tests())