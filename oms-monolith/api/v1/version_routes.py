"""
Version Tracking API Routes
Endpoints for version history and delta synchronization
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from pydantic import BaseModel, Field

from core.auth_utils import UserContext
from middleware.auth_middleware import get_current_user
from core.versioning.version_service import get_version_service
from models.etag import (
    DeltaRequest, CacheValidation, VersionInfo, ResourceVersion
)
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/versions", tags=["Version Tracking"])


# Request/Response Models

class VersionHistoryRequest(BaseModel):
    """Request for version history"""
    resource_type: str = Field(..., description="Type of resource")
    resource_id: str = Field(..., description="Resource identifier")
    branch: str = Field(..., description="Branch name")
    limit: int = Field(50, ge=1, le=100, description="Maximum versions to return")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class VersionHistoryResponse(BaseModel):
    """Response with version history"""
    resource_type: str
    resource_id: str
    branch: str
    versions: List[VersionInfo]
    total_versions: int
    has_more: bool


class DeltaSyncRequest(BaseModel):
    """Request for delta synchronization"""
    resources: List[Dict[str, Any]] = Field(..., description="Resources to sync")
    branch: str = Field(..., description="Branch name")
    include_full: bool = Field(False, description="Include full content for changes")


class BulkValidationRequest(BaseModel):
    """Request for bulk cache validation"""
    branch: str = Field(..., description="Branch name")
    resources: Dict[str, str] = Field(..., description="Map of resource key to ETag")


# Version History Endpoints

@router.get("/history/{resource_type}/{resource_id}")
async def get_version_history(
    resource_type: str,
    resource_id: str,
    branch: str = Query(..., description="Branch name"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: UserContext = Depends(get_current_user)
) -> VersionHistoryResponse:
    """Get version history for a resource"""
    version_service = await get_version_service()
    
    # This would query the database for version history
    # For now, return current version
    current = await version_service.get_resource_version(
        resource_type, resource_id, branch
    )
    
    if not current:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_type}/{resource_id} not found on branch {branch}"
        )
    
    return VersionHistoryResponse(
        resource_type=resource_type,
        resource_id=resource_id,
        branch=branch,
        versions=[current.current_version],
        total_versions=1,
        has_more=False
    )


@router.get("/version/{resource_type}/{resource_id}/{version}")
async def get_specific_version(
    resource_type: str,
    resource_id: str,
    version: int,
    branch: str = Query(..., description="Branch name"),
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get specific version of a resource"""
    version_service = await get_version_service()
    
    resource_version = await version_service.get_resource_version(
        resource_type, resource_id, branch, version
    )
    
    if not resource_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version} not found for {resource_type}/{resource_id}"
        )
    
    return {
        "version_info": resource_version.current_version.dict(),
        "content_hash": resource_version.content_hash,
        "content_size": resource_version.content_size
    }


# Delta Sync Endpoints

