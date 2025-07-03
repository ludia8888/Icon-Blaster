"""
GraphQL Schema for Document Features
Supports @unfoldable documents and @metadata frames
"""
from typing import List, Optional, Dict, Any
import strawberry
from strawberry.types import Info

from core.documents import (
    UnfoldLevel, UnfoldContext, UnfoldableDocument,
    SchemaDocumentation, SchemaDocumentationGenerator
)


@strawberry.enum
class UnfoldLevelEnum:
    """Levels of unfolding for documents"""
    COLLAPSED = "COLLAPSED"
    SHALLOW = "SHALLOW"
    DEEP = "DEEP"
    CUSTOM = "CUSTOM"


@strawberry.input
class UnfoldContextInput:
    """Input for unfold context"""
    level: UnfoldLevelEnum = UnfoldLevelEnum.COLLAPSED
    paths: Optional[List[str]] = None
    max_depth: int = 10
    size_threshold: int = 10240
    array_threshold: int = 100
    include_summaries: bool = True


@strawberry.type
class UnfoldableFieldInfo:
    """Information about an unfoldable field"""
    path: str
    display_name: str
    summary: Optional[str] = None
    size_bytes: Optional[int] = None
    item_count: Optional[int] = None
    is_large: bool = False


@strawberry.type
class UnfoldableDocumentResult:
    """Result of processing an unfoldable document"""
    content: strawberry.scalars.JSON
    unfoldable_paths: List[UnfoldableFieldInfo]
    metadata: Optional[strawberry.scalars.JSON] = None


@strawberry.type
class MetadataFrameInfo:
    """Information about a metadata frame"""
    frame_type: str
    content: strawberry.scalars.JSON
    position: List[int]  # [start_line, end_line]
    format: str


@strawberry.type
class DocumentMetadataResult:
    """Result of parsing document metadata"""
    cleaned_content: str
    metadata_frames: List[MetadataFrameInfo]
    summary: strawberry.scalars.JSON


@strawberry.type
class SchemaDocumentationResult:
    """Generated schema documentation"""
    name: str
    title: str
    description: str
    version: str
    markdown: str
    metadata_frames: List[MetadataFrameInfo]


# Query extensions
@strawberry.type
class DocumentQueries:
    """Document-related queries"""
    
    @strawberry.field
    async def unfold_document(
        self,
        info: Info,
        content: strawberry.scalars.JSON,
        context: UnfoldContextInput,
        metadata: Optional[strawberry.scalars.JSON] = None
    ) -> UnfoldableDocumentResult:
        """Process a document with unfoldable content"""
        # Convert input to core types
        unfold_level = UnfoldLevel[context.level.value]
        unfold_context = UnfoldContext(
            level=unfold_level,
            paths=set(context.paths) if context.paths else set(),
            max_depth=context.max_depth,
            size_threshold=context.size_threshold,
            array_threshold=context.array_threshold,
            include_summaries=context.include_summaries
        )
        
        # Create unfoldable document
        doc = UnfoldableDocument(content, metadata)
        
        # Fold document based on context
        folded_content = doc.fold(unfold_context)
        
        # Get unfoldable paths
        unfoldable_paths = [
            UnfoldableFieldInfo(
                path=path_info['path'],
                display_name=path_info['display_name'],
                summary=path_info.get('summary'),
                size_bytes=path_info.get('size_bytes'),
                item_count=path_info.get('item_count'),
                is_large=path_info.get('is_large', False)
            )
            for path_info in doc.get_unfoldable_paths()
        ]
        
        return UnfoldableDocumentResult(
            content=folded_content,
            unfoldable_paths=unfoldable_paths,
            metadata=metadata
        )
    
    @strawberry.field
    async def unfold_path(
        self,
        info: Info,
        content: strawberry.scalars.JSON,
        path: str
    ) -> strawberry.scalars.JSON:
        """Unfold a specific path in a document"""
        doc = UnfoldableDocument(content)
        return doc.unfold_path(path)
    
    @strawberry.field
    async def parse_metadata_frames(
        self,
        info: Info,
        markdown_content: str
    ) -> DocumentMetadataResult:
        """Parse metadata frames from markdown content"""
        from core.documents import MetadataFrameParser
        
        parser = MetadataFrameParser()
        cleaned_content, frames = parser.parse_document(markdown_content)
        
        # Convert frames to GraphQL type
        frame_infos = [
            MetadataFrameInfo(
                frame_type=frame.frame_type,
                content=frame.content,
                position=list(frame.position),
                format=frame.format
            )
            for frame in frames
        ]
        
        # Generate summary
        summary = {
            'total_frames': len(frames),
            'frame_types': {},
            'metadata': {}
        }
        
        for frame in frames:
            if frame.frame_type not in summary['frame_types']:
                summary['frame_types'][frame.frame_type] = 0
            summary['frame_types'][frame.frame_type] += 1
            
            if frame.frame_type == 'document':
                summary['metadata'].update(frame.content)
            else:
                if frame.frame_type not in summary['metadata']:
                    summary['metadata'][frame.frame_type] = []
                summary['metadata'][frame.frame_type].append(frame.content)
        
        return DocumentMetadataResult(
            cleaned_content=cleaned_content,
            metadata_frames=frame_infos,
            summary=summary
        )
    
    @strawberry.field
    async def generate_schema_documentation(
        self,
        info: Info,
        object_type: strawberry.scalars.JSON
    ) -> SchemaDocumentationResult:
        """Generate documentation for a schema object"""
        generator = SchemaDocumentationGenerator()
        doc = generator.generate_object_type_doc(object_type)
        
        # Convert metadata frames to GraphQL type
        frame_infos = [
            MetadataFrameInfo(
                frame_type=frame.frame_type,
                content=frame.content,
                position=list(frame.position),
                format=frame.format
            )
            for frame in doc.metadata_frames
        ]
        
        return SchemaDocumentationResult(
            name=doc.name,
            title=doc.title,
            description=doc.description,
            version=doc.version,
            markdown=doc.to_markdown(),
            metadata_frames=frame_infos
        )