"""
Graph Index Generator for OMS

Implements FR-LK-IDX and GF-02 requirements from Ontology_Requirements_Document.md
Generates automatic graph indexes for link types to optimize traversal performance.
"""

import hashlib
import json
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
from pydantic import BaseModel, Field

from models.domain import LinkType, ObjectType
from common_logging.setup import get_logger

logger = get_logger(__name__)


class GraphIndex(BaseModel):
    """Represents a graph index for optimized traversal"""
    index_id: str = Field(..., description="Unique index identifier")
    link_type_id: str = Field(..., description="Link type this index belongs to")
    index_type: str = Field(..., description="Type of index (src_dst, dst_src, composite)")
    key_pattern: str = Field(..., description="Key pattern for the index")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Performance metrics
    estimated_cardinality: Optional[int] = None
    avg_traversal_time_ms: Optional[float] = None
    last_optimized: Optional[datetime] = None


class TraversalMetadata(BaseModel):
    """Metadata for graph traversal optimization"""
    link_type_id: str
    source_type_id: str
    destination_type_id: str
    
    # Traversal settings
    transitive_closure: bool = Field(False, description="Enable transitive closure")
    cascade_depth: int = Field(1, description="Max cascade depth (0=unlimited)")
    bidirectional: bool = Field(False, description="Allow bidirectional traversal")
    
    # Index hints
    preferred_index: Optional[str] = None
    index_selectivity: Optional[float] = None
    
    # Propagation rules (for GF-03 integration)
    permission_inheritance: Optional[Dict[str, Any]] = None
    state_propagation: Optional[Dict[str, Any]] = None


