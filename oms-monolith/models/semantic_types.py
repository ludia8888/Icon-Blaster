"""
Semantic Type (Value Type) Definitions for OMS

Implements FR-SM-VALID requirement from Ontology_Requirements_Document.md
Provides domain-specific constraints and validation for data types.
"""

from typing import Dict, Any, Optional, List, Pattern, Union
from pydantic import BaseModel, Field, validator
from enum import Enum
import re
from datetime import datetime

class ConstraintType(str, Enum):
    """Types of constraints that can be applied to semantic types"""
    PATTERN = "pattern"          # Regular expression pattern
    MIN_VALUE = "min_value"      # Minimum numeric value
    MAX_VALUE = "max_value"      # Maximum numeric value
    MIN_LENGTH = "min_length"    # Minimum string length
    MAX_LENGTH = "max_length"    # Maximum string length
    ENUM = "enum"               # Enumerated values
    CUSTOM = "custom"           # Custom validation function

class SemanticTypeCategory(str, Enum):
    """Categories of semantic types for organization"""
    IDENTIFIER = "identifier"    # IDs, codes, keys
    CONTACT = "contact"         # Email, phone, address
    FINANCIAL = "financial"     # Currency, account numbers
    TEMPORAL = "temporal"       # Dates with business meaning
    GEOGRAPHIC = "geographic"   # Location-based
    MEASUREMENT = "measurement" # Units, quantities
    TEXT = "text"              # Structured text
    CUSTOM = "custom"          # Domain-specific

class ValidationRule(BaseModel):
    """Individual validation rule for a semantic type"""
    type: ConstraintType
    value: Any
    error_message: Optional[str] = None
    
    def validate_value(self, value: Any) -> tuple[bool, Optional[str]]:
        """
        Validate a value against this rule
        Returns (is_valid, error_message)
        """
        try:
            if self.type == ConstraintType.PATTERN:
                pattern = re.compile(self.value)
                if not pattern.match(str(value)):
                    return False, self.error_message or f"Value does not match pattern: {self.value}"
                    
            elif self.type == ConstraintType.MIN_VALUE:
                if float(value) < float(self.value):
                    return False, self.error_message or f"Value must be >= {self.value}"
                    
            elif self.type == ConstraintType.MAX_VALUE:
                if float(value) > float(self.value):
                    return False, self.error_message or f"Value must be <= {self.value}"
                    
            elif self.type == ConstraintType.MIN_LENGTH:
                if len(str(value)) < int(self.value):
                    return False, self.error_message or f"Length must be >= {self.value}"
                    
            elif self.type == ConstraintType.MAX_LENGTH:
                if len(str(value)) > int(self.value):
                    return False, self.error_message or f"Length must be <= {self.value}"
                    
            elif self.type == ConstraintType.ENUM:
                if value not in self.value:
                    return False, self.error_message or f"Value must be one of: {', '.join(map(str, self.value))}"
                    
            elif self.type == ConstraintType.CUSTOM:
                # Custom validation would be implemented via plugins
                pass
                
            return True, None
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"

