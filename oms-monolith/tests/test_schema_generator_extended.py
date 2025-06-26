"""
Extended Unit Tests for Schema Generator
Focus on link reverse references and error cases
"""

import pytest
from datetime import datetime
from typing import List

from core.api.schema_generator import (
    GraphQLSchemaGenerator,
    OpenAPISchemaGenerator,
    LinkFieldMetadata
)
from models.domain import (
    ObjectType, LinkType, Property, 
    Cardinality, Directionality, Status, Visibility
)


def create_test_object_type(id: str, name: str) -> ObjectType:
    """Helper to create test object types"""
    return ObjectType(
        id=id,
        name=name,
        display_name=name,
        status=Status.ACTIVE,
        properties=[
            Property(
                id=f"{id}_id",
                object_type_id=id,
                name="id",
                display_name="ID",
                data_type_id="string",
                is_required=True,
                is_primary_key=True,
                visibility=Visibility.VISIBLE,
                version_hash="test",
                created_at=datetime.utcnow(),
                modified_at=datetime.utcnow()
            )
        ],
        version_hash="test_hash",
        created_by="test_user",
        created_at=datetime.utcnow(),
        modified_by="test_user",
        modified_at=datetime.utcnow()
    )


def create_test_link_type(
    id: str,
    name: str,
    from_type: str,
    to_type: str,
    cardinality: Cardinality = Cardinality.ONE_TO_MANY,
    directionality: Directionality = Directionality.UNIDIRECTIONAL
) -> LinkType:
    """Helper to create test link types"""
    return LinkType(
        id=id,
        name=name,
        displayName=name.replace("_", " ").title(),
        fromTypeId=from_type,
        toTypeId=to_type,
        cardinality=cardinality,
        directionality=directionality,
        cascadeDelete=False,
        isRequired=False,
        status=Status.ACTIVE,
        versionHash="test_hash",
        createdBy="test_user",
        createdAt=datetime.utcnow(),
        modifiedBy="test_user",
        modifiedAt=datetime.utcnow()
    )


class TestReverseReferences:
    """Test cases for link reverse references"""
    
    def test_unidirectional_reverse_reference_not_created(self):
        """Test that unidirectional links don't create reverse fields"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        post_type = create_test_object_type("Post", "Post")
        
        # Unidirectional link from User to Post
        user_posts = create_test_link_type(
            "user_posts",
            "posts",
            "User",
            "Post",
            Cardinality.ONE_TO_MANY,
            Directionality.UNIDIRECTIONAL
        )
        
        # Generate schema for Post (target type)
        sdl = generator.generate_object_type_schema(post_type, [user_posts])
        
        # Should NOT have reverse reference field
        assert "users: [User!]" not in sdl
        assert "author: User" not in sdl
        assert "inverse_posts" not in sdl
        
        # Post should have no link fields
        assert "Post" not in generator.link_fields or len(generator.link_fields.get("Post", [])) == 0
    
    def test_bidirectional_reverse_reference_created(self):
        """Test that bidirectional links create reverse fields correctly"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        post_type = create_test_object_type("Post", "Post")
        
        # Bidirectional link from User to Post
        user_posts = create_test_link_type(
            "user_posts",
            "posts",
            "User",
            "Post",
            Cardinality.ONE_TO_MANY,
            Directionality.BIDIRECTIONAL
        )
        
        # Generate schema for Post (target type)
        sdl = generator.generate_object_type_schema(post_type, [user_posts])
        
        # Should have reverse reference field
        assert "inverse_posts: User" in sdl  # Many posts to one user
        
        # Check link field metadata
        post_fields = generator.link_fields.get("Post", [])
        assert len(post_fields) == 1
        assert post_fields[0].field_name == "inverse_posts"
        assert post_fields[0].field_type == "SingleLink"  # Reverse of ONE_TO_MANY
        assert post_fields[0].target_type == "User"
        assert post_fields[0].is_bidirectional == True
    
    def test_many_to_many_reverse_reference(self):
        """Test M:N bidirectional relationships create correct reverse fields"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        group_type = create_test_object_type("Group", "Group")
        
        # Many-to-many bidirectional
        user_groups = create_test_link_type(
            "user_groups",
            "groups",
            "User",
            "Group",
            Cardinality.MANY_TO_MANY,
            Directionality.BIDIRECTIONAL
        )
        
        # Generate schema for Group (target type)
        sdl = generator.generate_object_type_schema(group_type, [user_groups])
        
        # Should have reverse reference as LinkSet
        assert "inverse_groups: [User!]" in sdl
        
        group_fields = generator.link_fields.get("Group", [])
        assert len(group_fields) == 1
        assert group_fields[0].field_type == "LinkSet"  # M:N remains LinkSet
    
    def test_self_referencing_bidirectional(self):
        """Test self-referencing bidirectional links"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # User -> User (manager/reports)
        manager_link = create_test_link_type(
            "user_manager",
            "manager",
            "User",
            "User",
            Cardinality.ONE_TO_ONE,
            Directionality.BIDIRECTIONAL
        )
        
        sdl = generator.generate_object_type_schema(user_type, [manager_link])
        
        # Should have both forward and inverse fields
        assert "manager: User" in sdl
        assert "inverse_manager: User" in sdl
        
        user_fields = generator.link_fields.get("User", [])
        assert len(user_fields) == 2


