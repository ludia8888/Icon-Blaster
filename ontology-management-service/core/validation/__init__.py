# Validation Service Core Package

# Lazy import to prevent circular dependencies
def get_validation_service():
    from .service import ValidationService
    return ValidationService

# Direct imports
from .models import ValidationResult, ValidationContext
from .naming_config import NamingConfigService as NamingConfig
from .naming_convention import NamingConvention
from .naming_history import NamingConventionHistoryService as NamingHistory
from .policy_signing import PolicySigner
from .schema_validator import JsonSchemaValidator as SchemaValidator
from .version_manager import VersionManager
from .service import ValidationService

__all__ = [
    "get_validation_service",
    "ValidationService",
    "ValidationResult",
    "ValidationContext",
    "NamingConfig",
    "NamingConvention",
    "NamingHistory",
    "PolicySigner",
    "SchemaValidator",
    "VersionManager"
]
