"""
GraphQL Deep Linking and Path Query Optimization.
Implements advanced graph traversal with path discovery and optimization.
"""
from typing import List, Dict, Any, Optional, Set, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
import strawberry
from strawberry.types import Info
import networkx as nx
from cachetools import TTLCache
from ..database.clients.terminus_db import TerminusDBClient
from utils.logger import get_logger

logger = get_logger(__name__)

# Thread pool for CPU-intensive operations
_thread_pool = ThreadPoolExecutor(max_workers=4)


class TraversalDirection(Enum):
    FORWARD = "forward"
    BACKWARD = "backward"
    BIDIRECTIONAL = "bidirectional"


class PathStrategy(Enum):
    SHORTEST_PATH = "shortest"
    ALL_PATHS = "all"
    WEIGHTED_PATH = "weighted"
    CONSTRAINED_PATH = "constrained"


@strawberry.type
class PathNode:
    """Represents a node in a graph path."""
    id: str
    type: str
    properties: strawberry.scalars.JSON
    depth: int
    weight: Optional[float] = None


@strawberry.type
class PathEdge:
    """Represents an edge in a graph path."""
    source_id: str
    target_id: str
    edge_type: str
    properties: strawberry.scalars.JSON
    weight: Optional[float] = None


@strawberry.type
class GraphPath:
    """Represents a complete path through the graph."""
    nodes: List[PathNode]
    edges: List[PathEdge]
    total_weight: float
    path_length: int
    metadata: strawberry.scalars.JSON


@strawberry.input
class PathConstraint:
    """Constraints for path traversal."""
    max_depth: Optional[int] = None
    min_depth: Optional[int] = None
    allowed_node_types: Optional[List[str]] = None
    forbidden_node_types: Optional[List[str]] = None
    allowed_edge_types: Optional[List[str]] = None
    forbidden_edge_types: Optional[List[str]] = None
    node_filters: Optional[strawberry.scalars.JSON] = None
    edge_filters: Optional[strawberry.scalars.JSON] = None


@strawberry.input
class DeepLinkingQuery:
    """Deep linking query specification."""
    source_node_id: str
    target_node_id: Optional[str] = None
    strategy: PathStrategy = PathStrategy.SHORTEST_PATH
    direction: TraversalDirection = TraversalDirection.FORWARD
    max_paths: int = 10
    constraints: Optional[PathConstraint] = None
    include_metadata: bool = True
    optimize_for_performance: bool = True


class GraphPathBuilder:
    """
    Builds graph paths with real-time constraint checking and early pruning.
    """
    
    def __init__(self, constraints: Optional[PathConstraint] = None):
        self.constraints = constraints
    
    def is_valid_node(self, node_data: Dict[str, Any]) -> bool:
        """Check if node satisfies constraints."""
        if not self.constraints:
            return True
            
        node_type = node_data.get('type', 'Unknown')
        
        if self.constraints.allowed_node_types and node_type not in self.constraints.allowed_node_types:
            return False
            
        if self.constraints.forbidden_node_types and node_type in self.constraints.forbidden_node_types:
            return False
            
        if self.constraints.node_filters:
            for key, expected_value in self.constraints.node_filters.items():
                if node_data.get(key) != expected_value:
                    return False
                    
        return True
    
    def is_valid_edge(self, edge_data: Dict[str, Any]) -> bool:
        """Check if edge satisfies constraints."""
        if not self.constraints:
            return True
            
        edge_type = edge_data.get('edge_type', 'Unknown')
        
        if self.constraints.allowed_edge_types and edge_type not in self.constraints.allowed_edge_types:
            return False
            
        if self.constraints.forbidden_edge_types and edge_type in self.constraints.forbidden_edge_types:
            return False
            
        if self.constraints.edge_filters:
            for key, expected_value in self.constraints.edge_filters.items():
                if edge_data.get(key) != expected_value:
                    return False
                    
        return True
    
    def is_valid_path_depth(self, depth: int) -> bool:
        """Check if path depth satisfies constraints."""
        if not self.constraints:
            return True
            
        if self.constraints.max_depth and depth > self.constraints.max_depth:
            return False
            
        if self.constraints.min_depth and depth < self.constraints.min_depth:
            return False
            
        return True


