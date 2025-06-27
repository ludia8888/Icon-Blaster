"""
Audit API Routes
REST endpoints for audit log access and management
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from pydantic import BaseModel, Field

from core.auth import UserContext
from middleware.auth_middleware import get_current_user
from core.audit.audit_service import get_audit_service, AuditServiceError
from models.audit_events import AuditEventFilter, AuditAction, ResourceType
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/audit", tags=["Audit Management"])


# Request/Response Models

class AuditQueryRequest(BaseModel):
    """Request parameters for audit log queries"""
    start_time: Optional[datetime] = Field(None, description="Start time for query range")
    end_time: Optional[datetime] = Field(None, description="End time for query range")
    actor_ids: Optional[List[str]] = Field(None, description="Filter by actor IDs")
    actions: Optional[List[AuditAction]] = Field(None, description="Filter by actions")
    resource_types: Optional[List[ResourceType]] = Field(None, description="Filter by resource types")
    resource_ids: Optional[List[str]] = Field(None, description="Filter by resource IDs")
    branches: Optional[List[str]] = Field(None, description="Filter by branches")
    success: Optional[bool] = Field(None, description="Filter by success status")
    tags: Optional[Dict[str, str]] = Field(None, description="Filter by tags")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class AuditEventResponse(BaseModel):
    """Response model for audit events"""
    id: str
    created_at: datetime
    action: str
    actor_id: str
    actor_username: str
    actor_is_service: bool
    target_resource_type: str
    target_resource_id: str
    target_resource_name: Optional[str]
    target_branch: Optional[str]
    success: bool
    error_code: Optional[str]
    error_message: Optional[str]
    duration_ms: Optional[int]
    request_id: Optional[str]
    correlation_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    changes: Optional[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]]
    tags: Optional[Dict[str, str]]


class AuditQueryResponse(BaseModel):
    """Response for audit log queries"""
    events: List[AuditEventResponse]
    total_count: int
    page_info: Dict[str, Any]


class AuditStatisticsResponse(BaseModel):
    """Response for audit statistics"""
    total_events: int
    events_by_action: Dict[str, int]
    events_by_resource_type: Dict[str, int]
    top_actors: Dict[str, int]
    success_rate: float
    failure_rate: float
    service_stats: Dict[str, Any]
    queue_health: Dict[str, Any]


class ComplianceReportRequest(BaseModel):
    """Request for compliance report generation"""
    start_date: datetime = Field(..., description="Report start date")
    end_date: datetime = Field(..., description="Report end date")
    format: str = Field("json", description="Report format (json, csv)")


class ComplianceReportResponse(BaseModel):
    """Response for compliance reports"""
    report_period: Dict[str, Any]
    summary: Dict[str, Any]
    compliance_metrics: Dict[str, Any]
    security_highlights: Dict[str, Any]


# Audit Query Endpoints

@router.post("/query")
async def query_audit_events(
    request: AuditQueryRequest,
    user: UserContext = Depends(get_current_user)
) -> AuditQueryResponse:
    """Query audit events with filtering and pagination"""
    # Check permissions - only admins and auditors can query audit logs
    if not (user.is_admin or "auditor" in user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for audit log access"
        )
    
    try:
        audit_service = await get_audit_service()
        
        # Convert request to filter criteria
        filter_criteria = AuditEventFilter(
            start_time=request.start_time,
            end_time=request.end_time,
            actor_ids=request.actor_ids,
            actions=request.actions,
            resource_types=request.resource_types,
            resource_ids=request.resource_ids,
            branches=request.branches,
            success=request.success,
            tags=request.tags,
            limit=request.limit,
            offset=request.offset
        )
        
        events, total_count = await audit_service.query_audit_events(filter_criteria)
        
        # Convert to response format
        event_responses = [
            AuditEventResponse(
                id=event['id'],
                created_at=datetime.fromisoformat(event['created_at'].replace('Z', '+00:00')),
                action=event['action'],
                actor_id=event['actor_id'],
                actor_username=event['actor_username'],
                actor_is_service=event['actor_is_service'],
                target_resource_type=event['target_resource_type'],
                target_resource_id=event['target_resource_id'],
                target_resource_name=event.get('target_resource_name'),
                target_branch=event.get('target_branch'),
                success=event['success'],
                error_code=event.get('error_code'),
                error_message=event.get('error_message'),
                duration_ms=event.get('duration_ms'),
                request_id=event.get('request_id'),
                correlation_id=event.get('correlation_id'),
                ip_address=event.get('ip_address'),
                user_agent=event.get('user_agent'),
                changes=event.get('changes'),
                metadata=event.get('metadata'),
                tags=event.get('tags')
            )
            for event in events
        ]
        
        return AuditQueryResponse(
            events=event_responses,
            total_count=total_count,
            page_info={
                "limit": request.limit,
                "offset": request.offset,
                "has_more": request.offset + len(events) < total_count,
                "next_offset": request.offset + len(events) if request.offset + len(events) < total_count else None
            }
        )
        
    except AuditServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audit service error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error querying audit events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query audit events"
        )


@router.get("/events/{event_id}")
async def get_audit_event(
    event_id: str,
    user: UserContext = Depends(get_current_user)
) -> AuditEventResponse:
    """Get specific audit event by ID"""
    # Check permissions
    if not (user.is_admin or "auditor" in user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for audit log access"
        )
    
    try:
        audit_service = await get_audit_service()
        event = await audit_service.get_audit_event(event_id)
        
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Audit event not found: {event_id}"
            )
        
        return AuditEventResponse(
            id=event['id'],
            created_at=datetime.fromisoformat(event['created_at'].replace('Z', '+00:00')),
            action=event['action'],
            actor_id=event['actor_id'],
            actor_username=event['actor_username'],
            actor_is_service=event['actor_is_service'],
            target_resource_type=event['target_resource_type'],
            target_resource_id=event['target_resource_id'],
            target_resource_name=event.get('target_resource_name'),
            target_branch=event.get('target_branch'),
            success=event['success'],
            error_code=event.get('error_code'),
            error_message=event.get('error_message'),
            duration_ms=event.get('duration_ms'),
            request_id=event.get('request_id'),
            correlation_id=event.get('correlation_id'),
            ip_address=event.get('ip_address'),
            user_agent=event.get('user_agent'),
            changes=event.get('changes'),
            metadata=event.get('metadata'),
            tags=event.get('tags')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting audit event {event_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get audit event"
        )


# Statistics and Monitoring Endpoints

@router.get("/statistics")
async def get_audit_statistics(
    start_time: Optional[datetime] = Query(None, description="Statistics start time"),
    end_time: Optional[datetime] = Query(None, description="Statistics end time"),
    user: UserContext = Depends(get_current_user)
) -> AuditStatisticsResponse:
    """Get audit statistics for monitoring and dashboards"""
    # Check permissions
    if not (user.is_admin or "auditor" in user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for audit statistics"
        )
    
    try:
        audit_service = await get_audit_service()
        stats = await audit_service.get_audit_statistics(start_time, end_time)
        
        return AuditStatisticsResponse(
            total_events=stats.get('total_events', 0),
            events_by_action=stats.get('events_by_action', {}),
            events_by_resource_type=stats.get('events_by_resource_type', {}),
            top_actors=stats.get('top_actors', {}),
            success_rate=stats.get('success_rate', 0.0),
            failure_rate=stats.get('failure_rate', 0.0),
            service_stats=stats.get('service_stats', {}),
            queue_health=stats.get('queue_health', {})
        )
        
    except Exception as e:
        logger.error(f"Error getting audit statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get audit statistics"
        )


@router.get("/health")
async def get_audit_health(
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get audit system health status"""
    # Check permissions
    if not (user.is_admin or "auditor" in user.roles or user.is_service_account):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for audit health status"
        )
    
    try:
        audit_service = await get_audit_service()
        
        # Get recent statistics
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        stats = await audit_service.get_audit_statistics(recent_time)
        
        # Check system health indicators
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recent_activity": {
                "events_last_hour": stats.get('total_events', 0),
                "failure_rate": stats.get('failure_rate', 0.0)
            },
            "service_health": stats.get('service_stats', {}),
            "queue_health": stats.get('queue_health', {}),
            "database_accessible": True  # Will be False if database fails
        }
        
        # Determine overall health
        queue_health = stats.get('queue_health', {})
        if queue_health.get('queue_utilization', 0) > 0.9:
            health_status["status"] = "degraded"
            health_status["warnings"] = ["High queue utilization"]
        
        if stats.get('failure_rate', 0) > 0.1:  # > 10% failure rate
            health_status["status"] = "degraded"
            health_status.setdefault("warnings", []).append("High failure rate")
        
        return health_status
        
    except Exception as e:
        logger.error(f"Error getting audit health: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }


# Compliance and Export Endpoints

@router.post("/compliance/report")
async def generate_compliance_report(
    request: ComplianceReportRequest,
    user: UserContext = Depends(get_current_user)
) -> ComplianceReportResponse:
    """Generate compliance report for auditors"""
    # Check permissions - only auditors and compliance officers
    if not (user.is_admin or "auditor" in user.roles or "compliance" in user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for compliance reports"
        )
    
    try:
        audit_service = await get_audit_service()
        report = await audit_service.get_compliance_report(
            request.start_date,
            request.end_date
        )
        
        return ComplianceReportResponse(
            report_period=report['report_period'],
            summary=report['summary'],
            compliance_metrics=report['compliance_metrics'],
            security_highlights=report['security_highlights']
        )
        
    except Exception as e:
        logger.error(f"Error generating compliance report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate compliance report"
        )


@router.post("/export")
async def export_audit_logs(
    request: AuditQueryRequest,
    format: str = Query("json", description="Export format (json, csv)"),
    user: UserContext = Depends(get_current_user)
) -> Response:
    """Export audit logs for compliance and archival"""
    # Check permissions
    if not (user.is_admin or "auditor" in user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for audit log export"
        )
    
    try:
        audit_service = await get_audit_service()
        
        # Convert request to filter criteria
        filter_criteria = AuditEventFilter(
            start_time=request.start_time,
            end_time=request.end_time,
            actor_ids=request.actor_ids,
            actions=request.actions,
            resource_types=request.resource_types,
            resource_ids=request.resource_ids,
            branches=request.branches,
            success=request.success,
            tags=request.tags,
            limit=min(request.limit, 10000),  # Cap exports at 10k events
            offset=request.offset
        )
        
        export_data = await audit_service.export_audit_logs(filter_criteria, format)
        
        # Determine content type and filename
        if format.lower() == "json":
            content_type = "application/json"
            filename = f"audit_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported export format: {format}"
            )
        
        return Response(
            content=export_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Timestamp": datetime.now(timezone.utc).isoformat(),
                "X-Export-Format": format,
                "X-Exported-By": user.username
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export audit logs"
        )


# Administrative Endpoints

@router.post("/maintenance/cleanup")
async def cleanup_expired_events(
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Clean up expired audit events (admin only)"""
    # Check permissions - admin only
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator permissions required for maintenance operations"
        )
    
    try:
        audit_service = await get_audit_service()
        cleaned_count = await audit_service.cleanup_expired_events()
        
        return {
            "success": True,
            "message": f"Cleaned up {cleaned_count} expired audit events",
            "events_cleaned": cleaned_count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up expired events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cleanup expired events"
        )


@router.post("/maintenance/verify-integrity")
async def verify_audit_integrity(
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Verify audit log integrity (admin only)"""
    # Check permissions - admin only
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator permissions required for integrity verification"
        )
    
    try:
        audit_service = await get_audit_service()
        integrity_report = await audit_service.verify_integrity()
        
        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "integrity_report": integrity_report
        }
        
    except Exception as e:
        logger.error(f"Error verifying audit integrity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify audit integrity"
        )