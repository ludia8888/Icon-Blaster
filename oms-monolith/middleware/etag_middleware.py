"""
ETag Middleware
Handles ETag generation and validation for efficient caching
"""
from typing import Callable, Optional, Dict, Any
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import json
import hashlib
from datetime import datetime, timezone
import time
from prometheus_client import Counter, Histogram, Gauge

from core.versioning.version_service import get_version_service
from models.etag import DeltaRequest
from core.auth import UserContext
from utils.logger import get_logger
from middleware.etag_analytics import get_etag_analytics

logger = get_logger(__name__)

# Prometheus metrics for ETag operations
etag_requests_total = Counter(
    'etag_requests_total',
    'Total number of ETag requests',
    ['method', 'resource_type', 'result']
)

etag_cache_hits = Counter(
    'etag_cache_hits_total',
    'Number of ETag cache hits (304 responses)',
    ['resource_type']
)

etag_cache_misses = Counter(
    'etag_cache_misses_total', 
    'Number of ETag cache misses (200 responses with ETag)',
    ['resource_type']
)

etag_validation_duration = Histogram(
    'etag_validation_duration_seconds',
    'Time spent validating ETags',
    ['resource_type']
)

etag_generation_duration = Histogram(
    'etag_generation_duration_seconds',
    'Time spent generating ETags',
    ['resource_type']
)

etag_cache_effectiveness = Gauge(
    'etag_cache_effectiveness_ratio',
    'Cache hit ratio (hits / total requests)',
    ['resource_type']
)


