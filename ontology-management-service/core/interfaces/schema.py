"""Schema service protocol"""

from typing import Protocol, Dict, Any, List, Optional
from datetime import datetime

class SchemaServiceProtocol(Protocol):
    """Protocol for schema service implementations"""
    
    async def create_schema(self, name: str, schema_def: Dict[str, Any], 
                          created_by: str) -> Dict[str, Any]:
        """Create a new schema with versioning"""
        ...
    
    async def get_schema(self, schema_id: str) -> Dict[str, Any]:
        """Get schema by ID"""
        ...
    
    async def get_schema_by_name(self, name: str, branch: str) -> Optional[Dict[str, Any]]:
        """Get schema by name and branch"""
        ...
    
    async def update_schema(self, schema_id: str, name: Optional[str] = None,
                          schema_def: Optional[Dict[str, Any]] = None,
                          updated_by: Optional[str] = None) -> Dict[str, Any]:
        """Update existing schema"""
        ...
    
    async def delete_schema(self, schema_id: str, deleted_by: str) -> None:
        """Soft delete schema"""
        ...
    
    async def list_schemas(self, offset: int = 0, limit: int = 100,
                         filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """List schemas with pagination"""
        ...
    
    async def validate_schema(self, schema_def: Dict[str, Any]) -> Dict[str, Any]:
        """Validate schema definition"""
        ...
    
    async def get_schema_version(self, schema_id: str, version: int) -> Dict[str, Any]:
        """Get specific version of schema"""
        ...
    
    async def get_schema_versions(self, schema_id: str) -> List[Dict[str, Any]]:
        """Get all versions of a schema"""
        ...