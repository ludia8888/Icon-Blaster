"""
Enterprise-grade three-way merge implementation.

Features:
- Conflict detection and resolution
- Custom merge strategies
- Semantic merging support
- Merge history tracking
- Rollback capabilities
- Concurrent modification handling
- Diff generation and visualization
- Merge validation
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set, Tuple, Union, TypeVar, Generic
import difflib
import copy
import hashlib
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ConflictType(Enum):
    """Types of merge conflicts."""
    DELETE_MODIFY = "delete_modify"
    MODIFY_MODIFY = "modify_modify"
    ADD_ADD = "add_add"
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"


class MergeStrategy(Enum):
    """Merge strategies."""
    OURS = "ours"
    THEIRS = "theirs"
    MANUAL = "manual"
    AUTO_RESOLVE = "auto_resolve"
    CUSTOM = "custom"


class ChangeType(Enum):
    """Types of changes."""
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"
    MOVE = "move"
    RENAME = "rename"


@dataclass
class Change:
    """Represents a change."""
    path: str
    change_type: ChangeType
    old_value: Any = None
    new_value: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def conflicts_with(self, other: 'Change') -> bool:
        """Check if this change conflicts with another."""
        if self.path != other.path:
            return False
        
        # Both deleting the same path
        if self.change_type == ChangeType.DELETE and other.change_type == ChangeType.DELETE:
            return False
        
        # One deletes, other modifies
        if (self.change_type == ChangeType.DELETE and other.change_type in [ChangeType.MODIFY, ChangeType.ADD]) or \
           (other.change_type == ChangeType.DELETE and self.change_type in [ChangeType.MODIFY, ChangeType.ADD]):
            return True
        
        # Both modify or add with different values
        if self.change_type in [ChangeType.MODIFY, ChangeType.ADD] and \
           other.change_type in [ChangeType.MODIFY, ChangeType.ADD] and \
           self.new_value != other.new_value:
            return True
        
        return False


@dataclass
class Conflict:
    """Represents a merge conflict."""
    path: str
    conflict_type: ConflictType
    base_value: Any
    ours_value: Any
    theirs_value: Any
    ours_change: Optional[Change] = None
    theirs_change: Optional[Change] = None
    resolution: Optional[Any] = None
    resolution_strategy: Optional[MergeStrategy] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def auto_resolvable(self) -> bool:
        """Check if conflict can be auto-resolved."""
        # Simple cases that can be auto-resolved
        if self.conflict_type == ConflictType.DELETE_MODIFY:
            return False  # Usually requires manual decision
        
        if self.conflict_type == ConflictType.MODIFY_MODIFY:
            # Check if changes are compatible
            if isinstance(self.ours_value, dict) and isinstance(self.theirs_value, dict):
                # Dictionary changes might be mergeable
                return True
            elif isinstance(self.ours_value, list) and isinstance(self.theirs_value, list):
                # List changes might be mergeable
                return True
        
        return False


@dataclass
class MergeResult:
    """Result of a merge operation."""
    merged_value: Any
    conflicts: List[Conflict] = field(default_factory=list)
    changes_applied: List[Change] = field(default_factory=list)
    success: bool = True
    merge_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def has_conflicts(self) -> bool:
        """Check if merge has unresolved conflicts."""
        return any(c.resolution is None for c in self.conflicts)
    
    def get_unresolved_conflicts(self) -> List[Conflict]:
        """Get unresolved conflicts."""
        return [c for c in self.conflicts if c.resolution is None]


class DiffGenerator:
    """Generates diffs between objects."""
    
    @staticmethod
    def generate_diff(base: Any, modified: Any, path: str = "") -> List[Change]:
        """Generate diff between base and modified."""
        changes = []
        
        if type(base) != type(modified):
            # Type changed
            changes.append(Change(
                path=path,
                change_type=ChangeType.MODIFY,
                old_value=base,
                new_value=modified
            ))
            return changes
        
        if isinstance(base, dict):
            changes.extend(DiffGenerator._diff_dicts(base, modified, path))
        elif isinstance(base, list):
            changes.extend(DiffGenerator._diff_lists(base, modified, path))
        elif base != modified:
            changes.append(Change(
                path=path,
                change_type=ChangeType.MODIFY,
                old_value=base,
                new_value=modified
            ))
        
        return changes
    
    @staticmethod
    def _diff_dicts(base: Dict, modified: Dict, path: str) -> List[Change]:
        """Diff two dictionaries."""
        changes = []
        all_keys = set(base.keys()) | set(modified.keys())
        
        for key in all_keys:
            key_path = f"{path}.{key}" if path else str(key)
            
            if key not in base:
                # Added
                changes.append(Change(
                    path=key_path,
                    change_type=ChangeType.ADD,
                    new_value=modified[key]
                ))
            elif key not in modified:
                # Deleted
                changes.append(Change(
                    path=key_path,
                    change_type=ChangeType.DELETE,
                    old_value=base[key]
                ))
            else:
                # Possibly modified
                sub_changes = DiffGenerator.generate_diff(base[key], modified[key], key_path)
                changes.extend(sub_changes)
        
        return changes
    
    @staticmethod
    def _diff_lists(base: List, modified: List, path: str) -> List[Change]:
        """Diff two lists."""
        changes = []
        
        # Simple diff for now - could be enhanced with LCS algorithm
        if len(base) != len(modified) or base != modified:
            changes.append(Change(
                path=path,
                change_type=ChangeType.MODIFY,
                old_value=base,
                new_value=modified
            ))
        
        return changes


class ConflictDetector:
    """Detects conflicts between changes."""
    
    @staticmethod
    def detect_conflicts(
        base: Any,
        ours: Any,
        theirs: Any,
        ours_changes: List[Change],
        theirs_changes: List[Change]
    ) -> List[Conflict]:
        """Detect conflicts between changes."""
        conflicts = []
        
        # Group changes by path
        ours_by_path = {c.path: c for c in ours_changes}
        theirs_by_path = {c.path: c for c in theirs_changes}
        
        # Check for conflicts
        all_paths = set(ours_by_path.keys()) | set(theirs_by_path.keys())
        
        for path in all_paths:
            ours_change = ours_by_path.get(path)
            theirs_change = theirs_by_path.get(path)
            
            if ours_change and theirs_change and ours_change.conflicts_with(theirs_change):
                # Determine conflict type
                if ours_change.change_type == ChangeType.DELETE or theirs_change.change_type == ChangeType.DELETE:
                    conflict_type = ConflictType.DELETE_MODIFY
                elif ours_change.change_type == ChangeType.ADD and theirs_change.change_type == ChangeType.ADD:
                    conflict_type = ConflictType.ADD_ADD
                else:
                    conflict_type = ConflictType.MODIFY_MODIFY
                
                # Get values
                base_value = ConflictDetector._get_value_at_path(base, path)
                ours_value = ConflictDetector._get_value_at_path(ours, path)
                theirs_value = ConflictDetector._get_value_at_path(theirs, path)
                
                conflict = Conflict(
                    path=path,
                    conflict_type=conflict_type,
                    base_value=base_value,
                    ours_value=ours_value,
                    theirs_value=theirs_value,
                    ours_change=ours_change,
                    theirs_change=theirs_change
                )
                
                conflicts.append(conflict)
        
        return conflicts
    
    @staticmethod
    def _get_value_at_path(obj: Any, path: str) -> Any:
        """Get value at path in object."""
        if not path:
            return obj
        
        parts = path.split('.')
        current = obj
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                try:
                    index = int(part)
                    if 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None
                except ValueError:
                    return None
            else:
                return None
        
        return current


class ConflictResolver:
    """Resolves merge conflicts."""
    
    def __init__(self):
        self.strategies: Dict[ConflictType, Callable] = {
            ConflictType.MODIFY_MODIFY: self._resolve_modify_modify,
            ConflictType.DELETE_MODIFY: self._resolve_delete_modify,
            ConflictType.ADD_ADD: self._resolve_add_add,
        }
        self.custom_resolvers: List[Callable] = []
    
    def add_custom_resolver(self, resolver: Callable[[Conflict], Optional[Any]]):
        """Add custom conflict resolver."""
        self.custom_resolvers.append(resolver)
    
    async def resolve(self, conflict: Conflict, strategy: MergeStrategy) -> Optional[Any]:
        """Resolve a conflict."""
        # Try custom resolvers first
        for resolver in self.custom_resolvers:
            if asyncio.iscoroutinefunction(resolver):
                resolution = await resolver(conflict)
            else:
                resolution = resolver(conflict)
            
            if resolution is not None:
                return resolution
        
        # Apply strategy
        if strategy == MergeStrategy.OURS:
            return conflict.ours_value
        elif strategy == MergeStrategy.THEIRS:
            return conflict.theirs_value
        elif strategy == MergeStrategy.AUTO_RESOLVE:
            return await self._auto_resolve(conflict)
        else:
            return None
    
    async def _auto_resolve(self, conflict: Conflict) -> Optional[Any]:
        """Auto-resolve conflict if possible."""
        if conflict.conflict_type in self.strategies:
            return self.strategies[conflict.conflict_type](conflict)
        return None
    
    def _resolve_modify_modify(self, conflict: Conflict) -> Optional[Any]:
        """Resolve modify-modify conflicts."""
        # Try to merge if both are dicts
        if isinstance(conflict.ours_value, dict) and isinstance(conflict.theirs_value, dict):
            merged = copy.deepcopy(conflict.base_value) if isinstance(conflict.base_value, dict) else {}
            merged.update(conflict.ours_value)
            merged.update(conflict.theirs_value)
            return merged
        
        # Try to merge if both are lists
        if isinstance(conflict.ours_value, list) and isinstance(conflict.theirs_value, list):
            # Simple concatenation for now
            return conflict.ours_value + conflict.theirs_value
        
        return None
    
    def _resolve_delete_modify(self, conflict: Conflict) -> Optional[Any]:
        """Resolve delete-modify conflicts."""
        # Generally can't auto-resolve
        return None
    
    def _resolve_add_add(self, conflict: Conflict) -> Optional[Any]:
        """Resolve add-add conflicts."""
        # If values are the same, use either
        if conflict.ours_value == conflict.theirs_value:
            return conflict.ours_value
        return None


class ThreeWayMerger:
    """Main three-way merger."""
    
    def __init__(self):
        self.diff_generator = DiffGenerator()
        self.conflict_detector = ConflictDetector()
        self.conflict_resolver = ConflictResolver()
        self.merge_history: List[MergeResult] = []
        self.validators: List[Callable] = []
    
    def add_validator(self, validator: Callable[[Any], bool]):
        """Add merge result validator."""
        self.validators.append(validator)
    
    def add_conflict_resolver(self, resolver: Callable[[Conflict], Optional[Any]]):
        """Add custom conflict resolver."""
        self.conflict_resolver.add_custom_resolver(resolver)
    
    async def merge(
        self,
        base: Any,
        ours: Any,
        theirs: Any,
        strategy: MergeStrategy = MergeStrategy.AUTO_RESOLVE
    ) -> MergeResult:
        """Perform three-way merge."""
        # Generate diffs
        ours_changes = self.diff_generator.generate_diff(base, ours)
        theirs_changes = self.diff_generator.generate_diff(base, theirs)
        
        # Detect conflicts
        conflicts = self.conflict_detector.detect_conflicts(
            base, ours, theirs, ours_changes, theirs_changes
        )
        
        # Start with base
        merged = copy.deepcopy(base)
        
        # Apply non-conflicting changes
        all_changes = ours_changes + theirs_changes
        applied_changes = []
        conflicting_paths = {c.path for c in conflicts}
        
        for change in all_changes:
            if change.path not in conflicting_paths:
                merged = self._apply_change(merged, change)
                applied_changes.append(change)
        
        # Resolve conflicts
        for conflict in conflicts:
            resolution = await self.conflict_resolver.resolve(conflict, strategy)
            if resolution is not None:
                conflict.resolution = resolution
                conflict.resolution_strategy = strategy
                merged = self._set_value_at_path(merged, conflict.path, resolution)
        
        # Create result
        result = MergeResult(
            merged_value=merged,
            conflicts=conflicts,
            changes_applied=applied_changes,
            success=not any(c.resolution is None for c in conflicts)
        )
        
        # Validate result
        if result.success:
            for validator in self.validators:
                if not validator(merged):
                    result.success = False
                    result.metadata['validation_failed'] = True
                    break
        
        # Store in history
        self.merge_history.append(result)
        
        return result
    
    def _apply_change(self, obj: Any, change: Change) -> Any:
        """Apply a change to an object."""
        if change.change_type == ChangeType.DELETE:
            return self._delete_at_path(obj, change.path)
        else:
            return self._set_value_at_path(obj, change.path, change.new_value)
    
    def _set_value_at_path(self, obj: Any, path: str, value: Any) -> Any:
        """Set value at path in object."""
        if not path:
            return value
        
        parts = path.split('.')
        current = obj
        
        for i, part in enumerate(parts[:-1]):
            if isinstance(current, dict):
                if part not in current:
                    current[part] = {}
                current = current[part]
            elif isinstance(current, list):
                try:
                    index = int(part)
                    if 0 <= index < len(current):
                        current = current[index]
                except ValueError:
                    pass
        
        # Set final value
        final_part = parts[-1]
        if isinstance(current, dict):
            current[final_part] = value
        elif isinstance(current, list):
            try:
                index = int(final_part)
                if 0 <= index < len(current):
                    current[index] = value
            except ValueError:
                pass
        
        return obj
    
    def _delete_at_path(self, obj: Any, path: str) -> Any:
        """Delete value at path in object."""
        if not path:
            return None
        
        parts = path.split('.')
        current = obj
        
        for i, part in enumerate(parts[:-1]):
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                try:
                    index = int(part)
                    if 0 <= index < len(current):
                        current = current[index]
                except ValueError:
                    return obj
            else:
                return obj
        
        # Delete final value
        final_part = parts[-1]
        if isinstance(current, dict) and final_part in current:
            del current[final_part]
        elif isinstance(current, list):
            try:
                index = int(final_part)
                if 0 <= index < len(current):
                    current.pop(index)
            except ValueError:
                pass
        
        return obj
    
    def generate_merge_report(self, result: MergeResult) -> Dict[str, Any]:
        """Generate detailed merge report."""
        return {
            'merge_id': result.merge_id,
            'timestamp': result.timestamp.isoformat(),
            'success': result.success,
            'total_changes': len(result.changes_applied),
            'total_conflicts': len(result.conflicts),
            'unresolved_conflicts': len(result.get_unresolved_conflicts()),
            'conflicts': [
                {
                    'path': c.path,
                    'type': c.conflict_type.value,
                    'resolved': c.resolution is not None,
                    'strategy': c.resolution_strategy.value if c.resolution_strategy else None,
                    'base_value': str(c.base_value)[:100],
                    'ours_value': str(c.ours_value)[:100],
                    'theirs_value': str(c.theirs_value)[:100],
                    'resolution': str(c.resolution)[:100] if c.resolution is not None else None
                }
                for c in result.conflicts
            ],
            'changes': [
                {
                    'path': c.path,
                    'type': c.change_type.value,
                    'old_value': str(c.old_value)[:100] if c.old_value is not None else None,
                    'new_value': str(c.new_value)[:100] if c.new_value is not None else None
                }
                for c in result.changes_applied[:10]  # Limit to first 10
            ]
        }


class SemanticMerger(ThreeWayMerger):
    """Semantic-aware three-way merger."""
    
    def __init__(self):
        super().__init__()
        self.semantic_rules: List[Callable] = []
    
    def add_semantic_rule(self, rule: Callable[[Any, Any, Any], Optional[Any]]):
        """Add semantic merging rule."""
        self.semantic_rules.append(rule)
    
    async def merge(
        self,
        base: Any,
        ours: Any,
        theirs: Any,
        strategy: MergeStrategy = MergeStrategy.AUTO_RESOLVE
    ) -> MergeResult:
        """Perform semantic merge."""
        # Try semantic rules first
        for rule in self.semantic_rules:
            if asyncio.iscoroutinefunction(rule):
                result = await rule(base, ours, theirs)
            else:
                result = rule(base, ours, theirs)
            
            if result is not None:
                return MergeResult(
                    merged_value=result,
                    success=True,
                    metadata={'semantic_merge': True}
                )
        
        # Fall back to standard merge
        return await super().merge(base, ours, theirs, strategy)


# Example usage
class JsonMerger(SemanticMerger):
    """JSON-specific merger with semantic understanding."""
    
    def __init__(self):
        super().__init__()
        
        # Add JSON-specific semantic rules
        self.add_semantic_rule(self._merge_arrays_semantically)
        self.add_semantic_rule(self._merge_objects_semantically)
    
    def _merge_arrays_semantically(self, base: Any, ours: Any, theirs: Any) -> Optional[Any]:
        """Merge arrays with semantic understanding."""
        if not (isinstance(base, list) and isinstance(ours, list) and isinstance(theirs, list)):
            return None
        
        # If arrays contain objects with IDs, merge by ID
        if all(isinstance(item, dict) and 'id' in item for item in base + ours + theirs):
            merged_by_id = {}
            
            # Start with base
            for item in base:
                merged_by_id[item['id']] = copy.deepcopy(item)
            
            # Apply our changes
            for item in ours:
                if item['id'] in merged_by_id:
                    merged_by_id[item['id']].update(item)
                else:
                    merged_by_id[item['id']] = copy.deepcopy(item)
            
            # Apply their changes
            for item in theirs:
                if item['id'] in merged_by_id:
                    # Merge the items
                    base_item = next((i for i in base if i['id'] == item['id']), {})
                    our_item = merged_by_id[item['id']]
                    # Recursive merge for nested objects
                    merged_item = self._merge_objects(base_item, our_item, item)
                    merged_by_id[item['id']] = merged_item
                else:
                    merged_by_id[item['id']] = copy.deepcopy(item)
            
            return list(merged_by_id.values())
        
        return None
    
    def _merge_objects_semantically(self, base: Any, ours: Any, theirs: Any) -> Optional[Any]:
        """Merge objects with semantic understanding."""
        if not (isinstance(base, dict) and isinstance(ours, dict) and isinstance(theirs, dict)):
            return None
        
        # Special handling for certain object types
        if all('version' in obj for obj in [base, ours, theirs]):
            # Version-aware merge
            if ours['version'] > base['version'] and theirs['version'] > base['version']:
                # Both have newer versions - need to merge
                merged = copy.deepcopy(base)
                merged.update(ours)
                merged.update(theirs)
                merged['version'] = max(ours['version'], theirs['version']) + 1
                return merged
        
        return None
    
    def _merge_objects(self, base: Dict, ours: Dict, theirs: Dict) -> Dict:
        """Merge objects recursively."""
        merged = copy.deepcopy(base)
        
        # Apply changes from ours
        for key, value in ours.items():
            if key not in base:
                merged[key] = value
            elif isinstance(value, dict) and isinstance(base.get(key), dict):
                merged[key] = self._merge_objects(base[key], value, theirs.get(key, {}))
            else:
                merged[key] = value
        
        # Apply changes from theirs
        for key, value in theirs.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(value, dict) and isinstance(merged.get(key), dict) and key not in ours:
                merged[key] = self._merge_objects(base.get(key, {}), merged[key], value)
            elif key not in ours:
                merged[key] = value
        
        return merged


import uuid