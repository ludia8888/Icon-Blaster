#!/usr/bin/env python3
"""Quick verification of critical imports"""

def test_critical_imports():
    """Test critical import fixes"""
    print("=== Testing Critical Import Fixes ===\n")
    
    tests = [
        # External dependencies
        ("apscheduler", "apscheduler.schedulers.asyncio"),
        ("croniter", "croniter"),
        ("jsonschema", "jsonschema"),
        ("orjson", "orjson"), 
        ("minio", "minio"),
        ("pyotp", "pyotp"),
        
        # Core modules
        ("utils.retry_strategy", "utils.retry_strategy"),
        ("core.event_publisher", "core.event_publisher"),
        ("shared.cache.smart_cache", "shared.cache.smart_cache"),
        
        # GraphQL modules  
        ("api.graphql.resolvers", "api.graphql.resolvers"),
        ("api.gateway.auth", "api.gateway.auth"),
    ]
    
    passed = 0
    failed = 0
    
    for name, module_path in tests:
        try:
            __import__(module_path)
            print(f"✅ {name}: OK")
            passed += 1
        except ImportError as e:
            print(f"❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"⚠️  {name}: {type(e).__name__}: {e}")
            
    print(f"\n=== Results ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {passed}/{passed+failed} ({100*passed/(passed+failed):.1f}%)")

if __name__ == "__main__":
    test_critical_imports()