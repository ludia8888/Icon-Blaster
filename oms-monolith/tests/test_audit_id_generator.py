"""
Tests for Audit ID Generator
Validates structured audit ID generation and parsing
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from utils.audit_id_generator import AuditIDGenerator, AuditIDPatterns
from models.audit_events import AuditAction, ResourceType


class TestAuditIDGenerator:
    """Test the structured audit ID generator"""
    
    def test_generate_basic_id(self):
        """Test basic ID generation"""
        audit_id = AuditIDGenerator.generate(
            action=AuditAction.OBJECT_TYPE_CREATE,
            resource_type=ResourceType.OBJECT_TYPE,
            resource_id="User"
        )
        
        assert audit_id.startswith("audit-oms:")
        assert ":object_type:user:create:" in audit_id
        assert "Z:" in audit_id  # Timestamp contains Z
        
        # Check total structure
        parts = audit_id.split(":")
        assert len(parts) == 6
        assert parts[0] == "audit-oms"
        assert parts[1] == "object_type"
        assert parts[2] == "user"
        assert parts[3] == "create"
        # parts[4] is timestamp
        # parts[5] is UUID
    
    def test_generate_with_custom_timestamp(self):
        """Test ID generation with custom timestamp"""
        custom_time = datetime(2025, 6, 26, 10, 0, 0, tzinfo=timezone.utc)
        
        audit_id = AuditIDGenerator.generate(
            action=AuditAction.BRANCH_MERGE,
            resource_type=ResourceType.BRANCH,
            resource_id="feature-x",
            timestamp=custom_time
        )
        
        assert "20250626T100000Z" in audit_id
    
    def test_generate_with_custom_uuid(self):
        """Test ID generation with custom UUID"""
        custom_uuid = "550e8400-e29b-41d4-a716-446655440000"
        
        audit_id = AuditIDGenerator.generate(
            action=AuditAction.PROPOSAL_APPROVE,
            resource_type=ResourceType.PROPOSAL,
            resource_id="proposal-123",
            custom_uuid=custom_uuid
        )
        
        assert audit_id.endswith(f":{custom_uuid}")
    
    def test_clean_resource_id(self):
        """Test resource ID cleaning"""
        # Test special characters
        audit_id = AuditIDGenerator.generate(
            action=AuditAction.OBJECT_TYPE_CREATE,
            resource_type=ResourceType.OBJECT_TYPE,
            resource_id="User@Domain.com"
        )
        
        assert ":user_domain_com:" in audit_id
        
        # Test long ID
        long_id = "a" * 60  # 60 characters
        audit_id = AuditIDGenerator.generate(
            action=AuditAction.OBJECT_TYPE_CREATE,
            resource_type=ResourceType.OBJECT_TYPE,
            resource_id=long_id
        )
        
        # Should be truncated to 50 chars with "..."
        parts = audit_id.split(":")
        assert len(parts[2]) == 50
        assert parts[2].endswith("...")
    
    def test_parse_valid_id(self):
        """Test parsing a valid audit ID"""
        original_time = datetime(2025, 6, 26, 10, 0, 0, tzinfo=timezone.utc)
        original_uuid = "550e8400-e29b-41d4-a716-446655440000"
        
        audit_id = AuditIDGenerator.generate(
            action=AuditAction.LINK_TYPE_UPDATE,
            resource_type=ResourceType.LINK_TYPE,
            resource_id="contains",
            timestamp=original_time,
            custom_uuid=original_uuid
        )
        
        parsed = AuditIDGenerator.parse(audit_id)
        
        assert parsed["service"] == "oms"
        assert parsed["resource_type"] == "link_type"
        assert parsed["resource_id"] == "contains"
        assert parsed["action"] == "update"
        assert parsed["timestamp"] == original_time
        assert parsed["uuid"] == original_uuid
        assert parsed["full_id"] == audit_id
    
    def test_parse_invalid_id(self):
        """Test parsing invalid audit IDs"""
        invalid_ids = [
            "not-an-audit-id",
            "audit-oms:too:few:parts",
            "audit-oms:too:many:parts:here:now:extra",
            "audit-oms:valid:id:but:invaliddate:uuid"
        ]
        
        for invalid_id in invalid_ids:
            parsed = AuditIDGenerator.parse(invalid_id)
            assert parsed == {}
    
    def test_generate_search_pattern(self):
        """Test search pattern generation"""
        # All object type operations
        pattern = AuditIDGenerator.generate_search_pattern(
            resource_type="object_type"
        )
        assert pattern == "audit-oms:object_type:*:*:*:*"
        
        # All create operations
        pattern = AuditIDGenerator.generate_search_pattern(
            action="create"
        )
        assert pattern == "audit-oms:*:*:create:*:*"
        
        # Specific day
        pattern = AuditIDGenerator.generate_search_pattern(
            date_prefix="20250626"
        )
        assert pattern == "audit-oms:*:*:*:20250626*:*"
        
        # Combined filters
        pattern = AuditIDGenerator.generate_search_pattern(
            resource_type="proposal",
            action="approve",
            date_prefix="20250626"
        )
        assert pattern == "audit-oms:proposal:*:approve:20250626*:*"
    
    def test_anomaly_detection_keys(self):
        """Test anomaly detection key generation"""
        audit_id = "audit-oms:object_type:user:create:20250626T100000Z:550e8400-e29b-41d4-a716-446655440000"
        
        keys = AuditIDGenerator.get_anomaly_detection_keys(audit_id)
        
        expected_keys = [
            "object_type:create",
            "object_type:*",
            "*:create",
            "object_type:create:20250626T10",
            "object_type:create:20250626",
            "object_type:user:create"
        ]
        
        for expected_key in expected_keys:
            assert expected_key in keys


class TestAuditIDPatterns:
    """Test common audit ID patterns"""
    
    def test_pattern_methods(self):
        """Test pattern generation methods"""
        # Test all methods return valid patterns
        patterns = [
            AuditIDPatterns.all_object_type_operations(),
            AuditIDPatterns.all_create_operations(),
            AuditIDPatterns.today_operations()
        ]
        
        for pattern in patterns:
            assert pattern.startswith("audit-oms:")
            assert pattern.count(":") == 5
        
        # Test high-risk operations return list
        high_risk = AuditIDPatterns.high_risk_operations()
        assert isinstance(high_risk, list)
        assert len(high_risk) > 0
        
        # Test admin operations return list
        admin_ops = AuditIDPatterns.admin_operations()
        assert isinstance(admin_ops, list)
        assert len(admin_ops) > 0


class TestAuditIDIntegration:
    """Test integration with audit events"""
    
    def test_id_generation_in_audit_event(self):
        """Test that audit events use structured IDs"""
        from models.audit_events import AuditEventV1, ActorInfo, TargetInfo
        
        actor = ActorInfo(id="user123", username="testuser")
        target = TargetInfo(
            resource_type=ResourceType.OBJECT_TYPE,
            resource_id="TestType"
        )
        
        event = AuditEventV1(
            action=AuditAction.OBJECT_TYPE_CREATE,
            actor=actor,
            target=target
        )
        
        cloudevent = event.to_cloudevent()
        audit_id = cloudevent["id"]
        
        # Should be structured ID
        assert audit_id.startswith("audit-oms:")
        assert ":object_type:testtype:create:" in audit_id
        
        # Should be parseable
        parsed = AuditIDGenerator.parse(audit_id)
        assert parsed["resource_type"] == "object_type"
        assert parsed["action"] == "create"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])