"""
Integration tests for @unfoldable Documents feature
"""
import pytest
import json
from typing import Dict, Any, List

from core.documents.unfoldable import (
    UnfoldLevel,
    UnfoldContext,
    UnfoldableDocument,
    UnfoldableProcessor
)
from api.v1.document_routes import router
from api.graphql.document_schema import DocumentQueries
from common_logging.setup import get_logger

logger = get_logger(__name__)


class TestUnfoldableDocumentsIntegration:
    """Test suite for unfoldable documents functionality"""
    
    @pytest.fixture
    def sample_large_document(self):
        """Create a large document with various unfoldable sections"""
        return {
            "id": "doc-123",
            "title": "Large Document",
            "metadata": {
                "version": "1.0",
                "author": "Test Suite"
            },
            "@unfoldable": {
                "large_text": {
                    "summary": "Lorem ipsum text (10KB)",
                    "size": 10240,
                    "content": "Lorem ipsum dolor sit amet " * 500
                }
            },
            "sections": [
                {
                    "id": "section-1",
                    "title": "Introduction",
                    "content": "This is a brief introduction"
                },
                {
                    "id": "section-2", 
                    "title": "Data Section",
                    "@unfoldable": {
                        "large_dataset": {
                            "summary": "Dataset with 1000 records",
                            "item_count": 1000,
                            "content": [
                                {"id": i, "value": f"item_{i}", "data": "x" * 100}
                                for i in range(1000)
                            ]
                        }
                    }
                }
            ],
            "nested": {
                "level1": {
                    "level2": {
                        "@unfoldable": {
                            "deep_content": {
                                "summary": "Deeply nested large content",
                                "content": {"key": "value"} 
                            }
                        }
                    }
                }
            }
        }
    
    @pytest.fixture
    def unfold_contexts(self):
        """Different unfold contexts for testing"""
        return {
            "collapsed": UnfoldContext(
                level=UnfoldLevel.COLLAPSED,
                include_summaries=True
            ),
            "shallow": UnfoldContext(
                level=UnfoldLevel.SHALLOW,
                max_depth=1,
                include_summaries=True
            ),
            "deep": UnfoldContext(
                level=UnfoldLevel.DEEP,
                max_depth=10
            ),
            "custom": UnfoldContext(
                level=UnfoldLevel.CUSTOM,
                paths={"/sections/1/@unfoldable/large_dataset"},
                include_summaries=True
            ),
            "size_limited": UnfoldContext(
                level=UnfoldLevel.DEEP,
                size_threshold=5000,
                array_threshold=100
            )
        }
    
    def test_unfoldable_document_creation(self, sample_large_document):
        """Test creating and processing unfoldable documents"""
        doc = UnfoldableDocument(sample_large_document)
        
        # Get unfoldable paths
        paths = doc.get_unfoldable_paths()
        assert len(paths) == 3
        
        # Verify path detection
        path_locations = [p["path"] for p in paths]
        assert "/@unfoldable/large_text" in path_locations
        assert "/sections/1/@unfoldable/large_dataset" in path_locations
        assert "/nested/level1/level2/@unfoldable/deep_content" in path_locations
    
    def test_fold_collapsed_level(self, sample_large_document, unfold_contexts):
        """Test folding with COLLAPSED level - only summaries"""
        doc = UnfoldableDocument(sample_large_document)
        folded = doc.fold(unfold_contexts["collapsed"])
        
        # Check that content is replaced with summaries
        assert folded["@unfoldable"]["large_text"]["summary"] == "Lorem ipsum text (10KB)"
        assert "content" not in folded["@unfoldable"]["large_text"]
        
        # Check nested unfoldable
        section = folded["sections"][1]
        assert section["@unfoldable"]["large_dataset"]["summary"] == "Dataset with 1000 records"
        assert "content" not in section["@unfoldable"]["large_dataset"]
    
    def test_fold_shallow_level(self, sample_large_document, unfold_contexts):
        """Test folding with SHALLOW level - immediate children only"""
        doc = UnfoldableDocument(sample_large_document)
        folded = doc.fold(unfold_contexts["shallow"])
        
        # Top level unfoldable should be included
        assert "content" in folded["@unfoldable"]["large_text"]
        
        # Deeper unfoldables should be collapsed
        section = folded["sections"][1]
        assert "content" not in section["@unfoldable"]["large_dataset"]
        assert section["@unfoldable"]["large_dataset"]["summary"] == "Dataset with 1000 records"
    
    def test_fold_deep_level(self, sample_large_document, unfold_contexts):
        """Test folding with DEEP level - all content included"""
        doc = UnfoldableDocument(sample_large_document)
        folded = doc.fold(unfold_contexts["deep"])
        
        # All unfoldable content should be included
        assert "content" in folded["@unfoldable"]["large_text"]
        assert "content" in folded["sections"][1]["@unfoldable"]["large_dataset"]
        assert "content" in folded["nested"]["level1"]["level2"]["@unfoldable"]["deep_content"]
    
    def test_fold_custom_paths(self, sample_large_document, unfold_contexts):
        """Test folding with CUSTOM paths - selective unfolding"""
        doc = UnfoldableDocument(sample_large_document)
        folded = doc.fold(unfold_contexts["custom"])
        
        # Only specified path should be unfolded
        assert "content" not in folded["@unfoldable"]["large_text"]
        assert "content" in folded["sections"][1]["@unfoldable"]["large_dataset"]
        assert "content" not in folded["nested"]["level1"]["level2"]["@unfoldable"]["deep_content"]
    
    def test_size_threshold_folding(self, sample_large_document, unfold_contexts):
        """Test size-based automatic folding"""
        doc = UnfoldableDocument(sample_large_document)
        folded = doc.fold(unfold_contexts["size_limited"])
        
        # Large content should be auto-folded
        large_text = folded["@unfoldable"]["large_text"]
        if "content" in large_text:
            # If included, should be truncated or summarized
            assert len(str(large_text["content"])) < 10240
    
    def test_unfold_specific_path(self, sample_large_document):
        """Test unfolding a specific path"""
        doc = UnfoldableDocument(sample_large_document)
        
        # Unfold specific path
        content = doc.unfold_path("/sections/1/@unfoldable/large_dataset")
        assert content is not None
        assert "content" in content
        assert len(content["content"]) == 1000
        
        # Try non-existent path
        content = doc.unfold_path("/non/existent/path")
        assert content is None
    
    def test_prepare_document(self):
        """Test preparing a document with unfoldable annotations"""
        original = {
            "title": "Test Document",
            "large_content": "x" * 10000,
            "nested": {
                "big_array": list(range(1000))
            }
        }
        
        # Prepare with specific paths
        paths = ["/large_content", "/nested/big_array"]
        prepared = UnfoldableProcessor.prepare_document(original, paths)
        
        # Verify annotations added
        assert "@unfoldable" in prepared
        assert "large_content" in prepared["@unfoldable"]
        assert "@unfoldable" in prepared["nested"]
        assert "big_array" in prepared["nested"]["@unfoldable"]
    
    def test_extract_unfoldable_content(self, sample_large_document):
        """Test extracting unfoldable content from document"""
        main_doc, unfoldable_content = UnfoldableProcessor.extract_unfoldable_content(
            sample_large_document
        )
        
        # Main document should not have @unfoldable fields
        assert "@unfoldable" not in main_doc
        assert "@unfoldable" not in main_doc["sections"][1]
        
        # Unfoldable content should be extracted
        assert len(unfoldable_content) == 3
        assert "/@unfoldable/large_text" in unfoldable_content
        assert "/sections/1/@unfoldable/large_dataset" in unfoldable_content
    
    def test_automatic_unfoldable_detection(self):
        """Test automatic detection of large content"""
        doc_content = {
            "small_field": "small content",
            "large_field": "x" * 15000,  # Over default threshold
            "big_array": list(range(500)),  # Over array threshold
            "normal_array": [1, 2, 3, 4, 5]
        }
        
        # Process with auto-detection
        processor = UnfoldableProcessor()
        processed = processor.auto_mark_unfoldable(
            doc_content,
            size_threshold=10240,
            array_threshold=100
        )
        
        # Large fields should be marked
        assert "@unfoldable" in processed
        assert "large_field" in processed["@unfoldable"]
        assert "big_array" in processed["@unfoldable"]
        assert "small_field" not in processed.get("@unfoldable", {})
        assert "normal_array" not in processed.get("@unfoldable", {})
    
    def test_unfoldable_with_transformations(self, sample_large_document):
        """Test unfoldable documents with content transformations"""
        class CustomUnfoldableDocument(UnfoldableDocument):
            def transform_content(self, content: Any, path: str) -> Any:
                """Apply custom transformation to unfolded content"""
                if isinstance(content, list) and len(content) > 100:
                    # Return paginated view
                    return {
                        "total": len(content),
                        "page": 1,
                        "items": content[:50]
                    }
                return content
        
        doc = CustomUnfoldableDocument(sample_large_document)
        
        # Unfold with transformation
        context = UnfoldContext(level=UnfoldLevel.DEEP)
        folded = doc.fold(context)
        
        # Check transformation applied
        dataset = folded["sections"][1]["@unfoldable"]["large_dataset"]["content"]
        assert isinstance(dataset, dict)
        assert dataset["total"] == 1000
        assert len(dataset["items"]) == 50
    
    def test_circular_reference_handling(self):
        """Test handling of circular references in documents"""
        # Create document with circular reference
        doc_content = {"id": "root"}
        doc_content["self_ref"] = doc_content  # Circular reference
        doc_content["@unfoldable"] = {
            "data": {
                "content": {"nested": doc_content}  # Another circular ref
            }
        }
        
        # Should handle without infinite recursion
        doc = UnfoldableDocument(doc_content)
        context = UnfoldContext(level=UnfoldLevel.DEEP)
        
        # This should not cause stack overflow
        folded = doc.fold(context)
        assert folded is not None
    
    @pytest.mark.asyncio
    async def test_concurrent_unfold_operations(self, sample_large_document):
        """Test concurrent unfold operations"""
        import asyncio
        
        doc = UnfoldableDocument(sample_large_document)
        contexts = [
            UnfoldContext(level=UnfoldLevel.COLLAPSED),
            UnfoldContext(level=UnfoldLevel.SHALLOW),
            UnfoldContext(level=UnfoldLevel.DEEP),
            UnfoldContext(level=UnfoldLevel.CUSTOM, paths={"/sections/1/@unfoldable/large_dataset"})
        ]
        
        # Create concurrent fold operations
        tasks = [
            asyncio.create_task(asyncio.to_thread(doc.fold, ctx))
            for ctx in contexts
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Verify all succeeded with different results
        assert len(results) == 4
        assert all(r is not None for r in results)
        
        # Each should have different content based on context
        collapsed = results[0]
        deep = results[2]
        
        # Collapsed should have summaries only
        assert "content" not in collapsed["@unfoldable"]["large_text"]
        # Deep should have full content
        assert "content" in deep["@unfoldable"]["large_text"]
    
    def test_performance_large_documents(self, sample_large_document):
        """Test performance with very large documents"""
        import time
        
        # Create a very large document
        large_doc = {
            "sections": []
        }
        
        # Add many unfoldable sections
        for i in range(100):
            large_doc["sections"].append({
                "id": f"section-{i}",
                "@unfoldable": {
                    f"data_{i}": {
                        "summary": f"Large dataset {i}",
                        "content": [{"id": j, "data": "x" * 100} for j in range(100)]
                    }
                }
            })
        
        doc = UnfoldableDocument(large_doc)
        
        # Measure folding performance
        start = time.time()
        folded = doc.fold(UnfoldContext(level=UnfoldLevel.COLLAPSED))
        collapsed_time = time.time() - start
        
        start = time.time()
        folded = doc.fold(UnfoldContext(level=UnfoldLevel.DEEP))
        deep_time = time.time() - start
        
        # Collapsed should be much faster than deep
        assert collapsed_time < deep_time / 10
        assert collapsed_time < 0.1  # Should be very fast
        
        logger.info(f"Performance - Collapsed: {collapsed_time:.3f}s, Deep: {deep_time:.3f}s")


class TestUnfoldableDocumentsAPI:
    """Test REST API endpoints for unfoldable documents"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)
    
    def test_unfold_endpoint(self, client, sample_large_document):
        """Test POST /unfold endpoint"""
        response = client.post(
            "/api/v1/documents/unfold",
            json={
                "content": sample_large_document,
                "context": {
                    "level": "SHALLOW",
                    "max_depth": 2,
                    "include_summaries": True
                }
            }
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert "content" in result
        assert "unfoldable_paths" in result
        assert len(result["unfoldable_paths"]) > 0
        assert result["stats"]["unfold_level"] == "SHALLOW"
    
    def test_unfold_path_endpoint(self, client, sample_large_document):
        """Test POST /unfold-path endpoint"""
        response = client.post(
            "/api/v1/documents/unfold-path",
            json={
                "content": sample_large_document,
                "path": "/sections/1/@unfoldable/large_dataset"
            }
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["path"] == "/sections/1/@unfoldable/large_dataset"
        assert "content" in result["content"]
        assert result["type"] == "dict"
    
    def test_prepare_unfoldable_endpoint(self, client):
        """Test POST /prepare-unfoldable endpoint"""
        response = client.post(
            "/api/v1/documents/prepare-unfoldable",
            json={
                "content": {
                    "title": "Test",
                    "large_field": "x" * 10000
                },
                "unfoldable_paths": ["/large_field"]
            }
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert "@unfoldable" in result["content"]
        assert result["annotations_added"] == 1