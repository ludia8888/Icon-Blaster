"""
GraphQL resolvers for graph analysis operations.
Thin presentation layer that delegates to domain services.
"""
from typing import List, Dict, Any, Optional
import strawberry
from strawberry.types import Info

from ...services.graph_analysis import (
    GraphAnalysisService, 
    DeepLinkingQuery, 
    PathConstraint, 
    PathStrategy, 
    TraversalDirection,
    GraphPath,
    PathNode,
    PathEdge
)
from ...core.auth.resource_permission_checker import require_permission
from ...middleware.common.metrics import Counter, Timer
from utils.logger import get_logger

logger = get_logger(__name__)

# Metrics
graphql_resolver_counter = Counter("graphql_graph_resolvers_total", "Total GraphQL graph resolver calls")
graphql_resolver_duration = Timer("graphql_graph_resolver_duration_seconds", "GraphQL resolver execution time")


# Convert domain objects to GraphQL types
@strawberry.type
class GraphQLPathNode:
    """GraphQL representation of a path node."""
    id: str
    type: str
    properties: strawberry.scalars.JSON
    depth: int
    weight: Optional[float] = None
    
    @classmethod
    def from_domain(cls, domain_node: PathNode) -> 'GraphQLPathNode':
        return cls(
            id=domain_node.id,
            type=domain_node.type,
            properties=domain_node.properties,
            depth=domain_node.depth,
            weight=domain_node.weight
        )


@strawberry.type
class GraphQLPathEdge:
    """GraphQL representation of a path edge."""
    source_id: str
    target_id: str
    edge_type: str
    properties: strawberry.scalars.JSON
    weight: float
    
    @classmethod
    def from_domain(cls, domain_edge: PathEdge) -> 'GraphQLPathEdge':
        return cls(
            source_id=domain_edge.source_id,
            target_id=domain_edge.target_id,
            edge_type=domain_edge.edge_type,
            properties=domain_edge.properties,
            weight=domain_edge.weight
        )


@strawberry.type
class GraphQLGraphPath:
    """GraphQL representation of a complete graph path."""
    nodes: List[GraphQLPathNode]
    edges: List[GraphQLPathEdge]
    total_weight: float
    path_length: int
    metadata: strawberry.scalars.JSON
    
    @classmethod
    def from_domain(cls, domain_path: GraphPath) -> 'GraphQLGraphPath':
        return cls(
            nodes=[GraphQLPathNode.from_domain(node) for node in domain_path.nodes],
            edges=[GraphQLPathEdge.from_domain(edge) for edge in domain_path.edges],
            total_weight=domain_path.total_weight,
            path_length=domain_path.path_length,
            metadata=domain_path.metadata
        )


# Input types
@strawberry.input
class GraphQLPathConstraint:
    """GraphQL input for path constraints."""
    max_depth: Optional[int] = None
    min_depth: Optional[int] = None
    allowed_node_types: Optional[List[str]] = None
    forbidden_node_types: Optional[List[str]] = None
    allowed_edge_types: Optional[List[str]] = None
    forbidden_edge_types: Optional[List[str]] = None
    node_filters: Optional[strawberry.scalars.JSON] = None
    edge_filters: Optional[strawberry.scalars.JSON] = None
    max_weight: Optional[float] = None
    min_weight: Optional[float] = None
    
    def to_domain(self) -> PathConstraint:
        """Convert to domain object."""
        return PathConstraint(
            max_depth=self.max_depth,
            min_depth=self.min_depth,
            allowed_node_types=self.allowed_node_types,
            forbidden_node_types=self.forbidden_node_types,
            allowed_edge_types=self.allowed_edge_types,
            forbidden_edge_types=self.forbidden_edge_types,
            node_filters=self.node_filters,
            edge_filters=self.edge_filters,
            max_weight=self.max_weight,
            min_weight=self.min_weight
        )