class ETagMiddleware(BaseHTTPMiddleware):
    """
    Middleware for handling ETags and conditional requests
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.version_service = None
        self.analytics = get_etag_analytics()
        
        # Paths that support ETag
        self.etag_paths = {
            # Schema endpoints
            "/api/v1/schemas/{branch}/object-types": "object_types",
            "/api/v1/schemas/{branch}/object-types/{type_id}": "object_type",
            "/api/v1/schemas/{branch}/link-types": "link_types",
            "/api/v1/schemas/{branch}/link-types/{type_id}": "link_type",
            "/api/v1/schemas/{branch}/action-types": "action_types",
            "/api/v1/schemas/{branch}/action-types/{type_id}": "action_type",
            
            # Branch endpoints
            "/api/v1/branches": "branches",
            "/api/v1/branches/{branch_id}": "branch",
            
            # Proposals
            "/api/v1/proposals": "proposals",
            "/api/v1/proposals/{proposal_id}": "proposal"
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with ETag handling"""
        # Initialize version service if needed
        if not self.version_service:
            self.version_service = await get_version_service()
        
        # Check if this path supports ETag
        resource_type = self._match_etag_path(request.method, request.url.path)
        if not resource_type:
            logger.debug(f"ETag: Path {request.url.path} does not support ETag")
            return await call_next(request)
        
        # Extract resource info
        resource_info = self._extract_resource_info(request.url.path, resource_type)
        if not resource_info:
            logger.debug(f"ETag: Could not extract resource info from {request.url.path}")
            return await call_next(request)
        
        # Handle conditional GET requests
        if request.method == "GET":
            # Check If-None-Match header
            if_none_match = request.headers.get("If-None-Match")
            if if_none_match:
                # Track validation time
                start_time = time.time()
                
                # Validate ETag
                is_valid, current_version = await self.version_service.validate_etag(
                    resource_type=resource_info["type"],
                    resource_id=resource_info["id"],
                    branch=resource_info["branch"],
                    client_etag=if_none_match
                )
                
                # Record validation duration
                validation_time = time.time() - start_time
                etag_validation_duration.labels(resource_type=resource_type).observe(validation_time)
                
                if is_valid:
                    # Cache hit - return 304 Not Modified
                    etag_cache_hits.labels(resource_type=resource_type).inc()
                    etag_requests_total.labels(
                        method=request.method,
                        resource_type=resource_type,
                        result="cache_hit"
                    ).inc()
                    
                    logger.info(
                        "ETag cache hit",
                        extra={
                            "resource_type": resource_type,
                            "resource_id": resource_info["id"],
                            "etag": if_none_match,
                            "validation_time_ms": validation_time * 1000
                        }
                    )
                    
                    # Record analytics
                    self.analytics.record_request(
                        resource_type=resource_type,
                        is_cache_hit=True,
                        response_time_ms=validation_time * 1000,
                        etag=if_none_match
                    )
                    
                    return Response(
                        status_code=status.HTTP_304_NOT_MODIFIED,
                        headers={
                            "ETag": if_none_match,
                            "Cache-Control": "private, max-age=300"
                        }
                    )
            
            # Check for delta request
            if request.headers.get("X-Delta-Request") == "true":
                return await self._handle_delta_request(request, resource_info)
        
        # Process request normally
        response = await call_next(request)
        
        # Add ETag to successful responses
        if response.status_code == 200 and request.method in ["GET", "POST", "PUT"]:
            logger.debug(f"ETag: Processing successful response for {request.url.path}")
            # Get user context
            user = getattr(request.state, "user", None)
            logger.debug(f"ETag: User context present: {user is not None}")
            
            logger.debug(f"ETag: Response type: {type(response)}, has _body: {hasattr(response, '_body')}")
            
            # Handle GET requests separately - no body parsing needed
            if request.method == "GET":
                try:
                    logger.debug(f"ETag: Processing GET request for {resource_info}")
                    
                    # Track generation time
                    start_time = time.time()
                    
                    version = await self.version_service.get_resource_version(
                        resource_type=resource_info["type"],
                        resource_id=resource_info["id"],
                        branch=resource_info["branch"]
                    )
                    
                    generation_time = time.time() - start_time
                    etag_generation_duration.labels(resource_type=resource_type).observe(generation_time)
                    
                    if version:
                        response.headers["ETag"] = version.current_version.etag
                        response.headers["X-Version"] = str(version.current_version.version)
                        response.headers["Cache-Control"] = "private, max-age=300"
                        
                        # Cache miss - returned 200 with ETag
                        etag_cache_misses.labels(resource_type=resource_type).inc()
                        etag_requests_total.labels(
                            method=request.method,
                            resource_type=resource_type,
                            result="cache_miss"
                        ).inc()
                        
                        logger.info(
                            "ETag cache miss - generated new ETag",
                            extra={
                                "resource_type": resource_type,
                                "resource_id": resource_info["id"],
                                "etag": version.current_version.etag,
                                "version": version.current_version.version,
                                "generation_time_ms": generation_time * 1000
                            }
                        )
                        
                        # Record analytics
                        self.analytics.record_request(
                            resource_type=resource_type,
                            is_cache_hit=False,
                            response_time_ms=generation_time * 1000,
                            etag=version.current_version.etag
                        )
                        
                        # Update cache effectiveness ratio
                        self._update_cache_effectiveness(resource_type)
                    else:
                        logger.debug(f"ETag: No version found for resource")
                        etag_requests_total.labels(
                            method=request.method,
                            resource_type=resource_type,
                            result="no_version"
                        ).inc()
                
                except Exception as e:
                    logger.error(f"Error handling ETag for GET: {e}")
                    etag_requests_total.labels(
                        method=request.method,
                        resource_type=resource_type,
                        result="error"
                    ).inc()
            
            # Handle POST/PUT requests - need user and body
            elif request.method in ["POST", "PUT"] and user and hasattr(response, "_body"):
                try:
                    # Parse response body
                    body = response._body
                    if body:
                        content = json.loads(body)
                        change_type = "create" if request.method == "POST" else "update"
                        
                        # Extract fields changed from request
                        fields_changed = []
                        if request.method == "PUT" and hasattr(request, "_body"):
                            try:
                                request_data = json.loads(request._body)
                                fields_changed = list(request_data.keys())
                            except:
                                pass
                        
                        version = await self.version_service.track_change(
                            resource_type=resource_info["type"],
                            resource_id=resource_info["id"],
                            branch=resource_info["branch"],
                            content=content,
                            change_type=change_type,
                            user=user,
                            fields_changed=fields_changed
                        )
                        
                        # Add version headers
                        response.headers["ETag"] = version.current_version.etag
                        response.headers["X-Version"] = str(version.current_version.version)
                        response.headers["X-Commit"] = version.current_version.commit_hash[:12]
                
                except Exception as e:
                    logger.error(f"Error handling ETag for {request.method}: {e}")
        
        return response
    
    async def _handle_delta_request(
        self,
        request: Request,
        resource_info: Dict[str, str]
    ) -> Response:
        """Handle delta request for efficient sync"""
        try:
            # Parse delta request parameters
            delta_request = DeltaRequest(
                client_etag=request.headers.get("If-None-Match"),
                client_version=int(request.headers.get("X-Client-Version", 0)) or None,
                client_commit=request.headers.get("X-Client-Commit"),
                include_full=request.headers.get("X-Include-Full", "false").lower() == "true"
            )
            
            # Get delta response
            delta_response = await self.version_service.get_delta(
                resource_type=resource_info["type"],
                resource_id=resource_info["id"],
                branch=resource_info["branch"],
                delta_request=delta_request
            )
            
            # Return delta response
            return JSONResponse(
                content=delta_response.dict(),
                status_code=200,
                headers={
                    "ETag": delta_response.etag,
                    "X-Delta-Response": "true",
                    "X-Response-Type": delta_response.response_type,
                    "Cache-Control": delta_response.cache_control
                }
            )
            
        except Exception as e:
            logger.error(f"Error handling delta request: {e}")
            return JSONResponse(
                content={"error": "Failed to generate delta"},
                status_code=500
            )
    
    def _match_etag_path(self, method: str, path: str) -> Optional[str]:
        """Check if path supports ETag and return resource type"""
        if method not in ["GET", "POST", "PUT"]:
            return None
        
        # Try to match path patterns
        import re
        for pattern, resource_type in self.etag_paths.items():
            # Convert path pattern to regex
            regex_pattern = pattern
            regex_pattern = re.sub(r'\{[^}]+\}', r'[^/]+', regex_pattern)
            regex_pattern = f"^{regex_pattern}$"
            
            if re.match(regex_pattern, path):
                return resource_type
        
        return None
    
    def _extract_resource_info(self, path: str, resource_type: str) -> Optional[Dict[str, str]]:
        """Extract resource information from path"""
        parts = path.strip("/").split("/")
        
        try:
            if resource_type in ["object_types", "link_types", "action_types"]:
                # Collection endpoint
                branch_idx = parts.index("schemas") + 1
                return {
                    "type": resource_type,
                    "id": f"{parts[branch_idx]}_{resource_type}",  # Composite ID for collections
                    "branch": parts[branch_idx]
                }
            elif resource_type in ["object_type", "link_type", "action_type"]:
                # Individual resource
                branch_idx = parts.index("schemas") + 1
                resource_id = parts[-1]
                return {
                    "type": resource_type,
                    "id": resource_id,
                    "branch": parts[branch_idx]
                }
            elif resource_type == "branches":
                return {
                    "type": resource_type,
                    "id": "all_branches",
                    "branch": "main"  # Branches list is global
                }
            elif resource_type == "branch":
                branch_id = parts[-1]
                return {
                    "type": resource_type,
                    "id": branch_id,
                    "branch": branch_id
                }
            elif resource_type in ["proposals", "proposal"]:
                return {
                    "type": resource_type,
                    "id": parts[-1] if resource_type == "proposal" else "all_proposals",
                    "branch": "main"  # Proposals are typically on main
                }
        except (IndexError, ValueError):
            pass
        
        return None


    def _update_cache_effectiveness(self, resource_type: str):
        """Update the cache effectiveness ratio metric"""
        try:
            # Get current counts from metrics
            hits = 0
            misses = 0
            
            # Calculate from the counter values (this is simplified - in production
            # you'd want to track this per resource type more carefully)
            # For now, we'll update the gauge based on recent performance
            
            # This is a placeholder - in production, you'd aggregate over a time window
            # For demonstration, we'll set it based on the last request
            # A real implementation would use a sliding window or time-based calculation
            
            logger.debug(f"Updated cache effectiveness for {resource_type}")
        except Exception as e:
            logger.error(f"Error updating cache effectiveness: {e}")


def configure_etag_middleware(app):
    """Configure ETag middleware for the application"""
    app.add_middleware(ETagMiddleware)
    logger.info("ETag middleware configured")