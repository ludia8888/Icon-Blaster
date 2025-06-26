#!/usr/bin/env python3
"""
Run Phase 6 Performance Tests

This script runs the DAG compaction and merge conflict automation tests
to validate the performance requirements.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.logger import get_logger
from tests.performance.test_dag_merge_performance import test_full_performance_suite

logger = get_logger(__name__)


async def main():
    """Run Phase 6 performance tests"""
    logger.info("=" * 80)
    logger.info("Phase 6: DAG Compaction & Merge Conflict Automation Tests")
    logger.info("=" * 80)
    
    logger.info("\nTest Requirements:")
    logger.info("- P95 merge time < 200ms")
    logger.info("- Handle 10k branches")
    logger.info("- Process 100k merges")
    logger.info("- Auto-resolution rate > 80%")
    logger.info("")
    
    try:
        # Run the full performance test suite
        await test_full_performance_suite()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ All Phase 6 tests passed successfully!")
        logger.info("=" * 80)
        
        # Print summary
        logger.info("\nKey Achievements:")
        logger.info("- DAG Compaction Algorithm implemented")
        logger.info("- Merge Engine with automated conflict resolution")
        logger.info("- Severity-based conflict handling (INFO/WARN/ERROR/BLOCK)")
        logger.info("- Performance requirements met (P95 < 200ms)")
        logger.info("- Comprehensive test coverage")
        
        logger.info("\nNext Steps:")
        logger.info("1. Deploy incremental compaction to production")
        logger.info("2. Set up monitoring dashboards")
        logger.info("3. Configure alerting for performance thresholds")
        logger.info("4. Run real-world workload simulations")
        
    except Exception as e:
        logger.error(f"Test suite failed: {e}")
        raise
    

if __name__ == "__main__":
    # Run with asyncio
    asyncio.run(main())