@strawberry.input
class GraphQLDeepLinkingQuery:
    """GraphQL input for deep linking queries."""
    source_node_id: str
    target_node_id: Optional[str] = None
    strategy: str = "shortest"  # Will convert to enum
    direction: str = "forward"  # Will convert to enum
    max_paths: int = 10
    constraints: Optional[GraphQLPathConstraint] = None
    include_metadata: bool = True
    optimize_for_performance: bool = True
    k_value: int = 5
    
    def to_domain(self) -> DeepLinkingQuery:
        """Convert to domain object with validation."""
        # Convert string enums to domain enums
        strategy_mapping = {
            "shortest": PathStrategy.SHORTEST_PATH,
            "all": PathStrategy.ALL_PATHS,
            "weighted": PathStrategy.WEIGHTED_PATH,
            "constrained": PathStrategy.CONSTRAINED_PATH,
            "k_shortest": PathStrategy.K_SHORTEST_PATHS
        }
        
        direction_mapping = {
            "forward": TraversalDirection.FORWARD,
            "backward": TraversalDirection.BACKWARD,
            "bidirectional": TraversalDirection.BIDIRECTIONAL
        }
        
        strategy = strategy_mapping.get(self.strategy)
        if not strategy:
            raise ValueError(f"Invalid strategy: {self.strategy}")
        
        direction = direction_mapping.get(self.direction)
        if not direction:
            raise ValueError(f"Invalid direction: {self.direction}")
        
        return DeepLinkingQuery(
            source_node_id=self.source_node_id,
            target_node_id=self.target_node_id,
            strategy=strategy,
            direction=direction,
            max_paths=self.max_paths,
            constraints=self.constraints.to_domain() if self.constraints else None,
            include_metadata=self.include_metadata,
            optimize_for_performance=self.optimize_for_performance,
            k_value=self.k_value
        )


