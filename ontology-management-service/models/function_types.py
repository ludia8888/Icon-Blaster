"""
Function Types for OMS - Reusable computational logic definitions
Implements Palantir Foundry-style function types for transformations and computations

Function types define the metadata for functions that can:
- Transform data between types
- Perform calculations and aggregations
- Integrate with external systems
- Support custom business logic

OMS only manages function metadata - actual execution is handled by Function Service
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class FunctionCategory(str, Enum):
    """Categories of function types"""
    TRANSFORMATION = "transformation"  # Data type conversions and transformations
    AGGREGATION = "aggregation"       # Aggregate operations (sum, avg, count, etc.)
    VALIDATION = "validation"         # Data validation functions
    CALCULATION = "calculation"       # Mathematical and business calculations
    EXTRACTION = "extraction"         # Extract data from complex types
    ENRICHMENT = "enrichment"         # Enrich data with external sources
    FILTERING = "filtering"           # Filter and search operations
    INTEGRATION = "integration"       # External system integration
    TEMPORAL = "temporal"             # Time-based operations
    SPATIAL = "spatial"               # Geospatial operations
    ML_INFERENCE = "ml_inference"     # Machine learning inference
    CUSTOM = "custom"                 # Custom business logic


class FunctionRuntime(str, Enum):
    """Function runtime environments"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    SQL = "sql"
    SPARK = "spark"
    CUSTOM = "custom"


class ParameterDirection(str, Enum):
    """Parameter direction"""
    INPUT = "input"
    OUTPUT = "output"
    INOUT = "inout"  # Both input and output


class FunctionParameter(BaseModel):
    """Function parameter definition"""
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    display_name: str
    description: Optional[str] = None
    direction: ParameterDirection = ParameterDirection.INPUT
    data_type_id: str  # Reference to data type
    semantic_type_id: Optional[str] = None  # Optional semantic type
    struct_type_id: Optional[str] = None    # For struct parameters
    is_required: bool = True
    is_array: bool = False
    default_value: Optional[Any] = None
    validation_rules: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v[0].isalpha():
            raise ValueError("Name must start with a letter")
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("Name can only contain letters, numbers, and underscores")
        return v


class ReturnType(BaseModel):
    """Function return type definition"""
    data_type_id: str
    semantic_type_id: Optional[str] = None
    struct_type_id: Optional[str] = None
    is_array: bool = False
    is_nullable: bool = True
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RuntimeConfig(BaseModel):
    """Runtime configuration for function execution"""
    runtime: FunctionRuntime
    version: Optional[str] = None  # Runtime version
    timeout_ms: int = 30000  # Default 30 seconds
    memory_mb: int = 512     # Default 512MB
    cpu_cores: float = 1.0   # Default 1 CPU core
    max_retries: int = 3
    retry_delay_ms: int = 1000
    environment_vars: Dict[str, str] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)  # Package dependencies
    resource_limits: Dict[str, Any] = Field(default_factory=dict)


class FunctionBehavior(BaseModel):
    """Behavioral characteristics of the function"""
    is_deterministic: bool = True  # Same input always produces same output
    is_stateless: bool = True      # No side effects or state
    is_cacheable: bool = True      # Results can be cached
    is_parallelizable: bool = True # Can run in parallel
    has_side_effects: bool = False # Modifies external state
    is_expensive: bool = False     # Computationally expensive
    cache_ttl_seconds: Optional[int] = None  # Cache time-to-live


class FunctionExample(BaseModel):
    """Example usage of the function"""
    name: str
    description: Optional[str] = None
    input_values: Dict[str, Any]
    expected_output: Any
    explanation: Optional[str] = None


class FunctionMetrics(BaseModel):
    """Performance metrics for the function"""
    avg_execution_time_ms: Optional[float] = None
    p95_execution_time_ms: Optional[float] = None
    p99_execution_time_ms: Optional[float] = None
    success_rate: Optional[float] = None
    error_rate: Optional[float] = None
    invocation_count: Optional[int] = None
    last_invoked_at: Optional[datetime] = None


