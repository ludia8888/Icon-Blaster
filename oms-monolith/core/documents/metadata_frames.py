"""
Metadata Frames for Markdown Documentation
Implements @metadata frames for embedding structured metadata in markdown
"""
from typing import Dict, Any, List, Optional, Tuple
import re
import yaml
import json
from datetime import datetime
from dataclasses import dataclass, field

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MetadataFrame:
    """Represents a metadata frame in a document"""
    frame_type: str
    content: Dict[str, Any]
    position: Tuple[int, int]  # (start_line, end_line)
    format: str = "yaml"  # yaml, json, or toml
    
    def to_markdown(self) -> str:
        """Convert frame back to markdown format"""
        if self.format == "yaml":
            content_str = yaml.dump(self.content, default_flow_style=False)
        elif self.format == "json":
            content_str = json.dumps(self.content, indent=2)
        else:
            raise ValueError(f"Unsupported format: {self.format}")
            
        return f"```@metadata:{self.frame_type}\n{content_str}```"


class MetadataFrameParser:
    """
    Parser for @metadata frames in markdown documents
    """
    
    # Regex patterns for different frame formats
    FRAME_PATTERN = re.compile(
        r'```@metadata:(\w+)(?:\s+(\w+))?\n(.*?)\n```',
        re.DOTALL | re.MULTILINE
    )
    
    FRONT_MATTER_PATTERN = re.compile(
        r'^---\n(.*?)\n---',
        re.DOTALL | re.MULTILINE
    )
    
    def __init__(self):
        self.supported_formats = ['yaml', 'json', 'toml']
        self.frame_types = [
            'schema',      # Schema definition metadata
            'document',    # Document metadata
            'api',         # API endpoint metadata
            'example',     # Example metadata
            'validation',  # Validation rules
            'changelog',   # Change history
            'custom'       # Custom metadata
        ]
    
    def parse_document(self, markdown_content: str) -> Tuple[str, List[MetadataFrame]]:
        """
        Parse markdown document and extract metadata frames
        
        Returns:
            (cleaned_content, metadata_frames)
        """
        frames = []
        
        # Parse front matter first
        front_matter_match = self.FRONT_MATTER_PATTERN.match(markdown_content)
        if front_matter_match:
            try:
                front_matter_content = yaml.safe_load(front_matter_match.group(1))
                frames.append(MetadataFrame(
                    frame_type='document',
                    content=front_matter_content,
                    position=(0, len(front_matter_match.group(0).split('\n')) - 1),
                    format='yaml'
                ))
                # Remove front matter from content
                markdown_content = markdown_content[front_matter_match.end():]
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse front matter: {e}")
        
        # Parse @metadata frames
        offset = 0
        cleaned_content = markdown_content
        
        for match in self.FRAME_PATTERN.finditer(markdown_content):
            frame_type = match.group(1)
            format_hint = match.group(2) or 'yaml'
            content_str = match.group(3)
            
            try:
                # Parse content based on format
                if format_hint == 'json':
                    content = json.loads(content_str)
                elif format_hint == 'yaml' or format_hint is None:
                    content = yaml.safe_load(content_str)
                else:
                    logger.warning(f"Unsupported format: {format_hint}, treating as yaml")
                    content = yaml.safe_load(content_str)
                
                # Calculate position
                start_line = markdown_content[:match.start()].count('\n')
                end_line = start_line + match.group(0).count('\n')
                
                frames.append(MetadataFrame(
                    frame_type=frame_type,
                    content=content,
                    position=(start_line, end_line),
                    format=format_hint
                ))
                
            except (yaml.YAMLError, json.JSONDecodeError) as e:
                logger.error(f"Failed to parse metadata frame: {e}")
                continue
        
        # Remove metadata frames from content
        cleaned_content = self.FRAME_PATTERN.sub('', cleaned_content)
        
        return cleaned_content.strip(), frames
    
    def inject_frames(self, markdown_content: str, frames: List[MetadataFrame]) -> str:
        """
        Inject metadata frames back into markdown document
        """
        lines = markdown_content.split('\n')
        
        # Sort frames by position (reverse order for insertion)
        sorted_frames = sorted(frames, key=lambda f: f.position[0], reverse=True)
        
        for frame in sorted_frames:
            frame_markdown = frame.to_markdown()
            insert_line = frame.position[0]
            
            # Insert frame at the appropriate position
            if insert_line <= len(lines):
                lines.insert(insert_line, frame_markdown)
            else:
                lines.append(frame_markdown)
        
        return '\n'.join(lines)


