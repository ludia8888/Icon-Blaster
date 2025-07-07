"""
Document Processing Module
Provides advanced document features including unfoldable content and metadata frames
"""

from .unfoldable import (
    UnfoldLevel,
    UnfoldableField,
    UnfoldContext,
    UnfoldableDocument,
    UnfoldableProcessor
)

from .metadata_frames import (
    MetadataFrame,
    MetadataFrameParser,
    SchemaDocumentation,
    SchemaDocumentationGenerator
)

__all__ = [
    # Unfoldable
    "UnfoldLevel",
    "UnfoldableField",
    "UnfoldContext",
    "UnfoldableDocument",
    "UnfoldableProcessor",
    
    # Metadata Frames
    "MetadataFrame",
    "MetadataFrameParser",
    "SchemaDocumentation",
    "SchemaDocumentationGenerator"
]