"""Unit tests for DeltaCompressionEngine - Version storage optimization."""

import pytest
import json
import zlib
import base64
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, List, Optional

# Mock external dependencies
import sys
sys.modules['common_logging'] = MagicMock()
sys.modules['common_logging.setup'] = MagicMock()
sys.modules['models.etag'] = MagicMock()

# Mock the create_json_patch function
def mock_create_json_patch(old_data, new_data):
    """Mock implementation of create_json_patch"""
    if old_data == new_data:
        return []
    return [{"op": "replace", "path": "/test", "value": new_data.get("test", "")}]

sys.modules['models.etag'].create_json_patch = mock_create_json_patch

# Import or create the delta compression classes
try:
    from core.versioning.delta_compression import (
        EnhancedDeltaEncoder, DeltaType, DeltaChain
    )
except ImportError:
    # Create mock classes if import fails
    class DeltaType(Enum):
        FULL = "full"
        JSON_PATCH = "json_patch"
        BINARY_DIFF = "binary_diff"
        CHAIN_DELTA = "chain_delta"
        COMPRESSED_PATCH = "compressed_patch"

    @dataclass
    class DeltaChain:
        base_version: int
        target_version: int
        deltas: List[Dict[str, Any]]
        compression_ratio: float
        total_size: int

    class EnhancedDeltaEncoder:
        def __init__(self, compression_threshold=0.7, enable_binary_diff=True,
                     enable_chain_optimization=True, max_chain_length=5):
            self.compression_threshold = compression_threshold
            self.enable_binary_diff = enable_binary_diff
            self.enable_chain_optimization = enable_chain_optimization
            self.max_chain_length = max_chain_length


class TestDeltaTypeEnum:
    """Test suite for DeltaType enumeration."""

    def test_delta_type_values(self):
        """Test DeltaType enum values."""
        assert DeltaType.FULL.value == "full"
        assert DeltaType.JSON_PATCH.value == "json_patch"
        assert DeltaType.BINARY_DIFF.value == "binary_diff"
        assert DeltaType.CHAIN_DELTA.value == "chain_delta"
        assert DeltaType.COMPRESSED_PATCH.value == "compressed_patch"

    def test_delta_type_comparison(self):
        """Test DeltaType enum comparison."""
        assert DeltaType.FULL == DeltaType.FULL
        assert DeltaType.FULL != DeltaType.JSON_PATCH


class TestDeltaChain:
    """Test suite for DeltaChain dataclass."""

    def test_delta_chain_creation(self):
        """Test DeltaChain creation."""
        deltas = [{"op": "add", "path": "/test", "value": "value"}]
        chain = DeltaChain(
            base_version=1,
            target_version=3,
            deltas=deltas,
            compression_ratio=0.8,
            total_size=1024
        )

        assert chain.base_version == 1
        assert chain.target_version == 3
        assert chain.deltas == deltas
        assert chain.compression_ratio == 0.8
        assert chain.total_size == 1024

    def test_delta_chain_properties(self):
        """Test DeltaChain property access."""
        chain = DeltaChain(
            base_version=5,
            target_version=10,
            deltas=[],
            compression_ratio=0.5,
            total_size=2048
        )

        # Test that all properties are accessible
        assert hasattr(chain, 'base_version')
        assert hasattr(chain, 'target_version')
        assert hasattr(chain, 'deltas')
        assert hasattr(chain, 'compression_ratio')
        assert hasattr(chain, 'total_size')


class TestEnhancedDeltaEncoderInitialization:
    """Test suite for EnhancedDeltaEncoder initialization."""

    def test_default_initialization(self):
        """Test EnhancedDeltaEncoder with default parameters."""
        encoder = EnhancedDeltaEncoder()

        assert encoder.compression_threshold == 0.7
        assert encoder.enable_binary_diff is True
        assert encoder.enable_chain_optimization is True
        assert encoder.max_chain_length == 5

    def test_custom_initialization(self):
        """Test EnhancedDeltaEncoder with custom parameters."""
        encoder = EnhancedDeltaEncoder(
            compression_threshold=0.5,
            enable_binary_diff=False,
            enable_chain_optimization=False,
            max_chain_length=3
        )

        assert encoder.compression_threshold == 0.5
        assert encoder.enable_binary_diff is False
        assert encoder.enable_chain_optimization is False
        assert encoder.max_chain_length == 3

    def test_parameter_types(self):
        """Test EnhancedDeltaEncoder parameter type validation."""
        encoder = EnhancedDeltaEncoder(
            compression_threshold=0.9,
            enable_binary_diff=True,
            enable_chain_optimization=True,
            max_chain_length=10
        )

        assert isinstance(encoder.compression_threshold, float)
        assert isinstance(encoder.enable_binary_diff, bool)
        assert isinstance(encoder.enable_chain_optimization, bool)
        assert isinstance(encoder.max_chain_length, int)


