"""
Unit tests for Semantic Types
Tests requirement FR-SM-VALID from Ontology_Requirements_Document.md
"""

import pytest
from datetime import datetime
from typing import Any, List

from models.semantic_types import (
    SemanticType,
    SemanticTypeCategory,
    ConstraintType,
    ValidationRule,
    SemanticTypeRegistry,
    PREDEFINED_SEMANTIC_TYPES
)


class TestValidationRule:
    """Test individual validation rules"""
    
    def test_pattern_validation(self):
        """Test regex pattern validation"""
        rule = ValidationRule(
            type=ConstraintType.PATTERN,
            value=r"^[A-Z]{3}-\d{4}$",
            error_message="Invalid format"
        )
        
        # Valid cases
        assert rule.validate_value("ABC-1234")[0] is True
        assert rule.validate_value("XYZ-9999")[0] is True
        
        # Invalid cases
        is_valid, error = rule.validate_value("abc-1234")
        assert is_valid is False
        assert "Invalid format" in error
        
        is_valid, error = rule.validate_value("ABC-12345")
        assert is_valid is False
        
    def test_min_max_value_validation(self):
        """Test numeric min/max validation"""
        min_rule = ValidationRule(
            type=ConstraintType.MIN_VALUE,
            value=0
        )
        max_rule = ValidationRule(
            type=ConstraintType.MAX_VALUE,
            value=100
        )
        
        # Test min
        assert min_rule.validate_value(0)[0] is True
        assert min_rule.validate_value(50)[0] is True
        assert min_rule.validate_value(-1)[0] is False
        
        # Test max
        assert max_rule.validate_value(100)[0] is True
        assert max_rule.validate_value(50)[0] is True
        assert max_rule.validate_value(101)[0] is False
        
    def test_string_length_validation(self):
        """Test string length constraints"""
        min_len = ValidationRule(
            type=ConstraintType.MIN_LENGTH,
            value=5
        )
        max_len = ValidationRule(
            type=ConstraintType.MAX_LENGTH,
            value=10
        )
        
        # Test min length
        assert min_len.validate_value("12345")[0] is True
        assert min_len.validate_value("1234")[0] is False
        
        # Test max length
        assert max_len.validate_value("1234567890")[0] is True
        assert max_len.validate_value("12345678901")[0] is False
        
    def test_enum_validation(self):
        """Test enumerated value validation"""
        rule = ValidationRule(
            type=ConstraintType.ENUM,
            value=["RED", "GREEN", "BLUE"]
        )
        
        assert rule.validate_value("RED")[0] is True
        assert rule.validate_value("GREEN")[0] is True
        assert rule.validate_value("YELLOW")[0] is False
        
    def test_validation_error_handling(self):
        """Test error handling in validation"""
        rule = ValidationRule(
            type=ConstraintType.MIN_VALUE,
            value="not_a_number"  # This will cause an error
        )
        
        is_valid, error = rule.validate_value("test")
        assert is_valid is False
        assert "Validation error" in error


