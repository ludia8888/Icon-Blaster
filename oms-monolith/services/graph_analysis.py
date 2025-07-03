"""
Graph Analysis Service - Domain service for advanced graph operations.
Separated from presentation layer for better testability and reusability.
"""
from typing import List, Dict, Any, Optional, Set, Tuple, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict, deque
import hashlib
import json
from datetime import datetime

import networkx as nx
from cachetools import TTLCache

from ..core.graph.repositories import IGraphRepository, SubgraphData, GraphNode, GraphEdge
from ..shared.cache.smart_cache import SmartCache
from ..core.resilience.unified_circuit_breaker import unified_circuit_breaker
from ..core.events.unified_publisher import UnifiedEventPublisher
from ..middleware.common.metrics import Counter, Histogram, Gauge
from ..infra.tracing.jaeger_adapter import trace_graph_operation, trace_path_analysis, get_tracing_manager
from utils.logger import get_logger

logger = get_logger(__name__)

# Metrics
path_query_counter = Counter("graph_path_queries_total", "Total path queries executed")
path_query_duration = Histogram("graph_path_query_duration_seconds", "Path query execution time")
cache_hit_counter = Counter("graph_cache_hits_total", "Graph cache hits")
cache_miss_counter = Counter("graph_cache_misses_total", "Graph cache misses")
active_graph_size = Gauge("graph_nodes_active", "Number of nodes in active graphs")

# Thread pool for CPU-intensive NetworkX operations
_cpu_thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="graph-cpu")


class TraversalDirection(Enum):
    FORWARD = "forward"
    BACKWARD = "backward"
    BIDIRECTIONAL = "bidirectional"


class PathStrategy(Enum):
    SHORTEST_PATH = "shortest"
    ALL_PATHS = "all"
    WEIGHTED_PATH = "weighted"
    CONSTRAINED_PATH = "constrained"
    K_SHORTEST_PATHS = "k_shortest"


@dataclass
class PathConstraint:
    """Constraints for path traversal with validation."""
    max_depth: Optional[int] = None
    min_depth: Optional[int] = None
    allowed_node_types: Optional[List[str]] = None
    forbidden_node_types: Optional[List[str]] = None
    allowed_edge_types: Optional[List[str]] = None
    forbidden_edge_types: Optional[List[str]] = None
    node_filters: Optional[Dict[str, Any]] = None
    edge_filters: Optional[Dict[str, Any]] = None
    max_weight: Optional[float] = None
    min_weight: Optional[float] = None
    
    def __post_init__(self):
        """Validate constraints after initialization."""
        if self.max_depth is not None and self.max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        if self.min_depth is not None and self.min_depth < 1:
            raise ValueError("min_depth must be >= 1")
        if (self.min_depth is not None and self.max_depth is not None and 
            self.min_depth > self.max_depth):
            raise ValueError("min_depth cannot be greater than max_depth")


@dataclass
class PathNode:
    """Represents a node in a graph path."""
    id: str
    type: str
    properties: Dict[str, Any]
    depth: int
    weight: Optional[float] = None


@dataclass
class PathEdge:
    """Represents an edge in a graph path."""
    source_id: str
    target_id: str
    edge_type: str
    properties: Dict[str, Any]
    weight: float


@dataclass
class GraphPath:
    """Represents a complete path through the graph."""
    nodes: List[PathNode]
    edges: List[PathEdge]
    total_weight: float
    path_length: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeepLinkingQuery:
    """Deep linking query specification with validation."""
    source_node_id: str
    target_node_id: Optional[str] = None
    strategy: PathStrategy = PathStrategy.SHORTEST_PATH
    direction: TraversalDirection = TraversalDirection.FORWARD
    max_paths: int = 10
    constraints: Optional[PathConstraint] = None
    include_metadata: bool = True
    optimize_for_performance: bool = True
    k_value: int = 5  # For K-shortest paths
    
    def __post_init__(self):
        """Validate query parameters."""
        if self.max_paths < 1:
            raise ValueError("max_paths must be >= 1")
        if self.k_value < 1:
            raise ValueError("k_value must be >= 1")
        if not self.source_node_id:
            raise ValueError("source_node_id cannot be empty")