@router.post("/delta/{resource_type}/{resource_id}")
async def get_resource_delta(
    resource_type: str,
    resource_id: str,
    branch: str = Query(..., description="Branch name"),
    if_none_match: Optional[str] = Header(None, description="Client ETag"),
    x_client_version: Optional[int] = Header(None, description="Client version"),
    x_client_commit: Optional[str] = Header(None, description="Client commit"),
    x_include_full: bool = Header(False, description="Include full content"),
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get delta for a single resource"""
    version_service = await get_version_service()
    
    delta_request = DeltaRequest(
        client_etag=if_none_match,
        client_version=x_client_version,
        client_commit=x_client_commit,
        include_full=x_include_full
    )
    
    delta_response = await version_service.get_delta(
        resource_type, resource_id, branch, delta_request
    )
    
    return delta_response.dict()


@router.post("/sync")
async def bulk_sync(
    request: DeltaSyncRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Sync multiple resources with delta support"""
    version_service = await get_version_service()
    
    sync_results = []
    total_delta_size = 0
    
    for resource in request.resources:
        delta_request = DeltaRequest(
            client_etag=resource.get("etag"),
            client_version=resource.get("version"),
            include_full=request.include_full
        )
        
        delta_response = await version_service.get_delta(
            resource["type"],
            resource["id"],
            request.branch,
            delta_request
        )
        
        sync_results.append({
            "resource": f"{resource['type']}:{resource['id']}",
            "response_type": delta_response.response_type,
            "changes": len(delta_response.changes),
            "new_etag": delta_response.etag,
            "new_version": delta_response.to_version.version
        })
        
        total_delta_size += delta_response.delta_size
    
    return {
        "branch": request.branch,
        "resources_synced": len(sync_results),
        "total_delta_size": total_delta_size,
        "results": sync_results
    }


# Cache Validation Endpoints

@router.post("/validate-cache")
async def validate_cache(
    validation: CacheValidation,
    branch: str = Query(..., description="Branch name"),
    user: UserContext = Depends(get_current_user)
) -> CacheValidation:
    """Validate multiple resource ETags"""
    version_service = await get_version_service()
    
    result = await version_service.validate_cache(branch, validation)
    
    return result


@router.post("/validate")
async def validate_single_etag(
    resource_type: str = Query(..., description="Resource type"),
    resource_id: str = Query(..., description="Resource ID"),
    branch: str = Query(..., description="Branch name"),
    if_none_match: Optional[str] = Header(None, description="ETag to validate"),
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Validate a single ETag"""
    if not if_none_match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="If-None-Match header required"
        )
    
    version_service = await get_version_service()
    
    is_valid, current_version = await version_service.validate_etag(
        resource_type, resource_id, branch, if_none_match
    )
    
    return {
        "valid": is_valid,
        "client_etag": if_none_match,
        "current_etag": current_version.current_version.etag if current_version else None,
        "current_version": current_version.current_version.version if current_version else None
    }


# Version Summary Endpoints

@router.get("/summary/{branch}")
async def get_branch_version_summary(
    branch: str,
    resource_types: Optional[List[str]] = Query(None, description="Filter by types"),
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get version summary for a branch"""
    version_service = await get_version_service()
    
    summary = await version_service.get_branch_version_summary(
        branch, resource_types
    )
    
    return summary


@router.post("/compare/{branch1}/{branch2}")
async def compare_branches(
    branch1: str,
    branch2: str,
    resource_types: Optional[List[str]] = Query(None, description="Filter by types"),
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Compare versions between two branches"""
    version_service = await get_version_service()
    
    # Get summaries for both branches
    summary1 = await version_service.get_branch_version_summary(branch1, resource_types)
    summary2 = await version_service.get_branch_version_summary(branch2, resource_types)
    
    # Compare resource types
    comparison = {
        "branch1": branch1,
        "branch2": branch2,
        "differences": {
            "only_in_branch1": [],
            "only_in_branch2": [],
            "version_differences": []
        }
    }
    
    types1 = set(summary1["resource_types"].keys())
    types2 = set(summary2["resource_types"].keys())
    
    comparison["differences"]["only_in_branch1"] = list(types1 - types2)
    comparison["differences"]["only_in_branch2"] = list(types2 - types1)
    
    # Compare versions for common types
    for resource_type in types1 & types2:
        info1 = summary1["resource_types"][resource_type]
        info2 = summary2["resource_types"][resource_type]
        
        if info1["max_version"] != info2["max_version"]:
            comparison["differences"]["version_differences"].append({
                "resource_type": resource_type,
                "branch1_version": info1["max_version"],
                "branch2_version": info2["max_version"],
                "version_diff": info1["max_version"] - info2["max_version"]
            })
    
    return comparison


# Conflict Resolution Endpoints

@router.post("/conflicts/detect")
async def detect_conflicts(
    resource_type: str,
    resource_id: str,
    source_branch: str,
    target_branch: str,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Detect version conflicts between branches"""
    version_service = await get_version_service()
    
    # Get versions from both branches
    source_version = await version_service.get_resource_version(
        resource_type, resource_id, source_branch
    )
    target_version = await version_service.get_resource_version(
        resource_type, resource_id, target_branch
    )
    
    if not source_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource not found in source branch {source_branch}"
        )
    
    if not target_version:
        # No conflict - resource doesn't exist in target
        return {
            "has_conflict": False,
            "conflict_type": "new_in_source",
            "can_auto_merge": True
        }
    
    # Check if they have common ancestor
    has_conflict = source_version.current_version.commit_hash != target_version.current_version.commit_hash
    
    return {
        "has_conflict": has_conflict,
        "conflict_type": "version_divergence" if has_conflict else "no_conflict",
        "source_version": source_version.current_version.dict(),
        "target_version": target_version.current_version.dict(),
        "can_auto_merge": False  # Would need actual content comparison
    }