class TestSemanticType:
    """Test SemanticType model"""
    
    def test_semantic_type_creation(self):
        """Test creating a semantic type"""
        st = SemanticType(
            id="test_type",
            name="Test Type",
            category=SemanticTypeCategory.CUSTOM,
            base_type_id="string",
            created_by="test_user"
        )
        
        assert st.id == "test_type"
        assert st.name == "Test Type"
        assert st.category == SemanticTypeCategory.CUSTOM
        assert st.is_active is True
        assert st.is_system is False
        
    def test_semantic_type_validation(self):
        """Test validating values against semantic type"""
        st = SemanticType(
            id="age",
            name="Age",
            category=SemanticTypeCategory.MEASUREMENT,
            base_type_id="integer",
            validation_rules=[
                ValidationRule(type=ConstraintType.MIN_VALUE, value=0),
                ValidationRule(type=ConstraintType.MAX_VALUE, value=150)
            ],
            created_by="test"
        )
        
        # Valid values
        is_valid, errors = st.validate(25)
        assert is_valid is True
        assert len(errors) == 0
        
        # Invalid values
        is_valid, errors = st.validate(-5)
        assert is_valid is False
        assert len(errors) == 1
        
        is_valid, errors = st.validate(200)
        assert is_valid is False
        assert len(errors) == 1
        
    def test_multiple_validation_failures(self):
        """Test multiple validation rules failing"""
        st = SemanticType(
            id="test",
            name="Test",
            category=SemanticTypeCategory.CUSTOM,
            base_type_id="string",
            validation_rules=[
                ValidationRule(type=ConstraintType.MIN_LENGTH, value=5),
                ValidationRule(type=ConstraintType.MAX_LENGTH, value=10),
                ValidationRule(type=ConstraintType.PATTERN, value=r"^[A-Z].*")
            ],
            created_by="test"
        )
        
        # Fails all rules
        is_valid, errors = st.validate("abc")
        assert is_valid is False
        assert len(errors) == 2  # Too short and wrong pattern
        
    def test_display_formatting(self):
        """Test display format functionality"""
        st = SemanticType(
            id="currency",
            name="Currency",
            category=SemanticTypeCategory.FINANCIAL,
            base_type_id="decimal",
            display_format="${value}",
            created_by="test"
        )
        
        assert st.format_display(100.50) == "$100.5"
        assert st.format_display(0) == "$0"
        
        # Test without format
        st2 = SemanticType(
            id="plain",
            name="Plain",
            category=SemanticTypeCategory.TEXT,
            base_type_id="string",
            created_by="test"
        )
        assert st2.format_display("test") == "test"


class TestPredefinedTypes:
    """Test predefined semantic types"""
    
    def test_email_validation(self):
        """Test email address semantic type"""
        email_type = PREDEFINED_SEMANTIC_TYPES["email_address"]
        
        # Valid emails
        assert email_type.validate("user@example.com")[0] is True
        assert email_type.validate("john.doe+tag@company.org")[0] is True
        
        # Invalid emails
        assert email_type.validate("not-an-email")[0] is False
        assert email_type.validate("@example.com")[0] is False
        assert email_type.validate("user@")[0] is False
        
    def test_url_validation(self):
        """Test URL semantic type"""
        url_type = PREDEFINED_SEMANTIC_TYPES["url"]
        
        # Valid URLs
        assert url_type.validate("https://example.com")[0] is True
        assert url_type.validate("http://localhost:8080/path")[0] is True
        
        # Invalid URLs
        assert url_type.validate("not-a-url")[0] is False
        assert url_type.validate("ftp://example.com")[0] is False
        
    def test_phone_number_validation(self):
        """Test phone number semantic type"""
        phone_type = PREDEFINED_SEMANTIC_TYPES["phone_number"]
        
        # Valid phone numbers (E.164 format)
        assert phone_type.validate("+1234567890")[0] is True
        assert phone_type.validate("+442071234567")[0] is True
        
        # Invalid phone numbers
        assert phone_type.validate("123-456-7890")[0] is False
        assert phone_type.validate("not-a-phone")[0] is False
        
    def test_currency_validation(self):
        """Test currency semantic type"""
        currency_type = PREDEFINED_SEMANTIC_TYPES["currency_usd"]
        
        # Valid amounts
        assert currency_type.validate(100.00)[0] is True
        assert currency_type.validate(0)[0] is True
        
        # Invalid amounts
        assert currency_type.validate(-10)[0] is False
        assert currency_type.validate(1000000000)[0] is False
        
        # Test formatting (with comma separator)
        assert currency_type.format_display(1234.56) == "$1,234.56"
        
    def test_postal_code_validation(self):
        """Test US postal code semantic type"""
        postal_type = PREDEFINED_SEMANTIC_TYPES["postal_code_us"]
        
        # Valid postal codes
        assert postal_type.validate("12345")[0] is True
        assert postal_type.validate("12345-6789")[0] is True
        
        # Invalid postal codes
        assert postal_type.validate("1234")[0] is False
        assert postal_type.validate("ABCDE")[0] is False
        
    def test_percentage_validation(self):
        """Test percentage semantic type"""
        pct_type = PREDEFINED_SEMANTIC_TYPES["percentage"]
        
        # Valid percentages
        assert pct_type.validate(0)[0] is True
        assert pct_type.validate(50.5)[0] is True
        assert pct_type.validate(100)[0] is True
        
        # Invalid percentages
        assert pct_type.validate(-1)[0] is False
        assert pct_type.validate(101)[0] is False
        
        # Test formatting
        assert pct_type.format_display(75.5) == "75.5%"
        
    def test_sku_validation(self):
        """Test product SKU semantic type"""
        sku_type = PREDEFINED_SEMANTIC_TYPES["product_sku"]
        
        # Valid SKUs
        assert sku_type.validate("ABC-1234-A1")[0] is True
        assert sku_type.validate("XYZ-9876-B2")[0] is True
        
        # Invalid SKUs
        assert sku_type.validate("abc-1234-a1")[0] is False
        assert sku_type.validate("ABC-123-A1")[0] is False
        
    def test_country_code_validation(self):
        """Test ISO country code semantic type"""
        country_type = PREDEFINED_SEMANTIC_TYPES["iso_country_code"]
        
        # Valid country codes
        assert country_type.validate("US")[0] is True
        assert country_type.validate("GB")[0] is True
        
        # Invalid country codes
        assert country_type.validate("USA")[0] is False
        assert country_type.validate("ZZ")[0] is False  # Not in enum


