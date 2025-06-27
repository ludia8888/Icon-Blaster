"""
Enhanced GraphQL Resolvers with Enterprise Features
Integrates DataLoaders, Caching, BFF, and Monitoring
"""
from typing import List, Optional, Dict, Any
import strawberry
from strawberry.types import Info

from core.auth import UserContext as User

from .schema import (
    ObjectType,
    ObjectTypeConnection,
    Property,
    StatusEnum,
    TypeClassEnum,
)
from .resolvers import service_client
from .dataloaders import DataLoaderRegistry, EnterpriseDataLoader
from .cache import GraphQLCache, CacheLevel, CacheKeyBuilder
from .bff import BFFResolver, DataAggregator, BFFRegistry, ClientType
from .monitoring import get_monitor, TracingMiddleware
from .security import GraphQLSecurityValidator, PRODUCTION_SECURITY_CONFIG

from utils.logger import get_logger

logger = get_logger(__name__)


class EnhancedServiceClient:
    """Enhanced service client with DataLoader integration"""
    
    def __init__(self, base_client, loader_registry: DataLoaderRegistry):
        self.base_client = base_client
        self.loader_registry = loader_registry
        
    async def batch_load_object_types(self, ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Batch load object types from schema service with fallback"""
        if not ids:
            return []
            
        # Try batch endpoint first
        url = f"{self.base_client.schema_service_url}/api/v1/batch/object-types"
        try:
            result = await self.base_client.call_service(
                url, "POST", {"ids": ids}, None
            )
            
            # Map results back to requested order
            data = result.get("data", {})
            return [data.get(id) for id in ids]
            
        except Exception as e:
            logger.warning(f"Batch endpoint failed, falling back to individual loads: {e}")
            
            # Fallback: Load individually (less efficient but works)
            results = []
            for id in ids:
                try:
                    # Extract branch and type name from ID
                    parts = id.split(":", 1)
                    if len(parts) == 2:
                        branch, type_name = parts
                        url = f"{self.base_client.schema_service_url}/api/v1/schemas/{branch}/object-types/{type_name}"
                        result = await self.base_client.call_service(url, "GET", None, None)
                        results.append(result)
                    else:
                        results.append(None)
                except Exception as e:
                    logger.error(f"Failed to load object type {id}: {e}")
                    results.append(None)
            
            return results
    
    async def batch_load_properties(self, object_type_ids: List[str]) -> List[List[Dict[str, Any]]]:
        """Batch load properties for multiple object types with fallback"""
        if not object_type_ids:
            return []
            
        # Try batch endpoint first
        url = f"{self.base_client.schema_service_url}/api/v1/batch/properties"
        try:
            result = await self.base_client.call_service(
                url, "POST", {"object_type_ids": object_type_ids}, None
            )
            
            # Extract data mapping
            data = result.get("data", {})
            return [data.get(obj_id, []) for obj_id in object_type_ids]
            
        except Exception as e:
            logger.warning(f"Batch properties endpoint failed, falling back to individual loads: {e}")
            
            # Fallback: Load individually
            results = []
            for obj_id in object_type_ids:
                try:
                    # Extract branch and type name from ID
                    parts = obj_id.split(":", 1)
                    if len(parts) == 2:
                        branch, type_name = parts
                        url = f"{self.base_client.schema_service_url}/api/v1/schemas/{branch}/object-types/{type_name}/properties"
                        result = await self.base_client.call_service(url, "GET", None, None)
                        properties = result.get("properties", []) if isinstance(result, dict) else []
                        results.append(properties)
                    else:
                        results.append([])
                except Exception as e:
                    logger.error(f"Failed to load properties for {obj_id}: {e}")
                    results.append([])
            
            return results


@strawberry.type
class EnhancedQuery:
    """Enhanced GraphQL Query with all enterprise features"""
    
    @strawberry.field
    async def object_types(
        self,
        info: Info,
        branch: str = "main",
        status: Optional[StatusEnum] = None,
        type_class: Optional[TypeClassEnum] = None,
        interface: Optional[str] = None,
        search: Optional[str] = None,
        include_properties: bool = True,
        include_deprecated: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> ObjectTypeConnection:
        """Enhanced ObjectType list with caching and monitoring"""
        
        # Get context components
        context = info.context
        user = context.get("user")
        cache: GraphQLCache = context.get("cache")
        monitor = context.get("monitor")
        loader_registry: DataLoaderRegistry = context.get("loaders")
        bff_resolver: BFFResolver = context.get("bff_resolver")
        
        # Get client profile
        client_profile = bff_resolver.get_client_profile(context) if bff_resolver else None
        
        # Apply client-specific limits
        if client_profile:
            limit = min(limit, client_profile.max_limit)
        
        # Build cache key
        cache_key = CacheKeyBuilder.build_list_key(
            "object_types",
            filters={
                "branch": branch,
                "status": status.value if status else None,
                "type_class": type_class.value if type_class else None,
                "search": search
            },
            pagination={"limit": limit, "offset": offset}
        )
        
        # Try cache first
        if cache:
            cached_result = await cache.get(cache_key)
            if cached_result:
                if monitor:
                    monitor.record_cache_operation(context.get("query_id"), "get", True)
                return ObjectTypeConnection(**cached_result)
        
        # Record cache miss
        if monitor:
            monitor.record_cache_operation(context.get("query_id"), "get", False)
        
        # Call service
        params = {
            "status": status.value if status else None,
            "type_class": type_class.value if type_class else None,
            "limit": limit,
            "offset": offset
        }
        
        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/object-types"
        result = await service_client.call_service(url, "GET", params, user)
        
        # Transform data
        object_types = []
        for item in result.get('data', []):
            object_type = ObjectType(
                id=item.get('id', ''),
                name=item.get('name', ''),
                displayName=item.get('displayName', ''),
                pluralDisplayName=item.get('pluralDisplayName'),
                description=item.get('description'),
                status=StatusEnum(item.get('status', 'active')),
                typeClass=TypeClassEnum(item.get('typeClass', 'object')),
                versionHash=item.get('versionHash', ''),
                createdBy=item.get('createdBy', ''),
                createdAt=item.get('createdAt'),
                modifiedBy=item.get('modifiedBy', ''),
                modifiedAt=item.get('modifiedAt'),
                parentTypes=item.get('parentTypes', []),
                interfaces=item.get('interfaces', []),
                isAbstract=item.get('isAbstract', False),
                icon=item.get('icon'),
                color=item.get('color')
            )
            
            # Properties will be loaded via DataLoader if needed
            if include_properties and loader_registry:
                # Don't load properties here - let field resolver handle it
                pass
            
            object_types.append(object_type)
        
        total_count = result.get('totalCount', len(object_types))
        has_next = offset + limit < total_count
        has_prev = offset > 0
        
        connection = ObjectTypeConnection(
            data=object_types,
            totalCount=total_count,
            hasNextPage=has_next,
            hasPreviousPage=has_prev
        )
        
        # Cache the result
        if cache:
            cache_level = CacheLevel.STATIC if branch == "main" else CacheLevel.NORMAL
            await cache.set(
                cache_key,
                connection.dict(),
                cache_level=cache_level,
                dependencies=[("branch", branch)]
            )
        
        return connection
    
    @strawberry.field
    async def object_type(
        self,
        info: Info,
        id: str,
        branch: str = "main"
    ) -> Optional[ObjectType]:
        """Enhanced single object type query with DataLoader"""
        
        # Get context components
        context = info.context
        loader_registry: DataLoaderRegistry = context.get("loaders")
        monitor = context.get("monitor")
        
        if not loader_registry:
            # Fallback to direct service call
            url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/object-types/{id}"
            result = await service_client.call_service(url, "GET", None, context.get("user"))
            
            if not result:
                return None
                
            return ObjectType(**result)
        
        # Use DataLoader for batching
        enhanced_client = EnhancedServiceClient(service_client, loader_registry)
        loader = loader_registry.get_loader(
            "object_type",
            enhanced_client.batch_load_object_types
        )
        
        # Record DataLoader usage
        if monitor:
            monitor.record_dataloader_batch(
                context.get("query_id"),
                "object_type",
                1  # Will be batched with other requests
            )
        
        # Load via DataLoader
        data = await loader.load(id)
        if not data:
            return None
        
        return ObjectType(**data)


# Field resolvers with DataLoader
@strawberry.field
async def resolve_properties(
    self: ObjectType,
    info: Info
) -> List[Property]:
    """Resolve properties using DataLoader to prevent N+1"""
    
    context = info.context
    loader_registry: DataLoaderRegistry = context.get("loaders")
    monitor = context.get("monitor")
    
    if not loader_registry or not self.id:
        # Return empty if no loaders or ID
        return []
    
    # Get enhanced client
    enhanced_client = EnhancedServiceClient(service_client, loader_registry)
    
    # Get or create properties loader
    loader = loader_registry.get_loader(
        "properties_by_type",
        enhanced_client.batch_load_properties
    )
    
    # Record DataLoader usage
    if monitor:
        monitor.record_dataloader_batch(
            context.get("query_id"),
            "properties_by_type",
            1
        )
    
    # Load properties
    properties_data = await loader.load(self.id)
    
    # Convert to Property objects
    properties = []
    for prop_data in properties_data:
        properties.append(Property(
            id=prop_data.get('id', ''),
            objectTypeId=prop_data.get('objectTypeId', ''),
            name=prop_data.get('name', ''),
            displayName=prop_data.get('displayName', ''),
            dataType=prop_data.get('dataType', ''),
            isRequired=prop_data.get('isRequired', False),
            isUnique=prop_data.get('isUnique', False),
            isPrimaryKey=prop_data.get('isPrimaryKey', False),
            isSearchable=prop_data.get('isSearchable', False),
            isIndexed=prop_data.get('isIndexed', False),
            defaultValue=prop_data.get('defaultValue'),
            description=prop_data.get('description'),
            enumValues=prop_data.get('enumValues', []),
            linkedObjectType=prop_data.get('linkedObjectType'),
            status=StatusEnum(prop_data.get('status', 'active')),
            versionHash=prop_data.get('versionHash', ''),
            createdBy=prop_data.get('createdBy', ''),
            createdAt=prop_data.get('createdAt'),
            modifiedBy=prop_data.get('modifiedBy', ''),
            modifiedAt=prop_data.get('modifiedAt')
        ))
    
    return properties


# Add property resolver to ObjectType
ObjectType.properties = resolve_properties


def create_enhanced_context(
    request,
    user: Optional[User],
    redis_client=None
) -> Dict[str, Any]:
    """Create enhanced GraphQL context with all components"""
    
    # Get monitor
    monitor = get_monitor()
    
    # Extract operation info
    query_data = request.json() if hasattr(request, 'json') else {}
    operation_type = "query"  # Would be extracted from query
    operation_name = query_data.get("operationName")
    query_string = query_data.get("query", "")
    
    # Create monitoring context
    monitoring_context = monitor.start_query(
        f"{request.url.path}:{id(request)}",
        operation_type,
        operation_name,
        query_string
    )
    
    # Create components
    context = {
        "request": request,
        "user": user,
        "monitor": monitor,
        "query_id": monitoring_context["query_id"],
        "query_metrics": monitoring_context["query_metrics"]
    }
    
    # Add Redis-based components if available
    if redis_client:
        # Cache
        context["cache"] = GraphQLCache(redis_client)
        
        # DataLoader registry
        context["loaders"] = DataLoaderRegistry(redis_client)
        
        # BFF components
        registry = BFFRegistry()
        aggregator = DataAggregator(
            context["loaders"],
            context["cache"],
            {"schema_service": service_client}
        )
        context["bff_resolver"] = BFFResolver(aggregator, registry)
        
        # Extract client type from headers
        client_type = ClientType.WEB  # Would be extracted from user-agent
        context["client_type"] = client_type
    
    return context