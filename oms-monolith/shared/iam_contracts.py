"""
Shared IAM Contracts and DTOs
This module defines the interface between OMS and IAM service
No circular dependencies - only data structures
"""
from typing import List, Dict, Optional, Set, Any
from enum import Enum
from dataclasses import dataclass
from pydantic import BaseModel, Field


class IAMScope(str, Enum):
    """
    Standard IAM scopes for OMS
    These are defined by the IAM service and consumed by OMS
    """
    # Read scopes
    ONTOLOGIES_READ = "api:ontologies:read"
    SCHEMAS_READ = "api:schemas:read"
    BRANCHES_READ = "api:branches:read"
    PROPOSALS_READ = "api:proposals:read"
    AUDIT_READ = "api:audit:read"
    
    # Write scopes
    ONTOLOGIES_WRITE = "api:ontologies:write"
    SCHEMAS_WRITE = "api:schemas:write"
    BRANCHES_WRITE = "api:branches:write"
    PROPOSALS_WRITE = "api:proposals:write"
    
    # Admin scopes
    ONTOLOGIES_ADMIN = "api:ontologies:admin"
    PROPOSALS_APPROVE = "api:proposals:approve"
    SYSTEM_ADMIN = "api:system:admin"
    
    # Service scopes
    SERVICE_ACCOUNT = "api:service:account"
    WEBHOOK_EXECUTE = "api:webhook:execute"


class TokenValidationRequest(BaseModel):
    """Request to validate a JWT token"""
    token: str = Field(..., description="JWT token to validate")
    validate_scopes: bool = Field(True, description="Whether to validate scopes")
    required_scopes: Optional[List[str]] = Field(None, description="Required scopes for access")


class TokenValidationResponse(BaseModel):
    """Response from token validation"""
    valid: bool = Field(..., description="Whether token is valid")
    user_id: Optional[str] = Field(None, description="User ID from token")
    username: Optional[str] = Field(None, description="Username")
    email: Optional[str] = Field(None, description="Email address")
    scopes: List[str] = Field(default_factory=list, description="User's scopes")
    roles: List[str] = Field(default_factory=list, description="User's roles")
    tenant_id: Optional[str] = Field(None, description="Tenant ID")
    expires_at: Optional[str] = Field(None, description="Token expiration time")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    error: Optional[str] = Field(None, description="Error message if validation failed")


class UserInfoRequest(BaseModel):
    """Request for user information"""
    user_id: Optional[str] = Field(None, description="User ID to lookup")
    username: Optional[str] = Field(None, description="Username to lookup")
    email: Optional[str] = Field(None, description="Email to lookup")
    include_permissions: bool = Field(False, description="Include detailed permissions")


class UserInfoResponse(BaseModel):
    """User information from IAM"""
    user_id: str
    username: str
    email: str
    full_name: Optional[str] = None
    tenant_id: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    scopes: List[str] = Field(default_factory=list)
    teams: List[str] = Field(default_factory=list)
    permissions: Optional[Dict[str, List[str]]] = None
    mfa_enabled: bool = False
    active: bool = True
    created_at: str
    updated_at: str


class ServiceAuthRequest(BaseModel):
    """Service-to-service authentication request"""
    service_id: str = Field(..., description="Service identifier")
    service_secret: str = Field(..., description="Service secret or API key")
    requested_scopes: List[str] = Field(default_factory=list, description="Scopes needed")


class ServiceAuthResponse(BaseModel):
    """Service authentication response"""
    access_token: str = Field(..., description="Service access token")
    token_type: str = Field("Bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    scopes: List[str] = Field(default_factory=list, description="Granted scopes")


class ScopeCheckRequest(BaseModel):
    """Request to check if user has specific scopes"""
    user_id: str = Field(..., description="User ID to check")
    required_scopes: List[str] = Field(..., description="Scopes to check")
    check_mode: str = Field("any", description="Check mode: 'any' or 'all'")


class ScopeCheckResponse(BaseModel):
    """Response from scope check"""
    authorized: bool = Field(..., description="Whether user has required scopes")
    user_scopes: List[str] = Field(default_factory=list, description="User's actual scopes")
    missing_scopes: List[str] = Field(default_factory=list, description="Missing scopes")


@dataclass
class IAMConfig:
    """Configuration for IAM integration"""
    iam_service_url: str = "http://user-service:8000"
    jwks_url: Optional[str] = None
    expected_issuer: str = "iam.company"
    expected_audience: str = "oms"
    service_id: str = "oms-service"
    service_secret: Optional[str] = None
    timeout: int = 10
    retry_count: int = 3
    cache_ttl: int = 300
    enable_jwks: bool = True
    verify_ssl: bool = True


# Health check models
class IAMHealthResponse(BaseModel):
    """IAM service health status"""
    status: str = Field(..., description="Health status: healthy, degraded, unhealthy")
    version: str = Field(..., description="IAM service version")
    timestamp: str = Field(..., description="Check timestamp")
    components: Dict[str, Dict[str, any]] = Field(default_factory=dict)
    
    
# Scope hierarchy for reference (no imports needed)
SCOPE_HIERARCHY = {
    "api:system:admin": [
        "api:ontologies:admin",
        "api:proposals:approve",
        "api:audit:read"
    ],
    "api:ontologies:admin": [
        "api:ontologies:write",
        "api:ontologies:read"
    ],
    "api:ontologies:write": [
        "api:ontologies:read"
    ],
    "api:schemas:write": [
        "api:schemas:read"
    ],
    "api:branches:write": [
        "api:branches:read"
    ],
    "api:proposals:write": [
        "api:proposals:read"
    ],
    "api:proposals:approve": [
        "api:proposals:read"
    ]
}