class WOQLQueryBuilder:
    """
    Builds optimized WOQL queries with constraint filters.
    """
    
    @staticmethod
    def build_graph_query(query: DeepLinkingQuery) -> Dict[str, Any]:
        """Build WOQL query for graph data retrieval with constraints."""
        base_query = {
            "query": {
                "@type": "Or",
                "or": [
                    {
                        "@type": "Triple",
                        "subject": {"@type": "Variable", "name": "Node"},
                        "predicate": {"@type": "NodeValue", "node": "rdf:type"},
                        "object": {"@type": "Variable", "name": "NodeType"}
                    },
                    {
                        "@type": "Triple",
                        "subject": {"@type": "Variable", "name": "Edge"},
                        "predicate": {"@type": "NodeValue", "node": "rdf:type"},
                        "object": {"@type": "Variable", "name": "EdgeType"}
                    }
                ]
            }
        }
        
        # Add constraint filters to optimize DB query
        filters = []
        
        if query.constraints:
            # Node type constraints
            if query.constraints.allowed_node_types:
                node_type_filter = {
                    "@type": "Or",
                    "or": [
                        {
                            "@type": "Triple",
                            "subject": {"@type": "Variable", "name": "NodeType"},
                            "predicate": {"@type": "NodeValue", "node": "rdf:value"},
                            "object": {"@type": "NodeValue", "node": node_type}
                        }
                        for node_type in query.constraints.allowed_node_types
                    ]
                }
                filters.append(node_type_filter)
            
            # Edge type constraints
            if query.constraints.allowed_edge_types:
                edge_type_filter = {
                    "@type": "Or",
                    "or": [
                        {
                            "@type": "Triple",
                            "subject": {"@type": "Variable", "name": "EdgeType"},
                            "predicate": {"@type": "NodeValue", "node": "rdf:value"},
                            "object": {"@type": "NodeValue", "node": edge_type}
                        }
                        for edge_type in query.constraints.allowed_edge_types
                    ]
                }
                filters.append(edge_type_filter)
            
            # Forbidden type constraints
            if query.constraints.forbidden_node_types:
                forbidden_node_filter = {
                    "@type": "Not",
                    "query": {
                        "@type": "Or",
                        "or": [
                            {
                                "@type": "Triple",
                                "subject": {"@type": "Variable", "name": "NodeType"},
                                "predicate": {"@type": "NodeValue", "node": "rdf:value"},
                                "object": {"@type": "NodeValue", "node": node_type}
                            }
                            for node_type in query.constraints.forbidden_node_types
                        ]
                    }
                }
                filters.append(forbidden_node_filter)
        
        # Combine base query with filters
        if filters:
            base_query = {
                "@type": "And",
                "and": [base_query] + filters
            }
        
        return base_query