class TestSemanticTypeRegistry:
    """Test SemanticTypeRegistry functionality"""
    
    def test_registry_initialization(self):
        """Test registry loads predefined types"""
        registry = SemanticTypeRegistry()
        
        # Check all predefined types are loaded
        for type_id in PREDEFINED_SEMANTIC_TYPES:
            assert registry.get(type_id) is not None
            
    def test_register_custom_type(self):
        """Test registering custom semantic types"""
        registry = SemanticTypeRegistry()
        
        custom_type = SemanticType(
            id="custom_id",
            name="Custom Type",
            category=SemanticTypeCategory.CUSTOM,
            base_type_id="string",
            created_by="test"
        )
        
        registry.register(custom_type)
        assert registry.get("custom_id") == custom_type
        
    def test_cannot_override_system_types(self):
        """Test that system types cannot be overridden"""
        registry = SemanticTypeRegistry()
        
        # Try to override a system type
        email_override = SemanticType(
            id="email_address",
            name="Fake Email",
            category=SemanticTypeCategory.CUSTOM,
            base_type_id="string",
            created_by="test"
        )
        
        with pytest.raises(ValueError, match="Cannot override system semantic type"):
            registry.register(email_override)
            
    def test_list_all_types(self):
        """Test listing all types"""
        registry = SemanticTypeRegistry()
        
        all_types = registry.list_all()
        assert len(all_types) >= len(PREDEFINED_SEMANTIC_TYPES)
        
    def test_list_by_category(self):
        """Test listing types by category"""
        registry = SemanticTypeRegistry()
        
        contact_types = registry.list_by_category(SemanticTypeCategory.CONTACT)
        assert len(contact_types) > 0
        assert all(t.category == SemanticTypeCategory.CONTACT for t in contact_types)
        
        financial_types = registry.list_by_category(SemanticTypeCategory.FINANCIAL)
        assert len(financial_types) > 0
        assert all(t.category == SemanticTypeCategory.FINANCIAL for t in financial_types)
        
    def test_validate_through_registry(self):
        """Test validation through registry"""
        registry = SemanticTypeRegistry()
        
        # Valid email
        is_valid, errors = registry.validate_value("email_address", "test@example.com")
        assert is_valid is True
        
        # Invalid email
        is_valid, errors = registry.validate_value("email_address", "not-an-email")
        assert is_valid is False
        
        # Unknown type
        is_valid, errors = registry.validate_value("unknown_type", "value")
        assert is_valid is False
        assert "Unknown semantic type" in errors[0]


class TestSemanticTypeIntegration:
    """Integration tests for semantic types with properties"""
    
    def test_semantic_type_with_property(self):
        """Test semantic type used in a property definition"""
        # This would test integration with Property model
        # Since Property model exists and has semantic_type_id field
        pass  # Integration test would go here
        
    def test_semantic_type_validation_in_api(self):
        """Test semantic type validation in API context"""
        # This would test the API endpoints
        pass  # API integration test would go here


if __name__ == "__main__":
    pytest.main([__file__, "-v"])