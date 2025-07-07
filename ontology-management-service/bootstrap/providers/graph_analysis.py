"""
Graph Analysis Service Provider for dependency injection.
Provides singleton graph analysis service with all required dependencies.
"""
from typing import Optional
import asyncio
from .base import SingletonProvider
from ...services.graph_analysis import GraphAnalysisService
from ...core.graph.repositories import TerminusGraphRepository, CachedGraphRepository, IGraphRepository
from ...database.clients.terminus_db import TerminusDBClient
from ...shared.cache.smart_cache import SmartCache, create_graph_cache, create_path_cache
from ...core.events.unified_publisher import UnifiedEventPublisher
from ...config.redis_config import get_redis_client
from ...infra.tracing.jaeger_adapter import get_tracing_manager
from common_logging.setup import get_logger

logger = get_logger(__name__)


class GraphRepositoryProvider(SingletonProvider[IGraphRepository]):
    """Provider for graph repository with caching."""
    
    def __init__(self, terminus_client: TerminusDBClient, cache_manager: Optional[SmartCache] = None):
        super().__init__()
        self.terminus_client = terminus_client
        self.cache_manager = cache_manager
    
    async def _create(self) -> IGraphRepository:
        """Create graph repository instance."""
        base_repo = TerminusGraphRepository(self.terminus_client)
        
        if self.cache_manager:
            return CachedGraphRepository(base_repo, self.cache_manager)
        
        return base_repo
    
    async def shutdown(self) -> None:
        """Clean up repository resources."""
        if self._instance:
            # Repository cleanup if needed
            logger.info("Graph repository provider shutdown complete")


class GraphAnalysisServiceProvider(SingletonProvider[GraphAnalysisService]):
    """Provider for graph analysis service with all dependencies."""
    
    def __init__(self, 
                 graph_repository_provider: GraphRepositoryProvider,
                 cache_manager: Optional[SmartCache] = None,
                 event_publisher: Optional[UnifiedEventPublisher] = None):
        super().__init__()
        self.graph_repository_provider = graph_repository_provider
        self.cache_manager = cache_manager
        self.event_publisher = event_publisher
    
    async def _create(self) -> GraphAnalysisService:
        """Create graph analysis service instance."""
        graph_repository = await self.graph_repository_provider.provide()
        
        service = GraphAnalysisService(
            graph_repository=graph_repository,
            cache_manager=self.cache_manager,
            event_publisher=self.event_publisher
        )
        
        logger.info("Graph analysis service created with all dependencies")
        return service
    
    async def shutdown(self) -> None:
        """Clean up service resources."""
        if self._instance:
            # Service cleanup if needed
            await self.graph_repository_provider.shutdown()
            logger.info("Graph analysis service provider shutdown complete")


class GraphAnalysisProviderFactory:
    """Factory for creating graph analysis providers with proper configuration."""
    
    @staticmethod
    async def create_production_provider(terminus_client: TerminusDBClient,
                                        cache_manager: Optional[SmartCache] = None,
                                        event_publisher: Optional[UnifiedEventPublisher] = None) -> GraphAnalysisServiceProvider:
        """Create production graph analysis provider with full Redis and tracing integration."""
        
        # Initialize Redis client
        redis_client = None
        try:
            redis_client = await get_redis_client()
            logger.info("Redis client initialized for graph analysis")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis client: {e}")
        
        # Create optimized cache if not provided
        if cache_manager is None:
            cache_manager = await create_graph_cache(
                terminus_client=terminus_client,
                redis_client=redis_client
            )
            logger.info("Created optimized graph cache")
        
        # Initialize tracing
        try:
            await get_tracing_manager()
            logger.info("Distributed tracing initialized for graph analysis")
        except Exception as e:
            logger.warning(f"Failed to initialize tracing: {e}")
        
        # Create repository provider
        repo_provider = GraphRepositoryProvider(
            terminus_client=terminus_client,
            cache_manager=cache_manager
        )
        
        # Create service provider
        service_provider = GraphAnalysisServiceProvider(
            graph_repository_provider=repo_provider,
            cache_manager=cache_manager,
            event_publisher=event_publisher
        )
        
        logger.info("Production graph analysis provider created with full integration")
        return service_provider
    
    @staticmethod
    def create_test_provider(mock_repository: IGraphRepository) -> GraphAnalysisServiceProvider:
        """Create test provider with mock dependencies."""
        
        class MockRepositoryProvider(SingletonProvider[IGraphRepository]):
            def __init__(self, repo: IGraphRepository):
                super().__init__()
                self._repo = repo
            
            async def _create(self) -> IGraphRepository:
                return self._repo
            
            async def shutdown(self) -> None:
                pass
        
        repo_provider = MockRepositoryProvider(mock_repository)
        
        return GraphAnalysisServiceProvider(
            graph_repository_provider=repo_provider,
            cache_manager=None,
            event_publisher=None
        )