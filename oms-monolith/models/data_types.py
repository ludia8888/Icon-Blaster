"""
Data Types for OMS - Foundation for all data type definitions
Implements Palantir Foundry-style data types with validation and conversion

Data types define the basic formats allowed in properties:
- Primitive types: Boolean, String, Integer, Long, Double, Decimal
- Complex types: Array, Map, Struct
- Special types: Geopoint, Vector, TimeSeries, Attachment
- Temporal types: Date, Time, DateTime, Timestamp
"""
import json
import re
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


class DataTypeCategory(str, Enum):
    """Categories of data types"""
    PRIMITIVE = "primitive"
    COMPLEX = "complex"
    TEMPORAL = "temporal"
    SPATIAL = "spatial"
    BINARY = "binary"
    SPECIAL = "special"


class DataTypeFormat(str, Enum):
    """Standard data type formats (XSD compatible)"""
    # Primitive types
    BOOLEAN = "xsd:boolean"
    STRING = "xsd:string"
    INTEGER = "xsd:integer"
    LONG = "xsd:long"
    FLOAT = "xsd:float"
    DOUBLE = "xsd:double"
    DECIMAL = "xsd:decimal"

    # Temporal types
    DATE = "xsd:date"
    TIME = "xsd:time"
    DATETIME = "xsd:dateTime"
    TIMESTAMP = "xsd:dateTimeStamp"
    DURATION = "xsd:duration"

    # Binary types
    BINARY = "xsd:base64Binary"
    HEX_BINARY = "xsd:hexBinary"

    # Collection types
    ARRAY = "xsd:array"
    LIST = "xsd:list"

    # Special types
    JSON = "xsd:json"
    XML = "xsd:xml"
    ANY = "xsd:any"


class TypeConstraint(BaseModel):
    """Constraint for data type validation"""
    constraint_type: str  # min, max, minLength, maxLength, pattern, enum, precision, scale
    value: Any
    message: Optional[str] = None


class TypeConversion(BaseModel):
    """Conversion rule between data types"""
    from_type: str
    to_type: str
    conversion_type: str  # implicit, explicit, function
    function_name: Optional[str] = None
    is_lossy: bool = False


