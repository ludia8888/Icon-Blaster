"""
Adaptive rate limiting based on system load
"""
import asyncio
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging

from .models import RateLimitConfig, RateLimitAlgorithm
from ..common.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter that adjusts limits based on system conditions
    """
    
    def __init__(self):
        self.metrics = MetricsCollector("adaptive_rate_limit")
        self._load_history: list[float] = []
        self._adjustment_history: Dict[str, float] = {}
    
    def adjust_limits(
        self, 
        config: RateLimitConfig,
        load_factor: float
    ) -> RateLimitConfig:
        """
        Adjust rate limits based on system load
        
        Args:
            config: Base configuration
            load_factor: Current system load (0.0 - 2.0+)
                        1.0 = normal, <1.0 = low load, >1.0 = high load
        
        Returns:
            Adjusted configuration
        """
        if not config.adaptive_enabled:
            return config
        
        # Record load
        self._load_history.append(load_factor)
        if len(self._load_history) > 100:
            self._load_history.pop(0)
        
        # Calculate adjustment factor
        adjustment = self._calculate_adjustment(load_factor, config)
        
        # Create adjusted config
        adjusted_limit = int(config.requests_per_window * adjustment)
        adjusted_limit = max(config.min_requests, min(config.max_requests, adjusted_limit))
        
        adjusted_config = RateLimitConfig(
            requests_per_window=adjusted_limit,
            window_seconds=config.window_seconds,
            algorithm=config.algorithm,
            scope=config.scope,
            burst_size=config.burst_size,
            refill_rate=config.refill_rate,
            adaptive_enabled=False,  # Prevent recursive adjustment
            whitelist=config.whitelist,
            blacklist=config.blacklist,
            custom_limits=config.custom_limits
        )
        
        # Record metrics
        self.metrics.set_gauge(
            "adaptive_adjustment_factor",
            adjustment,
            labels={"algorithm": config.algorithm.value}
        )
        self.metrics.set_gauge(
            "adaptive_limit",
            adjusted_limit,
            labels={"algorithm": config.algorithm.value}
        )
        
        logger.debug(
            f"Adaptive rate limit: load={load_factor:.2f}, "
            f"adjustment={adjustment:.2f}, "
            f"limit={config.requests_per_window}->{adjusted_limit}"
        )
        
        return adjusted_config
    
    def _calculate_adjustment(
        self, 
        load_factor: float,
        config: RateLimitConfig
    ) -> float:
        """
        Calculate adjustment factor based on load
        
        Returns adjustment multiplier (0.1 - 2.0)
        """
        # Base adjustment using inverse relationship
        # High load -> lower limits, Low load -> higher limits
        base_adjustment = 2.0 - load_factor
        
        # Apply smoothing using recent history
        if len(self._load_history) > 5:
            avg_load = sum(self._load_history[-5:]) / 5
            smoothed_adjustment = 2.0 - avg_load
            # Weighted average of current and smoothed
            adjustment = 0.7 * base_adjustment + 0.3 * smoothed_adjustment
        else:
            adjustment = base_adjustment
        
        # Apply scale factor from config
        adjustment = 1.0 + (adjustment - 1.0) * config.scale_factor
        
        # Clamp to reasonable range
        adjustment = max(0.1, min(2.0, adjustment))
        
        return adjustment
    
    async def analyze_performance(
        self,
        time_window: timedelta = timedelta(minutes=5)
    ) -> Dict[str, Any]:
        """
        Analyze adaptive rate limiting performance
        """
        if not self._load_history:
            return {
                "status": "no_data",
                "message": "No load history available"
            }
        
        current_load = self._load_history[-1] if self._load_history else 1.0
        avg_load = sum(self._load_history) / len(self._load_history)
        min_load = min(self._load_history)
        max_load = max(self._load_history)
        
        # Calculate load variance
        variance = sum((x - avg_load) ** 2 for x in self._load_history) / len(self._load_history)
        volatility = variance ** 0.5
        
        # Determine system state
        if avg_load > 1.5:
            state = "overloaded"
            recommendation = "Consider scaling up resources"
        elif avg_load > 1.2:
            state = "high_load"
            recommendation = "Monitor closely, prepare to scale"
        elif avg_load < 0.5:
            state = "underutilized"
            recommendation = "Resources may be over-provisioned"
        else:
            state = "optimal"
            recommendation = "System operating normally"
        
        return {
            "current_load": round(current_load, 2),
            "average_load": round(avg_load, 2),
            "min_load": round(min_load, 2),
            "max_load": round(max_load, 2),
            "volatility": round(volatility, 2),
            "state": state,
            "recommendation": recommendation,
            "samples": len(self._load_history)
        }
    
    def reset_history(self):
        """Reset adaptation history"""
        self._load_history.clear()
        self._adjustment_history.clear()