class SemanticType(BaseModel):
    """
    Semantic Type definition - adds meaning and constraints to base data types
    Implements requirement FR-SM-VALID
    """
    id: str = Field(..., description="Unique identifier for the semantic type")
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None, description="Detailed description")
    category: SemanticTypeCategory = Field(..., description="Category for organization")
    base_type_id: str = Field(..., description="ID of the underlying data type")
    
    # Validation rules
    validation_rules: List[ValidationRule] = Field(
        default_factory=list,
        description="List of validation rules to apply"
    )
    
    # Display formatting
    display_format: Optional[str] = Field(
        None,
        description="Format string for display (e.g., '${value:,.2f}' for currency)"
    )
    input_mask: Optional[str] = Field(
        None,
        description="Input mask for UI (e.g., '(999) 999-9999' for phone)"
    )
    
    # Metadata
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    examples: List[Any] = Field(default_factory=list, description="Example valid values")
    
    # Audit fields
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    modified_at: Optional[datetime] = None
    modified_by: Optional[str] = None
    
    # Status
    is_active: bool = Field(True, description="Whether this semantic type is active")
    is_system: bool = Field(False, description="Whether this is a system-defined type")
    
    def validate(self, value: Any) -> tuple[bool, List[str]]:
        """
        Validate a value against all rules of this semantic type
        Returns (is_valid, list_of_errors)
        """
        errors = []
        
        for rule in self.validation_rules:
            is_valid, error = rule.validate_value(value)
            if not is_valid:
                errors.append(error)
                
        return len(errors) == 0, errors
    
    def format_display(self, value: Any) -> str:
        """Format value for display using the display_format"""
        if self.display_format:
            try:
                # Handle different format string styles
                if "{value" in self.display_format:
                    # Python format string style (e.g., "${value:,.2f}")
                    return self.display_format.format(value=value)
                else:
                    # Simple replacement style
                    return self.display_format.replace("{value}", str(value))
            except:
                return str(value)
        return str(value)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# Predefined Semantic Types Registry
PREDEFINED_SEMANTIC_TYPES = {
    "email_address": SemanticType(
        id="email_address",
        name="Email Address",
        description="Valid email address format",
        category=SemanticTypeCategory.CONTACT,
        base_type_id="string",
        validation_rules=[
            ValidationRule(
                type=ConstraintType.PATTERN,
                value=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                error_message="Invalid email address format"
            ),
            ValidationRule(
                type=ConstraintType.MAX_LENGTH,
                value=254,
                error_message="Email address too long"
            )
        ],
        examples=["user@example.com", "john.doe@company.org"],
        created_by="system",
        is_system=True
    ),
    
    "url": SemanticType(
        id="url",
        name="URL",
        description="Valid URL format",
        category=SemanticTypeCategory.CONTACT,
        base_type_id="string",
        validation_rules=[
            ValidationRule(
                type=ConstraintType.PATTERN,
                value=r"^https?://[^\s/$.?#].[^\s]*$",
                error_message="Invalid URL format"
            ),
            ValidationRule(
                type=ConstraintType.MAX_LENGTH,
                value=2048,
                error_message="URL too long"
            )
        ],
        examples=["https://example.com", "http://localhost:8080/path"],
        created_by="system",
        is_system=True
    ),
    
    "phone_number": SemanticType(
        id="phone_number",
        name="Phone Number",
        description="International phone number format",
        category=SemanticTypeCategory.CONTACT,
        base_type_id="string",
        validation_rules=[
            ValidationRule(
                type=ConstraintType.PATTERN,
                value=r"^\+?[1-9]\d{1,14}$",
                error_message="Invalid phone number format (E.164)"
            )
        ],
        input_mask="+9 (999) 999-9999",
        examples=["+1234567890", "+442071234567"],
        created_by="system",
        is_system=True
    ),
    
    "currency_usd": SemanticType(
        id="currency_usd",
        name="US Dollar Amount",
        description="Monetary amount in USD",
        category=SemanticTypeCategory.FINANCIAL,
        base_type_id="decimal",
        validation_rules=[
            ValidationRule(
                type=ConstraintType.MIN_VALUE,
                value=0,
                error_message="Amount cannot be negative"
            ),
            ValidationRule(
                type=ConstraintType.MAX_VALUE,
                value=999999999.99,
                error_message="Amount exceeds maximum"
            )
        ],
        display_format="${value:,.2f}",
        examples=[100.00, 1234.56],
        created_by="system",
        is_system=True
    ),
    
    "postal_code_us": SemanticType(
        id="postal_code_us",
        name="US Postal Code",
        description="5 or 9 digit US postal code",
        category=SemanticTypeCategory.GEOGRAPHIC,
        base_type_id="string",
        validation_rules=[
            ValidationRule(
                type=ConstraintType.PATTERN,
                value=r"^\d{5}(-\d{4})?$",
                error_message="Invalid US postal code format"
            )
        ],
        input_mask="99999-9999",
        examples=["12345", "12345-6789"],
        created_by="system",
        is_system=True
    ),
    
    "percentage": SemanticType(
        id="percentage",
        name="Percentage",
        description="Percentage value (0-100)",
        category=SemanticTypeCategory.MEASUREMENT,
        base_type_id="decimal",
        validation_rules=[
            ValidationRule(
                type=ConstraintType.MIN_VALUE,
                value=0,
                error_message="Percentage cannot be negative"
            ),
            ValidationRule(
                type=ConstraintType.MAX_VALUE,
                value=100,
                error_message="Percentage cannot exceed 100"
            )
        ],
        display_format="{value}%",
        examples=[0, 50, 99.99, 100],
        created_by="system",
        is_system=True
    ),
    
    "product_sku": SemanticType(
        id="product_sku",
        name="Product SKU",
        description="Stock Keeping Unit identifier",
        category=SemanticTypeCategory.IDENTIFIER,
        base_type_id="string",
        validation_rules=[
            ValidationRule(
                type=ConstraintType.PATTERN,
                value=r"^[A-Z]{3}-\d{4}-[A-Z0-9]{2}$",
                error_message="Invalid SKU format (expected: ABC-1234-X1)"
            )
        ],
        examples=["ABC-1234-A1", "XYZ-9876-B2"],
        created_by="system",
        is_system=True
    ),
    
    "iso_country_code": SemanticType(
        id="iso_country_code",
        name="ISO Country Code",
        description="2-letter ISO 3166-1 alpha-2 country code",
        category=SemanticTypeCategory.GEOGRAPHIC,
        base_type_id="string",
        validation_rules=[
            ValidationRule(
                type=ConstraintType.PATTERN,
                value=r"^[A-Z]{2}$",
                error_message="Invalid ISO country code"
            ),
            ValidationRule(
                type=ConstraintType.ENUM,
                value=["US", "GB", "FR", "DE", "JP", "CN", "IN", "BR", "CA", "AU"],  # Subset for example
                error_message="Unknown country code"
            )
        ],
        examples=["US", "GB", "FR"],
        created_by="system",
        is_system=True
    )
}

