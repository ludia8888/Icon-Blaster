"""
Graph Metadata Generator for OMS

Implements FR-LK-IDX and GF-02 requirements from Ontology_Requirements_Document.md
Generates metadata definitions that describe how graphs should be indexed and traversed.

IMPORTANT: OMS does NOT store or query actual graph data. It defines the rules and contracts
that other services (Object Set Service, Object Storage, Vertex) use to operate on graphs.
"""

import hashlib
import json
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
from pydantic import BaseModel, Field

from models.domain import LinkType, ObjectType, Directionality, Cardinality
from common_logging.setup import get_logger

logger = get_logger(__name__)


class GraphIndexMetadata(BaseModel):
    """
    Metadata definition for how a graph index should be created.
    This is used by Object Storage Service to create actual indexes.
    """
    index_id: str = Field(..., description="Unique identifier for this index definition")
    link_type_id: str = Field(..., description="Link type this index is for")
    source_type_id: str = Field(..., description="Source object type")
    destination_type_id: str = Field(..., description="Destination object type")
    
    # Index strategy hints for storage service
    index_strategy: str = Field(
        "btree", 
        description="Suggested index type (btree, hash, bitmap)"
    )
    index_columns: List[str] = Field(
        ..., 
        description="Columns to include in index"
    )
    
    # Performance hints
    expected_cardinality: str = Field(
        "medium", 
        description="Expected cardinality (low, medium, high)"
    )
    access_pattern: str = Field(
        "read_heavy", 
        description="Expected access pattern (read_heavy, write_heavy, balanced)"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    description: Optional[str] = None


class TraversalRuleMetadata(BaseModel):
    """
    Metadata defining rules for graph traversal.
    Used by Object Set Service for query generation.
    """
    rule_id: str = Field(..., description="Unique rule identifier")
    link_type_id: str = Field(..., description="Link type this rule applies to")
    
    # Traversal configuration
    max_depth: int = Field(
        1, 
        description="Maximum traversal depth (0=unlimited)"
    )
    allow_cycles: bool = Field(
        False, 
        description="Whether to allow cyclic paths"
    )
    traversal_direction: str = Field(
        "forward", 
        description="Direction: forward, reverse, both"
    )
    
    # Filter rules
    filter_expression: Optional[str] = Field(
        None, 
        description="Filter expression for traversal (e.g., 'status=active')"
    )
    
    # Performance hints
    enable_caching: bool = Field(True, description="Cache traversal results")
    cache_ttl_seconds: int = Field(300, description="Cache TTL in seconds")
    
    # For transitive relationships
    is_transitive: bool = Field(
        False, 
        description="Whether this relationship is transitive"
    )
    transitive_link_types: List[str] = Field(
        default_factory=list,
        description="Other link types to include in transitive closure"
    )


class PermissionPropagationRule(BaseModel):
    """
    Defines how permissions propagate through graph relationships.
    Used by Action Service and Security Service.
    """
    rule_id: str
    link_type_id: str
    
    # Propagation settings
    propagate_read: bool = Field(True, description="Propagate read permissions")
    propagate_write: bool = Field(False, description="Propagate write permissions")
    propagate_delete: bool = Field(False, description="Propagate delete permissions")
    
    # Direction of propagation
    propagation_direction: str = Field(
        "forward", 
        description="Direction: forward, reverse, both"
    )
    
    # Conditions
    condition_expression: Optional[str] = Field(
        None,
        description="Condition for propagation (e.g., 'link.strength > 0.5')"
    )
    
    # Inheritance rules
    inherit_from_parent: bool = Field(True)
    override_child_permissions: bool = Field(False)


class StatePropagationRule(BaseModel):
    """
    Defines how state changes propagate through graph relationships.
    Used by Action Service for cascade operations.
    """
    rule_id: str
    link_type_id: str
    
    # State fields to propagate
    propagated_fields: List[str] = Field(
        ...,
        description="Fields that propagate (e.g., ['status', 'visibility'])"
    )
    
    # Propagation behavior
    propagation_type: str = Field(
        "cascade",
        description="Type: cascade, aggregate, compute"
    )
    
    # Cascade settings
    cascade_on_create: bool = Field(False)
    cascade_on_update: bool = Field(True)
    cascade_on_delete: bool = Field(True)
    
    # Computation rule (for computed propagation)
    computation_expression: Optional[str] = Field(
        None,
        description="Expression for computing propagated value"
    )


class GraphMetadataGenerator:
    """
    Generates metadata definitions for graph structure and behavior.
    
    This class creates the "contracts" that other services use to:
    - Create indexes (Object Storage Service)
    - Execute queries (Object Set Service)
    - Propagate permissions (Security Service)
    - Cascade state changes (Action Service)
    - Visualize graphs (Vertex UI)
    """
    
    def __init__(self):
        self.index_metadata: Dict[str, GraphIndexMetadata] = {}
        self.traversal_rules: Dict[str, TraversalRuleMetadata] = {}
        self.permission_rules: Dict[str, PermissionPropagationRule] = {}
        self.state_rules: Dict[str, StatePropagationRule] = {}
    
    def generate_index_metadata(
        self,
        link_type: LinkType,
        source_type: ObjectType,
        destination_type: ObjectType,
        created_by: str
    ) -> List[GraphIndexMetadata]:
        """
        Generate index metadata for a link type.
        This metadata tells Object Storage how to create indexes.
        """
        metadata_list = []
        
        # Forward traversal index
        forward_index = GraphIndexMetadata(
            index_id=f"idx_fwd_{link_type.id}",
            link_type_id=link_type.id,
            source_type_id=source_type.id,
            destination_type_id=destination_type.id,
            index_strategy="btree",
            index_columns=[
                f"{source_type.id}_id",
                f"{destination_type.id}_id",
                "link_created_at"
            ],
            expected_cardinality=self._estimate_cardinality(link_type),
            access_pattern="read_heavy",
            created_by=created_by,
            description=f"Forward traversal index for {link_type.name}"
        )
        metadata_list.append(forward_index)
        self.index_metadata[forward_index.index_id] = forward_index
        
        # Reverse traversal index
        reverse_index = GraphIndexMetadata(
            index_id=f"idx_rev_{link_type.id}",
            link_type_id=link_type.id,
            source_type_id=destination_type.id,  # Swapped
            destination_type_id=source_type.id,  # Swapped
            index_strategy="btree",
            index_columns=[
                f"{destination_type.id}_id",
                f"{source_type.id}_id",
                "link_created_at"
            ],
            expected_cardinality=self._estimate_cardinality(link_type),
            access_pattern="read_heavy",
            created_by=created_by,
            description=f"Reverse traversal index for {link_type.name}"
        )
        metadata_list.append(reverse_index)
        self.index_metadata[reverse_index.index_id] = reverse_index
        
        logger.info(f"Generated index metadata for link type {link_type.id}")
        return metadata_list
    
    def generate_traversal_rules(
        self,
        link_type: LinkType,
        max_depth: int = 1,
        is_transitive: bool = False
    ) -> TraversalRuleMetadata:
        """
        Generate traversal rule metadata.
        This tells Object Set Service how to traverse this link type.
        """
        rule = TraversalRuleMetadata(
            rule_id=f"trav_{link_type.id}",
            link_type_id=link_type.id,
            max_depth=max_depth,
            allow_cycles=False,
            traversal_direction="both" if link_type.directionality == Directionality.BIDIRECTIONAL else "forward",
            is_transitive=is_transitive,
            enable_caching=True,
            cache_ttl_seconds=300
        )
        
        # Add filter if link has traversal metadata with filter
        if link_type.traversalMetadata and "filter" in link_type.traversalMetadata:
            rule.filter_expression = json.dumps(link_type.traversalMetadata["filter"])
        
        self.traversal_rules[rule.rule_id] = rule
        logger.info(f"Generated traversal rules for link type {link_type.id}")
        return rule
    
    def generate_permission_propagation_rules(
        self,
        link_type: LinkType,
        permission_config: Dict[str, Any]
    ) -> PermissionPropagationRule:
        """
        Generate permission propagation rules.
        This tells Security Service how permissions flow through this link.
        """
        rule = PermissionPropagationRule(
            rule_id=f"perm_{link_type.id}",
            link_type_id=link_type.id,
            propagate_read=permission_config.get("propagate_read", True),
            propagate_write=permission_config.get("propagate_write", False),
            propagate_delete=permission_config.get("propagate_delete", False),
            propagation_direction=permission_config.get("direction", "forward"),
            inherit_from_parent=permission_config.get("inherit_from_parent", True),
            override_child_permissions=permission_config.get("override_child", False)
        )
        
        if "condition" in permission_config:
            rule.condition_expression = permission_config["condition"]
        
        self.permission_rules[rule.rule_id] = rule
        logger.info(f"Generated permission propagation rules for link type {link_type.id}")
        return rule
    
    def generate_state_propagation_rules(
        self,
        link_type: LinkType,
        state_config: Dict[str, Any]
    ) -> StatePropagationRule:
        """
        Generate state propagation rules.
        This tells Action Service how state changes cascade through this link.
        """
        rule = StatePropagationRule(
            rule_id=f"state_{link_type.id}",
            link_type_id=link_type.id,
            propagated_fields=state_config.get("fields", ["status"]),
            propagation_type=state_config.get("type", "cascade"),
            cascade_on_create=state_config.get("on_create", False),
            cascade_on_update=state_config.get("on_update", True),
            cascade_on_delete=state_config.get("on_delete", True)
        )
        
        if "computation" in state_config:
            rule.computation_expression = state_config["computation"]
        
        self.state_rules[rule.rule_id] = rule
        logger.info(f"Generated state propagation rules for link type {link_type.id}")
        return rule
    
    def export_metadata_for_service(self, service_name: str) -> Dict[str, Any]:
        """
        Export metadata for a specific service.
        Each service gets only the metadata it needs.
        """
        if service_name == "ObjectStorageService":
            return {
                "indexes": [idx.dict() for idx in self.index_metadata.values()],
                "version": "1.0",
                "generated_at": datetime.utcnow().isoformat()
            }
        
        elif service_name == "ObjectSetService":
            return {
                "traversal_rules": [rule.dict() for rule in self.traversal_rules.values()],
                "index_hints": {
                    idx.link_type_id: idx.index_id 
                    for idx in self.index_metadata.values()
                },
                "version": "1.0",
                "generated_at": datetime.utcnow().isoformat()
            }
        
        elif service_name == "ActionService":
            return {
                "permission_rules": [rule.dict() for rule in self.permission_rules.values()],
                "state_rules": [rule.dict() for rule in self.state_rules.values()],
                "version": "1.0",
                "generated_at": datetime.utcnow().isoformat()
            }
        
        elif service_name == "VertexUI":
            return {
                "graph_schema": self._generate_graph_schema(),
                "traversal_rules": [rule.dict() for rule in self.traversal_rules.values()],
                "version": "1.0",
                "generated_at": datetime.utcnow().isoformat()
            }
        
        else:
            raise ValueError(f"Unknown service: {service_name}")
    
    def _estimate_cardinality(self, link_type: LinkType) -> str:
        """Estimate cardinality based on link type"""
        if link_type.cardinality == Cardinality.ONE_TO_ONE:
            return "low"
        elif link_type.cardinality == Cardinality.ONE_TO_MANY:
            return "medium"
        else:  # MANY_TO_MANY
            return "high"
    
    def _generate_graph_schema(self) -> Dict[str, Any]:
        """Generate graph schema for visualization"""
        schema = {
            "nodes": {},
            "edges": {}
        }
        
        # Add edge definitions from link types
        for rule in self.traversal_rules.values():
            schema["edges"][rule.link_type_id] = {
                "bidirectional": rule.traversal_direction == "both",
                "max_depth": rule.max_depth,
                "transitive": rule.is_transitive
            }
        
        return schema
    
    def validate_metadata_consistency(self) -> List[Dict[str, str]]:
        """
        Validate that all metadata is consistent.
        Returns list of validation issues.
        """
        issues = []
        
        # Check that all traversal rules have corresponding indexes
        for rule in self.traversal_rules.values():
            has_forward = any(
                idx.link_type_id == rule.link_type_id 
                for idx in self.index_metadata.values()
            )
            if not has_forward:
                issues.append({
                    "type": "missing_index",
                    "link_type_id": rule.link_type_id,
                    "message": f"Traversal rule exists but no index metadata found"
                })
        
        # Check permission and state rules reference valid link types
        all_link_types = {rule.link_type_id for rule in self.traversal_rules.values()}
        
        for perm_rule in self.permission_rules.values():
            if perm_rule.link_type_id not in all_link_types:
                issues.append({
                    "type": "orphaned_permission_rule",
                    "rule_id": perm_rule.rule_id,
                    "message": f"Permission rule references unknown link type"
                })
        
        return issues


# Global instance
graph_metadata_generator = GraphMetadataGenerator()