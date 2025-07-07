"""
Integration tests for @metadata Frames feature
"""
import pytest
import json
from typing import Dict, Any, List
from datetime import datetime

from core.documents.metadata_frames import (
    MetadataFrame,
    MetadataFrameParser,
    SchemaDocumentation,
    SchemaDocumentationGenerator
)
from api.v1.document_routes import router
from api.graphql.document_schema import DocumentQueries
from common_logging.setup import get_logger

logger = get_logger(__name__)


class TestMetadataFramesIntegration:
    """Test suite for metadata frames functionality"""
    
    @pytest.fixture
    def sample_markdown_with_frames(self):
        """Sample markdown document with various metadata frames"""
        return """# API Documentation

This document describes our API with embedded metadata.

```@metadata:document yaml
title: API Documentation
version: 2.0.0
author: Test Suite
date: 2024-01-15
tags:
  - api
  - documentation
  - testing
```

## Overview

Our API provides comprehensive features for data management.

```@metadata:api json
{
  "endpoint": "/api/v1/users",
  "method": "GET",
  "description": "List all users",
  "parameters": {
    "limit": {
      "type": "integer",
      "default": 10
    },
    "offset": {
      "type": "integer", 
      "default": 0
    }
  },
  "responses": {
    "200": "Success",
    "401": "Unauthorized"
  }
}
```

## Schema Definition

```@metadata:schema yaml
User:
  type: object
  properties:
    id:
      type: string
      format: uuid
    name:
      type: string
      minLength: 1
    email:
      type: string
      format: email
    created_at:
      type: string
      format: date-time
  required:
    - id
    - name
    - email
```

## Examples

```@metadata:example json
{
  "request": {
    "method": "POST",
    "url": "/api/v1/users",
    "body": {
      "name": "John Doe",
      "email": "john@example.com"
    }
  },
  "response": {
    "status": 201,
    "body": {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "name": "John Doe",
      "email": "john@example.com",
      "created_at": "2024-01-15T10:30:00Z"
    }
  }
}
```

## Validation Rules

```@metadata:validation yaml
rules:
  - field: email
    type: regex
    pattern: ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$
    message: Invalid email format
  - field: name
    type: length
    min: 1
    max: 100
    message: Name must be between 1 and 100 characters
```

## Changelog

```@metadata:changelog yaml
- version: 2.0.0
  date: 2024-01-15
  changes:
    - Added pagination support
    - Improved error responses
    - Added rate limiting
- version: 1.0.0
  date: 2023-12-01
  changes:
    - Initial release
```

## Custom Metadata

```@metadata:custom analytics
tracking_id: UA-123456789
events:
  - page_view
  - api_call
  - error
```

This concludes our API documentation with embedded metadata frames.
"""
    
    @pytest.fixture
    def parser(self):
        """Create metadata parser instance"""
        return MetadataFrameParser()
    
    @pytest.fixture
    def doc_generator(self):
        """Create documentation generator instance"""
        return SchemaDocumentationGenerator()
    
    def test_parse_all_frame_types(self, parser, sample_markdown_with_frames):
        """Test parsing all supported frame types"""
        cleaned_content, frames = parser.parse_document(sample_markdown_with_frames)
        
        # Verify all frame types detected
        frame_types = {frame.frame_type for frame in frames}
        expected_types = {'document', 'api', 'schema', 'example', 'validation', 'changelog', 'custom'}
        assert frame_types == expected_types
        
        # Verify frame count
        assert len(frames) == 7
        
        # Verify cleaned content has frames removed
        assert "```@metadata:" not in cleaned_content
        assert "# API Documentation" in cleaned_content
        assert "This document describes our API" in cleaned_content
    
    def test_parse_document_metadata(self, parser, sample_markdown_with_frames):
        """Test parsing document metadata frame"""
        _, frames = parser.parse_document(sample_markdown_with_frames)
        
        doc_frame = next(f for f in frames if f.frame_type == 'document')
        assert doc_frame.format == 'yaml'
        assert doc_frame.content['title'] == 'API Documentation'
        assert doc_frame.content['version'] == '2.0.0'
        assert doc_frame.content['tags'] == ['api', 'documentation', 'testing']
    
    def test_parse_api_metadata(self, parser, sample_markdown_with_frames):
        """Test parsing API metadata frame"""
        _, frames = parser.parse_document(sample_markdown_with_frames)
        
        api_frame = next(f for f in frames if f.frame_type == 'api')
        assert api_frame.format == 'json'
        assert api_frame.content['endpoint'] == '/api/v1/users'
        assert api_frame.content['method'] == 'GET'
        assert 'parameters' in api_frame.content
        assert api_frame.content['parameters']['limit']['default'] == 10
    
    def test_parse_schema_metadata(self, parser, sample_markdown_with_frames):
        """Test parsing schema metadata frame"""
        _, frames = parser.parse_document(sample_markdown_with_frames)
        
        schema_frame = next(f for f in frames if f.frame_type == 'schema')
        assert schema_frame.format == 'yaml'
        assert 'User' in schema_frame.content
        user_schema = schema_frame.content['User']
        assert user_schema['type'] == 'object'
        assert 'properties' in user_schema
        assert set(user_schema['required']) == {'id', 'name', 'email'}
    
    def test_parse_validation_rules(self, parser, sample_markdown_with_frames):
        """Test parsing validation metadata frame"""
        _, frames = parser.parse_document(sample_markdown_with_frames)
        
        validation_frame = next(f for f in frames if f.frame_type == 'validation')
        assert validation_frame.format == 'yaml'
        rules = validation_frame.content['rules']
        assert len(rules) == 2
        
        email_rule = next(r for r in rules if r['field'] == 'email')
        assert email_rule['type'] == 'regex'
        assert 'pattern' in email_rule
    
    def test_parse_changelog(self, parser, sample_markdown_with_frames):
        """Test parsing changelog metadata frame"""
        _, frames = parser.parse_document(sample_markdown_with_frames)
        
        changelog_frame = next(f for f in frames if f.frame_type == 'changelog')
        assert changelog_frame.format == 'yaml'
        
        versions = changelog_frame.content
        assert len(versions) == 2
        assert versions[0]['version'] == '2.0.0'
        assert len(versions[0]['changes']) == 3
    
    def test_parse_custom_metadata(self, parser, sample_markdown_with_frames):
        """Test parsing custom metadata frame"""
        _, frames = parser.parse_document(sample_markdown_with_frames)
        
        custom_frame = next(f for f in frames if f.frame_type == 'custom')
        assert custom_frame.format == 'analytics'  # Custom format
        
        # Custom parser should handle as YAML by default
        assert custom_frame.content['tracking_id'] == 'UA-123456789'
        assert len(custom_frame.content['events']) == 3
    
    def test_frame_positions(self, parser, sample_markdown_with_frames):
        """Test that frame positions are correctly tracked"""
        _, frames = parser.parse_document(sample_markdown_with_frames)
        
        # Verify positions are tuples of (start_line, end_line)
        for frame in frames:
            assert isinstance(frame.position, tuple)
            assert len(frame.position) == 2
            assert frame.position[0] < frame.position[1]
        
        # Verify frames are in document order
        positions = [f.position[0] for f in frames]
        assert positions == sorted(positions)
    
    def test_inject_frames(self, parser):
        """Test injecting metadata frames into content"""
        original_content = """# Document

Some content here.

More content.
"""
        
        frames = [
            MetadataFrame(
                frame_type='document',
                content={'title': 'Test Document', 'version': '1.0'},
                format='yaml',
                position=(0, 0)
            ),
            MetadataFrame(
                frame_type='api',
                content={'endpoint': '/test', 'method': 'GET'},
                format='json',
                position=(0, 0)
            )
        ]
        
        result = parser.inject_frames(original_content, frames)
        
        # Verify frames are injected
        assert "```@metadata:document yaml" in result
        assert "title: Test Document" in result
        assert "```@metadata:api json" in result
        assert '"endpoint": "/test"' in result
        
        # Verify original content preserved
        assert "# Document" in result
        assert "Some content here." in result
    
    def test_extract_front_matter(self, parser):
        """Test extracting front matter as metadata"""
        content_with_front_matter = """---
title: Front Matter Document
author: Test Author
date: 2024-01-15
tags:
  - test
  - metadata
---

# Main Content

This is the main content after front matter.
"""
        
        cleaned, frames = parser.parse_document(content_with_front_matter)
        
        # Front matter should be extracted as document frame
        doc_frames = [f for f in frames if f.frame_type == 'document']
        assert len(doc_frames) == 1
        
        doc_frame = doc_frames[0]
        assert doc_frame.content['title'] == 'Front Matter Document'
        assert doc_frame.content['author'] == 'Test Author'
        assert doc_frame.content['tags'] == ['test', 'metadata']
        
        # Cleaned content should not have front matter
        assert not cleaned.startswith('---')
        assert cleaned.strip().startswith('# Main Content')
    
    def test_generate_schema_documentation(self, doc_generator):
        """Test generating documentation for schema objects"""
        object_type = {
            "@type": "Class",
            "@id": "User", 
            "@documentation": {
                "@comment": "Represents a user in the system",
                "@label": "User Entity"
            },
            "id": "xsd:string",
            "name": "xsd:string",
            "email": "xsd:string",
            "created_at": "xsd:dateTime",
            "roles": {
                "@type": "Set",
                "@class": "Role"
            }
        }
        
        doc = doc_generator.generate_object_type_doc(object_type)
        
        assert doc.name == "User"
        assert doc.title == "User Entity"
        assert doc.description == "Represents a user in the system"
        
        # Check metadata frames
        frame_types = {f.frame_type for f in doc.metadata_frames}
        assert 'schema' in frame_types
        assert 'example' in frame_types
    
    def test_schema_doc_markdown_generation(self, doc_generator):
        """Test markdown generation for schema documentation"""
        object_type = {
            "@type": "Class",
            "@id": "Product",
            "@documentation": {
                "@comment": "Product entity for e-commerce",
                "@label": "Product"
            },
            "sku": "xsd:string",
            "name": "xsd:string", 
            "price": "xsd:decimal",
            "in_stock": "xsd:boolean"
        }
        
        doc = doc_generator.generate_object_type_doc(object_type)
        markdown = doc.to_markdown()
        
        # Verify markdown structure
        assert "# Product" in markdown
        assert "Product entity for e-commerce" in markdown
        assert "## Properties" in markdown
        assert "- **sku**: `xsd:string`" in markdown
        assert "- **price**: `xsd:decimal`" in markdown
        
        # Verify metadata frames in markdown
        assert "```@metadata:schema yaml" in markdown
        assert "```@metadata:example json" in markdown
    
    def test_metadata_summary_generation(self, parser, sample_markdown_with_frames):
        """Test generating metadata summary"""
        _, frames = parser.parse_document(sample_markdown_with_frames)
        
        summary = parser.generate_summary(frames)
        
        assert summary['total_frames'] == 7
        assert summary['frame_types']['document'] == 1
        assert summary['frame_types']['api'] == 1
        assert summary['frame_types']['schema'] == 1
        
        # Document metadata should be in top-level
        assert 'metadata' in summary
        assert summary['metadata']['title'] == 'API Documentation'
        assert summary['metadata']['version'] == '2.0.0'
    
    def test_complex_nested_metadata(self, parser):
        """Test parsing complex nested metadata structures"""
        complex_markdown = """# Complex Document

```@metadata:schema yaml
Database:
  type: object
  properties:
    tables:
      type: array
      items:
        type: object
        properties:
          name:
            type: string
          columns:
            type: array
            items:
              type: object
              properties:
                name:
                  type: string
                type:
                  type: string
                constraints:
                  type: array
                  items:
                    type: string
          indexes:
            type: array
            items:
              type: object
              properties:
                name:
                  type: string
                columns:
                  type: array
                  items:
                    type: string
                unique:
                  type: boolean
```

Content continues here.
"""
        
        cleaned, frames = parser.parse_document(complex_markdown)
        
        schema_frame = next(f for f in frames if f.frame_type == 'schema')
        db_schema = schema_frame.content['Database']
        
        # Verify deep nesting parsed correctly
        assert db_schema['type'] == 'object'
        tables_schema = db_schema['properties']['tables']
        assert tables_schema['type'] == 'array'
        
        table_item_schema = tables_schema['items']
        assert 'columns' in table_item_schema['properties']
        
        column_schema = table_item_schema['properties']['columns']['items']
        assert 'constraints' in column_schema['properties']
    
    def test_malformed_frame_handling(self, parser):
        """Test handling of malformed metadata frames"""
        malformed_markdown = """# Document

```@metadata:invalid
This is not valid YAML or JSON
- incomplete: 
```

```@metadata:document json
{
  "invalid": "json",
  "missing": "closing brace"
```

Normal content here.
"""
        
        # Should handle gracefully
        cleaned, frames = parser.parse_document(malformed_markdown)
        
        # Malformed frames should be skipped or handled
        assert len(frames) <= 2  # May parse 0, 1, or 2 depending on error handling
        assert "Normal content here." in cleaned
    
    def test_performance_large_document(self, parser):
        """Test performance with large documents containing many frames"""
        import time
        
        # Generate large document with many frames
        large_markdown = "# Large Document\n\n"
        
        for i in range(100):
            large_markdown += f"""
## Section {i}

Some content for section {i}.

```@metadata:api json
{{
  "endpoint": "/api/v1/resource{i}",
  "method": "GET",
  "description": "Get resource {i}"
}}
```

More content here.
"""
        
        start = time.time()
        cleaned, frames = parser.parse_document(large_markdown)
        parse_time = time.time() - start
        
        assert len(frames) == 100
        assert parse_time < 1.0  # Should parse quickly even with many frames
        
        logger.info(f"Parsed {len(frames)} frames in {parse_time:.3f}s")
    
    @pytest.mark.asyncio
    async def test_concurrent_parsing(self, parser, sample_markdown_with_frames):
        """Test concurrent parsing operations"""
        import asyncio
        
        # Create multiple parsing tasks
        tasks = []
        for i in range(10):
            # Modify document slightly for each task
            modified_doc = sample_markdown_with_frames.replace(
                "version: 2.0.0",
                f"version: 2.0.{i}"
            )
            
            task = asyncio.create_task(
                asyncio.to_thread(parser.parse_document, modified_doc)
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Verify all parsed successfully
        assert len(results) == 10
        
        for i, (cleaned, frames) in enumerate(results):
            doc_frame = next(f for f in frames if f.frame_type == 'document')
            assert doc_frame.content['version'] == f'2.0.{i}'


class TestMetadataFramesAPI:
    """Test REST and GraphQL API endpoints for metadata frames"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)
    
    def test_parse_metadata_endpoint(self, client, sample_markdown_with_frames):
        """Test POST /parse-metadata endpoint"""
        response = client.post(
            "/api/v1/documents/parse-metadata",
            json={
                "markdown_content": sample_markdown_with_frames
            }
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert "cleaned_content" in result
        assert "metadata_frames" in result
        assert "summary" in result
        
        assert len(result["metadata_frames"]) == 7
        assert result["summary"]["total_frames"] == 7
    
    def test_generate_documentation_endpoint(self, client):
        """Test POST /generate-documentation endpoint"""
        response = client.post(
            "/api/v1/documents/generate-documentation",
            json={
                "object_type": {
                    "@type": "Class",
                    "@id": "TestEntity",
                    "@documentation": {
                        "@comment": "Test entity for API",
                        "@label": "Test Entity"
                    },
                    "id": "xsd:string",
                    "value": "xsd:integer"
                },
                "include_examples": True
            }
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["name"] == "TestEntity"
        assert result["title"] == "Test Entity"
        assert "markdown" in result
        assert len(result["metadata_frames"]) > 0
    
    def test_metadata_frame_types_endpoint(self, client):
        """Test GET /metadata-frame-types endpoint"""
        response = client.get("/api/v1/documents/metadata-frame-types")
        
        assert response.status_code == 200
        result = response.json()
        
        assert "frame_types" in result
        assert "schema" in result["frame_types"]
        assert "document" in result["frame_types"]
        
        assert "description" in result
        assert result["description"]["schema"] == "Schema definition metadata"