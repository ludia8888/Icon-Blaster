"""
Audit Event Schemas for Audit Trail Service Integration
Defines CloudEvents for audit logging following Foundry-style architecture
"""
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID

from models.domain import BaseModel as DomainBaseModel


class AuditAction(str, Enum):
    """Audit action types for tracking all system activities"""
    # Schema Operations
    SCHEMA_CREATE = "schema.create"
    SCHEMA_UPDATE = "schema.update"
    SCHEMA_DELETE = "schema.delete"
    SCHEMA_REVERT = "schema.revert"
    
    # Object Type Operations
    OBJECT_TYPE_CREATE = "object_type.create"
    OBJECT_TYPE_UPDATE = "object_type.update"
    OBJECT_TYPE_DELETE = "object_type.delete"
    
    # Link Type Operations
    LINK_TYPE_CREATE = "link_type.create"
    LINK_TYPE_UPDATE = "link_type.update"
    LINK_TYPE_DELETE = "link_type.delete"
    
    # Action Type Operations
    ACTION_TYPE_CREATE = "action_type.create"
    ACTION_TYPE_UPDATE = "action_type.update"
    ACTION_TYPE_DELETE = "action_type.delete"
    
    # Function Type Operations
    FUNCTION_TYPE_CREATE = "function_type.create"
    FUNCTION_TYPE_UPDATE = "function_type.update"
    FUNCTION_TYPE_DELETE = "function_type.delete"
    
    # Branch Operations
    BRANCH_CREATE = "branch.create"
    BRANCH_UPDATE = "branch.update"
    BRANCH_DELETE = "branch.delete"
    BRANCH_MERGE = "branch.merge"
    BRANCH_MERGED = "branch.merged"
    
    # Indexing Operations
    INDEXING_STARTED = "indexing.started"
    INDEXING_COMPLETED = "indexing.completed"
    INDEXING_FAILED = "indexing.failed"
    
    # Proposal Operations
    PROPOSAL_CREATE = "proposal.create"
    PROPOSAL_UPDATE = "proposal.update"
    PROPOSAL_APPROVE = "proposal.approve"
    PROPOSAL_REJECT = "proposal.reject"
    PROPOSAL_MERGE = "proposal.merge"
    
    # Access Control Operations
    ACL_CREATE = "acl.create"
    ACL_UPDATE = "acl.update"
    ACL_DELETE = "acl.delete"
    
    # Authentication Events
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_REFRESH = "auth.token_refresh"
    AUTH_FAILED = "auth.failed"
    
    # System Operations
    SYSTEM_EXPORT = "system.export"
    SYSTEM_IMPORT = "system.import"
    SYSTEM_BACKUP = "system.backup"
    SYSTEM_RESTORE = "system.restore"


class ResourceType(str, Enum):
    """Resource types that can be audited"""
    SCHEMA = "schema"
    OBJECT_TYPE = "object_type"
    LINK_TYPE = "link_type"
    ACTION_TYPE = "action_type"
    FUNCTION_TYPE = "function_type"
    BRANCH = "branch"
    PROPOSAL = "proposal"
    ACL = "acl"
    USER = "user"
    SYSTEM = "system"


class ActorInfo(BaseModel):
    """Information about the actor performing the action"""
    id: str = Field(..., description="User ID from JWT 'sub' claim")
    username: str = Field(..., description="Username for display")
    email: Optional[str] = None
    roles: List[str] = Field(default_factory=list, description="User roles at time of action")
    tenant_id: Optional[str] = Field(None, description="Tenant ID for multi-tenant support")
    service_account: bool = Field(False, description="Whether this is a service account")
    
    # Authentication context
    auth_method: Optional[str] = Field(None, description="Authentication method (jwt, api_key, mtls)")
    session_id: Optional[str] = Field(None, description="Session ID for tracking")
    ip_address: Optional[str] = Field(None, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="Client user agent")


class TargetInfo(BaseModel):
    """Information about the target resource being acted upon"""
    resource_type: ResourceType
    resource_id: str
    resource_name: Optional[str] = None
    branch: Optional[str] = Field(None, description="Branch where action occurred")
    parent_id: Optional[str] = Field(None, description="Parent resource ID if hierarchical")
    
    # Additional context
    tags: Dict[str, str] = Field(default_factory=dict, description="Resource tags/labels")
    owner: Optional[str] = Field(None, description="Resource owner")
    workspace: Optional[str] = Field(None, description="Workspace/project context")


