"""
Edge case tests for the real health check.
These tests verify behavior under extreme conditions.
"""

import pytest
import asyncio
import time
import os
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
import psutil

from core.health import HealthChecker, HealthStatus


class TestHealthCheckEdgeCases:
    """
    Test extreme scenarios and edge cases.
    """

    @pytest.fixture
    def health_checker(self):
        return HealthChecker()

    @pytest.fixture
    def client(self):
        from main import app
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_database_timeout_handling(self, health_checker):
        """
        Test database check with exact 5-second timeout.
        """
        print("\n=== TEST: Database Timeout Handling ===")
        
        async def slow_connect(*args, **kwargs):
            # Sleep for exactly the timeout duration
            await asyncio.sleep(5.1)
            return MagicMock()
        
        with patch('asyncpg.connect', side_effect=slow_connect):
            start = time.time()
            result = await health_checker.get_health()
            duration = time.time() - start
            
            print(f"Check duration: {duration:.2f}s")
            print(f"Database check: {result['checks']['database']}")
            
            # Should timeout at 5 seconds
            assert result['checks']['database']['status'] == False
            assert "timeout" in result['checks']['database']['message'].lower()
            assert 4.5 < duration < 6  # Some tolerance for execution
            
            print("✓ Database timeout handled correctly!")

    @pytest.mark.asyncio
    async def test_redis_connection_refused(self, health_checker):
        """
        Test Redis check when connection is actively refused.
        """
        print("\n=== TEST: Redis Connection Refused ===")
        
        # Use a port that's likely not in use
        health_checker.redis_url = "redis://localhost:9999"
        
        result = await health_checker.get_health()
        
        print(f"Redis check: {result['checks']['redis']}")
        
        assert result['checks']['redis']['status'] == False
        assert "error" in result['checks']['redis']['message'].lower()
        
        print("✓ Redis connection refused handled correctly!")

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self, health_checker):
        """
        Test multiple concurrent health checks don't interfere.
        """
        print("\n=== TEST: Concurrent Health Checks ===")
        
        # Run 10 health checks concurrently
        tasks = [health_checker.get_health() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All should complete successfully
        assert len(results) == 10
        
        # Check that all have valid structure
        for result in results:
            assert "status" in result
            assert "checks" in result
            assert len(result["checks"]) >= 5  # At least 5 check types
        
        print(f"✓ {len(results)} concurrent checks completed successfully!")

    @pytest.mark.asyncio
    async def test_malformed_database_url(self, health_checker):
        """
        Test with invalid database URL format.
        """
        print("\n=== TEST: Malformed Database URL ===")
        
        health_checker.db_url = "not-a-valid-url"
        
        result = await health_checker.get_health()
        
        print(f"Database check: {result['checks']['database']}")
        
        assert result['checks']['database']['status'] == False
        assert result['status'] == HealthStatus.UNHEALTHY.value
        
        print("✓ Malformed database URL handled correctly!")

    @pytest.mark.asyncio
    async def test_disk_check_on_nonexistent_path(self, health_checker):
        """
        Test disk check when path doesn't exist.
        """
        print("\n=== TEST: Nonexistent Path Disk Check ===")
        
        with patch('psutil.disk_usage', side_effect=Exception("Path does not exist")):
            result = await health_checker.get_health()
            
            print(f"Disk check: {result['checks']['disk_space']}")
            
            assert result['checks']['disk_space']['status'] == False
            assert "Path does not exist" in result['checks']['disk_space']['message']
            
            print("✓ Nonexistent path handled correctly!")

    @pytest.mark.asyncio
    async def test_extreme_resource_values(self, health_checker):
        """
        Test with extreme resource usage values.
        """
        print("\n=== TEST: Extreme Resource Values ===")
        
        # Test with 100% usage
        with patch('psutil.virtual_memory') as mock_memory:
            mock_memory.return_value = MagicMock(percent=100.0)
            
            with patch('psutil.cpu_percent', return_value=100.0):
                with patch('psutil.disk_usage') as mock_disk:
                    mock_disk.return_value = MagicMock(percent=100.0)
                    
                    result = await health_checker.get_health()
        
        print(f"Status: {result['status']}")
        print(f"Memory: {result['checks']['memory']}")
        print(f"CPU: {result['checks']['cpu']}")
        print(f"Disk: {result['checks']['disk_space']}")
        
        # All resource checks should fail
        assert result['checks']['memory']['status'] == False
        assert result['checks']['cpu']['status'] == False
        assert result['checks']['disk_space']['status'] == False
        
        print("✓ Extreme values handled correctly!")

    @pytest.mark.asyncio
    async def test_partial_service_failure(self, health_checker):
        """
        Test degraded state with some services up, some down.
        """
        print("\n=== TEST: Partial Service Failure ===")
        
        # Mock database to fail, but leave Redis working
        with patch('asyncpg.connect', side_effect=Exception("DB down")):
            # Assume Redis is actually running or mock it to succeed
            with patch('redis.asyncio.from_url') as mock_redis:
                mock_redis.return_value.ping = AsyncMock(return_value=True)
                mock_redis.return_value.info = AsyncMock(return_value={
                    'used_memory': 1000000,
                    'connected_clients': 5
                })
                mock_redis.return_value.close = AsyncMock()
                
                result = await health_checker.get_health()
        
        print(f"Status: {result['status']}")
        print(f"Database: {result['checks']['database']['status']}")
        print(f"Redis: {result['checks']['redis']['status']}")
        
        # Should be unhealthy because database is critical
        assert result['status'] == HealthStatus.UNHEALTHY.value
        assert result['checks']['database']['status'] == False
        assert result['checks']['redis']['status'] == True
        
        print("✓ Partial failure correctly identified as unhealthy!")

    def test_health_check_under_load(self, client):
        """
        Test health check performance under system load.
        """
        print("\n=== TEST: Health Check Under Load ===")
        
        # Create some CPU load
        def cpu_burn():
            end = time.time() + 1
            while time.time() < end:
                _ = sum(i*i for i in range(1000))
        
        # Start background load
        import threading
        threads = []
        for _ in range(4):  # 4 threads
            t = threading.Thread(target=cpu_burn)
            t.start()
            threads.append(t)
        
        # Perform health check while under load
        response = client.get("/health")
        
        # Wait for threads to complete
        for t in threads:
            t.join()
        
        print(f"Response under load: {response.status_code}")
        print(f"CPU check: {response.json()['checks'].get('cpu', {})}")
        
        # Should still respond, even if degraded
        assert response.status_code in [200, 503]
        
        print("✓ Health check responds under load!")

    @pytest.mark.asyncio
    async def test_health_history_overflow(self, health_checker):
        """
        Test that health history doesn't grow unbounded.
        """
        print("\n=== TEST: Health History Overflow ===")
        
        # Set small history size for testing
        health_checker.max_history_size = 5
        
        # Perform more checks than history size
        for i in range(10):
            await health_checker.get_health()
        
        # History should be capped
        assert len(health_checker.check_history) == 5
        
        trends = await health_checker.get_health_trends()
        assert trends["total_checks"] == 5
        
        print("✓ Health history correctly capped at max size!")

    def test_all_health_endpoints_exist(self, client):
        """
        Verify all health endpoints are properly registered.
        """
        print("\n=== TEST: All Health Endpoints ===")
        
        endpoints = [
            ("/health", [200, 503]),
            ("/health/live", [200]),
            ("/health/ready", [200, 503]),
            ("/health/detailed", [401]),  # Requires auth
        ]
        
        for endpoint, valid_codes in endpoints:
            response = client.get(endpoint)
            assert response.status_code in valid_codes, \
                f"{endpoint} returned {response.status_code}, expected one of {valid_codes}"
            print(f"✓ {endpoint} -> {response.status_code}")
        
        print("✓ All health endpoints accessible!")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, '/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith')
    
    tester = TestHealthCheckEdgeCases()
    health_checker = HealthChecker()
    
    print("=" * 80)
    print("HEALTH CHECK EDGE CASES VALIDATION")
    print("=" * 80)
    
    # Run async tests
    async def run_async_tests():
        await tester.test_database_timeout_handling(health_checker)
        await tester.test_redis_connection_refused(health_checker)
        await tester.test_concurrent_health_checks(health_checker)
        await tester.test_malformed_database_url(health_checker)
        await tester.test_disk_check_on_nonexistent_path(health_checker)
        await tester.test_extreme_resource_values(health_checker)
        await tester.test_partial_service_failure(health_checker)
        await tester.test_health_history_overflow(health_checker)
    
    asyncio.run(run_async_tests())
    
    print("\n" + "=" * 80)
    print("EDGE CASES VALIDATION COMPLETE!")
    print("=" * 80)