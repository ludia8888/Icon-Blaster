#!/usr/bin/env python
"""
Comprehensive Test Runner for TerminusDB Extension Features
Tests all 9 implemented features with detailed reporting
"""
import os
import sys
import asyncio
import subprocess
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


class TestRunner:
    """Orchestrates comprehensive testing of all features"""
    
    def __init__(self):
        self.results: Dict[str, Any] = {}
        self.start_time = datetime.now()
        self.test_groups = [
            {
                "name": "Vector Embeddings",
                "tests": ["tests/unit/test_embedding_providers.py"],
                "requires": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
            },
            {
                "name": "GraphQL Deep Linking",
                "tests": ["tests/integration/test_graph_analysis_tracing_cache.py::TestGraphAnalysisService"],
                "requires": []
            },
            {
                "name": "Redis SmartCache",
                "tests": ["tests/integration/test_graph_analysis_tracing_cache.py::TestSmartCacheIntegration"],
                "requires": ["REDIS_HOST"]
            },
            {
                "name": "Jaeger Tracing",
                "tests": ["tests/integration/test_graph_analysis_tracing_cache.py::TestJaegerIntegration"],
                "requires": ["JAEGER_AGENT_HOST"]
            },
            {
                "name": "Time Travel Queries",
                "tests": ["tests/integration/test_time_travel_queries.py"],
                "requires": []
            },
            {
                "name": "Delta Encoding",
                "tests": ["tests/integration/test_delta_encoding.py"],
                "requires": []
            },
            {
                "name": "@unfoldable Documents",
                "tests": ["tests/integration/test_unfoldable_documents.py"],
                "requires": []
            },
            {
                "name": "@metadata Frames",
                "tests": ["tests/integration/test_metadata_frames.py"],
                "requires": []
            }
        ]
    
    def check_environment(self) -> Dict[str, bool]:
        """Check if required services and environment variables are available"""
        checks = {
            "Python Version": sys.version_info >= (3, 11),
            "Redis": self._check_redis(),
            "Environment Variables": self._check_env_vars()
        }
        return checks
    
    def _check_redis(self) -> bool:
        """Check if Redis is available"""
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379)
            r.ping()
            return True
        except:
            return False
    
    def _check_env_vars(self) -> bool:
        """Check if required environment variables are set"""
        # For testing, we can use mock values
        required = ["JWT_SECRET", "TERMINUS_SERVER"]
        return all(os.getenv(var) is not None for var in required)
    
    def setup_test_environment(self):
        """Setup environment for testing"""
        # Set test environment variables
        test_env = {
            "APP_ENV": "test",
            "JWT_SECRET": "test-secret-key",
            "JWT_ISSUER": "test-issuer",
            "JWT_AUDIENCE": "test-audience",
            "TERMINUS_SERVER": "http://localhost:6363",
            "TERMINUS_DATABASE": "test_db",
            "REDIS_HOST": "localhost",
            "REDIS_PORT": "6379",
            "JAEGER_AGENT_HOST": "localhost",
            "ENABLE_TRACING": "false",  # Disable for tests
            "LOG_LEVEL": "INFO"
        }
        
        for key, value in test_env.items():
            if not os.getenv(key):
                os.environ[key] = value
    
    async def run_test_group(self, group: Dict[str, Any]) -> Dict[str, Any]:
        """Run a group of tests"""
        print(f"\n{'='*60}")
        print(f"Testing: {group['name']}")
        print(f"{'='*60}")
        
        # Check requirements
        missing_env = [env for env in group['requires'] if not os.getenv(env)]
        if missing_env:
            print(f"⚠️  Skipping - Missing environment variables: {missing_env}")
            return {
                "name": group['name'],
                "status": "skipped",
                "reason": f"Missing: {missing_env}"
            }
        
        # Run tests
        results = {
            "name": group['name'],
            "status": "passed",
            "tests": []
        }
        
        for test_path in group['tests']:
            cmd = [
                sys.executable, "-m", "pytest",
                test_path,
                "-v",
                "--tb=short",
                "--no-header"
            ]
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=Path(__file__).parent
                )
                
                test_result = {
                    "test": test_path,
                    "passed": result.returncode == 0,
                    "output": result.stdout if result.returncode == 0 else result.stderr
                }
                
                results["tests"].append(test_result)
                
                if result.returncode != 0:
                    results["status"] = "failed"
                    print(f"❌ {test_path} - FAILED")
                    if result.stderr:
                        print(f"   Error: {result.stderr[:200]}...")
                else:
                    print(f"✅ {test_path} - PASSED")
                    
            except Exception as e:
                print(f"❌ {test_path} - ERROR: {e}")
                results["status"] = "error"
                results["tests"].append({
                    "test": test_path,
                    "passed": False,
                    "error": str(e)
                })
        
        return results
    
    async def run_integration_test(self) -> Dict[str, Any]:
        """Run comprehensive integration test"""
        print(f"\n{'='*60}")
        print("Running Integration Test Scenario")
        print(f"{'='*60}")
        
        # Create integration test that uses multiple features
        integration_test = """
import asyncio
import pytest
from core.embeddings import EmbeddingService, EmbeddingProvider
from shared.cache import SmartCache
from core.time_travel import TimeTravelService
from core.documents import UnfoldableDocument, UnfoldLevel, UnfoldContext

@pytest.mark.asyncio
async def test_integrated_scenario():
    '''Test scenario using multiple features together'''
    
    # 1. Initialize services
    cache = SmartCache("test_integration", use_redis=False)
    
    # 2. Test caching with embeddings (mock)
    @cache.cached()
    async def get_embedding(text: str):
        # Mock embedding
        return [0.1] * 384
    
    # 3. Test document unfolding
    large_doc = {
        "title": "Test Document",
        "@unfoldable": {
            "data": {
                "summary": "Large dataset",
                "content": list(range(1000))
            }
        }
    }
    
    doc = UnfoldableDocument(large_doc)
    folded = doc.fold(UnfoldContext(level=UnfoldLevel.COLLAPSED))
    
    assert "@unfoldable" in folded
    assert "content" not in folded["@unfoldable"]["data"]
    assert folded["@unfoldable"]["data"]["summary"] == "Large dataset"
    
    # 4. Test delta encoding
    from core.versioning.delta_compression import EnhancedDeltaEncoder
    
    encoder = EnhancedDeltaEncoder()
    old = {"version": 1, "data": "old"}
    new = {"version": 2, "data": "new"}
    
    delta_type, encoded, size = encoder.encode_delta(old, new)
    decoded = encoder.decode_delta(old, delta_type, encoded)
    
    assert decoded == new
    
    print("✅ Integration test passed!")
    return True

if __name__ == "__main__":
    asyncio.run(test_integrated_scenario())
"""
        
        # Write and run integration test
        test_file = Path(__file__).parent / "test_integration_scenario.py"
        test_file.write_text(integration_test)
        
        try:
            cmd = [sys.executable, str(test_file)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            return {
                "name": "Integration Scenario",
                "status": "passed" if result.returncode == 0 else "failed",
                "output": result.stdout or result.stderr
            }
        finally:
            if test_file.exists():
                test_file.unlink()
    
    def generate_report(self):
        """Generate comprehensive test report"""
        total_time = (datetime.now() - self.start_time).total_seconds()
        
        print(f"\n{'='*60}")
        print("TEST REPORT SUMMARY")
        print(f"{'='*60}")
        print(f"Total Time: {total_time:.2f} seconds")
        print(f"\nEnvironment Checks:")
        
        for check, passed in self.results["environment"].items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check}")
        
        print(f"\nFeature Tests:")
        passed = 0
        failed = 0
        skipped = 0
        
        for result in self.results["features"]:
            if result["status"] == "passed":
                print(f"  ✅ {result['name']}")
                passed += 1
            elif result["status"] == "failed":
                print(f"  ❌ {result['name']}")
                failed += 1
            else:
                print(f"  ⚠️  {result['name']} - {result.get('reason', 'skipped')}")
                skipped += 1
        
        print(f"\nIntegration Test:")
        if self.results.get("integration"):
            status = "✅" if self.results["integration"]["status"] == "passed" else "❌"
            print(f"  {status} {self.results['integration']['name']}")
        
        print(f"\nSummary:")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")
        print(f"  Skipped: {skipped}")
        print(f"  Total: {passed + failed + skipped}")
        
        # Save detailed report
        report_file = Path(__file__).parent / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, "w") as f:
            f.write("DETAILED TEST REPORT\n")
            f.write("=" * 60 + "\n")
            f.write(f"Generated: {datetime.now()}\n")
            f.write(f"Total Time: {total_time:.2f} seconds\n\n")
            
            import json
            f.write(json.dumps(self.results, indent=2))
        
        print(f"\nDetailed report saved to: {report_file}")
    
    async def run(self):
        """Run all tests"""
        print("🚀 Starting Comprehensive Test Suite")
        print(f"Time: {self.start_time}")
        
        # Setup environment
        self.setup_test_environment()
        
        # Check environment
        print("\n📋 Checking Environment...")
        self.results["environment"] = self.check_environment()
        
        # Run feature tests
        print("\n🧪 Running Feature Tests...")
        self.results["features"] = []
        
        for group in self.test_groups:
            result = await self.run_test_group(group)
            self.results["features"].append(result)
        
        # Run integration test
        self.results["integration"] = await self.run_integration_test()
        
        # Generate report
        self.generate_report()
        
        # Return exit code
        failed = any(r["status"] == "failed" for r in self.results["features"])
        return 1 if failed else 0


async def main():
    """Main entry point"""
    runner = TestRunner()
    exit_code = await runner.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())