class ChangeDetails(BaseModel):
    """Details about what changed in the resource"""
    commit_hash: Optional[str] = Field(None, description="Git-like commit hash")
    version_before: Optional[str] = Field(None, description="Version hash before change")
    version_after: Optional[str] = Field(None, description="Version hash after change")
    
    # Change diff (with PII masking support)
    fields_changed: List[str] = Field(default_factory=list, description="List of changed field names")
    old_values: Optional[Dict[str, Any]] = Field(None, description="Previous values (PII masked)")
    new_values: Optional[Dict[str, Any]] = Field(None, description="New values (PII masked)")
    
    # Change metadata
    change_size: Optional[int] = Field(None, description="Size of change in bytes")
    affected_items: Optional[int] = Field(None, description="Number of affected items")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ComplianceInfo(BaseModel):
    """Compliance and regulatory information"""
    data_classification: Optional[str] = Field(None, description="Data classification level")
    retention_period: Optional[int] = Field(None, description="Retention period in days")
    gdpr_relevant: bool = Field(False, description="Whether action involves GDPR data")
    pii_fields: List[str] = Field(default_factory=list, description="Fields containing PII")
    regulatory_tags: List[str] = Field(default_factory=list, description="Regulatory compliance tags")


class AuditEventV1(BaseModel):
    """
    Audit Event Schema v1 for Audit Trail Service
    Follows CloudEvents 1.0 specification with OMS extensions
    """
    # CloudEvents standard fields (will be set by event publisher)
    id: Optional[str] = Field(None, description="Unique event ID")
    source: str = Field("/oms", description="Event source")
    specversion: str = Field("1.0", description="CloudEvents version")
    type: str = Field("audit.activity.v1", description="Event type")
    time: Optional[datetime] = Field(None, description="Event timestamp")
    
    # Core audit fields
    action: AuditAction = Field(..., description="Action performed")
    actor: ActorInfo = Field(..., description="Who performed the action")
    target: TargetInfo = Field(..., description="What was acted upon")
    
    # Action details
    success: bool = Field(True, description="Whether action succeeded")
    error_code: Optional[str] = Field(None, description="Error code if failed")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    duration_ms: Optional[int] = Field(None, description="Action duration in milliseconds")
    
    # Change information
    changes: Optional[ChangeDetails] = Field(None, description="Details of changes made")
    
    # Compliance and security
    compliance: Optional[ComplianceInfo] = Field(None, description="Compliance metadata")
    
    # Request context
    request_id: Optional[str] = Field(None, description="Request ID for correlation")
    correlation_id: Optional[str] = Field(None, description="Correlation ID across services")
    causation_id: Optional[str] = Field(None, description="ID of event that caused this")
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    tags: Dict[str, str] = Field(default_factory=dict, description="Event tags for filtering")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def to_cloudevent(self) -> Dict[str, Any]:
        """Convert to CloudEvents format for publishing"""
        # Generate structured audit ID if not provided
        audit_id = self.id
        if not audit_id:
            # Import here to avoid circular dependency
            from utils.audit_id_generator import AuditIDGenerator
            audit_id = AuditIDGenerator.generate(
                action=self.action,
                resource_type=self.target.resource_type,
                resource_id=self.target.resource_id,
                timestamp=self.time
            )
        
        return {
            "specversion": self.specversion,
            "type": self.type,
            "source": self.source,
            "id": audit_id,
            "time": (self.time or datetime.utcnow()).isoformat(),
            "datacontenttype": "application/json",
            "data": {
                "action": self.action.value,
                "actor": self.actor.dict(),
                "target": self.target.dict(),
                "success": self.success,
                "error_code": self.error_code,
                "error_message": self.error_message,
                "duration_ms": self.duration_ms,
                "changes": self.changes.dict() if self.changes else None,
                "compliance": self.compliance.dict() if self.compliance else None,
                "request_id": self.request_id,
                "metadata": self.metadata,
                "tags": self.tags
            },
            # OMS extensions
            "correlationid": self.correlation_id,
            "causationid": self.causation_id
        }


class AuditEventFilter(BaseModel):
    """Filter criteria for querying audit events"""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    actor_ids: Optional[List[str]] = None
    actions: Optional[List[AuditAction]] = None
    resource_types: Optional[List[ResourceType]] = None
    resource_ids: Optional[List[str]] = None
    branches: Optional[List[str]] = None
    success: Optional[bool] = None
    tags: Optional[Dict[str, str]] = None
    
    # Pagination
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)


# Helper functions for creating audit events

def create_audit_event(
    action: AuditAction,
    actor: ActorInfo,
    target: TargetInfo,
    changes: Optional[ChangeDetails] = None,
    success: bool = True,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> AuditEventV1:
    """Helper to create an audit event with common defaults"""
    return AuditEventV1(
        action=action,
        actor=actor,
        target=target,
        changes=changes,
        success=success,
        error_code=error_code,
        error_message=error_message,
        request_id=request_id,
        metadata=metadata or {}
    )


def mask_pii_fields(data: Dict[str, Any], pii_fields: List[str]) -> Dict[str, Any]:
    """Mask PII fields in data for GDPR compliance"""
    masked_data = data.copy()
    for field in pii_fields:
        if field in masked_data:
            masked_data[field] = "***MASKED***"
    return masked_data