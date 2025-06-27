"""
ETag Performance Analytics
Provides hooks for analyzing cache effectiveness and performance
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio
import json
from prometheus_client import generate_latest
from utils.logger import get_logger

logger = get_logger(__name__)


class ETagAnalytics:
    """
    Real-time analytics for ETag cache performance
    Tracks hit rates, response times, and effectiveness over time windows
    """
    
    def __init__(self, window_size_minutes: int = 5):
        self.window_size = timedelta(minutes=window_size_minutes)
        
        # Track requests per resource type with sliding window
        self.requests: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # Performance stats
        self.stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "validation_times": [],
            "generation_times": []
        }
        
        # Hooks for external analytics
        self._analytics_hooks: List[callable] = []
        
    def record_request(
        self,
        resource_type: str,
        is_cache_hit: bool,
        response_time_ms: float,
        etag: Optional[str] = None
    ):
        """Record an ETag request for analytics"""
        timestamp = datetime.utcnow()
        
        request_data = {
            "timestamp": timestamp,
            "is_cache_hit": is_cache_hit,
            "response_time_ms": response_time_ms,
            "etag": etag
        }
        
        self.requests[resource_type].append(request_data)
        
        # Update global stats
        self.stats["total_requests"] += 1
        if is_cache_hit:
            self.stats["cache_hits"] += 1
        else:
            self.stats["cache_misses"] += 1
            
        # Trigger analytics hooks
        for hook in self._analytics_hooks:
            try:
                hook(resource_type, request_data)
            except Exception as e:
                logger.error(f"Analytics hook error: {e}")
    
    def get_hit_rate(self, resource_type: Optional[str] = None) -> float:
        """Calculate cache hit rate for a resource type or globally"""
        if resource_type:
            requests = self.requests.get(resource_type, [])
            if not requests:
                return 0.0
            hits = sum(1 for r in requests if r["is_cache_hit"])
            return hits / len(requests)
        else:
            # Global hit rate
            total = self.stats["total_requests"]
            if total == 0:
                return 0.0
            return self.stats["cache_hits"] / total
    
    def get_performance_summary(self, resource_type: Optional[str] = None) -> Dict:
        """Get comprehensive performance summary"""
        now = datetime.utcnow()
        cutoff = now - self.window_size
        
        if resource_type:
            requests = [
                r for r in self.requests.get(resource_type, [])
                if r["timestamp"] > cutoff
            ]
        else:
            # Aggregate all resource types
            requests = []
            for reqs in self.requests.values():
                requests.extend([r for r in reqs if r["timestamp"] > cutoff])
        
        if not requests:
            return {
                "window_minutes": self.window_size.total_seconds() / 60,
                "total_requests": 0,
                "cache_hit_rate": 0.0,
                "avg_response_time_ms": 0.0,
                "p95_response_time_ms": 0.0,
                "p99_response_time_ms": 0.0
            }
        
        response_times = [r["response_time_ms"] for r in requests]
        response_times.sort()
        
        hits = sum(1 for r in requests if r["is_cache_hit"])
        
        return {
            "window_minutes": self.window_size.total_seconds() / 60,
            "total_requests": len(requests),
            "cache_hit_rate": hits / len(requests),
            "avg_response_time_ms": sum(response_times) / len(response_times),
            "p95_response_time_ms": response_times[int(len(response_times) * 0.95)],
            "p99_response_time_ms": response_times[int(len(response_times) * 0.99)],
            "unique_etags": len(set(r["etag"] for r in requests if r["etag"]))
        }
    
    def add_analytics_hook(self, hook: callable):
        """Add a custom analytics hook for external processing"""
        self._analytics_hooks.append(hook)
        logger.info(f"Added analytics hook: {hook.__name__}")
    
    def export_metrics(self) -> Dict:
        """Export current metrics for monitoring systems"""
        summary = self.get_performance_summary()
        
        # Add per-resource-type breakdowns
        by_resource = {}
        for resource_type in self.requests.keys():
            by_resource[resource_type] = self.get_performance_summary(resource_type)
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "global": summary,
            "by_resource_type": by_resource,
            "prometheus_metrics": generate_latest().decode('utf-8')
        }
    
    async def start_periodic_reporting(self, interval_seconds: int = 60):
        """Start periodic analytics reporting"""
        while True:
            try:
                metrics = self.export_metrics()
                logger.info(
                    "ETag analytics report",
                    extra={
                        "global_hit_rate": metrics["global"]["cache_hit_rate"],
                        "total_requests": metrics["global"]["total_requests"],
                        "avg_response_ms": metrics["global"]["avg_response_time_ms"]
                    }
                )
                
                # Write to file for external monitoring
                with open("/tmp/etag_analytics.json", "w") as f:
                    json.dump(metrics, f, indent=2)
                    
            except Exception as e:
                logger.error(f"Error in periodic reporting: {e}")
                
            await asyncio.sleep(interval_seconds)


# Global analytics instance
_analytics = ETagAnalytics()


def get_etag_analytics() -> ETagAnalytics:
    """Get the global ETag analytics instance"""
    return _analytics


# Example analytics hooks

def log_slow_requests_hook(resource_type: str, request_data: Dict):
    """Log requests that take longer than 100ms"""
    if request_data["response_time_ms"] > 100:
        logger.warning(
            f"Slow ETag request",
            extra={
                "resource_type": resource_type,
                "response_time_ms": request_data["response_time_ms"],
                "is_cache_hit": request_data["is_cache_hit"]
            }
        )


def track_etag_changes_hook(resource_type: str, request_data: Dict):
    """Track when ETags change (cache invalidation)"""
    # This would track ETag changes over time to understand invalidation patterns
    # Implementation would depend on your specific needs
    pass