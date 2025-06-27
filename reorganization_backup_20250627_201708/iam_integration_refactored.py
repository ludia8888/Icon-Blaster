"""
Refactored IAM Integration
Uses the IAM Service Client for MSA communication
No circular dependencies
"""
from typing import Optional, List, Dict, Any
from functools import lru_cache

from shared.iam_contracts import IAMScope
from core.integrations.iam_service_client_with_fallback import (
    get_iam_client_with_fallback
)
from core.auth import UserContext
from models.scope_role_mapping import ScopeRoleMatrix
from models.permissions import Role
from utils.logger import get_logger

logger = get_logger(__name__)


class IAMIntegration:
    """
    Refactored IAM Integration that uses the MSA client
    Provides backwards compatibility while removing circular dependencies
    """
    
    def __init__(self):
        self.client = get_iam_client_with_fallback()
        self._role_cache: Dict[str, List[Role]] = {}
    
    async def validate_jwt_enhanced(self, token: str) -> UserContext:
        """
        Enhanced JWT validation using IAM service
        
        Args:
            token: JWT token to validate
            
        Returns:
            UserContext with user information and roles
            
        Raises:
            ValueError: If token is invalid
        """
        # Validate token with IAM service
        validation_response = await self.client.validate_token(token)
        
        if not validation_response.valid:
            raise ValueError(validation_response.error or "Token validation failed")
        
        # Convert IAM scopes to OMS roles
        oms_roles = self._convert_scopes_to_roles(validation_response.scopes)
        
        # Merge with any explicit roles from IAM
        all_roles = list(set(validation_response.roles + oms_roles))
        
        # Create UserContext
        return UserContext(
            user_id=validation_response.user_id,
            username=validation_response.username,
            email=validation_response.email,
            roles=all_roles,
            tenant_id=validation_response.tenant_id,
            metadata={
                "scopes": validation_response.scopes,
                "expires_at": validation_response.expires_at,
                **validation_response.metadata
            }
        )
    
    def _convert_scopes_to_roles(self, scopes: List[str]) -> List[str]:
        """
        Convert IAM scopes to OMS roles using the mapping matrix
        
        Args:
            scopes: List of IAM scopes
            
        Returns:
            List of OMS role names
        """
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        return [role.value for role in roles]
    
    def check_scope(self, user_context: UserContext, required_scope: str) -> bool:
        """
        Check if user has required scope
        
        Args:
            user_context: User context with scopes
            required_scope: Required scope
            
        Returns:
            True if user has the scope
        """
        user_scopes = user_context.metadata.get("scopes", [])
        return required_scope in user_scopes
    
    def check_any_scope(self, user_context: UserContext, required_scopes: List[str]) -> bool:
        """
        Check if user has any of the required scopes
        
        Args:
            user_context: User context with scopes
            required_scopes: List of required scopes
            
        Returns:
            True if user has any of the scopes
        """
        user_scopes = set(user_context.metadata.get("scopes", []))
        return bool(user_scopes.intersection(required_scopes))
    
    def check_all_scopes(self, user_context: UserContext, required_scopes: List[str]) -> bool:
        """
        Check if user has all required scopes
        
        Args:
            user_context: User context with scopes
            required_scopes: List of required scopes
            
        Returns:
            True if user has all scopes
        """
        user_scopes = set(user_context.metadata.get("scopes", []))
        return all(scope in user_scopes for scope in required_scopes)
    
    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """
        Get detailed user information from IAM service
        
        Args:
            token: User's access token
            
        Returns:
            User information dictionary
        """
        # First validate the token to get user_id
        validation_response = await self.client.validate_token(token)
        if not validation_response.valid:
            return {}
        
        # Get detailed user info
        user_info = await self.client.get_user_info(
            user_id=validation_response.user_id,
            include_permissions=True
        )
        
        if user_info:
            return user_info.dict()
        
        return {}
    
    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            New token response
        """
        return await self.client.refresh_token(refresh_token)
    
    @lru_cache(maxsize=1000)
    def get_required_scopes(self, resource_type: str, action: str) -> List[str]:
        """
        Get required scopes for a resource/action combination
        
        Args:
            resource_type: Type of resource
            action: Action to perform
            
        Returns:
            List of required scopes
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
        
        return [scope.value for scope in scope_map.get((resource_type, action), [])]
    
    async def check_health(self) -> Dict[str, Any]:
        """
        Check IAM service health
        
        Returns:
            Health status dictionary
        """
        health_response = await self.client.health_check()
        return health_response.dict()


# Global IAM integration instance
_iam_integration: Optional[IAMIntegration] = None


def get_iam_integration() -> IAMIntegration:
    """Get global IAM integration instance"""
    global _iam_integration
    if _iam_integration is None:
        _iam_integration = IAMIntegration()
    return _iam_integration