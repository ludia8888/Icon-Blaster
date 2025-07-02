"""
Backend for Frontend (BFF) Layer
Optimized data aggregation for different client needs
"""
from typing import Any, Dict, List, Optional, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from collections import defaultdict

from pydantic import BaseModel

from api.graphql.dataloaders import DataLoaderRegistry
from api.graphql.cache import GraphQLCache, CacheLevel
from utils.logger import get_logger
from database.clients.unified_http_client import UnifiedHTTPClient, HTTPClientConfig

logger = get_logger(__name__)


class ClientType(str, Enum):
    """Different client types with specific needs"""
    WEB = "web"                    # Full featured web app
    MOBILE = "mobile"              # Limited bandwidth, needs optimization
    PUBLIC_API = "public_api"      # External API, limited fields
    INTERNAL_API = "internal_api"  # Internal services, full access
    ADMIN = "admin"                # Admin dashboard, needs everything


@dataclass
class FieldPolicy:
    """Policy for field inclusion/transformation"""
    include: bool = True
    transform: Optional[Callable[[Any], Any]] = None
    requires_permission: Optional[str] = None
    cache_level: CacheLevel = CacheLevel.NORMAL


@dataclass
class ClientProfile:
    """Profile defining what data a client type needs"""
    client_type: ClientType
    max_depth: int = 10
    default_limit: int = 20
    max_limit: int = 100
    field_policies: Dict[str, FieldPolicy] = field(default_factory=dict)
    excluded_fields: Set[str] = field(default_factory=set)
    required_fields: Set[str] = field(default_factory=set)


class BFFRegistry:
    """Registry of client profiles and their data needs"""
    
    def __init__(self):
        self.profiles = {
            ClientType.WEB: ClientProfile(
                client_type=ClientType.WEB,
                max_depth=10,
                default_limit=50,
                max_limit=200,
                excluded_fields={"internal_metadata", "debug_info"},
                required_fields={"id", "name", "created_at", "updated_at"}
            ),
            
            ClientType.MOBILE: ClientProfile(
                client_type=ClientType.MOBILE,
                max_depth=5,  # Shallow queries for mobile
                default_limit=20,
                max_limit=50,
                excluded_fields={
                    "internal_metadata",
                    "debug_info",
                    "detailed_history",
                    "large_descriptions"
                },
                required_fields={"id", "name", "summary"},
                field_policies={
                    "description": FieldPolicy(
                        transform=lambda x: x[:200] + "..." if len(x) > 200 else x
                    ),
                    "history": FieldPolicy(include=False),  # Don't include history on mobile
                    "relationships": FieldPolicy(
                        transform=lambda x: x[:10] if isinstance(x, list) else x  # Limit relationships
                    )
                }
            ),
            
            ClientType.PUBLIC_API: ClientProfile(
                client_type=ClientType.PUBLIC_API,
                max_depth=3,
                default_limit=100,
                max_limit=1000,
                excluded_fields={
                    "internal_metadata",
                    "debug_info",
                    "internal_id",
                    "cost_metrics",
                    "performance_data"
                },
                field_policies={
                    "sensitive_data": FieldPolicy(
                        include=False
                    ),
                    "public_metrics": FieldPolicy(
                        cache_level=CacheLevel.STATIC  # Cache public data longer
                    )
                }
            ),
            
            ClientType.ADMIN: ClientProfile(
                client_type=ClientType.ADMIN,
                max_depth=15,
                default_limit=100,
                max_limit=1000,
                excluded_fields=set(),  # Admins see everything
                field_policies={
                    "audit_logs": FieldPolicy(
                        requires_permission="admin:audit:read"
                    ),
                    "performance_metrics": FieldPolicy(
                        requires_permission="admin:metrics:read"
                    )
                }
            )
        }
    
    def get_profile(self, client_type: ClientType) -> ClientProfile:
        """Get client profile"""
        return self.profiles.get(client_type, self.profiles[ClientType.WEB])


