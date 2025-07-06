"""
ETag and Version Hash Models
For efficient delta responses and caching
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import hashlib
import json


class VersionInfo(BaseModel):
    """Version information for a resource"""
    
    version: int = Field(..., description="Version number")
    commit_hash: str = Field(..., description="Git-like commit hash")
    etag: str = Field(..., description="ETag for HTTP caching")
    last_modified: datetime = Field(..., description="Last modification time")
    modified_by: str = Field(..., description="User who made the last change")
    
    # Delta tracking
    parent_version: Optional[int] = Field(None, description="Previous version number")
    parent_commit: Optional[str] = Field(None, description="Previous commit hash")
    
    # Change summary
    change_type: str = Field(..., description="Type of change (create, update, delete)")
    change_summary: Optional[str] = Field(None, description="Brief description of changes")
    fields_changed: List[str] = Field(default_factory=list, description="List of changed fields")


class ResourceVersion(BaseModel):
    """Version tracking for a specific resource"""
    
    resource_type: str = Field(..., description="Type of resource (object_type, link_type, etc)")
    resource_id: str = Field(..., description="Resource identifier")
    branch: str = Field(..., description="Branch name")
    
    # Current version
    current_version: VersionInfo = Field(..., description="Current version information")
    
    # Content hash
    content_hash: str = Field(..., description="SHA256 hash of resource content")
    
    # Size information
    content_size: int = Field(..., description="Size of resource in bytes")
    
    def generate_etag(self) -> str:
        """Generate ETag from version info"""
        return f'W/"{self.current_version.commit_hash[:12]}-{self.current_version.version}"'


class DeltaRequest(BaseModel):
    """Request for delta changes"""
    
    # Client version info
    client_etag: Optional[str] = Field(None, description="Client's current ETag")
    client_version: Optional[int] = Field(None, description="Client's current version")
    client_commit: Optional[str] = Field(None, description="Client's current commit hash")
    
    # Options
    include_full: bool = Field(False, description="Include full resource if changed")
    max_delta_size: Optional[int] = Field(None, description="Maximum delta size in bytes")
    
    # Filtering
    resource_types: Optional[List[str]] = Field(None, description="Filter by resource types")
    modified_since: Optional[datetime] = Field(None, description="Only changes after this time")


class DeltaResponse(BaseModel):
    """Delta response with changes"""
    
    # Version info
    from_version: Optional[VersionInfo] = Field(None, description="Starting version")
    to_version: VersionInfo = Field(..., description="Target version")
    
    # Response type
    response_type: str = Field(..., description="full, delta, or no_change")
    
    # Changes
    changes: List['ResourceDelta'] = Field(default_factory=list, description="List of changes")
    
    # Metadata
    total_changes: int = Field(..., description="Total number of changes")
    delta_size: int = Field(..., description="Size of delta in bytes")
    compression_ratio: Optional[float] = Field(None, description="Compression ratio if applicable")
    
    # Cache headers
    etag: str = Field(..., description="ETag for this response")
    cache_control: str = Field("private, max-age=300", description="Cache control header")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ResourceDelta(BaseModel):
    """Delta for a single resource"""
    
    # Resource identification
    resource_type: str = Field(..., description="Type of resource")
    resource_id: str = Field(..., description="Resource identifier")
    
    # Change type
    operation: str = Field(..., description="create, update, delete")
    
    # Version transition
    from_version: Optional[int] = Field(None, description="Previous version")
    to_version: int = Field(..., description="New version")
    
    # Delta content
    delta_type: str = Field(..., description="full, patch, or deleted")
    
    # For updates - JSON Patch format
    patches: Optional[List[Dict[str, Any]]] = Field(None, description="JSON Patch operations")
    
    # For full updates
    full_content: Optional[Dict[str, Any]] = Field(None, description="Full resource content")
    
    # Metadata
    modified_fields: List[str] = Field(default_factory=list, description="List of modified fields")
    size_before: Optional[int] = Field(None, description="Size before change")
    size_after: Optional[int] = Field(None, description="Size after change")


class VersionConflict(BaseModel):
    """Version conflict information"""
    
    resource_type: str
    resource_id: str
    
    client_version: VersionInfo
    server_version: VersionInfo
    
    conflict_type: str = Field(..., description="version_mismatch, deleted, or force_update")
    resolution_strategy: str = Field(..., description="merge, overwrite, or manual")
    
    # Conflict details
    conflicting_fields: List[str] = Field(default_factory=list)
    can_auto_merge: bool = Field(False)
    suggested_resolution: Optional[Dict[str, Any]] = Field(None)


class CacheValidation(BaseModel):
    """Cache validation request/response"""
    
    resource_etags: Dict[str, str] = Field(..., description="Map of resource ID to ETag")
    
    # Validation results
    valid_resources: List[str] = Field(default_factory=list, description="Resources that are still valid")
    stale_resources: List[str] = Field(default_factory=list, description="Resources that need refresh")
    deleted_resources: List[str] = Field(default_factory=list, description="Resources that were deleted")
    
    # Bulk ETag
    collection_etag: Optional[str] = Field(None, description="ETag for entire collection")


# Helper functions

def calculate_content_hash(content: Dict[str, Any]) -> str:
    """Calculate SHA256 hash of content"""
    # Sort keys for consistent hashing
    normalized = json.dumps(content, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(normalized.encode()).hexdigest()


def generate_commit_hash(
    parent_hash: Optional[str],
    content_hash: str,
    author: str,
    timestamp: datetime
) -> str:
    """Generate Git-like commit hash"""
    commit_data = {
        "parent": parent_hash or "root",
        "content": content_hash,
        "author": author,
        "timestamp": timestamp.isoformat()
    }
    commit_str = json.dumps(commit_data, sort_keys=True)
    return hashlib.sha256(commit_str.encode()).hexdigest()


def create_json_patch(old_content: Dict[str, Any], new_content: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create JSON Patch operations for delta"""
    # Simplified version - in production, use a proper JSON Patch library
    patches = []
    
    # Check for added fields
    for key, value in new_content.items():
        if key not in old_content:
            patches.append({
                "op": "add",
                "path": f"/{key}",
                "value": value
            })
        elif old_content[key] != value:
            patches.append({
                "op": "replace",
                "path": f"/{key}",
                "value": value
            })
    
    # Check for removed fields
    for key in old_content:
        if key not in new_content:
            patches.append({
                "op": "remove",
                "path": f"/{key}"
            })
    
    return patches