class FunctionType(BaseModel):
    """Function type definition - metadata for reusable computational logic"""
    id: str
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    display_name: str
    description: Optional[str] = None
    category: FunctionCategory

    # Function signature
    parameters: List[FunctionParameter] = Field(default_factory=list)
    return_type: ReturnType

    # Runtime configuration
    runtime_config: RuntimeConfig

    # Behavioral characteristics
    behavior: FunctionBehavior = Field(default_factory=FunctionBehavior)

    # Implementation details
    implementation_ref: Optional[str] = None  # Reference to actual implementation
    function_body: Optional[str] = None       # For inline functions

    # Usage and documentation
    examples: List[FunctionExample] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    # Access control
    is_public: bool = True
    allowed_roles: List[str] = Field(default_factory=list)
    allowed_users: List[str] = Field(default_factory=list)

    # Performance metrics
    metrics: Optional[FunctionMetrics] = None

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_system: bool = False
    is_deprecated: bool = False
    deprecation_message: Optional[str] = None

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

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v[0].isalpha():
            raise ValueError("Name must start with a letter")
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("Name can only contain letters, numbers, and underscores")
        return v

    def get_signature(self) -> str:
        """Get function signature as string"""
        params = ", ".join(
            f"{p.name}: {p.data_type_id}{'[]' if p.is_array else ''}"
            for p in sorted(self.parameters, key=lambda x: x.sort_order)
            if p.direction in [ParameterDirection.INPUT, ParameterDirection.INOUT]
        )
        return_str = f"{self.return_type.data_type_id}{'[]' if self.return_type.is_array else ''}"
        return f"{self.name}({params}) -> {return_str}"

    def validate_invocation(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate function invocation inputs"""
        errors = []

        # Check required parameters
        for param in self.parameters:
            if param.direction == ParameterDirection.OUTPUT:
                continue

            if param.is_required and param.name not in inputs:
                errors.append(f"Required parameter '{param.name}' is missing")

            # Additional validation would check types, ranges, etc.

        # Check for unknown parameters
        valid_params = {p.name for p in self.parameters if p.direction != ParameterDirection.OUTPUT}
        for input_name in inputs:
            if input_name not in valid_params:
                errors.append(f"Unknown parameter '{input_name}'")

        return errors


class FunctionTypeCreate(BaseModel):
    """Function type creation request"""
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    display_name: str
    description: Optional[str] = None
    category: FunctionCategory
    parameters: List[FunctionParameter]
    return_type: ReturnType
    runtime_config: RuntimeConfig
    behavior: Optional[FunctionBehavior] = None
    implementation_ref: Optional[str] = None
    function_body: Optional[str] = None
    examples: Optional[List[FunctionExample]] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = True
    allowed_roles: Optional[List[str]] = None
    allowed_users: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class FunctionTypeUpdate(BaseModel):
    """Function type update request"""
    display_name: Optional[str] = None
    description: Optional[str] = None
    parameters: Optional[List[FunctionParameter]] = None
    return_type: Optional[ReturnType] = None
    runtime_config: Optional[RuntimeConfig] = None
    behavior: Optional[FunctionBehavior] = None
    implementation_ref: Optional[str] = None
    function_body: Optional[str] = None
    examples: Optional[List[FunctionExample]] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None
    allowed_roles: Optional[List[str]] = None
    allowed_users: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    is_deprecated: Optional[bool] = None
    deprecation_message: Optional[str] = None


# Pre-defined system function types
SYSTEM_FUNCTION_TYPES = {
    # Type conversion functions
    "to_string": {
        "name": "to_string",
        "display_name": "To String",
        "description": "Convert any value to string representation",
        "category": FunctionCategory.TRANSFORMATION,
        "parameters": [
            FunctionParameter(
                name="value",
                display_name="Value",
                description="Value to convert",
                data_type_id="xsd:any",
                is_required=True,
                sort_order=1
            ),
            FunctionParameter(
                name="format",
                display_name="Format",
                description="Optional format string",
                data_type_id="xsd:string",
                is_required=False,
                sort_order=2
            )
        ],
        "return_type": ReturnType(
            data_type_id="xsd:string",
            is_nullable=False
        ),
        "runtime_config": RuntimeConfig(
            runtime=FunctionRuntime.PYTHON,
            timeout_ms=5000,
            memory_mb=128
        ),
        "behavior": FunctionBehavior(
            is_deterministic=True,
            is_stateless=True,
            is_cacheable=True
        )
    },

    # Aggregation functions
    "sum": {
        "name": "sum",
        "display_name": "Sum",
        "description": "Calculate sum of numeric values",
        "category": FunctionCategory.AGGREGATION,
        "parameters": [
            FunctionParameter(
                name="values",
                display_name="Values",
                description="Array of numeric values",
                data_type_id="xsd:double",
                is_required=True,
                is_array=True,
                sort_order=1
            )
        ],
        "return_type": ReturnType(
            data_type_id="xsd:double",
            is_nullable=False
        ),
        "runtime_config": RuntimeConfig(
            runtime=FunctionRuntime.PYTHON,
            timeout_ms=10000,
            memory_mb=256
        ),
        "behavior": FunctionBehavior(
            is_deterministic=True,
            is_stateless=True,
            is_cacheable=True,
            is_parallelizable=True
        )
    },

    # String manipulation
    "concat": {
        "name": "concat",
        "display_name": "Concatenate",
        "description": "Concatenate multiple strings",
        "category": FunctionCategory.TRANSFORMATION,
        "parameters": [
            FunctionParameter(
                name="strings",
                display_name="Strings",
                description="Array of strings to concatenate",
                data_type_id="xsd:string",
                is_required=True,
                is_array=True,
                sort_order=1
            ),
            FunctionParameter(
                name="separator",
                display_name="Separator",
                description="Optional separator between strings",
                data_type_id="xsd:string",
                is_required=False,
                default_value="",
                sort_order=2
            )
        ],
        "return_type": ReturnType(
            data_type_id="xsd:string",
            is_nullable=False
        ),
        "runtime_config": RuntimeConfig(
            runtime=FunctionRuntime.PYTHON,
            timeout_ms=5000,
            memory_mb=128
        )
    },

    # Date/Time functions
    "date_diff": {
        "name": "date_diff",
        "display_name": "Date Difference",
        "description": "Calculate difference between two dates",
        "category": FunctionCategory.TEMPORAL,
        "parameters": [
            FunctionParameter(
                name="start_date",
                display_name="Start Date",
                data_type_id="xsd:dateTime",
                is_required=True,
                sort_order=1
            ),
            FunctionParameter(
                name="end_date",
                display_name="End Date",
                data_type_id="xsd:dateTime",
                is_required=True,
                sort_order=2
            ),
            FunctionParameter(
                name="unit",
                display_name="Unit",
                description="Unit of difference (days, hours, minutes, seconds)",
                data_type_id="xsd:string",
                is_required=False,
                default_value="days",
                validation_rules={"enum": ["days", "hours", "minutes", "seconds"]},
                sort_order=3
            )
        ],
        "return_type": ReturnType(
            data_type_id="xsd:long",
            is_nullable=False
        ),
        "runtime_config": RuntimeConfig(
            runtime=FunctionRuntime.PYTHON,
            timeout_ms=5000,
            memory_mb=128
        )
    },

    # Validation functions
    "validate_email": {
        "name": "validate_email",
        "display_name": "Validate Email",
        "description": "Validate email address format",
        "category": FunctionCategory.VALIDATION,
        "parameters": [
            FunctionParameter(
                name="email",
                display_name="Email",
                data_type_id="xsd:string",
                is_required=True,
                sort_order=1
            )
        ],
        "return_type": ReturnType(
            data_type_id="xsd:boolean",
            is_nullable=False
        ),
        "runtime_config": RuntimeConfig(
            runtime=FunctionRuntime.PYTHON,
            timeout_ms=1000,
            memory_mb=64
        ),
        "behavior": FunctionBehavior(
            is_deterministic=True,
            is_stateless=True,
            is_cacheable=True
        )
    },

    # Geospatial functions
    "distance": {
        "name": "distance",
        "display_name": "Calculate Distance",
        "description": "Calculate distance between two geographic points",
        "category": FunctionCategory.SPATIAL,
        "parameters": [
            FunctionParameter(
                name="point1",
                display_name="Point 1",
                data_type_id="geopoint",
                is_required=True,
                sort_order=1
            ),
            FunctionParameter(
                name="point2",
                display_name="Point 2",
                data_type_id="geopoint",
                is_required=True,
                sort_order=2
            ),
            FunctionParameter(
                name="unit",
                display_name="Unit",
                description="Unit of distance (km, mi, m)",
                data_type_id="xsd:string",
                is_required=False,
                default_value="km",
                validation_rules={"enum": ["km", "mi", "m"]},
                sort_order=3
            )
        ],
        "return_type": ReturnType(
            data_type_id="xsd:double",
            is_nullable=False
        ),
        "runtime_config": RuntimeConfig(
            runtime=FunctionRuntime.PYTHON,
            timeout_ms=5000,
            memory_mb=128
        )
    },

    # JSON manipulation
    "json_extract": {
        "name": "json_extract",
        "display_name": "JSON Extract",
        "description": "Extract value from JSON using path",
        "category": FunctionCategory.EXTRACTION,
        "parameters": [
            FunctionParameter(
                name="json_data",
                display_name="JSON Data",
                data_type_id="xsd:json",
                is_required=True,
                sort_order=1
            ),
            FunctionParameter(
                name="path",
                display_name="JSON Path",
                description="JSON path expression",
                data_type_id="xsd:string",
                is_required=True,
                sort_order=2
            ),
            FunctionParameter(
                name="default_value",
                display_name="Default Value",
                description="Value to return if path not found",
                data_type_id="xsd:any",
                is_required=False,
                sort_order=3
            )
        ],
        "return_type": ReturnType(
            data_type_id="xsd:any",
            is_nullable=True
        ),
        "runtime_config": RuntimeConfig(
            runtime=FunctionRuntime.PYTHON,
            timeout_ms=5000,
            memory_mb=256
        )
    },

    # Array operations
    "array_filter": {
        "name": "array_filter",
        "display_name": "Array Filter",
        "description": "Filter array elements based on condition",
        "category": FunctionCategory.FILTERING,
        "parameters": [
            FunctionParameter(
                name="array",
                display_name="Array",
                data_type_id="xsd:any",
                is_array=True,
                is_required=True,
                sort_order=1
            ),
            FunctionParameter(
                name="condition",
                display_name="Condition",
                description="Filter condition expression",
                data_type_id="xsd:string",
                is_required=True,
                sort_order=2
            )
        ],
        "return_type": ReturnType(
            data_type_id="xsd:any",
            is_array=True,
            is_nullable=False
        ),
        "runtime_config": RuntimeConfig(
            runtime=FunctionRuntime.PYTHON,
            timeout_ms=10000,
            memory_mb=512
        ),
        "behavior": FunctionBehavior(
            is_deterministic=True,
            is_stateless=True,
            is_cacheable=True,
            is_parallelizable=True
        )
    },

    # Mathematical functions
    "round": {
        "name": "round",
        "display_name": "Round",
        "description": "Round numeric value to specified precision",
        "category": FunctionCategory.CALCULATION,
        "parameters": [
            FunctionParameter(
                name="value",
                display_name="Value",
                data_type_id="xsd:double",
                is_required=True,
                sort_order=1
            ),
            FunctionParameter(
                name="precision",
                display_name="Precision",
                description="Number of decimal places",
                data_type_id="xsd:integer",
                is_required=False,
                default_value=0,
                sort_order=2
            )
        ],
        "return_type": ReturnType(
            data_type_id="xsd:double",
            is_nullable=False
        ),
        "runtime_config": RuntimeConfig(
            runtime=FunctionRuntime.PYTHON,
            timeout_ms=1000,
            memory_mb=64
        )
    },

    # Hash functions
    "hash_sha256": {
        "name": "hash_sha256",
        "display_name": "SHA-256 Hash",
        "description": "Calculate SHA-256 hash of input",
        "category": FunctionCategory.TRANSFORMATION,
        "parameters": [
            FunctionParameter(
                name="input",
                display_name="Input",
                data_type_id="xsd:string",
                is_required=True,
                sort_order=1
            )
        ],
        "return_type": ReturnType(
            data_type_id="xsd:string",
            is_nullable=False
        ),
        "runtime_config": RuntimeConfig(
            runtime=FunctionRuntime.PYTHON,
            timeout_ms=1000,
            memory_mb=64
        ),
        "behavior": FunctionBehavior(
            is_deterministic=True,
            is_stateless=True,
            is_cacheable=True
        )
    }
}


class FunctionInvocation(BaseModel):
    """Function invocation request"""
    function_type_id: str
    inputs: Dict[str, Any]
    execution_context: Optional[Dict[str, Any]] = None
    timeout_override_ms: Optional[int] = None
    async_execution: bool = False
    callback_url: Optional[str] = None


class FunctionResult(BaseModel):
    """Function execution result"""
    invocation_id: str
    function_type_id: str
    status: str  # success, error, timeout
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: float
    executed_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FunctionTypeValidator:
    """Validates function type definitions"""

    @staticmethod
    def validate_function_type(func_type: FunctionType) -> List[str]:
        """Validate function type definition"""
        errors = []

        # Validate parameters
        param_names = set()
        for param in func_type.parameters:
            if param.name in param_names:
                errors.append(f"Duplicate parameter name: {param.name}")
            param_names.add(param.name)

        # Validate return type
        if not func_type.return_type.data_type_id:
            errors.append("Return type must specify a data type")

        # Validate runtime config
        if func_type.runtime_config.timeout_ms <= 0:
            errors.append("Timeout must be positive")

        if func_type.runtime_config.memory_mb <= 0:
            errors.append("Memory allocation must be positive")

        # Validate examples
        for example in func_type.examples:
            missing_params = []
            for param in func_type.parameters:
                if param.is_required and param.direction != ParameterDirection.OUTPUT:
                    if param.name not in example.input_values:
                        missing_params.append(param.name)

            if missing_params:
                errors.append(f"Example '{example.name}' missing required parameters: {missing_params}")

        return errors


class FunctionTypeRegistry:
    """Registry for managing function types"""

    def __init__(self):
        self._types: Dict[str, FunctionType] = {}
        self._load_system_types()

    def _load_system_types(self):
        """Load system-defined function types"""
        for type_id, type_def in SYSTEM_FUNCTION_TYPES.items():
            # Create FunctionType instance from definition
            self._types[type_id] = FunctionType(
                id=type_id,
                is_system=True,
                version_hash="system",
                created_by="system",
                created_at=datetime.now(timezone.utc),
                modified_by="system",
                modified_at=datetime.now(timezone.utc),
                **type_def
            )

    def register(self, func_type: FunctionType) -> None:
        """Register a new function type"""
        if func_type.id in self._types and self._types[func_type.id].is_system:
            raise ValueError(f"Cannot override system function type: {func_type.id}")

        # Validate before registering
        errors = FunctionTypeValidator.validate_function_type(func_type)
        if errors:
            raise ValueError(f"Invalid function type: {errors}")

        self._types[func_type.id] = func_type

    def get(self, type_id: str) -> Optional[FunctionType]:
        """Get a function type by ID"""
        return self._types.get(type_id)

    def list(self, category: Optional[FunctionCategory] = None) -> List[FunctionType]:
        """List all function types, optionally filtered by category"""
        types = list(self._types.values())
        if category:
            types = [t for t in types if t.category == category]
        return sorted(types, key=lambda t: t.name)

    def search(self, query: str) -> List[FunctionType]:
        """Search function types by name or description"""
        query_lower = query.lower()
        results = []

        for func_type in self._types.values():
            if (query_lower in func_type.name.lower() or
                query_lower in func_type.display_name.lower() or
                (func_type.description and query_lower in func_type.description.lower())):
                results.append(func_type)

        return sorted(results, key=lambda t: t.name)

    def get_by_category(self, category: FunctionCategory) -> List[FunctionType]:
        """Get all function types in a category"""
        return [t for t in self._types.values() if t.category == category]

    def validate_invocation(self, function_type_id: str, inputs: Dict[str, Any]) -> List[str]:
        """Validate function invocation"""
        func_type = self.get(function_type_id)
        if not func_type:
            return [f"Unknown function type: {function_type_id}"]

        return func_type.validate_invocation(inputs)


# Global registry instance
function_type_registry = FunctionTypeRegistry()


# Helper functions
def get_function_type(type_id: str) -> Optional[FunctionType]:
    """Get a function type by ID"""
    return function_type_registry.get(type_id)


def list_function_types(category: Optional[FunctionCategory] = None) -> List[FunctionType]:
    """List all function types"""
    return function_type_registry.list(category)


def search_function_types(query: str) -> List[FunctionType]:
    """Search function types"""
    return function_type_registry.search(query)


def validate_function_invocation(function_type_id: str, inputs: Dict[str, Any]) -> List[str]:
    """Validate function invocation"""
    return function_type_registry.validate_invocation(function_type_id, inputs)


# Function composition utilities
class FunctionComposition(BaseModel):
    """Represents a composition of multiple functions"""
    name: str
    description: Optional[str] = None
    steps: List[Dict[str, Any]]  # Each step has function_type_id and parameter mappings

    def validate(self) -> List[str]:
        """Validate the function composition"""
        errors = []

        # Track available outputs from previous steps
        available_outputs = {"input": True}  # Initial input is available

        for i, step in enumerate(self.steps):
            if "function_type_id" not in step:
                errors.append(f"Step {i} missing function_type_id")
                continue

            func_type = get_function_type(step["function_type_id"])
            if not func_type:
                errors.append(f"Step {i} references unknown function: {step['function_type_id']}")
                continue

            # Check parameter mappings
            mappings = step.get("parameter_mappings", {})
            for param in func_type.parameters:
                if param.direction == ParameterDirection.OUTPUT:
                    continue

                if param.is_required and param.name not in mappings:
                    errors.append(f"Step {i} missing required parameter mapping: {param.name}")

            # Add step output to available outputs
            available_outputs[f"step_{i}_output"] = True

        return errors
