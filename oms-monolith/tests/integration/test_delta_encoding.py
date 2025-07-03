"""
Integration tests for Delta Encoding with compression strategies
"""
import pytest
import json
import zlib
from typing import Dict, Any
import asyncio

from core.versioning.delta_compression import (
    EnhancedDeltaEncoder,
    DeltaType,
    CompressionMetrics
)
from core.versioning.version_service import VersionService
from shared.cache.smart_cache import SmartCache
from utils.logger import get_logger

logger = get_logger(__name__)


class TestDeltaEncodingIntegration:
    """Test suite for delta encoding functionality"""
    
    @pytest.fixture
    def encoder(self):
        """Create delta encoder instance"""
        return EnhancedDeltaEncoder(
            compression_threshold=100,
            enable_binary_diff=True
        )
    
    @pytest.fixture
    def version_service(self):
        """Create version service with mock dependencies"""
        cache = SmartCache(
            name="test_delta",
            ttl=60,
            use_redis=False  # Local cache only for tests
        )
        return VersionService(
            repo_name="test_repo",
            cache=cache
        )
    
    @pytest.fixture
    def sample_documents(self):
        """Generate sample documents for testing"""
        return {
            "small": {
                "old": {"name": "John", "age": 30, "city": "NYC"},
                "new": {"name": "John", "age": 31, "city": "Boston"}
            },
            "medium": {
                "old": {
                    "users": [{"id": i, "name": f"User{i}", "data": "x" * 50} 
                             for i in range(20)]
                },
                "new": {
                    "users": [{"id": i, "name": f"User{i}", "data": "y" * 50} 
                             for i in range(20)]
                }
            },
            "large": {
                "old": {
                    "content": "Lorem ipsum " * 1000,
                    "metadata": {"version": 1, "size": 12000}
                },
                "new": {
                    "content": "Lorem ipsum " * 1000 + " dolor sit amet",
                    "metadata": {"version": 2, "size": 12020}
                }
            },
            "binary_like": {
                "old": {"data": list(range(1000)), "checksum": "abc123"},
                "new": {"data": list(range(500, 1500)), "checksum": "def456"}
            }
        }
    
    def test_delta_type_selection(self, encoder, sample_documents):
        """Test automatic delta type selection based on content"""
        results = {}
        
        for doc_type, docs in sample_documents.items():
            delta_type, encoded, size = encoder.encode_delta(
                docs["old"], docs["new"]
            )
            results[doc_type] = {
                "type": delta_type,
                "size": size,
                "compression_ratio": size / len(json.dumps(docs["new"]))
            }
            
            # Verify we can decode
            decoded = encoder.decode_delta(docs["old"], delta_type, encoded)
            assert decoded == docs["new"], f"Failed to decode {doc_type}"
        
        # Verify type selection logic
        assert results["small"]["type"] == DeltaType.JSON_PATCH
        assert results["large"]["type"] in [DeltaType.COMPRESSED_PATCH, DeltaType.BINARY_DIFF]
        
        logger.info(f"Delta type selection results: {results}")
    
    def test_compression_efficiency(self, encoder, sample_documents):
        """Test compression efficiency for different document types"""
        metrics = CompressionMetrics()
        
        for doc_type, docs in sample_documents.items():
            # Force compressed patch
            encoder.compression_threshold = 0
            _, compressed_encoded, compressed_size = encoder.encode_delta(
                docs["old"], docs["new"]
            )
            
            # Force uncompressed patch
            encoder.compression_threshold = float('inf')
            _, uncompressed_encoded, uncompressed_size = encoder.encode_delta(
                docs["old"], docs["new"]
            )
            
            compression_ratio = 1 - (compressed_size / uncompressed_size)
            metrics.record_compression(
                doc_type,
                uncompressed_size,
                compressed_size
            )
            
            assert compression_ratio > 0, f"No compression benefit for {doc_type}"
            logger.info(f"{doc_type}: {compression_ratio:.2%} compression")
    
    def test_delta_chain_optimization(self, encoder):
        """Test delta chain optimization for multiple versions"""
        # Create version chain
        versions = [{"value": i, "data": f"version_{i}" * 10} for i in range(10)]
        
        # Create individual deltas
        deltas = []
        for i in range(1, len(versions)):
            _, encoded, _ = encoder.encode_delta(versions[i-1], versions[i])
            deltas.append(encoded)
        
        # Test chain optimization
        chain_deltas = encoder.optimize_delta_chain(
            versions[0],
            versions[-1],
            [(i, d) for i, d in enumerate(deltas)]
        )
        
        # Should create optimized path
        assert len(chain_deltas) < len(deltas)
        
        # Verify result
        result = versions[0]
        for delta in chain_deltas:
            result = encoder.decode_delta(result, DeltaType.JSON_PATCH, delta)
        assert result == versions[-1]
    
    @pytest.mark.asyncio
    async def test_version_service_integration(self, version_service, sample_documents):
        """Test delta encoding integration with version service"""
        doc = sample_documents["medium"]["old"]
        
        # Create multiple versions
        versions = []
        for i in range(5):
            doc["users"][0]["name"] = f"UpdatedUser{i}"
            version = await version_service.create_version(
                "test_resource",
                doc.copy(),
                f"Update {i}",
                {"author": "test"}
            )
            versions.append(version)
        
        # Verify delta storage
        for i in range(1, len(versions)):
            delta = await version_service._get_delta(
                versions[i-1]["version"],
                versions[i]["version"]
            )
            assert delta is not None
            assert "encoded" in delta
            assert "type" in delta
    
    def test_binary_diff_fallback(self, encoder):
        """Test binary diff fallback for non-JSON content"""
        # Create binary-like data
        old_data = {"binary": b"Hello World" * 100}
        new_data = {"binary": b"Hello Python" * 100}
        
        # Convert to JSON-serializable format
        old_json = {"binary": old_data["binary"].hex()}
        new_json = {"binary": new_data["binary"].hex()}
        
        delta_type, encoded, size = encoder.encode_delta(old_json, new_json)
        
        # Should use binary diff for efficiency
        assert delta_type == DeltaType.BINARY_DIFF
        
        # Verify decode
        decoded = encoder.decode_delta(old_json, delta_type, encoded)
        assert decoded == new_json
    
    def test_error_handling(self, encoder):
        """Test error handling in delta encoding/decoding"""
        # Test encoding with invalid input
        with pytest.raises(Exception):
            encoder.encode_delta(None, {"key": "value"})
        
        # Test decoding with corrupted delta
        with pytest.raises(Exception):
            encoder.decode_delta(
                {"key": "value"},
                DeltaType.COMPRESSED_PATCH,
                b"corrupted data"
            )
        
        # Test unsupported delta type
        with pytest.raises(ValueError):
            encoder.decode_delta(
                {"key": "value"},
                "INVALID_TYPE",
                b"data"
            )
    
    def test_performance_metrics(self, encoder, sample_documents):
        """Test performance metrics collection"""
        import time
        
        metrics = {
            "encoding_times": [],
            "decoding_times": [],
            "sizes": []
        }
        
        for _ in range(10):
            for doc_type, docs in sample_documents.items():
                # Measure encoding
                start = time.time()
                delta_type, encoded, size = encoder.encode_delta(
                    docs["old"], docs["new"]
                )
                encoding_time = time.time() - start
                
                # Measure decoding
                start = time.time()
                decoded = encoder.decode_delta(docs["old"], delta_type, encoded)
                decoding_time = time.time() - start
                
                metrics["encoding_times"].append(encoding_time)
                metrics["decoding_times"].append(decoding_time)
                metrics["sizes"].append(size)
        
        # Verify performance
        avg_encoding = sum(metrics["encoding_times"]) / len(metrics["encoding_times"])
        avg_decoding = sum(metrics["decoding_times"]) / len(metrics["decoding_times"])
        
        assert avg_encoding < 0.1, f"Encoding too slow: {avg_encoding:.3f}s"
        assert avg_decoding < 0.1, f"Decoding too slow: {avg_decoding:.3f}s"
        
        logger.info(f"Performance - Encoding: {avg_encoding:.3f}s, Decoding: {avg_decoding:.3f}s")
    
    @pytest.mark.asyncio
    async def test_concurrent_delta_operations(self, encoder):
        """Test concurrent delta encoding operations"""
        tasks = []
        
        # Create concurrent encoding tasks
        for i in range(20):
            old = {"id": i, "data": f"old_data_{i}" * 100}
            new = {"id": i, "data": f"new_data_{i}" * 100}
            
            task = asyncio.create_task(
                asyncio.to_thread(encoder.encode_delta, old, new)
            )
            tasks.append((task, old))
        
        # Wait for all encodings
        results = []
        for task, old in tasks:
            delta_type, encoded, size = await task
            results.append((delta_type, encoded, size, old))
        
        # Verify all succeeded
        assert len(results) == 20
        
        # Decode all concurrently
        decode_tasks = []
        for delta_type, encoded, _, old in results:
            task = asyncio.create_task(
                asyncio.to_thread(encoder.decode_delta, old, delta_type, encoded)
            )
            decode_tasks.append(task)
        
        decoded_results = await asyncio.gather(*decode_tasks)
        assert len(decoded_results) == 20


