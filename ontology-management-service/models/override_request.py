"""
Emergency Override Request Model
Implements approval workflow for emergency overrides
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field
from uuid import uuid4


class OverrideStatus(str, Enum):
    """Override request status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    USED = "used"


class OverrideRequest(BaseModel):
    """Emergency override request requiring approval"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    requester_id: str
    requester_name: str
    requester_roles: List[str]
    
    # Request details
    resource: str  # e.g., "schemas/main/object-types"
    action: str    # e.g., "create", "update", "delete"
    change_type: str  # e.g., "schema", "deletion", "acl"
    branch_name: str
    justification: str
    
    # Approval details
    status: OverrideStatus = OverrideStatus.PENDING
    approved_by: Optional[str] = None
    approved_by_name: Optional[str] = None
    approval_notes: Optional[str] = None
    rejected_by: Optional[str] = None
    rejected_reason: Optional[str] = None
    
    # Timestamps
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=24)
    )
    used_at: Optional[datetime] = None
    
    # Token for approved override
    override_token: Optional[str] = None
    
    def is_expired(self) -> bool:
        """Check if request has expired"""
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_valid_for_use(self) -> bool:
        """Check if override can be used"""
        return (
            self.status == OverrideStatus.APPROVED
            and not self.is_expired()
            and self.used_at is None
        )
    
    def mark_as_used(self):
        """Mark override as used"""
        self.status = OverrideStatus.USED
        self.used_at = datetime.now(timezone.utc)


class OverrideApprovalService:
    """Service for managing override approvals"""
    
    def __init__(self, db_service):
        self.db = db_service
        self.required_approvers = ["admin", "lead_developer", "security_admin"]
        self.notification_service = None  # Initialize with actual service
    
    async def request_override(
        self,
        user_context,
        resource: str,
        action: str,
        change_type: str,
        branch_name: str,
        justification: str
    ) -> OverrideRequest:
        """Create a new override request"""
        
        # Validate justification
        if len(justification) < 50:
            raise ValueError(
                "Override justification must be at least 50 characters "
                "and clearly explain the emergency"
            )
        
        # Create request
        request = OverrideRequest(
            requester_id=user_context.user_id,
            requester_name=user_context.username,
            requester_roles=user_context.roles,
            resource=resource,
            action=action,
            change_type=change_type,
            branch_name=branch_name,
            justification=justification
        )
        
        # Store in database
        await self.db.store_override_request(request)
        
        # Notify approvers
        await self._notify_approvers(request)
        
        return request
    
    async def approve_override(
        self,
        request_id: str,
        approver_context,
        approval_notes: Optional[str] = None
    ) -> str:
        """Approve an override request"""
        
        # Check approver permissions
        if not any(role in approver_context.roles for role in self.required_approvers):
            raise PermissionError(
                f"User {approver_context.username} is not authorized to approve overrides. "
                f"Required roles: {', '.join(self.required_approvers)}"
            )
        
        # Get request
        request = await self.db.get_override_request(request_id)
        if not request:
            raise ValueError(f"Override request {request_id} not found")
        
        # Check status
        if request.status != OverrideStatus.PENDING:
            raise ValueError(
                f"Override request is {request.status}, cannot approve"
            )
        
        # Check expiration
        if request.is_expired():
            request.status = OverrideStatus.EXPIRED
            await self.db.update_override_request(request)
            raise ValueError("Override request has expired")
        
        # Approve
        request.status = OverrideStatus.APPROVED
        request.approved_by = approver_context.user_id
        request.approved_by_name = approver_context.username
        request.approval_notes = approval_notes
        request.approved_at = datetime.now(timezone.utc)
        
        # Generate time-limited token
        import secrets
        request.override_token = secrets.token_urlsafe(32)
        
        # Update in database
        await self.db.update_override_request(request)
        
        # Notify requester
        await self._notify_requester_approved(request)
        
        return request.override_token
    
    async def reject_override(
        self,
        request_id: str,
        rejector_context,
        reason: str
    ):
        """Reject an override request"""
        
        # Check permissions
        if not any(role in rejector_context.roles for role in self.required_approvers):
            raise PermissionError(
                f"User {rejector_context.username} is not authorized to reject overrides"
            )
        
        # Get request
        request = await self.db.get_override_request(request_id)
        if not request:
            raise ValueError(f"Override request {request_id} not found")
        
        # Reject
        request.status = OverrideStatus.REJECTED
        request.rejected_by = rejector_context.user_id
        request.rejected_reason = reason
        request.rejected_at = datetime.now(timezone.utc)
        
        # Update in database
        await self.db.update_override_request(request)
        
        # Notify requester
        await self._notify_requester_rejected(request)
    
    async def validate_override_token(
        self,
        token: str,
        resource: str,
        action: str
    ) -> Optional[OverrideRequest]:
        """Validate an override token for use"""
        
        # Find request by token
        request = await self.db.get_override_by_token(token)
        if not request:
            return None
        
        # Check if valid for use
        if not request.is_valid_for_use():
            return None
        
        # Check if token matches the resource/action
        if request.resource != resource or request.action != action:
            return None
        
        # Mark as used
        request.mark_as_used()
        await self.db.update_override_request(request)
        
        return request
    
    async def _notify_approvers(self, request: OverrideRequest):
        """Send notification to approvers"""
        # Implementation would send actual notifications
        pass
    
    async def _notify_requester_approved(self, request: OverrideRequest):
        """Notify requester of approval"""
        pass
    
    async def _notify_requester_rejected(self, request: OverrideRequest):
        """Notify requester of rejection"""
        pass