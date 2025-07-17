"""
Production-Grade Error Handling Middleware
Provides centralized, security-conscious error handling for all API endpoints
"""

import logging
import uuid
import traceback
import time
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import ValidationError
import httpx

logger = logging.getLogger(__name__)


class ErrorType:
    """Error type constants for categorization"""
    VALIDATION = "validation_error"
    AUTHENTICATION = "authentication_error"
    AUTHORIZATION = "authorization_error"
    NOT_FOUND = "not_found_error"
    CONFLICT = "conflict_error"
    RATE_LIMIT = "rate_limit_error"
    EXTERNAL_SERVICE = "external_service_error"
    DATABASE = "database_error"
    BUSINESS_LOGIC = "business_logic_error"
    SYSTEM = "system_error"
    SECURITY = "security_error"


class ErrorResponse:
    """Standardized error response structure"""
    
    @staticmethod
    def create_error_response(
        error_type: str,
        message: str,
        details: Optional[str] = None,
        request_id: Optional[str] = None,
        status_code: int = 500,
        timestamp: Optional[str] = None,
        path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a standardized error response"""
        
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat() + "Z"
            
        response = {
            "error": {
                "type": error_type,
                "message": message,
                "timestamp": timestamp,
                "status_code": status_code
            }
        }
        
        if details and not _is_production():
            response["error"]["details"] = details
            
        if request_id:
            response["error"]["request_id"] = request_id
            
        if path:
            response["error"]["path"] = path
            
        return response


class ProductionErrorHandler(BaseHTTPMiddleware):
    """
    Production-grade error handling middleware
    
    Features:
    - Request ID tracking
    - Security-conscious error messages
    - Structured logging
    - Performance monitoring
    - Rate limiting protection
    """
    
    def __init__(self, app: FastAPI):
        super().__init__(app)
        self.request_counts = {}  # Simple in-memory rate limiting
        self.error_counts = {}    # Error rate monitoring
        
    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        start_time = time.time()
        
        # Add request ID to request state
        request.state.request_id = request_id
        
        # Basic rate limiting check
        client_ip = request.client.host if request.client else "unknown"
        if self._is_rate_limited(client_ip):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=ErrorResponse.create_error_response(
                    error_type=ErrorType.RATE_LIMIT,
                    message="Too many requests. Please try again later.",
                    request_id=request_id,
                    status_code=429,
                    path=str(request.url.path)
                )
            )
        
        try:
            # Log incoming request
            logger.info(
                f"Request started: {request.method} {request.url.path}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": client_ip,
                    "user_agent": request.headers.get("user-agent", "unknown")
                }
            )
            
            # Process request
            response = await call_next(request)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Log successful response
            logger.info(
                f"Request completed: {response.status_code}",
                extra={
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "processing_time": processing_time,
                    "path": request.url.path
                }
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as exc:
            # Track error occurrence
            self._track_error(client_ip)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Handle the exception
            return await self._handle_exception(exc, request, request_id, processing_time)
    
    def _is_rate_limited(self, client_ip: str) -> bool:
        """Simple rate limiting - 100 requests per minute per IP"""
        current_minute = int(time.time() / 60)
        key = f"{client_ip}:{current_minute}"
        
        count = self.request_counts.get(key, 0)
        if count >= 100:
            return True
            
        self.request_counts[key] = count + 1
        
        # Clean old entries (keep only last 5 minutes)
        keys_to_remove = [k for k in self.request_counts.keys() 
                         if int(k.split(':')[1]) < current_minute - 5]
        for k in keys_to_remove:
            del self.request_counts[k]
            
        return False
    
    def _track_error(self, client_ip: str):
        """Track error rates for monitoring"""
        current_minute = int(time.time() / 60)
        key = f"{client_ip}:{current_minute}"
        
        self.error_counts[key] = self.error_counts.get(key, 0) + 1
        
        # Alert if error rate is too high (>50 errors per minute)
        if self.error_counts[key] > 50:
            logger.warning(
                f"High error rate detected for IP {client_ip}: {self.error_counts[key]} errors/minute"
            )
    
    async def _handle_exception(
        self, 
        exc: Exception, 
        request: Request, 
        request_id: str,
        processing_time: float
    ) -> JSONResponse:
        """Handle different types of exceptions with appropriate responses"""
        
        path = str(request.url.path)
        client_ip = request.client.host if request.client else "unknown"
        
        # Log the exception
        logger.error(
            f"Request failed: {type(exc).__name__}: {str(exc)}",
            extra={
                "request_id": request_id,
                "path": path,
                "client_ip": client_ip,
                "processing_time": processing_time,
                "exception_type": type(exc).__name__
            },
            exc_info=not _is_production()  # Include traceback only in non-production
        )
        
        # Handle specific exception types
        if isinstance(exc, HTTPException):
            return self._handle_http_exception(exc, request_id, path)
        elif isinstance(exc, RequestValidationError):
            return self._handle_validation_exception(exc, request_id, path)
        elif isinstance(exc, ValidationError):
            return self._handle_pydantic_validation_exception(exc, request_id, path)
        elif isinstance(exc, httpx.HTTPError):
            return self._handle_external_service_exception(exc, request_id, path)
        elif isinstance(exc, ConnectionError):
            return self._handle_connection_exception(exc, request_id, path)
        elif isinstance(exc, TimeoutError):
            return self._handle_timeout_exception(exc, request_id, path)
        else:
            return self._handle_generic_exception(exc, request_id, path)
    
    def _handle_http_exception(self, exc: HTTPException, request_id: str, path: str) -> JSONResponse:
        """Handle HTTP exceptions"""
        error_type = ErrorType.SYSTEM
        
        if exc.status_code == 401:
            error_type = ErrorType.AUTHENTICATION
        elif exc.status_code == 403:
            error_type = ErrorType.AUTHORIZATION
        elif exc.status_code == 404:
            error_type = ErrorType.NOT_FOUND
        elif exc.status_code == 409:
            error_type = ErrorType.CONFLICT
        elif exc.status_code == 422:
            error_type = ErrorType.VALIDATION
        elif exc.status_code == 429:
            error_type = ErrorType.RATE_LIMIT
        
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse.create_error_response(
                error_type=error_type,
                message=str(exc.detail),
                request_id=request_id,
                status_code=exc.status_code,
                path=path
            ),
            headers={"X-Request-ID": request_id}
        )
    
    def _handle_validation_exception(
        self, 
        exc: RequestValidationError, 
        request_id: str, 
        path: str
    ) -> JSONResponse:
        """Handle FastAPI validation exceptions"""
        
        # Extract field-specific errors
        field_errors = []
        for error in exc.errors():
            field_errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"]
            })
        
        message = "Request validation failed"
        details = {"field_errors": field_errors} if not _is_production() else None
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse.create_error_response(
                error_type=ErrorType.VALIDATION,
                message=message,
                details=details,
                request_id=request_id,
                status_code=422,
                path=path
            ),
            headers={"X-Request-ID": request_id}
        )
    
    def _handle_pydantic_validation_exception(
        self, 
        exc: ValidationError, 
        request_id: str, 
        path: str
    ) -> JSONResponse:
        """Handle Pydantic validation exceptions"""
        
        message = "Data validation failed"
        details = str(exc) if not _is_production() else None
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse.create_error_response(
                error_type=ErrorType.VALIDATION,
                message=message,
                details=details,
                request_id=request_id,
                status_code=422,
                path=path
            ),
            headers={"X-Request-ID": request_id}
        )
    
    def _handle_external_service_exception(
        self, 
        exc: httpx.HTTPError, 
        request_id: str, 
        path: str
    ) -> JSONResponse:
        """Handle external service errors"""
        
        message = "External service unavailable"
        details = str(exc) if not _is_production() else None
        
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse.create_error_response(
                error_type=ErrorType.EXTERNAL_SERVICE,
                message=message,
                details=details,
                request_id=request_id,
                status_code=503,
                path=path
            ),
            headers={"X-Request-ID": request_id}
        )
    
    def _handle_connection_exception(
        self, 
        exc: ConnectionError, 
        request_id: str, 
        path: str
    ) -> JSONResponse:
        """Handle connection errors"""
        
        message = "Service temporarily unavailable"
        details = str(exc) if not _is_production() else None
        
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse.create_error_response(
                error_type=ErrorType.EXTERNAL_SERVICE,
                message=message,
                details=details,
                request_id=request_id,
                status_code=503,
                path=path
            ),
            headers={"X-Request-ID": request_id}
        )
    
    def _handle_timeout_exception(
        self, 
        exc: TimeoutError, 
        request_id: str, 
        path: str
    ) -> JSONResponse:
        """Handle timeout errors"""
        
        message = "Request timeout"
        details = str(exc) if not _is_production() else None
        
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=ErrorResponse.create_error_response(
                error_type=ErrorType.EXTERNAL_SERVICE,
                message=message,
                details=details,
                request_id=request_id,
                status_code=504,
                path=path
            ),
            headers={"X-Request-ID": request_id}
        )
    
    def _handle_generic_exception(
        self, 
        exc: Exception, 
        request_id: str, 
        path: str
    ) -> JSONResponse:
        """Handle unexpected exceptions"""
        
        # Log full traceback for debugging
        logger.error(
            f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
            extra={"request_id": request_id, "path": path},
            exc_info=True
        )
        
        # Return generic error to user
        message = "Internal server error"
        details = str(exc) if not _is_production() else None
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse.create_error_response(
                error_type=ErrorType.SYSTEM,
                message=message,
                details=details,
                request_id=request_id,
                status_code=500,
                path=path
            ),
            headers={"X-Request-ID": request_id}
        )


def _is_production() -> bool:
    """Check if running in production environment"""
    import os
    return os.getenv("ENVIRONMENT", "development").lower() == "production"


def setup_error_handlers(app: FastAPI):
    """Set up comprehensive error handling for the FastAPI application"""
    
    # Add the middleware
    app.add_middleware(ProductionErrorHandler)
    
    # Additional global exception handlers for specific cases
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
        
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse.create_error_response(
                error_type=ErrorType.NOT_FOUND if exc.status_code == 404 else ErrorType.SYSTEM,
                message=exc.detail,
                request_id=request_id,
                status_code=exc.status_code,
                path=str(request.url.path)
            ),
            headers={"X-Request-ID": request_id}
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
        
        # Extract validation errors
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"]
            })
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse.create_error_response(
                error_type=ErrorType.VALIDATION,
                message="Validation failed",
                details={"errors": errors} if not _is_production() else None,
                request_id=request_id,
                status_code=422,
                path=str(request.url.path)
            ),
            headers={"X-Request-ID": request_id}
        )
    
    logger.info("Production error handlers configured successfully")