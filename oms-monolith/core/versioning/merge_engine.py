"""
Merge Engine for OMS Schema Versioning

Implements high-performance merge operations with automated conflict resolution
based on the severity grades defined in MERGE_CONFLICT_RESOLUTION_SPEC.md
"""

from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import asyncio
from collections import defaultdict
import hashlib
import json

from core.schema.conflict_resolver import ConflictResolver
from models.domain import Cardinality
from utils.logger import get_logger

logger = get_logger(__name__)


class ConflictSeverity(Enum):
    """Conflict severity levels"""
    INFO = "INFO"      # Safe automatic resolution
    WARN = "WARN"      # Automatic with warnings
    ERROR = "ERROR"    # Manual resolution required
    BLOCK = "BLOCK"    # Cannot proceed


class ConflictType(Enum):
    """Types of merge conflicts"""
    PROPERTY_TYPE = "property_type_change"
    CARDINALITY = "cardinality_change"
    DELETE_MODIFY = "delete_after_modify"
    NAME_COLLISION = "name_collision"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    INTERFACE_MISMATCH = "interface_mismatch"
    CONSTRAINT_CONFLICT = "constraint_conflict"


@dataclass
class MergeConflict:
    """Represents a single merge conflict"""
    id: str
    type: ConflictType
    severity: ConflictSeverity
    entity_type: str
    entity_id: str
    branch_a_value: Any
    branch_b_value: Any
    description: str
    auto_resolvable: bool
    suggested_resolution: Optional[Dict[str, Any]] = None
    migration_impact: Optional[Dict[str, Any]] = None


@dataclass
class MergeResult:
    """Result of a merge operation"""
    status: str  # success, manual_required, blocked, failed
    merge_commit: Optional[str] = None
    conflicts: List[MergeConflict] = None
    warnings: List[str] = None
    duration_ms: float = 0
    auto_resolved: bool = False
    max_severity: Optional[ConflictSeverity] = None
    stats: Dict[str, int] = None