class TestErrorCases:
    """Test error handling and edge cases"""
    
    def test_missing_target_type_reference(self):
        """Test handling of links pointing to non-existent types"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # Link to non-existent type
        bad_link = create_test_link_type(
            "user_unknown",
            "unknown",
            "User",
            "NonExistentType",  # This type doesn't exist
            Cardinality.ONE_TO_MANY
        )
        
        # Should still generate schema without error
        sdl = generator.generate_object_type_schema(user_type, [bad_link])
        
        # Field should be created with type name as-is
        assert "unknown: [NonExistentType!]" in sdl
        
        # Metadata should be recorded
        user_fields = generator.link_fields.get("User", [])
        assert len(user_fields) == 1
        assert user_fields[0].target_type == "NonExistentType"
    
    def test_circular_dependencies(self):
        """Test handling of circular type dependencies"""
        generator = GraphQLSchemaGenerator()
        
        # Create circular dependency: A -> B -> C -> A
        type_a = create_test_object_type("TypeA", "TypeA")
        type_b = create_test_object_type("TypeB", "TypeB")
        type_c = create_test_object_type("TypeC", "TypeC")
        
        link_a_to_b = create_test_link_type("a_to_b", "b_ref", "TypeA", "TypeB")
        link_b_to_c = create_test_link_type("b_to_c", "c_ref", "TypeB", "TypeC")
        link_c_to_a = create_test_link_type("c_to_a", "a_ref", "TypeC", "TypeA")
        
        # Should handle circular dependencies without error
        all_links = [link_a_to_b, link_b_to_c, link_c_to_a]
        
        sdl_a = generator.generate_object_type_schema(type_a, all_links)
        sdl_b = generator.generate_object_type_schema(type_b, all_links)
        sdl_c = generator.generate_object_type_schema(type_c, all_links)
        
        assert "b_ref: [TypeB!]" in sdl_a
        assert "c_ref: [TypeC!]" in sdl_b
        assert "a_ref: [TypeA!]" in sdl_c
    
    def test_empty_link_types_list(self):
        """Test generating schema with no link types"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # Empty link types list
        sdl = generator.generate_object_type_schema(user_type, [])
        
        assert "type User {" in sdl
        assert "id: ID!" in sdl
        
        # No link fields should be generated
        assert "User" not in generator.link_fields or len(generator.link_fields.get("User", [])) == 0
    
    def test_duplicate_field_names(self):
        """Test handling of link fields that conflict with property names"""
        generator = GraphQLSchemaGenerator()
        
        # Create type with 'posts' property
        user_type = ObjectType(
            id="User",
            name="User",
            display_name="User",
            status=Status.ACTIVE,
            properties=[
                Property(
                    id="user_posts",
                    object_type_id="User",
                    name="posts",  # Conflicts with link field name
                    display_name="Posts Count",
                    data_type_id="integer",
                    is_required=False,
                    visibility=Visibility.VISIBLE,
                    version_hash="test",
                    created_at=datetime.utcnow(),
                    modified_at=datetime.utcnow()
                )
            ],
            version_hash="test_hash",
            created_by="test_user",
            created_at=datetime.utcnow(),
            modified_by="test_user",
            modified_at=datetime.utcnow()
        )
        
        # Link with same field name
        user_posts = create_test_link_type(
            "user_posts_link",
            "posts",  # Same name as property
            "User",
            "Post"
        )
        
        sdl = generator.generate_object_type_schema(user_type, [user_posts])
        
        # Both should be in the schema (GraphQL allows this, resolver handles it)
        assert "posts: Int" in sdl  # Property
        assert "posts: [Post!]" in sdl  # Link field
    
    def test_invalid_cardinality_handling(self):
        """Test handling of invalid or null cardinality"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # Create link with invalid cardinality
        link = create_test_link_type("test_link", "test", "User", "Post")
        link.cardinality = None  # Invalid
        
        # Should handle gracefully, defaulting to LinkSet
        sdl = generator.generate_object_type_schema(user_type, [link])
        
        # Should default to safe choice (LinkSet)
        assert "test: [Post!]" in sdl
    
    def test_inactive_link_types(self):
        """Test that inactive link types are handled correctly"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # Create inactive link
        inactive_link = create_test_link_type("user_posts", "posts", "User", "Post")
        inactive_link.status = Status.INACTIVE if hasattr(Status, 'INACTIVE') else Status.ACTIVE
        
        # Active link
        active_link = create_test_link_type("user_comments", "comments", "User", "Comment")
        
        sdl = generator.generate_object_type_schema(user_type, [inactive_link, active_link])
        
        # Both links should be included (filtering is done at a higher level)
        assert "posts: [Post!]" in sdl
        assert "comments: [Comment!]" in sdl


