"""
Test to validate that the merge engine fix properly detects conflicts
"""

import asyncio
import sys
import pytest
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.versioning.merge_engine_fix import fixed_merge_engine
from utils.logger import get_logger

logger = get_logger(__name__)


@pytest.mark.asyncio
async def test_conflict_detection():
    """Test that conflicts are properly detected"""
    logger.info("=" * 80)
    logger.info("Testing Fixed Merge Engine Conflict Detection")
    logger.info("=" * 80)
    
    # Base schema
    base_branch = {
        "branch_id": "main",
        "commit_id": "base_commit",
        "schema": {
            "Customer": {
                "properties": {
                    "id": {"type": "string", "required": True},
                    "email": {"type": "string", "required": True},
                    "name": {"type": "string", "required": True}
                }
            }
        }
    }
    
    # Developer A's changes
    dev_a_branch = {
        "branch_id": "feature_a",
        "commit_id": "dev_a_commit",
        "parent": "base_commit",
        "schema": {
            "Customer": {
                "properties": {
                    "id": {"type": "string", "required": True},
                    "email": {"type": "string", "required": True, "unique": True},  # Added unique
                    "name": {"type": "string", "required": True},
                    "phone": {"type": "string", "required": False}  # Added phone
                }
            }
        }
    }
    
    # Developer B's conflicting changes
    dev_b_branch = {
        "branch_id": "feature_b",
        "commit_id": "dev_b_commit",
        "parent": "base_commit",
        "schema": {
            "Customer": {
                "properties": {
                    "id": {"type": "string", "required": True},
                    "email": {"type": "string", "required": False},  # Made optional (CONFLICT!)
                    "name": {"type": "text", "required": True},  # Changed type (CONFLICT!)
                    "address": {"type": "string", "required": True}  # Added address
                }
            }
        }
    }
    
    logger.info("\n1. Testing merge of dev_a into main (should succeed)")
    result_a = await fixed_merge_engine.merge_branches(
        source_branch=dev_a_branch,
        target_branch=base_branch,
        base_branch=base_branch,
        auto_resolve=True
    )
    
    logger.info(f"   Status: {result_a.status}")
    logger.info(f"   Conflicts: {len(result_a.conflicts)}")
    logger.info(f"   Duration: {result_a.duration_ms:.2f}ms")
    
    logger.info("\n2. Testing merge of dev_b into main (should detect conflicts)")
    result_b = await fixed_merge_engine.merge_branches(
        source_branch=dev_b_branch,
        target_branch=base_branch,
        base_branch=base_branch,
        auto_resolve=True
    )
    
    logger.info(f"   Status: {result_b.status}")
    logger.info(f"   Conflicts: {len(result_b.conflicts)}")
    
    if result_b.conflicts:
        logger.info("\n   Conflicts detected:")
        for conflict in result_b.conflicts:
            logger.info(f"   - {conflict.conflict_type} in {conflict.entity_type}.{conflict.field_name}")
            logger.info(f"     Source: {conflict.source_value}")
            logger.info(f"     Target: {conflict.target_value}")
            logger.info(f"     Severity: {conflict.severity}")
            logger.info(f"     Hint: {conflict.resolution_hint}")
    
    logger.info("\n3. Testing merge of dev_b into dev_a (complex conflict)")
    result_complex = await fixed_merge_engine.merge_branches(
        source_branch=dev_b_branch,
        target_branch=dev_a_branch,
        base_branch=base_branch,
        auto_resolve=True
    )
    
    logger.info(f"   Status: {result_complex.status}")
    logger.info(f"   Conflicts: {len(result_complex.conflicts)}")
    logger.info(f"   Auto-resolved: {result_complex.auto_resolved}")
    
    if result_complex.resolution_log:
        logger.info("\n   Resolution log:")
        for log_entry in result_complex.resolution_log:
            logger.info(f"   - {log_entry}")
    
    # Validate results
    logger.info("\n" + "=" * 80)
    logger.info("VALIDATION RESULTS")
    logger.info("=" * 80)
    
    tests_passed = 0
    tests_total = 4
    
    # Test 1: First merge should succeed (no conflicts)
    if result_a.status == "success" and len(result_a.conflicts) == 0:
        logger.info("✅ Test 1 PASSED: Non-conflicting merge succeeded")
        tests_passed += 1
    else:
        logger.error("❌ Test 1 FAILED: Non-conflicting merge should succeed")
    
    # Test 2: Second merge should detect conflicts
    if result_b.status == "conflict" and len(result_b.conflicts) > 0:
        logger.info("✅ Test 2 PASSED: Conflicts properly detected")
        tests_passed += 1
    else:
        logger.error("❌ Test 2 FAILED: Conflicts not detected")
    
    # Test 3: Should detect email required conflict
    email_conflicts = [c for c in result_b.conflicts if c.field_name == "email" and c.conflict_type == "required_change"]
    if email_conflicts:
        logger.info("✅ Test 3 PASSED: Email required conflict detected")
        tests_passed += 1
    else:
        logger.error("❌ Test 3 FAILED: Email required conflict not detected")
    
    # Test 4: Should detect name type conflict
    type_conflicts = [c for c in result_b.conflicts if c.field_name == "name" and c.conflict_type == "property_type"]
    if type_conflicts:
        logger.info("✅ Test 4 PASSED: Property type conflict detected")
        tests_passed += 1
    else:
        logger.error("❌ Test 4 FAILED: Property type conflict not detected")
    
    logger.info(f"\nTests passed: {tests_passed}/{tests_total}")
    
    if tests_passed == tests_total:
        logger.info("\n🎉 ALL TESTS PASSED! Merge conflict detection is now working correctly.")
    else:
        logger.error("\n❌ Some tests failed. Merge conflict detection still has issues.")
    
    return tests_passed == tests_total