class NetworkXGraphBuilder:
    """
    Builds NetworkX graphs from repository data with direction awareness.
    """
    
    @staticmethod
    def build_graph(subgraph_data: SubgraphData, direction: TraversalDirection) -> nx.Graph:
        """Build NetworkX graph with proper direction handling."""
        
        # Choose graph type based on direction
        if direction == TraversalDirection.BIDIRECTIONAL:
            graph = nx.Graph()  # Undirected
        else:
            graph = nx.DiGraph()  # Directed
        
        # Add nodes
        for node in subgraph_data.nodes:
            graph.add_node(node.id, **{
                "type": node.type,
                "properties": node.properties
            })
        
        # Add edges with direction consideration
        for edge in subgraph_data.edges:
            if direction == TraversalDirection.BACKWARD:
                # Reverse edge direction for backward traversal
                graph.add_edge(edge.target_id, edge.source_id, **{
                    "edge_type": edge.edge_type,
                    "properties": edge.properties,
                    "weight": edge.weight,
                    "original_direction": "reversed"
                })
            else:
                graph.add_edge(edge.source_id, edge.target_id, **{
                    "edge_type": edge.edge_type,
                    "properties": edge.properties,
                    "weight": edge.weight,
                    "original_direction": "forward"
                })
        
        return graph
    
    @staticmethod
    def get_neighbors(graph: nx.Graph, node: str, direction: TraversalDirection) -> List[str]:
        """Get neighbors with direction awareness."""
        if isinstance(graph, nx.DiGraph):
            if direction == TraversalDirection.BACKWARD:
                return list(graph.predecessors(node))
            else:  # FORWARD or when building from reversed edges
                return list(graph.successors(node))
        else:  # Undirected graph
            return list(graph.neighbors(node))


class PathValidator:
    """
    Validates paths against constraints with early pruning.
    """
    
    def __init__(self, constraints: Optional[PathConstraint] = None):
        self.constraints = constraints
    
    def is_valid_node(self, node_data: Dict[str, Any]) -> bool:
        """Check if node satisfies constraints."""
        if not self.constraints:
            return True
            
        node_type = node_data.get('type', 'Unknown')
        
        # Type constraints
        if self.constraints.allowed_node_types and node_type not in self.constraints.allowed_node_types:
            return False
            
        if self.constraints.forbidden_node_types and node_type in self.constraints.forbidden_node_types:
            return False
        
        # Property filters
        if self.constraints.node_filters:
            properties = node_data.get('properties', {})
            for key, expected_value in self.constraints.node_filters.items():
                if properties.get(key) != expected_value:
                    return False
                    
        return True
    
    def is_valid_edge(self, edge_data: Dict[str, Any]) -> bool:
        """Check if edge satisfies constraints."""
        if not self.constraints:
            return True
            
        edge_type = edge_data.get('edge_type', 'Unknown')
        weight = edge_data.get('weight', 1.0)
        
        # Type constraints
        if self.constraints.allowed_edge_types and edge_type not in self.constraints.allowed_edge_types:
            return False
            
        if self.constraints.forbidden_edge_types and edge_type in self.constraints.forbidden_edge_types:
            return False
        
        # Weight constraints
        if self.constraints.max_weight is not None and weight > self.constraints.max_weight:
            return False
            
        if self.constraints.min_weight is not None and weight < self.constraints.min_weight:
            return False
        
        # Property filters
        if self.constraints.edge_filters:
            properties = edge_data.get('properties', {})
            for key, expected_value in self.constraints.edge_filters.items():
                if properties.get(key) != expected_value:
                    return False
                    
        return True
    
    def is_valid_path_depth(self, depth: int) -> bool:
        """Check if path depth satisfies constraints."""
        if not self.constraints:
            return True
            
        if self.constraints.max_depth is not None and depth > self.constraints.max_depth:
            return False
            
        if self.constraints.min_depth is not None and depth < self.constraints.min_depth:
            return False
            
        return True
    
    def is_valid_path(self, path: GraphPath) -> bool:
        """Final validation of complete path."""
        if not self.constraints:
            return True
        
        # Depth validation
        if not self.is_valid_path_depth(path.path_length):
            return False
        
        # Weight validation
        if self.constraints.max_weight is not None and path.total_weight > self.constraints.max_weight:
            return False
            
        if self.constraints.min_weight is not None and path.total_weight < self.constraints.min_weight:
            return False
        
        return True


