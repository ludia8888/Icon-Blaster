"""
Graph data repository layer for efficient TerminusDB graph queries.
Handles batch operations, query optimization, and data transformation.
"""
from typing import List, Dict, Any, Optional, Set, Tuple
from abc import ABC, abstractmethod
import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from ..database.clients.terminus_db import TerminusDBClient
from ..resilience.unified_circuit_breaker import circuit_breaker
from common_logging.setup import get_logger

logger = get_logger(__name__)


@dataclass
class GraphNode:
    """Represents a node in the graph."""
    id: str
    type: str
    properties: Dict[str, Any]


@dataclass
class GraphEdge:
    """Represents an edge in the graph."""
    source_id: str
    target_id: str
    edge_type: str
    properties: Dict[str, Any]
    weight: float = 1.0


@dataclass
class SubgraphData:
    """Container for subgraph data."""
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    metadata: Dict[str, Any]


class GraphQueryBuilder:
    """
    Optimized WOQL query builder for graph operations.
    Focuses on batch operations and constraint filtering.
    """
    
    @staticmethod
    def build_batch_subgraph_query(node_ids: List[str], 
                                 node_type_filters: Optional[List[str]] = None,
                                 edge_type_filters: Optional[List[str]] = None,
                                 forbidden_node_types: Optional[List[str]] = None,
                                 forbidden_edge_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Build optimized WOQL query for batch subgraph retrieval.
        Uses IN clauses and filters to minimize DB round trips.
        """
        
        # Base node query with batch IN clause
        node_query = {
            "@type": "And",
            "and": [
                {
                    "@type": "Triple",
                    "subject": {"@type": "Variable", "name": "Node"},
                    "predicate": {"@type": "NodeValue", "node": "@id"},
                    "object": {"@type": "Variable", "name": "NodeId"}
                },
                {
                    "@type": "Member",
                    "member": {"@type": "Variable", "name": "NodeId"},
                    "list": node_ids
                },
                {
                    "@type": "Triple",
                    "subject": {"@type": "Variable", "name": "Node"},
                    "predicate": {"@type": "NodeValue", "node": "@type"},
                    "object": {"@type": "Variable", "name": "NodeType"}
                }
            ]
        }
        
        # Add node type filters
        node_filters = []
        if node_type_filters:
            node_type_filter = {
                "@type": "Member",
                "member": {"@type": "Variable", "name": "NodeType"},
                "list": node_type_filters
            }
            node_filters.append(node_type_filter)
        
        if forbidden_node_types:
            forbidden_filter = {
                "@type": "Not",
                "query": {
                    "@type": "Member",
                    "member": {"@type": "Variable", "name": "NodeType"},
                    "list": forbidden_node_types
                }
            }
            node_filters.append(forbidden_filter)
        
        if node_filters:
            node_query["and"].extend(node_filters)
        
        # Batch edge query
        edge_query = {
            "@type": "And",
            "and": [
                {
                    "@type": "Triple",
                    "subject": {"@type": "Variable", "name": "SourceNode"},
                    "predicate": {"@type": "Variable", "name": "EdgeType"},
                    "object": {"@type": "Variable", "name": "TargetNode"}
                },
                {
                    "@type": "Member",
                    "member": {"@type": "Variable", "name": "SourceNode"},
                    "list": node_ids
                },
                {
                    "@type": "Member",
                    "member": {"@type": "Variable", "name": "TargetNode"},
                    "list": node_ids
                }
            ]
        }
        
        # Add edge type filters
        edge_filters = []
        if edge_type_filters:
            edge_type_filter = {
                "@type": "Member",
                "member": {"@type": "Variable", "name": "EdgeType"},
                "list": edge_type_filters
            }
            edge_filters.append(edge_type_filter)
        
        if forbidden_edge_types:
            forbidden_edge_filter = {
                "@type": "Not",
                "query": {
                    "@type": "Member",
                    "member": {"@type": "Variable", "name": "EdgeType"},
                    "list": forbidden_edge_types
                }
            }
            edge_filters.append(forbidden_edge_filter)
        
        if edge_filters:
            edge_query["and"].extend(edge_filters)
        
        # Combine node and edge queries
        combined_query = {
            "@type": "Or",
            "or": [node_query, edge_query]
        }
        
        return combined_query
    
    @staticmethod
    def build_neighborhood_query(center_node_id: str, 
                               max_hops: int = 2,
                               node_type_filters: Optional[List[str]] = None,
                               edge_type_filters: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Build query for node neighborhood discovery.
        Uses recursive traversal with hop limits.
        """
        
        # Build recursive path query
        path_query = {
            "@type": "Path",
            "subject": {"@type": "NodeValue", "node": center_node_id},
            "path": {
                "@type": "Star",
                "star": {
                    "@type": "Variable", 
                    "name": "EdgeType"
                },
                "min": 1,
                "max": max_hops
            },
            "object": {"@type": "Variable", "name": "ReachableNode"}
        }
        
        # Add filters if specified
        filters = []
        
        if node_type_filters or edge_type_filters:
            # Add type constraints to the path traversal
            if node_type_filters:
                node_filter = {
                    "@type": "Triple",
                    "subject": {"@type": "Variable", "name": "ReachableNode"},
                    "predicate": {"@type": "NodeValue", "node": "@type"},
                    "object": {"@type": "Variable", "name": "NodeType"}
                }
                type_constraint = {
                    "@type": "Member",
                    "member": {"@type": "Variable", "name": "NodeType"},
                    "list": node_type_filters
                }
                filters.extend([node_filter, type_constraint])
            
            if edge_type_filters:
                edge_filter = {
                    "@type": "Member",
                    "member": {"@type": "Variable", "name": "EdgeType"},
                    "list": edge_type_filters
                }
                filters.append(edge_filter)
        
        if filters:
            return {
                "@type": "And",
                "and": [path_query] + filters
            }
        
        return path_query
    
    @staticmethod
    def build_connection_discovery_query(source_nodes: List[str], 
                                       target_nodes: List[str],
                                       max_depth: int = 3) -> Dict[str, Any]:
        """
        Build optimized query for discovering connections between node sets.
        """
        
        return {
            "@type": "Path",
            "subject": {"@type": "Variable", "name": "Source"},
            "path": {
                "@type": "Star",
                "star": {"@type": "Variable", "name": "Predicate"},
                "min": 1,
                "max": max_depth
            },
            "object": {"@type": "Variable", "name": "Target"},
            "and": [
                {
                    "@type": "Member",
                    "member": {"@type": "Variable", "name": "Source"},
                    "list": source_nodes
                },
                {
                    "@type": "Member",
                    "member": {"@type": "Variable", "name": "Target"},
                    "list": target_nodes
                }
            ]
        }


class IGraphRepository(ABC):
    """Abstract interface for graph data access."""
    
    @abstractmethod
    async def get_subgraph(self, node_ids: List[str], **filters) -> SubgraphData:
        """Retrieve subgraph containing specified nodes and their connections."""
        pass
    
    @abstractmethod
    async def get_node_neighborhood(self, node_id: str, max_hops: int = 2, **filters) -> SubgraphData:
        """Get neighborhood of a specific node."""
        pass
    
    @abstractmethod
    async def discover_connections(self, source_nodes: List[str], target_nodes: List[str], 
                                 max_depth: int = 3) -> List[Dict[str, Any]]:
        """Discover connections between two sets of nodes."""
        pass
    
    @abstractmethod
    async def get_graph_statistics(self) -> Dict[str, Any]:
        """Get graph-wide statistics."""
        pass


class TerminusGraphRepository(IGraphRepository):
    """
    Production graph repository using TerminusDB with optimized batch queries.
    """
    
    def __init__(self, terminus_client: TerminusDBClient):
        self.terminus_client = terminus_client
        self.query_builder = GraphQueryBuilder()
    
    @circuit_breaker("terminus_db")
    async def get_subgraph(self, node_ids: List[str], 
                          node_type_filters: Optional[List[str]] = None,
                          edge_type_filters: Optional[List[str]] = None,
                          forbidden_node_types: Optional[List[str]] = None,
                          forbidden_edge_types: Optional[List[str]] = None) -> SubgraphData:
        """
        Efficiently retrieve subgraph using single batch query.
        Replaces N² individual queries with optimized WOQL.
        """
        
        if not node_ids:
            return SubgraphData(nodes=[], edges=[], metadata={})
        
        try:
            # Build optimized batch query
            woql_query = self.query_builder.build_batch_subgraph_query(
                node_ids=node_ids,
                node_type_filters=node_type_filters,
                edge_type_filters=edge_type_filters,
                forbidden_node_types=forbidden_node_types,
                forbidden_edge_types=forbidden_edge_types
            )
            
            # Execute single batch query
            start_time = datetime.utcnow()
            raw_results = await self.terminus_client.query(woql_query)
            query_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Transform results to domain objects
            nodes_map = {}
            edges = []
            
            for item in raw_results:
                if self._is_node_result(item):
                    node = self._transform_to_graph_node(item)
                    if node and node.id not in nodes_map:
                        nodes_map[node.id] = node
                
                elif self._is_edge_result(item):
                    edge = self._transform_to_graph_edge(item)
                    if edge and edge.source_id in node_ids and edge.target_id in node_ids:
                        edges.append(edge)
            
            nodes = list(nodes_map.values())
            
            metadata = {
                "query_time_seconds": query_time,
                "nodes_requested": len(node_ids),
                "nodes_found": len(nodes),
                "edges_found": len(edges),
                "filters_applied": {
                    "node_types": node_type_filters,
                    "edge_types": edge_type_filters,
                    "forbidden_node_types": forbidden_node_types,
                    "forbidden_edge_types": forbidden_edge_types
                }
            }
            
            logger.info(f"Subgraph query completed: {len(nodes)} nodes, {len(edges)} edges in {query_time:.3f}s")
            
            return SubgraphData(nodes=nodes, edges=edges, metadata=metadata)
            
        except Exception as e:
            logger.error(f"Failed to retrieve subgraph for {len(node_ids)} nodes: {e}")
            raise
    
    @circuit_breaker("terminus_db")
    async def get_node_neighborhood(self, node_id: str, max_hops: int = 2,
                                  node_type_filters: Optional[List[str]] = None,
                                  edge_type_filters: Optional[List[str]] = None) -> SubgraphData:
        """Get neighborhood of a specific node using path traversal."""
        
        try:
            woql_query = self.query_builder.build_neighborhood_query(
                center_node_id=node_id,
                max_hops=max_hops,
                node_type_filters=node_type_filters,
                edge_type_filters=edge_type_filters
            )
            
            start_time = datetime.utcnow()
            raw_results = await self.terminus_client.query(woql_query)
            query_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Extract reachable node IDs and get full subgraph
            reachable_node_ids = {node_id}  # Include center node
            for item in raw_results:
                if "ReachableNode" in item:
                    reachable_node_ids.add(item["ReachableNode"])
            
            # Get complete subgraph data
            subgraph = await self.get_subgraph(
                node_ids=list(reachable_node_ids),
                node_type_filters=node_type_filters,
                edge_type_filters=edge_type_filters
            )
            
            # Update metadata
            subgraph.metadata.update({
                "center_node": node_id,
                "max_hops": max_hops,
                "neighborhood_query_time": query_time
            })
            
            return subgraph
            
        except Exception as e:
            logger.error(f"Failed to get neighborhood for node {node_id}: {e}")
            raise
    
    @circuit_breaker("terminus_db")
    async def discover_connections(self, source_nodes: List[str], target_nodes: List[str], 
                                 max_depth: int = 3) -> List[Dict[str, Any]]:
        """Discover connections between two sets of nodes."""
        
        try:
            woql_query = self.query_builder.build_connection_discovery_query(
                source_nodes=source_nodes,
                target_nodes=target_nodes,
                max_depth=max_depth
            )
            
            start_time = datetime.utcnow()
            raw_results = await self.terminus_client.query(woql_query)
            query_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Group connections by source-target pairs
            connections = []
            for item in raw_results:
                if "Source" in item and "Target" in item:
                    connection = {
                        "source": item["Source"],
                        "target": item["Target"],
                        "path_exists": True,
                        "metadata": {
                            "max_depth_searched": max_depth,
                            "query_time": query_time
                        }
                    }
                    connections.append(connection)
            
            logger.info(f"Connection discovery: found {len(connections)} connections in {query_time:.3f}s")
            
            return connections
            
        except Exception as e:
            logger.error(f"Failed to discover connections: {e}")
            raise
    
    async def get_graph_statistics(self) -> Dict[str, Any]:
        """Get graph-wide statistics."""
        
        try:
            # Query for node count by type
            node_count_query = {
                "@type": "Triple",
                "subject": {"@type": "Variable", "name": "Node"},
                "predicate": {"@type": "NodeValue", "node": "@type"},
                "object": {"@type": "Variable", "name": "NodeType"}
            }
            
            # Query for edge count by type
            edge_count_query = {
                "@type": "Triple",
                "subject": {"@type": "Variable", "name": "Source"},
                "predicate": {"@type": "Variable", "name": "EdgeType"},
                "object": {"@type": "Variable", "name": "Target"}
            }
            
            # Execute queries in parallel
            node_results, edge_results = await asyncio.gather(
                self.terminus_client.query(node_count_query),
                self.terminus_client.query(edge_count_query),
                return_exceptions=True
            )
            
            # Process results
            node_type_counts = {}
            if not isinstance(node_results, Exception):
                for item in node_results:
                    node_type = item.get("NodeType", "Unknown")
                    node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1
            
            edge_type_counts = {}
            if not isinstance(edge_results, Exception):
                for item in edge_results:
                    edge_type = item.get("EdgeType", "Unknown")
                    edge_type_counts[edge_type] = edge_type_counts.get(edge_type, 0) + 1
            
            return {
                "total_nodes": sum(node_type_counts.values()),
                "total_edges": sum(edge_type_counts.values()),
                "node_type_distribution": node_type_counts,
                "edge_type_distribution": edge_type_counts,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get graph statistics: {e}")
            raise
    
    def _is_node_result(self, item: Dict[str, Any]) -> bool:
        """Check if query result represents a node."""
        return "@id" in item and "NodeType" in item
    
    def _is_edge_result(self, item: Dict[str, Any]) -> bool:
        """Check if query result represents an edge."""
        return "SourceNode" in item and "TargetNode" in item and "EdgeType" in item
    
    def _transform_to_graph_node(self, item: Dict[str, Any]) -> Optional[GraphNode]:
        """Transform query result to GraphNode."""
        try:
            node_id = item.get("@id")
            node_type = item.get("NodeType", "Unknown")
            
            if not node_id:
                return None
            
            # Extract properties (exclude system fields)
            properties = {k: v for k, v in item.items() 
                         if not k.startswith("@") and k not in ["NodeType"]}
            
            return GraphNode(
                id=node_id,
                type=node_type,
                properties=properties
            )
            
        except Exception as e:
            logger.warning(f"Failed to transform node result: {e}")
            return None
    
    def _transform_to_graph_edge(self, item: Dict[str, Any]) -> Optional[GraphEdge]:
        """Transform query result to GraphEdge."""
        try:
            source_id = item.get("SourceNode")
            target_id = item.get("TargetNode")
            edge_type = item.get("EdgeType", "Unknown")
            
            if not source_id or not target_id:
                return None
            
            # Extract properties and weight
            properties = {k: v for k, v in item.items() 
                         if k not in ["SourceNode", "TargetNode", "EdgeType"]}
            
            # Calculate weight from properties
            weight = self._extract_edge_weight(properties)
            
            return GraphEdge(
                source_id=source_id,
                target_id=target_id,
                edge_type=edge_type,
                properties=properties,
                weight=weight
            )
            
        except Exception as e:
            logger.warning(f"Failed to transform edge result: {e}")
            return None
    
    def _extract_edge_weight(self, properties: Dict[str, Any]) -> float:
        """Extract edge weight from properties with safe parsing."""
        weight = 1.0
        
        try:
            if 'weight' in properties:
                weight = float(properties['weight'])
            elif 'strength' in properties:
                strength = float(properties['strength'])
                weight = 1.0 / max(strength, 0.1)
            elif 'frequency' in properties:
                frequency = float(properties['frequency'])
                weight = 1.0 / max(frequency, 0.1)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse edge weight, using default 1.0: {e}")
        
        return max(weight, 0.001)  # Ensure positive weight


class CachedGraphRepository(IGraphRepository):
    """
    Cached wrapper for graph repository with intelligent cache management.
    """
    
    def __init__(self, base_repository: IGraphRepository, cache_manager):
        self.base_repository = base_repository
        self.cache = cache_manager
        self.cache_ttl = 1800  # 30 minutes
    
    async def get_subgraph(self, node_ids: List[str], **filters) -> SubgraphData:
        """Get subgraph with caching."""
        cache_key = self._generate_cache_key("subgraph", node_ids, filters)
        
        # Try cache first
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for subgraph: {cache_key}")
            return SubgraphData(**cached_result)
        
        # Cache miss - query repository
        result = await self.base_repository.get_subgraph(node_ids, **filters)
        
        # Cache the result
        await self.cache.set(cache_key, {
            "nodes": [{"id": n.id, "type": n.type, "properties": n.properties} for n in result.nodes],
            "edges": [{"source_id": e.source_id, "target_id": e.target_id, 
                      "edge_type": e.edge_type, "properties": e.properties, "weight": e.weight} 
                     for e in result.edges],
            "metadata": result.metadata
        }, ttl=self.cache_ttl)
        
        logger.debug(f"Cached subgraph result: {cache_key}")
        return result
    
    async def get_node_neighborhood(self, node_id: str, max_hops: int = 2, **filters) -> SubgraphData:
        """Get node neighborhood with caching."""
        cache_key = self._generate_cache_key("neighborhood", [node_id], {"max_hops": max_hops, **filters})
        
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            return SubgraphData(**cached_result)
        
        result = await self.base_repository.get_node_neighborhood(node_id, max_hops, **filters)
        
        await self.cache.set(cache_key, {
            "nodes": [{"id": n.id, "type": n.type, "properties": n.properties} for n in result.nodes],
            "edges": [{"source_id": e.source_id, "target_id": e.target_id, 
                      "edge_type": e.edge_type, "properties": e.properties, "weight": e.weight} 
                     for e in result.edges],
            "metadata": result.metadata
        }, ttl=self.cache_ttl)
        
        return result
    
    async def discover_connections(self, source_nodes: List[str], target_nodes: List[str], 
                                 max_depth: int = 3) -> List[Dict[str, Any]]:
        """Discover connections with caching."""
        cache_key = self._generate_cache_key("connections", 
                                           source_nodes + target_nodes, 
                                           {"max_depth": max_depth})
        
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            return cached_result
        
        result = await self.base_repository.discover_connections(source_nodes, target_nodes, max_depth)
        
        await self.cache.set(cache_key, result, ttl=self.cache_ttl)
        return result
    
    async def get_graph_statistics(self) -> Dict[str, Any]:
        """Get graph statistics with caching."""
        cache_key = "graph_statistics"
        
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            return cached_result
        
        result = await self.base_repository.get_graph_statistics()
        
        # Cache statistics for shorter time (5 minutes)
        await self.cache.set(cache_key, result, ttl=300)
        return result
    
    def _generate_cache_key(self, operation: str, node_ids: List[str], 
                          filters: Dict[str, Any]) -> str:
        """Generate stable cache key using SHA256."""
        key_data = {
            "operation": operation,
            "node_ids": sorted(node_ids),
            "filters": filters
        }
        
        # Create stable hash
        key_string = json.dumps(key_data, sort_keys=True)
        hash_object = hashlib.sha256(key_string.encode())
        return f"graph:{operation}:{hash_object.hexdigest()[:16]}"