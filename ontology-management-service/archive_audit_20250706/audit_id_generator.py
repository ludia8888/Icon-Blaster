"""
Audit Log ID Generator
Structured audit event ID generation for better searchability and anomaly detection
"""
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from models.audit_events import AuditAction, ResourceType


class AuditIDGenerator:
    """
    Generates structured audit IDs following the pattern:
    audit-{service}:{resource_type}:{resource_id}:{action}:{timestamp}:{uuid}
    
    Example:
    "audit-oms:object_type:User:create:20250626T100000Z:550e8400-e29b-41d4-a716-446655440000"
    
    Benefits:
    - Easy log searching by resource type/action
    - Chronological ordering
    - Anomaly detection patterns
    - Compliance audit trails
    """
    
    SERVICE_NAME = "oms"
    
    @classmethod
    def generate(
        cls,
        action: AuditAction,
        resource_type: ResourceType,
        resource_id: str,
        timestamp: Optional[datetime] = None,
        custom_uuid: Optional[str] = None
    ) -> str:
        """
        Generate structured audit ID
        
        Args:
            action: Audit action performed
            resource_type: Type of resource
            resource_id: ID of the resource
            timestamp: When the action occurred (defaults to now)
            custom_uuid: Custom UUID (defaults to generated)
            
        Returns:
            Structured audit ID string
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        if custom_uuid is None:
            custom_uuid = str(uuid4())
        
        # Clean resource_id (remove special characters, limit length)
        clean_resource_id = cls._clean_resource_id(resource_id)
        
        # Format timestamp as ISO with 'T' and 'Z'
        timestamp_str = timestamp.strftime("%Y%m%dT%H%M%SZ")
        
        # Extract action name without prefix
        action_name = action.value.split('.')[-1]  # e.g., "object_type.create" -> "create"
        
        # Build structured ID
        audit_id = f"audit-{cls.SERVICE_NAME}:{resource_type.value}:{clean_resource_id}:{action_name}:{timestamp_str}:{custom_uuid}"
        
        return audit_id
    
    @classmethod
    def _clean_resource_id(cls, resource_id: str) -> str:
        """
        Clean resource ID for use in audit ID
        - Remove special characters
        - Limit length
        - Convert to lowercase
        """
        # Replace special characters with underscores
        cleaned = re.sub(r'[^a-zA-Z0-9_-]', '_', resource_id)
        
        # Limit length to 50 characters
        if len(cleaned) > 50:
            cleaned = cleaned[:47] + "..."
        
        return cleaned.lower()
    
    @classmethod
    def parse(cls, audit_id: str) -> dict:
        """
        Parse structured audit ID back into components
        
        Returns:
            Dictionary with components or empty dict if invalid
        """
        try:
            if not audit_id.startswith("audit-"):
                return {}
            
            # Remove prefix and split
            parts = audit_id[6:].split(":")  # Remove "audit-"
            
            if len(parts) != 6:
                return {}
            
            service, resource_type, resource_id, action, timestamp_str, uuid_part = parts
            
            # Parse timestamp
            timestamp = datetime.strptime(timestamp_str, "%Y%m%dT%H%M%SZ")
            timestamp = timestamp.replace(tzinfo=timezone.utc)
            
            return {
                "service": service,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
                "timestamp": timestamp,
                "uuid": uuid_part,
                "full_id": audit_id
            }
            
        except (ValueError, IndexError):
            return {}
    
    @classmethod
    def generate_search_pattern(
        cls,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        date_prefix: Optional[str] = None
    ) -> str:
        """
        Generate search pattern for audit logs
        
        Args:
            resource_type: Filter by resource type
            action: Filter by action
            date_prefix: Date prefix (e.g., "20250626" for specific day)
            
        Returns:
            Search pattern for log systems
        """
        pattern_parts = ["audit", cls.SERVICE_NAME]
        
        if resource_type:
            pattern_parts.append(resource_type)
        else:
            pattern_parts.append("*")
        
        pattern_parts.append("*")  # resource_id (always wildcard for search)
        
        if action:
            pattern_parts.append(action)
        else:
            pattern_parts.append("*")
        
        if date_prefix:
            pattern_parts.append(f"{date_prefix}*")
        else:
            pattern_parts.append("*")
        
        pattern_parts.append("*")  # UUID (always wildcard)
        
        return ":".join(pattern_parts)
    
    @classmethod
    def get_anomaly_detection_keys(cls, audit_id: str) -> list:
        """
        Generate keys for anomaly detection systems
        
        Returns:
            List of keys that can be used for pattern analysis
        """
        parsed = cls.parse(audit_id)
        if not parsed:
            return []
        
        keys = []
        
        # Basic patterns
        keys.append(f"{parsed['resource_type']}:{parsed['action']}")
        keys.append(f"{parsed['resource_type']}:*")
        keys.append(f"*:{parsed['action']}")
        
        # Time-based patterns
        hour = parsed['timestamp'].strftime("%Y%m%dT%H")
        day = parsed['timestamp'].strftime("%Y%m%d")
        
        keys.append(f"{parsed['resource_type']}:{parsed['action']}:{hour}")
        keys.append(f"{parsed['resource_type']}:{parsed['action']}:{day}")
        
        # Resource-specific patterns
        keys.append(f"{parsed['resource_type']}:{parsed['resource_id']}:{parsed['action']}")
        
        return keys


class AuditIDPatterns:
    """
    Common audit ID patterns for searching and monitoring
    """
    
    @staticmethod
    def all_object_type_operations() -> str:
        """Pattern for all object type operations"""
        return AuditIDGenerator.generate_search_pattern(resource_type="object_type")
    
    @staticmethod
    def all_create_operations() -> str:
        """Pattern for all create operations"""
        return AuditIDGenerator.generate_search_pattern(action="create")
    
    @staticmethod
    def today_operations() -> str:
        """Pattern for today's operations"""
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        return AuditIDGenerator.generate_search_pattern(date_prefix=today)
    
    @staticmethod
    def high_risk_operations() -> list:
        """Patterns for high-risk operations that need monitoring"""
        return [
            AuditIDGenerator.generate_search_pattern(action="delete"),
            AuditIDGenerator.generate_search_pattern(resource_type="schema", action="revert"),
            AuditIDGenerator.generate_search_pattern(resource_type="branch", action="merge"),
            AuditIDGenerator.generate_search_pattern(resource_type="proposal", action="approve"),
        ]
    
    @staticmethod
    def admin_operations() -> list:
        """Patterns for admin-level operations"""
        return [
            AuditIDGenerator.generate_search_pattern(resource_type="acl"),
            AuditIDGenerator.generate_search_pattern(action="admin"),
            AuditIDGenerator.generate_search_pattern(resource_type="system"),
        ]


# Usage examples and tests
if __name__ == "__main__":
    from models.audit_events import AuditAction, ResourceType
    
    # Generate audit IDs
    audit_id = AuditIDGenerator.generate(
        action=AuditAction.OBJECT_TYPE_CREATE,
        resource_type=ResourceType.OBJECT_TYPE,
        resource_id="User"
    )
    print(f"Generated ID: {audit_id}")
    
    # Parse audit ID
    parsed = AuditIDGenerator.parse(audit_id)
    print(f"Parsed: {parsed}")
    
    # Generate search patterns
    print(f"All object type ops: {AuditIDPatterns.all_object_type_operations()}")
    print(f"All create ops: {AuditIDPatterns.all_create_operations()}")
    print(f"Today's ops: {AuditIDPatterns.today_operations()}")
    
    # Anomaly detection keys
    keys = AuditIDGenerator.get_anomaly_detection_keys(audit_id)
    print(f"Anomaly detection keys: {keys}")