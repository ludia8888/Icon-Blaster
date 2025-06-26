"""
Unit tests for Graph Metadata Generation
Tests requirements FR-LK-IDX, GF-02, and GF-03 from Ontology_Requirements_Document.md
"""

import pytest
from datetime import datetime
from typing import Dict, Any

from core.graph.metadata_generator import (
    GraphMetadataGenerator,
    GraphIndexMetadata,
    TraversalRuleMetadata,
    PermissionPropagationRule,
    StatePropagationRule
)
from models.domain import LinkType, ObjectType, Cardinality, Directionality, Status


def create_test_object_type(id: str, name: str) -> ObjectType:
    """Helper to create test object types"""
    return ObjectType(
        id=id,
        name=name,
        display_name=name.replace("_", " ").title(),
        status=Status.ACTIVE,
        version_hash="test_hash",
        created_by="test_user",
        created_at=datetime.utcnow(),
        modified_by="test_user",
        modified_at=datetime.utcnow()
    )


def create_test_link_type(
    id: str, 
    name: str,
    from_type_id: str,
    to_type_id: str,
    cardinality: Cardinality = Cardinality.ONE_TO_MANY
) -> LinkType:
    """Helper to create test link types"""
    return LinkType(
        id=id,
        name=name,
        displayName=name.replace("_", " ").title(),
        fromTypeId=from_type_id,
        toTypeId=to_type_id,
        cardinality=cardinality,
        directionality=Directionality.UNIDIRECTIONAL,
        cascadeDelete=False,
        isRequired=False,
        status=Status.ACTIVE,
        versionHash="test_hash",
        createdBy="test_user",
        createdAt=datetime.utcnow(),
        modifiedBy="test_user",
        modifiedAt=datetime.utcnow()
    )


class TestGraphIndexMetadata:
    """Test index metadata generation"""
    
    def test_generate_index_metadata(self):
        """Test generating index metadata for a link type"""
        generator = GraphMetadataGenerator()
        
        # Create test types
        person_type = create_test_object_type("person", "Person")
        company_type = create_test_object_type("company", "Company")
        link_type = create_test_link_type(
            "works_at", 
            "works_at",
            "person",
            "company",
            Cardinality.ONE_TO_MANY
        )
        
        # Generate metadata
        metadata_list = generator.generate_index_metadata(
            link_type,
            person_type,
            company_type,
            "test_user"
        )
        
        assert len(metadata_list) == 2  # Forward and reverse
        
        # Check forward index
        forward = metadata_list[0]
        assert forward.index_id == "idx_fwd_works_at"
        assert forward.link_type_id == "works_at"
        assert forward.source_type_id == "person"
        assert forward.destination_type_id == "company"
        assert forward.index_strategy == "btree"
        assert "person_id" in forward.index_columns
        assert "company_id" in forward.index_columns
        
        # Check reverse index
        reverse = metadata_list[1]
        assert reverse.index_id == "idx_rev_works_at"
        assert reverse.source_type_id == "company"  # Swapped
        assert reverse.destination_type_id == "person"  # Swapped
    
    def test_cardinality_estimation(self):
        """Test that cardinality is estimated correctly"""
        generator = GraphMetadataGenerator()
        
        # Test different cardinalities
        test_cases = [
            (Cardinality.ONE_TO_ONE, "low"),
            (Cardinality.ONE_TO_MANY, "medium"),
            (Cardinality.MANY_TO_MANY, "high")
        ]
        
        for cardinality, expected in test_cases:
            link_type = create_test_link_type(
                f"link_{cardinality.value.replace('-', '_')}",
                f"link_{cardinality.value.replace('-', '_')}",
                "type_a",
                "type_b",
                cardinality
            )
            
            metadata = generator.generate_index_metadata(
                link_type,
                create_test_object_type("type_a", "TypeA"),
                create_test_object_type("type_b", "TypeB"),
                "test_user"
            )[0]
            
            assert metadata.expected_cardinality == expected


class TestTraversalRuleMetadata:
    """Test traversal rule generation"""
    
    def test_generate_traversal_rules(self):
        """Test basic traversal rule generation"""
        generator = GraphMetadataGenerator()
        
        link_type = create_test_link_type(
            "parent_child",
            "parent_child",
            "node",
            "node"
        )
        
        rule = generator.generate_traversal_rules(
            link_type,
            max_depth=3,
            is_transitive=True
        )
        
        assert rule.rule_id == "trav_parent_child"
        assert rule.link_type_id == "parent_child"
        assert rule.max_depth == 3
        assert rule.is_transitive is True
        assert rule.traversal_direction == "forward"  # Not bidirectional
        assert rule.enable_caching is True
    
    def test_bidirectional_traversal(self):
        """Test bidirectional link traversal rules"""
        generator = GraphMetadataGenerator()
        
        link_type = create_test_link_type(
            "related_to",
            "related_to",
            "item",
            "item"
        )
        link_type.directionality = Directionality.BIDIRECTIONAL
        
        rule = generator.generate_traversal_rules(link_type)
        
        assert rule.traversal_direction == "both"
    
    def test_traversal_with_metadata(self):
        """Test traversal rules with metadata"""
        generator = GraphMetadataGenerator()
        
        link_type = create_test_link_type(
            "active_member",
            "active_member",
            "person",
            "group"
        )
        # Use traversalMetadata instead of constraints
        link_type.traversalMetadata = {"filter": {"status": "active", "verified": True}}
        
        rule = generator.generate_traversal_rules(link_type)
        
        # Metadata should be used in rule generation
        assert rule.rule_id == "trav_active_member"
        assert rule.link_type_id == "active_member"


