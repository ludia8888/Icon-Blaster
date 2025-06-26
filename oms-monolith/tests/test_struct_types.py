"""
Unit tests for Struct Types
Tests requirement FR-ST-STRUCT from Ontology_Requirements_Document.md
Includes validation for nested struct limitation per Foundry constraints
"""

import pytest
from datetime import datetime
from typing import Dict, Any

from models.struct_types import (
    StructType,
    StructFieldDefinition,
    StructTypeRegistry,
    PREDEFINED_STRUCT_TYPES
)


class TestStructFieldDefinition:
    """Test struct field definition"""
    
    def test_field_creation(self):
        """Test creating a struct field definition"""
        field = StructFieldDefinition(
            name="test_field",
            display_name="Test Field",
            data_type_id="string",
            is_required=True
        )
        
        assert field.name == "test_field"
        assert field.display_name == "Test Field"
        assert field.data_type_id == "string"
        assert field.is_required is True
        assert field.semantic_type_id is None
        
    def test_field_name_validation(self):
        """Test field name validation rules"""
        # Valid names
        valid_names = ["fieldName", "field_name", "field123", "_private"]
        for name in valid_names:
            field = StructFieldDefinition(
                name=name,
                display_name="Test",
                data_type_id="string"
            )
            assert field.name == name
        
        # Invalid names
        with pytest.raises(ValueError, match="must start with a letter"):
            StructFieldDefinition(
                name="123field",
                display_name="Test",
                data_type_id="string"
            )
        
        with pytest.raises(ValueError, match="can only contain"):
            StructFieldDefinition(
                name="field-name",
                display_name="Test",
                data_type_id="string"
            )


