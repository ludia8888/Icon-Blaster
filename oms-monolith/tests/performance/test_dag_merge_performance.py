"""
Performance Tests for DAG Compaction and Merge Operations

Tests the performance characteristics of:
- DAG compaction with 10k branches
- Merge operations with 100k merges
- Conflict resolution at scale
"""

import pytest
import asyncio
from datetime import datetime, timedelta
import random
import statistics
from typing import List, Dict, Any, Tuple
import uuid
import json
import time

from core.versioning.dag_compaction import DAGCompactionEngine, CommitNode
from core.versioning.merge_engine import MergeEngine
from core.schema.conflict_resolver import ConflictResolver
from tests.integration.test_merge_conflict_automation import MergeConflictSimulator
from utils.logger import get_logger

logger = get_logger(__name__)


class PerformanceMetrics:
    """Collect and analyze performance metrics"""
    
    def __init__(self):
        self.measurements = {
            "merge_times": [],
            "conflict_resolution_times": [],
            "dag_compaction_times": [],
            "memory_usage": []
        }
        
    def record_merge(self, duration_ms: float):
        self.measurements["merge_times"].append(duration_ms)
        
    def record_conflict_resolution(self, duration_ms: float):
        self.measurements["conflict_resolution_times"].append(duration_ms)
        
    def record_dag_compaction(self, duration_ms: float):
        self.measurements["dag_compaction_times"].append(duration_ms)
        
    def get_stats(self, metric: str) -> Dict[str, float]:
        """Get statistics for a metric"""
        values = self.measurements.get(metric, [])
        if not values:
            return {}
            
        sorted_values = sorted(values)
        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95": sorted_values[int(len(sorted_values) * 0.95)],
            "p99": sorted_values[int(len(sorted_values) * 0.99)],
            "min": min(values),
            "max": max(values)
        }
    
    def print_summary(self):
        """Print performance summary"""
        logger.info("=== Performance Summary ===")
        for metric, values in self.measurements.items():
            if values:
                stats = self.get_stats(metric)
                logger.info(f"\n{metric}:")
                logger.info(f"  Count: {stats['count']}")
                logger.info(f"  Mean: {stats['mean']:.2f}ms")
                logger.info(f"  P95: {stats['p95']:.2f}ms")
                logger.info(f"  P99: {stats['p99']:.2f}ms")


