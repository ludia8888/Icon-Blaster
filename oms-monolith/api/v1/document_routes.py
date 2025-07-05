"""
Document Processing API Routes
REST endpoints for unfoldable documents and metadata frames
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.auth_utils import UserContext
from middleware.auth_middleware import get_current_user
from core.documents import (
    UnfoldLevel, UnfoldContext, UnfoldableDocument,
    UnfoldableProcessor, MetadataFrameParser,
    SchemaDocumentationGenerator
)
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])


# Request/Response Models

class UnfoldContextRequest(BaseModel):
    """Request model for unfold context"""
    level: str = Field("COLLAPSED", description="Unfold level: COLLAPSED, SHALLOW, DEEP, CUSTOM")
    paths: Optional[List[str]] = Field(None, description="Specific paths to unfold")
    max_depth: int = Field(10, ge=1, le=20)
    size_threshold: int = Field(10240, ge=1024)
    array_threshold: int = Field(100, ge=10)
    include_summaries: bool = Field(True)


class UnfoldDocumentRequest(BaseModel):
    """Request for unfolding a document"""
    content: Dict[str, Any] = Field(..., description="Document content")
    context: UnfoldContextRequest = Field(..., description="Unfold context")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Document metadata")


class UnfoldPathRequest(BaseModel):
    """Request for unfolding a specific path"""
    content: Dict[str, Any] = Field(..., description="Document content")
    path: str = Field(..., description="Path to unfold")


class PrepareUnfoldableRequest(BaseModel):
    """Request for preparing a document with unfoldable annotations"""
    content: Dict[str, Any] = Field(..., description="Document content")
    unfoldable_paths: List[str] = Field(..., description="Paths to mark as unfoldable")


class ParseMetadataRequest(BaseModel):
    """Request for parsing metadata frames"""
    markdown_content: str = Field(..., description="Markdown content with metadata frames")


class GenerateDocumentationRequest(BaseModel):
    """Request for generating schema documentation"""
    object_type: Dict[str, Any] = Field(..., description="Object type definition")
    include_examples: bool = Field(True, description="Include example metadata frames")


# Endpoints

@router.post("/unfold")
async def unfold_document(
    request: UnfoldDocumentRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Process a document with unfoldable content
    
    Returns folded document based on the provided context
    """
    try:
        # Create unfold context
        unfold_level = UnfoldLevel[request.context.level]
        context = UnfoldContext(
            level=unfold_level,
            paths=set(request.context.paths) if request.context.paths else set(),
            max_depth=request.context.max_depth,
            size_threshold=request.context.size_threshold,
            array_threshold=request.context.array_threshold,
            include_summaries=request.context.include_summaries
        )
        
        # Create and process document
        doc = UnfoldableDocument(request.content, request.metadata)
        folded_content = doc.fold(context)
        unfoldable_paths = doc.get_unfoldable_paths()
        
        return {
            "content": folded_content,
            "unfoldable_paths": unfoldable_paths,
            "metadata": request.metadata,
            "stats": {
                "total_unfoldable_fields": len(unfoldable_paths),
                "unfold_level": request.context.level
            }
        }
        
    except Exception as e:
        logger.error(f"Error unfolding document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unfold document: {str(e)}"
        )


