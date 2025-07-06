"""
Enhanced Delta Compression for Version Storage
Improves storage efficiency with advanced delta encoding algorithms
"""
from typing import Dict, Any, List, Optional, Tuple
import json
import zlib
import base64
from dataclasses import dataclass
from enum import Enum

from models.etag import create_json_patch
from common_logging.setup import get_logger

logger = get_logger(__name__)


class DeltaType(Enum):
    """Types of delta encoding"""
    FULL = "full"
    JSON_PATCH = "json_patch"
    BINARY_DIFF = "binary_diff"
    CHAIN_DELTA = "chain_delta"
    COMPRESSED_PATCH = "compressed_patch"


@dataclass
class DeltaChain:
    """Represents a chain of deltas for efficient multi-version jumps"""
    base_version: int
    target_version: int
    deltas: List[Dict[str, Any]]
    compression_ratio: float
    total_size: int


class EnhancedDeltaEncoder:
    """
    Enhanced delta encoder with multiple compression strategies
    """
    
    def __init__(
        self,
        compression_threshold: float = 0.7,
        enable_binary_diff: bool = True,
        enable_chain_optimization: bool = True,
        max_chain_length: int = 5
    ):
        self.compression_threshold = compression_threshold
        self.enable_binary_diff = enable_binary_diff
        self.enable_chain_optimization = enable_chain_optimization
        self.max_chain_length = max_chain_length
    
    def encode_delta(
        self,
        old_content: Dict[str, Any],
        new_content: Dict[str, Any],
        version_info: Optional[Dict[str, Any]] = None
    ) -> Tuple[DeltaType, bytes, int]:
        """
        Encode delta using the most efficient method
        
        Returns:
            (delta_type, encoded_delta, size_bytes)
        """
        # Try different encoding strategies
        strategies = [
            (self._try_json_patch, DeltaType.JSON_PATCH),
            (self._try_compressed_patch, DeltaType.COMPRESSED_PATCH),
        ]
        
        if self.enable_binary_diff:
            strategies.append((self._try_binary_diff, DeltaType.BINARY_DIFF))
        
        # Calculate full size for comparison
        full_json = json.dumps(new_content, sort_keys=True)
        full_size = len(full_json.encode('utf-8'))
        
        best_type = DeltaType.FULL
        best_data = full_json.encode('utf-8')
        best_size = full_size
        
        # Try each strategy
        for strategy_func, delta_type in strategies:
            try:
                encoded_data, size = strategy_func(old_content, new_content)
                
                # Check if this is better than current best
                if size < best_size * self.compression_threshold:
                    best_type = delta_type
                    best_data = encoded_data
                    best_size = size
                    
            except Exception as e:
                logger.debug(f"Strategy {delta_type} failed: {e}")
                continue
        
        # Log compression ratio
        compression_ratio = 1 - (best_size / full_size) if full_size > 0 else 0
        logger.info(
            f"Delta encoding: {best_type.value}, "
            f"size: {best_size}/{full_size} bytes, "
            f"compression: {compression_ratio:.2%}"
        )
        
        return best_type, best_data, best_size
    
    def _try_json_patch(
        self,
        old_content: Dict[str, Any],
        new_content: Dict[str, Any]
    ) -> Tuple[bytes, int]:
        """Try standard JSON patch encoding"""
        patches = create_json_patch(old_content, new_content)
        patch_json = json.dumps(patches, sort_keys=True)
        encoded = patch_json.encode('utf-8')
        return encoded, len(encoded)
    
    def _try_compressed_patch(
        self,
        old_content: Dict[str, Any],
        new_content: Dict[str, Any]
    ) -> Tuple[bytes, int]:
        """Try compressed JSON patch"""
        patches = create_json_patch(old_content, new_content)
        patch_json = json.dumps(patches, sort_keys=True)
        
        # Apply zlib compression
        compressed = zlib.compress(patch_json.encode('utf-8'), level=9)
        
        # Only use if compression is effective
        if len(compressed) < len(patch_json) * 0.8:
            return compressed, len(compressed)
        else:
            raise ValueError("Compression not effective")
    
    def _try_binary_diff(
        self,
        old_content: Dict[str, Any],
        new_content: Dict[str, Any]
    ) -> Tuple[bytes, int]:
        """Try binary diff encoding using xdelta-style algorithm"""
        # Convert to canonical JSON for consistent binary representation
        old_bytes = json.dumps(old_content, sort_keys=True).encode('utf-8')
        new_bytes = json.dumps(new_content, sort_keys=True).encode('utf-8')
        
        # Simple binary diff implementation
        # In production, consider using python-xdelta3 or similar
        diff_data = self._compute_binary_diff(old_bytes, new_bytes)
        
        return diff_data, len(diff_data)
    
    def _compute_binary_diff(self, old_bytes: bytes, new_bytes: bytes) -> bytes:
        """
        Compute binary diff between two byte sequences
        Simple implementation - for production use python-xdelta3
        """
        # This is a simplified implementation
        # Real implementation would use rolling hash for finding matches
        
        if len(old_bytes) == 0:
            return new_bytes
        
        # Find common prefix
        prefix_len = 0
        min_len = min(len(old_bytes), len(new_bytes))
        for i in range(min_len):
            if old_bytes[i] != new_bytes[i]:
                break
            prefix_len = i + 1
        
        # Find common suffix
        suffix_len = 0
        for i in range(1, min_len - prefix_len + 1):
            if old_bytes[-i] != new_bytes[-i]:
                break
            suffix_len = i
        
        # Build diff commands
        diff_commands = []
        
        if prefix_len > 0:
            diff_commands.append(('copy', 0, prefix_len))
        
        # Middle section that differs
        old_middle = old_bytes[prefix_len:len(old_bytes)-suffix_len if suffix_len > 0 else None]
        new_middle = new_bytes[prefix_len:len(new_bytes)-suffix_len if suffix_len > 0 else None]
        
        if new_middle:
            diff_commands.append(('insert', new_middle))
        
        if suffix_len > 0:
            diff_commands.append(('copy', len(old_bytes)-suffix_len, suffix_len))
        
        # Encode diff commands
        return self._encode_diff_commands(diff_commands)
    
    def _encode_diff_commands(self, commands: List[Tuple]) -> bytes:
        """Encode diff commands into bytes"""
        # Simple encoding format
        parts = []
        
        for cmd in commands:
            if cmd[0] == 'copy':
                parts.append(f"C{cmd[1]}:{cmd[2]}".encode('utf-8'))
            elif cmd[0] == 'insert':
                data_b64 = base64.b64encode(cmd[1]).decode('ascii')
                parts.append(f"I{len(cmd[1])}:{data_b64}".encode('utf-8'))
        
        return b'|'.join(parts)
    
    def decode_delta(
        self,
        old_content: Dict[str, Any],
        delta_type: DeltaType,
        delta_data: bytes
    ) -> Dict[str, Any]:
        """Decode delta back to full content"""
        if delta_type == DeltaType.FULL:
            return json.loads(delta_data.decode('utf-8'))
        
        elif delta_type == DeltaType.JSON_PATCH:
            patches = json.loads(delta_data.decode('utf-8'))
            return self._apply_json_patch(old_content, patches)
        
        elif delta_type == DeltaType.COMPRESSED_PATCH:
            decompressed = zlib.decompress(delta_data)
            patches = json.loads(decompressed.decode('utf-8'))
            return self._apply_json_patch(old_content, patches)
        
        elif delta_type == DeltaType.BINARY_DIFF:
            old_bytes = json.dumps(old_content, sort_keys=True).encode('utf-8')
            new_bytes = self._apply_binary_diff(old_bytes, delta_data)
            return json.loads(new_bytes.decode('utf-8'))
        
        else:
            raise ValueError(f"Unknown delta type: {delta_type}")
    
    def _apply_json_patch(
        self,
        content: Dict[str, Any],
        patches: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Apply JSON patch operations to content"""
        # Deep copy to avoid modifying original
        result = json.loads(json.dumps(content))
        
        for patch in patches:
            op = patch['op']
            path = patch['path'].lstrip('/')
            
            if op == 'add':
                result[path] = patch['value']
            elif op == 'replace':
                result[path] = patch['value']
            elif op == 'remove':
                if path in result:
                    del result[path]
        
        return result
    
    def _apply_binary_diff(self, old_bytes: bytes, diff_data: bytes) -> bytes:
        """Apply binary diff to reconstruct new content"""
        result = bytearray()
        
        # Parse diff commands
        commands = diff_data.split(b'|')
        
        for cmd in commands:
            if cmd.startswith(b'C'):
                # Copy command
                parts = cmd[1:].decode('utf-8').split(':')
                offset = int(parts[0])
                length = int(parts[1])
                result.extend(old_bytes[offset:offset+length])
                
            elif cmd.startswith(b'I'):
                # Insert command
                parts = cmd[1:].decode('utf-8').split(':', 1)
                length = int(parts[0])
                data = base64.b64decode(parts[1])
                result.extend(data)
        
        return bytes(result)
    
    def optimize_delta_chain(
        self,
        deltas: List[Dict[str, Any]],
        base_content: Dict[str, Any]
    ) -> DeltaChain:
        """
        Optimize a chain of deltas for efficient multi-version jumps
        """
        if not self.enable_chain_optimization:
            return None
        
        # Calculate cumulative sizes
        total_size = 0
        cumulative_content = base_content
        optimized_deltas = []
        
        for i, delta in enumerate(deltas[:self.max_chain_length]):
            # Apply delta to get next version
            if delta['delta_type'] == 'full':
                cumulative_content = json.loads(delta['delta_content'])
            else:
                patches = json.loads(delta['delta_content'])
                cumulative_content = self._apply_json_patch(cumulative_content, patches)
            
            # Calculate optimized delta from base to current
            if i > 0:  # Skip first delta
                delta_type, encoded, size = self.encode_delta(
                    base_content, cumulative_content
                )
                
                optimized_deltas.append({
                    'version': delta['to_version'],
                    'delta_type': delta_type.value,
                    'delta_content': base64.b64encode(encoded).decode('ascii'),
                    'delta_size': size
                })
                total_size += size
        
        # Calculate compression ratio
        original_size = sum(delta.get('delta_size', 0) for delta in deltas)
        compression_ratio = 1 - (total_size / original_size) if original_size > 0 else 0
        
        return DeltaChain(
            base_version=deltas[0]['from_version'],
            target_version=deltas[-1]['to_version'],
            deltas=optimized_deltas,
            compression_ratio=compression_ratio,
            total_size=total_size
        )


class DeltaStorageOptimizer:
    """
    Optimizes delta storage by analyzing access patterns
    """
    
    def __init__(self, encoder: EnhancedDeltaEncoder):
        self.encoder = encoder
        self.access_stats = defaultdict(int)
    
    def record_access(self, resource_type: str, resource_id: str, version: int):
        """Record access pattern for optimization"""
        key = f"{resource_type}:{resource_id}:{version}"
        self.access_stats[key] += 1
    
    def suggest_materialization(
        self,
        resource_type: str,
        resource_id: str,
        version_range: Tuple[int, int],
        threshold: int = 10
    ) -> List[int]:
        """
        Suggest which versions to materialize based on access patterns
        """
        materialization_candidates = []
        
        for version in range(version_range[0], version_range[1] + 1):
            key = f"{resource_type}:{resource_id}:{version}"
            if self.access_stats.get(key, 0) >= threshold:
                materialization_candidates.append(version)
        
        return materialization_candidates
    
    def analyze_delta_chains(
        self,
        deltas: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze delta chains for optimization opportunities
        """
        chain_lengths = []
        chain_sizes = []
        current_chain = []
        
        for delta in deltas:
            if delta['delta_type'] == 'full':
                if current_chain:
                    chain_lengths.append(len(current_chain))
                    chain_sizes.append(sum(d['delta_size'] for d in current_chain))
                current_chain = []
            else:
                current_chain.append(delta)
        
        if current_chain:
            chain_lengths.append(len(current_chain))
            chain_sizes.append(sum(d['delta_size'] for d in current_chain))
        
        return {
            'avg_chain_length': sum(chain_lengths) / len(chain_lengths) if chain_lengths else 0,
            'max_chain_length': max(chain_lengths) if chain_lengths else 0,
            'avg_chain_size': sum(chain_sizes) / len(chain_sizes) if chain_sizes else 0,
            'recommendation': self._get_optimization_recommendation(chain_lengths, chain_sizes)
        }
    
    def _get_optimization_recommendation(
        self,
        chain_lengths: List[int],
        chain_sizes: List[int]
    ) -> str:
        """Get optimization recommendation based on analysis"""
        if not chain_lengths:
            return "No optimization needed"
        
        avg_length = sum(chain_lengths) / len(chain_lengths)
        max_length = max(chain_lengths)
        
        if max_length > 10:
            return f"Long delta chains detected (max: {max_length}). Consider more frequent full snapshots."
        elif avg_length > 5:
            return f"Average chain length is {avg_length:.1f}. Consider chain optimization."
        else:
            return "Delta chain lengths are optimal."