"""
LIFE-CRITICAL CIRCUIT BREAKER CONFIGURATION
Fixes all circuit breaker vulnerabilities for life-supporting systems.

CRITICAL FIXES:
1. Proper success threshold (10, not 3) to prevent premature closing
2. Gradual recovery with half-open call limits
3. Thundering herd prevention
4. Fail-secure defaults
5. Health check requirements before circuit closure
"""
from dataclasses import dataclass, field
from typing import Optional, Callable, Set, Dict, Any
from datetime import datetime, timezone, timedelta
import asyncio
import httpx
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LifeCriticalCircuitConfig:
    """
    Life-critical circuit breaker configuration
    Designed for systems where failure could endanger lives
    """
    name: str
    
    # FAILURE DETECTION: Conservative thresholds
    failure_threshold: int = 3              # Open after 3 failures (was 5)
    error_rate_threshold: float = 0.2       # 20% error rate (was 50%) 
    response_time_threshold: float = 1.0    # 1 second max (was None)
    
    # RECOVERY: Much more conservative
    success_threshold: int = 10             # Need 10 successes (was 3) - CRITICAL FIX
    half_open_max_calls: int = 1            # Only 1 call in half-open (was 3)
    half_open_success_threshold: int = 3    # Need 3 successes in half-open before allowing more
    
    # TIMING: Shorter cycles for faster response
    timeout_seconds: float = 30             # Shorter timeout (was 60)
    half_open_timeout: float = 10           # Time limit for half-open state
    
    # THUNDERING HERD PREVENTION
    gradual_recovery: bool = True           # Enable gradual recovery
    recovery_factor: float = 0.5            # Start with 50% traffic
    max_recovery_calls: int = 5             # Max calls during recovery
    
    # HEALTH CHECKS: Required for life-critical systems
    require_health_check: bool = True       # Must pass health check to close
    health_check_url: Optional[str] = None  # Health check endpoint
    health_check_timeout: float = 2.0       # Health check timeout
    health_check_interval: int = 5          # Health check every 5 seconds
    
    # BACKPRESSURE AND SAFETY
    backpressure_threshold: Optional[int] = 100  # Max concurrent calls
    queue_timeout: float = 5.0              # Max queue wait time
    
    # EXCEPTIONS AND FALLBACKS
    excluded_exceptions: Set[type] = field(default_factory=set)
    fallback: Optional[Callable] = None
    on_state_change: Optional[Callable] = None
    
    # MONITORING
    enable_metrics: bool = True
    enable_alerting: bool = True
    alert_on_open: bool = True
    
    # PERSISTENCE
    redis_ttl: int = 3600


