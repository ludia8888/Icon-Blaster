"""Unit tests for domain models."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from models.domain import ObjectType, Property, Status, TypeClass, Cardinality


class TestObjectType:
    """Test suite for ObjectType model."""
    
    def test_object_type_creation(self):
        """Test creating a valid ObjectType."""
        obj_type = ObjectType(
            id="obj-1",
            type_id="User",
            domain="test",
            name="User",
            description="Test user type"
        )
        
        assert obj_type.id == "obj-1"
        assert obj_type.type_id == "User"
        assert obj_type.domain == "test"
        assert obj_type.name == "User"
        assert obj_type.description == "Test user type"
    
    def test_object_type_with_status(self):
        """Test ObjectType with status."""
        obj_type = ObjectType(
            id="obj-1",
            type_id="User",
            domain="test",
            name="User",
            status=Status.ACTIVE
        )
        
        assert obj_type.status == Status.ACTIVE
    
    def test_object_type_with_properties(self):
        """Test ObjectType with properties."""
        properties = [
            Property(
                id="prop-1",
                property_id="name",
                object_type_id="User",
                name="Name",
                data_type="string"
            )
        ]
        
        obj_type = ObjectType(
            id="obj-1",
            type_id="User",
            domain="test",
            name="User",
            properties=properties
        )
        
        assert len(obj_type.properties) == 1
        assert obj_type.properties[0].property_id == "name"
    
    def test_object_type_validation_error(self):
        """Test ObjectType validation errors."""
        with pytest.raises(ValidationError):
            ObjectType(
                # Missing required fields
                domain="test"
            )
    
    def test_object_type_serialization(self):
        """Test ObjectType serialization."""
        obj_type = ObjectType(
            id="obj-1",
            type_id="User",
            domain="test",
            name="User",
            description="Test user type"
        )
        
        data = obj_type.model_dump()
        assert data["id"] == "obj-1"
        assert data["type_id"] == "User"
        assert data["domain"] == "test"
        assert data["name"] == "User"


class TestProperty:
    """Test suite for Property model."""
    
    def test_property_creation(self):
        """Test creating a valid Property."""
        prop = Property(
            id="prop-1",
            property_id="name",
            object_type_id="User",
            name="Name",
            data_type="string"
        )
        
        assert prop.id == "prop-1"
        assert prop.property_id == "name"
        assert prop.object_type_id == "User"
        assert prop.name == "Name"
        assert prop.data_type == "string"
    
    def test_property_with_required_flag(self):
        """Test Property with required flag."""
        prop = Property(
            id="prop-1",
            property_id="email",
            object_type_id="User",
            name="Email",
            data_type="string",
            is_required=True
        )
        
        assert prop.is_required is True
    
    def test_property_with_default_value(self):
        """Test Property with default value."""
        prop = Property(
            id="prop-1",
            property_id="status",
            object_type_id="User",
            name="Status",
            data_type="string",
            default_value="active"
        )
        
        assert prop.default_value == "active"
    
    def test_property_validation_error(self):
        """Test Property validation errors."""
        with pytest.raises(ValidationError):
            Property(
                # Missing required fields
                name="Name"
            )
    
    def test_property_with_constraints(self):
        """Test Property with constraints."""
        prop = Property(
            id="prop-1",
            property_id="age",
            object_type_id="User",
            name="Age",
            data_type="integer",
            min_value=0,
            max_value=150
        )
        
        assert prop.min_value == 0
        assert prop.max_value == 150


class TestEnums:
    """Test suite for enum values."""
    
    def test_status_enum(self):
        """Test Status enum values."""
        assert Status.ACTIVE == "active"
        assert Status.INACTIVE == "inactive"
        assert Status.DEPRECATED == "deprecated"
    
    def test_type_class_enum(self):
        """Test TypeClass enum values."""
        # Test that enum exists and has values
        assert hasattr(TypeClass, '__members__')
        assert len(TypeClass.__members__) > 0
    
    def test_cardinality_enum(self):
        """Test Cardinality enum values."""
        # Test that enum exists and has values
        assert hasattr(Cardinality, '__members__')
        assert len(Cardinality.__members__) > 0


class TestModelValidation:
    """Test suite for model validation."""
    
    def test_object_type_name_validation(self):
        """Test ObjectType name validation."""
        # Valid names should work
        valid_names = ["User", "UserAccount", "ProductItem"]
        for name in valid_names:
            obj_type = ObjectType(
                id="obj-1",
                type_id=name,
                domain="test",
                name=name
            )
            assert obj_type.name == name
    
    def test_property_data_type_validation(self):
        """Test Property data type validation."""
        valid_types = ["string", "integer", "boolean", "date", "datetime"]
        
        for data_type in valid_types:
            prop = Property(
                id="prop-1",
                property_id="test_prop",
                object_type_id="User",
                name="Test Property",
                data_type=data_type
            )
            assert prop.data_type == data_type
    
    def test_model_equality(self):
        """Test model equality comparison."""
        obj1 = ObjectType(
            id="obj-1",
            type_id="User",
            domain="test",
            name="User"
        )
        
        obj2 = ObjectType(
            id="obj-1",
            type_id="User",
            domain="test",
            name="User"
        )
        
        obj3 = ObjectType(
            id="obj-2",
            type_id="User",
            domain="test",
            name="User"
        )
        
        assert obj1 == obj2
        assert obj1 != obj3
    
    def test_model_repr(self):
        """Test model string representation."""
        obj_type = ObjectType(
            id="obj-1",
            type_id="User",
            domain="test",
            name="User"
        )
        
        repr_str = repr(obj_type)
        assert "User" in repr_str
        assert "obj-1" in repr_str