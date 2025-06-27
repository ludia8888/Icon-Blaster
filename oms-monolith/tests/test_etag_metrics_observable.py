"""
Test to verify ETag metrics are actually observable
"""
import pytest
import httpx
import asyncio
import os
import jwt as jwt_lib
from datetime import datetime, timedelta, timezone


@pytest.mark.etag
@pytest.mark.asyncio
async def test_etag_metrics_are_observable():
    """
    Verify that ETag metrics are actually exported and can be observed
    This test starts a server, makes requests, and checks the metrics endpoint
    """
    # Import here to avoid circular imports
    import sys
    sys.path.append('.')
    from test_comprehensive_real_validation import ComprehensiveRealValidator
    
    validator = ComprehensiveRealValidator()
    await validator.start_server()
    
    try:
        # Create valid JWT token
        jwt_secret = os.environ.get("JWT_SECRET", "test-secret")
        payload = {
            "user_id": "test-user-123",
            "username": "test-user",
            "email": "test@example.com",
            "roles": ["developer"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc)
        }
        token = jwt_lib.encode(payload, jwt_secret, algorithm="HS256")
        headers = {"Authorization": f"Bearer {token}"}
        
        async with httpx.AsyncClient() as client:
            # Make some requests to generate metrics
            print("\n🔍 Generating ETag metrics...")
            
            # First request - cache miss
            response1 = await client.get(
                "http://localhost:15432/api/v1/schemas/main/object-types",
                headers=headers
            )
            print(f"First request: {response1.status_code}")
            
            if response1.status_code == 200:
                etag = response1.headers.get("ETag")
                print(f"Got ETag: {etag}")
                
                # Second request with ETag - should be cache hit
                headers_with_etag = headers.copy()
                headers_with_etag["If-None-Match"] = etag
                
                response2 = await client.get(
                    "http://localhost:15432/api/v1/schemas/main/object-types",
                    headers=headers_with_etag
                )
                print(f"Second request (with ETag): {response2.status_code}")
            
            # Get metrics
            print("\n📊 Fetching metrics...")
            metrics_response = await client.get("http://localhost:15432/metrics")
            
            assert metrics_response.status_code == 200
            metrics_text = metrics_response.text
            
            print("\n📈 Metrics Output:")
            print("=" * 80)
            # Print first 1000 chars of metrics
            print(metrics_text[:1000])
            print("=" * 80)
            
            # Verify ETag metrics are present
            assert "etag_requests_total" in metrics_text
            assert "etag_cache_hits_total" in metrics_text
            assert "etag_cache_misses_total" in metrics_text
            assert "etag_validation_duration_seconds" in metrics_text
            assert "etag_generation_duration_seconds" in metrics_text
            
            # Verify analytics summary is present
            assert "ETag Analytics Summary" in metrics_text
            assert "Total Requests:" in metrics_text
            assert "Cache Hit Rate:" in metrics_text
            
            print("\n✅ ETag metrics are observable and working!")
            
    finally:
        await validator.stop_server()


if __name__ == "__main__":
    # Run directly for debugging
    asyncio.run(test_etag_metrics_are_observable())