class TestDeltaEncodingEdgeCases:
    """Test edge cases and special scenarios"""
    
    @pytest.fixture
    def encoder(self):
        return EnhancedDeltaEncoder()
    
    def test_empty_delta(self, encoder):
        """Test encoding when documents are identical"""
        doc = {"key": "value", "nested": {"a": 1, "b": 2}}
        delta_type, encoded, size = encoder.encode_delta(doc, doc)
        
        # Should produce minimal delta
        assert size < 50  # Very small delta
        decoded = encoder.decode_delta(doc, delta_type, encoded)
        assert decoded == doc
    
    def test_complete_replacement(self, encoder):
        """Test when new document is completely different"""
        old = {"a": 1, "b": 2, "c": 3}
        new = {"x": "foo", "y": "bar", "z": "baz"}
        
        delta_type, encoded, size = encoder.encode_delta(old, new)
        decoded = encoder.decode_delta(old, delta_type, encoded)
        assert decoded == new
    
    def test_deeply_nested_changes(self, encoder):
        """Test delta encoding with deeply nested structures"""
        old = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "value": "old"
                        }
                    }
                }
            }
        }
        
        new = json.loads(json.dumps(old))  # Deep copy
        new["level1"]["level2"]["level3"]["level4"]["value"] = "new"
        
        delta_type, encoded, size = encoder.encode_delta(old, new)
        decoded = encoder.decode_delta(old, delta_type, encoded)
        assert decoded == new
        
        # Delta should be efficient for small nested change
        assert size < len(json.dumps(new)) / 2
    
    def test_array_operations(self, encoder):
        """Test delta encoding with array modifications"""
        test_cases = [
            # Append
            ({"arr": [1, 2, 3]}, {"arr": [1, 2, 3, 4]}),
            # Remove
            ({"arr": [1, 2, 3, 4]}, {"arr": [1, 2, 3]}),
            # Insert
            ({"arr": [1, 3, 4]}, {"arr": [1, 2, 3, 4]}),
            # Reorder
            ({"arr": [1, 2, 3]}, {"arr": [3, 2, 1]}),
        ]
        
        for old, new in test_cases:
            delta_type, encoded, size = encoder.encode_delta(old, new)
            decoded = encoder.decode_delta(old, delta_type, encoded)
            assert decoded == new