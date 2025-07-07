"""
ETag Decorator System
Provides decorators for enabling ETag support on API endpoints
"""
import functools
from typing import Optional, Dict, Any, Callable, Union, List
from enum import Enum
import inspect
import time
from datetime import datetime

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
import structlog

from models.etag import ResourceVersion
from core.auth_utils import UserContext

logger = structlog.get_logger(__name__)


class ETagMode(Enum):
    """ETag validation modes"""
    STRONG = "strong"  # Exact match required
    WEAK = "weak"      # Semantic equivalence allowed
    

class ETagResourceType(Enum):
    """Supported resource types for ETag"""
    OBJECT_TYPE = "object_type"
    OBJECT_TYPES = "object_types"
    LINK_TYPE = "link_type"
    LINK_TYPES = "link_types"
    ACTION_TYPE = "action_type"
    ACTION_TYPES = "action_types"
    BRANCH = "branch"
    BRANCHES = "branches"
    PROPOSAL = "proposal"
    PROPOSALS = "proposals"
    DOCUMENT = "document"
    SCHEMA = "schema"
    CUSTOM = "custom"


class ETagConfig:
    """Configuration for ETag behavior"""
    def __init__(
        self,
        resource_type: Union[ETagResourceType, str],
        mode: ETagMode = ETagMode.WEAK,
        cache_control: str = "private, max-age=300",
        enable_delta: bool = True,
        track_changes: bool = True,
        resource_id_param: Optional[str] = None,
        branch_param: Optional[str] = "branch",
        custom_extractor: Optional[Callable] = None
    ):
        self.resource_type = resource_type if isinstance(resource_type, str) else resource_type.value
        self.mode = mode
        self.cache_control = cache_control
        self.enable_delta = enable_delta
        self.track_changes = track_changes
        self.resource_id_param = resource_id_param
        self.branch_param = branch_param
        self.custom_extractor = custom_extractor


# Global registry of ETag-enabled endpoints
_etag_registry: Dict[str, ETagConfig] = {}


def get_etag_registry() -> Dict[str, ETagConfig]:
    """Get the global ETag registry"""
    return _etag_registry