class DataType(BaseModel):
    """Base data type definition - OMS metadata for type system"""
    id: str
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    display_name: str
    description: Optional[str] = None
    category: DataTypeCategory
    format: DataTypeFormat
    constraints: List[TypeConstraint] = Field(default_factory=list)
    default_value: Optional[Any] = None
    is_nullable: bool = True
    is_array_type: bool = False
    array_item_type: Optional[str] = None  # For array types
    map_key_type: Optional[str] = None     # For map types
    map_value_type: Optional[str] = None   # For map types
    metadata: Dict[str, Any] = Field(default_factory=dict)
    supported_operations: List[str] = Field(default_factory=list)
    compatible_types: List[str] = Field(default_factory=list)

    # OMS-specific fields
    is_system: bool = False
    is_deprecated: bool = False
    deprecation_message: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    # Version management
    version: str = "1.0.0"
    version_hash: str
    previous_version_id: Optional[str] = None

    # Audit fields
    created_by: str
    created_at: datetime
    modified_by: str
    modified_at: datetime

    # Branch management
    branch_id: Optional[str] = None
    is_branch_specific: bool = False

    # Access control
    is_public: bool = True
    allowed_roles: List[str] = Field(default_factory=list)
    allowed_users: List[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v[0].isalpha():
            raise ValueError("Name must start with a letter")
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("Name can only contain letters, numbers, and underscores")
        return v

    def validate_schema(self) -> List[str]:
        """Validate the complete data type schema"""
        errors = []

        # Validate array type configuration
        if self.is_array_type and not self.array_item_type:
            errors.append("Array types must specify array_item_type")
        elif not self.is_array_type and self.array_item_type:
            errors.append("Non-array types cannot have array_item_type")

        # Validate map type configuration
        if self.map_key_type or self.map_value_type:
            if not (self.map_key_type and self.map_value_type):
                errors.append("Map types must specify both map_key_type and map_value_type")
            if self.category != DataTypeCategory.COMPLEX:
                errors.append("Map types must have COMPLEX category")

        # Validate constraints
        for constraint in self.constraints:
            if constraint.constraint_type == "enum" and not isinstance(constraint.value, list):
                errors.append("Enum constraint value must be a list")
            elif constraint.constraint_type in ["min", "max"] and self.category != DataTypeCategory.PRIMITIVE:
                errors.append("Min/max constraints only valid for primitive types")

        return errors


class DataTypeCreate(BaseModel):
    """Data type creation request"""
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    display_name: str
    description: Optional[str] = None
    category: DataTypeCategory
    format: DataTypeFormat
    constraints: Optional[List[TypeConstraint]] = None
    default_value: Optional[Any] = None
    is_nullable: Optional[bool] = True
    is_array_type: Optional[bool] = False
    array_item_type: Optional[str] = None
    map_key_type: Optional[str] = None
    map_value_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    supported_operations: Optional[List[str]] = None
    compatible_types: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = True
    allowed_roles: Optional[List[str]] = None
    allowed_users: Optional[List[str]] = None


class DataTypeUpdate(BaseModel):
    """Data type update request"""
    display_name: Optional[str] = None
    description: Optional[str] = None
    constraints: Optional[List[TypeConstraint]] = None
    default_value: Optional[Any] = None
    is_nullable: Optional[bool] = None
    is_array_type: Optional[bool] = None
    array_item_type: Optional[str] = None
    map_key_type: Optional[str] = None
    map_value_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    supported_operations: Optional[List[str]] = None
    compatible_types: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None
    allowed_roles: Optional[List[str]] = None
    allowed_users: Optional[List[str]] = None
    is_deprecated: Optional[bool] = None
    deprecation_message: Optional[str] = None


# Pre-defined system data types
SYSTEM_DATA_TYPES = {
    # Primitive types
    "boolean": {
        "name": "boolean",
        "display_name": "Boolean",
        "category": DataTypeCategory.PRIMITIVE,
        "format": DataTypeFormat.BOOLEAN,
        "supported_operations": ["equals", "not_equals", "is_null", "is_not_null"],
        "compatible_types": ["string"],
        "default_value": False
    },
    "string": {
        "name": "string",
        "display_name": "String",
        "category": DataTypeCategory.PRIMITIVE,
        "format": DataTypeFormat.STRING,
        "supported_operations": [
            "equals", "not_equals", "contains", "starts_with", "ends_with",
            "regex", "in", "not_in", "is_null", "is_not_null", "length"
        ],
        "compatible_types": ["boolean", "integer", "long", "float", "double", "decimal"],
        "constraints": [
            TypeConstraint(
                constraint_type="maxLength",
                value=65536,
                message="String length cannot exceed 65536 characters"
            )
        ]
    },
    "integer": {
        "name": "integer",
        "display_name": "Integer",
        "category": DataTypeCategory.PRIMITIVE,
        "format": DataTypeFormat.INTEGER,
        "supported_operations": [
            "equals", "not_equals", "less_than", "less_than_or_equals",
            "greater_than", "greater_than_or_equals", "between",
            "in", "not_in", "is_null", "is_not_null"
        ],
        "compatible_types": ["string", "long", "float", "double", "decimal"],
        "constraints": [
            TypeConstraint(
                constraint_type="min",
                value=-2147483648,
                message="Integer value out of range"
            ),
            TypeConstraint(
                constraint_type="max",
                value=2147483647,
                message="Integer value out of range"
            )
        ]
    },
    "long": {
        "name": "long",
        "display_name": "Long",
        "category": DataTypeCategory.PRIMITIVE,
        "format": DataTypeFormat.LONG,
        "supported_operations": [
            "equals", "not_equals", "less_than", "less_than_or_equals",
            "greater_than", "greater_than_or_equals", "between",
            "in", "not_in", "is_null", "is_not_null"
        ],
        "compatible_types": ["string", "integer", "float", "double", "decimal"],
        "constraints": [
            TypeConstraint(
                constraint_type="min",
                value=-9223372036854775808,
                message="Long value out of range"
            ),
            TypeConstraint(
                constraint_type="max",
                value=9223372036854775807,
                message="Long value out of range"
            )
        ]
    },
    "float": {
        "name": "float",
        "display_name": "Float",
        "category": DataTypeCategory.PRIMITIVE,
        "format": DataTypeFormat.FLOAT,
        "supported_operations": [
            "equals", "not_equals", "less_than", "less_than_or_equals",
            "greater_than", "greater_than_or_equals", "between",
            "is_null", "is_not_null"
        ],
        "compatible_types": ["string", "double", "decimal"],
        "metadata": {
            "precision": "32-bit IEEE 754",
            "special_values": ["NaN", "Infinity", "-Infinity"]
        }
    },
    "double": {
        "name": "double",
        "display_name": "Double",
        "category": DataTypeCategory.PRIMITIVE,
        "format": DataTypeFormat.DOUBLE,
        "supported_operations": [
            "equals", "not_equals", "less_than", "less_than_or_equals",
            "greater_than", "greater_than_or_equals", "between",
            "is_null", "is_not_null"
        ],
        "compatible_types": ["string", "float", "decimal"],
        "metadata": {
            "precision": "64-bit IEEE 754",
            "special_values": ["NaN", "Infinity", "-Infinity"]
        }
    },
    "decimal": {
        "name": "decimal",
        "display_name": "Decimal",
        "category": DataTypeCategory.PRIMITIVE,
        "format": DataTypeFormat.DECIMAL,
        "supported_operations": [
            "equals", "not_equals", "less_than", "less_than_or_equals",
            "greater_than", "greater_than_or_equals", "between",
            "is_null", "is_not_null"
        ],
        "compatible_types": ["string", "integer", "long", "float", "double"],
        "constraints": [
            TypeConstraint(
                constraint_type="precision",
                value=38,
                message="Decimal precision cannot exceed 38 digits"
            ),
            TypeConstraint(
                constraint_type="scale",
                value=18,
                message="Decimal scale cannot exceed 18 digits"
            )
        ],
        "metadata": {
            "default_precision": 18,
            "default_scale": 2
        }
    },

    # Temporal types
    "date": {
        "name": "date",
        "display_name": "Date",
        "category": DataTypeCategory.TEMPORAL,
        "format": DataTypeFormat.DATE,
        "supported_operations": [
            "equals", "not_equals", "before", "after", "between",
            "is_null", "is_not_null", "date_diff"
        ],
        "compatible_types": ["string", "datetime", "timestamp"],
        "metadata": {
            "format": "YYYY-MM-DD",
            "example": "2024-06-23"
        }
    },
    "time": {
        "name": "time",
        "display_name": "Time",
        "category": DataTypeCategory.TEMPORAL,
        "format": DataTypeFormat.TIME,
        "supported_operations": [
            "equals", "not_equals", "before", "after", "between",
            "is_null", "is_not_null"
        ],
        "compatible_types": ["string"],
        "metadata": {
            "format": "HH:MM:SS[.fff]",
            "example": "14:30:00"
        }
    },
    "datetime": {
        "name": "datetime",
        "display_name": "DateTime",
        "category": DataTypeCategory.TEMPORAL,
        "format": DataTypeFormat.DATETIME,
        "supported_operations": [
            "equals", "not_equals", "before", "after", "between",
            "is_null", "is_not_null", "date_diff", "date_add", "date_subtract"
        ],
        "compatible_types": ["string", "date", "timestamp"],
        "metadata": {
            "format": "YYYY-MM-DDTHH:MM:SS[.fff]",
            "example": "2024-06-23T14:30:00"
        }
    },
    "timestamp": {
        "name": "timestamp",
        "display_name": "Timestamp",
        "category": DataTypeCategory.TEMPORAL,
        "format": DataTypeFormat.TIMESTAMP,
        "supported_operations": [
            "equals", "not_equals", "before", "after", "between",
            "is_null", "is_not_null", "date_diff", "date_add", "date_subtract"
        ],
        "compatible_types": ["string", "datetime", "long"],
        "metadata": {
            "format": "ISO 8601 with timezone",
            "example": "2024-06-23T14:30:00Z",
            "supports_microseconds": True
        }
    },

    # Complex types
    "array": {
        "name": "array",
        "display_name": "Array",
        "category": DataTypeCategory.COMPLEX,
        "format": DataTypeFormat.JSON,
        "is_array_type": True,
        "supported_operations": [
            "contains", "contains_all", "contains_any", "size",
            "is_empty", "is_not_empty", "is_null", "is_not_null"
        ],
        "metadata": {
            "requires_item_type": True,
            "supports_nested_arrays": True
        }
    },
    "map": {
        "name": "map",
        "display_name": "Map",
        "category": DataTypeCategory.COMPLEX,
        "format": DataTypeFormat.JSON,
        "supported_operations": [
            "has_key", "has_value", "size", "is_empty", "is_not_empty",
            "is_null", "is_not_null"
        ],
        "metadata": {
            "requires_key_type": True,
            "requires_value_type": True,
            "key_constraints": ["string", "integer", "long"]
        }
    },
    "json": {
        "name": "json",
        "display_name": "JSON",
        "category": DataTypeCategory.COMPLEX,
        "format": DataTypeFormat.JSON,
        "supported_operations": [
            "json_path", "json_contains", "is_valid_json",
            "is_null", "is_not_null"
        ],
        "compatible_types": ["string"],
        "constraints": [
            TypeConstraint(
                constraint_type="maxLength",
                value=16777216,  # 16MB
                message="JSON size cannot exceed 16MB"
            )
        ]
    },

    # Spatial types
    "geopoint": {
        "name": "geopoint",
        "display_name": "Geopoint",
        "category": DataTypeCategory.SPATIAL,
        "format": DataTypeFormat.JSON,
        "supported_operations": [
            "within_distance", "within_bbox", "intersects",
            "is_null", "is_not_null"
        ],
        "metadata": {
            "structure": {
                "lat": "double",
                "lon": "double"
            },
            "coordinate_system": "WGS84",
            "lat_range": [-90, 90],
            "lon_range": [-180, 180]
        }
    },
    "geoshape": {
        "name": "geoshape",
        "display_name": "Geoshape",
        "category": DataTypeCategory.SPATIAL,
        "format": DataTypeFormat.JSON,
        "supported_operations": [
            "contains", "within", "intersects", "disjoint",
            "is_null", "is_not_null"
        ],
        "metadata": {
            "formats": ["WKT", "GeoJSON"],
            "supported_shapes": ["Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon"]
        }
    },

    # Special types
    "vector": {
        "name": "vector",
        "display_name": "Vector",
        "category": DataTypeCategory.SPECIAL,
        "format": DataTypeFormat.JSON,
        "supported_operations": [
            "cosine_similarity", "euclidean_distance", "dot_product",
            "magnitude", "normalize", "is_null", "is_not_null"
        ],
        "constraints": [
            TypeConstraint(
                constraint_type="dimensions",
                value=4096,
                message="Vector dimensions cannot exceed 4096"
            )
        ],
        "metadata": {
            "element_type": "float",
            "supports_sparse": True
        }
    },
    "timeseries": {
        "name": "timeseries",
        "display_name": "Time Series",
        "category": DataTypeCategory.SPECIAL,
        "format": DataTypeFormat.JSON,
        "supported_operations": [
            "aggregate", "interpolate", "resample", "rolling_window",
            "is_null", "is_not_null"
        ],
        "metadata": {
            "structure": {
                "timestamp": "timestamp",
                "value": "double",
                "metadata": "json"
            },
            "supports_multiple_series": True
        }
    },
    "attachment": {
        "name": "attachment",
        "display_name": "Attachment",
        "category": DataTypeCategory.BINARY,
        "format": DataTypeFormat.BINARY,
        "supported_operations": [
            "size", "mime_type", "is_null", "is_not_null"
        ],
        "constraints": [
            TypeConstraint(
                constraint_type="maxSize",
                value=1073741824,  # 1GB
                message="Attachment size cannot exceed 1GB"
            )
        ],
        "metadata": {
            "storage_type": "blob",
            "supports_streaming": True,
            "supported_mime_types": ["*/*"]
        }
    },
    "reference": {
        "name": "reference",
        "display_name": "Reference",
        "category": DataTypeCategory.SPECIAL,
        "format": DataTypeFormat.STRING,
        "supported_operations": [
            "equals", "not_equals", "in", "not_in",
            "is_null", "is_not_null", "resolve"
        ],
        "metadata": {
            "reference_type": "entity",
            "supports_foreign_key": True
        }
    }
}


class DataTypeValidator:
    """Validates values against data type constraints"""

    @staticmethod
    def validate(value: Any, data_type: DataType) -> Tuple[bool, List[str]]:
        """Validate a value against data type constraints"""
        errors = []

        # Null check
        if value is None:
            if not data_type.is_nullable:
                errors.append(f"Value cannot be null for non-nullable type {data_type.name}")
            return len(errors) == 0, errors

        # Type format validation
        if not DataTypeValidator._validate_format(value, data_type.format):
            errors.append(f"Value does not match expected format {data_type.format}")

        # Apply constraints
        for constraint in data_type.constraints:
            if not DataTypeValidator._apply_constraint(value, constraint):
                errors.append(constraint.message or f"Constraint {constraint.constraint_type} failed")

        return len(errors) == 0, errors

    @staticmethod
    def _validate_format(value: Any, format: DataTypeFormat) -> bool:
        """Validate value matches expected format"""
        try:
            if format == DataTypeFormat.BOOLEAN:
                return isinstance(value, bool)
            elif format == DataTypeFormat.STRING:
                return isinstance(value, str)
            elif format == DataTypeFormat.INTEGER:
                return isinstance(value, int) and not isinstance(value, bool)
            elif format == DataTypeFormat.LONG:
                return isinstance(value, int) and not isinstance(value, bool)
            elif format == DataTypeFormat.FLOAT:
                return isinstance(value, float)
            elif format == DataTypeFormat.DOUBLE:
                return isinstance(value, float)
            elif format == DataTypeFormat.DECIMAL:
                return isinstance(value, (Decimal, float, int))
            elif format == DataTypeFormat.DATE:
                if isinstance(value, date):
                    return True
                elif isinstance(value, str):
                    try:
                        from datetime import datetime
                        datetime.strptime(value, '%Y-%m-%d')
                        return True
                    except ValueError:
                        return False
                return False
            elif format == DataTypeFormat.TIME:
                return isinstance(value, (time, str))
            elif format == DataTypeFormat.DATETIME:
                return isinstance(value, (datetime, str))
            elif format == DataTypeFormat.TIMESTAMP:
                return isinstance(value, (datetime, int, float, str))
            elif format == DataTypeFormat.JSON:
                if isinstance(value, str):
                    json.loads(value)
                return True
            elif format == DataTypeFormat.BINARY:
                return isinstance(value, (bytes, str))
            else:
                return True
        except:
            return False

    @staticmethod
    def _apply_constraint(value: Any, constraint: TypeConstraint) -> bool:
        """Apply a single constraint to a value"""
        try:
            if constraint.constraint_type == "min":
                return value >= constraint.value
            elif constraint.constraint_type == "max":
                return value <= constraint.value
            elif constraint.constraint_type == "minLength":
                return len(str(value)) >= constraint.value
            elif constraint.constraint_type == "maxLength":
                return len(str(value)) <= constraint.value
            elif constraint.constraint_type == "pattern":
                return bool(re.match(constraint.value, str(value)))
            elif constraint.constraint_type == "enum":
                return value in constraint.value
            elif constraint.constraint_type == "precision":
                if isinstance(value, Decimal):
                    return len(str(value).replace('.', '').lstrip('-')) <= constraint.value
                return True
            elif constraint.constraint_type == "scale":
                if isinstance(value, Decimal):
                    decimal_str = str(value)
                    if '.' in decimal_str:
                        return len(decimal_str.split('.')[1]) <= constraint.value
                return True
            else:
                return True
        except:
            return False


class DataTypeConverter:
    """Converts values between data types"""

    # Conversion matrix defining allowed conversions
    CONVERSION_MATRIX = {
        "string": ["boolean", "integer", "long", "float", "double", "decimal", "date", "datetime", "timestamp", "json"],
        "boolean": ["string", "integer"],
        "integer": ["string", "long", "float", "double", "decimal", "boolean"],
        "long": ["string", "integer", "float", "double", "decimal", "timestamp"],
        "float": ["string", "double", "decimal"],
        "double": ["string", "float", "decimal"],
        "decimal": ["string", "integer", "long", "float", "double"],
        "date": ["string", "datetime", "timestamp"],
        "datetime": ["string", "date", "timestamp"],
        "timestamp": ["string", "datetime", "long"],
        "json": ["string"]
    }

    @staticmethod
    def can_convert(from_type: str, to_type: str) -> bool:
        """Check if conversion is possible between types"""
        if from_type == to_type:
            return True
        return to_type in DataTypeConverter.CONVERSION_MATRIX.get(from_type, [])

    @staticmethod
    def convert(value: Any, from_type: str, to_type: str) -> Tuple[bool, Any, Optional[str]]:
        """Convert value from one type to another"""
        if from_type == to_type:
            return True, value, None

        if not DataTypeConverter.can_convert(from_type, to_type):
            return False, None, f"Cannot convert from {from_type} to {to_type}"

        try:
            # String conversions
            if from_type == "string":
                if to_type == "boolean":
                    return True, value.lower() in ("true", "1", "yes", "on"), None
                elif to_type == "integer":
                    return True, int(value), None
                elif to_type == "long":
                    return True, int(value), None
                elif to_type == "float":
                    return True, float(value), None
                elif to_type == "double":
                    return True, float(value), None
                elif to_type == "decimal":
                    return True, Decimal(value), None
                elif to_type == "json":
                    return True, json.loads(value), None

            # Boolean conversions
            elif from_type == "boolean":
                if to_type == "string":
                    return True, str(value).lower(), None
                elif to_type == "integer":
                    return True, int(value), None

            # Numeric conversions
            elif from_type in ["integer", "long"]:
                if to_type == "string":
                    return True, str(value), None
                elif to_type == "boolean":
                    return True, bool(value), None
                elif to_type in ["float", "double"]:
                    return True, float(value), None
                elif to_type == "decimal":
                    return True, Decimal(str(value)), None

            # Float/Double conversions
            elif from_type in ["float", "double"]:
                if to_type == "string":
                    return True, str(value), None
                elif to_type == "decimal":
                    return True, Decimal(str(value)), None

            # Decimal conversions
            elif from_type == "decimal":
                if to_type == "string":
                    return True, str(value), None
                elif to_type in ["integer", "long"]:
                    return True, int(value), "Precision loss: decimal to integer"
                elif to_type in ["float", "double"]:
                    return True, float(value), "Possible precision loss"

            # Temporal conversions
            elif from_type == "timestamp" and to_type == "long":
                if isinstance(value, datetime):
                    return True, int(value.timestamp() * 1000), None

            return False, None, f"Conversion from {from_type} to {to_type} not implemented"

        except Exception as e:
            return False, None, f"Conversion error: {str(e)}"


class DataTypeRegistry:
    """Registry for managing available data types"""

    def __init__(self):
        self._types: Dict[str, DataType] = {}
        self._load_system_types()

    def _load_system_types(self):
        """Load system-defined data types"""
        from datetime import timezone
        now = datetime.now(timezone.utc)

        for type_id, type_def in SYSTEM_DATA_TYPES.items():
            # Create DataType instance from definition
            self._types[type_id] = DataType(
                id=type_id,
                is_system=True,
                version="1.0.0",
                version_hash="system",
                created_by="system",
                created_at=now,
                modified_by="system",
                modified_at=now,
                **type_def
            )

    def register(self, data_type: DataType) -> None:
        """Register a new data type"""
        if data_type.id in self._types and self._types[data_type.id].is_system:
            raise ValueError(f"Cannot override system type: {data_type.id}")
        self._types[data_type.id] = data_type

    def get(self, type_id: str) -> Optional[DataType]:
        """Get a data type by ID"""
        return self._types.get(type_id)

    def list(self, category: Optional[DataTypeCategory] = None) -> List[DataType]:
        """List all data types, optionally filtered by category"""
        types = list(self._types.values())
        if category:
            types = [t for t in types if t.category == category]
        return sorted(types, key=lambda t: t.name)

    def get_compatible_types(self, type_id: str) -> List[str]:
        """Get list of types compatible with the given type"""
        data_type = self.get(type_id)
        if data_type:
            return data_type.compatible_types
        return []

    def validate_value(self, value: Any, type_id: str) -> Tuple[bool, List[str]]:
        """Validate a value against a data type"""
        data_type = self.get(type_id)
        if not data_type:
            return False, [f"Unknown data type: {type_id}"]

        return DataTypeValidator.validate(value, data_type)

    def convert_value(self, value: Any, from_type_id: str, to_type_id: str) -> Tuple[bool, Any, Optional[str]]:
        """Convert a value between data types"""
        from_type = self.get(from_type_id)
        to_type = self.get(to_type_id)

        if not from_type or not to_type:
            return False, None, "Invalid type IDs"

        return DataTypeConverter.convert(value, from_type.name, to_type.name)


# Global registry instance
data_type_registry = DataTypeRegistry()


# Helper functions for common operations
def get_data_type(type_id: str) -> Optional[DataType]:
    """Get a data type by ID"""
    return data_type_registry.get(type_id)


def validate_value(value: Any, type_id: str) -> Tuple[bool, List[str]]:
    """Validate a value against a data type"""
    return data_type_registry.validate_value(value, type_id)


def convert_value(value: Any, from_type: str, to_type: str) -> Tuple[bool, Any, Optional[str]]:
    """Convert a value between data types"""
    return data_type_registry.convert_value(value, from_type, to_type)


def is_numeric_type(type_id: str) -> bool:
    """Check if a type is numeric"""
    return type_id in ["integer", "long", "float", "double", "decimal"]


def is_temporal_type(type_id: str) -> bool:
    """Check if a type is temporal"""
    return type_id in ["date", "time", "datetime", "timestamp"]


def is_complex_type(type_id: str) -> bool:
    """Check if a type is complex"""
    data_type = get_data_type(type_id)
    return data_type and data_type.category == DataTypeCategory.COMPLEX


def get_type_operations(type_id: str) -> List[str]:
    """Get supported operations for a data type"""
    data_type = get_data_type(type_id)
    return data_type.supported_operations if data_type else []