class SemanticTypeRegistry:
    """Registry for managing semantic types"""
    
    def __init__(self):
        self._types: Dict[str, SemanticType] = {}
        self._load_predefined_types()
        
    def _load_predefined_types(self):
        """Load predefined semantic types"""
        for type_id, semantic_type in PREDEFINED_SEMANTIC_TYPES.items():
            self._types[type_id] = semantic_type
            
    def register(self, semantic_type: SemanticType) -> None:
        """Register a new semantic type"""
        if semantic_type.id in self._types and self._types[semantic_type.id].is_system:
            raise ValueError(f"Cannot override system semantic type: {semantic_type.id}")
        self._types[semantic_type.id] = semantic_type
        
    def get(self, type_id: str) -> Optional[SemanticType]:
        """Get a semantic type by ID"""
        return self._types.get(type_id)
        
    def list_all(self) -> List[SemanticType]:
        """List all registered semantic types"""
        return list(self._types.values())
        
    def list_by_category(self, category: SemanticTypeCategory) -> List[SemanticType]:
        """List semantic types by category"""
        return [st for st in self._types.values() if st.category == category]
        
    def validate_value(self, type_id: str, value: Any) -> tuple[bool, List[str]]:
        """Validate a value against a semantic type"""
        semantic_type = self.get(type_id)
        if not semantic_type:
            return False, [f"Unknown semantic type: {type_id}"]
        return semantic_type.validate(value)

# Global registry instance
semantic_type_registry = SemanticTypeRegistry()