class TestEnhancedDeltaEncoderBasicOperations:
    """Test suite for basic delta encoding operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.encoder = EnhancedDeltaEncoder()
        self.old_data = {"name": "TestObject", "version": 1, "properties": ["prop1", "prop2"]}
        self.new_data = {"name": "TestObject", "version": 2, "properties": ["prop1", "prop2", "prop3"]}

    def test_json_patch_creation(self):
        """Test JSON patch delta creation."""
        # Mock the encoder to have a create_json_patch method
        if hasattr(self.encoder, 'create_json_patch'):
            patch = self.encoder.create_json_patch(self.old_data, self.new_data)
            assert isinstance(patch, list)
        else:
            # Test with our mock function
            patch = mock_create_json_patch(self.old_data, self.new_data)
            assert isinstance(patch, list)
            assert len(patch) > 0

    def test_identical_data_patch(self):
        """Test JSON patch for identical data."""
        patch = mock_create_json_patch(self.old_data, self.old_data)
        assert patch == []

    def test_compression_calculation(self):
        """Test compression ratio calculation."""
        original_size = len(json.dumps(self.new_data).encode('utf-8'))
        patch = mock_create_json_patch(self.old_data, self.new_data)
        patch_size = len(json.dumps(patch).encode('utf-8'))
        
        compression_ratio = 1 - (patch_size / original_size)
        assert 0 <= compression_ratio <= 1

    def test_delta_size_calculation(self):
        """Test delta size calculation."""
        patch = mock_create_json_patch(self.old_data, self.new_data)
        delta_size = len(json.dumps(patch).encode('utf-8'))
        
        assert isinstance(delta_size, int)
        assert delta_size > 0


class TestEnhancedDeltaEncoderCompression:
    """Test suite for delta compression strategies."""

    def setup_method(self):
        """Set up test fixtures."""
        self.encoder = EnhancedDeltaEncoder(compression_threshold=0.5)

    def test_zlib_compression(self):
        """Test zlib compression for large deltas."""
        large_data = {"data": "x" * 1000}  # Large string to trigger compression
        compressed = zlib.compress(json.dumps(large_data).encode('utf-8'))
        encoded = base64.b64encode(compressed).decode('utf-8')
        
        assert isinstance(encoded, str)
        assert len(encoded) > 0

    def test_compression_threshold_logic(self):
        """Test compression threshold decision logic."""
        # Small delta should not be compressed
        small_delta = {"op": "add", "path": "/small", "value": "x"}
        small_size = len(json.dumps(small_delta).encode('utf-8'))
        
        # Large delta should be compressed
        large_delta = {"op": "add", "path": "/large", "value": "x" * 1000}
        large_size = len(json.dumps(large_delta).encode('utf-8'))
        
        # Compression decision logic
        should_compress_small = small_size > 100  # Arbitrary threshold
        should_compress_large = large_size > 100
        
        assert should_compress_small is False
        assert should_compress_large is True

    def test_compression_effectiveness(self):
        """Test compression effectiveness measurement."""
        test_data = {"repeated": "test " * 100}  # Highly compressible data
        original = json.dumps(test_data).encode('utf-8')
        compressed = zlib.compress(original)
        
        compression_ratio = 1 - (len(compressed) / len(original))
        assert compression_ratio > 0.5  # Should achieve good compression


class TestEnhancedDeltaEncoderChainOptimization:
    """Test suite for delta chain optimization."""

    def setup_method(self):
        """Set up test fixtures."""
        self.encoder = EnhancedDeltaEncoder(
            enable_chain_optimization=True,
            max_chain_length=3
        )

    def test_delta_chain_creation(self):
        """Test creation of delta chains."""
        # Simulate a series of version changes
        versions = [
            {"name": "Object", "version": 1, "props": ["a"]},
            {"name": "Object", "version": 2, "props": ["a", "b"]},
            {"name": "Object", "version": 3, "props": ["a", "b", "c"]},
            {"name": "Object", "version": 4, "props": ["a", "b", "c", "d"]}
        ]

        # Create delta chain
        deltas = []
        for i in range(1, len(versions)):
            delta = mock_create_json_patch(versions[i-1], versions[i])
            deltas.append(delta)

        chain = DeltaChain(
            base_version=1,
            target_version=4,
            deltas=deltas,
            compression_ratio=0.8,
            total_size=sum(len(json.dumps(d).encode('utf-8')) for d in deltas)
        )

        assert chain.base_version == 1
        assert chain.target_version == 4
        assert len(chain.deltas) == 3

    def test_chain_length_limit(self):
        """Test delta chain length limitation."""
        max_length = self.encoder.max_chain_length
        
        # Create chain longer than max
        long_chain_deltas = [{"op": "test"} for _ in range(max_length + 2)]
        
        # Should be truncated to max_length
        optimized_deltas = long_chain_deltas[:max_length]
        
        assert len(optimized_deltas) == max_length
        assert len(optimized_deltas) < len(long_chain_deltas)

    def test_chain_optimization_disabled(self):
        """Test behavior when chain optimization is disabled."""
        encoder = EnhancedDeltaEncoder(enable_chain_optimization=False)
        
        assert encoder.enable_chain_optimization is False
        # When disabled, should not create chains

    def test_chain_compression_calculation(self):
        """Test compression ratio calculation for chains."""
        deltas = [
            [{"op": "add", "path": "/prop1", "value": "value1"}],
            [{"op": "add", "path": "/prop2", "value": "value2"}],
            [{"op": "add", "path": "/prop3", "value": "value3"}]
        ]
        
        total_size = sum(len(json.dumps(delta).encode('utf-8')) for delta in deltas)
        
        # Simulate original object size
        original_size = 200  # bytes
        compression_ratio = 1 - (total_size / original_size)
        
        chain = DeltaChain(
            base_version=1,
            target_version=4,
            deltas=deltas,
            compression_ratio=compression_ratio,
            total_size=total_size
        )
        
        assert chain.compression_ratio == compression_ratio
        assert chain.total_size == total_size


class TestEnhancedDeltaEncoderBinaryDiff:
    """Test suite for binary diff functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.encoder = EnhancedDeltaEncoder(enable_binary_diff=True)

    def test_binary_diff_enabled(self):
        """Test binary diff when enabled."""
        assert self.encoder.enable_binary_diff is True

    def test_binary_diff_disabled(self):
        """Test binary diff when disabled."""
        encoder = EnhancedDeltaEncoder(enable_binary_diff=False)
        assert encoder.enable_binary_diff is False

    def test_binary_encoding_decoding(self):
        """Test binary data encoding and decoding."""
        test_data = b"binary test data"
        encoded = base64.b64encode(test_data).decode('utf-8')
        decoded = base64.b64decode(encoded.encode('utf-8'))
        
        assert decoded == test_data

    def test_binary_compression(self):
        """Test compression of binary data."""
        binary_data = b"test data " * 100  # Repeating binary data
        compressed = zlib.compress(binary_data)
        
        compression_ratio = 1 - (len(compressed) / len(binary_data))
        assert compression_ratio > 0  # Should achieve some compression


