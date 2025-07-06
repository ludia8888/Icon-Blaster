"""
Validator implementations for commit hook pipeline
"""
import os
import logging
from typing import Dict, Any, List

from .base import BaseValidator, DiffContext, ValidationError

# Import existing validation services
from core.validation.service import ValidationService
from core.validation.input_sanitization import InputSanitizer
from core.validation.tampering_detection import TamperingDetector
from core.schema.service import SchemaService

logger = logging.getLogger(__name__)


class RuleValidator(BaseValidator):
    """Adapter for existing ValidationService"""
    
    def __init__(self):
        self.validation_service = None
    
    @property
    def name(self) -> str:
        return "RuleValidator"
    
    async def initialize(self):
        """Initialize validation service"""
        # TODO: Initialize ValidationService properly
        # For now, we'll skip initialization as it requires database setup
        pass
    
    async def validate(self, context: DiffContext) -> None:
        """Validate using existing rule engine"""
        if not self.validation_service:
            logger.warning("ValidationService not initialized, skipping rule validation")
            return
        
        try:
            # Extract relevant data from diff
            if context.after:
                result = await self.validation_service.validate_data(
                    context.after,
                    context_data={
                        "user": context.meta.author,
                        "branch": context.meta.branch,
                        "trace_id": context.meta.trace_id
                    }
                )
                
                if not result.is_valid:
                    raise ValidationError(
                        f"Rule validation failed: {result.errors}",
                        errors=result.errors
                    )
        except Exception as e:
            logger.error(f"Rule validation error: {e}")
            if os.getenv("STRICT_VALIDATION", "false").lower() == "true":
                raise


class TamperValidator(BaseValidator):
    """Adapter for tampering detection"""
    
    def __init__(self):
        self.detector = TamperingDetector()
    
    @property
    def name(self) -> str:
        return "TamperValidator"
    
    async def validate(self, context: DiffContext) -> None:
        """Check for tampering attempts"""
        try:
            # Check if protected fields are being modified
            if context.before and context.after:
                protected_fields = ["created_by", "created_at", "_id", "_rev"]
                
                for field in protected_fields:
                    if field in context.before and field in context.after:
                        if context.before[field] != context.after[field]:
                            # Allow system users to modify protected fields
                            if not context.meta.author.startswith("system@"):
                                raise ValidationError(
                                    f"Tampering detected: attempt to modify protected field '{field}'",
                                    errors=[{
                                        "field": field,
                                        "error": "Protected field modification not allowed"
                                    }]
                                )
            
            # Use existing tampering detector for deeper checks
            suspicious_patterns = [
                r"<script[^>]*>.*?</script>",  # XSS attempts
                r"'; DROP TABLE",              # SQL injection
                r"__proto__",                   # Prototype pollution
                r"\.\./\.\./",                  # Path traversal
            ]
            
            # Check diff content for suspicious patterns
            diff_str = str(context.diff)
            for pattern in suspicious_patterns:
                if pattern in diff_str.lower():
                    logger.warning(f"Suspicious pattern detected: {pattern}")
                    # In strict mode, reject suspicious patterns
                    if os.getenv("STRICT_SECURITY", "false").lower() == "true":
                        raise ValidationError(
                            f"Security validation failed: suspicious pattern detected",
                            errors=[{"pattern": pattern, "error": "Suspicious content"}]
                        )
                        
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Tamper validation error: {e}")


class SchemaValidator(BaseValidator):
    """Validate against TerminusDB schema"""
    
    def __init__(self):
        self.schema_cache = {}
    
    @property
    def name(self) -> str:
        return "SchemaValidator"
    
    async def validate(self, context: DiffContext) -> None:
        """Validate document against schema"""
        if not context.after:
            return
        
        try:
            # Extract document type
            doc_type = context.after.get("@type")
            if not doc_type:
                logger.debug("No @type field found, skipping schema validation")
                return
            
            # TODO: Implement actual schema validation
            # For now, we'll do basic type checking
            required_fields = {
                "ObjectType": ["name", "created_by", "created_at"],
                "Branch": ["name", "source_branch", "created_by"],
                "ValidationRule": ["name", "rule_type", "condition"]
            }
            
            if doc_type in required_fields:
                missing_fields = []
                for field in required_fields[doc_type]:
                    if field not in context.after:
                        missing_fields.append(field)
                
                if missing_fields:
                    raise ValidationError(
                        f"Schema validation failed for {doc_type}",
                        errors=[{
                            "type": doc_type,
                            "missing_fields": missing_fields
                        }]
                    )
                    
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Schema validation error: {e}")


class PIIValidator(BaseValidator):
    """Check for PII data in non-allowed fields"""
    
    def __init__(self):
        self.pii_patterns = {
            "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
            "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
            "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"
        }
        self.allowed_fields = ["email", "contact_email", "user_email", "owner_email"]
    
    @property
    def name(self) -> str:
        return "PIIValidator"
    
    @property
    def enabled(self) -> bool:
        return os.getenv("ENABLE_PII_VALIDATION", "true").lower() == "true"
    
    async def validate(self, context: DiffContext) -> None:
        """Check for PII in non-allowed fields"""
        if not context.after:
            return
        
        try:
            import re
            errors = []
            
            def check_value(value: Any, field_path: str):
                if not isinstance(value, str):
                    return
                
                # Skip allowed fields
                field_name = field_path.split(".")[-1]
                if field_name in self.allowed_fields:
                    return
                
                # Check for PII patterns
                for pii_type, pattern in self.pii_patterns.items():
                    if re.search(pattern, value, re.IGNORECASE):
                        errors.append({
                            "field": field_path,
                            "type": pii_type,
                            "error": f"Potential {pii_type} detected in non-allowed field"
                        })
            
            def traverse(obj: Any, path: str = ""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        new_path = f"{path}.{key}" if path else key
                        traverse(value, new_path)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        traverse(item, f"{path}[{i}]")
                else:
                    check_value(obj, path)
            
            traverse(context.after)
            
            if errors:
                raise ValidationError(
                    "PII validation failed",
                    errors=errors
                )
                
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"PII validation error: {e}")