class TestDAGMergePerformance:
    """Performance test suite for DAG and merge operations"""
    
    @pytest.fixture
    def metrics(self):
        return PerformanceMetrics()
    
    @pytest.fixture
    async def dag_engine(self):
        return DAGCompactionEngine()
    
    @pytest.fixture
    async def merge_engine(self):
        resolver = ConflictResolver()
        return MergeEngine(resolver)
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_dag_compaction_10k_branches(self, dag_engine, metrics):
        """Test DAG compaction performance with 10k branches"""
        logger.info("Starting DAG compaction test with 10k branches")
        
        # Generate realistic DAG structure
        commits = await self._generate_dag_structure(
            num_branches=10000,
            commits_per_branch=100,
            merge_frequency=0.1
        )
        
        # Measure compaction performance
        start_time = time.perf_counter()
        
        # Analyze DAG
        analysis = await dag_engine.analyze_dag(
            root_commits=[c.commit_id for c in commits[:100]]  # Sample roots
        )
        
        analysis_time = (time.perf_counter() - start_time) * 1000
        metrics.record_dag_compaction(analysis_time)
        
        logger.info(f"DAG Analysis completed in {analysis_time:.2f}ms")
        logger.info(f"Found {analysis['compactable_nodes']} compactable nodes")
        logger.info(f"Estimated savings: {analysis['estimated_space_savings'] / 1024 / 1024:.2f}MB")
        
        # Test actual compaction
        compaction_start = time.perf_counter()
        
        result = await dag_engine.compact_dag(
            root_commits=[c.commit_id for c in commits[:100]],
            dry_run=False
        )
        
        compaction_time = (time.perf_counter() - compaction_start) * 1000
        metrics.record_dag_compaction(compaction_time)
        
        # Assertions
        assert result["success"] is True
        assert compaction_time < 5000  # Should complete within 5 seconds
        assert result["space_saved"] > 0
        
        logger.info(f"Compaction completed in {compaction_time:.2f}ms")
        logger.info(f"Space saved: {result['space_saved'] / 1024 / 1024:.2f}MB")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_merge_performance_100k_operations(self, merge_engine, metrics):
        """Test merge performance with 100k operations"""
        logger.info("Starting merge performance test with 100k operations")
        
        # Generate test branches
        simulator = MergeConflictSimulator()
        await simulator.generate_branch_scenario(1000, divergence_factor=0.3)
        
        # Perform merges in batches
        total_merges = 0
        batch_size = 100
        target_merges = 100000
        
        while total_merges < target_merges:
            # Select random branches for merging
            branch_pairs = self._select_branch_pairs(simulator.branches, batch_size)
            
            # Execute concurrent merges
            tasks = []
            for source, target in branch_pairs:
                tasks.append(self._timed_merge(
                    merge_engine,
                    source,
                    target,
                    metrics
                ))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
            total_merges += len(results)
            
            if total_merges % 10000 == 0:
                logger.info(f"Completed {total_merges} merges...")
        
        # Check performance requirements
        merge_stats = metrics.get_stats("merge_times")
        
        assert merge_stats["p95"] < 200  # P95 < 200ms requirement
        assert merge_stats["mean"] < 100  # Average should be well under P95
        
        logger.info(f"Completed {total_merges} merges")
        logger.info(f"P95 merge time: {merge_stats['p95']:.2f}ms")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_conflict_resolution_at_scale(self, merge_engine, metrics):
        """Test conflict resolution performance at scale"""
        logger.info("Testing conflict resolution performance")
        
        # Generate high-conflict scenario
        simulator = MergeConflictSimulator()
        await simulator.generate_branch_scenario(500, divergence_factor=0.7)
        
        conflict_times = []
        auto_resolved = 0
        manual_required = 0
        
        # Test conflict resolution
        for i in range(1000):
            source = random.choice(list(simulator.branches.values()))
            target = random.choice(list(simulator.branches.values()))
            
            if source["branch_id"] == target["branch_id"]:
                continue
            
            start = time.perf_counter()
            
            # Analyze conflicts
            analysis = await merge_engine.analyze_conflicts(source, target)
            
            # Attempt resolution
            if analysis["conflicts"]:
                for conflict in analysis["conflicts"]:
                    resolution_start = time.perf_counter()
                    resolved = await merge_engine.resolver.resolve_conflict(conflict)
                    resolution_time = (time.perf_counter() - resolution_start) * 1000
                    
                    metrics.record_conflict_resolution(resolution_time)
                    
                    if resolved:
                        auto_resolved += 1
                    else:
                        manual_required += 1
            
            duration = (time.perf_counter() - start) * 1000
            conflict_times.append(duration)
        
        # Performance assertions
        avg_resolution_time = statistics.mean(metrics.measurements["conflict_resolution_times"])
        assert avg_resolution_time < 10  # Each conflict should resolve in <10ms
        
        auto_rate = auto_resolved / (auto_resolved + manual_required) if (auto_resolved + manual_required) > 0 else 0
        logger.info(f"Auto-resolution rate: {auto_rate:.2%}")
        logger.info(f"Average resolution time: {avg_resolution_time:.2f}ms")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_merge_stress(self, merge_engine, metrics):
        """Stress test with high concurrency"""
        logger.info("Starting concurrent merge stress test")
        
        # Generate branches
        simulator = MergeConflictSimulator()
        await simulator.generate_branch_scenario(200, divergence_factor=0.4)
        
        # Run concurrent merges
        concurrency_levels = [10, 50, 100, 200]
        
        for concurrency in concurrency_levels:
            logger.info(f"Testing with {concurrency} concurrent merges")
            
            start = time.perf_counter()
            tasks = []
            
            for _ in range(concurrency):
                source = random.choice(list(simulator.branches.values()))
                target = simulator.branches["main"]
                
                tasks.append(merge_engine.merge_branches(
                    source_branch=source,
                    target_branch=target,
                    auto_resolve=True
                ))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            duration = (time.perf_counter() - start) * 1000
            
            successful = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
            throughput = successful / (duration / 1000)  # merges per second
            
            logger.info(f"  Completed in {duration:.2f}ms")
            logger.info(f"  Throughput: {throughput:.2f} merges/second")
            
            # Should maintain performance under load
            assert throughput > 10  # At least 10 merges/second
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_memory_efficiency(self, dag_engine, merge_engine, metrics):
        """Test memory efficiency of operations"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        logger.info(f"Initial memory usage: {initial_memory:.2f}MB")
        
        # Generate large dataset
        commits = await self._generate_dag_structure(
            num_branches=1000,
            commits_per_branch=100,
            merge_frequency=0.2
        )
        
        after_generation = process.memory_info().rss / 1024 / 1024
        logger.info(f"After generation: {after_generation:.2f}MB (+{after_generation - initial_memory:.2f}MB)")
        
        # Run compaction
        await dag_engine.compact_dag(
            root_commits=[c.commit_id for c in commits[:50]],
            dry_run=False
        )
        
        after_compaction = process.memory_info().rss / 1024 / 1024
        logger.info(f"After compaction: {after_compaction:.2f}MB")
        
        # Memory should not grow excessively
        memory_growth = after_compaction - initial_memory
        assert memory_growth < 500  # Less than 500MB growth
        
        # Clear caches
        dag_engine.commit_cache.clear()
        merge_engine.resolver.clear_cache()
        
        after_cleanup = process.memory_info().rss / 1024 / 1024
        logger.info(f"After cleanup: {after_cleanup:.2f}MB")
    
    # Helper methods
    
    async def _generate_dag_structure(
        self,
        num_branches: int,
        commits_per_branch: int,
        merge_frequency: float
    ) -> List[CommitNode]:
        """Generate a realistic DAG structure"""
        commits = []
        branch_heads = {}
        
        # Create main branch
        main_commit = CommitNode(
            commit_id="main_root",
            parent_ids=[],
            branch_id="main",
            timestamp=datetime.utcnow(),
            schema_hash="root_hash"
        )
        commits.append(main_commit)
        branch_heads["main"] = main_commit
        
        # Create branches
        for branch_idx in range(num_branches):
            branch_name = f"branch_{branch_idx}"
            parent = main_commit
            
            for commit_idx in range(commits_per_branch):
                # Occasionally merge from another branch
                if random.random() < merge_frequency and len(branch_heads) > 1:
                    other_branch = random.choice([b for b in branch_heads.keys() if b != branch_name])
                    parent_ids = [parent.commit_id, branch_heads[other_branch].commit_id]
                else:
                    parent_ids = [parent.commit_id] if parent else []
                
                commit = CommitNode(
                    commit_id=f"{branch_name}_commit_{commit_idx}",
                    parent_ids=parent_ids,
                    branch_id=branch_name,
                    timestamp=datetime.utcnow() + timedelta(seconds=commit_idx),
                    schema_hash=f"hash_{branch_idx}_{commit_idx}"
                )
                
                commits.append(commit)
                parent = commit
            
            branch_heads[branch_name] = parent
        
        # Return commits without populating cache here
        # The DAG engine will populate its own cache when needed
        
        return commits
    
    def _select_branch_pairs(
        self,
        branches: Dict[str, Any],
        count: int
    ) -> List[Tuple[Dict, Dict]]:
        """Select random branch pairs for merging"""
        pairs = []
        branch_list = list(branches.values())
        
        for _ in range(count):
            source = random.choice(branch_list)
            target = random.choice(branch_list)
            
            if source["branch_id"] != target["branch_id"]:
                pairs.append((source, target))
        
        return pairs
    
    async def _timed_merge(
        self,
        merge_engine: MergeEngine,
        source: Dict[str, Any],
        target: Dict[str, Any],
        metrics: PerformanceMetrics
    ) -> Dict[str, Any]:
        """Execute a timed merge operation"""
        start = time.perf_counter()
        
        try:
            result = await merge_engine.merge_branches(
                source_branch=source,
                target_branch=target,
                auto_resolve=True
            )
            
            duration = (time.perf_counter() - start) * 1000
            metrics.record_merge(duration)
            
            return {
                "success": result.status == "success",
                "duration_ms": duration,
                "auto_resolved": result.auto_resolved
            }
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            metrics.record_merge(duration)
            return {
                "success": False,
                "duration_ms": duration,
                "error": str(e)
            }


@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_full_performance_suite():
    """Run complete performance test suite"""
    logger.info("Running full performance test suite")
    
    metrics = PerformanceMetrics()
    dag_engine = DAGCompactionEngine()
    merge_engine = MergeEngine()
    
    test_suite = TestDAGMergePerformance()
    
    # Run all performance tests
    await test_suite.test_dag_compaction_10k_branches(dag_engine, metrics)
    await test_suite.test_merge_performance_100k_operations(merge_engine, metrics)
    await test_suite.test_conflict_resolution_at_scale(merge_engine, metrics)
    await test_suite.test_concurrent_merge_stress(merge_engine, metrics)
    
    # Print final summary
    metrics.print_summary()
    
    # Verify key requirements
    merge_stats = metrics.get_stats("merge_times")
    assert merge_stats["p95"] < 200, f"P95 merge time {merge_stats['p95']}ms exceeds 200ms requirement"
    
    logger.info("✅ All performance requirements met!")


if __name__ == "__main__":
    asyncio.run(test_full_performance_suite())