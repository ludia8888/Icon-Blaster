"""Startup optimization for embedding service to reduce cold start time."""

import asyncio
import logging
import time
from typing import List, Dict, Any
import os

logger = logging.getLogger(__name__)


class StartupOptimizer:
    """Optimize service startup time."""
    
    def __init__(self):
        self.startup_tasks: List[Dict[str, Any]] = []
        self.critical_tasks: List[Dict[str, Any]] = []
        self.background_tasks: List[Dict[str, Any]] = []
    
    def add_critical_task(self, name: str, func, *args, **kwargs):
        """Add a critical task that must complete before service is ready."""
        self.critical_tasks.append({
            "name": name,
            "func": func,
            "args": args,
            "kwargs": kwargs
        })
    
    def add_background_task(self, name: str, func, *args, **kwargs):
        """Add a background task that can run after service is ready."""
        self.background_tasks.append({
            "name": name,
            "func": func,
            "args": args,
            "kwargs": kwargs
        })
    
    async def optimize_startup(self):
        """Run startup optimization."""
        start_time = time.time()
        
        # Run critical tasks in parallel
        logger.info("Running critical startup tasks...")
        critical_results = await self._run_tasks_parallel(self.critical_tasks)
        
        critical_time = time.time() - start_time
        logger.info(f"Critical tasks completed in {critical_time:.2f}s")
        
        # Schedule background tasks
        for task in self.background_tasks:
            asyncio.create_task(self._run_background_task(task))
        
        logger.info(f"Service ready in {critical_time:.2f}s, background tasks scheduled")
        
        return {
            "critical_time": critical_time,
            "critical_tasks": len(self.critical_tasks),
            "background_tasks": len(self.background_tasks)
        }
    
    async def _run_tasks_parallel(self, tasks: List[Dict[str, Any]]) -> List[Any]:
        """Run tasks in parallel and return results."""
        async def run_task(task):
            try:
                start = time.time()
                if asyncio.iscoroutinefunction(task["func"]):
                    result = await task["func"](*task["args"], **task["kwargs"])
                else:
                    result = task["func"](*task["args"], **task["kwargs"])
                duration = time.time() - start
                logger.info(f"Task '{task['name']}' completed in {duration:.2f}s")
                return result
            except Exception as e:
                logger.error(f"Task '{task['name']}' failed: {e}")
                raise
        
        return await asyncio.gather(*[run_task(task) for task in tasks])
    
    async def _run_background_task(self, task: Dict[str, Any]):
        """Run a background task."""
        try:
            logger.info(f"Starting background task: {task['name']}")
            start = time.time()
            
            if asyncio.iscoroutinefunction(task["func"]):
                await task["func"](*task["args"], **task["kwargs"])
            else:
                task["func"](*task["args"], **task["kwargs"])
            
            duration = time.time() - start
            logger.info(f"Background task '{task['name']}' completed in {duration:.2f}s")
            
        except Exception as e:
            logger.error(f"Background task '{task['name']}' failed: {e}")


