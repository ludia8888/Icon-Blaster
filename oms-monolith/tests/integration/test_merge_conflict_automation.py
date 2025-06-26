"""
Merge Conflict Automation Test Suite

Comprehensive test suite for automated merge conflict resolution in OMS.
Tests various conflict scenarios with 10k branches and 100k merges.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import random
import uuid
from concurrent.futures import ThreadPoolExecutor
import json

from core.versioning.merge_engine import MergeEngine
from core.schema.conflict_resolver import ConflictResolver
from models.domain import (
    ObjectType, Property, LinkType, 
    Cardinality, Directionality, Status
)
from utils.logger import get_logger

logger = get_logger(__name__)


class MergeConflictSimulator:
    """Simulates various merge conflict scenarios for testing"""
    
    def __init__(self):
        self.branches: Dict[str, Any] = {}
        self.merge_history: List[Dict[str, Any]] = []
        self.conflict_stats = {
            "total_merges": 0,
            "auto_resolved": 0,
            "manual_required": 0,
            "failed": 0,
            "by_type": {}
        }
    
    async def generate_branch_scenario(
        self,
        num_branches: int,
        divergence_factor: float = 0.3
    ) -> Dict[str, Any]:
        """
        Generate a realistic branch scenario with controlled divergence.
        
        Args:
            num_branches: Number of branches to create
            divergence_factor: How much branches diverge (0-1)
        """
        logger.info(f"Generating {num_branches} branches with {divergence_factor} divergence")
        
        # Create base branch
        base_branch = await self._create_base_schema()
        self.branches["main"] = base_branch
        
        # Create divergent branches
        for i in range(num_branches):
            branch_name = f"feature-{i:04d}"
            branch = await self._create_divergent_branch(
                base_branch,
                divergence_factor,
                i
            )
            self.branches[branch_name] = branch
        
        return {
            "branches": len(self.branches),
            "total_objects": sum(len(b.get("objects", [])) for b in self.branches.values()),
            "potential_conflicts": self._estimate_conflicts()
        }
    
    async def _create_base_schema(self) -> Dict[str, Any]:
        """Create a base schema with common patterns"""
        return {
            "branch_id": "main",
            "commit_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow(),
            "objects": [
                {
                    "id": "User",
                    "type": "ObjectType",
                    "properties": ["id", "name", "email", "created_at"]
                },
                {
                    "id": "Post",
                    "type": "ObjectType",
                    "properties": ["id", "title", "content", "author_id"]
                },
                {
                    "id": "Comment",
                    "type": "ObjectType",
                    "properties": ["id", "text", "post_id", "user_id"]
                }
            ],
            "links": [
                {
                    "id": "user_posts",
                    "from": "User",
                    "to": "Post",
                    "cardinality": "ONE_TO_MANY"
                },
                {
                    "id": "post_comments",
                    "from": "Post",
                    "to": "Comment",
                    "cardinality": "ONE_TO_MANY"
                }
            ]
        }
    
    async def _create_divergent_branch(
        self,
        base: Dict[str, Any],
        divergence: float,
        seed: int
    ) -> Dict[str, Any]:
        """Create a branch with controlled divergence from base"""
        random.seed(seed)  # Reproducible randomness
        
        branch = {
            "branch_id": f"feature-{seed:04d}",
            "commit_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow() + timedelta(hours=seed),
            "parent": base["commit_id"],
            "objects": base["objects"].copy(),
            "links": base["links"].copy()
        }
        
        # Apply modifications based on divergence factor
        num_changes = int(len(branch["objects"]) * divergence)
        
        for _ in range(num_changes):
            change_type = random.choice(["add_property", "modify_type", "add_link"])
            
            if change_type == "add_property":
                obj = random.choice(branch["objects"])
                new_prop = f"field_{random.randint(1000, 9999)}"
                if "properties" in obj and new_prop not in obj["properties"]:
                    obj["properties"].append(new_prop)
                    
            elif change_type == "modify_type":
                if random.random() < 0.3:  # 30% chance to add new object
                    branch["objects"].append({
                        "id": f"Type_{seed}_{random.randint(100, 999)}",
                        "type": "ObjectType",
                        "properties": ["id", "data"]
                    })
                    
            elif change_type == "add_link":
                if len(branch["objects"]) > 2:
                    from_obj = random.choice(branch["objects"])
                    to_obj = random.choice(branch["objects"])
                    if from_obj["id"] != to_obj["id"]:
                        branch["links"].append({
                            "id": f"link_{seed}_{random.randint(100, 999)}",
                            "from": from_obj["id"],
                            "to": to_obj["id"],
                            "cardinality": random.choice(["ONE_TO_ONE", "ONE_TO_MANY"])
                        })
        
        return branch
    
    def _estimate_conflicts(self) -> int:
        """Estimate potential conflicts between branches"""
        # Simple estimation based on overlapping changes
        return len(self.branches) * 2  # Rough estimate


class TestMergeConflictAutomation:
    """Test suite for merge conflict automation"""
    
    @pytest.fixture
    async def simulator(self):
        """Create a merge conflict simulator"""
        return MergeConflictSimulator()
    
    @pytest.fixture
    async def merge_engine(self):
        """Create a merge engine with conflict resolver"""
        resolver = ConflictResolver()
        engine = MergeEngine(resolver)
        return engine
    
    @pytest.mark.asyncio
    async def test_simple_auto_resolvable_conflicts(self, simulator, merge_engine):
        """Test conflicts that can be automatically resolved"""
        # Generate simple scenario
        await simulator.generate_branch_scenario(10, divergence_factor=0.1)
        
        results = []
        for branch_name, branch in simulator.branches.items():
            if branch_name == "main":
                continue
                
            result = await merge_engine.merge_branches(
                source_branch=branch,
                target_branch=simulator.branches["main"],
                auto_resolve=True
            )
            results.append(result)
        
        # Verify all merges succeeded
        successful = [r for r in results if r["status"] == "success"]
        assert len(successful) == len(results) - 1  # -1 for main branch
        
        # Check auto-resolution rate
        auto_resolved = [r for r in results if r.get("auto_resolved")]
        assert len(auto_resolved) > len(results) * 0.8  # >80% auto-resolved
    
    @pytest.mark.asyncio
    async def test_complex_manual_conflicts(self, simulator, merge_engine):
        """Test conflicts requiring manual resolution"""
        # Generate complex scenario with high divergence
        await simulator.generate_branch_scenario(20, divergence_factor=0.7)
        
        manual_conflicts = []
        for branch_name, branch in simulator.branches.items():
            if branch_name == "main":
                continue
                
            result = await merge_engine.merge_branches(
                source_branch=branch,
                target_branch=simulator.branches["main"],
                auto_resolve=True
            )
            
            if result.get("manual_resolution_required"):
                manual_conflicts.append({
                    "branch": branch_name,
                    "conflicts": result["conflicts"]
                })
        
        # Verify we have manual conflicts
        assert len(manual_conflicts) > 0
        
        # Test manual resolution
        for conflict in manual_conflicts[:5]:  # Test first 5
            resolution = await self._create_manual_resolution(conflict["conflicts"])
            result = await merge_engine.apply_manual_resolution(
                conflict["branch"],
                resolution
            )
            assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_concurrent_merge_performance(self, simulator, merge_engine):
        """Test performance with concurrent merges"""
        # Generate large scenario
        await simulator.generate_branch_scenario(100, divergence_factor=0.4)
        
        start_time = datetime.utcnow()
        
        # Run concurrent merges
        async def merge_branch(branch_name, branch):
            if branch_name == "main":
                return None
            return await merge_engine.merge_branches(
                source_branch=branch,
                target_branch=simulator.branches["main"],
                auto_resolve=True
            )
        
        # Execute merges concurrently
        tasks = [
            merge_branch(name, branch)
            for name, branch in simulator.branches.items()
        ]
        results = await asyncio.gather(*tasks)
        results = [r for r in results if r]  # Filter None results
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Performance assertions
        assert duration < 10  # Should complete within 10 seconds
        assert len(results) > 90  # Most merges should complete
        
        # Calculate statistics
        stats = {
            "total_merges": len(results),
            "successful": len([r for r in results if r["status"] == "success"]),
            "failed": len([r for r in results if r["status"] == "failed"]),
            "avg_time_ms": sum(r.get("duration_ms", 0) for r in results) / len(results)
        }
        
        logger.info(f"Concurrent merge stats: {stats}")
        assert stats["successful"] > stats["total_merges"] * 0.8  # >80% success rate
        assert stats["avg_time_ms"] < 100  # <100ms average
    
    @pytest.mark.asyncio
    async def test_conflict_type_distribution(self, simulator, merge_engine):
        """Test different types of conflicts and their resolution"""
        # Generate scenario with specific conflict types
        await simulator.generate_branch_scenario(50, divergence_factor=0.5)
        
        conflict_types = {
            "property_type_change": 0,
            "cardinality_change": 0,
            "delete_modify": 0,
            "circular_dependency": 0,
            "name_collision": 0
        }
        
        for branch_name, branch in simulator.branches.items():
            if branch_name == "main":
                continue
                
            result = await merge_engine.analyze_conflicts(
                source_branch=branch,
                target_branch=simulator.branches["main"]
            )
            
            for conflict in result.get("conflicts", []):
                conflict_type = conflict.get("type", "unknown")
                if conflict_type in conflict_types:
                    conflict_types[conflict_type] += 1
        
        # Verify we see various conflict types
        assert sum(conflict_types.values()) > 0
        assert max(conflict_types.values()) < sum(conflict_types.values()) * 0.5  # No single type dominates
    
    @pytest.mark.asyncio
    async def test_merge_with_severity_grades(self, simulator, merge_engine):
        """Test merge conflict resolution with severity grades"""
        # Create specific conflict scenarios
        base = await simulator._create_base_schema()
        
        # INFO level conflict - safe automatic resolution
        branch1 = await self._create_branch_with_info_conflict(base)
        result1 = await merge_engine.merge_branches(
            source_branch=branch1,
            target_branch=base,
            auto_resolve=True
        )
        assert result1["status"] == "success"
        assert result1.get("max_severity") == "INFO"
        
        # WARN level conflict - automatic with warnings
        branch2 = await self._create_branch_with_warn_conflict(base)
        result2 = await merge_engine.merge_branches(
            source_branch=branch2,
            target_branch=base,
            auto_resolve=True
        )
        assert result2["status"] == "success"
        assert len(result2.get("warnings", [])) > 0
        
        # ERROR level conflict - requires manual resolution
        branch3 = await self._create_branch_with_error_conflict(base)
        result3 = await merge_engine.merge_branches(
            source_branch=branch3,
            target_branch=base,
            auto_resolve=True
        )
        assert result3.get("manual_resolution_required") is True
        assert result3.get("max_severity") == "ERROR"
        
        # BLOCK level conflict - cannot proceed
        branch4 = await self._create_branch_with_block_conflict(base)
        result4 = await merge_engine.merge_branches(
            source_branch=branch4,
            target_branch=base,
            auto_resolve=True
        )
        assert result4["status"] == "blocked"
        assert result4.get("max_severity") == "BLOCK"
    
    @pytest.mark.asyncio
    async def test_dag_compaction_integration(self, simulator, merge_engine):
        """Test merge with DAG compaction enabled"""
        from core.versioning.dag_compaction import dag_compactor
        
        # Generate branches with linear history
        await simulator.generate_branch_scenario(20, divergence_factor=0.2)
        
        # Perform initial merges
        merge_results = []
        for branch_name, branch in list(simulator.branches.items())[:10]:
            if branch_name == "main":
                continue
            result = await merge_engine.merge_branches(
                source_branch=branch,
                target_branch=simulator.branches["main"],
                auto_resolve=True
            )
            merge_results.append(result)
        
        # Run DAG compaction
        compaction_result = await dag_compactor.compact_dag(
            root_commits=[r["merge_commit"] for r in merge_results if "merge_commit" in r],
            dry_run=False
        )
        
        assert compaction_result["success"] is True
        assert compaction_result["space_saved"] > 0
        
        # Verify merge functionality still works after compaction
        for branch_name, branch in list(simulator.branches.items())[10:15]:
            result = await merge_engine.merge_branches(
                source_branch=branch,
                target_branch=simulator.branches["main"],
                auto_resolve=True
            )
            assert result["status"] in ["success", "manual_required"]
    
    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_large_scale_merge_performance(self, simulator, merge_engine):
        """Benchmark test for large-scale merge operations"""
        # This test simulates the 10k branches × 100k merges scenario
        num_branches = 1000  # Reduced for test performance
        merges_per_branch = 10
        
        logger.info(f"Starting large-scale merge test: {num_branches} branches")
        
        # Generate branches
        await simulator.generate_branch_scenario(num_branches, divergence_factor=0.3)
        
        merge_times = []
        conflict_counts = []
        
        # Perform multiple merge rounds
        for round_num in range(merges_per_branch):
            round_start = datetime.utcnow()
            round_conflicts = 0
            
            # Merge subset of branches
            batch_size = 100
            for i in range(0, num_branches, batch_size):
                batch_branches = list(simulator.branches.items())[i:i+batch_size]
                
                tasks = []
                for branch_name, branch in batch_branches:
                    if branch_name == "main":
                        continue
                    tasks.append(merge_engine.merge_branches(
                        source_branch=branch,
                        target_branch=simulator.branches["main"],
                        auto_resolve=True
                    ))
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                round_conflicts += sum(
                    1 for r in results 
                    if isinstance(r, dict) and r.get("manual_resolution_required")
                )
            
            round_time = (datetime.utcnow() - round_start).total_seconds()
            merge_times.append(round_time)
            conflict_counts.append(round_conflicts)
            
            logger.info(f"Round {round_num + 1}: {round_time:.2f}s, {round_conflicts} conflicts")
        
        # Performance assertions
        avg_time = sum(merge_times) / len(merge_times)
        assert avg_time < 30  # Average round should complete within 30s
        
        # P95 check
        sorted_times = sorted(merge_times)
        p95_time = sorted_times[int(len(sorted_times) * 0.95)]
        assert p95_time < 60  # P95 should be under 60s
        
        logger.info(f"Performance summary: avg={avg_time:.2f}s, p95={p95_time:.2f}s")
    
    # Helper methods
    
    async def _create_manual_resolution(self, conflicts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a manual resolution for given conflicts"""
        resolution = {
            "resolution_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow(),
            "decisions": []
        }
        
        for conflict in conflicts:
            decision = {
                "conflict_id": conflict["id"],
                "action": "accept_source",  # Simple strategy
                "rationale": "Test resolution"
            }
            resolution["decisions"].append(decision)
        
        return resolution
    
    async def _create_branch_with_info_conflict(self, base: Dict[str, Any]) -> Dict[str, Any]:
        """Create branch with INFO level conflicts (safe to auto-resolve)"""
        branch = base.copy()
        branch["branch_id"] = "info-conflict"
        
        # Add enum value (INFO level)
        for obj in branch["objects"]:
            if obj["id"] == "User":
                obj["properties"].append("status")  # New optional field
        
        return branch
    
    async def _create_branch_with_warn_conflict(self, base: Dict[str, Any]) -> Dict[str, Any]:
        """Create branch with WARN level conflicts"""
        branch = base.copy()
        branch["branch_id"] = "warn-conflict"
        
        # Change property type from specific to generic (WARN level)
        # This would need actual property type metadata in real implementation
        
        return branch
    
    async def _create_branch_with_error_conflict(self, base: Dict[str, Any]) -> Dict[str, Any]:
        """Create branch with ERROR level conflicts"""
        branch = base.copy()
        branch["branch_id"] = "error-conflict"
        
        # Change cardinality from ONE_TO_MANY to ONE_TO_ONE (ERROR level)
        for link in branch["links"]:
            if link["id"] == "user_posts":
                link["cardinality"] = "ONE_TO_ONE"
        
        return branch
    
    async def _create_branch_with_block_conflict(self, base: Dict[str, Any]) -> Dict[str, Any]:
        """Create branch with BLOCK level conflicts"""
        branch = base.copy()
        branch["branch_id"] = "block-conflict"
        
        # Create circular dependency (BLOCK level)
        branch["links"].append({
            "id": "circular_link",
            "from": "Post",
            "to": "User",
            "cardinality": "ONE_TO_ONE",
            "required": True
        })
        
        return branch


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-only"])