class TestStructType:
    """Test StructType model"""
    
    def test_struct_type_creation(self):
        """Test creating a struct type"""
        fields = [
            StructFieldDefinition(
                name="field1",
                display_name="Field 1",
                data_type_id="string",
                is_required=True
            ),
            StructFieldDefinition(
                name="field2",
                display_name="Field 2",
                data_type_id="integer",
                is_required=False
            )
        ]
        
        struct = StructType(
            id="test_struct",
            name="Test Struct",
            fields=fields,
            created_by="test_user"
        )
        
        assert struct.id == "test_struct"
        assert struct.name == "Test Struct"
        assert len(struct.fields) == 2
        assert struct.field_count == 2
        assert struct.required_fields == ["field1"]
        assert struct.is_active is True
        assert struct.is_system is False
        
    def test_duplicate_field_names(self):
        """Test that duplicate field names are not allowed"""
        fields = [
            StructFieldDefinition(
                name="duplicate",
                display_name="Field 1",
                data_type_id="string"
            ),
            StructFieldDefinition(
                name="duplicate",
                display_name="Field 2",
                data_type_id="integer"
            )
        ]
        
        with pytest.raises(ValueError, match="Duplicate field names"):
            StructType(
                id="test",
                name="Test",
                fields=fields,
                created_by="test"
            )
    
    def test_nested_struct_validation(self):
        """Test that nested structs are properly rejected"""
        # Direct struct reference
        fields = [
            StructFieldDefinition(
                name="normal_field",
                display_name="Normal Field",
                data_type_id="string"
            ),
            StructFieldDefinition(
                name="nested_struct",
                display_name="Nested Struct",
                data_type_id="struct:address"  # This should fail
            )
        ]
        
        with pytest.raises(ValueError) as exc_info:
            StructType(
                id="test",
                name="Test",
                fields=fields,
                created_by="test"
            )
        
        assert "Nested structs are not supported" in str(exc_info.value)
        assert "nested_struct" in str(exc_info.value)
        assert "Please flatten the structure" in str(exc_info.value)
    
    def test_value_validation(self):
        """Test validating values against struct type"""
        struct = StructType(
            id="test",
            name="Test",
            fields=[
                StructFieldDefinition(
                    name="required_field",
                    display_name="Required",
                    data_type_id="string",
                    is_required=True
                ),
                StructFieldDefinition(
                    name="optional_field",
                    display_name="Optional",
                    data_type_id="string",
                    is_required=False
                )
            ],
            created_by="test"
        )
        
        # Valid value
        is_valid, errors = struct.validate_value({
            "required_field": "test",
            "optional_field": "optional"
        })
        assert is_valid is True
        assert len(errors) == 0
        
        # Missing required field
        is_valid, errors = struct.validate_value({
            "optional_field": "optional"
        })
        assert is_valid is False
        assert any("required_field" in e for e in errors)
        
        # Unexpected field
        is_valid, errors = struct.validate_value({
            "required_field": "test",
            "unexpected": "value"
        })
        assert is_valid is False
        assert any("Unexpected fields" in e for e in errors)
        
        # Not a dictionary
        is_valid, errors = struct.validate_value("not a dict")
        assert is_valid is False
        assert any("must be a dictionary" in e for e in errors)
    
    def test_display_formatting(self):
        """Test display template formatting"""
        struct = StructType(
            id="name",
            name="Name",
            fields=[
                StructFieldDefinition(
                    name="first",
                    display_name="First Name",
                    data_type_id="string"
                ),
                StructFieldDefinition(
                    name="last",
                    display_name="Last Name",
                    data_type_id="string"
                )
            ],
            display_template="{first} {last}",
            created_by="test"
        )
        
        formatted = struct.format_display({
            "first": "John",
            "last": "Doe"
        })
        assert formatted == "John Doe"
        
        # Without template
        struct2 = StructType(
            id="test",
            name="Test",
            fields=[
                StructFieldDefinition(
                    name="a",
                    display_name="A",
                    data_type_id="integer"
                )
            ],
            created_by="test"
        )
        assert struct2.format_display({"a": 1}) == "{'a': 1}"
    
    def test_get_field(self):
        """Test getting field by name"""
        field1 = StructFieldDefinition(
            name="field1",
            display_name="Field 1",
            data_type_id="string"
        )
        field2 = StructFieldDefinition(
            name="field2",
            display_name="Field 2",
            data_type_id="integer"
        )
        
        struct = StructType(
            id="test",
            name="Test",
            fields=[field1, field2],
            created_by="test"
        )
        
        assert struct.get_field("field1") == field1
        assert struct.get_field("field2") == field2
        assert struct.get_field("nonexistent") is None
    
    def test_json_schema_generation(self):
        """Test JSON Schema generation"""
        struct = StructType(
            id="test",
            name="Test Struct",
            description="Test description",
            fields=[
                StructFieldDefinition(
                    name="string_field",
                    display_name="String Field",
                    data_type_id="string",
                    is_required=True
                ),
                StructFieldDefinition(
                    name="number_field",
                    display_name="Number Field",
                    data_type_id="integer",
                    is_required=False,
                    default_value=0
                )
            ],
            created_by="test"
        )
        
        schema = struct.to_json_schema()
        
        assert schema["type"] == "object"
        assert schema["title"] == "Test Struct"
        assert schema["description"] == "Test description"
        assert "string_field" in schema["properties"]
        assert "number_field" in schema["properties"]
        assert schema["required"] == ["string_field"]
        assert schema["additionalProperties"] is False
        assert schema["properties"]["number_field"]["default"] == 0


class TestPredefinedStructTypes:
    """Test predefined struct types"""
    
    def test_address_struct(self):
        """Test address struct type"""
        address = PREDEFINED_STRUCT_TYPES["address"]
        
        assert address.name == "Address"
        assert len(address.fields) == 6
        assert address.required_fields == ["street1", "city", "state", "postal_code", "country"]
        
        # Valid address
        valid_address = {
            "street1": "123 Main St",
            "city": "Anytown",
            "state": "CA",
            "postal_code": "12345",
            "country": "US"
        }
        is_valid, errors = address.validate_value(valid_address)
        assert is_valid is True
        
        # Test display formatting
        formatted = address.format_display(valid_address)
        assert formatted == "123 Main St, Anytown, CA 12345"
    
    def test_person_name_struct(self):
        """Test person name struct type"""
        name_struct = PREDEFINED_STRUCT_TYPES["person_name"]
        
        assert name_struct.name == "Person Name"
        assert len(name_struct.fields) == 4
        assert name_struct.required_fields == ["first_name", "last_name"]
        
        # Valid name
        valid_name = {
            "first_name": "John",
            "last_name": "Doe"
        }
        is_valid, errors = name_struct.validate_value(valid_name)
        assert is_valid is True
        
        # Test display formatting
        formatted = name_struct.format_display(valid_name)
        assert formatted == "John Doe"
    
    def test_time_range_struct(self):
        """Test time range struct type"""
        time_range = PREDEFINED_STRUCT_TYPES["time_range"]
        
        assert time_range.name == "Time Range"
        assert len(time_range.fields) == 3
        assert time_range.required_fields == ["start_time", "end_time"]
        
        # Check default timezone
        tz_field = time_range.get_field("timezone")
        assert tz_field.default_value == "UTC"