@dataclass
class SchemaDocumentation:
    """
    Schema documentation with metadata frames
    """
    name: str
    title: str
    description: str
    version: str = "1.0.0"
    author: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    metadata_frames: List[MetadataFrame] = field(default_factory=list)
    content: str = ""
    
    def to_markdown(self) -> str:
        """Generate markdown documentation with metadata frames"""
        # Front matter
        front_matter = {
            'name': self.name,
            'title': self.title,
            'version': self.version,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'author': self.author,
            'tags': self.tags
        }
        
        # Remove None values
        front_matter = {k: v for k, v in front_matter.items() if v is not None}
        
        markdown_parts = []
        
        # Add front matter
        markdown_parts.append('---')
        markdown_parts.append(yaml.dump(front_matter, default_flow_style=False).strip())
        markdown_parts.append('---')
        markdown_parts.append('')
        
        # Add title and description
        markdown_parts.append(f'# {self.title}')
        markdown_parts.append('')
        markdown_parts.append(self.description)
        markdown_parts.append('')
        
        # Add content
        if self.content:
            markdown_parts.append(self.content)
            markdown_parts.append('')
        
        # Add metadata frames
        for frame in self.metadata_frames:
            markdown_parts.append(frame.to_markdown())
            markdown_parts.append('')
        
        return '\n'.join(markdown_parts)


class SchemaDocumentationGenerator:
    """
    Generates schema documentation with metadata frames
    """
    
    def __init__(self):
        self.parser = MetadataFrameParser()
    
    def generate_object_type_doc(
        self,
        object_type: Dict[str, Any]
    ) -> SchemaDocumentation:
        """Generate documentation for an object type"""
        doc = SchemaDocumentation(
            name=object_type['name'],
            title=object_type.get('displayName', object_type['name']),
            description=object_type.get('description', ''),
            version=object_type.get('version', '1.0.0'),
            created_at=datetime.fromisoformat(object_type['createdAt']) if 'createdAt' in object_type else None,
            updated_at=datetime.fromisoformat(object_type['modifiedAt']) if 'modifiedAt' in object_type else None,
            tags=object_type.get('tags', [])
        )
        
        # Generate content sections
        content_parts = []
        
        # Properties section
        if 'properties' in object_type:
            content_parts.append('## Properties\n')
            for prop in object_type['properties']:
                content_parts.append(f"### {prop['displayName']}")
                content_parts.append(f"- **Name**: `{prop['name']}`")
                content_parts.append(f"- **Type**: `{prop['dataType']}`")
                content_parts.append(f"- **Required**: {prop.get('isRequired', False)}")
                if 'description' in prop:
                    content_parts.append(f"- **Description**: {prop['description']}")
                content_parts.append('')
        
        doc.content = '\n'.join(content_parts)
        
        # Add metadata frames
        
        # Schema frame
        schema_frame = MetadataFrame(
            frame_type='schema',
            content={
                'type': 'object_type',
                'name': object_type['name'],
                'extends': object_type.get('extends'),
                'implements': object_type.get('implements', []),
                'status': object_type.get('status', 'active')
            },
            position=(0, 0)
        )
        doc.metadata_frames.append(schema_frame)
        
        # Validation frame if there are validation rules
        validation_rules = {}
        for prop in object_type.get('properties', []):
            if prop.get('isRequired') or prop.get('isUnique') or prop.get('isPrimaryKey'):
                validation_rules[prop['name']] = {
                    'required': prop.get('isRequired', False),
                    'unique': prop.get('isUnique', False),
                    'primaryKey': prop.get('isPrimaryKey', False)
                }
        
        if validation_rules:
            validation_frame = MetadataFrame(
                frame_type='validation',
                content={'properties': validation_rules},
                position=(0, 0)
            )
            doc.metadata_frames.append(validation_frame)
        
        return doc
    
    def generate_api_doc(
        self,
        endpoint: Dict[str, Any]
    ) -> SchemaDocumentation:
        """Generate API documentation with metadata frames"""
        doc = SchemaDocumentation(
            name=endpoint['operationId'],
            title=endpoint.get('summary', endpoint['operationId']),
            description=endpoint.get('description', ''),
            tags=endpoint.get('tags', [])
        )
        
        # API metadata frame
        api_frame = MetadataFrame(
            frame_type='api',
            content={
                'method': endpoint['method'],
                'path': endpoint['path'],
                'operationId': endpoint['operationId'],
                'parameters': endpoint.get('parameters', []),
                'requestBody': endpoint.get('requestBody'),
                'responses': endpoint.get('responses', {})
            },
            position=(0, 0)
        )
        doc.metadata_frames.append(api_frame)
        
        # Example frame if examples exist
        if 'examples' in endpoint:
            example_frame = MetadataFrame(
                frame_type='example',
                content=endpoint['examples'],
                position=(0, 0)
            )
            doc.metadata_frames.append(example_frame)
        
        return doc
    
    def extract_metadata_summary(
        self,
        markdown_content: str
    ) -> Dict[str, Any]:
        """Extract summary of all metadata from a markdown document"""
        _, frames = self.parser.parse_document(markdown_content)
        
        summary = {
            'total_frames': len(frames),
            'frame_types': {},
            'metadata': {}
        }
        
        for frame in frames:
            # Count frame types
            if frame.frame_type not in summary['frame_types']:
                summary['frame_types'][frame.frame_type] = 0
            summary['frame_types'][frame.frame_type] += 1
            
            # Merge metadata
            if frame.frame_type == 'document':
                summary['metadata'].update(frame.content)
            else:
                if frame.frame_type not in summary['metadata']:
                    summary['metadata'][frame.frame_type] = []
                summary['metadata'][frame.frame_type].append(frame.content)
        
        return summary