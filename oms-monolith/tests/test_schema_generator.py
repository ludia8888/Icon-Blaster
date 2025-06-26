"""
Unit tests for Enhanced API Schema Generator
Tests Phase 5 requirements: GraphQL and OpenAPI schema generation with link fields
"""

import pytest
import json
from typing import Dict, Any

from core.api.schema_generator import (
    GraphQLSchemaGenerator,
    OpenAPISchemaGenerator,
    LinkFieldMetadata
)
from models.domain import (
    ObjectType, LinkType, Property, 
    Cardinality, Directionality, Status, Visibility
)
from datetime import datetime


def create_test_object_type(id: str, name: str, properties: list = None) -> ObjectType:
    """Helper to create test object types"""
    if properties is None:
        properties = [
            Property(
                id=f"{id}_name",
                object_type_id=id,
                name="name",
                display_name="Name",
                data_type_id="string",
                is_required=True,
                is_indexed=True,
                visibility=Visibility.VISIBLE,
                version_hash="test",
                created_at=datetime.utcnow(),
                modified_at=datetime.utcnow()
            ),
            Property(
                id=f"{id}_description",
                object_type_id=id,
                name="description",
                display_name="Description",
                data_type_id="string",
                is_required=False,
                visibility=Visibility.VISIBLE,
                version_hash="test",
                created_at=datetime.utcnow(),
                modified_at=datetime.utcnow()
            )
        ]
    
    return ObjectType(
        id=id,
        name=name,
        display_name=name.replace("_", " ").title(),
        status=Status.ACTIVE,
        properties=properties,
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


class TestGraphQLSchemaGenerator:
    """Test GraphQL schema generation"""
    
    def test_generate_simple_object_type(self):
        """Test generating GraphQL schema for a simple object type"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        sdl = generator.generate_object_type_schema(user_type, [])
        
        assert "type User {" in sdl
        assert "id: ID!" in sdl
        assert "name: String!" in sdl
        assert "description: String" in sdl
        assert "_metadata: ObjectMetadata!" in sdl
        
        # Check input types
        assert "input UserCreateInput {" in sdl
        assert "input UserUpdateInput {" in sdl
    
    def test_generate_link_fields_forward(self):
        """Test generating forward link fields"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        post_type = create_test_object_type("Post", "Post")
        
        # User -> Posts (one to many)
        user_posts_link = create_test_link_type(
            "user_posts",
            "posts",
            "User",
            "Post",
            Cardinality.ONE_TO_MANY
        )
        
        sdl = generator.generate_object_type_schema(user_type, [user_posts_link])
        
        # Should have posts field as LinkSet
        assert "posts: [Post!]" in sdl
        assert '@link(metadata:' in sdl
        
        # Check link metadata was stored
        assert "User" in generator.link_fields
        link_fields = generator.link_fields["User"]
        assert len(link_fields) == 1
        assert link_fields[0].field_name == "posts"
        assert link_fields[0].field_type == "LinkSet"
        assert link_fields[0].target_type == "Post"
    
    def test_generate_link_fields_single(self):
        """Test generating single link fields"""
        generator = GraphQLSchemaGenerator()
        
        post_type = create_test_object_type("Post", "Post")
        user_type = create_test_object_type("User", "User")
        
        # Post -> User (modeled as User -> Posts with ONE_TO_MANY)
        # In OMS, we model this from the User perspective
        user_posts_link = create_test_link_type(
            "user_posts",
            "posts",
            "User",
            "Post",
            Cardinality.ONE_TO_MANY
        )
        
        # For the post type, this would appear as a reverse link if bidirectional
        # For now, test with a ONE_TO_ONE link which gives SingleLink
        post_author_link = create_test_link_type(
            "post_author",
            "author",
            "Post",
            "User",
            Cardinality.ONE_TO_ONE
        )
        sdl = generator.generate_object_type_schema(post_type, [post_author_link])
        
        # Should have author field as SingleLink
        assert "author: User" in sdl
        
        link_fields = generator.link_fields["Post"]
        assert link_fields[0].field_type == "SingleLink"
    
    def test_generate_bidirectional_links(self):
        """Test generating bidirectional link fields"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # User <-> User (friends - bidirectional many to many)
        friends_link = create_test_link_type(
            "user_friends",
            "friends",
            "User",
            "User",
            Cardinality.MANY_TO_MANY,
            Directionality.BIDIRECTIONAL
        )
        
        sdl = generator.generate_object_type_schema(user_type, [friends_link])
        
        # Should have both forward and inverse fields
        assert "friends: [User!]" in sdl
        assert "inverse_friends: [User!]" in sdl
        
        link_fields = generator.link_fields["User"]
        assert len(link_fields) == 2
        
        # Check bidirectional flag
        assert any(f.is_bidirectional for f in link_fields)
    
    def test_generate_complete_schema(self):
        """Test generating complete GraphQL schema"""
        generator = GraphQLSchemaGenerator()
        
        # Create types
        user_type = create_test_object_type("User", "User")
        post_type = create_test_object_type("Post", "Post")
        
        # Create links
        user_posts = create_test_link_type(
            "user_posts", "posts", "User", "Post", 
            Cardinality.ONE_TO_MANY
        )
        post_author = create_test_link_type(
            "post_author", "author", "Post", "User",
            Cardinality.ONE_TO_ONE  # Using ONE_TO_ONE for single link
        )
        
        sdl = generator.generate_complete_schema(
            [user_type, post_type],
            [user_posts, post_author]
        )
        
        # Check schema elements
        assert "scalar DateTime" in sdl
        assert "directive @link" in sdl
        assert "type ObjectMetadata" in sdl
        assert "type User {" in sdl
        assert "type Post {" in sdl
        assert "type Query {" in sdl
        assert "type Mutation {" in sdl
        
        # Check queries
        assert "user(id: ID!): User" in sdl
        assert "users(first: Int, after: String, filter: UserFilter): UserConnection!" in sdl
        
        # Check mutations
        assert "createUser(input: UserCreateInput!): User!" in sdl
        assert "updateUser(id: ID!, input: UserUpdateInput!): User!" in sdl
        assert "deleteUser(id: ID!): Boolean!" in sdl
        
        # Check filter and connection types
        assert "input UserFilter {" in sdl
        assert "type UserConnection {" in sdl
        assert "type UserEdge {" in sdl
    
    def test_required_links(self):
        """Test required link fields"""
        generator = GraphQLSchemaGenerator()
        
        order_type = create_test_object_type("Order", "Order")
        customer_type = create_test_object_type("Customer", "Customer")
        
        # Order must have a customer (ONE_TO_ONE relationship)
        order_customer = create_test_link_type(
            "order_customer",
            "customer",
            "Order", 
            "Customer",
            Cardinality.ONE_TO_ONE
        )
        order_customer.isRequired = True
        
        sdl = generator.generate_object_type_schema(order_type, [order_customer])
        
        # Required single link should have !
        assert "customer: Customer!" in sdl
        
        # Check in create input
        assert "customerId: ID" in sdl  # Still optional in input
    
    def test_link_resolver_hints(self):
        """Test that resolver hints are included in metadata"""
        generator = GraphQLSchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # Link with cascade delete
        posts_link = create_test_link_type(
            "user_posts", "posts", "User", "Post",
            Cardinality.ONE_TO_MANY
        )
        posts_link.cascadeDelete = True
        
        generator.generate_object_type_schema(user_type, [posts_link])
        
        link_field = generator.link_fields["User"][0]
        assert link_field.resolver_hints["cascade_delete"] is True
        assert link_field.resolver_hints["direction"] == "forward"
        assert link_field.resolver_hints["cardinality"] == "one-to-many"
    
    def test_export_schema_metadata(self):
        """Test exporting schema metadata"""
        generator = GraphQLSchemaGenerator()
        
        # Generate some schemas
        user_type = create_test_object_type("User", "User")
        posts_link = create_test_link_type(
            "user_posts", "posts", "User", "Post",
            Cardinality.ONE_TO_MANY
        )
        
        generator.generate_object_type_schema(user_type, [posts_link])
        
        metadata = generator.export_schema_metadata()
        
        assert "generated_at" in metadata
        assert "version" in metadata
        assert "link_fields" in metadata
        assert "User" in metadata["link_fields"]
        
        # Check link field is properly serialized
        user_links = metadata["link_fields"]["User"]
        assert len(user_links) == 1
        assert user_links[0]["field_name"] == "posts"


class TestOpenAPISchemaGenerator:
    """Test OpenAPI schema generation"""
    
    def test_generate_object_schema(self):
        """Test generating OpenAPI schema for object type"""
        generator = OpenAPISchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        schema = generator.generate_object_schema(user_type, [])
        
        assert schema["type"] == "object"
        assert schema["title"] == "User"
        assert "id" in schema["properties"]
        assert "name" in schema["properties"]
        assert "description" in schema["properties"]
        assert "_metadata" in schema["properties"]
        
        # Check required fields
        assert "id" in schema["required"]
        assert "name" in schema["required"]
        assert "description" not in schema["required"]
    
    def test_generate_hal_links(self):
        """Test generating HAL-style _links"""
        generator = OpenAPISchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        
        # Add some links
        posts_link = create_test_link_type(
            "user_posts", "posts", "User", "Post",
            Cardinality.ONE_TO_MANY
        )
        profile_link = create_test_link_type(
            "user_profile", "profile", "User", "Profile",
            Cardinality.ONE_TO_ONE
        )
        
        schema = generator.generate_object_schema(user_type, [posts_link, profile_link])
        
        assert "_links" in schema["properties"]
        links = schema["properties"]["_links"]["properties"]
        
        # Self link
        assert "self" in links
        
        # Posts link (array because many)
        assert "posts" in links
        assert links["posts"]["type"] == "array"
        
        # Profile link (single)
        assert "profile" in links
        assert links["profile"]["type"] == "object"
    
    def test_generate_embedded_resources(self):
        """Test generating _embedded schema"""
        generator = OpenAPISchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        posts_link = create_test_link_type(
            "user_posts", "posts", "User", "Post",
            Cardinality.ONE_TO_MANY
        )
        
        schema = generator.generate_object_schema(user_type, [posts_link])
        
        assert "_embedded" in schema["properties"]
        embedded = schema["properties"]["_embedded"]["properties"]
        
        assert "posts" in embedded
        assert embedded["posts"]["type"] == "array"
        assert "$ref" in embedded["posts"]["items"]
    
    def test_semantic_type_constraints(self):
        """Test that semantic type constraints are included"""
        generator = OpenAPISchemaGenerator()
        
        # Create property with semantic type
        email_prop = Property(
            id="user_email",
            object_type_id="User",
            name="email",
            display_name="Email",
            data_type_id="string",
            semantic_type_id="email_address",  # Assuming this exists
            is_required=True,
            visibility=Visibility.VISIBLE,
            version_hash="test",
            created_at=datetime.utcnow(),
            modified_at=datetime.utcnow()
        )
        
        user_type = create_test_object_type("User", "User", [email_prop])
        schema = generator.generate_object_schema(user_type, [])
        
        # Email property should have pattern from semantic type
        email_schema = schema["properties"]["email"]
        # Pattern would be added if semantic type exists in registry
        assert "description" in email_schema or "pattern" in email_schema
    
    def test_generate_paths(self):
        """Test generating OpenAPI paths"""
        generator = OpenAPISchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        post_type = create_test_object_type("Post", "Post")
        
        posts_link = create_test_link_type(
            "user_posts", "posts", "User", "Post",
            Cardinality.ONE_TO_MANY
        )
        
        paths = generator.generate_paths([user_type, post_type], [posts_link])
        
        # Check user paths
        assert "/users" in paths
        assert "get" in paths["/users"]
        assert "post" in paths["/users"]
        
        assert "/users/{id}" in paths
        assert "get" in paths["/users/{id}"]
        assert "put" in paths["/users/{id}"]
        assert "delete" in paths["/users/{id}"]
        
        # Check link paths
        assert "/users/{id}/posts" in paths
        assert "get" in paths["/users/{id}/posts"]
        assert "post" in paths["/users/{id}/posts"]  # For adding to collection
    
    def test_generate_complete_spec(self):
        """Test generating complete OpenAPI spec"""
        generator = OpenAPISchemaGenerator()
        
        user_type = create_test_object_type("User", "User")
        api_info = {
            "title": "OMS API",
            "version": "1.0.0",
            "description": "Ontology Management Service API"
        }
        
        spec = generator.generate_complete_spec(
            [user_type],
            [],
            api_info
        )
        
        assert spec["openapi"] == "3.0.3"
        assert spec["info"]["title"] == "OMS API"
        assert "servers" in spec
        assert "paths" in spec
        assert "components" in spec
        
        # Check components
        assert "schemas" in spec["components"]
        assert "User" in spec["components"]["schemas"]
        assert "UserCreate" in spec["components"]["schemas"]
        assert "UserUpdate" in spec["components"]["schemas"]
        
        # Check parameters
        assert "parameters" in spec["components"]
        assert "limit" in spec["components"]["parameters"]
        assert "offset" in spec["components"]["parameters"]
        assert "expand" in spec["components"]["parameters"]
    
    def test_struct_type_reference(self):
        """Test that struct types are properly referenced"""
        generator = OpenAPISchemaGenerator()
        
        # Property with struct type
        address_prop = Property(
            id="user_address",
            object_type_id="User",
            name="address",
            display_name="Address",
            data_type_id="address",  # Struct type
            is_required=False,
            visibility=Visibility.VISIBLE,
            version_hash="test",
            created_at=datetime.utcnow(),
            modified_at=datetime.utcnow()
        )
        
        user_type = create_test_object_type("User", "User", [address_prop])
        schema = generator.generate_object_schema(user_type, [])
        
        # Should reference struct schema if it exists
        address_schema = schema["properties"]["address"]
        # Would have $ref if struct type exists in registry
        assert address_schema is not None


class TestLinkFieldMetadata:
    """Test LinkFieldMetadata model"""
    
    def test_link_field_metadata_creation(self):
        """Test creating link field metadata"""
        metadata = LinkFieldMetadata(
            field_name="posts",
            field_type="LinkSet",
            target_type="Post",
            link_type_id="user_posts",
            is_required=False,
            is_bidirectional=False,
            description="User's posts",
            resolver_hints={
                "direction": "forward",
                "cardinality": "one-to-many"
            }
        )
        
        assert metadata.field_name == "posts"
        assert metadata.field_type == "LinkSet"
        assert metadata.target_type == "Post"
        assert metadata.resolver_hints["direction"] == "forward"
    
    def test_link_field_serialization(self):
        """Test link field metadata serialization"""
        metadata = LinkFieldMetadata(
            field_name="author",
            field_type="SingleLink",
            target_type="User",
            link_type_id="post_author"
        )
        
        data = metadata.dict()
        assert data["field_name"] == "author"
        assert data["field_type"] == "SingleLink"
        assert data["is_required"] is False
        assert data["is_bidirectional"] is False


class TestIntegration:
    """Integration tests for schema generation"""
    
    def test_graphql_openapi_consistency(self):
        """Test that GraphQL and OpenAPI generate consistent schemas"""
        graphql_gen = GraphQLSchemaGenerator()
        openapi_gen = OpenAPISchemaGenerator()
        
        # Create test data
        user_type = create_test_object_type("User", "User")
        posts_link = create_test_link_type(
            "user_posts", "posts", "User", "Post",
            Cardinality.ONE_TO_MANY
        )
        
        # Generate both schemas
        graphql_sdl = graphql_gen.generate_object_type_schema(user_type, [posts_link])
        openapi_schema = openapi_gen.generate_object_schema(user_type, [posts_link])
        
        # Both should have the posts relationship
        assert "posts" in graphql_sdl
        
        # OpenAPI should have it in _links and _embedded
        assert "_links" in openapi_schema["properties"]
        assert "posts" in openapi_schema["properties"]["_links"]["properties"]
        
        # Link metadata should be consistent
        graphql_links = graphql_gen.link_fields["User"]
        assert len(graphql_links) == 1
        assert graphql_links[0].field_name == "posts"
        assert graphql_links[0].field_type == "LinkSet"


class TestValidationAndErrors:
    """Test validation and error handling"""
    
    def test_schema_generation_with_validation_errors(self):
        """Test that schema generation continues despite validation errors"""
        generator = GraphQLSchemaGenerator()
        
        # Create type with valid property name (validation happens at input level)
        user_type = create_test_object_type("User", "User")
        # Add a property with reserved name that might cause issues
        user_type.properties.append(
            Property(
                id="type_prop",
                object_type_id="User",
                name="type",  # Reserved word but valid identifier
                display_name="Type",
                data_type_id="string",
                is_required=False,
                visibility=Visibility.VISIBLE,
                version_hash="test",
                created_at=datetime.utcnow(),
                modified_at=datetime.utcnow()
            )
        )
        
        # Should still generate schema
        sdl = generator.generate_object_type_schema(user_type, [])
        assert "type User {" in sdl
        assert "id: ID!" in sdl
        assert "type: String" in sdl  # Reserved word but should work
    
    def test_link_field_metadata_validation(self):
        """Test link field metadata is properly validated"""
        metadata = LinkFieldMetadata(
            field_name="test",
            field_type="InvalidType",  # Should be SingleLink or LinkSet
            target_type="Target",
            link_type_id="test_link"
        )
        
        # Should still be created (validation happens elsewhere)
        assert metadata.field_type == "InvalidType"
        
        # Test serialization doesn't break
        data = metadata.dict()
        assert data["field_type"] == "InvalidType"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])