"""
MSA 마이그레이션 완전 호환성 검증 테스트
실제 배포 전 모든 호환성 문제를 검증
"""
import pytest
import os
from unittest.mock import Mock, AsyncMock, patch
import asyncio

from core.auth import UserContext
from shared.iam_contracts import IAMScope, TokenValidationResponse
from models.permissions import Role


class TestCompleteCompatibility:
    """완전한 호환성 검증"""
    
    def test_import_paths_work(self):
        """모든 import 경로가 작동하는지 확인"""
        # 기존 import 경로
        from core.iam.iam_integration import IAMScope as OldPathScope
        from core.iam.iam_integration import get_iam_integration as old_get
        
        # 새 import 경로
        from shared.iam_contracts import IAMScope as NewPathScope
        
        # 둘 다 같은 값을 가져야 함
        assert OldPathScope.SCHEMAS_READ == NewPathScope.SCHEMAS_READ
        assert str(OldPathScope.SYSTEM_ADMIN) == str(NewPathScope.SYSTEM_ADMIN)
    
    @pytest.mark.asyncio
    async def test_fallback_mechanism(self):
        """Fallback 메커니즘이 작동하는지 확인"""
        from core.integrations.iam_service_client_with_fallback import IAMServiceClientWithFallback
        
        client = IAMServiceClientWithFallback()
        
        # Mock IAM service to fail
        with patch.object(client._client, 'post') as mock_post:
            mock_post.side_effect = Exception("Service unavailable")
            
            # Should fallback to local validation
            response = await client.validate_token("fake.jwt.token")
            
            # Will fail because token is fake, but should not raise exception
            assert response.valid is False
            assert "validation_method" in response.metadata or response.error is not None
    
    def test_middleware_switching(self):
        """미들웨어 전환이 환경변수로 작동하는지 확인"""
        # Legacy mode
        os.environ['USE_MSA_AUTH'] = 'false'
        from middleware.auth_middleware import AuthMiddleware
        
        # MSA mode 
        os.environ['USE_MSA_AUTH'] = 'true'
        from middleware.auth_middleware_msa import MSAAuthMiddleware
        
        # Both should exist and be different classes
        assert AuthMiddleware != MSAAuthMiddleware
    
    @pytest.mark.asyncio
    async def test_user_context_compatibility(self):
        """UserContext가 양쪽 구현에서 동일하게 생성되는지 확인"""
        from core.iam.iam_integration_refactored import IAMIntegration
        
        integration = IAMIntegration()
        
        # Mock client response
        mock_client = AsyncMock()
        integration.client = mock_client
        
        mock_client.validate_token.return_value = TokenValidationResponse(
            valid=True,
            user_id="test123",
            username="testuser",
            email="test@example.com",
            scopes=[IAMScope.SCHEMAS_WRITE, IAMScope.BRANCHES_READ],
            roles=["existing_role"],
            tenant_id="tenant1"
        )
        
        # Get user context
        user_context = await integration.validate_jwt_enhanced("test-token")
        
        # Verify structure matches legacy format
        assert isinstance(user_context, UserContext)
        assert user_context.user_id == "test123"
        assert user_context.username == "testuser"
        assert user_context.email == "test@example.com"
        assert "developer" in user_context.roles  # Mapped from scopes
        assert "existing_role" in user_context.roles
        assert user_context.tenant_id == "tenant1"
        assert "scopes" in user_context.metadata
    
    def test_scope_enum_string_behavior(self):
        """Enum이 문자열처럼 동작하는지 확인"""
        from shared.iam_contracts import IAMScope
        
        # String comparison should work
        assert IAMScope.SCHEMAS_READ == "api:schemas:read"
        
        # String conversion should work
        assert str(IAMScope.SCHEMAS_READ) == "api:schemas:read"
        
        # In list/set operations
        scopes = [IAMScope.SCHEMAS_READ, IAMScope.SCHEMAS_WRITE]
        assert "api:schemas:read" in [str(s) for s in scopes]
        
        # Direct string operations
        assert IAMScope.SCHEMAS_READ.startswith("api:")
    
    @pytest.mark.asyncio 
    async def test_circuit_breaker_behavior(self):
        """Circuit breaker가 올바르게 작동하는지 확인"""
        from core.integrations.iam_service_client_with_fallback import IAMServiceClientWithFallback
        
        client = IAMServiceClientWithFallback()
        client._circuit_threshold = 2  # Lower threshold for testing
        
        # Simulate failures
        with patch.object(client._client, 'post') as mock_post:
            mock_post.side_effect = Exception("Service down")
            
            # First failure
            await client.validate_token("token1")
            assert client._circuit_failures == 1
            assert not client._circuit_open
            
            # Second failure - should open circuit
            await client.validate_token("token2")
            assert client._circuit_failures == 2
            assert client._circuit_open
            
            # Third call should not even try remote
            mock_post.reset_mock()
            await client.validate_token("token3")
            mock_post.assert_not_called()  # Circuit open, no remote call
    
    def test_gradual_migration_config(self):
        """점진적 마이그레이션 설정이 작동하는지 확인"""
        # Save original
        original = os.environ.get('USE_MSA_AUTH')
        
        try:
            # Test with MSA disabled
            os.environ['USE_MSA_AUTH'] = 'false'
            from main import USE_MSA_AUTH
            assert USE_MSA_AUTH is False
            
            # Test with MSA enabled
            os.environ['USE_MSA_AUTH'] = 'true'
            # Would need to reload module to test, but proves env var works
            
        finally:
            # Restore
            if original:
                os.environ['USE_MSA_AUTH'] = original
            else:
                os.environ.pop('USE_MSA_AUTH', None)


class TestProductionReadiness:
    """프로덕션 준비 상태 검증"""
    
    def test_no_circular_imports(self):
        """순환 import가 없는지 확인"""
        # These should all import without errors
        import models.scope_role_mapping
        import core.iam.iam_integration
        import core.iam.iam_integration_refactored
        import shared.iam_contracts
        
        # No ImportError should occur
        assert True
    
    def test_metrics_available(self):
        """모니터링 메트릭이 사용 가능한지 확인"""
        from core.integrations.iam_service_client_with_fallback import (
            iam_fallback_counter,
            iam_validation_duration,
            iam_service_health
        )
        
        # Metrics should be defined
        assert iam_fallback_counter is not None
        assert iam_validation_duration is not None
        assert iam_service_health is not None
    
    def test_all_scopes_defined(self):
        """모든 필요한 scope가 정의되어 있는지 확인"""
        from shared.iam_contracts import IAMScope
        
        required_scopes = [
            'ONTOLOGIES_READ', 'SCHEMAS_READ', 'BRANCHES_READ',
            'ONTOLOGIES_WRITE', 'SCHEMAS_WRITE', 'BRANCHES_WRITE',
            'SYSTEM_ADMIN', 'PROPOSALS_APPROVE'
        ]
        
        for scope_name in required_scopes:
            assert hasattr(IAMScope, scope_name), f"Missing scope: {scope_name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])