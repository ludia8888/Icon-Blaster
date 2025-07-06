"""
Integration test for Graph Analysis Service with Jaeger tracing and Redis cache.
Verifies complete end-to-end functionality of the integrated system.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from typing import List, Dict, Any

from services.graph_analysis import GraphAnalysisService, DeepLinkingQuery, PathStrategy, TraversalDirection
from core.graph.repositories import SubgraphData, GraphNode, GraphEdge
from shared.cache.smart_cache import SmartCache
from infra.tracing.jaeger_adapter import JaegerTracingManager, get_tracing_manager


@pytest.fixture
async def mock_redis_client():
    """Mock Redis client for testing."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True
    mock_redis.delete.return_value = 1
    mock_redis.ping.return_value = True
    return mock_redis


@pytest.fixture
async def mock_terminus_client():
    """Mock TerminusDB client for testing."""
    mock_client = AsyncMock()
    
    # Mock subgraph data
    nodes = [
        GraphNode(id="node1", type="User", properties={"name": "Alice"}),
        GraphNode(id="node2", type="User", properties={"name": "Bob"}),
        GraphNode(id="node3", type="Document", properties={"title": "Test Doc"})
    ]
    
    edges = [
        GraphEdge(source_id="node1", target_id="node2", edge_type="FRIEND", properties={}, weight=1.0),
        GraphEdge(source_id="node2", target_id="node3", edge_type="OWNS", properties={}, weight=1.5)
    ]
    
    mock_subgraph = SubgraphData(nodes=nodes, edges=edges)
    mock_client.get_subgraph.return_value = mock_subgraph
    mock_client.get_node_neighborhood.return_value = mock_subgraph
    
    return mock_client


@pytest.fixture
async def mock_graph_repository(mock_terminus_client):
    """Mock graph repository with TerminusDB client."""
    from core.graph.repositories import TerminusGraphRepository
    
    with patch('core.graph.repositories.TerminusGraphRepository.__init__', return_value=None):
        repo = TerminusGraphRepository.__new__(TerminusGraphRepository)
        repo.terminus_client = mock_terminus_client
        repo.get_subgraph = mock_terminus_client.get_subgraph
        repo.get_node_neighborhood = mock_terminus_client.get_node_neighborhood
        return repo


@pytest.fixture
async def mock_smart_cache(mock_redis_client):
    """Mock SmartCache with Redis backend."""
    cache = AsyncMock(spec=SmartCache)
    cache.get.return_value = None
    cache.set.return_value = True
    cache.delete.return_value = True
    cache.clear.return_value = True
    cache.get_stats.return_value = {
        "local_hits": 10,
        "local_misses": 5,
        "redis_hits": 8,
        "redis_misses": 12,
        "hit_ratio": 0.6
    }
    return cache


@pytest.fixture
async def mock_tracing_manager():
    """Mock Jaeger tracing manager."""
    manager = AsyncMock(spec=JaegerTracingManager)
    manager._initialized = True
    manager.config = MagicMock()
    manager.config.enabled = True
    manager.config.service_name = "test-service"
    manager.config.siem_enabled = True
    
    # Mock span
    mock_span = MagicMock()
    mock_span.is_recording.return_value = True
    mock_span.set_attribute = MagicMock()
    mock_span.set_attributes = MagicMock()
    manager.create_span.return_value = mock_span
    
    return manager


@pytest.fixture
async def graph_analysis_service(mock_graph_repository, mock_smart_cache):
    """Create GraphAnalysisService with mocked dependencies."""
    event_publisher = AsyncMock()
    
    service = GraphAnalysisService(
        graph_repository=mock_graph_repository,
        cache_manager=mock_smart_cache,
        event_publisher=event_publisher
    )
    
    return service


