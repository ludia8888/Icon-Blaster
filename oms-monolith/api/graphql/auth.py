"""
GraphQL Authentication Module
Provides authentication for GraphQL endpoints and WebSocket connections
"""
import os
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import asyncio
import redis.asyncio as redis
from fastapi import Depends, HTTPException, status, Request, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.auth import UserContext
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
    if not credentials:
        return None
    
    try:
        # Try to get user from request state (set by middleware)
        if hasattr(request.state, "user"):
            return request.state.user
        
        # Fallback to direct validation
        token = credentials.credentials
        user = await validate_jwt_token(token)
        return user
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