"""
Pydantic Request Models for API Endpoints
Type-safe request validation models replacing Dict[str, Any] parameters
"""

from pydantic import BaseModel, validator, Field
from typing import Optional, List, Dict, Any, Literal
import re
import email.utils


class BranchCreateRequest(BaseModel):
    """Request model for creating a new branch"""
    branch_name: str = Field(..., min_length=1, max_length=100, description="Name of the new branch")
    from_branch: Optional[str] = Field(None, max_length=100, description="Source branch to create from")
    
    @validator('branch_name', 'from_branch')
    def validate_branch_name(cls, v):
        if v is not None:
            if not re.match(r'^[a-zA-Z0-9/_-]+$', v):
                raise ValueError('Branch name can only contain letters, numbers, hyphens, underscores, and slashes')
        return v


class CheckoutRequest(BaseModel):
    """Request model for checkout operation"""
    target: str = Field(..., min_length=1, max_length=100, description="Branch name or commit ID to checkout")
    type: Literal["branch", "commit"] = Field("branch", description="Type of target: branch or commit")
    
    @validator('target')
    def validate_target(cls, v, values):
        target_type = values.get('type', 'branch')
        if target_type == "branch":
            # Branch name validation
            if not re.match(r'^[a-zA-Z0-9/_-]+$', v):
                raise ValueError('Branch name can only contain letters, numbers, hyphens, underscores, and slashes')
        elif target_type == "commit":
            # Commit ID validation (hexadecimal)
            if not re.match(r'^[a-fA-F0-9]+$', v):
                raise ValueError('Commit ID must be hexadecimal characters only')
        return v


class CommitRequest(BaseModel):
    """Request model for committing changes"""
    message: str = Field(..., min_length=1, max_length=500, description="Commit message")
    author: str = Field(..., description="Author email address")
    branch: Optional[str] = Field(None, max_length=100, description="Target branch for commit")
    
    @validator('author')
    def validate_author_email(cls, v):
        if not email.utils.parseaddr(v)[1]:
            raise ValueError('Author must be a valid email address')
        return v
    
    @validator('branch')
    def validate_branch_name(cls, v):
        if v is not None:
            if not re.match(r'^[a-zA-Z0-9/_-]+$', v):
                raise ValueError('Branch name can only contain letters, numbers, hyphens, underscores, and slashes')
        return v


class MergeRequest(BaseModel):
    """Request model for merging branches"""
    source_branch: str = Field(..., min_length=1, max_length=100, description="Source branch to merge from")
    target_branch: str = Field(..., min_length=1, max_length=100, description="Target branch to merge into")
    strategy: Literal["merge", "squash", "rebase"] = Field("merge", description="Merge strategy")
    message: Optional[str] = Field(None, max_length=500, description="Merge commit message")
    author: Optional[str] = Field(None, description="Author email address")
    
    @validator('source_branch', 'target_branch')
    def validate_branch_names(cls, v):
        if not re.match(r'^[a-zA-Z0-9/_-]+$', v):
            raise ValueError('Branch name can only contain letters, numbers, hyphens, underscores, and slashes')
        return v
    
    @validator('author')
    def validate_author_email(cls, v):
        if v is not None and not email.utils.parseaddr(v)[1]:
            raise ValueError('Author must be a valid email address')
        return v


class RollbackRequest(BaseModel):
    """Request model for rollback operation"""
    target_commit: str = Field(..., min_length=1, description="Commit ID to rollback to")
    create_branch: bool = Field(True, description="Whether to create a new branch for rollback")
    branch_name: Optional[str] = Field(None, max_length=100, description="Name for the rollback branch")
    
    @validator('target_commit')
    def validate_commit_id(cls, v):
        if not re.match(r'^[a-fA-F0-9]+$', v):
            raise ValueError('Commit ID must be hexadecimal characters only')
        return v
    
    @validator('branch_name')
    def validate_branch_name(cls, v):
        if v is not None:
            if not re.match(r'^[a-zA-Z0-9/_-]+$', v):
                raise ValueError('Branch name can only contain letters, numbers, hyphens, underscores, and slashes')
        return v


class DatabaseCreateRequest(BaseModel):
    """Request model for creating a database"""
    name: str = Field(..., min_length=1, max_length=50, description="Database name")
    description: str = Field("", max_length=500, description="Database description")
    
    @validator('name')
    def validate_database_name(cls, v):
        # Use the same validation as validate_db_name function
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', v):
            raise ValueError('Database name must start with a letter and contain only letters, numbers, hyphens, and underscores')
        return v


class ClassCreateRequest(BaseModel):
    """Request model for creating an ontology class"""
    id: str = Field(..., min_length=1, max_length=100, description="Class ID")
    label: str = Field(..., min_length=1, max_length=200, description="Class label")
    description: Optional[str] = Field(None, max_length=1000, description="Class description")
    properties: Optional[Dict[str, Any]] = Field(None, description="Class properties")
    
    @validator('id')
    def validate_class_id(cls, v):
        # Basic class ID validation - alphanumeric with underscores
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', v):
            raise ValueError('Class ID must start with a letter and contain only letters, numbers, and underscores')
        return v


class QueryRequest(BaseModel):
    """Request model for structured queries"""
    type: Literal["select", "count", "exists"] = Field(..., description="Query type")
    class_id: Optional[str] = Field(None, description="Target class ID")
    filters: Optional[List[Dict[str, Any]]] = Field(None, description="Query filters")
    limit: Optional[int] = Field(None, ge=1, le=1000, description="Result limit")
    offset: Optional[int] = Field(None, ge=0, description="Result offset")
    
    @validator('class_id')
    def validate_class_id(cls, v):
        if v is not None:
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', v):
                raise ValueError('Class ID must start with a letter and contain only letters, numbers, and underscores')
        return v


class MappingImportRequest(BaseModel):
    """Request model for importing label mappings"""
    db_name: str = Field(..., description="Target database name")
    classes: List[Dict[str, Any]] = Field([], description="Class mappings to import")
    properties: List[Dict[str, Any]] = Field([], description="Property mappings to import")
    relationships: List[Dict[str, Any]] = Field([], description="Relationship mappings to import")
    
    @validator('db_name')
    def validate_database_name(cls, v):
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', v):
            raise ValueError('Database name must start with a letter and contain only letters, numbers, hyphens, and underscores')
        return v
    
    @validator('classes', 'properties', 'relationships')
    def validate_mapping_lists(cls, v):
        if len(v) > 1000:  # Prevent excessive imports
            raise ValueError('Too many mappings in single import (max 1000 per type)')
        return v


# Response models for consistent API responses
class ApiResponse(BaseModel):
    """Standard API response format"""
    status: Literal["success", "error"] = Field(..., description="Response status")
    message: str = Field(..., description="Response message")
    data: Optional[Any] = Field(None, description="Response data")


class ErrorResponse(BaseModel):
    """Standard error response format"""
    status: Literal["error"] = Field("error", description="Error status")
    message: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    code: Optional[str] = Field(None, description="Error code")