"""Validation service protocol"""

from typing import Protocol, Dict, Any, List

class ValidationServiceProtocol(Protocol):
    """Protocol for validation service implementations"""
    
    async def validate_data(self, data: Dict[str, Any], schema_id: str) -> Dict[str, Any]:
        """Validate data against a schema"""
        ...
    
    async def validate_schema_definition(self, schema_def: Dict[str, Any]) -> Dict[str, Any]:
        """Validate schema definition format"""
        ...
    
    async def get_validation_rules(self, schema_id: str) -> List[Dict[str, Any]]:
        """Get validation rules for a schema"""
        ...
    
    async def add_validation_rule(self, schema_id: str, rule: Dict[str, Any]) -> None:
        """Add custom validation rule"""
        ...
    
    async def remove_validation_rule(self, schema_id: str, rule_id: str) -> None:
        """Remove validation rule"""
        ...