@pytest.mark.asyncio
async def test_auto_resolution():
    """Test auto-resolution of safe conflicts"""
    logger.info("\n" + "=" * 80)
    logger.info("Testing Auto-Resolution of Safe Conflicts")
    logger.info("=" * 80)
    
    base_branch = {
        "branch_id": "main",
        "schema": {
            "Product": {
                "properties": {
                    "id": {"type": "string", "required": True},
                    "name": {"type": "string", "required": True}
                }
            }
        }
    }
    
    # Branch A: string -> text (safe widening)
    branch_a = {
        "branch_id": "feature_a",
        "schema": {
            "Product": {
                "properties": {
                    "id": {"type": "string", "required": True},
                    "name": {"type": "text", "required": True}  # Widened type
                }
            }
        }
    }
    
    # Branch B: required -> optional (safe relaxation)
    branch_b = {
        "branch_id": "feature_b",
        "schema": {
            "Product": {
                "properties": {
                    "id": {"type": "string", "required": False},  # Made optional
                    "name": {"type": "string", "required": True}
                }
            }
        }
    }
    
    # Test merging both into main
    result = await fixed_merge_engine.merge_branches(
        source_branch=branch_a,
        target_branch=branch_b,
        base_branch=base_branch,
        auto_resolve=True
    )
    
    logger.info(f"Status: {result.status}")
    logger.info(f"Auto-resolved: {result.auto_resolved}")
    
    if result.resolution_log:
        logger.info("\nResolution log:")
        for entry in result.resolution_log:
            logger.info(f"  - {entry}")
    
    return result.status == "success" and result.auto_resolved


async def main():
    """Run all validation tests"""
    conflict_test_passed = await test_conflict_detection()
    resolution_test_passed = await test_auto_resolution()
    
    logger.info("\n" + "=" * 80)
    logger.info("FINAL VALIDATION SUMMARY")
    logger.info("=" * 80)
    
    if conflict_test_passed and resolution_test_passed:
        logger.info("✅ Merge engine fix is working correctly!")
        logger.info("✅ Conflicts are properly detected")
        logger.info("✅ Safe conflicts are auto-resolved")
        logger.info("\nThe critical merge issue has been FIXED.")
    else:
        logger.error("❌ Merge engine still has issues")
    
    return conflict_test_passed and resolution_test_passed


if __name__ == "__main__":
    success = asyncio.run(main())