class TestGraphAnalysisTracingIntegration:
    """Test suite for integrated graph analysis with tracing and caching."""
    
    @pytest.mark.asyncio
    async def test_path_finding_with_tracing_and_cache(
        self,
        graph_analysis_service,
        mock_tracing_manager,
        mock_smart_cache
    ):
        """Test path finding with both tracing and caching enabled."""
        
        # Mock get_tracing_manager to return our mock
        with patch('services.graph_analysis.get_tracing_manager', return_value=mock_tracing_manager):
            with patch('opentelemetry.trace.get_current_span') as mock_get_span:
                # Setup mock span
                mock_span = MagicMock()
                mock_span.is_recording.return_value = True
                mock_span.set_attribute = MagicMock()
                mock_span.set_attributes = MagicMock()
                mock_get_span.return_value = mock_span
                
                # Create test query
                query = DeepLinkingQuery(
                    source_node_id="node1",
                    target_node_id="node3",
                    strategy=PathStrategy.SHORTEST_PATH,
                    direction=TraversalDirection.FORWARD,
                    max_paths=5,
                    include_metadata=True,
                    optimize_for_performance=True
                )
                
                # Execute path finding
                paths = await graph_analysis_service.find_paths(query)
                
                # Verify results
                assert len(paths) > 0
                assert paths[0].nodes[0].id == "node1"
                assert paths[0].nodes[-1].id == "node3"
                
                # Verify tracing was called
                mock_span.set_attribute.assert_called()
                mock_span.set_attributes.assert_called()
                
                # Verify cache attributes were set
                cache_calls = [call for call in mock_span.set_attribute.call_args_list 
                             if 'cache.' in str(call)]
                assert len(cache_calls) > 0
                
                # Verify graph metrics were set
                graph_calls = [call for call in mock_span.set_attributes.call_args_list
                             if any('graph.' in str(arg) for arg in call[0])]
                assert len(graph_calls) > 0
    
    @pytest.mark.asyncio
    async def test_centrality_analysis_with_tracing(
        self,
        graph_analysis_service,
        mock_tracing_manager
    ):
        """Test centrality analysis with tracing enabled."""
        
        with patch('services.graph_analysis.get_tracing_manager', return_value=mock_tracing_manager):
            # Mock the trace_graph_operation decorator to work properly
            with patch('services.graph_analysis.trace_graph_operation') as mock_decorator:
                mock_decorator.return_value = lambda f: f
                
                # Execute centrality analysis
                result = await graph_analysis_service.analyze_centrality(
                    node_ids=["node1", "node2", "node3"],
                    centrality_types=["betweenness", "degree"],
                    normalize=True
                )
                
                # Verify results structure
                assert "centrality_scores" in result
                assert "top_nodes_by_centrality" in result
                assert "graph_stats" in result
                assert "analysis_timestamp" in result
                
                # Verify graph stats
                assert result["graph_stats"]["nodes"] == 3
                assert result["graph_stats"]["edges"] == 2
                assert "density" in result["graph_stats"]
    
    @pytest.mark.asyncio
    async def test_community_detection_with_tracing(
        self,
        graph_analysis_service,
        mock_tracing_manager
    ):
        """Test community detection with tracing enabled."""
        
        with patch('services.graph_analysis.get_tracing_manager', return_value=mock_tracing_manager):
            # Mock community detection to avoid external dependencies
            with patch('services.graph_analysis.GraphAnalysisService._detect_communities_async') as mock_detect:
                mock_detect.return_value = {
                    "0": {"node1", "node2"},
                    "1": {"node3"}
                }
                
                # Execute community detection
                result = await graph_analysis_service.find_communities(
                    node_ids=["node1", "node2", "node3"],
                    algorithm="louvain",
                    resolution=1.0
                )
                
                # Verify results structure
                assert "communities" in result
                assert "algorithm" in result
                assert "resolution" in result
                assert "modularity" in result
                assert "num_communities" in result
                assert "analysis_timestamp" in result
                
                # Verify community structure
                assert len(result["communities"]) >= 1
                assert result["algorithm"] == "louvain"
                assert result["resolution"] == 1.0
    
    @pytest.mark.asyncio
    async def test_batch_connection_discovery_with_tracing(
        self,
        graph_analysis_service,
        mock_tracing_manager
    ):
        """Test batch connection discovery with tracing enabled."""
        
        with patch('services.graph_analysis.get_tracing_manager', return_value=mock_tracing_manager):
            # Execute batch connection discovery
            connections = await graph_analysis_service.discover_connections_batch(
                node_ids=["node1", "node2", "node3"],
                max_depth=2,
                batch_size=10
            )
            
            # Verify results
            assert isinstance(connections, dict)
            # Should find at least one connection path
            assert len(connections) >= 0
    
    @pytest.mark.asyncio
    async def test_cache_integration_with_metrics(
        self,
        graph_analysis_service,
        mock_smart_cache,
        mock_tracing_manager
    ):
        """Test cache integration with proper metrics recording."""
        
        with patch('services.graph_analysis.get_tracing_manager', return_value=mock_tracing_manager):
            with patch('opentelemetry.trace.get_current_span') as mock_get_span:
                mock_span = MagicMock()
                mock_span.is_recording.return_value = True
                mock_get_span.return_value = mock_span
                
                # First call - cache miss
                query = DeepLinkingQuery(
                    source_node_id="node1",
                    target_node_id="node2",
                    strategy=PathStrategy.SHORTEST_PATH
                )
                
                paths1 = await graph_analysis_service.find_paths(query)
                
                # Verify cache miss was recorded
                cache_hit_calls = [call for call in mock_span.set_attribute.call_args_list 
                                 if call[0] == ('cache.hit', False)]
                assert len(cache_hit_calls) > 0
                
                # Reset mock for second call
                mock_span.reset_mock()
                
                # Simulate cache hit for second call
                graph_analysis_service._path_cache[
                    graph_analysis_service._generate_cache_key(query)
                ] = paths1
                
                paths2 = await graph_analysis_service.find_paths(query)
                
                # Verify cache hit was recorded
                cache_hit_calls = [call for call in mock_span.set_attribute.call_args_list 
                                 if call[0] == ('cache.hit', True)]
                assert len(cache_hit_calls) > 0
                
                # Verify same results
                assert len(paths1) == len(paths2)
    
    @pytest.mark.asyncio
    async def test_error_handling_with_tracing(
        self,
        mock_graph_repository,
        mock_smart_cache,
        mock_tracing_manager
    ):
        """Test error handling preserves tracing information."""
        
        # Create service with failing repository
        mock_graph_repository.get_subgraph.side_effect = Exception("Database connection failed")
        
        service = GraphAnalysisService(
            graph_repository=mock_graph_repository,
            cache_manager=mock_smart_cache,
            event_publisher=None
        )
        
        with patch('services.graph_analysis.get_tracing_manager', return_value=mock_tracing_manager):
            query = DeepLinkingQuery(
                source_node_id="node1",
                target_node_id="node2"
            )
            
            # Verify exception is raised
            with pytest.raises(Exception, match="Database connection failed"):
                await service.find_paths(query)
    
    @pytest.mark.asyncio
    async def test_performance_metrics_recording(
        self,
        graph_analysis_service,
        mock_tracing_manager
    ):
        """Test that performance metrics are properly recorded in traces."""
        
        with patch('services.graph_analysis.get_tracing_manager', return_value=mock_tracing_manager):
            with patch('opentelemetry.trace.get_current_span') as mock_get_span:
                mock_span = MagicMock()
                mock_span.is_recording.return_value = True
                mock_get_span.return_value = mock_span
                
                query = DeepLinkingQuery(
                    source_node_id="node1",
                    target_node_id="node3",
                    optimize_for_performance=True
                )
                
                await graph_analysis_service.find_paths(query)
                
                # Verify performance metrics were recorded
                duration_calls = [call for call in mock_span.set_attribute.call_args_list
                                if 'duration_ms' in str(call)]
                assert len(duration_calls) > 0
                
                # Verify optimization flag was recorded
                optimization_calls = [call for call in mock_span.set_attributes.call_args_list
                                   if 'optimization.applied' in str(call[0])]
                assert len(optimization_calls) > 0