class DataAggregator:
    """
    Aggregates data from multiple sources efficiently
    Uses DataLoaders to batch requests and prevent N+1
    """
    
    def __init__(
        self,
        loader_registry: DataLoaderRegistry,
        cache: GraphQLCache,
        service_clients: Dict[str, UnifiedHTTPClient]
    ):
        self.loaders = loader_registry
        self.cache = cache
        self.service_clients = service_clients
    
    async def aggregate_object_type_details(
        self,
        object_type_id: str,
        include_properties: bool = True,
        include_relationships: bool = True,
        include_history: bool = False,
        include_metrics: bool = False
    ) -> Dict[str, Any]:
        """
        Aggregate all data for an object type
        Demonstrates efficient parallel data fetching
        """
        tasks = {}
        
        # Base object type (using DataLoader)
        object_type_loader = self.loaders.get_loader(
            "object_type",
            self._batch_load_object_types
        )
        tasks["object_type"] = object_type_loader.load(object_type_id)
        
        # Properties (if requested)
        if include_properties:
            properties_loader = self.loaders.get_loader(
                "properties_by_type",
                self._batch_load_properties_by_type
            )
            tasks["properties"] = properties_loader.load(object_type_id)
        
        # Relationships (if requested)
        if include_relationships:
            tasks["relationships"] = self._load_relationships(object_type_id)
        
        # History (if requested)
        if include_history:
            tasks["history"] = self._load_history(object_type_id)
        
        # Metrics (if requested)
        if include_metrics:
            tasks["metrics"] = self._load_metrics(object_type_id)
        
        # Execute all tasks in parallel
        results = await asyncio.gather(
            *[task for task in tasks.values()],
            return_exceptions=True
        )
        
        # Build result dictionary
        aggregated = {}
        for key, result in zip(tasks.keys(), results):
            if not isinstance(result, Exception):
                aggregated[key] = result
            else:
                logger.error(f"Failed to load {key} for {object_type_id}: {result}")
                aggregated[key] = None
        
        return aggregated
    
    async def aggregate_schema_overview(
        self,
        branch: str = "main",
        client_profile: ClientProfile = None
    ) -> Dict[str, Any]:
        """
        Aggregate schema overview optimized for client type
        """
        cache_key = f"schema_overview:{branch}:{client_profile.client_type if client_profile else 'default'}"
        
        # Check cache
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        # Parallel fetching of all schema components
        tasks = {
            "stats": self._load_schema_stats(branch),
            "recent_changes": self._load_recent_changes(branch, limit=10),
            "object_types": self._load_object_types_summary(branch, client_profile),
            "link_types": self._load_link_types_summary(branch, client_profile),
            "action_types": self._load_action_types_summary(branch, client_profile)
        }
        
        # Add admin-only data if needed
        if client_profile and client_profile.client_type == ClientType.ADMIN:
            tasks["validation_issues"] = self._load_validation_issues(branch)
            tasks["performance_metrics"] = self._load_performance_metrics(branch)
        
        # Execute in parallel
        results = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True
        )
        
        # Build overview
        overview = {
            key: result if not isinstance(result, Exception) else None
            for key, result in zip(tasks.keys(), results)
        }
        
        # Cache the result
        cache_level = CacheLevel.STATIC if branch == "main" else CacheLevel.VOLATILE
        await self.cache.set(cache_key, overview, cache_level=cache_level)
        
        return overview
    
    async def _batch_load_object_types(self, ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Batch load object types"""
        # This would be replaced with actual service call
        client = self.service_clients.get("schema_service")
        if not client:
            return [None] * len(ids)
        
        try:
            response = await client.post(
                "/api/v1/batch/object-types",
                json={"ids": ids}
            )
            data = response.json()
            
            # Map results back to requested order
            id_map = {item["id"]: item for item in data}
            return [id_map.get(id) for id in ids]
            
        except Exception as e:
            logger.error(f"Failed to batch load object types: {e}")
            return [None] * len(ids)
    
    async def _batch_load_properties_by_type(
        self,
        type_ids: List[str]
    ) -> List[List[Dict[str, Any]]]:
        """Batch load properties for multiple types"""
        client = self.service_clients.get("schema_service")
        if not client:
            return [[] for _ in type_ids]
        
        try:
            response = await client.post(
                "/api/v1/batch/properties-by-types",
                json={"type_ids": type_ids}
            )
            data = response.json()
            
            # Group by type_id
            grouped = defaultdict(list)
            for prop in data:
                grouped[prop["object_type_id"]].append(prop)
            
            return [grouped[type_id] for type_id in type_ids]
            
        except Exception as e:
            logger.error(f"Failed to batch load properties: {e}")
            return [[] for _ in type_ids]
    
    async def _load_relationships(self, object_type_id: str) -> Dict[str, Any]:
        """Load relationships for an object type"""
        # Parallel load both incoming and outgoing relationships
        incoming_task = self._load_incoming_relationships(object_type_id)
        outgoing_task = self._load_outgoing_relationships(object_type_id)
        
        incoming, outgoing = await asyncio.gather(
            incoming_task,
            outgoing_task,
            return_exceptions=True
        )
        
        return {
            "incoming": incoming if not isinstance(incoming, Exception) else [],
            "outgoing": outgoing if not isinstance(outgoing, Exception) else []
        }
    
    async def _load_incoming_relationships(self, object_type_id: str) -> List[Dict[str, Any]]:
        """Load incoming relationships"""
        # Implementation would query link types where target = object_type_id
        return []
    
    async def _load_outgoing_relationships(self, object_type_id: str) -> List[Dict[str, Any]]:
        """Load outgoing relationships"""
        # Implementation would query link types where source = object_type_id
        return []
    
    async def _load_history(self, object_type_id: str) -> List[Dict[str, Any]]:
        """Load history for an object type"""
        # Implementation would query history service
        return []
    
    async def _load_metrics(self, object_type_id: str) -> Dict[str, Any]:
        """Load metrics for an object type"""
        # Implementation would query metrics service
        return {
            "usage_count": 0,
            "query_performance": {
                "avg_ms": 0,
                "p99_ms": 0
            }
        }
    
    async def _load_schema_stats(self, branch: str) -> Dict[str, int]:
        """Load schema statistics"""
        return {
            "object_types": 0,
            "link_types": 0,
            "properties": 0,
            "action_types": 0
        }
    
    async def _load_recent_changes(self, branch: str, limit: int) -> List[Dict[str, Any]]:
        """Load recent schema changes"""
        return []
    
    async def _load_object_types_summary(
        self,
        branch: str,
        profile: Optional[ClientProfile]
    ) -> List[Dict[str, Any]]:
        """Load object types summary based on client profile"""
        # Apply client-specific filters and limits
        limit = profile.default_limit if profile else 50
        
        # Would load from service with proper pagination
        return []
    
    async def _load_link_types_summary(
        self,
        branch: str,
        profile: Optional[ClientProfile]
    ) -> List[Dict[str, Any]]:
        """Load link types summary"""
        return []
    
    async def _load_action_types_summary(
        self,
        branch: str,
        profile: Optional[ClientProfile]
    ) -> List[Dict[str, Any]]:
        """Load action types summary"""
        return []
    
    async def _load_validation_issues(self, branch: str) -> List[Dict[str, Any]]:
        """Load validation issues (admin only)"""
        return []
    
    async def _load_performance_metrics(self, branch: str) -> Dict[str, Any]:
        """Load performance metrics (admin only)"""
        return {
            "query_count": 0,
            "avg_response_time": 0,
            "error_rate": 0
        }


class BFFResolver:
    """
    GraphQL resolver that uses BFF patterns
    Optimizes data fetching based on client type
    """
    
    def __init__(
        self,
        aggregator: DataAggregator,
        registry: BFFRegistry
    ):
        self.aggregator = aggregator
        self.registry = registry
    
    def get_client_profile(self, context: Dict[str, Any]) -> ClientProfile:
        """Get client profile from context"""
        # Extract client type from headers or user agent
        client_type = context.get("client_type", ClientType.WEB)
        return self.registry.get_profile(client_type)
    
    async def resolve_object_type(
        self,
        id: str,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Resolve object type with client-optimized data"""
        profile = self.get_client_profile(context)
        
        # Determine what to include based on client profile
        include_properties = "properties" not in profile.excluded_fields
        include_relationships = "relationships" not in profile.excluded_fields
        include_history = (
            "history" not in profile.excluded_fields and
            profile.client_type != ClientType.MOBILE
        )
        
        # Aggregate data
        data = await self.aggregator.aggregate_object_type_details(
            id,
            include_properties=include_properties,
            include_relationships=include_relationships,
            include_history=include_history
        )
        
        # Apply field policies
        return self._apply_field_policies(data, profile)
    
    def _apply_field_policies(
        self,
        data: Dict[str, Any],
        profile: ClientProfile
    ) -> Dict[str, Any]:
        """Apply client-specific field policies"""
        result = {}
        
        for key, value in data.items():
            # Check if field is excluded
            if key in profile.excluded_fields:
                continue
            
            # Apply field policy if exists
            policy = profile.field_policies.get(key)
            if policy:
                if not policy.include:
                    continue
                
                if policy.transform:
                    value = policy.transform(value)
            
            result[key] = value
        
        # Ensure required fields are present
        for field in profile.required_fields:
            if field not in result and field in data:
                result[field] = data[field]
        
        return result