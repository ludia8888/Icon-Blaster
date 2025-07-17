"""
Production-Grade Request/Response Validation Middleware
Provides comprehensive validation, sanitization, and security checks
"""

import logging
import time
import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from security.input_sanitizer import sanitize_input, SecurityViolationError

logger = logging.getLogger(__name__)


class SecurityConfig:
    """Security configuration constants"""
    
    # Request size limits
    MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_JSON_DEPTH = 10
    MAX_FIELD_LENGTH = 1000
    MAX_ARRAY_LENGTH = 1000
    
    # Rate limiting
    MAX_REQUESTS_PER_MINUTE = 100
    MAX_REQUESTS_PER_HOUR = 1000
    
    # Security patterns
    SUSPICIOUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # XSS
        r'javascript:',               # JavaScript injection
        r'vbscript:',                # VBScript injection
        r'on\w+\s*=',                # Event handlers
        r'expression\s*\(',          # CSS expression
        r'url\s*\(',                 # CSS URL
        r'@import',                  # CSS import
        r'\beval\s*\(',              # eval() calls
        r'\bexec\s*\(',              # exec() calls
        r'\.\./',                    # Path traversal
        r'\\.\\./',                  # Windows path traversal
        r'union\s+select',           # SQL injection
        r'drop\s+table',             # SQL injection
        r'insert\s+into',            # SQL injection
        r'delete\s+from',            # SQL injection
    ]
    
    # Allowed content types
    ALLOWED_CONTENT_TYPES = [
        'application/json',
        'application/x-www-form-urlencoded',
        'multipart/form-data',
        'text/plain'
    ]


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive request validation middleware
    
    Features:
    - Input sanitization and validation
    - Security pattern detection
    - Request size limits
    - Content type validation
    - JSON structure validation
    - Rate limiting
    - Request logging
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.request_history = {}  # Simple in-memory tracking
        
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        try:
            # Pre-process validation
            await self._validate_request(request)
            
            # Process the request
            response = await call_next(request)
            
            # Post-process validation
            response = await self._validate_response(request, response)
            
            processing_time = time.time() - start_time
            
            # Log successful request
            logger.debug(
                f"Request validated successfully: {request.method} {request.url.path}",
                extra={
                    "processing_time": processing_time,
                    "status_code": response.status_code
                }
            )
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Validation middleware error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Request validation failed"
            )
    
    async def _validate_request(self, request: Request):
        """Comprehensive request validation"""
        
        # 1. Rate limiting check
        await self._check_rate_limits(request)
        
        # 2. Request size validation
        await self._validate_request_size(request)
        
        # 3. Content type validation
        await self._validate_content_type(request)
        
        # 4. Header validation
        await self._validate_headers(request)
        
        # 5. URL validation
        await self._validate_url(request)
        
        # 6. Body validation (if present)
        if request.method in ['POST', 'PUT', 'PATCH']:
            await self._validate_body(request)
    
    async def _check_rate_limits(self, request: Request):
        """Check rate limiting rules"""
        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()
        current_minute = int(current_time / 60)
        current_hour = int(current_time / 3600)
        
        # Initialize tracking for this IP if needed
        if client_ip not in self.request_history:
            self.request_history[client_ip] = {
                'minute_requests': {},
                'hour_requests': {},
                'last_request': current_time
            }
        
        history = self.request_history[client_ip]
        
        # Check requests per minute
        minute_key = current_minute
        minute_count = history['minute_requests'].get(minute_key, 0)
        if minute_count >= SecurityConfig.MAX_REQUESTS_PER_MINUTE:
            logger.warning(f"Rate limit exceeded for IP {client_ip}: {minute_count} requests/minute")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests per minute"
            )
        
        # Check requests per hour
        hour_key = current_hour
        hour_count = history['hour_requests'].get(hour_key, 0)
        if hour_count >= SecurityConfig.MAX_REQUESTS_PER_HOUR:
            logger.warning(f"Rate limit exceeded for IP {client_ip}: {hour_count} requests/hour")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests per hour"
            )
        
        # Update counters
        history['minute_requests'][minute_key] = minute_count + 1
        history['hour_requests'][hour_key] = hour_count + 1
        history['last_request'] = current_time
        
        # Clean old entries
        self._cleanup_request_history(client_ip, current_minute, current_hour)
    
    def _cleanup_request_history(self, client_ip: str, current_minute: int, current_hour: int):
        """Clean up old request history entries"""
        history = self.request_history[client_ip]
        
        # Keep only last 5 minutes
        minute_keys_to_remove = [k for k in history['minute_requests'].keys() 
                               if k < current_minute - 5]
        for k in minute_keys_to_remove:
            del history['minute_requests'][k]
        
        # Keep only last 2 hours
        hour_keys_to_remove = [k for k in history['hour_requests'].keys() 
                             if k < current_hour - 2]
        for k in hour_keys_to_remove:
            del history['hour_requests'][k]
    
    async def _validate_request_size(self, request: Request):
        """Validate request size limits"""
        content_length = request.headers.get('content-length')
        if content_length:
            try:
                size = int(content_length)
                if size > SecurityConfig.MAX_REQUEST_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Request too large. Maximum size: {SecurityConfig.MAX_REQUEST_SIZE} bytes"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Content-Length header"
                )
    
    async def _validate_content_type(self, request: Request):
        """Validate content type"""
        if request.method in ['POST', 'PUT', 'PATCH']:
            content_type = request.headers.get('content-type', '').lower()
            if content_type:
                # Extract base content type (without charset, etc.)
                base_content_type = content_type.split(';')[0].strip()
                if base_content_type not in SecurityConfig.ALLOWED_CONTENT_TYPES:
                    logger.warning(f"Suspicious content type: {content_type}")
                    # Don't block, but log for monitoring
    
    async def _validate_headers(self, request: Request):
        """Validate HTTP headers for security issues"""
        for header_name, header_value in request.headers.items():
            # Check for suspicious patterns in headers
            if self._contains_suspicious_patterns(header_value):
                logger.warning(f"Suspicious pattern in header {header_name}: {header_value}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid header content"
                )
            
            # Check header length
            if len(header_value) > SecurityConfig.MAX_FIELD_LENGTH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Header value too long: {header_name}"
                )
    
    async def _validate_url(self, request: Request):
        """Validate URL for security issues"""
        url_str = str(request.url)
        
        # Check for suspicious patterns in URL
        if self._contains_suspicious_patterns(url_str):
            logger.warning(f"Suspicious pattern in URL: {url_str}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid URL format"
            )
        
        # Check URL length
        if len(url_str) > 2048:  # Standard URL length limit
            raise HTTPException(
                status_code=status.HTTP_414_REQUEST_URI_TOO_LARGE,
                detail="URL too long"
            )
    
    async def _validate_body(self, request: Request):
        """Validate request body content"""
        content_type = request.headers.get('content-type', '').lower()
        
        if 'application/json' in content_type:
            await self._validate_json_body(request)
    
    async def _validate_json_body(self, request: Request):
        """Validate JSON body structure and content"""
        try:
            # Read the body
            body = await request.body()
            if not body:
                return
            
            # Parse JSON
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid JSON format: {str(e)}"
                )
            
            # Validate JSON structure
            self._validate_json_structure(data, depth=0)
            
            # Security sanitization
            try:
                sanitized_data = sanitize_input(data)
                # Store sanitized data for use by endpoints
                request.state.sanitized_body = sanitized_data
            except SecurityViolationError as e:
                logger.warning(f"Security violation in request body: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Request contains potentially malicious content"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"JSON validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request body validation failed"
            )
    
    def _validate_json_structure(self, data: Any, depth: int = 0):
        """Recursively validate JSON structure"""
        if depth > SecurityConfig.MAX_JSON_DEPTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON structure too deep"
            )
        
        if isinstance(data, dict):
            if len(data) > SecurityConfig.MAX_ARRAY_LENGTH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Too many object properties"
                )
            
            for key, value in data.items():
                # Validate key
                if len(str(key)) > SecurityConfig.MAX_FIELD_LENGTH:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Object key too long"
                    )
                
                if self._contains_suspicious_patterns(str(key)):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid object key content"
                    )
                
                # Recursively validate value
                self._validate_json_structure(value, depth + 1)
        
        elif isinstance(data, list):
            if len(data) > SecurityConfig.MAX_ARRAY_LENGTH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Array too long"
                )
            
            for item in data:
                self._validate_json_structure(item, depth + 1)
        
        elif isinstance(data, str):
            if len(data) > SecurityConfig.MAX_FIELD_LENGTH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="String value too long"
                )
            
            if self._contains_suspicious_patterns(data):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid string content"
                )
    
    def _contains_suspicious_patterns(self, text: str) -> bool:
        """Check if text contains suspicious security patterns"""
        text_lower = text.lower()
        
        for pattern in SecurityConfig.SUSPICIOUS_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        
        return False
    
    async def _validate_response(self, request: Request, response: Response) -> Response:
        """Validate and sanitize response"""
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Add request ID if available
        request_id = getattr(request.state, 'request_id', None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        
        return response


def setup_validation_middleware(app):
    """Set up request validation middleware"""
    app.add_middleware(RequestValidationMiddleware)
    logger.info("Request validation middleware configured successfully")