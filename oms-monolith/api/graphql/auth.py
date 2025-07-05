"""
GraphQL Authentication Module
Provides authentication for GraphQL endpoints and WebSocket connections

DESIGN INTENT:
This module provides specialized authentication for GraphQL's unique requirements:
1. Optional authentication for public queries
2. WebSocket session management for subscriptions
3. Connection-level authentication state

WHY SEPARATE FROM MAIN AUTH:
GraphQL has specific needs that differ from REST APIs:
- Queries can be partially public (some fields require auth, others don't)
- WebSocket connections need persistent session management
- Subscriptions require connection-level auth state tracking
- Different error handling patterns (return null vs HTTP 401)

ARCHITECTURE:
- Delegates actual token validation to unified_auth module
- Adds GraphQL-specific session management layer
- Provides WebSocket authentication lifecycle

USE THIS FOR:
- All GraphQL query/mutation authentication
- WebSocket connection authentication
- GraphQL subscription authorization

NOT FOR:
- REST API authentication (use middleware/auth_middleware.py)
- Background job authentication
- Service-to-service auth

Related modules:
- core/auth/unified_auth.py: Core authentication logic
- middleware/auth_middleware.py: REST API authentication
- api/gateway/auth.py: DEPRECATED gateway auth
"""
import os
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import asyncio
import redis.asyncio as redis
from fastapi import Depends, HTTPException, status, Request, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.auth_utils import UserContext
from middleware.auth_middleware import get_current_user
from core.integrations.user_service_client import validate_jwt_token
from utils.logger import get_logger

logger = get_logger(__name__)

security = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[UserContext]:
    """
    Get current user for GraphQL queries (optional authentication)
    Returns None if no valid token is provided
    """
    # Check if user is already authenticated by middleware
    if hasattr(request.state, "user") and request.state.user:
        return request.state.user
    
    # If no credentials provided, return None (optional auth)
    if not credentials:
        return None
    
    # Validate token using the existing validate_jwt_token function
    try:
        user_data = await validate_jwt_token(credentials.credentials)
        
        if user_data:
            return UserContext(
                user_id=user_data.get("user_id", user_data.get("sub")),
                username=user_data.get("username", user_data.get("name", "unknown")),
                email=user_data.get("email"),
                roles=user_data.get("roles", []),
                permissions=user_data.get("permissions", []),
                is_authenticated=True,
                metadata=user_data
            )
    except Exception as e:
        logger.debug(f"Optional auth failed: {e}")
    
    return None


class AuthenticationManager:
    """
    Manages authentication state and session tracking
    Used for WebSocket connections and session management
    """
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self._session_ttl = 3600  # 1 hour
    
    async def init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("Redis connection established for AuthenticationManager")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            self.redis_client = None
    
    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
    
    async def validate_token(self, token: str) -> Optional[UserContext]:
        """Validate JWT token and cache result"""
        if not token:
            return None
        
        # Check cache first
        if self.redis_client:
            cached = await self.redis_client.get(f"auth:token:{token}")
            if cached:
                # Parse cached user data
                import json
                user_data = json.loads(cached)
                return UserContext(**user_data)
        
        # Validate token
        try:
            user = await validate_jwt_token(token)
            
            # Cache the result
            if self.redis_client and user:
                import json
                await self.redis_client.setex(
                    f"auth:token:{token}",
                    self._session_ttl,
                    json.dumps(user.dict())
                )
            
            return user
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return None
    
    async def create_session(self, user: UserContext, connection_id: str) -> str:
        """Create WebSocket session"""
        session_id = f"ws:{user.user_id}:{connection_id}"
        
        if self.redis_client:
            session_data = {
                "user_id": user.user_id,
                "username": user.username,
                "connection_id": connection_id,
                "connected_at": datetime.now(timezone.utc).isoformat()
            }
            await self.redis_client.hset(
                f"session:{session_id}",
                mapping=session_data
            )
            await self.redis_client.expire(f"session:{session_id}", self._session_ttl)
        
        return session_id
    
    async def remove_session(self, session_id: str):
        """Remove WebSocket session"""
        if self.redis_client:
            await self.redis_client.delete(f"session:{session_id}")


class GraphQLWebSocketAuth:
    """
    WebSocket authentication for GraphQL subscriptions
    Handles connection lifecycle and authentication
    """
    
    def __init__(self, auth_manager: AuthenticationManager):
        self.auth_manager = auth_manager
        self._connections: Dict[str, UserContext] = {}
    
    async def authenticate_websocket(
        self, 
        websocket: WebSocket,
        token: Optional[str] = None
    ) -> Optional[UserContext]:
        """
        Authenticate WebSocket connection
        
        Args:
            websocket: WebSocket connection
            token: JWT token from connection params or headers
            
        Returns:
            UserContext if authenticated, None otherwise
        """
        if not token:
            # Try to get token from headers
            auth_header = websocket.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        
        if not token:
            logger.warning("WebSocket connection attempted without token")
            return None
        
        # Validate token
        user = await self.auth_manager.validate_token(token)
        if not user:
            logger.warning("WebSocket connection with invalid token")
            return None
        
        # Create session
        connection_id = str(id(websocket))
        session_id = await self.auth_manager.create_session(user, connection_id)
        
        # Store connection
        self._connections[connection_id] = user
        
        logger.info(f"WebSocket authenticated for user {user.username} (session: {session_id})")
        return user
    
    async def disconnect_websocket(self, websocket: WebSocket):
        """Handle WebSocket disconnection"""
        connection_id = str(id(websocket))
        
        if connection_id in self._connections:
            user = self._connections[connection_id]
            session_id = f"ws:{user.user_id}:{connection_id}"
            
            # Remove session
            await self.auth_manager.remove_session(session_id)
            
            # Remove from connections
            del self._connections[connection_id]
            
            logger.info(f"WebSocket disconnected for user {user.username}")
    
    def get_user_for_connection(self, websocket: WebSocket) -> Optional[UserContext]:
        """Get user for active WebSocket connection"""
        connection_id = str(id(websocket))
        return self._connections.get(connection_id)
    
    async def authenticate_graphql_subscription(
        self, 
        websocket: WebSocket
    ) -> Optional[UserContext]:
        """
        Authenticate GraphQL subscription WebSocket
        Alias for authenticate_websocket to match main.py usage
        """
        # Accept the WebSocket first
        await websocket.accept()
        
        # Try to get token from headers
        auth_header = websocket.headers.get("Authorization", "")
        token = None
        
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            
        # If no token, allow anonymous connection
        if not token:
            logger.info("WebSocket connection without token - allowing anonymous")
            return None
            
        # Authenticate with token
        return await self.authenticate_websocket(websocket, token)
    
    async def authorize_subscription(
        self,
        user: UserContext,
        subscription_name: str,
        variables: Dict[str, Any]
    ) -> bool:
        """
        Authorize a specific subscription for a user
        
        Args:
            user: The authenticated user context
            subscription_name: Name of the subscription being requested
            variables: Variables passed to the subscription
            
        Returns:
            True if authorized, False otherwise
        """
        # For now, allow all authenticated users to subscribe
        # In production, implement proper authorization logic
        if not user or not user.is_authenticated:
            return False
            
        # Add subscription-specific authorization here
        # Example: Check if user has permission for specific subscriptions
        
        return True