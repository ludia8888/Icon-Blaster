#!/usr/bin/env python3
"""
Comprehensive Test Runner for OMS

Runs all test suites across all phases to ensure complete functionality.
"""

import asyncio
import sys
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from common_logging.setup import get_logger

logger = get_logger(__name__)


class TestRunner:
    """Comprehensive test runner for all OMS phases"""
    
    def __init__(self):
        self.results = {}
        self.start_time = None
        self.test_suites = [
            # Phase 1: Semantic Types
            ("Phase 1 - Semantic Types", [
                "tests/test_semantic_types.py",
                "tests/integration/test_semantic_type_validation.py"
            ]),
            
            # Phase 2: Struct Types
            ("Phase 2 - Struct Types", [
                "tests/test_struct_types.py",
                "tests/integration/test_struct_type_validation.py"
            ]),
            
            # Phase 3: Link Meta Extensions
            ("Phase 3 - Link Meta Extensions", [
                "tests/test_graph_metadata.py",
                "tests/integration/test_link_meta_extensions.py"
            ]),
            
            # Phase 4: Propagation Rules
            ("Phase 4 - Propagation Rules", [
                "tests/test_propagation_rules.py",
                "tests/integration/test_permission_inheritance.py"
            ]),
            
            # Phase 5: API Schema Generation
            ("Phase 5 - API Schema Generation", [
                "tests/test_schema_generator.py",
                "tests/test_schema_generator_extended.py",
                "tests/integration/test_link_reverse_references.py",
                "tests/test_schema_generation_api.py"
            ]),
            
            # Phase 6: Performance & Merge Testing
            ("Phase 6 - Performance & Merge", [
                "tests/integration/test_merge_conflict_automation.py",
                "tests/performance/test_dag_merge_performance.py"
            ])
        ]
    
    async def run_all_tests(self) -> bool:
        """Run all test suites and return success status"""
        self.start_time = datetime.now()
        logger.info("=" * 80)
        logger.info("OMS Comprehensive Test Suite")
        logger.info("=" * 80)
        logger.info(f"Starting at: {self.start_time}")
        logger.info("")
        
        all_passed = True
        
        for phase_name, test_files in self.test_suites:
            phase_passed = await self.run_phase_tests(phase_name, test_files)
            all_passed = all_passed and phase_passed
        
        # Run integration tests
        integration_passed = await self.run_integration_tests()
        all_passed = all_passed and integration_passed
        
        # Print summary
        self.print_summary()
        
        return all_passed
    
    async def run_phase_tests(self, phase_name: str, test_files: List[str]) -> bool:
        """Run tests for a specific phase"""
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Running {phase_name}")
        logger.info(f"{'=' * 60}")
        
        phase_results = []
        phase_passed = True
        
        for test_file in test_files:
            if not os.path.exists(test_file):
                logger.warning(f"Test file not found: {test_file}")
                continue
            
            result = await self.run_test_file(test_file)
            phase_results.append((test_file, result))
            phase_passed = phase_passed and result["passed"]
        
        self.results[phase_name] = {
            "passed": phase_passed,
            "tests": phase_results,
            "duration": sum(r[1]["duration"] for r in phase_results)
        }
        
        return phase_passed
    
    async def run_test_file(self, test_file: str) -> Dict:
        """Run a single test file"""
        logger.info(f"\nRunning: {test_file}")
        start = time.time()
        
        try:
            # Run pytest
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                cwd=project_root
            )
            
            duration = time.time() - start
            passed = result.returncode == 0
            
            if passed:
                logger.info(f"✅ PASSED ({duration:.2f}s)")
            else:
                logger.error(f"❌ FAILED ({duration:.2f}s)")
                if result.stdout:
                    logger.error(f"Output: {result.stdout[-500:]}")  # Last 500 chars
                if result.stderr:
                    logger.error(f"Error: {result.stderr[-500:]}")
            
            return {
                "passed": passed,
                "duration": duration,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
            
        except Exception as e:
            logger.error(f"Exception running test: {e}")
            return {
                "passed": False,
                "duration": time.time() - start,
                "error": str(e)
            }
    
    async def run_integration_tests(self) -> bool:
        """Run cross-phase integration tests"""
        logger.info(f"\n{'=' * 60}")
        logger.info("Running Integration Tests")
        logger.info(f"{'=' * 60}")
        
        # Test complete workflow
        integration_tests = [
            self.test_complete_schema_workflow(),
            self.test_merge_with_schema_changes(),
            self.test_performance_requirements()
        ]
        
        results = await asyncio.gather(*integration_tests)
        return all(results)
    
    async def test_complete_schema_workflow(self) -> bool:
        """Test complete workflow from schema definition to API generation"""
        logger.info("\nTesting complete schema workflow...")
        
        try:
            # Import necessary modules
            from models.semantic_types import semantic_type_registry
            from models.struct_types import struct_type_registry
            from core.api.schema_generator import graphql_generator, openapi_generator
            from models.domain import ObjectType, Property, LinkType, Cardinality
            
            # Create test schema
            user_type = ObjectType(
                id="TestUser",
                name="TestUser",
                display_name="Test User",
                properties=[
                    Property(
                        id="user_email",
                        object_type_id="TestUser",
                        name="email",
                        display_name="Email",
                        data_type_id="string",
                        semantic_type_id="email",
                        is_required=True
                    )
                ]
            )
            
            # Generate schemas
            graphql_schema = graphql_generator.generate_object_type_schema(user_type, [])
            openapi_schema = openapi_generator.generate_object_schema(user_type, [])
            
            # Verify generation
            assert "type TestUser" in graphql_schema
            assert openapi_schema["properties"]["email"]
            
            logger.info("✅ Complete workflow test passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Workflow test failed: {e}")
            return False
    
    async def test_merge_with_schema_changes(self) -> bool:
        """Test merge operations with schema modifications"""
        logger.info("\nTesting merge with schema changes...")
        
        try:
            from core.versioning.merge_engine import merge_engine
            
            # Create test branches
            base_branch = {
                "branch_id": "main",
                "commit_id": "base_001",
                "objects": [{"id": "User", "properties": ["id", "name"]}]
            }
            
            feature_branch = {
                "branch_id": "feature",
                "commit_id": "feat_001",
                "parent": "base_001",
                "objects": [{"id": "User", "properties": ["id", "name", "email"]}]
            }
            
            # Test merge
            result = await merge_engine.merge_branches(
                source_branch=feature_branch,
                target_branch=base_branch,
                auto_resolve=True
            )
            
            assert result.status in ["success", "dry_run_success"]
            logger.info("✅ Merge test passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Merge test failed: {e}")
            return False
    
    async def test_performance_requirements(self) -> bool:
        """Verify performance requirements are met"""
        logger.info("\nVerifying performance requirements...")
        
        try:
            # Check if performance metrics meet requirements
            merge_times = []
            
            # Simulate some quick merges
            from core.versioning.merge_engine import merge_engine
            
            for i in range(10):
                start = time.time()
                result = await merge_engine.analyze_conflicts(
                    {"branch_id": f"test_{i}", "objects": []},
                    {"branch_id": "main", "objects": []}
                )
                duration = (time.time() - start) * 1000
                merge_times.append(duration)
            
            avg_time = sum(merge_times) / len(merge_times)
            assert avg_time < 200  # Should be well under 200ms
            
            logger.info(f"✅ Performance test passed (avg: {avg_time:.2f}ms)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Performance test failed: {e}")
            return False
    
    def print_summary(self):
        """Print test summary"""
        total_duration = (datetime.now() - self.start_time).total_seconds()
        
        logger.info(f"\n{'=' * 80}")
        logger.info("TEST SUMMARY")
        logger.info(f"{'=' * 80}")
        
        total_tests = 0
        passed_tests = 0
        
        for phase_name, results in self.results.items():
            phase_status = "✅ PASSED" if results["passed"] else "❌ FAILED"
            logger.info(f"\n{phase_name}: {phase_status}")
            
            for test_file, test_result in results["tests"]:
                test_status = "✅" if test_result["passed"] else "❌"
                logger.info(f"  {test_status} {os.path.basename(test_file)} ({test_result['duration']:.2f}s)")
                total_tests += 1
                if test_result["passed"]:
                    passed_tests += 1
        
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Total Duration: {total_duration:.2f}s")
        logger.info(f"Tests Run: {total_tests}")
        logger.info(f"Tests Passed: {passed_tests}")
        logger.info(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")
        
        if passed_tests == total_tests:
            logger.info("\n🎉 ALL TESTS PASSED! 🎉")
        else:
            logger.error(f"\n⚠️  {total_tests - passed_tests} tests failed")


async def main():
    """Main entry point"""
    runner = TestRunner()
    success = await runner.run_all_tests()
    
    if success:
        logger.info("\n✅ OMS Test Suite: ALL TESTS PASSED")
        logger.info("\nNext Steps:")
        logger.info("1. Deploy to staging environment")
        logger.info("2. Run production load tests")
        logger.info("3. Enable monitoring and alerting")
        logger.info("4. Begin incremental rollout")
        return 0
    else:
        logger.error("\n❌ OMS Test Suite: SOME TESTS FAILED")
        logger.error("Please fix failing tests before proceeding")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))