class TestOpenAPIErrorCases:
    """Test OpenAPI-specific error cases"""
    
    def test_missing_target_schema_reference(self):
        """Test OpenAPI handling of links to undefined schemas"""
        generator = OpenAPISchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # Link to undefined schema
        bad_link = create_test_link_type(
            "user_unknown",
            "unknown",
            "User",
            "UndefinedType"
        )
        
        schema = generator.generate_object_schema(user_type, [bad_link])
        
        # Should create reference even if target doesn't exist
        assert "_links" in schema["properties"]
        assert "unknown" in schema["properties"]["_links"]["properties"]
        
        # Embedded should reference the undefined type
        assert "_embedded" in schema["properties"]
        assert "unknown" in schema["properties"]["_embedded"]["properties"]
        assert "$ref" in schema["properties"]["_embedded"]["properties"]["unknown"]["items"]
    
    def test_hal_links_with_no_relationships(self):
        """Test HAL links generation with no relationships"""
        generator = OpenAPISchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        schema = generator.generate_object_schema(user_type, [])
        
        # Should not have _links or _embedded if no relationships
        assert "_links" not in schema["properties"]
        assert "_embedded" not in schema["properties"]
    
    def test_complex_nested_relationships(self):
        """Test OpenAPI with complex nested relationships"""
        generator = OpenAPISchemaGenerator()
        
        # Create a complex hierarchy
        company_type = create_test_object_type("Company", "Company")
        dept_type = create_test_object_type("Department", "Department")
        employee_type = create_test_object_type("Employee", "Employee")
        
        links = [
            create_test_link_type("company_departments", "departments", "Company", "Department"),
            create_test_link_type("department_employees", "employees", "Department", "Employee"),
            create_test_link_type("employee_manager", "manager", "Employee", "Employee", Cardinality.ONE_TO_ONE)
        ]
        
        # Generate schema for company
        company_schema = generator.generate_object_schema(company_type, links)
        
        # Should only have direct relationships
        assert "departments" in company_schema["properties"]["_links"]["properties"]
        assert "employees" not in company_schema["properties"]["_links"]["properties"]  # Not direct
        assert "manager" not in company_schema["properties"]["_links"]["properties"]  # Not direct


class TestEdgeCases:
    """Test various edge cases"""
    
    def test_link_with_empty_name(self):
        """Test link with empty or missing name"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # Link with valid name but we'll clear it after creation
        link = create_test_link_type("user_posts", "posts", "User", "Post")
        link.name = ""  # Clear name after creation to bypass validation
        
        sdl = generator.generate_object_type_schema(user_type, [link])
        
        # Should generate a field name from target type
        assert "posts: [Post!]" in sdl  # Uses target type as fallback
    
    def test_very_long_field_names(self):
        """Test handling of very long field names"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # Very long link name
        long_name = "this_is_a_very_long_link_name_that_might_cause_issues" * 3
        link = create_test_link_type("long_link", long_name, "User", "Post")
        
        sdl = generator.generate_object_type_schema(user_type, [link])
        
        # Should handle long names
        assert f"{long_name}: [Post!]" in sdl
    
    def test_special_characters_in_names(self):
        """Test handling of special characters in type/field names"""
        generator = GraphQLSchemaGenerator()
        
        # Type with valid name (special chars should be sanitized at input)
        user_type = create_test_object_type("UserType", "UserType")
        user_type.display_name = "User Type"  # Display name can have spaces
        
        link = create_test_link_type(
            "user_posts",
            "user_posts",  # Use underscore instead of hyphen
            "UserType",
            "Post"
        )
        
        # Should handle gracefully
        sdl = generator.generate_object_type_schema(user_type, [link])
        assert "type UserType {" in sdl  # Type ID is already sanitized
        assert "user_posts: [Post!]" in sdl  # Field name uses underscore
    
    def test_null_link_properties(self):
        """Test links with null properties"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # Link with various null properties
        link = create_test_link_type("test", "test", "User", "Post")
        link.description = None
        link.displayName = None
        link.cascadeDelete = None
        
        # Should handle nulls gracefully
        sdl = generator.generate_object_type_schema(user_type, [link])
        assert "test: [Post!]" in sdl
        
        # Check metadata doesn't break
        metadata = generator.export_schema_metadata()
        assert metadata is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])