#!/usr/bin/env python3
"""
ETag and Delta Sync Demo
Shows how to use ETags for efficient caching and delta synchronization
"""
import asyncio
import httpx
import json
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8002"
BRANCH = "main"


async def demo_etag_caching():
    """Demonstrate ETag caching"""
    async with httpx.AsyncClient() as client:
        print("=== ETag Caching Demo ===\n")
        
        # First request - no ETag
        print("1. Initial request (no ETag):")
        response = await client.get(f"{BASE_URL}/api/v1/schemas/{BRANCH}/object-types")
        print(f"   Status: {response.status_code}")
        print(f"   ETag: {response.headers.get('ETag', 'None')}")
        print(f"   Cache-Control: {response.headers.get('Cache-Control', 'None')}")
        
        if response.status_code == 200:
            etag = response.headers.get('ETag')
            data = response.json()
            print(f"   Received {len(data.get('objectTypes', []))} object types")
            
            # Second request with ETag
            print("\n2. Conditional request with ETag:")
            headers = {"If-None-Match": etag} if etag else {}
            response2 = await client.get(
                f"{BASE_URL}/api/v1/schemas/{BRANCH}/object-types",
                headers=headers
            )
            print(f"   Status: {response2.status_code}")
            
            if response2.status_code == 304:
                print("   ✓ 304 Not Modified - Cache is valid!")
            else:
                print("   Cache miss - Data was updated")


async def demo_delta_sync():
    """Demonstrate delta synchronization"""
    async with httpx.AsyncClient() as client:
        print("\n\n=== Delta Sync Demo ===\n")
        
        # Get initial version
        print("1. Get initial version:")
        headers = {"X-Delta-Request": "true"}
        response = await client.get(
            f"{BASE_URL}/api/v1/versions/delta/object_types/main_object_types",
            params={"branch": BRANCH},
            headers=headers
        )
        
        if response.status_code == 200:
            delta_data = response.json()
            print(f"   Response type: {delta_data.get('response_type')}")
            print(f"   Current version: {delta_data.get('to_version', {}).get('version')}")
            print(f"   ETag: {delta_data.get('etag')}")
            
            # Simulate having an older version
            print("\n2. Request delta from older version:")
            headers = {
                "X-Delta-Request": "true",
                "X-Client-Version": "1",  # Pretend we have version 1
                "X-Include-Full": "false"
            }
            
            response2 = await client.get(
                f"{BASE_URL}/api/v1/versions/delta/object_types/main_object_types",
                params={"branch": BRANCH},
                headers=headers
            )
            
            if response2.status_code == 200:
                delta_data2 = response2.json()
                print(f"   Response type: {delta_data2.get('response_type')}")
                print(f"   Total changes: {delta_data2.get('total_changes')}")
                print(f"   Delta size: {delta_data2.get('delta_size')} bytes")
                
                if delta_data2.get('changes'):
                    for change in delta_data2['changes']:
                        print(f"   - {change.get('operation')} from v{change.get('from_version')} to v{change.get('to_version')}")


async def demo_bulk_validation():
    """Demonstrate bulk cache validation"""
    async with httpx.AsyncClient() as client:
        print("\n\n=== Bulk Cache Validation Demo ===\n")
        
        # Simulate having multiple cached resources
        cached_resources = {
            "object_type:Employee": 'W/"abc123-1"',
            "object_type:Department": 'W/"def456-2"',
            "link_type:works_in": 'W/"ghi789-1"'
        }
        
        print("1. Validating cached resources:")
        for resource, etag in cached_resources.items():
            print(f"   - {resource}: {etag}")
        
        # Validate all at once
        validation_request = {
            "resource_etags": cached_resources
        }
        
        response = await client.post(
            f"{BASE_URL}/api/v1/versions/validate-cache",
            params={"branch": BRANCH},
            json=validation_request
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n2. Validation results:")
            print(f"   Valid: {len(result.get('valid_resources', []))} resources")
            print(f"   Stale: {len(result.get('stale_resources', []))} resources")
            print(f"   Deleted: {len(result.get('deleted_resources', []))} resources")
            
            if result.get('stale_resources'):
                print("\n   Stale resources that need refresh:")
                for resource in result['stale_resources']:
                    print(f"   - {resource}")


async def demo_version_history():
    """Demonstrate version history tracking"""
    async with httpx.AsyncClient() as client:
        print("\n\n=== Version History Demo ===\n")
        
        # Get version history for a resource
        print("1. Getting version history:")
        response = await client.get(
            f"{BASE_URL}/api/v1/versions/history/object_type/Employee",
            params={"branch": BRANCH, "limit": 10}
        )
        
        if response.status_code == 200:
            history = response.json()
            print(f"   Resource: {history.get('resource_type')}/{history.get('resource_id')}")
            print(f"   Total versions: {history.get('total_versions')}")
            
            if history.get('versions'):
                print("\n   Recent versions:")
                for version in history['versions'][:5]:
                    print(f"   - v{version['version']} ({version['change_type']}) by {version['modified_by']}")
                    print(f"     {version['last_modified']} - {version.get('change_summary', 'No summary')}")


async def main():
    """Run all demos"""
    print("OMS ETag and Delta Sync Demo")
    print("============================")
    print(f"Server: {BASE_URL}")
    print(f"Branch: {BRANCH}")
    print(f"Time: {datetime.now().isoformat()}")
    
    try:
        # Check server health
        async with httpx.AsyncClient() as client:
            health = await client.get(f"{BASE_URL}/health")
            if health.status_code != 200:
                print("\n❌ Server is not responding. Please start the OMS server first.")
                return
        
        # Run demos
        await demo_etag_caching()
        await demo_delta_sync()
        await demo_bulk_validation()
        await demo_version_history()
        
        print("\n\n✅ Demo completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure the OMS server is running on port 8002")


if __name__ == "__main__":
    asyncio.run(main())