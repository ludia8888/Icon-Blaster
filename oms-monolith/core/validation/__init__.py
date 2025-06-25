# Validation Service Core Package

# Lazy import to prevent circular dependencies
def get_validation_service():
    from .service import ValidationService
    return ValidationService

__all__ = ["get_validation_service"]