@strawberry.type
class GraphAnalysisQueries:
    """GraphQL queries for graph analysis operations."""
    
    @strawberry.field
    @graphql_resolver_counter.count_calls()
    @graphql_resolver_duration.time()
    @require_permission("graph:read")
    async def find_paths(self, 
                        info: Info,
                        query: GraphQLDeepLinkingQuery) -> List[GraphQLGraphPath]:
        """
        Find paths between nodes using various strategies.
        
        Args:
            query: Deep linking query specification
            
        Returns:
            List of graph paths matching the query criteria
            
        Raises:
            ValueError: Invalid query parameters
            PermissionError: Insufficient permissions
        """
        try:
            # Get service from context
            graph_service: GraphAnalysisService = info.context["graph_analysis_service"]
            
            # Convert GraphQL input to domain object
            domain_query = query.to_domain()
            
            # Apply user-based constraints if needed
            user_context = info.context.get("user")
            if user_context:
                domain_query = await self._apply_user_constraints(domain_query, user_context)
            
            # Execute domain service
            domain_paths = await graph_service.find_paths(domain_query)
            
            # Convert back to GraphQL types
            graphql_paths = [GraphQLGraphPath.from_domain(path) for path in domain_paths]
            
            logger.info(f"GraphQL find_paths: found {len(graphql_paths)} paths for user {user_context.get('id', 'unknown')}")
            
            return graphql_paths
            
        except Exception as e:
            logger.error(f"GraphQL find_paths failed: {e}")
            raise
    
    @strawberry.field
    @graphql_resolver_counter.count_calls()
    @graphql_resolver_duration.time()
    @require_permission("graph:read")
    async def discover_connections(self,
                                 info: Info,
                                 node_ids: List[str],
                                 max_depth: int = 3,
                                 batch_size: int = 50) -> strawberry.scalars.JSON:
        """
        Discover connections between multiple nodes.
        
        Args:
            node_ids: List of node IDs to analyze
            max_depth: Maximum search depth
            batch_size: Batch size for parallel processing
            
        Returns:
            Dictionary mapping node pairs to their connection paths
        """
        try:
            graph_service: GraphAnalysisService = info.context["graph_analysis_service"]
            user_context = info.context.get("user")
            
            # Apply permission filtering to node_ids
            filtered_node_ids = await self._filter_accessible_nodes(node_ids, user_context)
            
            if not filtered_node_ids:
                logger.warning(f"No accessible nodes for user {user_context.get('id', 'unknown')}")
                return {}
            
            # Execute service
            connections = await graph_service.discover_connections_batch(
                filtered_node_ids, max_depth, batch_size
            )
            
            # Convert paths to GraphQL format
            graphql_connections = {}
            for key, paths in connections.items():
                graphql_connections[key] = [
                    {
                        "nodes": [{"id": n.id, "type": n.type, "depth": n.depth} for n in path.nodes],
                        "edges": [{"source": e.source_id, "target": e.target_id, "weight": e.weight} for e in path.edges],
                        "total_weight": path.total_weight,
                        "path_length": path.path_length
                    }
                    for path in paths
                ]
            
            logger.info(f"GraphQL discover_connections: found {len(graphql_connections)} connection pairs")
            
            return graphql_connections
            
        except Exception as e:
            logger.error(f"GraphQL discover_connections failed: {e}")
            raise
    
    @strawberry.field
    @graphql_resolver_counter.count_calls()
    @graphql_resolver_duration.time()
    @require_permission("graph:analyze")
    async def analyze_centrality(self,
                               info: Info,
                               node_ids: List[str],
                               centrality_types: Optional[List[str]] = None,
                               normalize: bool = True) -> strawberry.scalars.JSON:
        """
        Analyze node centrality using various measures.
        
        Args:
            node_ids: Nodes to analyze
            centrality_types: Types of centrality to calculate
            normalize: Whether to normalize scores
            
        Returns:
            Centrality analysis results
        """
        try:
            graph_service: GraphAnalysisService = info.context["graph_analysis_service"]
            user_context = info.context.get("user")
            
            # Permission and access filtering
            filtered_node_ids = await self._filter_accessible_nodes(node_ids, user_context)
            
            if not filtered_node_ids:
                return {"error": "No accessible nodes for analysis"}
            
            # Execute analysis
            results = await graph_service.analyze_centrality(
                filtered_node_ids, centrality_types, normalize
            )
            
            logger.info(f"GraphQL analyze_centrality: analyzed {len(filtered_node_ids)} nodes")
            
            return results
            
        except Exception as e:
            logger.error(f"GraphQL analyze_centrality failed: {e}")
            raise
    
    @strawberry.field
    @graphql_resolver_counter.count_calls()
    @graphql_resolver_duration.time()
    @require_permission("graph:analyze")
    async def find_communities(self,
                             info: Info,
                             node_ids: List[str],
                             algorithm: str = "louvain",
                             resolution: float = 1.0) -> strawberry.scalars.JSON:
        """
        Detect communities in the graph.
        
        Args:
            node_ids: Nodes to analyze
            algorithm: Community detection algorithm
            resolution: Resolution parameter for community detection
            
        Returns:
            Community detection results
        """
        try:
            graph_service: GraphAnalysisService = info.context["graph_analysis_service"]
            user_context = info.context.get("user")
            
            # Access filtering
            filtered_node_ids = await self._filter_accessible_nodes(node_ids, user_context)
            
            if not filtered_node_ids:
                return {"error": "No accessible nodes for community analysis"}
            
            # Execute community detection
            results = await graph_service.find_communities(
                filtered_node_ids, algorithm, resolution
            )
            
            logger.info(f"GraphQL find_communities: found {results.get('num_communities', 0)} communities")
            
            return results
            
        except Exception as e:
            logger.error(f"GraphQL find_communities failed: {e}")
            raise
    
    @strawberry.field
    @graphql_resolver_counter.count_calls()
    @graphql_resolver_duration.time()
    @require_permission("graph:read")
    async def get_graph_statistics(self, info: Info) -> strawberry.scalars.JSON:
        """
        Get graph-wide statistics.
        
        Returns:
            Graph statistics including node/edge counts and distributions
        """
        try:
            graph_service: GraphAnalysisService = info.context["graph_analysis_service"]
            
            # Get statistics from repository
            stats = await graph_service.graph_repository.get_graph_statistics()
            
            logger.info("GraphQL get_graph_statistics: retrieved graph statistics")
            
            return stats
            
        except Exception as e:
            logger.error(f"GraphQL get_graph_statistics failed: {e}")
            raise
    
    # Helper methods for permission and access control
    async def _apply_user_constraints(self, query: DeepLinkingQuery, user_context: Dict[str, Any]) -> DeepLinkingQuery:
        """Apply user-specific constraints to query based on permissions."""
        
        # Get user's allowed node types based on their role/scope
        user_allowed_types = await self._get_user_allowed_node_types(user_context)
        
        if user_allowed_types:
            # Merge with existing constraints
            if query.constraints:
                if query.constraints.allowed_node_types:
                    # Intersection of user allowed and query allowed
                    allowed_types = list(set(query.constraints.allowed_node_types) & set(user_allowed_types))
                else:
                    allowed_types = user_allowed_types
                
                # Update constraints
                query.constraints.allowed_node_types = allowed_types
            else:
                # Create new constraints
                query.constraints = PathConstraint(allowed_node_types=user_allowed_types)
        
        return query
    
    async def _filter_accessible_nodes(self, node_ids: List[str], user_context: Dict[str, Any]) -> List[str]:
        """Filter node IDs based on user access permissions."""
        
        # In a real implementation, this would check against user permissions
        # For now, return all nodes (assuming RBAC middleware already filtered)
        
        user_scopes = user_context.get("scopes", []) if user_context else []
        
        # Example: filter based on node ID patterns and user scopes
        if "admin" in user_scopes:
            return node_ids  # Admin can access all nodes
        
        # Regular users might be restricted to certain node patterns
        filtered_nodes = []
        for node_id in node_ids:
            if await self._user_can_access_node(node_id, user_context):
                filtered_nodes.append(node_id)
        
        return filtered_nodes
    
    async def _get_user_allowed_node_types(self, user_context: Dict[str, Any]) -> Optional[List[str]]:
        """Get list of node types the user is allowed to access."""
        
        user_role = user_context.get("role")
        
        # Example role-based node type restrictions
        role_permissions = {
            "admin": None,  # No restrictions
            "analyst": ["DataSource", "ObjectType", "Property"],
            "viewer": ["ObjectType", "Property"],
            "guest": ["Property"]
        }
        
        return role_permissions.get(user_role)
    
    async def _user_can_access_node(self, node_id: str, user_context: Dict[str, Any]) -> bool:
        """Check if user can access specific node."""
        
        # Example implementation - in practice this would check against 
        # actual permission system
        user_id = user_context.get("id") if user_context else None
        user_scopes = user_context.get("scopes", []) if user_context else []
        
        # Admin users can access everything
        if "admin" in user_scopes:
            return True
        
        # Check if node belongs to user's organization/scope
        # This is just an example - real implementation would be more sophisticated
        if user_id and node_id.startswith(f"org_{user_id[:8]}"):
            return True
        
        # Public nodes are accessible to all authenticated users
        if node_id.startswith("public_"):
            return True
        
        return False


@strawberry.type
class GraphAnalysisMutations:
    """GraphQL mutations for graph analysis operations."""
    
    @strawberry.mutation
    @require_permission("graph:write")
    async def invalidate_graph_cache(self, info: Info) -> bool:
        """
        Invalidate graph analysis caches.
        
        Returns:
            True if cache was successfully invalidated
        """
        try:
            graph_service: GraphAnalysisService = info.context["graph_analysis_service"]
            
            # Clear local caches
            graph_service._graph_cache.clear()
            graph_service._path_cache.clear()
            
            # Clear distributed cache if available
            if graph_service.cache:
                # Pattern-based cache invalidation for graph-related keys
                await graph_service.cache.delete_pattern("graph:*")
                await graph_service.cache.delete_pattern("path:*")
            
            logger.info("Graph analysis caches invalidated")
            return True
            
        except Exception as e:
            logger.error(f"Failed to invalidate graph cache: {e}")
            raise


# Schema registration
graph_analysis_queries = GraphAnalysisQueries()
graph_analysis_mutations = GraphAnalysisMutations()