class GraphIndexGenerator:
    """
    Generates and manages graph indexes for link types
    Implements automatic indexing strategy for optimal traversal
    """
    
    def __init__(self):
        self.indexes: Dict[str, GraphIndex] = {}
        self.traversal_metadata: Dict[str, TraversalMetadata] = {}
        
    def generate_indexes_for_link_type(
        self, 
        link_type: LinkType,
        source_type: ObjectType,
        destination_type: ObjectType
    ) -> List[GraphIndex]:
        """
        Generate indexes for a link type
        
        Creates multiple indexes:
        1. Source -> Destination index (forward traversal)
        2. Destination -> Source index (reverse traversal)
        3. Composite indexes for complex queries
        """
        indexes = []
        
        # Generate index ID
        base_id = f"{link_type.id}_{source_type.id}_{destination_type.id}"
        
        # 1. Forward index (src -> dst)
        forward_index = GraphIndex(
            index_id=f"idx_fwd_{base_id}",
            link_type_id=link_type.id,
            index_type="src_dst",
            key_pattern=f"{source_type.id}:*->{destination_type.id}:*",
            metadata={
                "source_type": source_type.id,
                "destination_type": destination_type.id,
                "direction": "forward"
            }
        )
        indexes.append(forward_index)
        
        # 2. Reverse index (dst -> src)
        reverse_index = GraphIndex(
            index_id=f"idx_rev_{base_id}",
            link_type_id=link_type.id,
            index_type="dst_src",
            key_pattern=f"{destination_type.id}:*<-{source_type.id}:*",
            metadata={
                "source_type": destination_type.id,
                "destination_type": source_type.id,
                "direction": "reverse"
            }
        )
        indexes.append(reverse_index)
        
        # 3. Composite index for multi-hop queries
        if link_type.cardinality in ["ONE_TO_MANY", "MANY_TO_MANY"]:
            composite_index = GraphIndex(
                index_id=f"idx_comp_{base_id}",
                link_type_id=link_type.id,
                index_type="composite",
                key_pattern=f"{source_type.id}:*->*->{destination_type.id}:*",
                metadata={
                    "source_type": source_type.id,
                    "destination_type": destination_type.id,
                    "cardinality": link_type.cardinality,
                    "supports_multi_hop": True
                }
            )
            indexes.append(composite_index)
        
        # Store indexes
        for index in indexes:
            self.indexes[index.index_id] = index
            
        logger.info(f"Generated {len(indexes)} indexes for link type {link_type.id}")
        return indexes
    
    def calculate_src_dst_key(
        self,
        source_id: str,
        destination_id: str,
        link_type_id: str
    ) -> str:
        """
        Calculate deterministic key for source-destination pair
        Used for efficient index lookups
        """
        # Create a stable hash key
        key_components = [link_type_id, source_id, destination_id]
        key_string = ":".join(sorted(key_components))
        
        # Generate hash for consistent key
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        
        return f"{link_type_id}:{source_id}->{destination_id}:{key_hash}"
    
    def generate_traversal_metadata(
        self,
        link_type: LinkType,
        source_type: ObjectType,
        destination_type: ObjectType
    ) -> TraversalMetadata:
        """
        Generate traversal metadata for optimization
        Includes settings for transitive closure and cascade depth
        """
        metadata = TraversalMetadata(
            link_type_id=link_type.id,
            source_type_id=source_type.id,
            destination_type_id=destination_type.id,
            transitive_closure=link_type.metadata.get("transitive_closure", False),
            cascade_depth=link_type.metadata.get("cascade_depth", 1),
            bidirectional=link_type.is_bidirectional
        )
        
        # Add propagation rules if present (for GF-03)
        if hasattr(link_type, 'permission_inheritance'):
            metadata.permission_inheritance = link_type.permission_inheritance
        if hasattr(link_type, 'state_propagation'):
            metadata.state_propagation = link_type.state_propagation
        
        # Store metadata
        self.traversal_metadata[link_type.id] = metadata
        
        return metadata
    
    def optimize_for_latency(
        self,
        link_type_id: str,
        target_latency_ms: float = 200.0
    ) -> Dict[str, Any]:
        """
        Optimize indexes for target latency requirement
        Implements NFR-PERF-1: Graph traversal latency ≤ 200ms
        """
        optimization_results = {
            "link_type_id": link_type_id,
            "target_latency_ms": target_latency_ms,
            "optimizations_applied": []
        }
        
        # Get all indexes for this link type
        link_indexes = [
            idx for idx in self.indexes.values() 
            if idx.link_type_id == link_type_id
        ]
        
        for index in link_indexes:
            # Apply optimizations based on index type
            if index.index_type == "src_dst":
                # Optimize forward traversal
                self._optimize_forward_index(index)
                optimization_results["optimizations_applied"].append({
                    "index_id": index.index_id,
                    "optimization": "forward_traversal_cache"
                })
                
            elif index.index_type == "composite":
                # Optimize multi-hop queries
                self._optimize_composite_index(index)
                optimization_results["optimizations_applied"].append({
                    "index_id": index.index_id,
                    "optimization": "multi_hop_materialization"
                })
        
        return optimization_results
    
    def _optimize_forward_index(self, index: GraphIndex) -> None:
        """Apply forward index optimizations"""
        # In a real implementation, this would:
        # 1. Add caching hints
        # 2. Pre-compute common paths
        # 3. Add bloom filters for existence checks
        index.metadata["cache_enabled"] = True
        index.metadata["bloom_filter"] = True
        index.last_optimized = datetime.utcnow()
    
    def _optimize_composite_index(self, index: GraphIndex) -> None:
        """Apply composite index optimizations"""
        # In a real implementation, this would:
        # 1. Materialize frequent multi-hop paths
        # 2. Add path compression
        # 3. Implement path caching
        index.metadata["path_materialization"] = True
        index.metadata["path_compression"] = True
        index.last_optimized = datetime.utcnow()
    
    def get_traversal_path(
        self,
        source_id: str,
        destination_id: str,
        link_type_id: str,
        max_depth: int = 5
    ) -> List[Dict[str, str]]:
        """
        Get traversal path between source and destination
        Returns list of nodes in the path
        """
        # This is a simplified implementation
        # In reality, this would query the graph database
        path = [
            {"id": source_id, "type": "source"},
            {"id": destination_id, "type": "destination"}
        ]
        
        return path
    
    def estimate_cardinality(
        self,
        link_type_id: str,
        source_type_id: str
    ) -> int:
        """
        Estimate cardinality for a link type from a source type
        Used for query optimization
        """
        # In a real implementation, this would:
        # 1. Query statistics from the database
        # 2. Use sampling for large datasets
        # 3. Cache results for performance
        
        # Placeholder implementation
        metadata = self.traversal_metadata.get(link_type_id)
        if metadata:
            # Estimate based on link type characteristics
            if "MANY" in str(metadata):
                return 1000  # High cardinality
            else:
                return 10   # Low cardinality
        
        return 100  # Default estimate
    
    def create_index_storage_spec(self) -> Dict[str, Any]:
        """
        Create storage specification for indexes
        This spec is used by TerminusDB for physical storage
        """
        storage_spec = {
            "indexes": [],
            "metadata": {
                "version": "1.0",
                "created_at": datetime.utcnow().isoformat(),
                "index_count": len(self.indexes)
            }
        }
        
        for index in self.indexes.values():
            storage_spec["indexes"].append({
                "id": index.index_id,
                "type": index.index_type,
                "key_pattern": index.key_pattern,
                "storage_hints": {
                    "compression": "lz4",
                    "cache_policy": "lru",
                    "partition_key": index.metadata.get("source_type", "default")
                }
            })
        
        return storage_spec
    
    def validate_index_consistency(self) -> List[Dict[str, Any]]:
        """
        Validate consistency of all indexes
        Returns list of any issues found
        """
        issues = []
        
        # Check for orphaned indexes
        for index_id, index in self.indexes.items():
            if index.link_type_id not in self.traversal_metadata:
                issues.append({
                    "type": "orphaned_index",
                    "index_id": index_id,
                    "message": f"Index {index_id} references non-existent link type {index.link_type_id}"
                })
        
        # Check for missing indexes
        for link_type_id, metadata in self.traversal_metadata.items():
            expected_indexes = [
                f"idx_fwd_{link_type_id}_{metadata.source_type_id}_{metadata.destination_type_id}",
                f"idx_rev_{link_type_id}_{metadata.source_type_id}_{metadata.destination_type_id}"
            ]
            
            for expected_id in expected_indexes:
                if not any(idx.index_id.startswith(expected_id.split('_')[0:2]) for idx in self.indexes.values()):
                    issues.append({
                        "type": "missing_index",
                        "link_type_id": link_type_id,
                        "message": f"Missing expected index pattern for {link_type_id}"
                    })
        
        return issues


# Global instance
graph_index_generator = GraphIndexGenerator()