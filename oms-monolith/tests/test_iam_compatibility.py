"""
Compatibility verification tests for IAM MSA integration
Ensures exact backward compatibility with existing code
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import inspect

from core.auth import UserContext
from models.permissions import Role


class TestBackwardCompatibility:
    """Verify that refactored implementation maintains exact compatibility"""
    
    def test_iam_scope_import_compatibility(self):
        """Test that IAMScope can be imported from multiple locations"""
        # Original import path
        from core.iam.iam_integration import IAMScope as OriginalIAMScope
        
        # New import path
        from shared.iam_contracts import IAMScope as NewIAMScope
        
        # Both should have same values
        assert OriginalIAMScope.SCHEMAS_READ == NewIAMScope.SCHEMAS_READ
        assert OriginalIAMScope.SYSTEM_ADMIN == NewIAMScope.SYSTEM_ADMIN
        assert OriginalIAMScope.PROPOSALS_APPROVE == NewIAMScope.PROPOSALS_APPROVE
        
        # Test string values are identical
        assert str(OriginalIAMScope.ONTOLOGIES_WRITE) == str(NewIAMScope.ONTOLOGIES_WRITE)
    
    def test_method_signatures_match(self):
        """Verify all public method signatures are identical"""
        from core.iam.iam_integration import IAMIntegration as Original
        from core.iam.iam_integration_refactored import IAMIntegration as Refactored
        
        # Get all public methods
        original_methods = {
            name: inspect.signature(method) 
            for name, method in inspect.getmembers(Original, inspect.isfunction)
            if not name.startswith('_')
        }
        
        refactored_methods = {
            name: inspect.signature(method)
            for name, method in inspect.getmembers(Refactored, inspect.isfunction)
            if not name.startswith('_')
        }
        
        # Critical methods that must exist
        critical_methods = [
            'validate_jwt_enhanced',
            'check_scope',
            'check_any_scope',
            'check_all_scopes',
            'get_user_info',
            'refresh_token',
            'get_required_scopes'
        ]
        
        for method_name in critical_methods:
            assert method_name in original_methods, f"Missing {method_name} in original"
            assert method_name in refactored_methods, f"Missing {method_name} in refactored"
            
            # Signatures should match
            orig_sig = str(original_methods[method_name])
            refact_sig = str(refactored_methods[method_name])
            assert orig_sig == refact_sig, f"Signature mismatch for {method_name}: {orig_sig} != {refact_sig}"
    
    @pytest.mark.asyncio
    async def test_validate_jwt_enhanced_compatibility(self):
        """Test that validate_jwt_enhanced returns compatible UserContext"""
        from core.iam.iam_integration_refactored import IAMIntegration
        from shared.iam_contracts import TokenValidationResponse, IAMScope
        
        # Mock the IAM client
        integration = IAMIntegration()
        mock_client = AsyncMock()
        integration.client = mock_client
        
        # Mock validation response
        mock_client.validate_token.return_value = TokenValidationResponse(
            valid=True,
            user_id="test123",
            username="testuser",
            email="test@example.com",
            scopes=[IAMScope.SCHEMAS_WRITE, IAMScope.PROPOSALS_READ],
            roles=["custom_role"],
            tenant_id="tenant1",
            expires_at="2024-12-31T23:59:59Z",
            metadata={"auth_time": 12345}
        )
        
        # Call the method
        result = await integration.validate_jwt_enhanced("test-token")
        
        # Verify UserContext structure
        assert isinstance(result, UserContext)
        assert result.user_id == "test123"
        assert result.username == "testuser"
        assert result.email == "test@example.com"
        assert "developer" in result.roles  # Should be mapped from scopes
        assert "custom_role" in result.roles  # Should keep original roles
        assert result.tenant_id == "tenant1"
        assert result.metadata["scopes"] == [IAMScope.SCHEMAS_WRITE, IAMScope.PROPOSALS_READ]
    
    def test_scope_checking_compatibility(self):
        """Test scope checking methods work identically"""
        from core.iam.iam_integration_refactored import IAMIntegration
        from shared.iam_contracts import IAMScope
        
        integration = IAMIntegration()
        
        # Create test user context
        user = UserContext(
            user_id="test123",
            username="testuser",
            roles=["developer"],
            metadata={
                "scopes": [
                    IAMScope.SCHEMAS_READ,
                    IAMScope.ONTOLOGIES_WRITE,
                    IAMScope.BRANCHES_READ
                ]
            }
        )
        
        # Test check_scope
        assert integration.check_scope(user, IAMScope.SCHEMAS_READ) is True
        assert integration.check_scope(user, IAMScope.SCHEMAS_WRITE) is False
        
        # Test check_any_scope
        assert integration.check_any_scope(user, [
            IAMScope.SCHEMAS_WRITE,  # Don't have
            IAMScope.BRANCHES_READ   # Have this
        ]) is True
        
        assert integration.check_any_scope(user, [
            IAMScope.SCHEMAS_WRITE,  # Don't have
            IAMScope.PROPOSALS_APPROVE  # Don't have
        ]) is False
        
        # Test check_all_scopes
        assert integration.check_all_scopes(user, [
            IAMScope.SCHEMAS_READ,
            IAMScope.BRANCHES_READ
        ]) is True
        
        assert integration.check_all_scopes(user, [
            IAMScope.SCHEMAS_READ,
            IAMScope.SCHEMAS_WRITE  # Don't have this
        ]) is False
    
    def test_get_required_scopes_compatibility(self):
        """Test that get_required_scopes returns same values"""
        from core.iam.iam_integration import IAMIntegration as Original
        from core.iam.iam_integration_refactored import IAMIntegration as Refactored
        from shared.iam_contracts import IAMScope
        
        orig = Original()
        refact = Refactored()
        
        # Test various resource/action combinations
        test_cases = [
            ("schema", "read"),
            ("schema", "create"),
            ("object_type", "delete"),
            ("branch", "merge"),
            ("proposal", "approve"),
            ("audit", "read")
        ]
        
        for resource, action in test_cases:
            orig_scopes = orig.get_required_scopes(resource, action)
            refact_scopes = refact.get_required_scopes(resource, action)
            
            # Convert to sets for comparison (order doesn't matter)
            assert set(orig_scopes) == set(refact_scopes), \
                f"Mismatch for {resource}:{action} - {orig_scopes} != {refact_scopes}"
    
    def test_singleton_pattern_compatibility(self):
        """Test that get_iam_integration returns singleton"""
        from core.iam.iam_integration import get_iam_integration as orig_get
        from core.iam.iam_integration_refactored import get_iam_integration as refact_get
        
        # Original should return singleton
        orig1 = orig_get()
        orig2 = orig_get()
        assert orig1 is orig2
        
        # Refactored should return singleton
        refact1 = refact_get()
        refact2 = refact_get()
        assert refact1 is refact2
    
    def test_scope_role_mapping_compatibility(self):
        """Test that scope role mapping still works with refactored code"""
        from models.scope_role_mapping import ScopeRoleMatrix
        from shared.iam_contracts import IAMScope
        
        # Test scope to role mapping
        scopes = [IAMScope.ONTOLOGIES_WRITE, IAMScope.SCHEMAS_READ]
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        
        assert Role.DEVELOPER in roles
        
        # Test validation
        is_valid, issues = ScopeRoleMatrix.validate_role_scope_assignment(
            Role.DEVELOPER,
            scopes
        )
        assert is_valid is True
        assert len(issues) == 0


class TestMigrationPath:
    """Test that migration from old to new works smoothly"""
    
    def test_compatibility_layer(self):
        """Test the compatibility layer works correctly"""
        import os
        
        # Test with MSA disabled (use original)
        os.environ['USE_MSA_AUTH'] = 'false'
        from core.iam.iam_integration_compat import get_iam_integration, IAMScope
        
        integration = get_iam_integration()
        assert integration is not None
        assert hasattr(integration, 'validate_jwt_enhanced')
        assert IAMScope.SCHEMAS_READ == "api:schemas:read"
        
        # Can't test with MSA enabled without proper mocking
        # as it would try to connect to actual IAM service


if __name__ == "__main__":
    pytest.main([__file__, "-v"])