@router.post("/unfold-path")
async def unfold_path(
    request: UnfoldPathRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Unfold a specific path in a document
    
    Returns the content at the specified path
    """
    try:
        doc = UnfoldableDocument(request.content)
        content = doc.unfold_path(request.path)
        
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Path not found: {request.path}"
            )
        
        return {
            "path": request.path,
            "content": content,
            "type": type(content).__name__
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unfolding path: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unfold path: {str(e)}"
        )


@router.post("/prepare-unfoldable")
async def prepare_unfoldable(
    request: PrepareUnfoldableRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Prepare a document with @unfoldable annotations
    
    Marks specified paths as unfoldable in the document
    """
    try:
        prepared = UnfoldableProcessor.prepare_document(
            request.content,
            request.unfoldable_paths
        )
        
        return {
            "content": prepared,
            "unfoldable_paths": request.unfoldable_paths,
            "annotations_added": len(request.unfoldable_paths)
        }
        
    except Exception as e:
        logger.error(f"Error preparing unfoldable document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to prepare document: {str(e)}"
        )


@router.post("/extract-unfoldable")
async def extract_unfoldable(
    content: Dict[str, Any],
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Extract unfoldable content from a document
    
    Separates main document from unfoldable content
    """
    try:
        main_doc, unfoldable_content = UnfoldableProcessor.extract_unfoldable_content(
            content
        )
        
        return {
            "main_document": main_doc,
            "unfoldable_content": unfoldable_content,
            "stats": {
                "unfoldable_fields": len(unfoldable_content)
            }
        }
        
    except Exception as e:
        logger.error(f"Error extracting unfoldable content: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract content: {str(e)}"
        )


@router.post("/parse-metadata")
async def parse_metadata_frames(
    request: ParseMetadataRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Parse metadata frames from markdown content
    
    Extracts @metadata frames and returns cleaned content
    """
    try:
        parser = MetadataFrameParser()
        cleaned_content, frames = parser.parse_document(request.markdown_content)
        
        # Build summary
        summary = {
            'total_frames': len(frames),
            'frame_types': {},
            'metadata': {}
        }
        
        frame_list = []
        for frame in frames:
            frame_list.append({
                "frame_type": frame.frame_type,
                "content": frame.content,
                "position": frame.position,
                "format": frame.format
            })
            
            # Update summary
            if frame.frame_type not in summary['frame_types']:
                summary['frame_types'][frame.frame_type] = 0
            summary['frame_types'][frame.frame_type] += 1
            
            if frame.frame_type == 'document':
                summary['metadata'].update(frame.content)
        
        return {
            "cleaned_content": cleaned_content,
            "metadata_frames": frame_list,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Error parsing metadata frames: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse metadata: {str(e)}"
        )


@router.post("/generate-documentation")
async def generate_documentation(
    request: GenerateDocumentationRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Generate schema documentation with metadata frames
    
    Creates markdown documentation for schema objects
    """
    try:
        generator = SchemaDocumentationGenerator()
        doc = generator.generate_object_type_doc(request.object_type)
        
        # Extract frame information
        frames = []
        for frame in doc.metadata_frames:
            frames.append({
                "frame_type": frame.frame_type,
                "content": frame.content,
                "format": frame.format
            })
        
        return {
            "name": doc.name,
            "title": doc.title,
            "description": doc.description,
            "version": doc.version,
            "markdown": doc.to_markdown(),
            "metadata_frames": frames,
            "stats": {
                "total_frames": len(frames),
                "content_length": len(doc.to_markdown())
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating documentation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate documentation: {str(e)}"
        )


@router.get("/metadata-frame-types")
async def get_metadata_frame_types(
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get supported metadata frame types"""
    parser = MetadataFrameParser()
    
    return {
        "frame_types": parser.frame_types,
        "supported_formats": parser.supported_formats,
        "description": {
            "schema": "Schema definition metadata",
            "document": "Document metadata (front matter)",
            "api": "API endpoint metadata",
            "example": "Example metadata",
            "validation": "Validation rules",
            "changelog": "Change history",
            "custom": "Custom metadata"
        }
    }


@router.get("/unfold-levels")
async def get_unfold_levels(
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get supported unfold levels"""
    return {
        "levels": [
            {
                "name": "COLLAPSED",
                "value": 0,
                "description": "Only show summary/metadata"
            },
            {
                "name": "SHALLOW",
                "value": 1,
                "description": "Show immediate children"
            },
            {
                "name": "DEEP",
                "value": 2,
                "description": "Show all nested content"
            },
            {
                "name": "CUSTOM",
                "value": 3,
                "description": "Custom unfold paths"
            }
        ]
    }


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check for document service"""
    return {
        "status": "healthy",
        "service": "document-processor",
        "features": ["unfoldable", "metadata-frames"]
    }