class MergeEngine:
    """
    High-performance merge engine for schema versioning.
    
    Handles automated conflict resolution based on severity grades
    and provides detailed conflict analysis for manual resolution.
    """
    
    def __init__(self, conflict_resolver: ConflictResolver = None):
        self.resolver = conflict_resolver or ConflictResolver()
        self.merge_cache = {}
        self.conflict_stats = defaultdict(int)
        
    async def merge_branches(
        self,
        source_branch: Dict[str, Any],
        target_branch: Dict[str, Any],
        auto_resolve: bool = True,
        dry_run: bool = False
    ) -> MergeResult:
        """
        Merge source branch into target branch.
        
        Args:
            source_branch: Source branch data
            target_branch: Target branch data
            auto_resolve: Attempt automatic conflict resolution
            dry_run: Analyze only, don't perform merge
            
        Returns:
            MergeResult with status and conflict details
        """
        start_time = datetime.utcnow()
        logger.info(f"Starting merge: {source_branch['branch_id']} -> {target_branch['branch_id']}")
        
        try:
            # Find common ancestor
            common_ancestor = await self._find_common_ancestor(source_branch, target_branch)
            
            # Detect conflicts
            conflicts = await self._detect_conflicts(
                source_branch,
                target_branch,
                common_ancestor
            )
            
            # Analyze severity
            max_severity = self._get_max_severity(conflicts)
            
            # Check if blocked
            if max_severity == ConflictSeverity.BLOCK:
                return MergeResult(
                    status="blocked",
                    conflicts=conflicts,
                    max_severity=max_severity,
                    duration_ms=self._calculate_duration(start_time)
                )
            
            # Attempt auto-resolution if enabled
            if auto_resolve and max_severity in [ConflictSeverity.INFO, ConflictSeverity.WARN]:
                resolved_conflicts, warnings = await self._auto_resolve_conflicts(conflicts)
                
                if dry_run:
                    return MergeResult(
                        status="dry_run_success",
                        conflicts=resolved_conflicts,
                        warnings=warnings,
                        auto_resolved=True,
                        max_severity=max_severity,
                        duration_ms=self._calculate_duration(start_time)
                    )
                
                # Apply merge
                merge_commit = await self._apply_merge(
                    source_branch,
                    target_branch,
                    resolved_conflicts
                )
                
                return MergeResult(
                    status="success",
                    merge_commit=merge_commit,
                    warnings=warnings,
                    auto_resolved=True,
                    max_severity=max_severity,
                    duration_ms=self._calculate_duration(start_time),
                    stats=self._get_merge_stats(resolved_conflicts)
                )
            
            # Manual resolution required
            if max_severity == ConflictSeverity.ERROR:
                return MergeResult(
                    status="manual_required",
                    conflicts=conflicts,
                    max_severity=max_severity,
                    duration_ms=self._calculate_duration(start_time)
                )
            
            # No conflicts - fast forward
            if not conflicts:
                if dry_run:
                    return MergeResult(
                        status="dry_run_success",
                        duration_ms=self._calculate_duration(start_time)
                    )
                    
                merge_commit = await self._fast_forward_merge(source_branch, target_branch)
                return MergeResult(
                    status="success",
                    merge_commit=merge_commit,
                    duration_ms=self._calculate_duration(start_time)
                )
                
        except Exception as e:
            logger.error(f"Merge failed: {e}")
            return MergeResult(
                status="failed",
                warnings=[str(e)],
                duration_ms=self._calculate_duration(start_time)
            )
    
    async def analyze_conflicts(
        self,
        source_branch: Dict[str, Any],
        target_branch: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze potential conflicts without performing merge"""
        common_ancestor = await self._find_common_ancestor(source_branch, target_branch)
        conflicts = await self._detect_conflicts(source_branch, target_branch, common_ancestor)
        
        # Group conflicts by type
        by_type = defaultdict(list)
        for conflict in conflicts:
            by_type[conflict.type.value].append(conflict)
        
        return {
            "total_conflicts": len(conflicts),
            "by_type": dict(by_type),
            "max_severity": self._get_max_severity(conflicts),
            "auto_resolvable": sum(1 for c in conflicts if c.auto_resolvable),
            "conflicts": conflicts
        }
    
    async def apply_manual_resolution(
        self,
        branch_id: str,
        resolution: Dict[str, Any]
    ) -> MergeResult:
        """Apply manual conflict resolution"""
        # Implementation for applying manual resolutions
        logger.info(f"Applying manual resolution for branch {branch_id}")
        
        # Validate resolution
        if not self._validate_resolution(resolution):
            return MergeResult(
                status="failed",
                warnings=["Invalid resolution format"]
            )
        
        # Apply resolution decisions
        # This would integrate with the actual merge process
        
        return MergeResult(
            status="success",
            merge_commit=f"merge_{branch_id}_{datetime.utcnow().timestamp()}"
        )
    
    async def _detect_conflicts(
        self,
        source: Dict[str, Any],
        target: Dict[str, Any],
        ancestor: Optional[Dict[str, Any]]
    ) -> List[MergeConflict]:
        """Detect all conflicts between branches"""
        conflicts = []
        
        # Check object type conflicts
        conflicts.extend(await self._detect_object_conflicts(source, target, ancestor))
        
        # Check property conflicts
        conflicts.extend(await self._detect_property_conflicts(source, target, ancestor))
        
        # Check link conflicts
        conflicts.extend(await self._detect_link_conflicts(source, target, ancestor))
        
        # Check constraint conflicts
        conflicts.extend(await self._detect_constraint_conflicts(source, target, ancestor))
        
        return conflicts
    
    async def _detect_object_conflicts(
        self,
        source: Dict[str, Any],
        target: Dict[str, Any],
        ancestor: Optional[Dict[str, Any]]
    ) -> List[MergeConflict]:
        """Detect conflicts in object type definitions"""
        conflicts = []
        
        source_objects = {obj["id"]: obj for obj in source.get("objects", [])}
        target_objects = {obj["id"]: obj for obj in target.get("objects", [])}
        ancestor_objects = {obj["id"]: obj for obj in ancestor.get("objects", [])} if ancestor else {}
        
        # Check for conflicting modifications
        for obj_id in set(source_objects.keys()) & set(target_objects.keys()):
            source_obj = source_objects[obj_id]
            target_obj = target_objects[obj_id]
            ancestor_obj = ancestor_objects.get(obj_id)
            
            # Both modified differently from ancestor
            if ancestor_obj and source_obj != ancestor_obj and target_obj != ancestor_obj:
                if source_obj != target_obj:
                    conflicts.append(MergeConflict(
                        id=f"obj_conflict_{obj_id}",
                        type=ConflictType.NAME_COLLISION,
                        severity=ConflictSeverity.WARN,
                        entity_type="ObjectType",
                        entity_id=obj_id,
                        branch_a_value=source_obj,
                        branch_b_value=target_obj,
                        description=f"Object {obj_id} modified in both branches",
                        auto_resolvable=True,
                        suggested_resolution={"action": "merge_properties"}
                    ))
        
        # Check delete-modify conflicts
        for obj_id in source_objects:
            if obj_id not in target_objects and obj_id in ancestor_objects:
                # Deleted in target, modified in source
                if source_objects[obj_id] != ancestor_objects[obj_id]:
                    conflicts.append(MergeConflict(
                        id=f"delete_modify_{obj_id}",
                        type=ConflictType.DELETE_MODIFY,
                        severity=ConflictSeverity.ERROR,
                        entity_type="ObjectType",
                        entity_id=obj_id,
                        branch_a_value=source_objects[obj_id],
                        branch_b_value=None,
                        description=f"Object {obj_id} deleted in target but modified in source",
                        auto_resolvable=False
                    ))
        
        return conflicts
    
    async def _detect_property_conflicts(
        self,
        source: Dict[str, Any],
        target: Dict[str, Any],
        ancestor: Optional[Dict[str, Any]]
    ) -> List[MergeConflict]:
        """Detect conflicts in property definitions"""
        conflicts = []
        
        # Group properties by object
        source_props = self._group_properties_by_object(source)
        target_props = self._group_properties_by_object(target)
        
        for obj_id in set(source_props.keys()) & set(target_props.keys()):
            for prop_name in set(source_props[obj_id].keys()) & set(target_props[obj_id].keys()):
                source_prop = source_props[obj_id][prop_name]
                target_prop = target_props[obj_id][prop_name]
                
                # Check property type conflicts
                if source_prop.get("type") != target_prop.get("type"):
                    severity = self._get_property_conflict_severity(
                        source_prop.get("type"),
                        target_prop.get("type")
                    )
                    
                    conflicts.append(MergeConflict(
                        id=f"prop_type_{obj_id}_{prop_name}",
                        type=ConflictType.PROPERTY_TYPE,
                        severity=severity,
                        entity_type="Property",
                        entity_id=f"{obj_id}.{prop_name}",
                        branch_a_value=source_prop,
                        branch_b_value=target_prop,
                        description=f"Property type conflict: {source_prop.get('type')} vs {target_prop.get('type')}",
                        auto_resolvable=severity in [ConflictSeverity.INFO, ConflictSeverity.WARN]
                    ))
        
        return conflicts
    
    async def _detect_link_conflicts(
        self,
        source: Dict[str, Any],
        target: Dict[str, Any],
        ancestor: Optional[Dict[str, Any]]
    ) -> List[MergeConflict]:
        """Detect conflicts in link type definitions"""
        conflicts = []
        
        source_links = {link["id"]: link for link in source.get("links", [])}
        target_links = {link["id"]: link for link in target.get("links", [])}
        
        for link_id in set(source_links.keys()) & set(target_links.keys()):
            source_link = source_links[link_id]
            target_link = target_links[link_id]
            
            # Check cardinality conflicts
            if source_link.get("cardinality") != target_link.get("cardinality"):
                severity, migration_impact = self._get_cardinality_conflict_severity(
                    source_link.get("cardinality"),
                    target_link.get("cardinality")
                )
                
                conflicts.append(MergeConflict(
                    id=f"cardinality_{link_id}",
                    type=ConflictType.CARDINALITY,
                    severity=severity,
                    entity_type="LinkType",
                    entity_id=link_id,
                    branch_a_value=source_link,
                    branch_b_value=target_link,
                    description=f"Cardinality conflict: {source_link.get('cardinality')} vs {target_link.get('cardinality')}",
                    auto_resolvable=severity == ConflictSeverity.INFO,
                    migration_impact=migration_impact
                ))
        
        # Check for circular dependencies
        circular = await self._detect_circular_dependencies(source_links, target_links)
        if circular:
            conflicts.append(MergeConflict(
                id="circular_dependency",
                type=ConflictType.CIRCULAR_DEPENDENCY,
                severity=ConflictSeverity.BLOCK,
                entity_type="LinkType",
                entity_id="multiple",
                branch_a_value=circular["source"],
                branch_b_value=circular["target"],
                description="Circular dependency detected",
                auto_resolvable=False
            ))
        
        return conflicts
    
    async def _detect_constraint_conflicts(
        self,
        source: Dict[str, Any],
        target: Dict[str, Any],
        ancestor: Optional[Dict[str, Any]]
    ) -> List[MergeConflict]:
        """Detect conflicts in constraints and validation rules"""
        conflicts = []
        
        # Check semantic type constraints
        # Check struct type constraints
        # Implementation depends on constraint representation
        
        return conflicts
    
    def _get_property_conflict_severity(
        self,
        type_a: str,
        type_b: str
    ) -> ConflictSeverity:
        """Determine severity of property type conflict"""
        # Based on MERGE_CONFLICT_RESOLUTION_SPEC.md matrix
        safe_conversions = {
            ("string", "text"): ConflictSeverity.INFO,
            ("integer", "long"): ConflictSeverity.INFO,
            ("float", "double"): ConflictSeverity.INFO,
        }
        
        unsafe_conversions = {
            ("string", "integer"): ConflictSeverity.ERROR,
            ("double", "integer"): ConflictSeverity.ERROR,
            ("json", "string"): ConflictSeverity.ERROR,
        }
        
        pair = (type_a, type_b)
        if pair in safe_conversions:
            return safe_conversions[pair]
        elif pair in unsafe_conversions:
            return unsafe_conversions[pair]
        elif type_a == "json" or type_b == "json":
            return ConflictSeverity.WARN
        else:
            return ConflictSeverity.ERROR
    
    def _get_cardinality_conflict_severity(
        self,
        card_a: str,
        card_b: str
    ) -> Tuple[ConflictSeverity, Dict[str, Any]]:
        """Determine severity and migration impact of cardinality conflict"""
        # Based on MERGE_CONFLICT_RESOLUTION_SPEC.md
        if card_a == card_b:
            return ConflictSeverity.INFO, None
        
        # ONE_TO_ONE -> ONE_TO_MANY: Safe
        if card_a == "ONE_TO_ONE" and card_b == "ONE_TO_MANY":
            return ConflictSeverity.INFO, {"impact": "FK remains valid"}
        
        # ONE_TO_MANY -> MANY_TO_MANY: Needs junction table
        if card_a == "ONE_TO_MANY" and card_b == "MANY_TO_MANY":
            return ConflictSeverity.WARN, {"impact": "Junction table needed"}
        
        # Narrowing conversions: Error
        if card_b == "ONE_TO_ONE" and card_a in ["ONE_TO_MANY", "MANY_TO_MANY"]:
            return ConflictSeverity.ERROR, {"impact": "Potential data loss"}
        
        return ConflictSeverity.ERROR, {"impact": "Complex migration required"}
    
    async def _detect_circular_dependencies(
        self,
        source_links: Dict[str, Any],
        target_links: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Detect circular dependencies in link structure"""
        # Build combined graph
        all_links = {**source_links, **target_links}
        graph = defaultdict(set)
        
        for link_id, link in all_links.items():
            if link.get("required"):
                graph[link["from"]].add(link["to"])
        
        # DFS to detect cycles
        def has_cycle(node, visited, rec_stack):
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph[node]:
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        visited = set()
        for node in graph:
            if node not in visited:
                if has_cycle(node, visited, set()):
                    return {
                        "source": source_links,
                        "target": target_links,
                        "cycle_detected": True
                    }
        
        return None
    
    async def _auto_resolve_conflicts(
        self,
        conflicts: List[MergeConflict]
    ) -> Tuple[List[MergeConflict], List[str]]:
        """Automatically resolve conflicts where possible"""
        resolved = []
        warnings = []
        
        for conflict in conflicts:
            if conflict.auto_resolvable:
                resolution = await self.resolver.resolve_conflict(conflict)
                if resolution:
                    resolved.append(resolution)
                    if conflict.severity == ConflictSeverity.WARN:
                        warnings.append(f"Auto-resolved with warning: {conflict.description}")
                else:
                    resolved.append(conflict)
            else:
                resolved.append(conflict)
        
        return resolved, warnings
    
    async def _apply_merge(
        self,
        source: Dict[str, Any],
        target: Dict[str, Any],
        resolved_conflicts: List[MergeConflict]
    ) -> str:
        """Apply the merge with resolved conflicts"""
        # Create merge commit
        merge_data = {
            "type": "merge",
            "source": source["commit_id"],
            "target": target["commit_id"],
            "timestamp": datetime.utcnow(),
            "conflicts_resolved": len(resolved_conflicts)
        }
        
        # Generate commit ID
        commit_id = hashlib.sha256(
            json.dumps(merge_data, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        logger.info(f"Created merge commit: {commit_id}")
        return commit_id
    
    async def _fast_forward_merge(
        self,
        source: Dict[str, Any],
        target: Dict[str, Any]
    ) -> str:
        """Perform fast-forward merge when possible"""
        logger.info("Performing fast-forward merge")
        return source["commit_id"]
    
    async def _find_common_ancestor(
        self,
        source: Dict[str, Any],
        target: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find common ancestor of two branches"""
        # Simplified - in real implementation would traverse commit history
        if source.get("parent") == target.get("parent"):
            return {"commit_id": source["parent"]}
        return None
    
    def _group_properties_by_object(self, branch: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Group properties by their parent object"""
        result = defaultdict(dict)
        
        for obj in branch.get("objects", []):
            obj_id = obj["id"]
            for prop in obj.get("properties", []):
                if isinstance(prop, dict):
                    result[obj_id][prop["name"]] = prop
                else:
                    # Simple property name
                    result[obj_id][prop] = {"name": prop}
        
        return result
    
    def _get_max_severity(self, conflicts: List[MergeConflict]) -> Optional[ConflictSeverity]:
        """Get maximum severity from conflicts"""
        if not conflicts:
            return None
        
        severity_order = {
            ConflictSeverity.INFO: 0,
            ConflictSeverity.WARN: 1,
            ConflictSeverity.ERROR: 2,
            ConflictSeverity.BLOCK: 3
        }
        
        max_severity = ConflictSeverity.INFO
        for conflict in conflicts:
            if severity_order[conflict.severity] > severity_order[max_severity]:
                max_severity = conflict.severity
        
        return max_severity
    
    def _calculate_duration(self, start_time: datetime) -> float:
        """Calculate duration in milliseconds"""
        return (datetime.utcnow() - start_time).total_seconds() * 1000
    
    def _get_merge_stats(self, conflicts: List[MergeConflict]) -> Dict[str, int]:
        """Get merge statistics"""
        stats = {
            "total_conflicts": len(conflicts),
            "auto_resolved": sum(1 for c in conflicts if c.auto_resolvable),
            "by_type": defaultdict(int)
        }
        
        for conflict in conflicts:
            stats["by_type"][conflict.type.value] += 1
        
        return dict(stats)
    
    def _validate_resolution(self, resolution: Dict[str, Any]) -> bool:
        """Validate manual resolution format"""
        required_fields = ["resolution_id", "timestamp", "decisions"]
        return all(field in resolution for field in required_fields)


# Global instance
merge_engine = MergeEngine()