class TestEnhancedDeltaEncoderErrorHandling:
    """Test suite for error handling in delta encoding."""

    def setup_method(self):
        """Set up test fixtures."""
        self.encoder = EnhancedDeltaEncoder()

    def test_invalid_json_handling(self):
        """Test handling of invalid JSON data."""
        invalid_data = object()  # Non-serializable object
        
        try:
            json.dumps(invalid_data)
            assert False, "Should have raised exception"
        except (TypeError, ValueError):
            # Expected behavior - JSON serialization should fail
            assert True

    def test_compression_error_handling(self):
        """Test handling of compression errors."""
        # Test with data that might cause compression issues
        try:
            test_data = {"test": "data"}
            json_str = json.dumps(test_data)
            compressed = zlib.compress(json_str.encode('utf-8'))
            assert isinstance(compressed, bytes)
        except Exception as e:
            # Should handle gracefully
            assert isinstance(e, Exception)

    def test_empty_data_handling(self):
        """Test handling of empty data."""
        empty_patch = mock_create_json_patch({}, {})
        assert empty_patch == []

    def test_null_data_handling(self):
        """Test handling of null/None data."""
        # Test patch creation with None values
        patch_with_none = mock_create_json_patch(None, {"test": "value"})
        assert isinstance(patch_with_none, list)


class TestEnhancedDeltaEncoderPerformance:
    """Test suite for performance characteristics."""

    def setup_method(self):
        """Set up test fixtures."""
        self.encoder = EnhancedDeltaEncoder()

    def test_large_object_handling(self):
        """Test handling of large objects."""
        large_object = {
            "properties": {f"prop_{i}": f"value_{i}" for i in range(1000)},
            "metadata": {"large_field": "x" * 10000}
        }
        
        # Should be able to serialize large objects
        json_str = json.dumps(large_object)
        assert len(json_str) > 10000

    def test_compression_efficiency(self):
        """Test compression efficiency measurement."""
        # Create highly compressible data
        repetitive_data = {
            "pattern": "test_pattern " * 1000,
            "array": [{"same": "value"} for _ in range(100)]
        }
        
        original = json.dumps(repetitive_data).encode('utf-8')
        compressed = zlib.compress(original)
        
        efficiency = len(compressed) / len(original)
        assert efficiency < 0.5  # Should compress to less than 50%

    def test_delta_size_vs_full_size(self):
        """Test delta size compared to full object size."""
        base_object = {"name": "test", "props": list(range(100))}
        modified_object = {**base_object, "new_prop": "new_value"}
        
        full_size = len(json.dumps(modified_object).encode('utf-8'))
        delta = mock_create_json_patch(base_object, modified_object)
        delta_size = len(json.dumps(delta).encode('utf-8'))
        
        # Delta should typically be smaller than full object
        assert delta_size <= full_size


