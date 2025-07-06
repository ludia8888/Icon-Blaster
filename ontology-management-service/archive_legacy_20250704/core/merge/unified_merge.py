"""
Unified Three-Way Merge Implementation
Consolidates all merge algorithms with pluggable strategies
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import TypeVar, Generic, Optional, Dict, List, Any, Tuple, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
import json

logger = logging.getLogger(__name__)

T = TypeVar('T')


class MergeStrategy(Enum):
    """Available merge strategies"""
    OURS = "ours"              # Take source version
    THEIRS = "theirs"          # Take target version
    MANUAL = "manual"          # Require manual resolution
    AUTO_RESOLVE = "auto"      # Automatic conflict resolution
    CUSTOM = "custom"          # User-defined strategy
    FAST_FORWARD = "fast_forward"  # Fast-forward when possible


class ConflictType(Enum):
    """Types of merge conflicts"""
    # Basic conflicts
    DELETE_MODIFY = "delete_modify"   # One deleted, other modified
    MODIFY_MODIFY = "modify_modify"   # Both modified differently
    ADD_ADD = "add_add"              # Both added same path
    
    # Structural conflicts
    TYPE_CHANGE = "type_change"       # Type mismatch
    CARDINALITY = "cardinality"       # Relationship cardinality
    STRUCTURAL = "structural"         # Structure-level conflicts
    
    # Semantic conflicts
    SEMANTIC = "semantic"             # Business logic conflicts
    CONSTRAINT = "constraint"         # Constraint violations
    CIRCULAR_DEP = "circular_dependency"  # Circular references
    
    # Schema-specific
    PROPERTY_TYPE = "property_type"   # Property type changes
    REQUIRED_CHANGE = "required_change"  # Required field changes
    NAME_COLLISION = "name_collision"    # Naming conflicts


class ConflictSeverity(Enum):
    """Severity levels for conflicts"""
    INFO = 1    # Safe to auto-resolve
    WARN = 2    # Auto-resolve with warning
    ERROR = 3   # Manual resolution required
    BLOCK = 4   # Cannot proceed


@dataclass
class MergeConflict:
    """Represents a merge conflict"""
    path: str
    conflict_type: ConflictType
    severity: ConflictSeverity
    base_value: Any
    source_value: Any
    target_value: Any
    description: str
    resolution_hint: Optional[str] = None
    auto_resolvable: bool = False


@dataclass
class MergeResult(Generic[T]):
    """Result of a merge operation"""
    merged_data: Optional[T]
    conflicts: List[MergeConflict]
    warnings: List[str]
    statistics: Dict[str, Any]
    success: bool
    strategy_used: MergeStrategy
    execution_time_ms: float
    auto_resolved_count: int = 0


@dataclass
class MergeConfig:
    """Configuration for merge operations"""
    # Strategy settings
    default_strategy: MergeStrategy = MergeStrategy.AUTO_RESOLVE
    custom_resolvers: Dict[ConflictType, Callable] = field(default_factory=dict)
    
    # Conflict handling
    auto_resolve_severity: ConflictSeverity = ConflictSeverity.WARN
    strict_mode: bool = False  # Fail on any conflict
    
    # Data type specific
    merge_arrays_by_id: bool = True
    id_fields: List[str] = field(default_factory=lambda: ["id", "@id", "_id"])
    ignore_fields: Set[str] = field(default_factory=lambda: {"@timestamp", "@version"})
    system_field_prefix: str = "@"
    
    # Schema-specific
    enable_type_widening: bool = True  # e.g., int → float
    enable_cardinality_relaxation: bool = True
    
    # Performance
    enable_caching: bool = True
    parallel_processing: bool = True
    
    # Validation
    enable_post_merge_validation: bool = True
    validators: List[Callable] = field(default_factory=list)
    
    @classmethod
    def strict(cls) -> "MergeConfig":
        """Strict configuration - no auto-resolution"""
        return cls(
            default_strategy=MergeStrategy.MANUAL,
            strict_mode=True,
            auto_resolve_severity=ConflictSeverity.BLOCK
        )
    
    @classmethod
    def lenient(cls) -> "MergeConfig":
        """Lenient configuration - maximize auto-resolution"""
        return cls(
            default_strategy=MergeStrategy.AUTO_RESOLVE,
            auto_resolve_severity=ConflictSeverity.ERROR,
            enable_type_widening=True,
            enable_cardinality_relaxation=True
        )
    
    @classmethod
    def schema_merge(cls) -> "MergeConfig":
        """Configuration optimized for schema merging"""
        return cls(
            merge_arrays_by_id=True,
            id_fields=["@id", "name"],
            ignore_fields={"@timestamp", "@version", "_rev"},
            enable_type_widening=True,
            enable_cardinality_relaxation=True
        )


class MergeAlgorithm(ABC):
    """Base interface for merge algorithms"""
    
    @abstractmethod
    async def merge(
        self,
        base: T,
        source: T,
        target: T,
        config: Optional[MergeConfig] = None
    ) -> MergeResult[T]:
        """Perform three-way merge"""
        pass


class UnifiedThreeWayMerge(Generic[T], MergeAlgorithm):
    """
    Unified three-way merge implementation
    Combines best features from all existing implementations
    """
    
    def __init__(self, config: Optional[MergeConfig] = None):
        self.config = config or MergeConfig()
        self._diff_cache = {} if config.enable_caching else None
        self._resolution_history = []
    
    async def merge(
        self,
        base: T,
        source: T,
        target: T,
        config: Optional[MergeConfig] = None
    ) -> MergeResult[T]:
        """
        Perform three-way merge
        
        Args:
            base: Common ancestor version
            source: Source branch version (ours)
            target: Target branch version (theirs)
            config: Optional config override
            
        Returns:
            MergeResult with merged data and conflicts
        """
        start_time = asyncio.get_event_loop().time()
        config = config or self.config
        
        # Fast-forward check
        if await self._can_fast_forward(base, source, target):
            return self._fast_forward_result(target, start_time)
        
        # Generate diffs
        source_changes = await self._diff(base, source)
        target_changes = await self._diff(base, target)
        
        # Detect conflicts
        conflicts = await self._detect_conflicts(
            base, source, target,
            source_changes, target_changes
        )
        
        # Apply merge strategy
        merged_data, resolved_conflicts = await self._apply_strategy(
            base, source, target,
            conflicts, config
        )
        
        # Post-merge validation
        if config.enable_post_merge_validation and merged_data:
            validation_warnings = await self._validate_merge(merged_data, config)
        else:
            validation_warnings = []
        
        # Calculate statistics
        execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
        statistics = self._calculate_statistics(
            source_changes, target_changes,
            conflicts, resolved_conflicts
        )
        
        return MergeResult(
            merged_data=merged_data,
            conflicts=[c for c in conflicts if c not in resolved_conflicts],
            warnings=validation_warnings,
            statistics=statistics,
            success=len([c for c in conflicts if c not in resolved_conflicts]) == 0,
            strategy_used=config.default_strategy,
            execution_time_ms=execution_time,
            auto_resolved_count=len(resolved_conflicts)
        )
    
    async def _can_fast_forward(self, base: T, source: T, target: T) -> bool:
        """Check if fast-forward merge is possible"""
        # Fast-forward if source hasn't changed from base
        if await self._deep_equal(base, source):
            return True
        # Fast-forward if target hasn't changed from base
        if await self._deep_equal(base, target):
            return False
        return False
    
    def _fast_forward_result(self, data: T, start_time: float) -> MergeResult[T]:
        """Create fast-forward merge result"""
        execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
        return MergeResult(
            merged_data=data,
            conflicts=[],
            warnings=[],
            statistics={"fast_forward": True},
            success=True,
            strategy_used=MergeStrategy.FAST_FORWARD,
            execution_time_ms=execution_time
        )
    
    async def _diff(self, old: Any, new: Any, path: str = "") -> Dict[str, Any]:
        """Generate diff between two versions"""
        if self._diff_cache and (old, new, path) in self._diff_cache:
            return self._diff_cache[(old, new, path)]
        
        changes = {}
        
        if type(old) != type(new):
            changes[path] = {
                "type": "type_change",
                "old": old,
                "new": new
            }
        elif isinstance(old, dict):
            # Handle dictionaries
            all_keys = set(old.keys()) | set(new.keys())
            for key in all_keys:
                if self._should_ignore_field(key):
                    continue
                    
                sub_path = f"{path}.{key}" if path else key
                
                if key not in old:
                    changes[sub_path] = {"type": "add", "value": new[key]}
                elif key not in new:
                    changes[sub_path] = {"type": "delete", "value": old[key]}
                else:
                    sub_changes = await self._diff(old[key], new[key], sub_path)
                    changes.update(sub_changes)
                    
        elif isinstance(old, list):
            # Handle arrays
            if self.config.merge_arrays_by_id:
                changes.update(await self._diff_arrays_by_id(old, new, path))
            else:
                changes.update(await self._diff_arrays_by_index(old, new, path))
        else:
            # Handle primitives
            if old != new:
                changes[path] = {
                    "type": "modify",
                    "old": old,
                    "new": new
                }
        
        if self._diff_cache:
            self._diff_cache[(old, new, path)] = changes
        
        return changes
    
    async def _diff_arrays_by_id(
        self,
        old_array: List[Any],
        new_array: List[Any],
        path: str
    ) -> Dict[str, Any]:
        """Diff arrays using ID fields"""
        changes = {}
        
        # Build ID maps
        old_map = {}
        new_map = {}
        
        for item in old_array:
            if isinstance(item, dict):
                item_id = self._get_item_id(item)
                if item_id:
                    old_map[item_id] = item
        
        for item in new_array:
            if isinstance(item, dict):
                item_id = self._get_item_id(item)
                if item_id:
                    new_map[item_id] = item
        
        # Compare by ID
        all_ids = set(old_map.keys()) | set(new_map.keys())
        
        for item_id in all_ids:
            sub_path = f"{path}[id={item_id}]"
            
            if item_id not in old_map:
                changes[sub_path] = {"type": "add", "value": new_map[item_id]}
            elif item_id not in new_map:
                changes[sub_path] = {"type": "delete", "value": old_map[item_id]}
            else:
                sub_changes = await self._diff(
                    old_map[item_id],
                    new_map[item_id],
                    sub_path
                )
                changes.update(sub_changes)
        
        return changes
    
    async def _diff_arrays_by_index(
        self,
        old_array: List[Any],
        new_array: List[Any],
        path: str
    ) -> Dict[str, Any]:
        """Diff arrays by index position"""
        changes = {}
        max_len = max(len(old_array), len(new_array))
        
        for i in range(max_len):
            sub_path = f"{path}[{i}]"
            
            if i >= len(old_array):
                changes[sub_path] = {"type": "add", "value": new_array[i]}
            elif i >= len(new_array):
                changes[sub_path] = {"type": "delete", "value": old_array[i]}
            else:
                sub_changes = await self._diff(old_array[i], new_array[i], sub_path)
                changes.update(sub_changes)
        
        return changes
    
    async def _detect_conflicts(
        self,
        base: Any,
        source: Any,
        target: Any,
        source_changes: Dict[str, Any],
        target_changes: Dict[str, Any]
    ) -> List[MergeConflict]:
        """Detect conflicts between source and target changes"""
        conflicts = []
        
        # Find paths changed in both branches
        common_paths = set(source_changes.keys()) & set(target_changes.keys())
        
        for path in common_paths:
            source_change = source_changes[path]
            target_change = target_changes[path]
            
            conflict = await self._analyze_conflict(
                path, base, source, target,
                source_change, target_change
            )
            
            if conflict:
                conflicts.append(conflict)
        
        # Check for semantic conflicts
        semantic_conflicts = await self._detect_semantic_conflicts(
            base, source, target, conflicts
        )
        conflicts.extend(semantic_conflicts)
        
        return conflicts
    
    async def _analyze_conflict(
        self,
        path: str,
        base: Any,
        source: Any,
        target: Any,
        source_change: Dict[str, Any],
        target_change: Dict[str, Any]
    ) -> Optional[MergeConflict]:
        """Analyze a specific conflict"""
        source_type = source_change["type"]
        target_type = target_change["type"]
        
        # Determine conflict type
        if source_type == "delete" and target_type == "modify":
            conflict_type = ConflictType.DELETE_MODIFY
            severity = ConflictSeverity.ERROR
        elif source_type == "modify" and target_type == "delete":
            conflict_type = ConflictType.DELETE_MODIFY
            severity = ConflictSeverity.ERROR
        elif source_type == "modify" and target_type == "modify":
            # Check if modifications are identical
            if source_change.get("new") == target_change.get("new"):
                return None  # Same change, no conflict
            conflict_type = ConflictType.MODIFY_MODIFY
            severity = await self._assess_modify_severity(
                path, source_change, target_change
            )
        elif source_type == "add" and target_type == "add":
            # Check if additions are identical
            if source_change.get("value") == target_change.get("value"):
                return None  # Same addition, no conflict
            conflict_type = ConflictType.ADD_ADD
            severity = ConflictSeverity.WARN
        else:
            return None
        
        # Get actual values
        base_value = self._get_value_at_path(base, path)
        source_value = self._get_value_at_path(source, path)
        target_value = self._get_value_at_path(target, path)
        
        return MergeConflict(
            path=path,
            conflict_type=conflict_type,
            severity=severity,
            base_value=base_value,
            source_value=source_value,
            target_value=target_value,
            description=f"{conflict_type.value} conflict at {path}",
            auto_resolvable=severity.value <= self.config.auto_resolve_severity.value
        )
    
    async def _assess_modify_severity(
        self,
        path: str,
        source_change: Dict[str, Any],
        target_change: Dict[str, Any]
    ) -> ConflictSeverity:
        """Assess severity of modification conflict"""
        # Check for type changes
        source_old_type = type(source_change.get("old"))
        source_new_type = type(source_change.get("new"))
        target_old_type = type(target_change.get("old"))
        target_new_type = type(target_change.get("new"))
        
        if source_new_type != target_new_type:
            # Type conflict
            if self._can_widen_type(source_new_type, target_new_type):
                return ConflictSeverity.WARN
            return ConflictSeverity.ERROR
        
        # Check for semantic fields
        if any(field in path for field in ["type", "required", "unique", "cardinality"]):
            return ConflictSeverity.ERROR
        
        return ConflictSeverity.WARN
    
    async def _detect_semantic_conflicts(
        self,
        base: Any,
        source: Any,
        target: Any,
        existing_conflicts: List[MergeConflict]
    ) -> List[MergeConflict]:
        """Detect higher-level semantic conflicts"""
        semantic_conflicts = []
        
        # Example: Circular dependency detection
        if isinstance(source, dict) and isinstance(target, dict):
            source_deps = self._extract_dependencies(source)
            target_deps = self._extract_dependencies(target)
            
            if self._has_circular_dependency(source_deps) or \
               self._has_circular_dependency(target_deps):
                semantic_conflicts.append(MergeConflict(
                    path="",
                    conflict_type=ConflictType.CIRCULAR_DEP,
                    severity=ConflictSeverity.BLOCK,
                    base_value=None,
                    source_value=source_deps,
                    target_value=target_deps,
                    description="Circular dependency detected",
                    auto_resolvable=False
                ))
        
        return semantic_conflicts
    
    async def _apply_strategy(
        self,
        base: T,
        source: T,
        target: T,
        conflicts: List[MergeConflict],
        config: MergeConfig
    ) -> Tuple[Optional[T], List[MergeConflict]]:
        """Apply merge strategy to resolve conflicts"""
        
        if config.strict_mode and conflicts:
            return None, []
        
        if config.default_strategy == MergeStrategy.OURS:
            return source, conflicts
        elif config.default_strategy == MergeStrategy.THEIRS:
            return target, conflicts
        elif config.default_strategy == MergeStrategy.MANUAL:
            return None, []
        
        # AUTO_RESOLVE strategy
        merged = await self._deep_copy(target)
        resolved_conflicts = []
        
        for conflict in conflicts:
            if conflict.auto_resolvable:
                resolution = await self._auto_resolve_conflict(
                    conflict, merged, config
                )
                if resolution:
                    resolved_conflicts.append(conflict)
                    self._resolution_history.append({
                        "conflict": conflict,
                        "resolution": resolution,
                        "timestamp": datetime.utcnow()
                    })
        
        return merged, resolved_conflicts
    
    async def _auto_resolve_conflict(
        self,
        conflict: MergeConflict,
        merged_data: Any,
        config: MergeConfig
    ) -> Optional[str]:
        """Automatically resolve a conflict"""
        
        # Check for custom resolver
        if conflict.conflict_type in config.custom_resolvers:
            resolver = config.custom_resolvers[conflict.conflict_type]
            return await resolver(conflict, merged_data)
        
        # Built-in resolution strategies
        if conflict.conflict_type == ConflictType.MODIFY_MODIFY:
            # Type widening
            if config.enable_type_widening:
                source_type = type(conflict.source_value)
                target_type = type(conflict.target_value)
                
                if self._can_widen_type(source_type, target_type):
                    # Use the wider type
                    wider_value = self._get_wider_value(
                        conflict.source_value,
                        conflict.target_value
                    )
                    self._set_value_at_path(merged_data, conflict.path, wider_value)
                    return f"Widened type to accommodate both values"
        
        elif conflict.conflict_type == ConflictType.ADD_ADD:
            # For additions, prefer the more complete version
            if self._is_more_complete(conflict.source_value, conflict.target_value):
                self._set_value_at_path(merged_data, conflict.path, conflict.source_value)
                return "Used source version (more complete)"
            else:
                self._set_value_at_path(merged_data, conflict.path, conflict.target_value)
                return "Used target version (more complete)"
        
        return None
    
    async def _validate_merge(
        self,
        merged_data: T,
        config: MergeConfig
    ) -> List[str]:
        """Validate merged result"""
        warnings = []
        
        for validator in config.validators:
            try:
                if asyncio.iscoroutinefunction(validator):
                    result = await validator(merged_data)
                else:
                    result = validator(merged_data)
                
                if isinstance(result, str):
                    warnings.append(result)
                elif isinstance(result, list):
                    warnings.extend(result)
            except Exception as e:
                warnings.append(f"Validation error: {str(e)}")
        
        return warnings
    
    def _calculate_statistics(
        self,
        source_changes: Dict[str, Any],
        target_changes: Dict[str, Any],
        conflicts: List[MergeConflict],
        resolved_conflicts: List[MergeConflict]
    ) -> Dict[str, Any]:
        """Calculate merge statistics"""
        return {
            "source_changes": len(source_changes),
            "target_changes": len(target_changes),
            "total_conflicts": len(conflicts),
            "auto_resolved": len(resolved_conflicts),
            "manual_required": len(conflicts) - len(resolved_conflicts),
            "conflict_types": {
                ct.value: sum(1 for c in conflicts if c.conflict_type == ct)
                for ct in ConflictType
            },
            "severity_distribution": {
                sev.name: sum(1 for c in conflicts if c.severity == sev)
                for sev in ConflictSeverity
            }
        }
    
    # Helper methods
    def _should_ignore_field(self, field: str) -> bool:
        """Check if field should be ignored"""
        return field in self.config.ignore_fields or \
               field.startswith(self.config.system_field_prefix)
    
    def _get_item_id(self, item: Dict[str, Any]) -> Optional[str]:
        """Get ID from dictionary item"""
        for id_field in self.config.id_fields:
            if id_field in item:
                return str(item[id_field])
        return None
    
    def _get_value_at_path(self, data: Any, path: str) -> Any:
        """Get value at specified path"""
        if not path:
            return data
        
        parts = path.split(".")
        current = data
        
        for part in parts:
            if "[" in part and "]" in part:
                # Handle array notation
                field, index = part.split("[")
                index = index.rstrip("]")
                
                if field:
                    current = current.get(field, {}) if isinstance(current, dict) else None
                
                if current and isinstance(current, list):
                    if index.startswith("id="):
                        # ID-based access
                        target_id = index[3:]
                        for item in current:
                            if self._get_item_id(item) == target_id:
                                current = item
                                break
                        else:
                            return None
                    else:
                        # Index-based access
                        idx = int(index)
                        current = current[idx] if idx < len(current) else None
            else:
                # Regular field access
                current = current.get(part) if isinstance(current, dict) else None
            
            if current is None:
                break
        
        return current
    
    def _set_value_at_path(self, data: Any, path: str, value: Any) -> None:
        """Set value at specified path"""
        if not path:
            return
        
        parts = path.split(".")
        current = data
        
        for i, part in enumerate(parts[:-1]):
            if "[" in part and "]" in part:
                # Handle array notation
                field, index = part.split("[")
                index = index.rstrip("]")
                
                if field and field not in current:
                    current[field] = []
                
                if field:
                    current = current[field]
                
                # Handle array access...
            else:
                if part not in current:
                    current[part] = {}
                current = current[part]
        
        # Set the final value
        final_key = parts[-1]
        if "[" in final_key and "]" in final_key:
            # Handle array assignment...
            pass
        else:
            current[final_key] = value
    
    def _can_widen_type(self, type1: type, type2: type) -> bool:
        """Check if types can be widened"""
        widening_rules = {
            (int, float): True,
            (str, str): True,  # string to text
            (bool, int): True,
            (type(None), Any): True
        }
        return (type1, type2) in widening_rules or (type2, type1) in widening_rules
    
    def _get_wider_value(self, value1: Any, value2: Any) -> Any:
        """Get the wider of two values"""
        if type(value1) == int and type(value2) == float:
            return float(value1)
        elif type(value1) == float and type(value2) == int:
            return value1
        # Add more widening logic as needed
        return value2  # Default to target
    
    def _is_more_complete(self, value1: Any, value2: Any) -> bool:
        """Check which value is more complete"""
        if isinstance(value1, dict) and isinstance(value2, dict):
            return len(value1) > len(value2)
        elif isinstance(value1, list) and isinstance(value2, list):
            return len(value1) > len(value2)
        elif isinstance(value1, str) and isinstance(value2, str):
            return len(value1) > len(value2)
        return False
    
    def _extract_dependencies(self, data: Dict[str, Any]) -> Dict[str, Set[str]]:
        """Extract dependencies from data structure"""
        # Simplified - would need domain-specific logic
        return {}
    
    def _has_circular_dependency(self, dependencies: Dict[str, Set[str]]) -> bool:
        """Check for circular dependencies using DFS"""
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in dependencies.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node in dependencies:
            if node not in visited:
                if has_cycle(node):
                    return True
        
        return False
    
    async def _deep_equal(self, obj1: Any, obj2: Any) -> bool:
        """Deep equality comparison"""
        if type(obj1) != type(obj2):
            return False
        
        if isinstance(obj1, dict):
            if set(obj1.keys()) != set(obj2.keys()):
                return False
            for key in obj1:
                if not await self._deep_equal(obj1[key], obj2[key]):
                    return False
            return True
        elif isinstance(obj1, list):
            if len(obj1) != len(obj2):
                return False
            for i in range(len(obj1)):
                if not await self._deep_equal(obj1[i], obj2[i]):
                    return False
            return True
        else:
            return obj1 == obj2
    
    async def _deep_copy(self, obj: T) -> T:
        """Deep copy an object"""
        import copy
        return copy.deepcopy(obj)


# Convenience functions
async def merge_json(
    base: str,
    source: str,
    target: str,
    config: Optional[MergeConfig] = None
) -> MergeResult[Dict[str, Any]]:
    """Merge JSON strings"""
    merger = UnifiedThreeWayMerge[Dict[str, Any]](config)
    
    base_data = json.loads(base)
    source_data = json.loads(source)
    target_data = json.loads(target)
    
    return await merger.merge(base_data, source_data, target_data)


async def merge_schemas(
    base: Dict[str, Any],
    source: Dict[str, Any],
    target: Dict[str, Any]
) -> MergeResult[Dict[str, Any]]:
    """Merge schema definitions with schema-specific config"""
    config = MergeConfig.schema_merge()
    merger = UnifiedThreeWayMerge[Dict[str, Any]](config)
    
    return await merger.merge(base, source, target)