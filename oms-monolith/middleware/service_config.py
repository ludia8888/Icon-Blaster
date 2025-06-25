"""
Service-specific Configuration System
Enterprise-grade configuration management per component
"""

import json
import os
from typing import Any, Dict, Optional, Set, List
from dataclasses import dataclass, field
from enum import Enum
import yaml
from pydantic import BaseModel, Field, validator

from database.clients import RedisHAClient
from utils import logging
from shared.observability import metrics

logger = logging.get_logger(__name__)


class ConfigLevel(str, Enum):
    GLOBAL = "global"
    SERVICE = "service"
    COMPONENT = "component"
    ENDPOINT = "endpoint"
    USER = "user"


class ConfigType(str, Enum):
    FEATURE_FLAG = "feature_flag"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    RETRY = "retry"
    CACHE = "cache"
    SECURITY = "security"
    MONITORING = "monitoring"
    BEHAVIOR = "behavior"


@dataclass
class ConfigValue:
    """Configuration value with metadata"""
    value: Any
    type: ConfigType
    level: ConfigLevel
    description: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    conditions: Dict[str, Any] = field(default_factory=dict)
    override_priority: int = 0
    last_modified: Optional[str] = None
    modified_by: Optional[str] = None


class ServiceConfig(BaseModel):
    """Service-specific configuration"""
    service_name: str
    enabled: bool = True
    
    # Feature flags
    feature_flags: Dict[str, bool] = Field(default_factory=dict)
    
    # Rate limiting
    rate_limits: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    
    # Timeouts
    timeouts: Dict[str, float] = Field(default_factory=dict)
    
    # Retry policies
    retry_policies: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    # Cache settings
    cache_settings: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    # Security settings
    security_settings: Dict[str, Any] = Field(default_factory=dict)
    
    # Monitoring settings
    monitoring_settings: Dict[str, Any] = Field(default_factory=dict)
    
    # Custom behavior
    custom_behavior: Dict[str, Any] = Field(default_factory=dict)


class ComponentConfig(ServiceConfig):
    """Component-specific configuration"""
    component_name: str
    parent_service: str