# Embedding service specific optimizations
class EmbeddingServiceOptimizer(StartupOptimizer):
    """Embedding service specific startup optimizations."""
    
    def __init__(self, service):
        super().__init__()
        self.service = service
        self._setup_tasks()
    
    def _setup_tasks(self):
        """Setup embedding service specific tasks."""
        # Critical tasks - required for service to function
        self.add_critical_task(
            "initialize_default_model",
            self._initialize_default_model
        )
        
        self.add_critical_task(
            "connect_redis",
            self._connect_redis
        )
        
        # Background tasks - can be done after service is ready
        self.add_background_task(
            "preload_popular_models",
            self._preload_popular_models
        )
        
        self.add_background_task(
            "warm_cache",
            self._warm_cache
        )
    
    async def _initialize_default_model(self):
        """Initialize only the default model during startup."""
        default_model = os.getenv("DEFAULT_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        
        # Load only the default model
        logger.info(f"Loading default model: {default_model}")
        await self.service._load_model(default_model)
    
    async def _connect_redis(self):
        """Connect to Redis cache."""
        if hasattr(self.service, '_connect_redis'):
            await self.service._connect_redis()
    
    async def _preload_popular_models(self):
        """Preload popular models in the background."""
        popular_models = [
            "sentence-transformers/all-mpnet-base-v2",
            "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"
        ]
        
        for model in popular_models:
            try:
                logger.info(f"Preloading model: {model}")
                await self.service._load_model(model)
            except Exception as e:
                logger.warning(f"Failed to preload model {model}: {e}")
    
    async def _warm_cache(self):
        """Warm up the cache with common requests."""
        test_texts = [
            "Hello world",
            "Test embedding",
            "Sample document"
        ]
        
        for text in test_texts:
            try:
                await self.service.generate_embedding(text)
            except Exception as e:
                logger.debug(f"Cache warming failed for '{text}': {e}")


# Scheduler service specific optimizations
class SchedulerServiceOptimizer(StartupOptimizer):
    """Scheduler service specific startup optimizations."""
    
    def __init__(self, service):
        super().__init__()
        self.service = service
        self._setup_tasks()
    
    def _setup_tasks(self):
        """Setup scheduler service specific tasks."""
        # Critical tasks
        self.add_critical_task(
            "connect_redis",
            self._connect_redis
        )
        
        self.add_critical_task(
            "start_scheduler",
            self._start_scheduler
        )
        
        # Background tasks
        self.add_background_task(
            "restore_jobs",
            self._restore_jobs
        )
    
    async def _connect_redis(self):
        """Connect to Redis."""
        await self.service._connect_redis()
    
    async def _start_scheduler(self):
        """Start the APScheduler instance."""
        self.service.scheduler.start()
    
    async def _restore_jobs(self):
        """Restore jobs from Redis in the background."""
        await self.service._restore_jobs()


# Event Gateway specific optimizations
class EventGatewayOptimizer(StartupOptimizer):
    """Event Gateway specific startup optimizations."""
    
    def __init__(self, service):
        super().__init__()
        self.service = service
        self._setup_tasks()
    
    def _setup_tasks(self):
        """Setup event gateway specific tasks."""
        # Critical tasks
        self.add_critical_task(
            "connect_nats",
            self._connect_nats
        )
        
        self.add_critical_task(
            "connect_redis",
            self._connect_redis
        )
        
        # Background tasks
        self.add_background_task(
            "create_default_streams",
            self._create_default_streams
        )
        
        self.add_background_task(
            "start_webhook_processor",
            self._start_webhook_processor
        )
    
    async def _connect_nats(self):
        """Connect to NATS."""
        import nats
        self.service.nc = await nats.connect(self.service.nats_url)
        self.service.js = self.service.nc.jetstream()
    
    async def _connect_redis(self):
        """Connect to Redis."""
        import aioredis
        self.service.redis = await aioredis.from_url(
            self.service.redis_url,
            decode_responses=True
        )
    
    async def _create_default_streams(self):
        """Create default streams."""
        await self.service._create_default_streams()
    
    async def _start_webhook_processor(self):
        """Start webhook processor."""
        asyncio.create_task(self.service._webhook_processor())


# General optimization utilities
def optimize_imports():
    """Pre-import commonly used modules to reduce import time."""
    import_list = [
        "json",
        "asyncio",
        "logging",
        "datetime",
        "typing",
        "pydantic",
        "fastapi",
        "httpx",
        "redis",
        "grpc"
    ]
    
    for module in import_list:
        try:
            __import__(module)
        except ImportError:
            pass


def configure_lazy_loading():
    """Configure lazy loading for heavy dependencies."""
    # Set environment variables for lazy loading
    os.environ["TOKENIZERS_PARALLELISM"] = "false"  # Disable HuggingFace parallelism
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"  # Reduce TensorFlow logging
    
    # Disable unnecessary warnings
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=FutureWarning)


def profile_startup(func):
    """Decorator to profile startup time."""
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        
        # Pre-optimization
        optimize_imports()
        configure_lazy_loading()
        
        # Run the function
        result = await func(*args, **kwargs)
        
        duration = time.time() - start_time
        logger.info(f"Total startup time: {duration:.2f}s")
        
        return result
    
    return wrapper