class TestPermissionPropagationRule:
    """Test permission propagation rule generation"""
    
    def test_basic_permission_propagation(self):
        """Test basic permission propagation rules"""
        generator = GraphMetadataGenerator()
        
        link_type = create_test_link_type(
            "owns",
            "owns",
            "user",
            "resource"
        )
        
        permission_config = {
            "propagate_read": True,
            "propagate_write": True,
            "propagate_delete": False,
            "direction": "forward"
        }
        
        rule = generator.generate_permission_propagation_rules(
            link_type,
            permission_config
        )
        
        assert rule.rule_id == "perm_owns"
        assert rule.propagate_read is True
        assert rule.propagate_write is True
        assert rule.propagate_delete is False
        assert rule.propagation_direction == "forward"
    
    def test_conditional_permission_propagation(self):
        """Test permission propagation with conditions"""
        generator = GraphMetadataGenerator()
        
        link_type = create_test_link_type(
            "manages",
            "manages",
            "manager",
            "team"
        )
        
        permission_config = {
            "propagate_read": True,
            "propagate_write": True,
            "condition": "link.active == true AND link.role == 'admin'",
            "override_child": True
        }
        
        rule = generator.generate_permission_propagation_rules(
            link_type,
            permission_config
        )
        
        assert rule.condition_expression is not None
        assert "active" in rule.condition_expression
        assert rule.override_child_permissions is True


class TestStatePropagationRule:
    """Test state propagation rule generation"""
    
    def test_cascade_state_propagation(self):
        """Test cascade-type state propagation"""
        generator = GraphMetadataGenerator()
        
        link_type = create_test_link_type(
            "contains",
            "contains",
            "container",
            "item"
        )
        
        state_config = {
            "fields": ["status", "visibility"],
            "type": "cascade",
            "on_create": False,
            "on_update": True,
            "on_delete": True
        }
        
        rule = generator.generate_state_propagation_rules(
            link_type,
            state_config
        )
        
        assert rule.rule_id == "state_contains"
        assert "status" in rule.propagated_fields
        assert "visibility" in rule.propagated_fields
        assert rule.propagation_type == "cascade"
        assert rule.cascade_on_update is True
        assert rule.cascade_on_delete is True
    
    def test_computed_state_propagation(self):
        """Test computed state propagation"""
        generator = GraphMetadataGenerator()
        
        link_type = create_test_link_type(
            "aggregates",
            "aggregates",
            "summary",
            "detail"
        )
        
        state_config = {
            "fields": ["total_count", "average_score"],
            "type": "compute",
            "computation": "SUM(children.count) AS total_count, AVG(children.score) AS average_score"
        }
        
        rule = generator.generate_state_propagation_rules(
            link_type,
            state_config
        )
        
        assert rule.propagation_type == "compute"
        assert rule.computation_expression is not None
        assert "SUM" in rule.computation_expression


class TestServiceMetadataExport:
    """Test metadata export for different services"""
    
    def test_export_for_object_storage(self):
        """Test exporting metadata for Object Storage Service"""
        generator = GraphMetadataGenerator()
        
        # Generate some metadata
        link_type = create_test_link_type("test_link", "test_link", "a", "b")
        generator.generate_index_metadata(
            link_type,
            create_test_object_type("a", "A"),
            create_test_object_type("b", "B"),
            "test_user"
        )
        
        export = generator.export_metadata_for_service("ObjectStorageService")
        
        assert "indexes" in export
        assert len(export["indexes"]) > 0
        assert "version" in export
        assert "generated_at" in export
    
    def test_export_for_object_set(self):
        """Test exporting metadata for Object Set Service"""
        generator = GraphMetadataGenerator()
        
        # Generate metadata
        link_type = create_test_link_type("test_link", "test_link", "a", "b")
        generator.generate_traversal_rules(link_type)
        generator.generate_index_metadata(
            link_type,
            create_test_object_type("a", "A"),
            create_test_object_type("b", "B"),
            "test_user"
        )
        
        export = generator.export_metadata_for_service("ObjectSetService")
        
        assert "traversal_rules" in export
        assert "index_hints" in export
        assert len(export["traversal_rules"]) > 0
        assert "test_link" in export["index_hints"]
    
    def test_export_for_action_service(self):
        """Test exporting metadata for Action Service"""
        generator = GraphMetadataGenerator()
        
        # Generate metadata
        link_type = create_test_link_type("test_link", "test_link", "a", "b")
        generator.generate_permission_propagation_rules(link_type, {})
        generator.generate_state_propagation_rules(link_type, {"fields": ["status"]})
        
        export = generator.export_metadata_for_service("ActionService")
        
        assert "permission_rules" in export
        assert "state_rules" in export
        assert len(export["permission_rules"]) > 0
        assert len(export["state_rules"]) > 0
    
    def test_export_for_vertex_ui(self):
        """Test exporting metadata for Vertex UI"""
        generator = GraphMetadataGenerator()
        
        # Generate metadata
        link_type = create_test_link_type("test_link", "test_link", "a", "b")
        generator.generate_traversal_rules(link_type, is_transitive=True)
        
        export = generator.export_metadata_for_service("VertexUI")
        
        assert "graph_schema" in export
        assert "traversal_rules" in export
        assert "edges" in export["graph_schema"]
    
    def test_unknown_service_export(self):
        """Test that unknown service names raise error"""
        generator = GraphMetadataGenerator()
        
        with pytest.raises(ValueError, match="Unknown service"):
            generator.export_metadata_for_service("UnknownService")


