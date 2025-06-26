"""
Schema Registry for OMS
Provides centralized schema management
"""

from typing import Dict, List, Any, Optional
from models.semantic_types import SemanticType

class SchemaRegistry:
    """Central registry for schema components"""
    
    def __init__(self):
        self._semantic_types: Dict[str, SemanticType] = {}
        self._schemas: Dict[str, Any] = {}
    
    def register_semantic_type(self, semantic_type: SemanticType) -> None:
        """Register a semantic type"""
        self._semantic_types[semantic_type.id] = semantic_type
    
    def get_semantic_type(self, type_id: str) -> Optional[SemanticType]:
        """Get semantic type by ID"""
        return self._semantic_types.get(type_id)
    
    def list_semantic_types(self) -> List[SemanticType]:
        """List all semantic types"""
        return list(self._semantic_types.values())
    
    async def list_object_types(self) -> List[Any]:
        """List all object types"""
        return []  # Mock implementation
    
    async def list_link_types(self) -> List[Any]:
        """List all link types"""
        return []  # Mock implementation
    
    async def get_object_type(self, type_id: str) -> Optional[Any]:
        """Get object type by ID"""
        return None  # Mock implementation
    
    def generate_schema(self, schema_type: str = "jsonschema") -> Dict[str, Any]:
        """Generate schema in specified format"""
        if schema_type == "jsonschema":
            return {
                "type": "object",
                "properties": {},
                "semantic_types": [st.model_dump() for st in self._semantic_types.values()]
            }
        return {}

# Global registry instance
schema_registry = SchemaRegistry()