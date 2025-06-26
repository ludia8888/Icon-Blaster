"""
Test merge engine with correct data format
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.versioning.merge_engine import merge_engine
from utils.logger import get_logger

logger = get_logger(__name__)


async def test_merge_with_correct_format():
    """Test merge engine with the correct data format it expects"""
    logger.info("=" * 80)
    logger.info("Testing OMS Merge Engine with CORRECT Data Format")
    logger.info("=" * 80)
    
    # Base branch with correct format
    base_branch = {
        "branch_id": "main",
        "commit_id": "base_001",
        "objects": [
            {
                "id": "Customer",
                "type": "object",
                "properties": [
                    {"name": "id", "type": "string", "required": True},
                    {"name": "email", "type": "string", "required": True},
                    {"name": "name", "type": "string", "required": True}
                ]
            }
        ]
    }
    
    # Developer A: Add phone, make email unique
    dev_a_branch = {
        "branch_id": "feature_a",
        "commit_id": "dev_a_001",
        "parent": "base_001",
        "objects": [
            {
                "id": "Customer",
                "type": "object", 
                "properties": [
                    {"name": "id", "type": "string", "required": True},
                    {"name": "email", "type": "string", "required": True, "unique": True},  # Added unique
                    {"name": "name", "type": "string", "required": True},
                    {"name": "phone", "type": "string", "required": False}  # Added phone
                ]
            }
        ]
    }
    
    # Developer B: Make email optional, change name type
    dev_b_branch = {
        "branch_id": "feature_b",
        "commit_id": "dev_b_001", 
        "parent": "base_001",
        "objects": [
            {
                "id": "Customer",
                "type": "object",
                "properties": [
                    {"name": "id", "type": "string", "required": True},
                    {"name": "email", "type": "string", "required": False},  # Made optional (CONFLICT!)
                    {"name": "name", "type": "text", "required": True},  # Changed type (CONFLICT!)
                    {"name": "address", "type": "string", "required": True}  # Added address
                ]
            }
        ]
    }
    
    logger.info("\n1. Testing non-conflicting merge (Dev A into Main)")
    try:
        result_a = await merge_engine.merge_branches(
            source_branch=dev_a_branch,
            target_branch=base_branch,
            auto_resolve=True,
            dry_run=True
        )
        
        logger.info(f"   Status: {result_a.status}")
        logger.info(f"   Auto-resolved: {result_a.auto_resolved}")
        logger.info(f"   Conflicts found: {len(result_a.conflicts) if result_a.conflicts else 0}")
        logger.info(f"   Max severity: {result_a.max_severity}")
        
        if result_a.conflicts:
            logger.info("   Conflicts detected:")
            for conflict in result_a.conflicts:
                logger.info(f"     - {conflict.type.value}: {conflict.description}")
        
    except Exception as e:
        logger.error(f"   Error in merge A: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info("\n2. Testing conflicting merge (Dev B into Main)")
    try:
        result_b = await merge_engine.merge_branches(
            source_branch=dev_b_branch,
            target_branch=base_branch,
            auto_resolve=True,
            dry_run=True
        )
        
        logger.info(f"   Status: {result_b.status}")
        logger.info(f"   Auto-resolved: {result_b.auto_resolved}")
        logger.info(f"   Conflicts found: {len(result_b.conflicts) if result_b.conflicts else 0}")
        logger.info(f"   Max severity: {result_b.max_severity}")
        
        if result_b.conflicts:
            logger.info("   Conflicts detected:")
            for conflict in result_b.conflicts:
                logger.info(f"     - {conflict.type.value}: {conflict.description}")
                logger.info(f"       Severity: {conflict.severity.value}")
                logger.info(f"       Auto-resolvable: {conflict.auto_resolvable}")
        
    except Exception as e:
        logger.error(f"   Error in merge B: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info("\n3. Testing complex 3-way merge (Dev B into Dev A)")
    try:
        result_complex = await merge_engine.merge_branches(
            source_branch=dev_b_branch,
            target_branch=dev_a_branch,
            auto_resolve=False,  # Don't auto-resolve to see all conflicts
            dry_run=True
        )
        
        logger.info(f"   Status: {result_complex.status}")
        logger.info(f"   Auto-resolved: {result_complex.auto_resolved}")
        logger.info(f"   Conflicts found: {len(result_complex.conflicts) if result_complex.conflicts else 0}")
        logger.info(f"   Max severity: {result_complex.max_severity}")
        
        if result_complex.conflicts:
            logger.info("   Conflicts detected:")
            for conflict in result_complex.conflicts:
                logger.info(f"     - {conflict.type.value}: {conflict.description}")
                logger.info(f"       Entity: {conflict.entity_id}")
                logger.info(f"       Severity: {conflict.severity.value}")
                logger.info(f"       Source value: {conflict.branch_a_value}")
                logger.info(f"       Target value: {conflict.branch_b_value}")
        
    except Exception as e:
        logger.error(f"   Error in complex merge: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info("\n4. Testing conflict analysis")
    try:
        analysis = await merge_engine.analyze_conflicts(
            source_branch=dev_b_branch,
            target_branch=dev_a_branch
        )
        
        logger.info(f"   Conflict analysis results:")
        logger.info(f"     Total conflicts: {analysis.get('total_conflicts', 0)}")
        logger.info(f"     Auto-resolvable: {analysis.get('auto_resolvable', 0)}")
        logger.info(f"     Max severity: {analysis.get('max_severity')}")
        logger.info(f"     By type: {analysis.get('by_type', {})}")
        
    except Exception as e:
        logger.error(f"   Error in conflict analysis: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info("\n" + "=" * 80)
    logger.info("EVALUATION OF MERGE ENGINE WITH CORRECT FORMAT")
    logger.info("=" * 80)
    
    return True


async def test_property_level_conflicts():
    """Test property-level conflict detection"""
    logger.info("\n" + "=" * 80)
    logger.info("Testing Property-Level Conflict Detection")
    logger.info("=" * 80)
    
    # Create branches that should definitely conflict at property level
    base = {
        "branch_id": "main",
        "commit_id": "prop_base",
        "objects": [
            {
                "id": "Product",
                "properties": [
                    {"name": "id", "type": "string"},
                    {"name": "price", "type": "decimal"},
                    {"name": "name", "type": "string"}
                ]
            }
        ]
    }
    
    branch_a = {
        "branch_id": "branch_a",
        "commit_id": "prop_a", 
        "parent": "prop_base",
        "objects": [
            {
                "id": "Product",
                "properties": [
                    {"name": "id", "type": "string"},
                    {"name": "price", "type": "integer"},  # CONFLICT: decimal -> integer
                    {"name": "name", "type": "string"},
                    {"name": "category", "type": "string"}  # Added
                ]
            }
        ]
    }
    
    branch_b = {
        "branch_id": "branch_b",
        "commit_id": "prop_b",
        "parent": "prop_base", 
        "objects": [
            {
                "id": "Product",
                "properties": [
                    {"name": "id", "type": "string"},
                    {"name": "price", "type": "currency"},  # CONFLICT: decimal -> currency
                    {"name": "name", "type": "text"},  # CONFLICT: string -> text
                    {"name": "description", "type": "text"}  # Added different property
                ]
            }
        ]
    }
    
    try:
        result = await merge_engine.merge_branches(
            source_branch=branch_a,
            target_branch=branch_b,
            auto_resolve=False,
            dry_run=True
        )
        
        logger.info(f"Property conflict test results:")
        logger.info(f"  Status: {result.status}")
        logger.info(f"  Conflicts: {len(result.conflicts) if result.conflicts else 0}")
        
        if result.conflicts:
            for conflict in result.conflicts:
                logger.info(f"  - Conflict: {conflict.description}")
                logger.info(f"    Type: {conflict.type.value}")
                logger.info(f"    Severity: {conflict.severity.value}")
        
    except Exception as e:
        logger.error(f"Property conflict test error: {e}")
        import traceback
        traceback.print_exc()
    
    return True


async def main():
    """Run all correct format tests"""
    format_test = await test_merge_with_correct_format()
    property_test = await test_property_level_conflicts()
    
    logger.info("\n" + "=" * 80)
    logger.info("FINAL ASSESSMENT WITH CORRECT DATA FORMAT")
    logger.info("=" * 80)
    
    if format_test and property_test:
        logger.info("✅ Merge engine tests with correct format completed!")
        logger.info("✅ Now we can properly evaluate the conflict detection")
    else:
        logger.error("❌ Some tests failed")
    
    return format_test and property_test


if __name__ == "__main__":
    success = asyncio.run(main())