"""Unit tests for SchemaConflictResolver - Conflict resolution functionality."""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

# Mock external dependencies
import sys
sys.modules['common_logging'] = MagicMock()
sys.modules['common_logging.setup'] = MagicMock()

# Import the conflict resolver
try:
    from core.schema.conflict_resolver import ConflictResolver, ResolutionStrategy
except ImportError:
    # Create mock classes if import fails
    class ConflictResolver:
        def __init__(self):
            self.strategies = {}
            self.resolution_history = []
            self.resolution_cache = {}
    
    class ResolutionStrategy:
        def __init__(self, name, description, applicable_types, max_severity, resolution_func):
            self.name = name
            self.description = description
            self.applicable_types = applicable_types
            self.max_severity = max_severity
            self.resolution_func = resolution_func

# Mock conflict types and severities
class ConflictType(Enum):
    PROPERTY_TYPE_CHANGE = "property_type_change"
    CONSTRAINT_CONFLICT = "constraint_conflict"
    DELETE_AFTER_MODIFY = "delete_after_modify"
    NAME_COLLISION = "name_collision"
    CARDINALITY_CHANGE = "cardinality_change"

class ConflictSeverity(Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    BLOCK = "BLOCK"

@dataclass
class MergeConflict:
    """Mock merge conflict class"""
    id: str
    type: ConflictType
    severity: ConflictSeverity
    entity_id: str
    branch_a_value: Dict[str, Any]
    branch_b_value: Dict[str, Any]
    suggested_resolution: Optional[Dict[str, Any]] = None
    auto_resolvable: bool = False
    migration_impact: Optional[Dict[str, Any]] = None


class TestConflictResolverInitialization:
    """Test suite for ConflictResolver initialization."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = ConflictResolver()

    def test_conflict_resolver_initialization(self):
        """Test ConflictResolver initializes with default strategies."""
        assert self.resolver.strategies is not None
        assert self.resolver.resolution_history == []
        assert self.resolver.resolution_cache == {}

    def test_strategies_initialization(self):
        """Test that resolution strategies are properly initialized."""
        resolver = ConflictResolver()
        
        # Check that strategies are populated
        assert len(resolver.strategies) > 0
        
        # Check specific strategy exists
        assert "type_widening" in resolver.strategies
        assert "union_constraints" in resolver.strategies
        assert "prefer_modification" in resolver.strategies
        assert "merge_properties" in resolver.strategies
        assert "expand_cardinality" in resolver.strategies

    def test_strategy_properties(self):
        """Test strategy properties are correctly set."""
        resolver = ConflictResolver()
        
        type_widening = resolver.strategies.get("type_widening")
        assert type_widening is not None
        assert type_widening.name == "type_widening"
        assert type_widening.description == "Widen type to accommodate both values"
        assert "property_type_change" in type_widening.applicable_types
        assert type_widening.max_severity == "INFO"


class TestConflictResolverTypeWidening:
    """Test suite for type widening conflict resolution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = ConflictResolver()

    @pytest.mark.asyncio
    async def test_type_widening_string_to_text(self):
        """Test widening string to text type."""
        conflict = MergeConflict(
            id="test-conflict-1",
            type=ConflictType.PROPERTY_TYPE_CHANGE,
            severity=ConflictSeverity.INFO,
            entity_id="prop1",
            branch_a_value={"type": "string", "name": "field1"},
            branch_b_value={"type": "text", "name": "field1"}
        )

        resolved = await self.resolver._resolve_by_type_widening(conflict)
        
        assert resolved is not None
        assert resolved.suggested_resolution is not None
        assert resolved.suggested_resolution["resolved_type"] == "text"
        assert resolved.auto_resolvable is True

    @pytest.mark.asyncio
    async def test_type_widening_integer_to_long(self):
        """Test widening integer to long type."""
        conflict = MergeConflict(
            id="test-conflict-2",
            type=ConflictType.PROPERTY_TYPE_CHANGE,
            severity=ConflictSeverity.INFO,
            entity_id="prop2",
            branch_a_value={"type": "integer", "name": "field2"},
            branch_b_value={"type": "long", "name": "field2"}
        )

        resolved = await self.resolver._resolve_by_type_widening(conflict)
        
        assert resolved is not None
        assert resolved.suggested_resolution["resolved_type"] == "long"

    @pytest.mark.asyncio
    async def test_type_widening_incompatible_types(self):
        """Test type widening with incompatible types."""
        conflict = MergeConflict(
            id="test-conflict-3",
            type=ConflictType.PROPERTY_TYPE_CHANGE,
            severity=ConflictSeverity.INFO,
            entity_id="prop3",
            branch_a_value={"type": "string", "name": "field3"},
            branch_b_value={"type": "integer", "name": "field3"}
        )

        resolved = await self.resolver._resolve_by_type_widening(conflict)
        
        # Should return None for incompatible types
        assert resolved is None


class TestConflictResolverConstraintUnion:
    """Test suite for constraint union conflict resolution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = ConflictResolver()

    @pytest.mark.asyncio
    async def test_union_constraints_basic(self):
        """Test basic constraint union resolution."""
        conflict = MergeConflict(
            id="test-conflict-4",
            type=ConflictType.CONSTRAINT_CONFLICT,
            severity=ConflictSeverity.WARN,
            entity_id="prop4",
            branch_a_value={
                "type": "string",
                "constraints": [
                    {"type": "min_length", "value": 5},
                    {"type": "max_length", "value": 100}
                ]
            },
            branch_b_value={
                "type": "string",
                "constraints": [
                    {"type": "min_length", "value": 3},
                    {"type": "max_length", "value": 150}
                ]
            }
        )

        resolved = await self.resolver._resolve_by_union_constraints(conflict)
        
        assert resolved is not None
        assert resolved.auto_resolvable is True
        
        # Check that more permissive constraints are selected
        constraints = resolved.suggested_resolution["resolved_constraints"]
        min_constraint = next(c for c in constraints if c["type"] == "min_length")
        max_constraint = next(c for c in constraints if c["type"] == "max_length")
        
        assert min_constraint["value"] == 3  # More permissive (smaller min)
        assert max_constraint["value"] == 150  # More permissive (larger max)

    @pytest.mark.asyncio
    async def test_union_constraints_enum_values(self):
        """Test constraint union with enum values."""
        conflict = MergeConflict(
            id="test-conflict-5",
            type=ConflictType.CONSTRAINT_CONFLICT,
            severity=ConflictSeverity.WARN,
            entity_id="prop5",
            branch_a_value={
                "type": "string",
                "constraints": [
                    {"type": "enum", "values": ["A", "B", "C"]}
                ]
            },
            branch_b_value={
                "type": "string",
                "constraints": [
                    {"type": "enum", "values": ["B", "C", "D"]}
                ]
            }
        )

        resolved = await self.resolver._resolve_by_union_constraints(conflict)
        
        assert resolved is not None
        constraints = resolved.suggested_resolution["resolved_constraints"]
        enum_constraint = next(c for c in constraints if c["type"] == "enum")
        
        # Should contain union of all enum values
        assert set(enum_constraint["values"]) == {"A", "B", "C", "D"}


class TestConflictResolverModificationPreference:
    """Test suite for modification preference conflict resolution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = ConflictResolver()

    @pytest.mark.asyncio
    async def test_prefer_modification_over_deletion(self):
        """Test preferring modification over deletion."""
        conflict = MergeConflict(
            id="test-conflict-6",
            type=ConflictType.DELETE_AFTER_MODIFY,
            severity=ConflictSeverity.WARN,
            entity_id="entity6",
            branch_a_value={
                "id": "entity6",
                "name": "Modified Entity",
                "status": "active"
            },
            branch_b_value=None  # Deletion
        )

        resolved = await self.resolver._resolve_prefer_modification(conflict)
        
        assert resolved is not None
        assert resolved.auto_resolvable is True
        assert resolved.suggested_resolution["action"] == "keep_modification"
        assert resolved.suggested_resolution["resolved_value"] == conflict.branch_a_value

    @pytest.mark.asyncio
    async def test_allow_deletion_of_deprecated_entity(self):
        """Test allowing deletion of deprecated entities."""
        conflict = MergeConflict(
            id="test-conflict-7",
            type=ConflictType.DELETE_AFTER_MODIFY,
            severity=ConflictSeverity.WARN,
            entity_id="entity7",
            branch_a_value={
                "id": "entity7",
                "name": "Deprecated Entity",
                "deprecated": True
            },
            branch_b_value=None  # Deletion
        )

        resolved = await self.resolver._resolve_prefer_modification(conflict)
        
        assert resolved is not None
        assert resolved.suggested_resolution["action"] == "accept_deletion"
        assert resolved.suggested_resolution["reason"] == "Entity marked as deprecated"


class TestConflictResolverPropertyMerging:
    """Test suite for property merging conflict resolution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = ConflictResolver()

    @pytest.mark.asyncio
    async def test_merge_properties_success(self):
        """Test successful property merging."""
        conflict = MergeConflict(
            id="test-conflict-8",
            type=ConflictType.NAME_COLLISION,
            severity=ConflictSeverity.WARN,
            entity_id="type8",
            branch_a_value={
                "name": "TestType",
                "properties": ["prop1", "prop2", "prop3"]
            },
            branch_b_value={
                "name": "TestType",
                "properties": ["prop2", "prop3", "prop4"]
            }
        )

        resolved = await self.resolver._resolve_by_merging_properties(conflict)
        
        assert resolved is not None
        assert resolved.auto_resolvable is True
        
        merged_props = resolved.suggested_resolution["merged_properties"]
        assert set(merged_props) == {"prop1", "prop2", "prop3", "prop4"}

    @pytest.mark.asyncio
    async def test_merge_properties_with_conflicts(self):
        """Test property merging with conflicts."""
        # Mock has_property_conflicts to return True
        with patch.object(self.resolver, '_has_property_conflicts', return_value=True):
            conflict = MergeConflict(
                id="test-conflict-9",
                type=ConflictType.NAME_COLLISION,
                severity=ConflictSeverity.WARN,
                entity_id="type9",
                branch_a_value={
                    "name": "TestType",
                    "properties": ["prop1", "prop2"]
                },
                branch_b_value={
                    "name": "TestType",
                    "properties": ["prop2", "prop3"]
                }
            )

            resolved = await self.resolver._resolve_by_merging_properties(conflict)
            
            # Should return None when properties conflict
            assert resolved is None


class TestConflictResolverCardinalityExpansion:
    """Test suite for cardinality expansion conflict resolution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = ConflictResolver()

    @pytest.mark.asyncio
    async def test_expand_cardinality_one_to_many(self):
        """Test expanding cardinality from one-to-one to one-to-many."""
        conflict = MergeConflict(
            id="test-conflict-10",
            type=ConflictType.CARDINALITY_CHANGE,
            severity=ConflictSeverity.INFO,
            entity_id="rel10",
            branch_a_value={
                "name": "TestRelation",
                "cardinality": "ONE_TO_ONE"
            },
            branch_b_value={
                "name": "TestRelation",
                "cardinality": "ONE_TO_MANY"
            }
        )

        resolved = await self.resolver._resolve_cardinality_expansion(conflict)
        
        assert resolved is not None
        assert resolved.auto_resolvable is True
        assert resolved.suggested_resolution["resolved_cardinality"] == "ONE_TO_MANY"
        assert resolved.migration_impact is not None

    @pytest.mark.asyncio
    async def test_expand_cardinality_to_many_to_many(self):
        """Test expanding cardinality to many-to-many."""
        conflict = MergeConflict(
            id="test-conflict-11",
            type=ConflictType.CARDINALITY_CHANGE,
            severity=ConflictSeverity.INFO,
            entity_id="rel11",
            branch_a_value={
                "name": "TestRelation",
                "cardinality": "ONE_TO_MANY"
            },
            branch_b_value={
                "name": "TestRelation",
                "cardinality": "MANY_TO_MANY"
            }
        )

        resolved = await self.resolver._resolve_cardinality_expansion(conflict)
        
        assert resolved is not None
        assert resolved.suggested_resolution["resolved_cardinality"] == "MANY_TO_MANY"
        assert resolved.migration_impact["data_migration_required"] is True

    @pytest.mark.asyncio
    async def test_cardinality_expansion_impossible(self):
        """Test cardinality expansion when not possible."""
        conflict = MergeConflict(
            id="test-conflict-12",
            type=ConflictType.CARDINALITY_CHANGE,
            severity=ConflictSeverity.INFO,
            entity_id="rel12",
            branch_a_value={
                "name": "TestRelation",
                "cardinality": "MANY_TO_MANY"
            },
            branch_b_value={
                "name": "TestRelation",
                "cardinality": "ONE_TO_ONE"
            }
        )

        resolved = await self.resolver._resolve_cardinality_expansion(conflict)
        
        # Should return None for impossible expansion
        assert resolved is None


class TestConflictResolverMainFlow:
    """Test suite for main conflict resolution flow."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = ConflictResolver()

    @pytest.mark.asyncio
    async def test_resolve_conflict_success(self):
        """Test successful conflict resolution."""
        conflict = MergeConflict(
            id="test-conflict-13",
            type=ConflictType.PROPERTY_TYPE_CHANGE,
            severity=ConflictSeverity.INFO,
            entity_id="prop13",
            branch_a_value={"type": "string"},
            branch_b_value={"type": "text"}
        )

        resolved = await self.resolver.resolve_conflict(conflict)
        
        assert resolved is not None
        assert resolved.auto_resolvable is True
        assert len(self.resolver.resolution_history) == 1
        assert self.resolver.resolution_history[0]["success"] is True

    @pytest.mark.asyncio
    async def test_resolve_conflict_no_strategy(self):
        """Test conflict resolution when no strategy is available."""
        conflict = MergeConflict(
            id="test-conflict-14",
            type=ConflictType.PROPERTY_TYPE_CHANGE,
            severity=ConflictSeverity.BLOCK,  # Too high severity
            entity_id="prop14",
            branch_a_value={"type": "string"},
            branch_b_value={"type": "text"}
        )

        resolved = await self.resolver.resolve_conflict(conflict)
        
        assert resolved is None

    @pytest.mark.asyncio
    async def test_resolve_conflict_caching(self):
        """Test conflict resolution caching."""
        conflict = MergeConflict(
            id="test-conflict-15",
            type=ConflictType.PROPERTY_TYPE_CHANGE,
            severity=ConflictSeverity.INFO,
            entity_id="prop15",
            branch_a_value={"type": "string"},
            branch_b_value={"type": "text"}
        )

        # First resolution
        resolved1 = await self.resolver.resolve_conflict(conflict)
        assert resolved1 is not None
        
        # Second resolution should use cache
        resolved2 = await self.resolver.resolve_conflict(conflict)
        assert resolved2 is not None
        assert resolved2 is resolved1  # Should be same object from cache

    @pytest.mark.asyncio
    async def test_resolve_conflict_strategy_failure(self):
        """Test conflict resolution when strategy fails."""
        conflict = MergeConflict(
            id="test-conflict-16",
            type=ConflictType.PROPERTY_TYPE_CHANGE,
            severity=ConflictSeverity.INFO,
            entity_id="prop16",
            branch_a_value={"type": "string"},
            branch_b_value={"type": "text"}
        )

        # Mock strategy to fail
        with patch.object(self.resolver, '_resolve_by_type_widening', 
                         side_effect=Exception("Strategy failed")):
            resolved = await self.resolver.resolve_conflict(conflict)
            
            assert resolved is None
            assert len(self.resolver.resolution_history) == 1
            assert self.resolver.resolution_history[0]["success"] is False


class TestConflictResolverUtilities:
    """Test suite for ConflictResolver utility methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = ConflictResolver()

    def test_severity_allows_check(self):
        """Test severity level checking."""
        assert self.resolver._severity_allows(ConflictSeverity.INFO, "WARN") is True
        assert self.resolver._severity_allows(ConflictSeverity.WARN, "WARN") is True
        assert self.resolver._severity_allows(ConflictSeverity.ERROR, "WARN") is False
        assert self.resolver._severity_allows(ConflictSeverity.BLOCK, "INFO") is False

    def test_find_applicable_strategy(self):
        """Test finding applicable strategy for conflict."""
        conflict = MergeConflict(
            id="test-conflict-17",
            type=ConflictType.PROPERTY_TYPE_CHANGE,
            severity=ConflictSeverity.INFO,
            entity_id="prop17",
            branch_a_value={"type": "string"},
            branch_b_value={"type": "text"}
        )

        strategy = self.resolver._find_applicable_strategy(conflict)
        
        assert strategy is not None
        assert strategy.name == "type_widening"

    def test_merge_constraints_permissive(self):
        """Test merging constraints with permissive selection."""
        constraints_a = [
            {"type": "min_length", "value": 5},
            {"type": "max_length", "value": 100}
        ]
        constraints_b = [
            {"type": "min_length", "value": 3},
            {"type": "max_length", "value": 150}
        ]

        merged = self.resolver._merge_constraints(constraints_a, constraints_b)
        
        assert len(merged) == 2
        min_constraint = next(c for c in merged if c["type"] == "min_length")
        max_constraint = next(c for c in merged if c["type"] == "max_length")
        
        assert min_constraint["value"] == 3  # More permissive
        assert max_constraint["value"] == 150  # More permissive

    def test_get_resolution_stats(self):
        """Test getting resolution statistics."""
        # Add some mock history
        self.resolver.resolution_history = [
            {"conflict_id": "c1", "strategy": "type_widening", "success": True},
            {"conflict_id": "c2", "strategy": "type_widening", "success": False},
            {"conflict_id": "c3", "strategy": "union_constraints", "success": True}
        ]
        
        # Add cache entry
        self.resolver.resolution_cache["test_key"] = Mock()

        stats = self.resolver.get_resolution_stats()
        
        assert stats["total_attempts"] == 3
        assert stats["successful"] == 2
        assert stats["success_rate"] == 2/3
        assert stats["by_strategy"]["type_widening"]["total"] == 2
        assert stats["by_strategy"]["type_widening"]["success"] == 1
        assert stats["cache_size"] == 1

    def test_clear_cache(self):
        """Test cache clearing."""
        self.resolver.resolution_cache["test_key"] = Mock()
        assert len(self.resolver.resolution_cache) == 1
        
        self.resolver.clear_cache()
        
        assert len(self.resolver.resolution_cache) == 0

    def test_get_cache_key(self):
        """Test cache key generation."""
        conflict = MergeConflict(
            id="test-conflict-18",
            type=ConflictType.PROPERTY_TYPE_CHANGE,
            severity=ConflictSeverity.INFO,
            entity_id="prop18",
            branch_a_value={"type": "string"},
            branch_b_value={"type": "text"}
        )

        key = self.resolver._get_cache_key(conflict)
        
        assert isinstance(key, str)
        assert "property_type_change" in key
        assert "prop18" in key

    def test_get_cardinality_migration_notes(self):
        """Test cardinality migration notes generation."""
        notes = self.resolver._get_cardinality_migration_notes(
            "ONE_TO_ONE", "ONE_TO_MANY", "ONE_TO_MANY"
        )
        
        assert notes["from"] == "ONE_TO_ONE"
        assert notes["to"] == "ONE_TO_MANY"
        assert notes["data_migration_required"] is False
        assert len(notes["schema_changes"]) > 0

        # Test migration requiring data changes
        notes = self.resolver._get_cardinality_migration_notes(
            "ONE_TO_ONE", "MANY_TO_MANY", "MANY_TO_MANY"
        )
        
        assert notes["data_migration_required"] is True


# Integration tests
class TestConflictResolverIntegration:
    """Integration tests for ConflictResolver."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = ConflictResolver()

    @pytest.mark.asyncio
    async def test_full_resolution_workflow(self):
        """Test complete resolution workflow."""
        conflicts = [
            MergeConflict(
                id="integration-1",
                type=ConflictType.PROPERTY_TYPE_CHANGE,
                severity=ConflictSeverity.INFO,
                entity_id="prop1",
                branch_a_value={"type": "string"},
                branch_b_value={"type": "text"}
            ),
            MergeConflict(
                id="integration-2",
                type=ConflictType.CARDINALITY_CHANGE,
                severity=ConflictSeverity.INFO,
                entity_id="rel1",
                branch_a_value={"cardinality": "ONE_TO_ONE"},
                branch_b_value={"cardinality": "ONE_TO_MANY"}
            )
        ]

        resolved_conflicts = []
        for conflict in conflicts:
            resolved = await self.resolver.resolve_conflict(conflict)
            if resolved:
                resolved_conflicts.append(resolved)

        assert len(resolved_conflicts) == 2
        assert all(c.auto_resolvable for c in resolved_conflicts)
        assert len(self.resolver.resolution_history) == 2

    @pytest.mark.asyncio
    async def test_resolution_with_mixed_success(self):
        """Test resolution with some successes and failures."""
        conflicts = [
            MergeConflict(
                id="mixed-1",
                type=ConflictType.PROPERTY_TYPE_CHANGE,
                severity=ConflictSeverity.INFO,
                entity_id="prop1",
                branch_a_value={"type": "string"},
                branch_b_value={"type": "text"}
            ),
            MergeConflict(
                id="mixed-2",
                type=ConflictType.PROPERTY_TYPE_CHANGE,
                severity=ConflictSeverity.BLOCK,  # Too high severity
                entity_id="prop2",
                branch_a_value={"type": "string"},
                branch_b_value={"type": "integer"}
            )
        ]

        resolved_count = 0
        for conflict in conflicts:
            resolved = await self.resolver.resolve_conflict(conflict)
            if resolved:
                resolved_count += 1

        assert resolved_count == 1
        stats = self.resolver.get_resolution_stats()
        assert stats["total_attempts"] == 1  # Only one had applicable strategy
        assert stats["successful"] == 1