class GraphAnalysisService:
    """
    Enhanced graph analysis service with enterprise features.
    Provides path finding, centrality analysis, and connection discovery.
    """
    
    def __init__(self, 
                 graph_repository: IGraphRepository,
                 cache_manager: Optional[SmartCache] = None,
                 event_publisher: Optional[UnifiedEventPublisher] = None):
        self.graph_repository = graph_repository
        self.cache = cache_manager
        self.event_publisher = event_publisher
        self.graph_builder = NetworkXGraphBuilder()
        
        # Local caches for performance
        self._graph_cache = TTLCache(maxsize=50, ttl=1800)  # 30 min
        self._path_cache = TTLCache(maxsize=200, ttl=900)   # 15 min
    
    @unified_circuit_breaker("graph_analysis")
    @trace_path_analysis("find_paths")
    async def find_paths(self, query: DeepLinkingQuery) -> List[GraphPath]:
        """
        Find paths between nodes with comprehensive optimization.
        """
        start_time = datetime.utcnow()
        path_query_counter.inc()
        
        try:
            # Get current tracing span for detailed metrics
            tracing_manager = await get_tracing_manager()
            current_span = None
            if tracing_manager._initialized:
                from opentelemetry import trace
                current_span = trace.get_current_span()
            
            # Generate cache key
            cache_key = self._generate_cache_key(query)
            
            # Check cache first
            if cache_key in self._path_cache:
                cache_hit_counter.inc()
                logger.debug(f"Path cache hit: {cache_key}")
                
                # Record cache hit in span
                if current_span and current_span.is_recording():
                    current_span.set_attribute("cache.hit", True)
                    current_span.set_attribute("cache.key", cache_key)
                
                return self._path_cache[cache_key]
            
            cache_miss_counter.inc()
            
            # Record cache miss in span
            if current_span and current_span.is_recording():
                current_span.set_attribute("cache.hit", False)
                current_span.set_attribute("cache.key", cache_key)
            
            # Build graph representation
            graph = await self._build_graph_for_query(query)
            active_graph_size.set(graph.number_of_nodes())
            
            # Execute path finding strategy
            paths = await self._execute_path_strategy(graph, query)
            
            # Apply optimizations
            if query.optimize_for_performance:
                paths = await self._optimize_paths(paths, query)
            
            # Record detailed tracing metrics
            if current_span and current_span.is_recording():
                current_span.set_attributes({
                    "graph.nodes.count": graph.number_of_nodes(),
                    "graph.edges.count": graph.number_of_edges(),
                    "paths.found": len(paths),
                    "query.strategy": query.strategy.value,
                    "query.direction": query.direction.value,
                    "query.max_paths": query.max_paths,
                    "query.has_target": query.target_node_id is not None,
                    "query.has_constraints": query.constraints is not None,
                    "optimization.applied": query.optimize_for_performance
                })
                
                if paths:
                    avg_path_length = sum(p.path_length for p in paths) / len(paths)
                    avg_path_weight = sum(p.total_weight for p in paths) / len(paths)
                    current_span.set_attributes({
                        "paths.avg_length": avg_path_length,
                        "paths.avg_weight": avg_path_weight
                    })
            
            # Cache results
            self._path_cache[cache_key] = paths
            
            # Publish analytics event
            if self.event_publisher:
                await self._publish_path_query_event(query, paths, start_time)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            path_query_duration.observe(duration)
            
            # Record final timing in span
            if current_span and current_span.is_recording():
                current_span.set_attribute("operation.duration_ms", duration * 1000)
            
            logger.info(f"Found {len(paths)} paths for {query.strategy.value} strategy in {duration:.3f}s")
            return paths
            
        except Exception as e:
            logger.error(f"Path finding failed: {e}")
            raise
    
    @trace_graph_operation("discover_connections_batch")
    async def discover_connections_batch(self, 
                                       node_ids: List[str], 
                                       max_depth: int = 3,
                                       batch_size: int = 50) -> Dict[str, List[GraphPath]]:
        """
        Discover connections with intelligent batching and parallel processing.
        """
        connections = {}
        
        # Use semaphore to limit concurrent operations
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent path queries
        
        async def find_connection_batch(source_batch: List[str], target_batch: List[str]):
            async with semaphore:
                batch_connections = {}
                
                for source_id in source_batch:
                    for target_id in target_batch:
                        if source_id != target_id:
                            try:
                                query = DeepLinkingQuery(
                                    source_node_id=source_id,
                                    target_node_id=target_id,
                                    strategy=PathStrategy.SHORTEST_PATH,
                                    constraints=PathConstraint(max_depth=max_depth),
                                    max_paths=3  # Limit for performance
                                )
                                
                                paths = await self.find_paths(query)
                                if paths:
                                    key = f"{source_id}->{target_id}"
                                    batch_connections[key] = paths
                                    
                            except Exception as e:
                                logger.warning(f"Failed to find path {source_id}->{target_id}: {e}")
                
                return batch_connections
        
        # Create batches
        batches = []
        for i in range(0, len(node_ids), batch_size):
            source_batch = node_ids[i:i + batch_size]
            for j in range(0, len(node_ids), batch_size):
                target_batch = node_ids[j:j + batch_size]
                batches.append((source_batch, target_batch))
        
        # Execute batches in parallel
        batch_tasks = [find_connection_batch(src, tgt) for src, tgt in batches]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        
        # Collect results
        for result in batch_results:
            if isinstance(result, dict):
                connections.update(result)
            elif isinstance(result, Exception):
                logger.warning(f"Batch connection discovery failed: {result}")
        
        return connections
    
    @trace_graph_operation("analyze_centrality")
    async def analyze_centrality(self, 
                               node_ids: List[str],
                               centrality_types: List[str] = None,
                               normalize: bool = True) -> Dict[str, Any]:
        """
        Analyze node centrality with multiple algorithms.
        """
        if centrality_types is None:
            centrality_types = ["betweenness", "closeness", "degree", "eigenvector"]
        
        # Get subgraph
        subgraph_data = await self.graph_repository.get_subgraph(node_ids)
        graph = self.graph_builder.build_graph(subgraph_data, TraversalDirection.BIDIRECTIONAL)
        
        # Calculate centralities in parallel using thread pool
        centrality_tasks = []
        
        for centrality_type in centrality_types:
            task = asyncio.create_task(
                self._calculate_centrality_async(graph, centrality_type, normalize)
            )
            centrality_tasks.append((centrality_type, task))
        
        # Collect results
        centrality_results = {}
        for centrality_type, task in centrality_tasks:
            try:
                centrality_results[centrality_type] = await task
            except Exception as e:
                logger.warning(f"Failed to calculate {centrality_type} centrality: {e}")
                centrality_results[centrality_type] = {}
        
        # Find top nodes for each centrality measure
        top_nodes = {}
        for centrality_type, values in centrality_results.items():
            if values:
                sorted_nodes = sorted(values.items(), key=lambda x: x[1], reverse=True)
                top_nodes[centrality_type] = sorted_nodes[:10]  # Top 10
        
        return {
            "centrality_scores": centrality_results,
            "top_nodes_by_centrality": top_nodes,
            "graph_stats": {
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "density": nx.density(graph),
                "is_connected": nx.is_connected(graph) if not isinstance(graph, nx.DiGraph) else nx.is_weakly_connected(graph)
            },
            "analysis_timestamp": datetime.utcnow().isoformat()
        }
    
    @trace_graph_operation("find_communities")
    async def find_communities(self, 
                             node_ids: List[str],
                             algorithm: str = "louvain",
                             resolution: float = 1.0) -> Dict[str, Any]:
        """
        Detect communities in the graph using various algorithms.
        """
        # Get subgraph
        subgraph_data = await self.graph_repository.get_subgraph(node_ids)
        graph = self.graph_builder.build_graph(subgraph_data, TraversalDirection.BIDIRECTIONAL)
        
        # Convert to undirected if needed
        if isinstance(graph, nx.DiGraph):
            graph = graph.to_undirected()
        
        # Run community detection in thread pool
        communities = await self._detect_communities_async(graph, algorithm, resolution)
        
        # Analyze community structure
        community_stats = {}
        for community_id, nodes in communities.items():
            subgraph = graph.subgraph(nodes)
            community_stats[community_id] = {
                "size": len(nodes),
                "nodes": list(nodes),
                "internal_edges": subgraph.number_of_edges(),
                "density": nx.density(subgraph) if len(nodes) > 1 else 0
            }
        
        return {
            "communities": community_stats,
            "algorithm": algorithm,
            "resolution": resolution,
            "modularity": self._calculate_modularity(graph, communities),
            "num_communities": len(communities),
            "analysis_timestamp": datetime.utcnow().isoformat()
        }
    
    async def _build_graph_for_query(self, query: DeepLinkingQuery) -> nx.Graph:
        """Build optimized graph representation for query."""
        # Determine nodes to include based on query type
        if query.target_node_id:
            # For specific source-target queries, get neighborhood of both nodes
            source_neighborhood = await self.graph_repository.get_node_neighborhood(
                query.source_node_id, max_hops=2
            )
            target_neighborhood = await self.graph_repository.get_node_neighborhood(
                query.target_node_id, max_hops=2
            )
            
            # Combine neighborhoods
            all_nodes = set()
            all_nodes.update(n.id for n in source_neighborhood.nodes)
            all_nodes.update(n.id for n in target_neighborhood.nodes)
            
            # Get complete subgraph
            subgraph_data = await self.graph_repository.get_subgraph(
                list(all_nodes),
                node_type_filters=query.constraints.allowed_node_types if query.constraints else None,
                edge_type_filters=query.constraints.allowed_edge_types if query.constraints else None,
                forbidden_node_types=query.constraints.forbidden_node_types if query.constraints else None,
                forbidden_edge_types=query.constraints.forbidden_edge_types if query.constraints else None
            )
        else:
            # For exploration queries, get larger neighborhood
            max_hops = query.constraints.max_depth if query.constraints and query.constraints.max_depth else 3
            subgraph_data = await self.graph_repository.get_node_neighborhood(
                query.source_node_id, 
                max_hops=min(max_hops + 1, 4)  # Slightly larger than query depth
            )
        
        return self.graph_builder.build_graph(subgraph_data, query.direction)
    
    async def _execute_path_strategy(self, graph: nx.Graph, query: DeepLinkingQuery) -> List[GraphPath]:
        """Execute path finding strategy with thread pool optimization."""
        
        if query.strategy == PathStrategy.SHORTEST_PATH:
            return await self._find_shortest_paths_async(graph, query)
        elif query.strategy == PathStrategy.ALL_PATHS:
            return await self._find_all_paths_async(graph, query)
        elif query.strategy == PathStrategy.WEIGHTED_PATH:
            return await self._find_weighted_paths_async(graph, query)
        elif query.strategy == PathStrategy.K_SHORTEST_PATHS:
            return await self._find_k_shortest_paths_async(graph, query)
        elif query.strategy == PathStrategy.CONSTRAINED_PATH:
            return await self._find_constrained_paths_async(graph, query)
        else:
            raise ValueError(f"Unsupported path strategy: {query.strategy}")
    
    async def _find_shortest_paths_async(self, graph: nx.Graph, query: DeepLinkingQuery) -> List[GraphPath]:
        """Find shortest paths using thread pool."""
        
        def find_paths():
            try:
                if query.target_node_id:
                    # Find paths to specific target
                    paths = list(nx.all_shortest_paths(
                        graph, query.source_node_id, query.target_node_id, weight='weight'
                    ))
                else:
                    # Find shortest paths to all reachable nodes
                    lengths = nx.single_source_shortest_path_length(
                        graph, query.source_node_id, cutoff=query.constraints.max_depth if query.constraints else 5
                    )
                    paths = []
                    for target, length in sorted(lengths.items(), key=lambda x: x[1]):
                        if target != query.source_node_id:
                            path = nx.shortest_path(graph, query.source_node_id, target, weight='weight')
                            paths.append(path)
                            if len(paths) >= query.max_paths:
                                break
                
                return paths[:query.max_paths]
                
            except nx.NetworkXNoPath:
                return []
        
        # Execute in thread pool
        loop = asyncio.get_event_loop()
        nx_paths = await loop.run_in_executor(_cpu_thread_pool, find_paths)
        
        # Convert to GraphPath objects
        graph_paths = []
        for path in nx_paths:
            graph_path = await self._convert_to_graph_path(graph, path, query)
            if self._validate_path(graph_path, query.constraints):
                graph_paths.append(graph_path)
        
        return graph_paths
    
    async def _find_k_shortest_paths_async(self, graph: nx.Graph, query: DeepLinkingQuery) -> List[GraphPath]:
        """Find K shortest paths using Yen's algorithm."""
        
        def find_k_paths():
            try:
                # Use NetworkX simple paths with length limit for K-shortest approximation
                if query.target_node_id:
                    max_depth = query.constraints.max_depth if query.constraints else 6
                    all_paths = list(nx.all_simple_paths(
                        graph, query.source_node_id, query.target_node_id, cutoff=max_depth
                    ))
                    
                    # Calculate path weights and sort
                    weighted_paths = []
                    for path in all_paths:
                        total_weight = 0
                        for i in range(len(path) - 1):
                            edge_data = graph.get_edge_data(path[i], path[i + 1])
                            total_weight += edge_data.get('weight', 1.0) if edge_data else 1.0
                        weighted_paths.append((path, total_weight))
                    
                    # Sort by weight and return top K
                    weighted_paths.sort(key=lambda x: x[1])
                    return [path for path, weight in weighted_paths[:query.k_value]]
                else:
                    return []
                    
            except nx.NetworkXNoPath:
                return []
        
        loop = asyncio.get_event_loop()
        nx_paths = await loop.run_in_executor(_cpu_thread_pool, find_k_paths)
        
        # Convert to GraphPath objects
        graph_paths = []
        for path in nx_paths:
            graph_path = await self._convert_to_graph_path(graph, path, query)
            if self._validate_path(graph_path, query.constraints):
                graph_paths.append(graph_path)
        
        return graph_paths
    
    async def _find_constrained_paths_async(self, graph: nx.Graph, query: DeepLinkingQuery) -> List[GraphPath]:
        """Find paths with constraints using optimized search."""
        
        if not query.target_node_id:
            return await self._find_reachable_paths_async(graph, query)
        
        validator = PathValidator(query.constraints)
        max_depth = query.constraints.max_depth if query.constraints else 10
        
        def constrained_search():
            # BFS with constraint checking
            queue = deque([(query.source_node_id, [query.source_node_id], 0, 0.0)])
            valid_paths = []
            visited_paths = set()
            
            while queue and len(valid_paths) < query.max_paths * 2:  # Get more for optimization
                current, path, depth, weight = queue.popleft()
                
                # Check if reached target
                if current == query.target_node_id and validator.is_valid_path_depth(depth):
                    valid_paths.append(path)
                    continue
                
                # Continue search if within depth limit
                if depth < max_depth:
                    neighbors = self.graph_builder.get_neighbors(graph, current, query.direction)
                    
                    for neighbor in neighbors:
                        if neighbor not in path:  # Avoid cycles
                            edge_data = graph.get_edge_data(current, neighbor, {})
                            
                            # Validate edge and neighbor
                            if (validator.is_valid_edge(edge_data) and 
                                validator.is_valid_node(graph.nodes.get(neighbor, {}))):
                                
                                edge_weight = edge_data.get('weight', 1.0)
                                new_path = path + [neighbor]
                                new_weight = weight + edge_weight
                                path_key = tuple(new_path)
                                
                                if path_key not in visited_paths:
                                    visited_paths.add(path_key)
                                    queue.append((neighbor, new_path, depth + 1, new_weight))
            
            return valid_paths
        
        loop = asyncio.get_event_loop()
        nx_paths = await loop.run_in_executor(_cpu_thread_pool, constrained_search)
        
        # Convert to GraphPath objects
        graph_paths = []
        for path in nx_paths:
            graph_path = await self._convert_to_graph_path(graph, path, query)
            if self._validate_path(graph_path, query.constraints):
                graph_paths.append(graph_path)
        
        return graph_paths[:query.max_paths]
    
    async def _convert_to_graph_path(self, graph: nx.Graph, path: List[str], query: DeepLinkingQuery) -> GraphPath:
        """Convert NetworkX path to GraphPath with comprehensive metadata."""
        nodes = []
        edges = []
        total_weight = 0.0
        
        # Convert nodes
        for i, node_id in enumerate(path):
            node_data = graph.nodes.get(node_id, {})
            nodes.append(PathNode(
                id=node_id,
                type=node_data.get('type', 'Unknown'),
                properties=node_data.get('properties', {}),
                depth=i,
                weight=node_data.get('weight')
            ))
        
        # Convert edges
        for i in range(len(path) - 1):
            source_id = path[i]
            target_id = path[i + 1]
            edge_data = graph.get_edge_data(source_id, target_id, {})
            
            weight = edge_data.get('weight', 1.0)
            total_weight += weight
            
            edges.append(PathEdge(
                source_id=source_id,
                target_id=target_id,
                edge_type=edge_data.get('edge_type', 'Unknown'),
                properties=edge_data.get('properties', {}),
                weight=weight
            ))
        
        metadata = {}
        if query.include_metadata:
            metadata = {
                "query_strategy": query.strategy.value,
                "traversal_direction": query.direction.value,
                "has_constraints": query.constraints is not None,
                "path_discovery_timestamp": datetime.utcnow().isoformat(),
                "graph_size": graph.number_of_nodes(),
                "optimization_applied": query.optimize_for_performance
            }
        
        return GraphPath(
            nodes=nodes,
            edges=edges,
            total_weight=total_weight,
            path_length=len(path),
            metadata=metadata
        )
    
    def _validate_path(self, path: GraphPath, constraints: Optional[PathConstraint]) -> bool:
        """Validate complete path against constraints."""
        if not constraints:
            return True
        
        validator = PathValidator(constraints)
        return validator.is_valid_path(path)
    
    async def _optimize_paths(self, paths: List[GraphPath], query: DeepLinkingQuery) -> List[GraphPath]:
        """Apply advanced path optimization strategies."""
        if not paths:
            return paths
        
        # Deduplication
        unique_paths = self._deduplicate_paths(paths)
        
        # Relevance scoring
        for path in unique_paths:
            path.metadata["relevance_score"] = self._calculate_relevance_score(path, query)
        
        # Diversity filtering if too many results
        if len(unique_paths) > query.max_paths * 2:
            unique_paths = self._apply_diversity_filter(unique_paths, query.max_paths)
        
        # Final sorting
        if query.strategy == PathStrategy.SHORTEST_PATH:
            unique_paths.sort(key=lambda p: (p.path_length, p.total_weight))
        elif query.strategy == PathStrategy.WEIGHTED_PATH:
            unique_paths.sort(key=lambda p: p.total_weight)
        else:
            unique_paths.sort(key=lambda p: -p.metadata.get("relevance_score", 0))
        
        return unique_paths[:query.max_paths]
    
    def _calculate_relevance_score(self, path: GraphPath, query: DeepLinkingQuery) -> float:
        """Calculate path relevance score."""
        score = 0.0
        
        # Shorter paths are generally more relevant
        length_penalty = 1.0 / (1.0 + path.path_length * 0.1)
        score += length_penalty * 0.4
        
        # Lower weight paths are more relevant  
        weight_bonus = 1.0 / (1.0 + path.total_weight * 0.1)
        score += weight_bonus * 0.3
        
        # Diversity bonus
        unique_types = len(set(node.type for node in path.nodes))
        diversity_bonus = unique_types / len(path.nodes) if path.nodes else 0
        score += diversity_bonus * 0.3
        
        return score
    
    def _generate_cache_key(self, query: DeepLinkingQuery) -> str:
        """Generate stable cache key using SHA256."""
        key_data = {
            "source": query.source_node_id,
            "target": query.target_node_id,
            "strategy": query.strategy.value,
            "direction": query.direction.value,
            "max_paths": query.max_paths,
            "constraints": self._serialize_constraints(query.constraints)
        }
        
        key_string = json.dumps(key_data, sort_keys=True)
        hash_object = hashlib.sha256(key_string.encode())
        return f"path:{hash_object.hexdigest()[:16]}"
    
    def _serialize_constraints(self, constraints: Optional[PathConstraint]) -> Dict[str, Any]:
        """Serialize constraints for cache key generation."""
        if not constraints:
            return {}
        
        return {
            "max_depth": constraints.max_depth,
            "min_depth": constraints.min_depth,
            "allowed_node_types": sorted(constraints.allowed_node_types or []),
            "forbidden_node_types": sorted(constraints.forbidden_node_types or []),
            "allowed_edge_types": sorted(constraints.allowed_edge_types or []),
            "forbidden_edge_types": sorted(constraints.forbidden_edge_types or []),
            "max_weight": constraints.max_weight,
            "min_weight": constraints.min_weight
        }
    
    async def _publish_path_query_event(self, query: DeepLinkingQuery, paths: List[GraphPath], start_time: datetime):
        """Publish analytics event for path query."""
        if not self.event_publisher:
            return
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        event_data = {
            "event_type": "PathQueryExecuted",
            "query": {
                "strategy": query.strategy.value,
                "direction": query.direction.value,
                "has_target": query.target_node_id is not None,
                "max_paths": query.max_paths,
                "has_constraints": query.constraints is not None
            },
            "results": {
                "paths_found": len(paths),
                "avg_path_length": sum(p.path_length for p in paths) / len(paths) if paths else 0,
                "avg_path_weight": sum(p.total_weight for p in paths) / len(paths) if paths else 0
            },
            "performance": {
                "duration_seconds": duration,
                "cache_hit": duration < 0.1  # Assume cache hit if very fast
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            await self.event_publisher.publish("graph.path_query", event_data)
        except Exception as e:
            logger.warning(f"Failed to publish path query event: {e}")
    
    # Additional helper methods for centrality, community detection, etc.
    async def _calculate_centrality_async(self, graph: nx.Graph, centrality_type: str, normalize: bool) -> Dict[str, float]:
        """Calculate centrality measures in thread pool."""
        
        def calculate():
            if centrality_type == "betweenness":
                return nx.betweenness_centrality(graph, normalized=normalize)
            elif centrality_type == "closeness":
                return nx.closeness_centrality(graph, normalized=normalize)
            elif centrality_type == "degree":
                return nx.degree_centrality(graph)
            elif centrality_type == "eigenvector":
                try:
                    return nx.eigenvector_centrality(graph, max_iter=1000)
                except nx.PowerIterationFailedConvergence:
                    logger.warning("Eigenvector centrality failed to converge")
                    return {}
            else:
                return {}
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_cpu_thread_pool, calculate)
    
    async def _detect_communities_async(self, graph: nx.Graph, algorithm: str, resolution: float) -> Dict[str, Set[str]]:
        """Detect communities in thread pool."""
        
        def detect():
            try:
                if algorithm == "louvain":
                    import community as community_louvain
                    partition = community_louvain.best_partition(graph, resolution=resolution)
                    communities = defaultdict(set)
                    for node, community_id in partition.items():
                        communities[str(community_id)].add(node)
                    return dict(communities)
                else:
                    # Fallback to connected components
                    communities = {}
                    for i, component in enumerate(nx.connected_components(graph)):
                        communities[str(i)] = component
                    return communities
            except Exception as e:
                logger.warning(f"Community detection failed: {e}")
                return {}
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_cpu_thread_pool, detect)
    
    def _calculate_modularity(self, graph: nx.Graph, communities: Dict[str, Set[str]]) -> float:
        """Calculate modularity score for community structure."""
        try:
            # Convert communities to list of sets for NetworkX
            community_list = [nodes for nodes in communities.values()]
            return nx.community.modularity(graph, community_list)
        except Exception as e:
            logger.warning(f"Failed to calculate modularity: {e}")
            return 0.0