class TestMetadataValidation:
    """Test metadata consistency validation"""
    
    def test_validate_missing_indexes(self):
        """Test detection of missing indexes"""
        generator = GraphMetadataGenerator()
        
        # Create traversal rule without indexes
        link_type = create_test_link_type("orphan_link", "orphan_link", "a", "b")
        generator.generate_traversal_rules(link_type)
        
        issues = generator.validate_metadata_consistency()
        
        assert len(issues) > 0
        assert any(issue["type"] == "missing_index" for issue in issues)
        assert any("orphan_link" in issue["link_type_id"] for issue in issues)
    
    def test_validate_orphaned_permission_rules(self):
        """Test detection of orphaned permission rules"""
        generator = GraphMetadataGenerator()
        
        # Create permission rule without traversal rule
        link_type = create_test_link_type("orphan_perm", "orphan_perm", "a", "b")
        generator.generate_permission_propagation_rules(link_type, {})
        
        issues = generator.validate_metadata_consistency()
        
        assert len(issues) > 0
        assert any(issue["type"] == "orphaned_permission_rule" for issue in issues)
    
    def test_validate_consistent_metadata(self):
        """Test that consistent metadata passes validation"""
        generator = GraphMetadataGenerator()
        
        # Create complete metadata set
        link_type = create_test_link_type("complete_link", "complete_link", "a", "b")
        generator.generate_index_metadata(
            link_type,
            create_test_object_type("a", "A"),
            create_test_object_type("b", "B"),
            "test_user"
        )
        generator.generate_traversal_rules(link_type)
        generator.generate_permission_propagation_rules(link_type, {})
        generator.generate_state_propagation_rules(link_type, {"fields": ["status"]})
        
        issues = generator.validate_metadata_consistency()
        
        # Should have no issues
        assert len(issues) == 0


class TestIntegrationWithLinkType:
    """Test integration with LinkType model"""
    
    def test_link_type_with_graph_metadata(self):
        """Test LinkType with graph metadata fields"""
        link_type = LinkType(
            id="enriched_link",
            name="enriched_link",
            displayName="Enriched Link",
            fromTypeId="source",
            toTypeId="target",
            cardinality=Cardinality.ONE_TO_MANY,
            directionality=Directionality.UNIDIRECTIONAL,
            status=Status.ACTIVE,
            versionHash="test_hash",
            createdBy="test_user",
            createdAt=datetime.utcnow(),
            modifiedBy="test_user",
            modifiedAt=datetime.utcnow(),
            # Graph metadata fields
            permissionInheritance={
                "propagate_read": True,
                "propagate_write": False,
                "direction": "forward"
            },
            statePropagation={
                "fields": ["status", "visibility"],
                "type": "cascade",
                "on_update": True,
                "on_delete": True
            },
            traversalMetadata={
                "max_depth": 3,
                "enable_caching": True,
                "is_transitive": True
            }
        )
        
        # Verify metadata fields are set
        assert link_type.permissionInheritance is not None
        assert link_type.statePropagation is not None
        assert link_type.traversalMetadata is not None
        
        # Generate metadata using the enriched link type
        generator = GraphMetadataGenerator()
        
        # Should use metadata from link type
        perm_rule = generator.generate_permission_propagation_rules(
            link_type,
            link_type.permissionInheritance
        )
        assert perm_rule.propagate_read is True
        assert perm_rule.propagate_write is False
        
        state_rule = generator.generate_state_propagation_rules(
            link_type,
            link_type.statePropagation
        )
        assert "status" in state_rule.propagated_fields


if __name__ == "__main__":
    pytest.main([__file__, "-v"])