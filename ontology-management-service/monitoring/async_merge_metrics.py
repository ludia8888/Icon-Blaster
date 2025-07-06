"""
Async Merge Performance Monitoring
Prometheus metrics for tracking async merge operations
"""
from prometheus_client import Counter, Histogram, Gauge, Info
import time
from typing import Dict, Any
from functools import wraps

# Job metrics
job_requests_total = Counter(
    'async_merge_job_requests_total',
    'Total number of async merge job requests',
    ['job_type', 'status', 'strategy']
)

job_duration_seconds = Histogram(
    'async_merge_job_duration_seconds',
    'Time taken to complete async merge jobs',
    ['job_type', 'strategy', 'status'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600]  # 1s to 1h
)

job_queue_depth = Gauge(
    'async_merge_job_queue_depth',
    'Current number of jobs in queue',
    ['queue_name', 'status']
)

job_worker_active = Gauge(
    'async_merge_workers_active',
    'Number of active worker processes'
)

job_retries_total = Counter(
    'async_merge_job_retries_total',
    'Total number of job retries',
    ['job_type', 'retry_reason']
)

# API metrics
api_response_time_seconds = Histogram(
    'async_merge_api_response_time_seconds',
    'API response time for merge endpoints',
    ['endpoint', 'method', 'status_code'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

api_concurrent_requests = Gauge(
    'async_merge_api_concurrent_requests',
    'Number of concurrent API requests being processed'
)

# System metrics
redis_operations_total = Counter(
    'async_merge_redis_operations_total',
    'Total Redis operations',
    ['operation', 'status']
)

redis_connection_pool_size = Gauge(
    'async_merge_redis_connection_pool_size',
    'Redis connection pool size'
)

# Business metrics
merge_conflicts_total = Counter(
    'async_merge_conflicts_total',
    'Total number of merge conflicts encountered',
    ['conflict_type', 'resolution_strategy']
)

merge_size_bytes = Histogram(
    'async_merge_size_bytes',
    'Size of data being merged in bytes',
    ['merge_strategy'],
    buckets=[1024, 10240, 102400, 1048576, 10485760, 104857600, 1073741824]  # 1KB to 1GB
)

# System info
system_info = Info(
    'async_merge_system_info',
    'System information for async merge service'
)


class MetricsCollector:
    """Collects and reports metrics for async merge operations"""
    
    def __init__(self):
        self.active_requests = 0
    
    def record_job_request(self, job_type: str, strategy: str):
        """Record a new job request"""
        job_requests_total.labels(
            job_type=job_type,
            status='requested',
            strategy=strategy
        ).inc()
    
    def record_job_completion(self, job_type: str, strategy: str, 
                             status: str, duration_seconds: float):
        """Record job completion"""
        job_requests_total.labels(
            job_type=job_type,
            status=status,
            strategy=strategy
        ).inc()
        
        job_duration_seconds.labels(
            job_type=job_type,
            strategy=strategy,
            status=status
        ).observe(duration_seconds)
    
    def record_job_retry(self, job_type: str, reason: str):
        """Record job retry"""
        job_retries_total.labels(
            job_type=job_type,
            retry_reason=reason
        ).inc()
    
    def update_queue_depth(self, queue_name: str, status: str, count: int):
        """Update queue depth gauge"""
        job_queue_depth.labels(
            queue_name=queue_name,
            status=status
        ).set(count)
    
    def update_active_workers(self, count: int):
        """Update active workers count"""
        job_worker_active.set(count)
    
    def record_merge_conflict(self, conflict_type: str, resolution: str):
        """Record merge conflict"""
        merge_conflicts_total.labels(
            conflict_type=conflict_type,
            resolution_strategy=resolution
        ).inc()
    
    def record_merge_size(self, strategy: str, size_bytes: int):
        """Record merge data size"""
        merge_size_bytes.labels(merge_strategy=strategy).observe(size_bytes)
    
    def record_redis_operation(self, operation: str, success: bool):
        """Record Redis operation"""
        status = 'success' if success else 'error'
        redis_operations_total.labels(
            operation=operation,
            status=status
        ).inc()


# Global metrics collector instance
metrics_collector = MetricsCollector()


def track_api_performance(endpoint: str, method: str = 'POST'):
    """Decorator to track API endpoint performance"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            metrics_collector.active_requests += 1
            api_concurrent_requests.set(metrics_collector.active_requests)
            
            status_code = 200
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                # Extract status code from HTTPException if possible
                if hasattr(e, 'status_code'):
                    status_code = e.status_code
                else:
                    status_code = 500
                raise
            finally:
                duration = time.time() - start_time
                metrics_collector.active_requests -= 1
                api_concurrent_requests.set(metrics_collector.active_requests)
                
                api_response_time_seconds.labels(
                    endpoint=endpoint,
                    method=method,
                    status_code=str(status_code)
                ).observe(duration)
        
        return wrapper
    return decorator


def track_job_lifecycle(job_type: str, strategy: str):
    """Decorator to track complete job lifecycle"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Record job start
            metrics_collector.record_job_request(job_type, strategy)
            
            start_time = time.time()
            status = 'failed'
            
            try:
                result = await func(*args, **kwargs)
                status = 'completed'
                return result
            except Exception as e:
                status = 'failed'
                raise
            finally:
                duration = time.time() - start_time
                metrics_collector.record_job_completion(
                    job_type, strategy, status, duration
                )
        
        return wrapper
    return decorator


async def collect_system_metrics():
    """Collect system-wide metrics"""
    try:
        # Update system info
        import platform
        import psutil
        import os
        
        system_info.info({
            'version': os.getenv('APP_VERSION', 'unknown'),
            'python_version': platform.python_version(),
            'platform': platform.platform(),
            'hostname': platform.node(),
            'cpu_count': str(psutil.cpu_count()),
            'memory_total_gb': str(round(psutil.virtual_memory().total / (1024**3), 2))
        })
        
        # Redis metrics
        from bootstrap.providers import RedisProvider
        provider = RedisProvider()
        redis_client = await provider.provide()
        
        try:
            pool_size = redis_client.connection_pool.max_connections
            redis_connection_pool_size.set(pool_size)
            
            # Test Redis connectivity
            await redis_client.ping()
            metrics_collector.record_redis_operation('ping', True)
        except Exception as e:
            metrics_collector.record_redis_operation('ping', False)
        
        # Job queue metrics
        from services.job_service import JobService
        job_service = JobService()
        await job_service.initialize()
        
        stats = await job_service.get_job_stats()
        metrics_collector.update_queue_depth('default', 'queued', stats.queued)
        metrics_collector.update_queue_depth('default', 'in_progress', stats.in_progress)
        
        # Worker metrics (if Celery is available)
        try:
            from workers.celery_app import app as celery_app
            inspect = celery_app.control.inspect()
            active_workers = inspect.active()
            if active_workers:
                total_workers = sum(len(workers) for workers in active_workers.values())
                metrics_collector.update_active_workers(total_workers)
        except Exception:
            pass  # Celery not available or workers not running
            
    except Exception as e:
        # Log error but don't fail
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error collecting system metrics: {e}")


# Export for use in other modules
__all__ = [
    'metrics_collector',
    'track_api_performance', 
    'track_job_lifecycle',
    'collect_system_metrics'
]