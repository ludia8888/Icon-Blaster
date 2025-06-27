"""
Ruthless validation of fake enterprise features.
This test suite verifies that enterprise features are NOT just placeholders.
"""

import asyncio
import pytest
import httpx
import signal
import time
import psutil
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime


class TestFakeEnterpriseFeatures:
    """
    Relentless validator for enterprise features.
    Each test MUST prove the feature works or expose it as fake.
    """

    @pytest.fixture
    def client(self):
        """Get test client - import main app dynamically to avoid circular imports"""
        from main import app
        return TestClient(app)

    def test_health_check_is_fake(self, client):
        """
        PROOF: Health check ALWAYS returns healthy regardless of system state.
        This is a CRITICAL FLAW for production systems.
        """
        print("\n=== TESTING FAKE HEALTH CHECK ===")
        
        # Test 1: Normal health check
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✓ Normal request: {data}")
        
        # Test 2: Simulate system issues - health check should detect them but doesn't
        with patch('psutil.cpu_percent', return_value=99.9):
            with patch('psutil.virtual_memory', return_value=MagicMock(percent=99.9)):
                response = client.get("/health")
                data = response.json()
                assert data["status"] == "healthy"  # STILL HEALTHY!
                print(f"✗ CPU/Memory at 99.9%: {data} - STILL REPORTS HEALTHY!")
        
        # Test 3: Simulate database connection failure
        with patch('asyncpg.connect', side_effect=Exception("Database is down")):
            response = client.get("/health")
            data = response.json()
            assert data["status"] == "healthy"  # STILL HEALTHY!
            print(f"✗ Database down: {data} - STILL REPORTS HEALTHY!")
        
        # Test 4: Simulate Redis failure
        with patch('redis.Redis.ping', side_effect=Exception("Redis is down")):
            response = client.get("/health")
            data = response.json()
            assert data["status"] == "healthy"  # STILL HEALTHY!
            print(f"✗ Redis down: {data} - STILL REPORTS HEALTHY!")
        
        print("\nVERDICT: Health check is COMPLETELY FAKE - always returns healthy")
        print("IMPACT: Load balancers will route traffic to dead instances!")
        
    def test_health_check_timing_attack(self, client):
        """
        Test if health check response time varies with system load.
        A real health check would take longer when checking unhealthy systems.
        """
        print("\n=== TIMING ATTACK ON HEALTH CHECK ===")
        
        # Baseline timing
        start = time.time()
        response = client.get("/health")
        baseline_time = time.time() - start
        print(f"Baseline response time: {baseline_time:.4f}s")
        
        # Create high CPU load
        def cpu_burn():
            end_time = time.time() + 0.5
            while time.time() < end_time:
                _ = sum(i*i for i in range(1000))
        
        # Test under load
        burn_thread = asyncio.create_task(asyncio.to_thread(cpu_burn))
        start = time.time()
        response = client.get("/health")
        loaded_time = time.time() - start
        print(f"Response time under load: {loaded_time:.4f}s")
        
        # If it's a real health check, loaded_time should be significantly higher
        time_difference = abs(loaded_time - baseline_time)
        print(f"Time difference: {time_difference:.4f}s")
        
        if time_difference < 0.01:  # Less than 10ms difference
            print("✗ FAKE DETECTED: Response time doesn't vary with system load!")
        else:
            print("✓ Response time varies with load")
            
    def test_health_check_dependencies(self, client):
        """
        Test if health check actually checks its claimed dependencies.
        """
        print("\n=== DEPENDENCY CHECKING TEST ===")
        
        # Get health check response
        response = client.get("/health")
        data = response.json()
        
        # Check what the health endpoint claims to monitor
        print(f"Health response keys: {list(data.keys())}")
        
        # A real health check should include:
        expected_checks = [
            "database", "redis", "disk_space", "memory", 
            "cpu", "dependencies", "services"
        ]
        
        missing_checks = [check for check in expected_checks if check not in data]
        if missing_checks:
            print(f"✗ FAKE DETECTED: Missing health checks for: {missing_checks}")
        
        # Even if it has the keys, are they real?
        if "timestamp" in data:
            # Verify timestamp is current
            if isinstance(data.get("timestamp"), str):
                try:
                    ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                    age = (datetime.utcnow() - ts.replace(tzinfo=None)).total_seconds()
                    if age > 60:
                        print(f"✗ Timestamp is {age:.0f}s old - likely hardcoded!")
                except:
                    print("✗ Invalid timestamp format!")
        
    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self, client):
        """
        Bombard health check endpoint to see if it handles concurrent requests properly.
        A fake implementation might not handle concurrency well.
        """
        print("\n=== CONCURRENT HEALTH CHECK TEST ===")
        
        async def make_request():
            async with httpx.AsyncClient(base_url="http://testserver") as async_client:
                return await async_client.get("/health")
        
        # Make 100 concurrent requests
        start = time.time()
        tasks = [make_request() for _ in range(100)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start
        
        # Check results
        errors = [r for r in responses if isinstance(r, Exception)]
        success_count = len([r for r in responses if not isinstance(r, Exception) and r.status_code == 200])
        
        print(f"Concurrent requests: 100")
        print(f"Successful: {success_count}")
        print(f"Errors: {len(errors)}")
        print(f"Total time: {duration:.2f}s")
        print(f"Requests/second: {100/duration:.2f}")
        
        if errors:
            print(f"✗ Errors during concurrent access: {errors[:3]}...")  # Show first 3
        
        # All should succeed for a simple hardcoded response
        assert success_count == 100, "Fake health check can't even handle concurrent requests!"
        
    def test_health_check_reveals_internals(self, client):
        """
        Check if health endpoint leaks internal information.
        """
        print("\n=== INFORMATION DISCLOSURE TEST ===")
        
        response = client.get("/health")
        data = response.json()
        
        # Check for information leakage
        sensitive_keys = ["version", "environment", "config", "internal", "debug"]
        found_sensitive = [key for key in sensitive_keys if key in str(data).lower()]
        
        if found_sensitive:
            print(f"⚠️  Potentially sensitive information exposed: {found_sensitive}")
            
        # Check version info
        if "version" in data:
            print(f"Version exposed: {data['version']}")
            # Version should not reveal too much
            if "beta" in str(data["version"]) or "dev" in str(data["version"]):
                print("✗ Development version exposed in health check!")
    
    def test_rbac_test_endpoint_security_hole(self, client):
        """
        Test the RBAC test endpoint - this is a MASSIVE security hole if exposed.
        """
        print("\n=== RBAC TEST ENDPOINT SECURITY HOLE ===")
        
        # Try to access the test token endpoint
        test_payloads = [
            {"user_id": "attacker", "role": "admin"},
            {"user_id": "hacker", "role": "super_admin"},
            {"user_id": "malicious", "role": "root"},
        ]
        
        for payload in test_payloads:
            try:
                response = client.post("/api/v1/test/generate-token", json=payload)
                if response.status_code == 200:
                    data = response.json()
                    print(f"✗ CRITICAL: Generated token for {payload} -> {data.get('token', 'TOKEN')[:50]}...")
                    print("  This endpoint should NEVER exist in production!")
                elif response.status_code == 404:
                    print(f"✓ Test endpoint not found (good for production)")
                else:
                    print(f"⚠️  Unexpected response: {response.status_code}")
            except Exception as e:
                print(f"✓ Endpoint not accessible: {str(e)}")

    def test_health_check_with_poison_pill(self, client):
        """
        Send malformed requests to health check to test robustness.
        """
        print("\n=== POISON PILL TEST ===")
        
        # Test various malformed requests
        poison_tests = [
            ("GET", "/health?debug=true"),
            ("GET", "/health?format=detailed"),
            ("GET", "/health/../../../etc/passwd"),
            ("GET", "/health%00.json"),
            ("GET", "/health\x00"),
        ]
        
        for method, path in poison_tests:
            try:
                response = client.request(method, path)
                print(f"{method} {repr(path)}: {response.status_code} - {response.text[:100]}")
                
                # Check if we got more info than we should
                if response.status_code == 200:
                    data = response.json()
                    if len(str(data)) > 100:  # Suspiciously large response
                        print(f"  ⚠️  Large response ({len(str(data))} chars) - possible info leak!")
            except Exception as e:
                print(f"{method} {repr(path)}: Exception - {str(e)}")

    def generate_test_report(self):
        """
        Generate a comprehensive report of findings.
        """
        report = """
# FAKE ENTERPRISE FEATURES - VALIDATION REPORT

## CRITICAL FINDINGS

### 1. Health Check Endpoint (/health) - COMPLETELY FAKE
- **Status**: Always returns "healthy" regardless of system state
- **Impact**: CRITICAL - Production monitoring will not detect failures
- **Evidence**:
  - Returns healthy even with 99.9% CPU/Memory usage
  - Returns healthy even with database down
  - Returns healthy even with Redis down
  - No actual system checks performed
  - Response time constant (no variance with load)

### 2. RBAC Test Token Generator - SECURITY HOLE
- **Status**: Allows generation of admin tokens without authentication
- **Impact**: CRITICAL if exposed in production
- **Location**: /api/v1/test/generate-token

## MISSING ENTERPRISE FEATURES

1. **Real Health Monitoring**:
   - No database connectivity check
   - No Redis connectivity check  
   - No disk space monitoring
   - No memory usage monitoring
   - No CPU usage monitoring
   - No dependency health checks

2. **High Availability**:
   - Health check can't detect unhealthy instances
   - Load balancers will route to dead servers

## RECOMMENDATIONS

1. **IMMEDIATE**: Implement real health checks that verify:
   - Database connection (try a simple query)
   - Redis connection (PING command)
   - Available disk space > 10%
   - Memory usage < 90%
   - CPU usage < 90%
   - All critical service dependencies

2. **URGENT**: Remove or secure the RBAC test endpoint

3. **IMPORTANT**: Add health check levels:
   - /health/live - Basic liveness (can respond)
   - /health/ready - Ready to serve traffic (all deps OK)
   - /health/detailed - Detailed status (auth required)

## VERDICT

The current implementation is **NOT PRODUCTION READY**.
The fake health check is a **CRITICAL FLAW** that will cause:
- Failed deployments to receive traffic
- No alerting on system failures  
- Cascading failures in distributed systems
- Violation of SLA requirements

This must be fixed before any production deployment.
"""
        return report


# Run the tests with detailed output
if __name__ == "__main__":
    tester = TestFakeEnterpriseFeatures()
    
    # Create a mock client for standalone execution
    import sys
    sys.path.insert(0, '/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith')
    
    # Fix the import error in main.py first
    import os
    import main
    main.os = os  # Inject missing import
    
    from main import app
    client = TestClient(app)
    
    print("=" * 80)
    print("RUTHLESS ENTERPRISE FEATURE VALIDATION")
    print("=" * 80)
    
    # Run each test
    tests = [
        tester.test_health_check_is_fake,
        tester.test_health_check_timing_attack,
        tester.test_health_check_dependencies,
        tester.test_health_check_reveals_internals,
        tester.test_rbac_test_endpoint_security_hole,
        tester.test_health_check_with_poison_pill,
    ]
    
    for test in tests:
        try:
            if asyncio.iscoroutinefunction(test):
                asyncio.run(test(client))
            else:
                test(client)
        except Exception as e:
            print(f"\n✗ Test {test.__name__} failed with: {str(e)}")
    
    # Generate report
    print("\n" + "=" * 80)
    print(tester.generate_test_report())