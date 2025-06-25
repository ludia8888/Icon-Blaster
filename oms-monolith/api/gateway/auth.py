"""
Enhanced Authentication and Authorization Module
JWT 기반 인증 및 RBAC 권한 관리 시스템
"""
import os
from typing import Any, Dict, List, Optional, Set

import httpx
from fastapi import WebSocket
import jwt
import redis.asyncio as redis
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
JWT_ALGORITHM = "HS256"

# Service URLs
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8007")

# Redis for session management
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

class UserContext(BaseModel):
    """User context for authenticated requests"""
    id: int
    username: str
    email: str
    full_name: str
    roles: List[str]
    permissions: Set[str]
    is_active: bool

class PermissionManager:
    """Role-based permission management"""

    # Define role-based permissions
    ROLE_PERMISSIONS = {
        "admin": {
            # Schema permissions
            "schema:read", "schema:write", "schema:delete", "schema:admin",
            # Branch permissions
            "branch:read", "branch:write", "branch:delete", "branch:merge", "branch:admin",
            # Action permissions
            "action:read", "action:write", "action:execute", "action:admin",
            # User permissions
            "user:read", "user:write", "user:admin",
            # System permissions
            "system:admin", "system:monitor"
        },
        "schema_admin": {
            "schema:read", "schema:write", "schema:delete",
            "branch:read", "branch:write", "branch:merge",
            "action:read", "action:write", "action:execute"
        },
        "developer": {
            "schema:read", "schema:write",
            "branch:read", "branch:write", "branch:merge",
            "action:read", "action:write", "action:execute"
        },
        "analyst": {
            "schema:read",
            "branch:read",
            "action:read", "action:execute"
        },
        "user": {
            "schema:read",
            "branch:read",
            "action:read"
        },
        "guest": {
            "schema:read"
        }
    }

    @classmethod
    def get_permissions_for_roles(cls, roles: List[str]) -> Set[str]:
        """Get all permissions for given roles"""
        permissions = set()
        for role in roles:
            if role in cls.ROLE_PERMISSIONS:
                permissions.update(cls.ROLE_PERMISSIONS[role])
        return permissions

    @classmethod
    def has_permission(cls, user_roles: List[str], required_permission: str) -> bool:
        """Check if user has required permission"""
        user_permissions = cls.get_permissions_for_roles(user_roles)
        return required_permission in user_permissions

class BranchPermissionManager:
    """Branch-level permission management"""

    # Branch protection rules
    PROTECTED_BRANCHES = {"main", "master", "production", "release"}

    @classmethod
    async def check_branch_permission(
        cls,
        user: UserContext,
        branch_name: str,
        action: str,
        redis_client: redis.Redis
    ) -> bool:
        """Check if user has permission to perform action on branch"""

        # Admin can do anything
        if "admin" in user.roles:
            return True

        # Check if branch is protected
        is_protected = branch_name.lower() in cls.PROTECTED_BRANCHES

        # Define required permissions for actions
        action_permissions = {
            "read": "branch:read",
            "write": "branch:write",
            "merge": "branch:merge",
            "delete": "branch:delete"
        }

        required_permission = action_permissions.get(action, "branch:read")

        # Check basic permission
        if not PermissionManager.has_permission(user.roles, required_permission):
            return False

        # Additional checks for protected branches
        if is_protected and action in ["write", "merge", "delete"]:
            # Only schema_admin or admin can modify protected branches
            if not any(role in ["admin", "schema_admin"] for role in user.roles):
                return False

            # Check for branch-specific permissions in cache
            cache_key = f"branch_permission:{user.id}:{branch_name}:{action}"
            cached_permission = await redis_client.get(cache_key)

            if cached_permission is not None:
                return cached_permission.decode() == "true"

            # For merge operations on protected branches, require approval
            if action == "merge":
                # TODO: Implement merge approval workflow
                # For now, allow schema_admin and admin
                has_permission = any(role in ["admin", "schema_admin"] for role in user.roles)
            else:
                has_permission = True

            # Cache the result for 5 minutes
            await redis_client.setex(cache_key, 300, "true" if has_permission else "false")
            return has_permission

        return True

class AuthenticationManager:
    """Enhanced authentication manager"""

    def __init__(self):
        self.redis_client = None
        self.http_client = httpx.AsyncClient(timeout=10.0)

    async def init_redis(self):
        """Initialize Redis connection"""
        if not self.redis_client:
            self.redis_client = redis.from_url(REDIS_URL)

    async def close(self):
        """Close connections"""
        if self.redis_client:
            await self.redis_client.close()
        await self.http_client.aclose()

    async def verify_token(self, token: str) -> Optional[UserContext]:
        """Verify JWT token and return user context"""
        try:
            # Decode JWT
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

            if payload.get("type") != "access":
                return None

            user_id = payload.get("sub")
            if not user_id:
                return None

            # Check token blacklist
            await self.init_redis()
            blacklisted = await self.redis_client.get(f"blacklist:{token}")
            if blacklisted:
                return None

            # Get user info from cache first
            cache_key = f"user:{user_id}"
            cached_user = await self.redis_client.get(cache_key)

            if cached_user:
                import json
                user_data = json.loads(cached_user.decode())
            else:
                # Fetch from user service using mTLS
                from database.clients import create_user_client

                user_client = create_user_client("api-gateway")
                user_data = await user_client.validate_user(user_id)

                if not user_data:
                    return None

                # Cache for 5 minutes
                import json
                await self.redis_client.setex(
                    cache_key, 300, json.dumps(user_data)
                )

            if not user_data.get("is_active", False):
                return None

            # Get permissions for roles
            permissions = PermissionManager.get_permissions_for_roles(
                user_data.get("roles", [])
            )

            return UserContext(
                id=user_data["id"],
                username=user_data["username"],
                email=user_data["email"],
                full_name=user_data["full_name"],
                roles=user_data.get("roles", []),
                permissions=permissions,
                is_active=user_data["is_active"]
            )

        except jwt.ExpiredSignatureError:
            return None
        except jwt.JWTError:
            return None
        except Exception:
            return None

    async def blacklist_token(self, token: str, ttl: int = 3600):
        """Add token to blacklist"""
        await self.init_redis()
        await self.redis_client.setex(f"blacklist:{token}", ttl, "1")

    async def get_user_from_request(self, request: Request) -> Optional[UserContext]:
        """Extract and validate user from request"""
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ")[1]
        return await self.verify_token(token)

