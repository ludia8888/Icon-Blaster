"""
Unfoldable Documents Support
Implements @unfoldable annotation for selective loading of nested content
"""
from typing import Dict, Any, List, Optional, Set, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

from common_logging.setup import get_logger

logger = get_logger(__name__)


class UnfoldLevel(Enum):
    """Levels of unfolding for documents"""
    COLLAPSED = 0  # Only show summary/metadata
    SHALLOW = 1    # Show immediate children
    DEEP = 2       # Show all nested content
    CUSTOM = 3     # Custom unfold paths


@dataclass
class UnfoldableField:
    """Represents a field that can be unfolded"""
    path: str
    display_name: str
    summary: Optional[str] = None
    size_bytes: Optional[int] = None
    item_count: Optional[int] = None
    unfold_hint: Optional[str] = None
    is_large: bool = False
    
    def to_placeholder(self) -> Dict[str, Any]:
        """Convert to placeholder representation"""
        placeholder = {
            "@unfoldable": True,
            "path": self.path,
            "display_name": self.display_name
        }
        
        if self.summary:
            placeholder["summary"] = self.summary
        if self.size_bytes:
            placeholder["size_bytes"] = self.size_bytes
        if self.item_count:
            placeholder["item_count"] = self.item_count
        if self.unfold_hint:
            placeholder["hint"] = self.unfold_hint
        if self.is_large:
            placeholder["is_large"] = True
            
        return placeholder


@dataclass
class UnfoldContext:
    """Context for unfolding operations"""
    level: UnfoldLevel = UnfoldLevel.COLLAPSED
    paths: Set[str] = field(default_factory=set)
    max_depth: int = 10
    size_threshold: int = 10240  # 10KB
    array_threshold: int = 100
    include_summaries: bool = True


class UnfoldableDocument:
    """
    Handles documents with @unfoldable annotations
    """
    
    def __init__(self, content: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None):
        self.content = content
        self.metadata = metadata or {}
        self._unfoldable_fields = self._detect_unfoldable_fields()
    
    def _detect_unfoldable_fields(self) -> Dict[str, UnfoldableField]:
        """Detect fields marked as @unfoldable or large fields"""
        unfoldable_fields = {}
        
        def scan_object(obj: Any, path: str = "") -> None:
            if isinstance(obj, dict):
                # Check for explicit @unfoldable annotation
                if "@unfoldable" in obj and obj["@unfoldable"] is True:
                    field_info = UnfoldableField(
                        path=path,
                        display_name=obj.get("@display_name", path.split(".")[-1]),
                        summary=obj.get("@summary"),
                        unfold_hint=obj.get("@hint")
                    )
                    unfoldable_fields[path] = field_info
                    return
                
                # Scan nested fields
                for key, value in obj.items():
                    if key.startswith("@"):
                        continue
                    
                    new_path = f"{path}.{key}" if path else key
                    
                    # Auto-detect large fields
                    if self._should_auto_unfold(value):
                        field_info = self._create_auto_unfoldable(new_path, value)
                        unfoldable_fields[new_path] = field_info
                    else:
                        scan_object(value, new_path)
                        
            elif isinstance(obj, list):
                # Large arrays can be unfoldable
                if len(obj) > 100:
                    field_info = UnfoldableField(
                        path=path,
                        display_name=path.split(".")[-1],
                        summary=f"Array with {len(obj)} items",
                        item_count=len(obj),
                        is_large=True
                    )
                    unfoldable_fields[path] = field_info
        
        scan_object(self.content)
        return unfoldable_fields
    
    def _should_auto_unfold(self, value: Any) -> bool:
        """Check if a value should be automatically marked as unfoldable"""
        if isinstance(value, dict):
            # Large nested objects
            json_size = len(json.dumps(value))
            return json_size > 5000
        elif isinstance(value, list):
            # Large arrays
            return len(value) > 50
        elif isinstance(value, str):
            # Large text content
            return len(value) > 1000
        return False
    
    def _create_auto_unfoldable(self, path: str, value: Any) -> UnfoldableField:
        """Create unfoldable field for auto-detected large content"""
        field_name = path.split(".")[-1]
        
        if isinstance(value, dict):
            return UnfoldableField(
                path=path,
                display_name=field_name,
                summary=f"Object with {len(value)} fields",
                size_bytes=len(json.dumps(value)),
                is_large=True
            )
        elif isinstance(value, list):
            return UnfoldableField(
                path=path,
                display_name=field_name,
                summary=f"Array with {len(value)} items",
                item_count=len(value),
                is_large=True
            )
        elif isinstance(value, str):
            return UnfoldableField(
                path=path,
                display_name=field_name,
                summary=value[:100] + "..." if len(value) > 100 else value,
                size_bytes=len(value),
                is_large=True
            )
        else:
            return UnfoldableField(
                path=path,
                display_name=field_name,
                summary=str(value)[:100]
            )
    
    def fold(self, context: UnfoldContext) -> Dict[str, Any]:
        """
        Fold document based on context
        """
        if context.level == UnfoldLevel.DEEP:
            # Return full document
            return self.content
        
        # Create folded version
        folded = self._fold_recursive(self.content, "", 0, context)
        
        # Add metadata
        if self.metadata:
            folded["@metadata"] = self.metadata
            
        return folded
    
    def _fold_recursive(
        self,
        obj: Any,
        path: str,
        depth: int,
        context: UnfoldContext
    ) -> Any:
        """Recursively fold object based on context"""
        if depth > context.max_depth:
            return {"@truncated": True, "reason": "max_depth_exceeded"}
        
        # Check if this path should be unfolded
        should_unfold = (
            context.level == UnfoldLevel.DEEP or
            path in context.paths or
            (context.level == UnfoldLevel.SHALLOW and depth <= 1)
        )
        
        if isinstance(obj, dict):
            # Check if this is an unfoldable field
            if path in self._unfoldable_fields and not should_unfold:
                return self._unfoldable_fields[path].to_placeholder()
            
            # Process nested object
            result = {}
            for key, value in obj.items():
                if key.startswith("@"):
                    result[key] = value
                    continue
                    
                new_path = f"{path}.{key}" if path else key
                result[key] = self._fold_recursive(value, new_path, depth + 1, context)
                
            return result
            
        elif isinstance(obj, list):
            # Check if this is a large array that should be folded
            if path in self._unfoldable_fields and not should_unfold:
                return self._unfoldable_fields[path].to_placeholder()
            
            # Handle array truncation
            if len(obj) > context.array_threshold and not should_unfold:
                return {
                    "@unfoldable": True,
                    "path": path,
                    "summary": f"Array with {len(obj)} items",
                    "preview": obj[:10],
                    "total_count": len(obj)
                }
            
            # Process array items
            return [
                self._fold_recursive(item, f"{path}[{i}]", depth + 1, context)
                for i, item in enumerate(obj)
            ]
            
        else:
            # Primitive values are returned as-is
            return obj
    
    def unfold_path(self, path: str) -> Any:
        """
        Unfold a specific path in the document
        """
        parts = path.split(".")
        current = self.content
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                # Handle array indices
                if part.startswith("[") and part.endswith("]"):
                    index = int(part[1:-1])
                    if 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None
            else:
                return None
                
        return current
    
    def get_unfoldable_paths(self) -> List[Dict[str, Any]]:
        """Get list of all unfoldable paths in the document"""
        paths = []
        
        for path, field_info in self._unfoldable_fields.items():
            paths.append({
                "path": path,
                "display_name": field_info.display_name,
                "summary": field_info.summary,
                "size_bytes": field_info.size_bytes,
                "item_count": field_info.item_count,
                "is_large": field_info.is_large
            })
            
        return sorted(paths, key=lambda x: x["path"])