class EnterpriseConfigManager:
    """
    Enterprise-grade configuration management system
    Features:
    - Hierarchical configuration (global -> service -> component -> endpoint)
    - Dynamic configuration updates
    - A/B testing support
    - Configuration versioning
    - Audit trail
    - Environment-specific overrides
    """
    
    def __init__(
        self,
        redis_client: RedisHAClient,
        config_file: Optional[str] = None,
        environment: str = "production",
        enable_hot_reload: bool = True,
        cache_ttl: int = 300
    ):
        self.redis_client = redis_client
        self.environment = environment
        self.enable_hot_reload = enable_hot_reload
        self.cache_ttl = cache_ttl
        
        # Configuration hierarchy
        self._global_config: Dict[str, ConfigValue] = {}
        self._service_configs: Dict[str, ServiceConfig] = {}
        self._component_configs: Dict[str, ComponentConfig] = {}
        self._endpoint_configs: Dict[str, Dict[str, ConfigValue]] = {}
        self._user_configs: Dict[str, Dict[str, ConfigValue]] = {}
        
        # Configuration cache
        self._config_cache: Dict[str, Any] = {}
        
        # Watchers for dynamic updates
        self._config_watchers: Dict[str, List[callable]] = {}
        
        # Load initial configuration
        if config_file and os.path.exists(config_file):
            self._load_config_file(config_file)
        
        # Default configurations
        self._initialize_defaults()
        
        # Metrics
        self.config_updates = metrics.Counter(
            'config_updates_total',
            'Total configuration updates',
            ['level', 'type']
        )
        self.config_lookups = metrics.Counter(
            'config_lookups_total',
            'Total configuration lookups',
            ['level', 'hit']
        )
    
    def _initialize_defaults(self):
        """Initialize default configurations"""
        # Global defaults
        self._global_config.update({
            "max_request_size": ConfigValue(
                value=10 * 1024 * 1024,  # 10MB
                type=ConfigType.BEHAVIOR,
                level=ConfigLevel.GLOBAL,
                description="Maximum request size in bytes"
            ),
            "default_timeout": ConfigValue(
                value=30.0,
                type=ConfigType.TIMEOUT,
                level=ConfigLevel.GLOBAL,
                description="Default request timeout in seconds"
            ),
            "enable_distributed_tracing": ConfigValue(
                value=True,
                type=ConfigType.MONITORING,
                level=ConfigLevel.GLOBAL
            )
        })
        
        # Service-specific defaults
        self._service_configs.update({
            "schema": ServiceConfig(
                service_name="schema",
                feature_flags={
                    "enable_versioning": True,
                    "enable_soft_delete": True,
                    "enable_audit_trail": True
                },
                rate_limits={
                    "default": {"per_minute": 200, "per_hour": 2000},
                    "write": {"per_minute": 50, "per_hour": 500}
                },
                timeouts={
                    "read": 5.0,
                    "write": 10.0,
                    "bulk": 30.0
                },
                retry_policies={
                    "default": {
                        "max_retries": 3,
                        "backoff": "exponential",
                        "base_delay": 1.0
                    }
                },
                cache_settings={
                    "default": {
                        "ttl": 300,
                        "max_size": 1000,
                        "eviction": "lru"
                    }
                }
            ),
            "branch": ServiceConfig(
                service_name="branch",
                feature_flags={
                    "enable_protected_branches": True,
                    "enable_auto_merge": False,
                    "enable_conflict_resolution": True
                },
                rate_limits={
                    "default": {"per_minute": 100, "per_hour": 1000},
                    "merge": {"per_minute": 10, "per_hour": 100}
                },
                timeouts={
                    "merge": 60.0,
                    "diff": 30.0
                }
            ),
            "validation": ServiceConfig(
                service_name="validation",
                feature_flags={
                    "enable_ml_analysis": True,
                    "enable_impact_prediction": True,
                    "enable_auto_fix": False
                },
                rate_limits={
                    "default": {"per_minute": 50, "per_hour": 500}
                },
                timeouts={
                    "validate": 30.0,
                    "analyze": 60.0
                }
            ),
            "action": ServiceConfig(
                service_name="action",
                feature_flags={
                    "enable_async_execution": True,
                    "enable_webhooks": True,
                    "enable_scheduling": True
                },
                rate_limits={
                    "execute": {"per_minute": 20, "per_hour": 200}
                },
                timeouts={
                    "execute": 300.0,
                    "webhook": 30.0
                },
                retry_policies={
                    "webhook": {
                        "max_retries": 5,
                        "backoff": "exponential",
                        "base_delay": 2.0
                    }
                }
            ),
            "user": ServiceConfig(
                service_name="user",
                feature_flags={
                    "enable_mfa": True,
                    "enable_sso": True,
                    "enable_password_policy": True
                },
                security_settings={
                    "password_min_length": 12,
                    "password_require_special": True,
                    "password_history_count": 12,
                    "mfa_required_roles": ["admin", "developer"],
                    "session_timeout_minutes": 30,
                    "max_concurrent_sessions": 5
                }
            )
        })
    
    def _load_config_file(self, config_file: str):
        """Load configuration from file"""
        try:
            with open(config_file, 'r') as f:
                if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                    config_data = yaml.safe_load(f)
                else:
                    config_data = json.load(f)
            
            # Process configuration data
            self._process_config_data(config_data)
            
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
    
    def _process_config_data(self, config_data: Dict[str, Any]):
        """Process configuration data from file"""
        # Global configuration
        if "global" in config_data:
            for key, value in config_data["global"].items():
                self._global_config[key] = ConfigValue(
                    value=value.get("value"),
                    type=ConfigType(value.get("type", "behavior")),
                    level=ConfigLevel.GLOBAL,
                    description=value.get("description")
                )
        
        # Service configurations
        if "services" in config_data:
            for service_name, service_config in config_data["services"].items():
                self._service_configs[service_name] = ServiceConfig(
                    service_name=service_name,
                    **service_config
                )
    
    async def get_config(
        self,
        key: str,
        level: ConfigLevel = ConfigLevel.GLOBAL,
        service: Optional[str] = None,
        component: Optional[str] = None,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        default: Any = None
    ) -> Any:
        """Get configuration value with hierarchical lookup"""
        # Check cache
        cache_key = f"{level}:{service}:{component}:{endpoint}:{user_id}:{key}"
        if cache_key in self._config_cache:
            self.config_lookups.labels(level=level.value, hit="true").inc()
            return self._config_cache[cache_key]
        
        self.config_lookups.labels(level=level.value, hit="false").inc()
        
        # Hierarchical lookup
        value = None
        
        # User level (highest priority)
        if user_id and user_id in self._user_configs:
            if key in self._user_configs[user_id]:
                value = self._user_configs[user_id][key].value
        
        # Endpoint level
        if value is None and endpoint and endpoint in self._endpoint_configs:
            if key in self._endpoint_configs[endpoint]:
                value = self._endpoint_configs[endpoint][key].value
        
        # Component level
        if value is None and component and component in self._component_configs:
            config = self._component_configs[component]
            value = self._get_value_from_config(config, key)
        
        # Service level
        if value is None and service and service in self._service_configs:
            config = self._service_configs[service]
            value = self._get_value_from_config(config, key)
        
        # Global level
        if value is None and key in self._global_config:
            value = self._global_config[key].value
        
        # Use default if no value found
        if value is None:
            value = default
        
        # Cache the result
        if value is not None:
            self._config_cache[cache_key] = value
            # Set TTL in Redis
            if self.redis_client:
                asyncio.create_task(
                    self.redis_client.setex(
                        f"config:{cache_key}",
                        self.cache_ttl,
                        json.dumps(value)
                    )
                )
        
        return value
    
    def _get_value_from_config(self, config: ServiceConfig, key: str) -> Any:
        """Extract value from core.user.service config"""
        # Check feature flags
        if key in config.feature_flags:
            return config.feature_flags[key]
        
        # Check rate limits
        if key.startswith("rate_limit."):
            parts = key.split(".", 2)
            if len(parts) >= 2 and parts[1] in config.rate_limits:
                return config.rate_limits[parts[1]]
        
        # Check timeouts
        if key.endswith("_timeout") or key in config.timeouts:
            timeout_key = key.replace("_timeout", "") if key.endswith("_timeout") else key
            if timeout_key in config.timeouts:
                return config.timeouts[timeout_key]
        
        # Check other settings
        for attr in ["retry_policies", "cache_settings", "security_settings", "monitoring_settings", "custom_behavior"]:
            settings = getattr(config, attr, {})
            if key in settings:
                return settings[key]
        
        return None
    
    async def set_config(
        self,
        key: str,
        value: Any,
        level: ConfigLevel = ConfigLevel.GLOBAL,
        service: Optional[str] = None,
        component: Optional[str] = None,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        config_type: ConfigType = ConfigType.BEHAVIOR,
        description: Optional[str] = None,
        modified_by: str = "system"
    ):
        """Set configuration value"""
        config_value = ConfigValue(
            value=value,
            type=config_type,
            level=level,
            description=description,
            modified_by=modified_by,
            last_modified=datetime.now().isoformat()
        )
        
        # Update appropriate configuration store
        if level == ConfigLevel.USER and user_id:
            if user_id not in self._user_configs:
                self._user_configs[user_id] = {}
            self._user_configs[user_id][key] = config_value
        
        elif level == ConfigLevel.ENDPOINT and endpoint:
            if endpoint not in self._endpoint_configs:
                self._endpoint_configs[endpoint] = {}
            self._endpoint_configs[endpoint][key] = config_value
        
        elif level == ConfigLevel.COMPONENT and component:
            if component not in self._component_configs:
                self._component_configs[component] = ComponentConfig(
                    service_name=service or "unknown",
                    component_name=component,
                    parent_service=service or "unknown"
                )
            self._update_service_config(self._component_configs[component], key, value)
        
        elif level == ConfigLevel.SERVICE and service:
            if service not in self._service_configs:
                self._service_configs[service] = ServiceConfig(service_name=service)
            self._update_service_config(self._service_configs[service], key, value)
        
        else:  # Global
            self._global_config[key] = config_value
        
        # Clear cache
        cache_pattern = f"{level}:*{service}*{component}*{endpoint}*{user_id}*{key}"
        self._clear_cache_pattern(cache_pattern)
        
        # Update metrics
        self.config_updates.labels(level=level.value, type=config_type.value).inc()
        
        # Notify watchers
        await self._notify_watchers(key, value, level, service, component)
        
        # Persist to Redis
        if self.redis_client:
            await self._persist_config(key, config_value, level, service, component, endpoint, user_id)
    
    def _update_service_config(self, config: ServiceConfig, key: str, value: Any):
        """Update service configuration"""
        # Update appropriate section based on key
        if key in config.feature_flags or key.startswith("feature_"):
            config.feature_flags[key] = value
        elif key.startswith("rate_limit."):
            parts = key.split(".", 2)
            if len(parts) >= 2:
                config.rate_limits[parts[1]] = value
        elif key.endswith("_timeout"):
            config.timeouts[key.replace("_timeout", "")] = value
        else:
            config.custom_behavior[key] = value
    
    async def watch_config(
        self,
        key: str,
        callback: callable,
        level: ConfigLevel = ConfigLevel.GLOBAL,
        service: Optional[str] = None,
        component: Optional[str] = None
    ):
        """Watch configuration changes"""
        watch_key = f"{level}:{service}:{component}:{key}"
        if watch_key not in self._config_watchers:
            self._config_watchers[watch_key] = []
        self._config_watchers[watch_key].append(callback)
    
    async def _notify_watchers(
        self,
        key: str,
        value: Any,
        level: ConfigLevel,
        service: Optional[str],
        component: Optional[str]
    ):
        """Notify configuration watchers"""
        watch_key = f"{level}:{service}:{component}:{key}"
        
        if watch_key in self._config_watchers:
            for callback in self._config_watchers[watch_key]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(key, value)
                    else:
                        callback(key, value)
                except Exception as e:
                    logger.error(f"Error notifying config watcher: {e}")
    
    def _clear_cache_pattern(self, pattern: str):
        """Clear cache entries matching pattern"""
        keys_to_remove = [k for k in self._config_cache.keys() if self._matches_pattern(k, pattern)]
        for key in keys_to_remove:
            del self._config_cache[key]
    
    def _matches_pattern(self, key: str, pattern: str) -> bool:
        """Check if key matches pattern"""
        # Simple pattern matching with wildcards
        import re
        regex_pattern = pattern.replace("*", ".*")
        return bool(re.match(regex_pattern, key))
    
    async def _persist_config(
        self,
        key: str,
        config_value: ConfigValue,
        level: ConfigLevel,
        service: Optional[str],
        component: Optional[str],
        endpoint: Optional[str],
        user_id: Optional[str]
    ):
        """Persist configuration to Redis"""
        redis_key = f"config:{level.value}:{service or 'global'}:{component or 'none'}:{endpoint or 'none'}:{user_id or 'none'}:{key}"
        await self.redis_client.set(
            redis_key,
            json.dumps({
                "value": config_value.value,
                "type": config_value.type.value,
                "level": config_value.level.value,
                "description": config_value.description,
                "modified_by": config_value.modified_by,
                "last_modified": config_value.last_modified
            })
        )
    
    async def get_service_config(self, service: str) -> ServiceConfig:
        """Get complete service configuration"""
        if service in self._service_configs:
            return self._service_configs[service]
        
        # Load from Redis if not in memory
        if self.redis_client:
            config_data = await self.redis_client.get(f"service_config:{service}")
            if config_data:
                return ServiceConfig(**json.loads(config_data))
        
        # Return default
        return ServiceConfig(service_name=service)
    
    async def get_feature_flag(
        self,
        flag: str,
        service: Optional[str] = None,
        user_id: Optional[str] = None,
        default: bool = False
    ) -> bool:
        """Get feature flag value"""
        return await self.get_config(
            flag,
            level=ConfigLevel.SERVICE if service else ConfigLevel.GLOBAL,
            service=service,
            user_id=user_id,
            default=default
        )
    
    async def get_rate_limit(
        self,
        limit_type: str,
        service: str,
        endpoint: Optional[str] = None,
        default: Optional[Dict[str, int]] = None
    ) -> Dict[str, int]:
        """Get rate limit configuration"""
        key = f"rate_limit.{limit_type}"
        return await self.get_config(
            key,
            level=ConfigLevel.ENDPOINT if endpoint else ConfigLevel.SERVICE,
            service=service,
            endpoint=endpoint,
            default=default or {"per_minute": 100, "per_hour": 1000}
        )
    
    async def get_timeout(
        self,
        operation: str,
        service: str,
        default: float = 30.0
    ) -> float:
        """Get timeout configuration"""
        return await self.get_config(
            f"{operation}_timeout",
            level=ConfigLevel.SERVICE,
            service=service,
            default=default
        )
    
    async def export_config(self, format: str = "yaml") -> str:
        """Export current configuration"""
        config_data = {
            "global": {
                key: {
                    "value": cv.value,
                    "type": cv.type.value,
                    "description": cv.description
                }
                for key, cv in self._global_config.items()
            },
            "services": {
                name: config.dict()
                for name, config in self._service_configs.items()
            }
        }
        
        if format == "yaml":
            return yaml.dump(config_data, default_flow_style=False)
        else:
            return json.dumps(config_data, indent=2)
    
    async def import_config(self, config_data: str, format: str = "yaml"):
        """Import configuration"""
        if format == "yaml":
            data = yaml.safe_load(config_data)
        else:
            data = json.loads(config_data)
        
        self._process_config_data(data)
    
    def get_all_feature_flags(self, service: Optional[str] = None) -> Dict[str, bool]:
        """Get all feature flags for a service or globally"""
        if service and service in self._service_configs:
            return self._service_configs[service].feature_flags.copy()
        
        # Return global feature flags
        flags = {}
        for key, config_value in self._global_config.items():
            if config_value.type == ConfigType.FEATURE_FLAG:
                flags[key] = config_value.value
        
        return flags
    
    async def enable_feature(self, feature: str, service: Optional[str] = None):
        """Enable a feature flag"""
        await self.set_config(
            feature,
            True,
            level=ConfigLevel.SERVICE if service else ConfigLevel.GLOBAL,
            service=service,
            config_type=ConfigType.FEATURE_FLAG
        )
    
    async def disable_feature(self, feature: str, service: Optional[str] = None):
        """Disable a feature flag"""
        await self.set_config(
            feature,
            False,
            level=ConfigLevel.SERVICE if service else ConfigLevel.GLOBAL,
            service=service,
            config_type=ConfigType.FEATURE_FLAG
        )


# Decorator for feature flags
def feature_flag(flag_name: str, service: Optional[str] = None):
    """Decorator to check feature flag before executing function"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Get config manager from somewhere (e.g., request context)
            config_manager = kwargs.get('config_manager')
            if not config_manager:
                # Fallback to global instance
                from main import service_manager
                config_manager = service_manager.services.get('config_manager')
            
            if config_manager:
                enabled = await config_manager.get_feature_flag(flag_name, service)
                if not enabled:
                    raise Exception(f"Feature '{flag_name}' is not enabled")
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# Usage example:
# @feature_flag("enable_ml_analysis", service="validation")
# async def analyze_with_ml(data):
#     # This function only runs if ML analysis is enabled
#     pass