class TestStructTypeRegistry:
    """Test StructTypeRegistry functionality"""
    
    def test_registry_initialization(self):
        """Test registry loads predefined types"""
        registry = StructTypeRegistry()
        
        # Check predefined types are loaded
        assert registry.get("address") is not None
        assert registry.get("person_name") is not None
        assert registry.get("time_range") is not None
    
    def test_register_custom_type(self):
        """Test registering custom struct types"""
        registry = StructTypeRegistry()
        
        custom_struct = StructType(
            id="custom_struct",
            name="Custom Struct",
            fields=[
                StructFieldDefinition(
                    name="field1",
                    display_name="Field 1",
                    data_type_id="string"
                )
            ],
            created_by="test"
        )
        
        registry.register(custom_struct)
        assert registry.get("custom_struct") == custom_struct
    
    def test_cannot_override_system_types(self):
        """Test that system types cannot be overridden"""
        registry = StructTypeRegistry()
        
        # Try to override a system type
        address_override = StructType(
            id="address",
            name="Fake Address",
            fields=[
                StructFieldDefinition(
                    name="fake_field",
                    display_name="Fake",
                    data_type_id="string"
                )
            ],
            created_by="test"
        )
        
        with pytest.raises(ValueError, match="Cannot override system struct type"):
            registry.register(address_override)
    
    def test_nested_struct_prevention_in_registry(self):
        """Test that registry prevents nested struct registration"""
        registry = StructTypeRegistry()
        
        # First register a base struct
        base_struct = StructType(
            id="base",
            name="Base",
            fields=[
                StructFieldDefinition(
                    name="simple",
                    display_name="Simple",
                    data_type_id="string"
                )
            ],
            created_by="test"
        )
        registry.register(base_struct)
        
        # Try to register a struct that references the base struct
        nested_struct = StructType(
            id="nested",
            name="Nested",
            fields=[
                StructFieldDefinition(
                    name="nested_field",
                    display_name="Nested",
                    data_type_id="base"  # References existing struct
                )
            ],
            created_by="test"
        )
        
        with pytest.raises(ValueError) as exc_info:
            registry.register(nested_struct)
        
        assert "Nested structs are not supported" in str(exc_info.value)
        assert "nested_field" in str(exc_info.value)
    
    def test_list_all_types(self):
        """Test listing all types"""
        registry = StructTypeRegistry()
        
        all_types = registry.list_all()
        assert len(all_types) >= 3  # At least the predefined types
        
        # Check types are StructType instances
        for struct_type in all_types:
            assert isinstance(struct_type, StructType)
    
    def test_validate_through_registry(self):
        """Test validation through registry"""
        registry = StructTypeRegistry()
        
        # Valid address
        is_valid, errors = registry.validate_value("address", {
            "street1": "123 Main St",
            "city": "Anytown",
            "state": "CA",
            "postal_code": "12345",
            "country": "US"
        })
        assert is_valid is True
        
        # Invalid struct type
        is_valid, errors = registry.validate_value("nonexistent", {})
        assert is_valid is False
        assert "Unknown struct type" in errors[0]
    
    def test_exists_method(self):
        """Test checking if struct type exists"""
        registry = StructTypeRegistry()
        
        assert registry.exists("address") is True
        assert registry.exists("person_name") is True
        assert registry.exists("nonexistent") is False


class TestStructTypeIntegration:
    """Integration tests for struct types"""
    
    def test_struct_with_semantic_types(self):
        """Test struct fields with semantic types"""
        # Address struct has postal_code field with semantic type
        address = PREDEFINED_STRUCT_TYPES["address"]
        postal_field = address.get_field("postal_code")
        
        assert postal_field.semantic_type_id == "postal_code_us"
        
        # Country field also has semantic type
        country_field = address.get_field("country")
        assert country_field.semantic_type_id == "iso_country_code"
        assert country_field.default_value == "US"
    
    def test_struct_type_as_property_type(self):
        """Test struct type used as a property data type"""
        # This would test integration with Property model
        # Properties should be able to use "struct:address" as data_type_id
        pass  # Integration test would go here


if __name__ == "__main__":
    pytest.main([__file__, "-v"])