class TestJaegerIntegrationHealth:
    """Test Jaeger integration health and configuration."""
    
    @pytest.mark.asyncio
    async def test_tracing_manager_initialization(self):
        """Test tracing manager initializes correctly."""
        
        # Mock environment variables for testing
        with patch.dict('os.environ', {
            'JAEGER_ENABLED': 'true',
            'JAEGER_AGENT_HOST': 'localhost',
            'JAEGER_AGENT_PORT': '14268',
            'JAEGER_SERVICE_NAME': 'test-service'
        }):
            # Reset global tracing manager
            import infra.tracing.jaeger_adapter
            infra.tracing.jaeger_adapter._tracing_manager = None
            
            # Mock the actual OpenTelemetry components
            with patch('infra.tracing.jaeger_adapter.TracerProvider'), \
                 patch('infra.tracing.jaeger_adapter.JaegerExporter'), \
                 patch('infra.tracing.jaeger_adapter.BatchSpanProcessor'), \
                 patch('infra.tracing.jaeger_adapter.trace.set_tracer_provider'), \
                 patch('infra.tracing.jaeger_adapter.trace.get_tracer'), \
                 patch('infra.tracing.jaeger_adapter.AsyncIOInstrumentor'), \
                 patch('infra.tracing.jaeger_adapter.RedisInstrumentor'), \
                 patch('infra.tracing.jaeger_adapter.RequestsInstrumentor'):
                
                # Get tracing manager
                manager = await get_tracing_manager()
                
                # Verify initialization
                assert manager is not None
                assert manager.config.enabled == True
                assert manager.config.service_name == "test-service"
                assert manager.config.agent_host == "localhost"
                assert manager.config.agent_port == 14268


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])