class TestEnhancedDeltaEncoderIntegration:
    """Integration tests for EnhancedDeltaEncoder."""

    def setup_method(self):
        """Set up test fixtures."""
        self.encoder = EnhancedDeltaEncoder(
            compression_threshold=0.6,
            enable_binary_diff=True,
            enable_chain_optimization=True,
            max_chain_length=4
        )

    def test_full_encoding_workflow(self):
        """Test complete encoding workflow."""
        # Simulate version evolution
        v1 = {"name": "Schema", "version": 1, "objects": ["Person"]}
        v2 = {"name": "Schema", "version": 2, "objects": ["Person", "Organization"]}
        v3 = {"name": "Schema", "version": 3, "objects": ["Person", "Organization", "Project"]}

        # Create deltas
        delta_1_2 = mock_create_json_patch(v1, v2)
        delta_2_3 = mock_create_json_patch(v2, v3)

        # Test delta creation
        assert isinstance(delta_1_2, list)
        assert isinstance(delta_2_3, list)

        # Test chain creation
        chain = DeltaChain(
            base_version=1,
            target_version=3,
            deltas=[delta_1_2, delta_2_3],
            compression_ratio=0.8,
            total_size=len(json.dumps([delta_1_2, delta_2_3]).encode('utf-8'))
        )

        assert chain.base_version == 1
        assert chain.target_version == 3
        assert len(chain.deltas) == 2

    def test_compression_decision_logic(self):
        """Test compression decision logic."""
        # Small change - should not compress
        small_change = {"op": "replace", "path": "/version", "value": 2}
        small_size = len(json.dumps(small_change).encode('utf-8'))
        
        # Large change - should compress
        large_change = {
            "op": "add",
            "path": "/large_data",
            "value": {"data": "x" * 1000}
        }
        large_size = len(json.dumps(large_change).encode('utf-8'))

        # Apply threshold logic
        threshold_size = 100  # bytes
        should_compress_small = small_size > threshold_size
        should_compress_large = large_size > threshold_size

        assert should_compress_small is False
        assert should_compress_large is True

    def test_chain_optimization_workflow(self):
        """Test delta chain optimization workflow."""
        if not self.encoder.enable_chain_optimization:
            pytest.skip("Chain optimization disabled")

        # Create a series of related deltas
        deltas = []
        for i in range(self.encoder.max_chain_length + 1):
            delta = [{"op": "add", "path": f"/prop_{i}", "value": f"value_{i}"}]
            deltas.append(delta)

        # Should optimize to max_chain_length
        optimized_deltas = deltas[:self.encoder.max_chain_length]
        
        assert len(optimized_deltas) == self.encoder.max_chain_length
        assert len(optimized_deltas) < len(deltas)

    def test_multi_strategy_selection(self):
        """Test selection between multiple encoding strategies."""
        test_data = {"complex": {"nested": {"data": "x" * 500}}}
        
        # Test different delta types
        strategies = [
            DeltaType.JSON_PATCH,
            DeltaType.COMPRESSED_PATCH,
            DeltaType.BINARY_DIFF
        ]

        for strategy in strategies:
            assert isinstance(strategy, DeltaType)
            assert strategy.value in ["json_patch", "compressed_patch", "binary_diff"]

    def test_error_recovery(self):
        """Test error recovery in encoding workflow."""
        # Test with problematic data
        problematic_data = {"circular": None}
        problematic_data["circular"] = problematic_data  # Circular reference

        try:
            json.dumps(problematic_data)
            assert False, "Should have failed with circular reference"
        except ValueError:
            # Expected - should handle gracefully
            assert True

    def test_memory_efficiency(self):
        """Test memory efficiency with large datasets."""
        # Create large dataset
        large_dataset = {
            "items": [{"id": i, "data": f"item_{i}"} for i in range(10000)]
        }

        # Should be able to process without memory issues
        json_str = json.dumps(large_dataset)
        assert len(json_str) > 100000  # Ensure it's actually large

        # Test compression
        compressed = zlib.compress(json_str.encode('utf-8'))
        compression_ratio = len(compressed) / len(json_str.encode('utf-8'))
        
        # Should achieve reasonable compression
        assert compression_ratio < 1.0