def enable_etag(
    resource_type: Union[ETagResourceType, str],
    mode: ETagMode = ETagMode.WEAK,
    cache_control: str = "private, max-age=300",
    enable_delta: bool = True,
    track_changes: bool = True,
    resource_id_param: Optional[str] = None,
    branch_param: Optional[str] = "branch",
    custom_extractor: Optional[Callable] = None
):
    """
    Decorator to enable ETag support for an endpoint
    
    Args:
        resource_type: Type of resource being accessed
        mode: Strong or weak ETag validation
        cache_control: Cache-Control header value
        enable_delta: Enable delta/diff responses
        track_changes: Track changes for POST/PUT operations
        resource_id_param: Parameter name for resource ID (auto-detected if None)
        branch_param: Parameter name for branch (default: "branch")
        custom_extractor: Custom function to extract resource info from request
    
    Example:
        @router.get("/schemas/{branch}/object-types/{type_id}")
        @enable_etag(ETagResourceType.OBJECT_TYPE)
        async def get_object_type(branch: str, type_id: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        # Create ETag configuration
        config = ETagConfig(
            resource_type=resource_type,
            mode=mode,
            cache_control=cache_control,
            enable_delta=enable_delta,
            track_changes=track_changes,
            resource_id_param=resource_id_param,
            branch_param=branch_param,
            custom_extractor=custom_extractor
        )
        
        # Extract function signature for parameter detection
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        
        # Auto-detect resource_id parameter if not specified
        if not config.resource_id_param and config.resource_type not in ['branches', 'proposals']:
            # Common parameter names for resource IDs
            id_params = ['id', 'type_id', 'resource_id', 'proposal_id', 'document_id']
            for param in id_params:
                if param in params:
                    config.resource_id_param = param
                    break
        
        # Register endpoint
        endpoint_key = f"{func.__module__}.{func.__name__}"
        _etag_registry[endpoint_key] = config
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request and response from arguments
            request = None
            response = None
            
            # Find Request and Response objects in args/kwargs
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                elif isinstance(arg, Response):
                    response = arg
            
            for key, value in kwargs.items():
                if isinstance(value, Request):
                    request = value
                elif isinstance(value, Response):
                    response = value
            
            # Store ETag config in request state for middleware
            if request:
                request.state.etag_config = config
                request.state.etag_endpoint_key = endpoint_key
            
            # Add correlation ID for tracing
            correlation_id = request.headers.get("X-Correlation-ID") if request else None
            if correlation_id:
                logger.bind(correlation_id=correlation_id)
            
            # Log endpoint call
            logger.info(
                "ETag-enabled endpoint called",
                endpoint=endpoint_key,
                resource_type=config.resource_type,
                mode=config.mode.value,
                method=request.method if request else "unknown"
            )
            
            # Call the actual endpoint
            result = await func(*args, **kwargs)
            
            # For successful responses, ensure ETag headers are set
            if response and response.status_code in [200, 201]:
                if not response.headers.get("ETag"):
                    logger.warning(
                        "ETag-enabled endpoint returned success without ETag",
                        endpoint=endpoint_key,
                        status_code=response.status_code
                    )
            
            return result
        
        # Mark the wrapper as ETag-enabled
        wrapper._etag_enabled = True
        wrapper._etag_config = config
        
        return wrapper
    
    return decorator


def extract_resource_info(
    request: Request,
    config: ETagConfig,
    path_params: Dict[str, Any]
) -> Optional[Dict[str, str]]:
    """
    Extract resource information from request
    
    Returns dict with keys: type, id, branch
    """
    if config.custom_extractor:
        return config.custom_extractor(request, path_params)
    
    resource_info = {
        "type": config.resource_type,
        "branch": "main"  # default branch
    }
    
    # Extract branch
    if config.branch_param and config.branch_param in path_params:
        resource_info["branch"] = path_params[config.branch_param]
    
    # Extract resource ID
    if config.resource_id_param and config.resource_id_param in path_params:
        resource_info["id"] = path_params[config.resource_id_param]
    elif config.resource_type in ["branches", "proposals", "object_types", "link_types", "action_types"]:
        # Collection endpoints - use composite ID
        resource_info["id"] = f"{resource_info['branch']}_{config.resource_type}"
    else:
        # Try to find any ID-like parameter
        for key, value in path_params.items():
            if 'id' in key.lower():
                resource_info["id"] = str(value)
                break
    
    return resource_info if "id" in resource_info else None


def conditional_etag(
    func: Optional[Callable] = None,
    *,
    strong: bool = False,
    max_age: int = 300
):
    """
    Simplified decorator for conditional GET support
    
    Example:
        @router.get("/resources/{id}")
        @conditional_etag(strong=True)
        async def get_resource(id: str):
            ...
    """
    def decorator(f: Callable) -> Callable:
        mode = ETagMode.STRONG if strong else ETagMode.WEAK
        cache_control = f"private, max-age={max_age}"
        
        return enable_etag(
            resource_type=ETagResourceType.CUSTOM,
            mode=mode,
            cache_control=cache_control,
            enable_delta=False,
            track_changes=False
        )(f)
    
    if func is None:
        return decorator
    else:
        return decorator(func)


def batch_etag(
    resource_types: List[Union[ETagResourceType, str]],
    **kwargs
):
    """
    Decorator for endpoints that handle multiple resource types
    
    Example:
        @router.post("/batch/update")
        @batch_etag([ETagResourceType.OBJECT_TYPE, ETagResourceType.LINK_TYPE])
        async def batch_update(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        # Store all resource types in config
        config = ETagConfig(
            resource_type="batch",
            **kwargs
        )
        config.resource_types = [
            rt.value if isinstance(rt, ETagResourceType) else rt 
            for rt in resource_types
        ]
        
        endpoint_key = f"{func.__module__}.{func.__name__}"
        _etag_registry[endpoint_key] = config
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Find request
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if request:
                request.state.etag_config = config
                request.state.etag_endpoint_key = endpoint_key
            
            return await func(*args, **kwargs)
        
        wrapper._etag_enabled = True
        wrapper._etag_config = config
        
        return wrapper
    
    return decorator


class ETagInterceptor:
    """
    Request/Response interceptor for ETag processing
    Can be used for custom ETag logic
    """
    
    async def on_request(
        self,
        request: Request,
        config: ETagConfig,
        resource_info: Dict[str, str]
    ) -> Optional[Response]:
        """
        Called before endpoint execution
        Return a Response to short-circuit the request
        """
        return None
    
    async def on_response(
        self,
        request: Request,
        response: Response,
        config: ETagConfig,
        resource_info: Dict[str, str]
    ) -> Response:
        """
        Called after endpoint execution
        Can modify the response
        """
        return response


# Helper functions for common patterns

def get_etag_config(request: Request) -> Optional[ETagConfig]:
    """Get ETag configuration from request state"""
    return getattr(request.state, 'etag_config', None)


def is_etag_enabled(request: Request) -> bool:
    """Check if current request has ETag enabled"""
    return hasattr(request.state, 'etag_config')


def get_resource_info_from_request(request: Request) -> Optional[Dict[str, str]]:
    """Get resource information from request state"""
    return getattr(request.state, 'etag_resource_info', None)


# Utility decorators for specific resource types

def etag_for_schemas(
    cache_control: str = "private, max-age=600",
    **kwargs
):
    """Decorator specifically for schema endpoints"""
    return enable_etag(
        resource_type=ETagResourceType.SCHEMA,
        cache_control=cache_control,
        **kwargs
    )


def etag_for_documents(
    cache_control: str = "private, max-age=300",
    **kwargs
):
    """Decorator specifically for document endpoints"""
    return enable_etag(
        resource_type=ETagResourceType.DOCUMENT,
        cache_control=cache_control,
        enable_delta=False,  # Documents typically don't need delta
        **kwargs
    )


def etag_for_proposals(
    cache_control: str = "private, max-age=60",
    **kwargs
):
    """Decorator specifically for proposal endpoints"""
    return enable_etag(
        resource_type=ETagResourceType.PROPOSAL,
        cache_control=cache_control,
        **kwargs
    )