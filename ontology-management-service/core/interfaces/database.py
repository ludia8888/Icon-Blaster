"""Database client protocol"""

from typing import Protocol, Any, Dict, List, Optional
from datetime import datetime

class DatabaseClientProtocol(Protocol):
    """Protocol for database client implementations"""
    
    async def connect(self) -> None:
        """Establish database connection"""
        ...
    
    async def close(self) -> None:
        """Close database connection"""
        ...
    
    async def create_schema(self, schema_data: Dict[str, Any]) -> str:
        """Create a new schema"""
        ...
    
    async def get_schema(self, schema_id: str) -> Dict[str, Any]:
        """Get schema by ID"""
        ...
    
    async def update_schema(self, schema_id: str, schema_data: Dict[str, Any]) -> None:
        """Update existing schema"""
        ...
    
    async def delete_schema(self, schema_id: str) -> None:
        """Delete schema"""
        ...
    
    async def list_schemas(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """List all schemas with optional filters"""
        ...
    
    async def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute raw database query"""
        ...