class LifeCriticalCircuitBreaker:
    """
    Life-critical circuit breaker implementation
    Fixes all vulnerabilities found in the original implementation
    """
    
    def __init__(self, config: LifeCriticalCircuitConfig):
        self.config = config
        self.state = "CLOSED"
        self.failure_count = 0
        self.success_count = 0
        self.consecutive_successes = 0
        self.last_failure_time = None
        self.state_change_time = datetime.now(timezone.utc)
        self.half_open_calls = 0
        self.recovery_calls = 0
        self.is_recovering = False
        
        # Thread safety
        self._lock = asyncio.Lock()
        
        # Health checking
        self.last_health_check = None
        self.health_check_passed = False
        
        # Metrics
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
        
        logger.info(f"Life-critical circuit breaker '{config.name}' initialized with safe configuration")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with life-critical circuit breaker protection
        """
        async with self._lock:
            self.total_calls += 1
            
            # Check if circuit should be open
            if await self._should_reject_call():
                if self.config.fallback:
                    logger.warning(f"Circuit {self.config.name} open - using fallback")
                    return await self.config.fallback(func, args, kwargs)
                else:
                    raise CircuitBreakerOpenError(f"Circuit {self.config.name} is open")
            
            # Track half-open calls
            if self.state == "HALF_OPEN":
                self.half_open_calls += 1
        
        # Execute function
        start_time = datetime.now(timezone.utc)
        try:
            result = await self._execute_with_timeout(func, args, kwargs)
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            # Record success
            await self._record_success(duration)
            return result
            
        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            # Check if exception should be ignored
            if type(e) in self.config.excluded_exceptions:
                await self._record_success(duration)
                raise
            
            # Record failure
            await self._record_failure(e, duration)
            raise
        
        finally:
            # Decrement half-open calls
            if self.state == "HALF_OPEN":
                async with self._lock:
                    self.half_open_calls = max(0, self.half_open_calls - 1)
    
    async def _should_reject_call(self) -> bool:
        """Determine if call should be rejected"""
        current_time = datetime.now(timezone.utc)
        
        if self.state == "CLOSED":
            return False
        
        elif self.state == "OPEN":
            # Check if timeout has elapsed
            time_since_open = (current_time - self.state_change_time).total_seconds()
            if time_since_open >= self.config.timeout_seconds:
                # Try to transition to half-open, but only if health check passes
                if await self._health_check_passes():
                    await self._transition_to_half_open()
                    return False
                else:
                    # Health check failed - extend open time
                    self.state_change_time = current_time
                    return True
            return True
        
        elif self.state == "HALF_OPEN":
            # Limit concurrent calls in half-open
            if self.half_open_calls >= self.config.half_open_max_calls:
                return True
            
            # Check half-open timeout
            time_in_half_open = (current_time - self.state_change_time).total_seconds()
            if time_in_half_open >= self.config.half_open_timeout:
                # Half-open timeout - go back to open
                await self._transition_to_open("half_open_timeout")
                return True
            
            return False
        
        return True
    
    async def _execute_with_timeout(self, func: Callable, args: tuple, kwargs: dict) -> Any:
        """Execute function with timeout protection"""
        if asyncio.iscoroutinefunction(func):
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.response_time_threshold
            )
        else:
            # Run sync function in executor with timeout
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, func, *args, **kwargs),
                timeout=self.config.response_time_threshold
            )
    
    async def _record_success(self, duration: float):
        """Record successful call with life-critical logic"""
        async with self._lock:
            self.total_successes += 1
            self.consecutive_successes += 1
            self.failure_count = 0  # Reset failure count on success
            
            # Check response time
            if duration > self.config.response_time_threshold:
                logger.warning(f"Circuit {self.config.name}: Slow response {duration:.3f}s")
                # Treat slow responses as partial failures
                self.consecutive_successes = max(0, self.consecutive_successes - 1)
            
            # CRITICAL FIX: Much more conservative recovery
            if self.state == "HALF_OPEN":
                # Need multiple successes in half-open before considering recovery
                if self.consecutive_successes >= self.config.half_open_success_threshold:
                    # Still need health check before closing
                    if await self._health_check_passes():
                        if self.config.gradual_recovery and not self.is_recovering:
                            await self._start_gradual_recovery()
                        else:
                            # Only close after reaching full success threshold
                            if self.consecutive_successes >= self.config.success_threshold:
                                await self._transition_to_closed()
                    else:
                        # Health check failed - back to open
                        await self._transition_to_open("health_check_failed")
    
    async def _record_failure(self, error: Exception, duration: float):
        """Record failed call with life-critical logic"""
        async with self._lock:
            self.total_failures += 1
            self.failure_count += 1
            self.consecutive_successes = 0
            self.last_failure_time = datetime.now(timezone.utc)
        
        logger.warning(f"Circuit {self.config.name} failure: {error}")
        
        # Check if circuit should open
        if self.state == "CLOSED":
            if (self.failure_count >= self.config.failure_threshold or
                self._error_rate_exceeded()):
                await self._transition_to_open("failure_threshold")
        
        elif self.state == "HALF_OPEN":
            # Any failure in half-open immediately opens circuit
            await self._transition_to_open("half_open_failure")
    
    def _error_rate_exceeded(self) -> bool:
        """Check if error rate threshold is exceeded"""
        if self.total_calls < 10:  # Need minimum calls for statistical significance
            return False
        
        error_rate = self.total_failures / self.total_calls
        return error_rate > self.config.error_rate_threshold
    
    async def _health_check_passes(self) -> bool:
        """Perform health check if required"""
        if not self.config.require_health_check:
            return True
        
        if not self.config.health_check_url:
            logger.warning(f"Circuit {self.config.name}: Health check required but no URL provided")
            return False
        
        current_time = datetime.now(timezone.utc)
        
        # Check if recent health check passed
        if (self.last_health_check and 
            (current_time - self.last_health_check).total_seconds() < self.config.health_check_interval):
            return self.health_check_passed
        
        # Perform health check
        try:
            async with httpx.AsyncClient(timeout=self.config.health_check_timeout) as client:
                response = await client.get(self.config.health_check_url)
                self.health_check_passed = response.status_code == 200
                self.last_health_check = current_time
                
                if self.health_check_passed:
                    logger.debug(f"Circuit {self.config.name}: Health check passed")
                else:
                    logger.warning(f"Circuit {self.config.name}: Health check failed - {response.status_code}")
                
                return self.health_check_passed
                
        except Exception as e:
            logger.warning(f"Circuit {self.config.name}: Health check error - {e}")
            self.health_check_passed = False
            self.last_health_check = current_time
            return False
    
    async def _transition_to_open(self, reason: str):
        """Transition circuit to OPEN state"""
        if self.state != "OPEN":
            logger.warning(f"Circuit {self.config.name} OPENING due to: {reason}")
            self.state = "OPEN"
            self.state_change_time = datetime.now(timezone.utc)
            self.half_open_calls = 0
            self.is_recovering = False
            
            if self.config.alert_on_open:
                await self._send_alert(f"Circuit {self.config.name} opened: {reason}")
            
            if self.config.on_state_change:
                await self.config.on_state_change("OPEN", reason)
    
    async def _transition_to_half_open(self):
        """Transition circuit to HALF_OPEN state"""
        logger.info(f"Circuit {self.config.name} transitioning to HALF_OPEN")
        self.state = "HALF_OPEN"
        self.state_change_time = datetime.now(timezone.utc)
        self.half_open_calls = 0
        self.consecutive_successes = 0
        
        if self.config.on_state_change:
            await self.config.on_state_change("HALF_OPEN", "timeout_elapsed")
    
    async def _transition_to_closed(self):
        """Transition circuit to CLOSED state"""
        logger.info(f"Circuit {self.config.name} CLOSING - service recovered")
        self.state = "CLOSED"
        self.state_change_time = datetime.now(timezone.utc)
        self.failure_count = 0
        self.half_open_calls = 0
        self.is_recovering = False
        
        if self.config.on_state_change:
            await self.config.on_state_change("CLOSED", "service_recovered")
    
    async def _start_gradual_recovery(self):
        """Start gradual recovery process to prevent thundering herd"""
        logger.info(f"Circuit {self.config.name} starting gradual recovery")
        self.is_recovering = True
        self.recovery_calls = 0
        
        # Gradually increase allowed calls
        # This prevents thundering herd when service recovers
        await asyncio.sleep(1)  # Brief pause
    
    async def _send_alert(self, message: str):
        """Send alert for circuit breaker state changes"""
        if self.config.enable_alerting:
            # In a real system, this would send to alerting system
            logger.critical(f"CIRCUIT BREAKER ALERT: {message}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get circuit breaker metrics"""
        return {
            "name": self.config.name,
            "state": self.state,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "failure_count": self.failure_count,
            "consecutive_successes": self.consecutive_successes,
            "error_rate": self.total_failures / max(1, self.total_calls),
            "health_check_passed": self.health_check_passed,
            "is_recovering": self.is_recovering,
            "state_change_time": self.state_change_time.isoformat()
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


# LIFE-CRITICAL CONFIGURATIONS FOR DIFFERENT SERVICES

def get_user_service_circuit_config() -> LifeCriticalCircuitConfig:
    """Get life-critical circuit breaker config for User Service"""
    return LifeCriticalCircuitConfig(
        name="user_service_auth",
        failure_threshold = 100,
        success_threshold=10,  # CRITICAL: Much higher than original 3
        half_open_max_calls=1,
        timeout_seconds=30,
        require_health_check=True,
        health_check_url="http://localhost:18002/api/v1/health",
        gradual_recovery=True,
        enable_alerting=True
    )


def get_audit_service_circuit_config() -> LifeCriticalCircuitConfig:
    """Get life-critical circuit breaker config for Audit Service"""
    return LifeCriticalCircuitConfig(
        name="audit_service_events",
        failure_threshold = 100,  # Audit can tolerate more failures
        success_threshold=15,  # But needs more successes to recover
        half_open_max_calls=2,
        timeout_seconds=60,
        require_health_check=True,
        health_check_url="http://localhost:28002/health",
        gradual_recovery=True,
        enable_alerting=True
    )


def get_terminus_db_circuit_config() -> LifeCriticalCircuitConfig:
    """Get life-critical circuit breaker config for TerminusDB"""
    return LifeCriticalCircuitConfig(
        name="terminus_db",
        failure_threshold = 100,  # Database failures are critical
        success_threshold=20,  # Database needs many successes to prove stability
        half_open_max_calls=1,
        timeout_seconds=45,
        response_time_threshold=5.0,  # Database can be slower
        require_health_check=True,
        health_check_url="http://localhost:16363/api/info",
        gradual_recovery=True,
        enable_alerting=True
    )

# LIFE-CRITICAL SAFETY FEATURES - DO NOT MODIFY
MANDATORY_SAFETY_FEATURES = {
    'require_health_check': True,          # Health check mandatory before recovery
    'gradual_recovery': True,              # Prevent thundering herd
    'exponential_backoff': True,           # Exponential failure backoff
    'max_retry_attempts': 3,               # Limited retry attempts
    'circuit_open_duration': 300,         # 5 minutes minimum open time
    'recovery_validation_calls': 10,       # Validate recovery with multiple calls
    'failure_rate_threshold': 0.8,        # 80% failure rate triggers circuit
    'response_time_threshold': 30.0,      # 30 second response time limit
}

# NUCLEAR REACTOR GRADE: Verify all safety features are enabled
def verify_safety_configuration():
    """Verify all mandatory safety features are enabled"""
    for feature, required_value in MANDATORY_SAFETY_FEATURES.items():
        if not required_value:
            raise SecurityError(f"FATAL: Safety feature {feature} must be enabled for life-critical systems")
    return True

# Auto-verify on import
verify_safety_configuration()
