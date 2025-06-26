"""
Conflict Resolver for OMS Schema Merge Operations

Implements automated conflict resolution strategies based on
conflict type and severity grades.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
import json

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ResolutionStrategy:
    """Defines a conflict resolution strategy"""
    name: str
    description: str
    applicable_types: List[str]
    max_severity: str
    resolution_func: callable


class ConflictResolver:
    """
    Automated conflict resolution engine.
    
    Resolves conflicts based on predefined strategies and rules
    from MERGE_CONFLICT_RESOLUTION_SPEC.md
    """
    
    def __init__(self):
        self.strategies = self._initialize_strategies()
        self.resolution_history = []
        self.resolution_cache = {}
        
    def _initialize_strategies(self) -> Dict[str, ResolutionStrategy]:
        """Initialize resolution strategies"""
        return {
            "type_widening": ResolutionStrategy(
                name="type_widening",
                description="Widen type to accommodate both values",
                applicable_types=["property_type_change"],
                max_severity="INFO",
                resolution_func=self._resolve_by_type_widening
            ),
            "union_constraints": ResolutionStrategy(
                name="union_constraints",
                description="Union of constraint sets",
                applicable_types=["constraint_conflict"],
                max_severity="WARN",
                resolution_func=self._resolve_by_union_constraints
            ),
            "prefer_modification": ResolutionStrategy(
                name="prefer_modification",
                description="Prefer modification over deletion",
                applicable_types=["delete_after_modify"],
                max_severity="WARN",
                resolution_func=self._resolve_prefer_modification
            ),
            "merge_properties": ResolutionStrategy(
                name="merge_properties",
                description="Merge property sets from both branches",
                applicable_types=["name_collision"],
                max_severity="WARN",
                resolution_func=self._resolve_by_merging_properties
            ),
            "expand_cardinality": ResolutionStrategy(
                name="expand_cardinality",
                description="Expand to more permissive cardinality",
                applicable_types=["cardinality_change"],
                max_severity="INFO",
                resolution_func=self._resolve_cardinality_expansion
            )
        }
    
    async def resolve_conflict(self, conflict: 'MergeConflict') -> Optional['MergeConflict']:
        """
        Attempt to automatically resolve a conflict.
        
        Returns resolved conflict or None if cannot resolve.
        """
        # Check cache
        cache_key = self._get_cache_key(conflict)
        if cache_key in self.resolution_cache:
            return self.resolution_cache[cache_key]
        
        # Find applicable strategy
        strategy = self._find_applicable_strategy(conflict)
        if not strategy:
            logger.debug(f"No strategy found for conflict: {conflict.id}")
            return None
        
        # Apply strategy
        try:
            resolved = await strategy.resolution_func(conflict)
            if resolved:
                # Cache result
                self.resolution_cache[cache_key] = resolved
                
                # Record history
                self.resolution_history.append({
                    "conflict_id": conflict.id,
                    "strategy": strategy.name,
                    "timestamp": datetime.utcnow(),
                    "success": True
                })
                
                logger.info(f"Resolved conflict {conflict.id} using {strategy.name}")
                return resolved
        except Exception as e:
            logger.error(f"Strategy {strategy.name} failed: {e}")
            self.resolution_history.append({
                "conflict_id": conflict.id,
                "strategy": strategy.name,
                "timestamp": datetime.utcnow(),
                "success": False,
                "error": str(e)
            })
        
        return None
    
    def _find_applicable_strategy(self, conflict: 'MergeConflict') -> Optional[ResolutionStrategy]:
        """Find strategy applicable to given conflict"""
        for strategy in self.strategies.values():
            if (conflict.type.value in strategy.applicable_types and
                self._severity_allows(conflict.severity, strategy.max_severity)):
                return strategy
        return None
    
    def _severity_allows(self, conflict_severity: str, max_severity: str) -> bool:
        """Check if conflict severity is within strategy's limit"""
        severity_order = ["INFO", "WARN", "ERROR", "BLOCK"]
        return (severity_order.index(conflict_severity.value) <= 
                severity_order.index(max_severity))
    
    async def _resolve_by_type_widening(self, conflict: 'MergeConflict') -> Optional['MergeConflict']:
        """Resolve by widening type to accommodate both values"""
        type_a = conflict.branch_a_value.get("type")
        type_b = conflict.branch_b_value.get("type")
        
        # Type widening rules
        widening_rules = {
            ("string", "text"): "text",
            ("text", "string"): "text",
            ("integer", "long"): "long",
            ("long", "integer"): "long",
            ("float", "double"): "double",
            ("double", "float"): "double",
            ("string", "json"): "json",
            ("json", "string"): "json"
        }
        
        widened_type = widening_rules.get((type_a, type_b))
        if widened_type:
            # Create resolved conflict
            resolved_value = {**conflict.branch_a_value, "type": widened_type}
            
            conflict.suggested_resolution = {
                "action": "widen_type",
                "resolved_type": widened_type,
                "resolved_value": resolved_value
            }
            conflict.auto_resolvable = True
            
            return conflict
        
        return None
    
    async def _resolve_by_union_constraints(self, conflict: 'MergeConflict') -> Optional['MergeConflict']:
        """Resolve by taking union of constraints"""
        constraints_a = conflict.branch_a_value.get("constraints", [])
        constraints_b = conflict.branch_b_value.get("constraints", [])
        
        # Union constraints, keeping the most permissive
        union_constraints = self._merge_constraints(constraints_a, constraints_b)
        
        resolved_value = {
            **conflict.branch_a_value,
            "constraints": union_constraints
        }
        
        conflict.suggested_resolution = {
            "action": "union_constraints",
            "resolved_constraints": union_constraints,
            "resolved_value": resolved_value
        }
        conflict.auto_resolvable = True
        
        return conflict
    
    async def _resolve_prefer_modification(self, conflict: 'MergeConflict') -> Optional['MergeConflict']:
        """Resolve delete-modify conflict by preferring modification"""
        # Check if entity is marked as deprecated
        if conflict.branch_a_value and conflict.branch_a_value.get("deprecated"):
            # If deprecated, allow deletion
            conflict.suggested_resolution = {
                "action": "accept_deletion",
                "reason": "Entity marked as deprecated"
            }
        else:
            # Prefer modification
            conflict.suggested_resolution = {
                "action": "keep_modification",
                "resolved_value": conflict.branch_a_value,
                "reason": "Preserving data over deletion"
            }
        
        conflict.auto_resolvable = True
        return conflict
    
    async def _resolve_by_merging_properties(self, conflict: 'MergeConflict') -> Optional['MergeConflict']:
        """Resolve by merging property sets"""
        props_a = set(conflict.branch_a_value.get("properties", []))
        props_b = set(conflict.branch_b_value.get("properties", []))
        
        # Union of properties
        merged_props = list(props_a | props_b)
        
        # Check for property conflicts
        common_props = props_a & props_b
        if self._has_property_conflicts(conflict.branch_a_value, conflict.branch_b_value, common_props):
            # Cannot auto-resolve if properties conflict
            return None
        
        resolved_value = {
            **conflict.branch_a_value,
            "properties": sorted(merged_props)
        }
        
        conflict.suggested_resolution = {
            "action": "merge_properties",
            "merged_properties": merged_props,
            "resolved_value": resolved_value
        }
        conflict.auto_resolvable = True
        
        return conflict
    
    async def _resolve_cardinality_expansion(self, conflict: 'MergeConflict') -> Optional['MergeConflict']:
        """Resolve by expanding to more permissive cardinality"""
        card_a = conflict.branch_a_value.get("cardinality")
        card_b = conflict.branch_b_value.get("cardinality")
        
        # Expansion rules (safe directions only)
        expansion_rules = {
            ("ONE_TO_ONE", "ONE_TO_MANY"): "ONE_TO_MANY",
            ("ONE_TO_ONE", "MANY_TO_MANY"): "MANY_TO_MANY",
            ("ONE_TO_MANY", "MANY_TO_MANY"): "MANY_TO_MANY"
        }
        
        # Check both directions
        expanded = expansion_rules.get((card_a, card_b)) or expansion_rules.get((card_b, card_a))
        
        if expanded:
            resolved_value = {
                **conflict.branch_a_value,
                "cardinality": expanded
            }
            
            migration_notes = self._get_cardinality_migration_notes(card_a, card_b, expanded)
            
            conflict.suggested_resolution = {
                "action": "expand_cardinality",
                "resolved_cardinality": expanded,
                "resolved_value": resolved_value,
                "migration_notes": migration_notes
            }
            conflict.auto_resolvable = True
            conflict.migration_impact = migration_notes
            
            return conflict
        
        return None
    
    def _merge_constraints(self, constraints_a: List[Dict], constraints_b: List[Dict]) -> List[Dict]:
        """Merge two sets of constraints, keeping most permissive"""
        merged = {}
        
        # Group by constraint type
        for constraint in constraints_a + constraints_b:
            c_type = constraint.get("type")
            if c_type not in merged:
                merged[c_type] = constraint
            else:
                # Keep more permissive
                merged[c_type] = self._more_permissive_constraint(
                    merged[c_type], constraint
                )
        
        return list(merged.values())
    
    def _more_permissive_constraint(self, c1: Dict, c2: Dict) -> Dict:
        """Return more permissive of two constraints"""
        c_type = c1.get("type")
        
        if c_type == "min_length":
            # Smaller min is more permissive
            return c1 if c1.get("value", 0) <= c2.get("value", 0) else c2
        elif c_type == "max_length":
            # Larger max is more permissive
            return c1 if c1.get("value", float('inf')) >= c2.get("value", float('inf')) else c2
        elif c_type == "pattern":
            # For patterns, we'd need to analyze regex - for now, return first
            return c1
        elif c_type == "enum":
            # Union of enum values
            values = list(set(c1.get("values", [])) | set(c2.get("values", [])))
            return {**c1, "values": values}
        
        return c1
    
    def _has_property_conflicts(
        self,
        obj_a: Dict,
        obj_b: Dict,
        common_props: set
    ) -> bool:
        """Check if common properties have conflicts"""
        # In a real implementation, would check property definitions
        # For now, assume no conflicts if property names match
        return False
    
    def _get_cardinality_migration_notes(
        self,
        from_card: str,
        to_card: str,
        resolved: str
    ) -> Dict[str, Any]:
        """Get migration notes for cardinality change"""
        notes = {
            "from": from_card,
            "to": resolved,
            "data_migration_required": False,
            "schema_changes": []
        }
        
        if from_card == "ONE_TO_ONE" and resolved == "ONE_TO_MANY":
            notes["schema_changes"].append("No schema change needed, FK remains valid")
        elif from_card == "ONE_TO_ONE" and resolved == "MANY_TO_MANY":
            notes["data_migration_required"] = True
            notes["schema_changes"].append("Create junction table")
            notes["schema_changes"].append("Migrate existing FKs to junction table")
        elif from_card == "ONE_TO_MANY" and resolved == "MANY_TO_MANY":
            notes["data_migration_required"] = True
            notes["schema_changes"].append("Create junction table")
            notes["schema_changes"].append("Migrate existing one-to-many relationships")
        
        return notes
    
    def _get_cache_key(self, conflict: 'MergeConflict') -> str:
        """Generate cache key for conflict"""
        return f"{conflict.type.value}:{conflict.entity_id}:{hash(str(conflict.branch_a_value))}:{hash(str(conflict.branch_b_value))}"
    
    def get_resolution_stats(self) -> Dict[str, Any]:
        """Get statistics about conflict resolutions"""
        total = len(self.resolution_history)
        successful = sum(1 for r in self.resolution_history if r["success"])
        
        by_strategy = {}
        for record in self.resolution_history:
            strategy = record["strategy"]
            if strategy not in by_strategy:
                by_strategy[strategy] = {"total": 0, "success": 0}
            by_strategy[strategy]["total"] += 1
            if record["success"]:
                by_strategy[strategy]["success"] += 1
        
        return {
            "total_attempts": total,
            "successful": successful,
            "success_rate": successful / total if total > 0 else 0,
            "by_strategy": by_strategy,
            "cache_size": len(self.resolution_cache)
        }
    
    def clear_cache(self):
        """Clear resolution cache"""
        self.resolution_cache.clear()
        logger.info("Conflict resolution cache cleared")


# Global instance
conflict_resolver = ConflictResolver()