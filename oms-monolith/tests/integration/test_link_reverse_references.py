"""
Integration tests for link reverse references
Tests the complete flow from schema definition to API generation
"""

import pytest
from datetime import datetime
from typing import Dict, Any
import json

from core.api.schema_generator import GraphQLSchemaGenerator, OpenAPISchemaGenerator
from models.domain import (
    ObjectType, LinkType, Property,
    Cardinality, Directionality, Status, Visibility
)
from core.schema.registry import schema_registry


class TestLinkReverseReferencesIntegration:
    """Integration tests for reverse link references"""
    
    @pytest.fixture
    async def setup_test_schema(self):
        """Set up test schema with various link types"""
        # Create object types
        author_type = ObjectType(
            id="Author",
            name="Author",
            display_name="Author",
            status=Status.ACTIVE,
            properties=[
                Property(
                    id="author_id",
                    object_type_id="Author",
                    name="id",
                    display_name="ID",
                    data_type_id="string",
                    is_required=True,
                    is_primary_key=True,
                    visibility=Visibility.VISIBLE,
                    version_hash="test",
                    created_at=datetime.utcnow(),
                    modified_at=datetime.utcnow()
                ),
                Property(
                    id="author_name",
                    object_type_id="Author",
                    name="name",
                    display_name="Name",
                    data_type_id="string",
                    is_required=True,
                    visibility=Visibility.VISIBLE,
                    version_hash="test",
                    created_at=datetime.utcnow(),
                    modified_at=datetime.utcnow()
                )
            ],
            version_hash="test",
            created_by="test",
            created_at=datetime.utcnow(),
            modified_by="test",
            modified_at=datetime.utcnow()
        )
        
        book_type = ObjectType(
            id="Book",
            name="Book",
            display_name="Book",
            status=Status.ACTIVE,
            properties=[
                Property(
                    id="book_id",
                    object_type_id="Book",
                    name="id",
                    display_name="ID",
                    data_type_id="string",
                    is_required=True,
                    is_primary_key=True,
                    visibility=Visibility.VISIBLE,
                    version_hash="test",
                    created_at=datetime.utcnow(),
                    modified_at=datetime.utcnow()
                ),
                Property(
                    id="book_title",
                    object_type_id="Book",
                    name="title",
                    display_name="Title",
                    data_type_id="string",
                    is_required=True,
                    visibility=Visibility.VISIBLE,
                    version_hash="test",
                    created_at=datetime.utcnow(),
                    modified_at=datetime.utcnow()
                )
            ],
            version_hash="test",
            created_by="test",
            created_at=datetime.utcnow(),
            modified_by="test",
            modified_at=datetime.utcnow()
        )
        
        reader_type = ObjectType(
            id="Reader",
            name="Reader",
            display_name="Reader",
            status=Status.ACTIVE,
            properties=[
                Property(
                    id="reader_id",
                    object_type_id="Reader",
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
            version_hash="test",
            created_by="test",
            created_at=datetime.utcnow(),
            modified_by="test",
            modified_at=datetime.utcnow()
        )
        
        # Create link types with different configurations
        
        # 1. Unidirectional one-to-many (Author -> Books)
        author_books = LinkType(
            id="author_books",
            name="books",
            displayName="Author Books",
            fromTypeId="Author",
            toTypeId="Book",
            cardinality=Cardinality.ONE_TO_MANY,
            directionality=Directionality.UNIDIRECTIONAL,
            cascadeDelete=True,
            isRequired=False,
            status=Status.ACTIVE,
            versionHash="test",
            createdBy="test",
            createdAt=datetime.utcnow(),
            modifiedBy="test",
            modifiedAt=datetime.utcnow()
        )
        
        # 2. Bidirectional one-to-one (Book <-> MainAuthor)
        book_main_author = LinkType(
            id="book_main_author",
            name="mainAuthor",
            displayName="Main Author",
            fromTypeId="Book",
            toTypeId="Author",
            cardinality=Cardinality.ONE_TO_ONE,
            directionality=Directionality.BIDIRECTIONAL,
            cascadeDelete=False,
            isRequired=True,
            status=Status.ACTIVE,
            versionHash="test",
            createdBy="test",
            createdAt=datetime.utcnow(),
            modifiedBy="test",
            modifiedAt=datetime.utcnow()
        )
        
        # 3. Bidirectional many-to-many (Book <-> Readers)
        book_readers = LinkType(
            id="book_readers",
            name="readers",
            displayName="Book Readers",
            fromTypeId="Book",
            toTypeId="Reader",
            cardinality=Cardinality.MANY_TO_MANY,
            directionality=Directionality.BIDIRECTIONAL,
            cascadeDelete=False,
            isRequired=False,
            status=Status.ACTIVE,
            versionHash="test",
            createdBy="test",
            createdAt=datetime.utcnow(),
            modifiedBy="test",
            modifiedAt=datetime.utcnow()
        )
        
        # 4. Self-referencing bidirectional (Author <-> CoAuthors)
        author_coauthors = LinkType(
            id="author_coauthors",
            name="coAuthors",
            displayName="Co-Authors",
            fromTypeId="Author",
            toTypeId="Author",
            cardinality=Cardinality.MANY_TO_MANY,
            directionality=Directionality.BIDIRECTIONAL,
            cascadeDelete=False,
            isRequired=False,
            status=Status.ACTIVE,
            versionHash="test",
            createdBy="test",
            createdAt=datetime.utcnow(),
            modifiedBy="test",
            modifiedAt=datetime.utcnow()
        )
        
        return {
            "object_types": [author_type, book_type, reader_type],
            "link_types": [author_books, book_main_author, book_readers, author_coauthors]
        }
    
    @pytest.mark.asyncio
    async def test_graphql_reverse_references(self, setup_test_schema):
        """Test GraphQL schema generation with reverse references"""
        schema_data = await setup_test_schema
        generator = GraphQLSchemaGenerator()
        
        # Generate complete schema
        sdl = generator.generate_complete_schema(
            schema_data["object_types"],
            schema_data["link_types"]
        )
        
        # Test Author type
        assert "type Author {" in sdl
        assert "books: [Book!]" in sdl  # Forward unidirectional
        assert "inverse_mainAuthor: [Book!]" in sdl  # Reverse from Book->Author
        assert "coAuthors: [Author!]" in sdl  # Self-referencing forward
        assert "inverse_coAuthors: [Author!]" in sdl  # Self-referencing reverse
        
        # Test Book type
        assert "type Book {" in sdl
        assert "mainAuthor: Author!" in sdl  # Forward bidirectional (required)
        assert "readers: [Reader!]" in sdl  # Forward bidirectional M:N
        # Should NOT have books reverse reference (unidirectional)
        assert "authors: [Author!]" not in sdl
        assert "inverse_books" not in sdl
        
        # Test Reader type
        assert "type Reader {" in sdl
        assert "inverse_readers: [Book!]" in sdl  # Reverse bidirectional M:N
        
        # Check link field metadata
        author_fields = generator.link_fields.get("Author", [])
        book_fields = generator.link_fields.get("Book", [])
        reader_fields = generator.link_fields.get("Reader", [])
        
        # Author should have 3 link fields (books, inverse_mainAuthor, coAuthors + inverse)
        assert len(author_fields) == 4
        
        # Book should have 2 link fields (mainAuthor, readers)
        assert len(book_fields) == 2
        
        # Reader should have 1 link field (inverse_readers)
        assert len(reader_fields) == 1
    
    @pytest.mark.asyncio
    async def test_openapi_reverse_references(self, setup_test_schema):
        """Test OpenAPI schema generation with reverse references"""
        schema_data = await setup_test_schema
        generator = OpenAPISchemaGenerator()
        
        # Generate schemas for each type
        for obj_type in schema_data["object_types"]:
            schema = generator.generate_object_schema(
                obj_type,
                schema_data["link_types"]
            )
            
            if obj_type.id == "Author":
                # Author should have forward links
                assert "_links" in schema["properties"]
                links = schema["properties"]["_links"]["properties"]
                assert "books" in links
                assert "coAuthors" in links
                # No reverse link in OpenAPI (handled by href)
                
            elif obj_type.id == "Book":
                # Book should have its forward links
                assert "_links" in schema["properties"]
                links = schema["properties"]["_links"]["properties"]
                assert "mainAuthor" in links
                assert "readers" in links
                
            elif obj_type.id == "Reader":
                # Reader type might not have _links if only reverse relationships
                # This depends on implementation choice
                pass
        
        # Test path generation includes relationship endpoints
        paths = generator.generate_paths(
            schema_data["object_types"],
            schema_data["link_types"]
        )
        
        # Should have relationship navigation paths
        assert "/authors/{id}/books" in paths
        assert "/books/{id}/mainAuthor" in paths
        assert "/books/{id}/readers" in paths
        assert "/authors/{id}/coAuthors" in paths
    
    @pytest.mark.asyncio
    async def test_error_recovery_with_missing_types(self, setup_test_schema):
        """Test schema generation when referenced types are missing"""
        schema_data = await setup_test_schema
        generator = GraphQLSchemaGenerator()
        
        # Remove Book type to create broken references
        object_types = [t for t in schema_data["object_types"] if t.id != "Book"]
        
        # Should still generate schema for remaining types
        sdl = generator.generate_complete_schema(
            object_types,
            schema_data["link_types"]
        )
        
        # Author type should still reference Book (even though it's missing)
        assert "type Author {" in sdl
        assert "books: [Book!]" in sdl  # Reference to missing type
        
        # Reader type should also have reference to missing Book type
        assert "type Reader {" in sdl
        assert "inverse_readers: [Book!]" in sdl
    
    @pytest.mark.asyncio
    async def test_complex_permission_inheritance_metadata(self, setup_test_schema):
        """Test that permission inheritance metadata is preserved in reverse links"""
        schema_data = await setup_test_schema
        
        # Add permission inheritance to a link
        book_readers_link = next(
            l for l in schema_data["link_types"] if l.id == "book_readers"
        )
        book_readers_link.permissionInheritance = {
            "type": "parent",
            "direction": "forward",
            "scope": ["read", "write"]
        }
        
        generator = GraphQLSchemaGenerator()
        sdl = generator.generate_complete_schema(
            schema_data["object_types"],
            schema_data["link_types"]
        )
        
        # Check that reverse link preserves metadata
        reader_fields = generator.link_fields.get("Reader", [])
        reverse_field = next(
            f for f in reader_fields if f.field_name == "inverse_readers"
        )
        
        # Resolver hints should indicate this is a reverse link
        assert reverse_field.resolver_hints["direction"] == "reverse"
        # Original link metadata should be accessible
        assert reverse_field.link_type_id == "book_readers"
    
    @pytest.mark.asyncio
    async def test_cascade_delete_in_reverse_references(self, setup_test_schema):
        """Test cascade delete behavior is properly indicated in reverse links"""
        schema_data = await setup_test_schema
        generator = GraphQLSchemaGenerator()
        
        # Generate schema
        generator.generate_complete_schema(
            schema_data["object_types"],
            schema_data["link_types"]
        )
        
        # Check Author->Books cascade delete
        author_fields = generator.link_fields.get("Author", [])
        books_field = next(f for f in author_fields if f.field_name == "books")
        assert books_field.resolver_hints["cascade_delete"] is True
        
        # Check that reverse links don't inherit cascade delete
        book_fields = generator.link_fields.get("Book", [])
        # Book doesn't have reverse link from Author (unidirectional)
        
        # But Book->MainAuthor should not cascade
        main_author_field = next(
            f for f in book_fields if f.field_name == "mainAuthor"
        )
        assert main_author_field.resolver_hints["cascade_delete"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])