class DeepLinkingEngine:
    """
    Advanced deep linking engine with path optimization and caching.
    """
    
    def __init__(self, terminus_client: TerminusDBClient):
        self.terminus_client = terminus_client
        # Use TTL cache for automatic cleanup
        self.graph_cache = TTLCache(maxsize=100, ttl=3600)  # 1 hour TTL
        self.path_cache = TTLCache(maxsize=1000, ttl=1800)  # 30 min TTL
        
    async def find_paths(self, query: DeepLinkingQuery) -> List[GraphPath]:
        """
        Find paths between nodes based on the deep linking query.
        """
        try:
            # Generate cache key
            cache_key = self._generate_cache_key(query)
            
            # Check cache first
            if cache_key in self.path_cache:
                logger.info(f"Returning cached paths for query: {cache_key}")
                return self.path_cache[cache_key]
            
            # Build or retrieve graph representation
            graph = await self._build_graph_representation(query)
            
            # Execute path finding based on strategy
            paths = await self._execute_path_strategy(graph, query)
            
            # Optimize paths if requested
            if query.optimize_for_performance:
                paths = await self._optimize_paths(paths, query)
            
            # Cache results
            self.path_cache[cache_key] = paths
            
            logger.info(f"Found {len(paths)} paths for deep linking query")
            return paths
            
        except Exception as e:
            logger.error(f"Error in deep linking path finding: {e}")
            raise

    async def discover_connections(self, 
                                 node_ids: List[str], 
                                 max_depth: int = 3) -> Dict[str, List[GraphPath]]:
        """
        Discover all connections between a set of nodes using parallel processing.
        """
        connections = {}
        
        # Create tasks for parallel execution
        tasks = []
        for i, source_id in enumerate(node_ids):
            for j, target_id in enumerate(node_ids):
                if i != j:
                    query = DeepLinkingQuery(
                        source_node_id=source_id,
                        target_node_id=target_id,
                        strategy=PathStrategy.ALL_PATHS,
                        constraints=PathConstraint(max_depth=max_depth)
                    )
                    
                    task = asyncio.create_task(
                        self._find_connection_with_key(source_id, target_id, query)
                    )
                    tasks.append(task)
        
        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect successful results
        for result in results:
            if isinstance(result, tuple) and not isinstance(result, Exception):
                key, paths = result
                if paths:
                    connections[key] = paths
            elif isinstance(result, Exception):
                logger.warning(f"Connection discovery task failed: {result}")
        
        return connections

    async def _find_connection_with_key(self, source_id: str, target_id: str, 
                                      query: DeepLinkingQuery) -> Tuple[str, List[GraphPath]]:
        """Helper method to find connection and return with key."""
        paths = await self.find_paths(query)
        key = f"{source_id}->{target_id}"
        return key, paths

    async def find_central_nodes(self, 
                               node_ids: List[str], 
                               centrality_type: str = "betweenness") -> List[Dict[str, Any]]:
        """
        Find central nodes in a subgraph using various centrality measures.
        """
        # Build subgraph
        graph = await self._build_subgraph(node_ids)
        
        # Calculate centrality
        if centrality_type == "betweenness":
            centrality = nx.betweenness_centrality(graph)
        elif centrality_type == "closeness":
            centrality = nx.closeness_centrality(graph)
        elif centrality_type == "degree":
            centrality = nx.degree_centrality(graph)
        elif centrality_type == "eigenvector":
            centrality = nx.eigenvector_centrality(graph)
        else:
            raise ValueError(f"Unsupported centrality type: {centrality_type}")
        
        # Sort by centrality score
        central_nodes = [
            {
                "node_id": node_id,
                "centrality_score": score,
                "centrality_type": centrality_type
            }
            for node_id, score in sorted(centrality.items(), 
                                       key=lambda x: x[1], reverse=True)
        ]
        
        return central_nodes

    async def _build_graph_representation(self, query: DeepLinkingQuery) -> nx.Graph:
        """
        Build NetworkX graph representation for efficient path finding.
        """
        # Check if we have cached graph for this query context
        graph_key = self._generate_graph_cache_key(query)
        
        if graph_key in self.graph_cache:
            return self.graph_cache[graph_key]
        
        # Query TerminusDB for graph data with optimized constraints
        woql_query = WOQLQueryBuilder.build_graph_query(query)
        graph_data = await self.terminus_client.query(woql_query)
        
        # Choose appropriate graph type based on traversal direction
        if query.direction == TraversalDirection.FORWARD:
            graph = nx.DiGraph()
        elif query.direction == TraversalDirection.BACKWARD:
            graph = nx.DiGraph()  # Will use predecessors for traversal
        else:  # BIDIRECTIONAL
            graph = nx.Graph()
        
        # Initialize path builder for constraint checking
        path_builder = GraphPathBuilder(query.constraints)
        
        # Add nodes and edges with constraint checking
        nodes_added = set()
        for item in graph_data:
            if item.get("@type") == "ObjectType":
                node_id = item.get("@id")
                if node_id and node_id not in nodes_added:
                    node_data = {
                        "type": item.get("@type"),
                        "properties": item
                    }
                    
                    # Only add node if it satisfies constraints
                    if path_builder.is_valid_node(node_data):
                        graph.add_node(node_id, **node_data)
                        nodes_added.add(node_id)
            
            elif item.get("@type") == "LinkType":
                source = item.get("source")
                target = item.get("target")
                if source and target and source in nodes_added and target in nodes_added:
                    edge_data = {
                        "edge_type": item.get("@type"),
                        "properties": item,
                        "weight": self._calculate_edge_weight(item, query)
                    }
                    
                    # Only add edge if it satisfies constraints
                    if path_builder.is_valid_edge(edge_data):
                        graph.add_edge(source, target, **edge_data)
        
        # Cache the graph
        self.graph_cache[graph_key] = graph
        
        return graph

    async def _execute_path_strategy(self, graph: nx.Graph, query: DeepLinkingQuery) -> List[GraphPath]:
        """
        Execute the specific path finding strategy.
        """
        source = query.source_node_id
        target = query.target_node_id
        
        if not target:
            # If no target, find reachable nodes
            return await self._find_reachable_paths(graph, source, query)
        
        if query.strategy == PathStrategy.SHORTEST_PATH:
            return await self._find_shortest_paths(graph, source, target, query)
        elif query.strategy == PathStrategy.ALL_PATHS:
            return await self._find_all_paths(graph, source, target, query)
        elif query.strategy == PathStrategy.WEIGHTED_PATH:
            return await self._find_weighted_paths(graph, source, target, query)
        elif query.strategy == PathStrategy.CONSTRAINED_PATH:
            return await self._find_constrained_paths(graph, source, target, query)
        else:
            raise ValueError(f"Unsupported path strategy: {query.strategy}")

    async def _find_shortest_paths(self, 
                                 graph: nx.Graph, 
                                 source: str, 
                                 target: str, 
                                 query: DeepLinkingQuery) -> List[GraphPath]:
        """Find shortest paths between source and target using thread pool for CPU-intensive work."""
        try:
            # Offload CPU-intensive NetworkX operation to thread pool
            def find_paths():
                return list(nx.all_shortest_paths(graph, source, target, weight='weight'))
            
            loop = asyncio.get_event_loop()
            paths = await loop.run_in_executor(_thread_pool, find_paths)
            
            graph_paths = []
            for path in paths[:query.max_paths]:
                graph_path = await self._convert_to_graph_path(graph, path, query)
                # Constraints already checked during graph building, skip redundant check
                graph_paths.append(graph_path)
            
            return graph_paths
            
        except nx.NetworkXNoPath:
            return []

    async def _find_all_paths(self, 
                            graph: nx.Graph, 
                            source: str, 
                            target: str, 
                            query: DeepLinkingQuery) -> List[GraphPath]:
        """Find all simple paths between source and target."""
        max_depth = query.constraints.max_depth if query.constraints else 10
        
        try:
            paths = list(nx.all_simple_paths(graph, source, target, cutoff=max_depth))
            
            graph_paths = []
            for path in paths[:query.max_paths]:
                graph_path = await self._convert_to_graph_path(graph, path, query)
                if await self._satisfies_constraints(graph_path, query.constraints):
                    graph_paths.append(graph_path)
            
            # Sort by path weight/length
            graph_paths.sort(key=lambda p: (p.total_weight, p.path_length))
            
            return graph_paths
            
        except nx.NetworkXNoPath:
            return []

    async def _find_weighted_paths(self, 
                                 graph: nx.Graph, 
                                 source: str, 
                                 target: str, 
                                 query: DeepLinkingQuery) -> List[GraphPath]:
        """Find paths optimizing for weight."""
        try:
            path = nx.shortest_path(graph, source, target, weight='weight')
            graph_path = await self._convert_to_graph_path(graph, path, query)
            
            if await self._satisfies_constraints(graph_path, query.constraints):
                return [graph_path]
            else:
                return []
                
        except nx.NetworkXNoPath:
            return []

    async def _find_constrained_paths(self, 
                                    graph: nx.Graph, 
                                    source: str, 
                                    target: str, 
                                    query: DeepLinkingQuery) -> List[GraphPath]:
        """Find paths with specific constraints using optimized custom algorithm."""
        constraints = query.constraints
        if not constraints:
            return await self._find_shortest_paths(graph, source, target, query)
        
        path_builder = GraphPathBuilder(constraints)
        
        # Performance optimization: use early stopping and pruning
        max_paths = query.max_paths if query.optimize_for_performance else query.max_paths * 2
        max_depth = constraints.max_depth or 10
        
        # Choose appropriate neighbor function based on graph direction
        def get_neighbors(node):
            if isinstance(graph, nx.DiGraph):
                if query.direction == TraversalDirection.BACKWARD:
                    return graph.predecessors(node)
                else:  # FORWARD or BIDIRECTIONAL
                    return graph.successors(node)
            else:
                return graph.neighbors(node)
        
        # Custom BFS/DFS with enhanced constraint checking and early pruning
        queue = deque([(source, [source], 0, 0.0)])  # (current_node, path, depth, weight)
        valid_paths = []
        visited_paths = set()
        pruned_count = 0
        
        while queue and len(valid_paths) < max_paths:
            current, path, depth, weight = queue.popleft()
            
            # Early depth pruning
            if not path_builder.is_valid_path_depth(depth):
                pruned_count += 1
                continue
            
            # Check if we reached target
            if current == target:
                if path_builder.is_valid_path_depth(depth):
                    graph_path = await self._convert_to_graph_path(graph, path, query)
                    valid_paths.append(graph_path)
                continue
            
            # Performance optimization: skip if too deep
            if depth >= max_depth:
                continue
            
            # Explore neighbors with direction awareness
            for neighbor in get_neighbors(current):
                if neighbor not in path:  # Avoid cycles
                    edge_data = graph.get_edge_data(current, neighbor, {})
                    
                    # Early edge validation
                    if not path_builder.is_valid_edge(edge_data):
                        pruned_count += 1
                        continue
                    
                    # Check neighbor node validity
                    neighbor_data = graph.nodes.get(neighbor, {})
                    if not path_builder.is_valid_node(neighbor_data):
                        pruned_count += 1
                        continue
                    
                    edge_weight = edge_data.get('weight', 1.0)
                    new_path = path + [neighbor]
                    new_weight = weight + edge_weight
                    path_key = tuple(new_path)
                    
                    if path_key not in visited_paths:
                        visited_paths.add(path_key)
                        queue.append((neighbor, new_path, depth + 1, new_weight))
        
        logger.debug(f"Constrained path search: found {len(valid_paths)} paths, pruned {pruned_count} invalid branches")
        
        return valid_paths[:query.max_paths]

    async def _find_reachable_paths(self, 
                                  graph: nx.Graph, 
                                  source: str, 
                                  query: DeepLinkingQuery) -> List[GraphPath]:
        """Find all reachable nodes from source within constraints."""
        constraints = query.constraints
        max_depth = constraints.max_depth if constraints else 5
        
        reachable_paths = []
        queue = deque([(source, [source], 0, 0.0)])
        visited = {source}
        
        while queue and len(reachable_paths) < query.max_paths:
            current, path, depth, weight = queue.popleft()
            
            if depth > 0:  # Don't include the source itself
                graph_path = await self._convert_to_graph_path(graph, path, query)
                if await self._satisfies_constraints(graph_path, constraints):
                    reachable_paths.append(graph_path)
            
            if depth < max_depth:
                for neighbor in graph.neighbors(current):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        edge_data = graph.get_edge_data(current, neighbor)
                        edge_weight = edge_data.get('weight', 1.0) if edge_data else 1.0
                        
                        new_path = path + [neighbor]
                        new_weight = weight + edge_weight
                        queue.append((neighbor, new_path, depth + 1, new_weight))
        
        return reachable_paths

    async def _convert_to_graph_path(self, 
                                   graph: nx.Graph, 
                                   path: List[str], 
                                   query: DeepLinkingQuery) -> GraphPath:
        """Convert NetworkX path to GraphPath object."""
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
                "path_discovery_time": "calculated_during_execution"
            }
        
        return GraphPath(
            nodes=nodes,
            edges=edges,
            total_weight=total_weight,
            path_length=len(path),
            metadata=metadata
        )

    async def _satisfies_constraints(self, 
                                   path: GraphPath, 
                                   constraints: Optional[PathConstraint]) -> bool:
        """
        Check if path satisfies the given constraints.
        Note: Most constraint checking is now done during graph building and path construction
        for better performance. This method serves as a final validation step.
        """
        if not constraints:
            return True
        
        path_builder = GraphPathBuilder(constraints)
        
        # Check depth constraints
        if not path_builder.is_valid_path_depth(path.path_length):
            return False
        
        # Additional validation for complex constraints that couldn't be pre-filtered
        if constraints.node_filters:
            for node in path.nodes:
                if not path_builder.is_valid_node({"type": node.type, **node.properties}):
                    return False
        
        if constraints.edge_filters:
            for edge in path.edges:
                if not path_builder.is_valid_edge({"edge_type": edge.edge_type, **edge.properties}):
                    return False
        
        return True

    async def _optimize_paths(self, 
                            paths: List[GraphPath], 
                            query: DeepLinkingQuery) -> List[GraphPath]:
        """Optimize paths for performance and relevance with advanced strategies."""
        if not paths:
            return paths
        
        # Performance optimization strategies
        optimization_strategies = {
            "deduplication": True,
            "relevance_scoring": query.optimize_for_performance,
            "diversity_filtering": query.optimize_for_performance and len(paths) > query.max_paths * 2,
            "early_stopping": query.optimize_for_performance
        }
        
        optimized_paths = paths
        
        # 1. Remove duplicate paths
        if optimization_strategies["deduplication"]:
            unique_paths = []
            seen_signatures = set()
            
            for path in optimized_paths:
                signature = self._generate_path_signature(path)
                if signature not in seen_signatures:
                    seen_signatures.add(signature)
                    unique_paths.append(path)
            
            optimized_paths = unique_paths
        
        # 2. Apply relevance scoring
        if optimization_strategies["relevance_scoring"]:
            for path in optimized_paths:
                path.metadata["relevance_score"] = self._calculate_relevance_score(path, query)
        
        # 3. Diversity filtering (avoid too similar paths)
        if optimization_strategies["diversity_filtering"]:
            optimized_paths = self._apply_diversity_filter(optimized_paths, query.max_paths)
        
        # 4. Sort by optimization criteria
        if query.strategy == PathStrategy.SHORTEST_PATH:
            optimized_paths.sort(key=lambda p: (p.path_length, p.total_weight))
        elif query.strategy == PathStrategy.WEIGHTED_PATH:
            optimized_paths.sort(key=lambda p: p.total_weight)
        elif optimization_strategies["relevance_scoring"]:
            optimized_paths.sort(key=lambda p: -p.metadata.get("relevance_score", 0))
        else:
            optimized_paths.sort(key=lambda p: (p.total_weight, p.path_length))
        
        # 5. Early stopping
        if optimization_strategies["early_stopping"]:
            return optimized_paths[:query.max_paths]
        
        return optimized_paths[:query.max_paths]
    
    def _calculate_relevance_score(self, path: GraphPath, query: DeepLinkingQuery) -> float:
        """Calculate relevance score based on path characteristics."""
        score = 0.0
        
        # Shorter paths are generally more relevant
        length_penalty = 1.0 / (1.0 + path.path_length * 0.1)
        score += length_penalty * 0.3
        
        # Lower weight paths are more relevant
        weight_bonus = 1.0 / (1.0 + path.total_weight * 0.1)
        score += weight_bonus * 0.4
        
        # Paths with diverse node types are more interesting
        unique_types = len(set(node.type for node in path.nodes))
        diversity_bonus = unique_types / len(path.nodes) if path.nodes else 0
        score += diversity_bonus * 0.3
        
        return score
    
    def _apply_diversity_filter(self, paths: List[GraphPath], max_paths: int) -> List[GraphPath]:
        """Apply diversity filtering to avoid too similar paths."""
        if len(paths) <= max_paths:
            return paths
        
        selected_paths = []
        remaining_paths = paths.copy()
        
        # Select first path (usually best scoring)
        if remaining_paths:
            selected_paths.append(remaining_paths.pop(0))
        
        # Select subsequent paths based on diversity
        while len(selected_paths) < max_paths and remaining_paths:
            best_candidate = None
            best_diversity_score = -1
            
            for candidate in remaining_paths:
                # Calculate diversity score (dissimilarity with selected paths)
                diversity_score = min(
                    self._calculate_path_similarity(candidate, selected_path)
                    for selected_path in selected_paths
                )
                
                if diversity_score > best_diversity_score:
                    best_diversity_score = diversity_score
                    best_candidate = candidate
            
            if best_candidate:
                selected_paths.append(best_candidate)
                remaining_paths.remove(best_candidate)
            else:
                break
        
        return selected_paths
    
    def _calculate_path_similarity(self, path1: GraphPath, path2: GraphPath) -> float:
        """Calculate similarity between two paths (0 = identical, 1 = completely different)."""
        # Compare node sequences
        nodes1 = [node.id for node in path1.nodes]
        nodes2 = [node.id for node in path2.nodes]
        
        # Jaccard distance for node overlap
        set1, set2 = set(nodes1), set(nodes2)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        if union == 0:
            return 1.0
        
        jaccard_similarity = intersection / union
        return 1.0 - jaccard_similarity  # Convert to distance

    def _generate_path_signature(self, path: GraphPath) -> str:
        """Generate unique signature for path deduplication."""
        node_ids = [node.id for node in path.nodes]
        return "->".join(node_ids)

    def _calculate_edge_weight(self, edge_data: Dict[str, Any], query: DeepLinkingQuery) -> float:
        """Calculate edge weight based on properties and query context."""
        # Default weight
        weight = 1.0
        
        # Adjust weight based on edge properties
        if 'weight' in edge_data:
            weight = float(edge_data['weight'])
        elif 'strength' in edge_data:
            weight = 1.0 / max(float(edge_data['strength']), 0.1)
        elif 'frequency' in edge_data:
            weight = 1.0 / max(float(edge_data['frequency']), 0.1)
        
        return weight

    def _build_graph_query(self, query: DeepLinkingQuery) -> Dict[str, Any]:
        """Build WOQL query for graph data retrieval (deprecated - use WOQLQueryBuilder)."""
        # Delegate to the new optimized query builder
        return WOQLQueryBuilder.build_graph_query(query)

    async def _build_subgraph(self, node_ids: List[str]) -> nx.Graph:
        """Build subgraph containing only specified nodes and their connections."""
        # Query for subgraph data
        woql_query = {
            "query": {
                "@type": "Triple",
                "subject": {"@type": "Variable", "name": "Node"},
                "predicate": {"@type": "NodeValue", "node": "@id"},
                "object": {"@type": "Variable", "name": "NodeId"}
            },
            "filter": {
                "@type": "Member",
                "member": {"@type": "Variable", "name": "NodeId"},
                "list": node_ids
            }
        }
        
        subgraph_data = await self.terminus_client.query(woql_query)
        
        # Build NetworkX subgraph
        subgraph = nx.Graph()
        
        for item in subgraph_data:
            if item.get("@id") in node_ids:
                subgraph.add_node(item.get("@id"), **item)
        
        # Add edges between nodes in the subgraph
        for source in node_ids:
            for target in node_ids:
                if source != target:
                    # Query for edge between source and target
                    edge_query = self._build_edge_query(source, target)
                    edge_data = await self.terminus_client.query(edge_query)
                    
                    if edge_data:
                        subgraph.add_edge(source, target, **edge_data[0])
        
        return subgraph

    def _build_edge_query(self, source: str, target: str) -> Dict[str, Any]:
        """Build WOQL query to find edge between two nodes."""
        return {
            "query": {
                "@type": "And",
                "and": [
                    {
                        "@type": "Triple",
                        "subject": {"@type": "NodeValue", "node": source},
                        "predicate": {"@type": "Variable", "name": "Predicate"},
                        "object": {"@type": "NodeValue", "node": target}
                    }
                ]
            }
        }

    def _generate_cache_key(self, query: DeepLinkingQuery) -> str:
        """Generate cache key for path query."""
        key_parts = [
            query.source_node_id,
            query.target_node_id or "any",
            query.strategy.value,
            query.direction.value,
            str(query.max_paths)
        ]
        
        if query.constraints:
            constraint_parts = [
                str(query.constraints.max_depth),
                str(query.constraints.min_depth),
                str(sorted(query.constraints.allowed_node_types or [])),
                str(sorted(query.constraints.forbidden_node_types or [])),
                str(sorted(query.constraints.allowed_edge_types or [])),
                str(sorted(query.constraints.forbidden_edge_types or []))
            ]
            key_parts.extend(constraint_parts)
        
        return "|".join(key_parts)

    def _generate_graph_cache_key(self, query: DeepLinkingQuery) -> str:
        """Generate cache key for graph representation."""
        # For now, use a simple key - in practice, this would be more sophisticated
        return f"graph_{query.direction.value}_{hash(str(query.constraints))}"


# GraphQL resolvers for deep linking
@strawberry.type
class DeepLinkingQueries:
    @strawberry.field
    async def find_paths(self, 
                        info: Info,
                        query: DeepLinkingQuery) -> List[GraphPath]:
        """Find paths between nodes using deep linking."""
        terminus_client = info.context["terminus_client"]
        engine = DeepLinkingEngine(terminus_client)
        return await engine.find_paths(query)
    
    @strawberry.field
    async def discover_connections(self,
                                 info: Info,
                                 node_ids: List[str],
                                 max_depth: int = 3) -> strawberry.scalars.JSON:
        """Discover connections between multiple nodes."""
        terminus_client = info.context["terminus_client"]
        engine = DeepLinkingEngine(terminus_client)
        connections = await engine.discover_connections(node_ids, max_depth)
        return connections
    
    @strawberry.field
    async def find_central_nodes(self,
                               info: Info,
                               node_ids: List[str],
                               centrality_type: str = "betweenness") -> strawberry.scalars.JSON:
        """Find central nodes in a subgraph."""
        terminus_client = info.context["terminus_client"]
        engine = DeepLinkingEngine(terminus_client)
        central_nodes = await engine.find_central_nodes(node_ids, centrality_type)
        return central_nodes