# Global auth manager instance
auth_manager = AuthenticationManager()

# FastAPI security scheme
security = HTTPBearer()

# Alias for compatibility with GraphQL modules
User = UserContext

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = None,
    request: Request = None
) -> UserContext:
    """Get current authenticated user"""

    if credentials:
        token = credentials.credentials
    elif request:
        user = await auth_manager.get_user_from_request(request)
        if user:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    user = await auth_manager.verify_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return user

async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = None,
    request: Request = None
) -> Optional[UserContext]:
    """Get current authenticated user, return None if not authenticated"""
    try:
        return await get_current_user(credentials, request)
    except HTTPException:
        return None

async def require_permission(permission: str):
    """Dependency factory for permission requirements"""
    async def permission_checker(user: UserContext = None, request: Request = None):
        if not user:
            user = await get_current_user(request=request)

        if not PermissionManager.has_permission(user.roles, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission}"
            )

        return user

    return permission_checker

async def require_branch_permission(branch: str, action: str):
    """Dependency factory for branch-specific permissions"""
    async def branch_permission_checker(user: UserContext = None, request: Request = None):
        if not user:
            user = await get_current_user(request=request)

        await auth_manager.init_redis()

        has_permission = await BranchPermissionManager.check_branch_permission(
            user, branch, action, auth_manager.redis_client
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions for {action} on branch {branch}"
            )

        return user

    return branch_permission_checker

def require_roles(*required_roles: str):
    """Dependency factory for role requirements"""
    async def role_checker(user: UserContext = None, request: Request = None):
        if not user:
            user = await get_current_user(request=request)

        if not any(role in user.roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient roles. Required: {', '.join(required_roles)}"
            )

        return user

    return role_checker

# Utility functions for backward compatibility
async def get_user_context(request: Request) -> Dict[str, Any]:
    """Get user context from request (backward compatible)"""
    try:
        user = await auth_manager.get_user_from_request(request)
        if user:
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "roles": user.roles,
                "permissions": list(user.permissions),
                "is_active": user.is_active
            }
    except Exception:
        pass

    # Return system user for backward compatibility
    return {"id": "system", "username": "system", "roles": ["admin"]}

async def extract_user_from_request(request: Request) -> Dict[str, Any]:
    """Extract user context from request"""
    return await get_user_context(request)

# Permission decorators for easy use
def permission_required(permission: str):
    """Decorator for permission requirements"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # This would need to be integrated with FastAPI dependency injection
            # For now, it's a placeholder
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def role_required(*roles: str):
    """Decorator for role requirements"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # This would need to be integrated with FastAPI dependency injection
            # For now, it's a placeholder
            return await func(*args, **kwargs)
        return wrapper
    return decorator

class GraphQLWebSocketAuth:
    """GraphQL WebSocket Authentication Handler"""
    
    def __init__(self, auth_manager: 'AuthenticationManager'):
        self.auth_manager = auth_manager
    
    async def authenticate_graphql_subscription(self, websocket: WebSocket) -> Optional[UserContext]:
        """Authenticate WebSocket connection for GraphQL subscriptions"""
        try:
            # Extract token from WebSocket headers or query params
            auth_header = websocket.headers.get("authorization")
            if not auth_header:
                # Try query parameter
                token = websocket.query_params.get("token")
                if not token:
                    await websocket.close(code=1008, reason="Authentication required")
                    return None
            else:
                token = auth_header.replace("Bearer ", "")
            
            # Verify token
            user = await self.auth_manager.verify_token(token)
            if user:
                await websocket.accept()
                return user
            else:
                await websocket.close(code=1008, reason="Invalid token")
                return None
                
        except Exception as e:
            await websocket.close(code=1011, reason=f"Authentication error: {str(e)}")
            return None
    
    async def authorize_subscription(self, user: UserContext, subscription_name: str, variables: Dict[str, Any]) -> bool:
        """Check if user is authorized for specific subscription"""
        # Basic authorization - can be extended based on subscription type
        if not user.is_active:
            return False
            
        # Define subscription permissions
        subscription_permissions = {
            "schemaChanges": "schema:read",
            "branchUpdates": "branch:read", 
            "actionProgress": "action:read",
            "proposalUpdates": "branch:read"
        }
        
        required_permission = subscription_permissions.get(subscription_name, "read")
        return PermissionManager.has_permission(user.roles, required_permission)

# Cleanup function
async def cleanup_auth():
    """Cleanup authentication resources"""
    await auth_manager.close()