class UnfoldableProcessor:
    """
    Processes documents with @unfoldable annotations
    """
    
    @staticmethod
    def prepare_document(
        content: Dict[str, Any],
        unfoldable_paths: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Prepare a document with @unfoldable annotations
        """
        if not unfoldable_paths:
            return content
            
        prepared = json.loads(json.dumps(content))  # Deep copy
        
        for path in unfoldable_paths:
            parts = path.split(".")
            current = prepared
            
            # Navigate to parent
            for i, part in enumerate(parts[:-1]):
                if part not in current:
                    current[part] = {}
                current = current[part]
            
            # Mark field as unfoldable
            field_name = parts[-1]
            if field_name in current:
                value = current[field_name]
                current[field_name] = {
                    "@unfoldable": True,
                    "@display_name": field_name,
                    "@content": value
                }
        
        return prepared
    
    @staticmethod
    def extract_unfoldable_content(
        document: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Extract unfoldable content from a document
        
        Returns:
            (main_document, unfoldable_content)
        """
        main_doc = {}
        unfoldable_content = {}
        
        def process_object(src: Any, dst_main: Any, dst_unfold: Any, path: str = ""):
            if isinstance(src, dict):
                if "@unfoldable" in src and src["@unfoldable"] is True:
                    # Extract unfoldable content
                    content = src.get("@content", {})
                    unfoldable_content[path] = content
                    
                    # Leave placeholder in main document
                    return {
                        "@unfoldable": True,
                        "path": path,
                        "display_name": src.get("@display_name", path.split(".")[-1])
                    }
                else:
                    # Process nested object
                    result = {}
                    for key, value in src.items():
                        new_path = f"{path}.{key}" if path else key
                        result[key] = process_object(value, None, None, new_path)
                    return result
            else:
                return src
        
        main_doc = process_object(document, main_doc, unfoldable_content)
        
        return main_doc, unfoldable_content