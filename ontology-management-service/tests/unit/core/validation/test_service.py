"""Unit tests for validation service."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from core.validation.service import ValidationService
from core.validation.models import ValidationResult, BreakingChange
from models.domain import ObjectType, Property, Status


class TestValidationService:
    """Test suite for ValidationService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = ValidationService()
    
    def test_validation_service_creation(self):
        """Test creating ValidationService instance."""
        service = ValidationService()
        assert service is not None
        assert hasattr(service, 'validate')
        assert hasattr(service, 'validate_schema')
    
    @pytest.mark.asyncio
    async def test_validate_object_type_valid(self):
        """Test validating a valid object type."""
        object_type = ObjectType(
            id="test-obj-1",
            type_id="User",
            domain="test",
            name="User",
            description="Test user type",
            status=Status.ACTIVE
        )
        
        result = await self.service.validate_object_type(object_type)
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_object_type_with_properties(self):
        """Test validating object type with properties."""
        properties = [
            Property(
                id="prop-1",
                property_id="name",
                object_type_id="User",
                name="Name",
                description="User name",
                data_type="string",
                is_required=True
            ),
            Property(
                id="prop-2",
                property_id="email",
                object_type_id="User",
                name="Email",
                description="User email",
                data_type="string",
                is_required=True
            )
        ]
        
        object_type = ObjectType(
            id="test-obj-1",
            type_id="User",
            domain="test",
            name="User",
            description="Test user type",
            status=Status.ACTIVE,
            properties=properties
        )
        
        result = await self.service.validate_object_type(object_type)
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_object_type_invalid_name(self):
        """Test validating object type with invalid name."""
        object_type = ObjectType(
            id="test-obj-1",
            type_id="",  # Empty type_id
            domain="test",
            name="User",
            description="Test user type",
            status=Status.ACTIVE
        )
        
        result = await self.service.validate_object_type(object_type)
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("type_id" in error.lower() for error in result.errors)
    
    @pytest.mark.asyncio
    async def test_validate_property_valid(self):
        """Test validating a valid property."""
        property_obj = Property(
            id="prop-1",
            property_id="name",
            object_type_id="User",
            name="Name",
            description="User name",
            data_type="string",
            is_required=True
        )
        
        result = await self.service.validate_property(property_obj)
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_property_invalid_data_type(self):
        """Test validating property with invalid data type."""
        property_obj = Property(
            id="prop-1",
            property_id="age",
            object_type_id="User",
            name="Age",
            description="User age",
            data_type="invalid_type",  # Invalid data type
            is_required=False
        )
        
        result = await self.service.validate_property(property_obj)
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("data_type" in error.lower() for error in result.errors)
    
    @pytest.mark.asyncio
    async def test_validate_schema_changes(self):
        """Test validating schema changes."""
        old_object_type = ObjectType(
            id="test-obj-1",
            type_id="User",
            domain="test",
            name="User",
            description="Test user type",
            status=Status.ACTIVE
        )
        
        new_object_type = ObjectType(
            id="test-obj-1",
            type_id="User",
            domain="test",
            name="User",
            description="Updated user type",  # Description changed
            status=Status.ACTIVE
        )
        
        result = await self.service.validate_schema_changes(
            old_schema=old_object_type,
            new_schema=new_object_type
        )
        
        assert isinstance(result, ValidationResult)
        # Description change should not be a breaking change
        assert result.is_valid is True
    
    @pytest.mark.asyncio
    async def test_detect_breaking_changes(self):
        """Test detecting breaking changes."""
        old_properties = [
            Property(
                id="prop-1",
                property_id="name",
                object_type_id="User",
                name="Name",
                data_type="string",
                is_required=True
            )
        ]
        
        new_properties = [
            Property(
                id="prop-1",
                property_id="name",
                object_type_id="User",
                name="Name",
                data_type="text",  # Data type changed
                is_required=True
            )
        ]
        
        old_object_type = ObjectType(
            id="test-obj-1",
            type_id="User",
            domain="test",
            name="User",
            properties=old_properties
        )
        
        new_object_type = ObjectType(
            id="test-obj-1",
            type_id="User",
            domain="test",
            name="User",
            properties=new_properties
        )
        
        breaking_changes = await self.service.detect_breaking_changes(
            old_schema=old_object_type,
            new_schema=new_object_type
        )
        
        assert len(breaking_changes) > 0
        assert isinstance(breaking_changes[0], BreakingChange)
    
    @pytest.mark.asyncio
    async def test_validate_naming_conventions(self):
        """Test validating naming conventions."""
        # Test valid naming
        assert await self.service.validate_naming_convention("User", "object_type") is True
        assert await self.service.validate_naming_convention("userName", "property") is True
        
        # Test invalid naming
        assert await self.service.validate_naming_convention("user", "object_type") is False
        assert await self.service.validate_naming_convention("User Name", "property") is False
    
    @pytest.mark.asyncio
    async def test_validate_domain_constraints(self):
        """Test validating domain-specific constraints."""
        object_type = ObjectType(
            id="test-obj-1",
            type_id="User",
            domain="test",
            name="User",
            description="Test user type",
            status=Status.ACTIVE
        )
        
        result = await self.service.validate_domain_constraints(object_type, "test")
        assert result.is_valid is True
    
    @pytest.mark.asyncio
    async def test_validation_context(self):
        """Test validation with context."""
        context = {
            "user_id": "user123",
            "tenant_id": "tenant456",
            "branch_id": "branch789"
        }
        
        object_type = ObjectType(
            id="test-obj-1",
            type_id="User",
            domain="test",
            name="User",
            description="Test user type",
            status=Status.ACTIVE
        )
        
        result = await self.service.validate_with_context(object_type, context)
        assert result.is_valid is True
    
    def test_validation_result_structure(self):
        """Test ValidationResult structure."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Minor issue"],
            breaking_changes=[]
        )
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 1
        assert result.warnings[0] == "Minor issue"
        assert len(result.breaking_changes) == 0
    
    def test_breaking_change_structure(self):
        """Test BreakingChange structure."""
        breaking_change = BreakingChange(
            type="property_type_change",
            description="Property data type changed from string to integer",
            impact="high",
            affected_objects=["User"],
            mitigation="Data migration required"
        )
        
        assert breaking_change.type == "property_type_change"
        assert breaking_change.impact == "high"
        assert "User" in breaking_change.affected_objects
        assert breaking_change.mitigation == "Data migration required"
    
    @pytest.mark.asyncio
    async def test_validate_circular_references(self):
        """Test validation of circular references."""
        # Create object types with potential circular reference
        user_type = ObjectType(
            id="user-1",
            type_id="User",
            domain="test",
            name="User"
        )
        
        group_type = ObjectType(
            id="group-1",
            type_id="Group",
            domain="test",
            name="Group"
        )
        
        # This would need actual relationship data
        result = await self.service.validate_circular_references([user_type, group_type])
        assert result.is_valid is True
    
    @pytest.mark.asyncio
    async def test_validate_batch_operations(self):
        """Test batch validation operations."""
        object_types = [
            ObjectType(
                id="user-1",
                type_id="User",
                domain="test",
                name="User"
            ),
            ObjectType(
                id="group-1",
                type_id="Group",
                domain="test",
                name="Group"
            )
        ]
        
        results = await self.service.validate_batch(object_types)
        assert len(results) == 2
        assert all(result.is_valid for result in results)
    
    @patch('core.validation.service.logger')
    @pytest.mark.asyncio
    async def test_validation_logging(self, mock_logger):
        """Test that validation operations are logged."""
        object_type = ObjectType(
            id="test-obj-1",
            type_id="User",
            domain="test",
            name="User",
            description="Test user type",
            status=Status.ACTIVE
        )
        
        await self.service.validate_object_type(object_type)
        
        # Should log validation activity
        mock_logger.info.assert_called()
    
    @pytest.mark.asyncio
    async def test_validation_performance(self):
        """Test validation performance with large schemas."""
        # Create a large number of properties
        properties = [
            Property(
                id=f"prop-{i}",
                property_id=f"property_{i}",
                object_type_id="User",
                name=f"Property {i}",
                data_type="string",
                is_required=False
            ) for i in range(100)
        ]
        
        object_type = ObjectType(
            id="test-obj-1",
            type_id="User",
            domain="test",
            name="User",
            properties=properties
        )
        
        import time
        start_time = time.time()
        result = await self.service.validate_object_type(object_type)
        end_time = time.time()
        
        # Should complete validation in reasonable time
        assert end_time - start_time < 1.0  # Less than 1 second
        assert result.is_valid is True