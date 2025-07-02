"""
Integration tests for mTLS and fallback mechanisms
Tests complex scenarios including certificate validation, fallback chains, and error recovery
"""
import asyncio
import ssl
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from freezegun import freeze_time

from core.integrations.iam_service_client_with_fallback import (
    IAMServiceClientWithFallback,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from database.clients.terminus_db import TerminusDBClient
from shared.iam_contracts import TokenValidationResponse, UserInfoResponse


class TestMTLSIntegration:
    """Test mTLS functionality across different clients"""

    @pytest.mark.asyncio
    async def test_terminus_db_mtls_handshake(self):
        """Test TerminusDB client mTLS handshake and fallback"""
        with patch.dict('os.environ', {
            'TERMINUSDB_USE_MTLS': 'true',
            'TERMINUSDB_CERT_PATH': '/mock/cert.pem',
            'TERMINUSDB_KEY_PATH': '/mock/key.pem',
            'TERMINUSDB_CA_PATH': '/mock/ca.pem',
        }):
            client = TerminusDBClient(
                endpoint="https://secure-terminus.example.com:6363",
                use_connection_pool=True
            )

            # Mock SSL context creation
            with patch('ssl.create_default_context') as mock_ssl_context:
                mock_context = Mock()
                mock_ssl_context.return_value = mock_context

                # Mock successful mTLS initialization
                with patch('database.clients.unified_http_client.create_terminus_client') as mock_create:
                    mock_http_client = AsyncMock()
                    mock_http_client.get.return_value = Mock(status_code=200)
                    mock_create.return_value = mock_http_client

                    await client._initialize_client()

                    # Verify mTLS was configured
                    mock_create.assert_called_once()
                    call_args = mock_create.call_args[1]
                    assert call_args['enable_mtls'] is True
                    assert call_args['ssl_context'] == mock_context
                    assert call_args['enable_mtls_fallback'] is True

            await client.close()

    @pytest.mark.asyncio
    async def test_mtls_certificate_rotation(self):
        """Test handling of certificate rotation and renewal"""
        client = TerminusDBClient(
            endpoint="https://secure-terminus.example.com:6363",
            use_mtls=True
        )

        # Simulate certificate expiry and renewal
        with patch('database.clients.unified_http_client.create_terminus_client') as mock_create:
            mock_http_client = AsyncMock()
            
            # First call fails due to expired cert
            mock_http_client.get.side_effect = [
                ssl.SSLError("certificate verify failed: certificate has expired"),
                Mock(status_code=200, json=lambda: {"status": "renewed"})
            ]
            
            mock_create.return_value = mock_http_client

            await client._initialize_client()
            
            # Should handle cert renewal gracefully
            result = await client.ping()
            assert result is True

        await client.close()

    @pytest.mark.asyncio
    async def test_mtls_fallback_chain(self):
        """Test complete mTLS fallback chain"""
        scenarios = [
            # Scenario 1: mTLS fails, falls back to TLS
            {
                'mtls_error': ssl.SSLError("peer did not return a certificate"),
                'tls_response': Mock(status_code=200),
                'expected_mtls': False
            },
            # Scenario 2: mTLS succeeds
            {
                'mtls_error': None,
                'tls_response': None,
                'expected_mtls': True
            },
            # Scenario 3: Both fail
            {
                'mtls_error': ssl.SSLError("handshake failure"),
                'tls_response': Exception("Connection refused"),
                'expected_mtls': False
            }
        ]

        for scenario in scenarios:
            client = TerminusDBClient(use_mtls=True)
            
            with patch('database.clients.unified_http_client.create_terminus_client') as mock_create:
                mock_http_client = AsyncMock()
                
                if scenario['mtls_error']:
                    if scenario['tls_response']:
                        mock_http_client.get.side_effect = [
                            scenario['mtls_error'],
                            scenario['tls_response']
                        ]
                    else:
                        mock_http_client.get.side_effect = scenario['mtls_error']
                else:
                    mock_http_client.get.return_value = Mock(status_code=200)
                
                mock_create.return_value = mock_http_client
                
                try:
                    await client._initialize_client()
                    if isinstance(scenario.get('tls_response'), Exception):
                        pytest.fail("Expected exception not raised")
                except Exception as e:
                    if not isinstance(scenario.get('tls_response'), Exception):
                        pytest.fail(f"Unexpected exception: {e}")

            await client.close()


class TestIAMServiceFallback:
    """Test IAM service fallback mechanisms"""

    @pytest.fixture
    async def iam_client(self):
        """Create IAM client with fallback"""
        with patch.dict('os.environ', {
            'JWT_SECRET': 'test-secret-key-for-testing-only-32chars',
            'IAM_SERVICE_URL': 'https://iam.example.com',
            'IAM_TIMEOUT': '2',
            'IAM_MAX_RETRIES': '1',
        }):
            client = IAMServiceClientWithFallback()
            yield client
            await client.close()

    @pytest.mark.asyncio
    async def test_circuit_breaker_with_health_check(self, iam_client):
        """Test circuit breaker with health check before reset"""
        # Simulate failures to open circuit
        with patch.object(iam_client._client, 'post') as mock_post:
            mock_post.side_effect = ServiceTimeoutError("Timeout")
            
            # Make enough requests to open circuit
            for _ in range(5):
                response = await iam_client.validate_token("fake-token")
                assert not response.valid

        # Circuit should be open
        assert iam_client._circuit_open is True

        # Fast forward time to reset period
        with freeze_time(datetime.now() + timedelta(seconds=61)):
            # Mock health check
            with patch.object(iam_client._client, 'get') as mock_get:
                # Health check fails
                mock_get.side_effect = Exception("Still down")
                
                # Token validation should use fallback
                response = await iam_client.validate_token("fake-token")
                
                # Should have attempted health check
                mock_get.assert_called_with("/health")
                
                # Circuit should remain open
                assert iam_client._circuit_open is True

    @pytest.mark.asyncio
    async def test_fallback_validation_with_jwks(self, iam_client):
        """Test local JWT validation with JWKS fallback"""
        # Create a valid JWT token
        import jwt
        
        payload = {
            'sub': 'user123',
            'preferred_username': 'testuser',
            'email': 'test@example.com',
            'scope': 'read write',
            'roles': ['user', 'admin'],
            'tenant_id': 'tenant123',
            'exp': int((datetime.now() + timedelta(hours=1)).timestamp()),
            'iss': 'iam.company',
            'aud': 'oms',
        }
        
        token = jwt.encode(
            payload,
            'test-secret-key-for-testing-only-32chars',
            algorithm='HS256'
        )

        # Simulate service unavailable - fallback to local
        with patch.object(iam_client._client, 'post') as mock_post:
            mock_post.side_effect = ServiceUnavailableError("Service down")
            
            response = await iam_client.validate_token(token)
            
            assert response.valid
            assert response.user_id == 'user123'
            assert response.username == 'testuser'
            assert 'read' in response.scopes
            assert 'admin' in response.roles
            assert response.metadata.get('validation_method') == 'local_fallback'

    @pytest.mark.asyncio
    async def test_get_user_info_error_handling(self, iam_client):
        """Test comprehensive error handling for get_user_info"""
        test_cases = [
            # Case 1: User not found (404)
            {
                'response': Mock(status_code=404),
                'expected_result': None,
                'expected_error': None
            },
            # Case 2: Service timeout
            {
                'response': ServiceTimeoutError("Timeout"),
                'expected_result': None,
                'expected_error': ServiceTimeoutError
            },
            # Case 3: Service unavailable
            {
                'response': ServiceUnavailableError("Down"),
                'expected_result': None,
                'expected_error': ServiceUnavailableError
            },
            # Case 4: Success
            {
                'response': Mock(
                    status_code=200,
                    json=lambda: {
                        'user_id': 'user123',
                        'username': 'testuser',
                        'email': 'test@example.com'
                    }
                ),
                'expected_result': UserInfoResponse(
                    user_id='user123',
                    username='testuser',
                    email='test@example.com'
                ),
                'expected_error': None
            }
        ]

        for case in test_cases:
            with patch.object(iam_client._client, 'post') as mock_post:
                if isinstance(case['response'], Exception):
                    mock_post.side_effect = case['response']
                else:
                    mock_post.return_value = case['response']

                if case['expected_error']:
                    with pytest.raises(case['expected_error']):
                        await iam_client.get_user_info('user123')
                else:
                    result = await iam_client.get_user_info('user123')
                    if case['expected_result'] is None:
                        assert result is None
                    else:
                        assert result.user_id == case['expected_result'].user_id

    @pytest.mark.asyncio
    async def test_concurrent_fallback_requests(self, iam_client):
        """Test handling of concurrent requests during fallback"""
        # Simulate service down
        with patch.object(iam_client._client, 'post') as mock_post:
            mock_post.side_effect = ServiceUnavailableError("Service down")
            
            # Create multiple valid tokens
            tokens = []
            for i in range(5):
                payload = {
                    'sub': f'user{i}',
                    'exp': int((datetime.now() + timedelta(hours=1)).timestamp()),
                    'iss': 'iam.company',
                    'aud': 'oms',
                }
                token = jwt.encode(
                    payload,
                    'test-secret-key-for-testing-only-32chars',
                    algorithm='HS256'
                )
                tokens.append(token)
            
            # Validate all tokens concurrently
            tasks = [iam_client.validate_token(token) for token in tokens]
            responses = await asyncio.gather(*tasks)
            
            # All should be valid via fallback
            assert all(r.valid for r in responses)
            assert all(r.metadata.get('validation_method') == 'local_fallback' for r in responses)
            
            # Verify unique user IDs
            user_ids = [r.user_id for r in responses]
            assert len(set(user_ids)) == 5


class TestBackupServiceIntegration:
    """Test backup service with streaming and large file support"""

    @pytest.mark.asyncio
    async def test_large_file_streaming(self):
        """Test streaming of large backup files"""
        from core.backup.production_backup import ProductionBackupOrchestrator
        
        orchestrator = ProductionBackupOrchestrator()
        
        # Mock large file streaming
        with patch('database.clients.unified_http_client.create_streaming_client') as mock_create:
            mock_client = AsyncMock()
            
            # Simulate streaming response
            async def mock_stream(*args, **kwargs):
                mock_response = Mock()
                mock_response.status_code = 200
                
                async def iter_chunks():
                    # Simulate 500MB file in 10MB chunks
                    for i in range(50):
                        yield b'x' * (10 * 1024 * 1024)  # 10MB chunk
                
                mock_response.aiter_bytes = iter_chunks
                return mock_response
            
            mock_client.stream = mock_stream
            mock_create.return_value = mock_client
            
            # Mock other dependencies
            with patch('redis.asyncio.from_url') as mock_redis, \
                 patch('minio.Minio') as mock_minio:
                
                mock_redis.return_value = AsyncMock()
                mock_minio.return_value = Mock()
                mock_minio.return_value.bucket_exists.return_value = True
                
                await orchestrator.initialize()
                
                # Verify streaming client created with correct params
                mock_create.assert_called_once()
                call_args = mock_create.call_args[1]
                assert call_args['timeout'] == 300.0
                assert call_args['stream_support'] is True
                assert call_args['enable_large_file_streaming'] is True

            await orchestrator.close()

    @pytest.mark.asyncio
    async def test_backup_retry_with_metrics(self):
        """Test backup retry logic with metric collection"""
        from core.backup.production_backup import ProductionBackupOrchestrator
        
        orchestrator = ProductionBackupOrchestrator()
        
        with patch('database.clients.unified_http_client.create_streaming_client') as mock_create:
            mock_client = AsyncMock()
            
            # Simulate retry scenario
            mock_client.get.side_effect = [
                Exception("Network error"),
                Exception("Network error"),
                Mock(status_code=200, json=lambda: {"databases": ["db1", "db2"]})
            ]
            
            mock_create.return_value = mock_client
            
            # Mock dependencies
            with patch('redis.asyncio.from_url') as mock_redis, \
                 patch('minio.Minio') as mock_minio:
                
                mock_redis.return_value = AsyncMock()
                mock_minio.return_value = Mock()
                mock_minio.return_value.bucket_exists.return_value = True
                
                await orchestrator.initialize()
                
                # Should succeed after retries
                databases = await orchestrator._get_databases(mock_client)
                assert databases == {"databases": ["db1", "db2"]}

            await orchestrator.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])