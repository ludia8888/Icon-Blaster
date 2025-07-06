"""
IAM Service Integration
Enhanced JWT validation and Scope-based authorization for IAM MSA integration
"""
import os
import json
import httpx
import asyncio
import redis.asyncio as redis
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timezone
from functools import lru_cache
import jwt
from jwt import PyJWKClient

from core.auth_utils import UserContext
from common_logging.setup import get_logger
from database.clients.unified_http_client import create_iam_client

logger = get_logger(__name__)


# Import IAMScope from shared contracts to avoid duplication
from shared.iam_contracts import IAMScope

# Export for backward compatibility
__all__ = ['IAMIntegration', 'IAMScope', 'get_iam_integration', 'IAMServiceUnavailableError']


class IAMServiceUnavailableError(Exception):
    """Raised when IAM service is unavailable"""
    pass


class IAMIntegration:
    """
    IAM Service integration for enhanced authentication and authorization
    Supports JWKS, scope-based permissions, and role synchronization
    """
    
    def __init__(self):
        self.iam_base_url = os.getenv("IAM_SERVICE_URL", "https://iam-service:8443")
        self.jwks_url = f"{self.iam_base_url}/.well-known/jwks.json"
        self.expected_issuer = os.getenv("JWT_ISSUER", "iam.company")
        self.expected_audience = os.getenv("JWT_AUDIENCE", "oms")
        
        # Initialize HTTP client for IAM communication
        verify_ssl = not os.getenv("IAM_VERIFY_SSL", "true").lower() == "false"
        self._http_client = create_iam_client(
            base_url=self.iam_base_url,
            verify_ssl=verify_ssl,
            enable_fallback=True
        )
        
        # Initialize Redis client for permission caching
        self._redis_client = None
        self._init_redis_client()
        
        # Initialize JWKS client for key rotation support
        self.jwks_client = None
        if not os.getenv("JWT_LOCAL_VALIDATION", "true").lower() == "true":
            try:
                self.jwks_client = PyJWKClient(self.jwks_url)
            except Exception as e:
                logger.warning(f"Failed to initialize JWKS client: {e}")
        
        # Cache for role mappings
        self._role_scope_cache: Dict[str, Set[str]] = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_timestamp = 0
        
        # Permission cache TTL (configurable via env)
        self._permission_cache_ttl = int(os.getenv("IAM_PERMISSION_CACHE_TTL", "300"))  # 5 minutes default
    
    def _init_redis_client(self):
        """Initialize Redis client for permission caching"""
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self._redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            logger.info("Redis client initialized for IAM permission caching")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis client: {e}. Caching disabled.")
            self._redis_client = None
    
    async def _get_cached_permissions(self, user_id: str) -> Optional[List[str]]:
        """Get cached permissions from Redis"""
        if not self._redis_client:
            return None
        
        try:
            cache_key = f"iam:permissions:{user_id}"
            cached_data = await self._redis_client.get(cache_key)
            
            if cached_data:
                permissions = json.loads(cached_data)
                logger.debug(f"Cache hit for user {user_id} permissions")
                return permissions
            
            return None
        except Exception as e:
            logger.warning(f"Redis cache read error: {e}")
            return None
    
    async def _cache_permissions(self, user_id: str, permissions: List[str]):
        """Cache permissions in Redis with TTL"""
        if not self._redis_client:
            return
        
        try:
            cache_key = f"iam:permissions:{user_id}"
            await self._redis_client.setex(
                cache_key,
                self._permission_cache_ttl,
                json.dumps(permissions)
            )
            logger.debug(f"Cached permissions for user {user_id} with TTL {self._permission_cache_ttl}s")
        except Exception as e:
            logger.warning(f"Redis cache write error: {e}")
    
    async def invalidate_user_permissions(self, user_id: str):
        """Invalidate cached permissions for a user"""
        if not self._redis_client:
            return
        
        try:
            cache_key = f"iam:permissions:{user_id}"
            await self._redis_client.delete(cache_key)
            logger.info(f"Invalidated permission cache for user {user_id}")
        except Exception as e:
            logger.warning(f"Redis cache invalidation error: {e}")
    
    async def validate_jwt_enhanced(self, token: str) -> UserContext:
        """
        Enhanced JWT validation with full IAM integration
        
        Validates:
        - Signature using JWKS
        - Issuer (iss)
        - Audience (aud)
        - Expiration (exp)
        - Scopes
        - Key ID (kid)
        """
        try:
            # Get signing key from JWKS
            if self.jwks_client:
                try:
                    signing_key = self.jwks_client.get_signing_key_from_jwt(token)
                    key = signing_key.key
                except Exception as e:
                    logger.error(f"Failed to get signing key from JWKS: {e}")
                    # Fallback to local validation
                    key = os.getenv("JWT_SECRET", "your-secret-key")
            else:
                # Local validation mode
                key = os.getenv("JWT_SECRET", "your-secret-key")
            
            # Decode and validate JWT
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256", "HS256"],  # Support both for flexibility
                audience=self.expected_audience,
                issuer=self.expected_issuer,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True
                }
            )
            
            # Extract user information
            user_id = payload.get("sub")
            if not user_id:
                raise ValueError("Missing 'sub' claim in token")
            
            # Extract scopes and convert to roles
            scopes = payload.get("scope", "").split() if payload.get("scope") else []
            roles = await self._scopes_to_roles(scopes)
            
            # Add any explicit roles from token
            token_roles = payload.get("roles", [])
            if token_roles:
                roles.extend(token_roles)
            
            # Create user context
            user_context = UserContext(
                user_id=user_id,
                username=payload.get("preferred_username", payload.get("username", user_id)),
                email=payload.get("email"),
                roles=list(set(roles)),  # Deduplicate
                tenant_id=payload.get("tenant_id"),
                metadata={
                    "scopes": scopes,
                    "auth_time": payload.get("auth_time"),
                    "azp": payload.get("azp"),  # Authorized party
                    "session_state": payload.get("session_state"),
                    "acr": payload.get("acr"),  # Authentication context class
                    "jti": payload.get("jti"),  # JWT ID for tracking
                }
            )
            
            return user_context
            
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidAudienceError:
            raise ValueError(f"Invalid audience - expected {self.expected_audience}")
        except jwt.InvalidIssuerError:
            raise ValueError(f"Invalid issuer - expected {self.expected_issuer}")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {str(e)}")
        except Exception as e:
            logger.error(f"JWT validation error: {e}")
            raise ValueError(f"Token validation failed: {str(e)}")
    
    async def _scopes_to_roles(self, scopes: List[str]) -> List[str]:
        """
        Convert IAM scopes to OMS roles using the structured mapping
        """
        # Import here to avoid circular dependency
        from models.scope_role_mapping import ScopeRoleMatrix
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        return [role.value for role in roles]
    
    def check_scope(self, user_context: UserContext, required_scope: str) -> bool:
        """
        Check if user has required scope
        Scopes are stored in user context metadata
        """
        user_scopes = user_context.metadata.get("scopes", [])
        return required_scope in user_scopes
    
    def check_any_scope(self, user_context: UserContext, required_scopes: List[str]) -> bool:
        """Check if user has any of the required scopes"""
        user_scopes = set(user_context.metadata.get("scopes", []))
        return bool(user_scopes.intersection(required_scopes))
    
    def check_all_scopes(self, user_context: UserContext, required_scopes: List[str]) -> bool:
        """Check if user has all required scopes"""
        user_scopes = set(user_context.metadata.get("scopes", []))
        return all(scope in user_scopes for scope in required_scopes)
    
    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """
        Get detailed user information from IAM service
        Uses the standard OIDC userinfo endpoint
        """
        try:
            response = await self._http_client.get(
                "/userinfo",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get user info: {response.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return {}
    
    async def get_user_permissions(self, user_id: str, token: str = None) -> List[str]:
        """
        Get user's actual permissions from user-service IAM endpoint
        This is the source of truth for user permissions
        
        Args:
            user_id: User ID to fetch permissions for
            token: Optional bearer token for authorization
            
        Returns:
            List of permission strings (e.g., ['schema:read', 'branch:create'])
            
        Raises:
            IAMServiceUnavailableError: When IAM service is unreachable
        """
        # First, check cache
        cached_permissions = await self._get_cached_permissions(user_id)
        if cached_permissions is not None:
            return cached_permissions
        
        # Cache miss - fetch from IAM service
        try:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            
            # Call user-service IAM endpoint
            response = await self._http_client.get(
                f"/iam/users/{user_id}/permissions",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                permissions = data.get("permissions", [])
                
                # Convert IAM scopes to OMS-style permissions using scope mapper
                from core.iam.scope_mapper import get_scope_mapper
                scope_mapper = get_scope_mapper()
                normalized_permissions = scope_mapper.transform_scopes(permissions)
                
                # Cache the permissions
                await self._cache_permissions(user_id, normalized_permissions)
                
                logger.info(f"Fetched {len(normalized_permissions)} permissions for user {user_id}")
                return normalized_permissions
            elif response.status_code in [502, 503, 504]:
                # Service unavailable - raise specific exception
                logger.error(f"IAM service unavailable: {response.status_code}")
                raise IAMServiceUnavailableError(
                    f"IAM service temporarily unavailable (HTTP {response.status_code})"
                )
            else:
                logger.error(f"Failed to get user permissions: {response.status_code}")
                # For non-5xx errors, assume user has no permissions (secure default)
                return []
                
        except httpx.RequestError as e:
            # Network errors - service is unreachable
            logger.error(f"Cannot reach IAM service for user {user_id}: {e}")
            raise IAMServiceUnavailableError(
                "IAM service is unreachable. Please try again later."
            )
        except IAMServiceUnavailableError:
            # Re-raise our specific exception
            raise
        except Exception as e:
            # Other unexpected errors - log but don't expose details
            logger.error(f"Unexpected error getting user permissions for {user_id}: {e}")
            raise IAMServiceUnavailableError(
                "Unable to verify permissions at this time"
            )
    
    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token
        Returns new access token and optionally new refresh token
        """
        try:
            response = await self._http_client.post(
                "/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": os.getenv("OAUTH_CLIENT_ID", "oms-service")
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise ValueError(f"Token refresh failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            raise
    
    @lru_cache(maxsize=1000)
    def get_required_scopes(self, resource_type: str, action: str) -> List[str]:
        """
        Get required scopes for a resource/action combination
        Cached for performance
        """
        # Define scope requirements
        scope_map = {
            # Schema operations
            ("schema", "read"): [IAMScope.SCHEMAS_READ],
            ("schema", "create"): [IAMScope.SCHEMAS_WRITE],
            ("schema", "update"): [IAMScope.SCHEMAS_WRITE],
            ("schema", "delete"): [IAMScope.SCHEMAS_WRITE, IAMScope.ONTOLOGIES_ADMIN],
            
            # Object/Link/Action/Function types
            ("object_type", "read"): [IAMScope.ONTOLOGIES_READ],
            ("object_type", "create"): [IAMScope.ONTOLOGIES_WRITE],
            ("object_type", "update"): [IAMScope.ONTOLOGIES_WRITE],
            ("object_type", "delete"): [IAMScope.ONTOLOGIES_WRITE],
            
            ("link_type", "read"): [IAMScope.ONTOLOGIES_READ],
            ("link_type", "create"): [IAMScope.ONTOLOGIES_WRITE],
            ("link_type", "update"): [IAMScope.ONTOLOGIES_WRITE],
            ("link_type", "delete"): [IAMScope.ONTOLOGIES_WRITE],
            
            # Branch operations
            ("branch", "read"): [IAMScope.BRANCHES_READ],
            ("branch", "create"): [IAMScope.BRANCHES_WRITE],
            ("branch", "update"): [IAMScope.BRANCHES_WRITE],
            ("branch", "delete"): [IAMScope.BRANCHES_WRITE],
            ("branch", "merge"): [IAMScope.BRANCHES_WRITE],
            
            # Proposal operations
            ("proposal", "read"): [IAMScope.PROPOSALS_READ],
            ("proposal", "create"): [IAMScope.PROPOSALS_WRITE],
            ("proposal", "update"): [IAMScope.PROPOSALS_WRITE],
            ("proposal", "approve"): [IAMScope.PROPOSALS_APPROVE],
            ("proposal", "reject"): [IAMScope.PROPOSALS_APPROVE],
            
            # Audit operations
            ("audit", "read"): [IAMScope.AUDIT_READ],
            ("audit", "create"): [IAMScope.SYSTEM_ADMIN],  # Only system can create audit logs
            
            # Webhook operations
            ("webhook", "execute"): [IAMScope.WEBHOOK_EXECUTE],
        }
        
        return scope_map.get((resource_type, action), [])


# Global IAM integration instance
_iam_integration: Optional[IAMIntegration] = None


def get_iam_integration() -> IAMIntegration:
    """Get global IAM integration instance"""
    global _iam_integration
    if _iam_integration is None:
        _iam_integration = IAMIntegration()
    return _iam_integration