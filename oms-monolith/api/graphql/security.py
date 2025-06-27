"""
GraphQL Security Layer
Query complexity analysis, depth limiting, and rate limiting
"""
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum
import time

from graphql import (
    GraphQLSchema,
    FieldNode,
    FragmentDefinitionNode,
    DocumentNode,
    OperationDefinitionNode,
    validate,
    parse
)
from graphql.validation import ValidationRule
from graphql.language.visitor import Visitor

from utils.logger import get_logger

logger = get_logger(__name__)


class SecurityViolationType(str, Enum):
    """Types of security violations"""
    DEPTH_EXCEEDED = "depth_exceeded"
    COMPLEXITY_EXCEEDED = "complexity_exceeded"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    FIELD_DENIED = "field_denied"
    INTROSPECTION_DISABLED = "introspection_disabled"
    QUERY_SIZE_EXCEEDED = "query_size_exceeded"


@dataclass
class SecurityConfig:
    """Security configuration for GraphQL"""
    max_depth: int = 10                    # Maximum query depth
    max_complexity: int = 1000             # Maximum query complexity score
    max_query_size: int = 10000            # Maximum query string size in bytes
    enable_introspection: bool = False     # Allow introspection in production
    rate_limit_window: int = 60            # Rate limit window in seconds
    rate_limit_max_requests: int = 100     # Max requests per window
    complexity_multipliers: Dict[str, int] = None  # Field-specific complexity
    
    def __post_init__(self):
        if self.complexity_multipliers is None:
            self.complexity_multipliers = {
                # Expensive operations have higher multipliers
                "search": 10,
                "aggregate": 20,
                "export": 50,
                "bulkOperation": 100
            }


class QueryDepthValidator(Visitor):
    """
    Validates query depth to prevent deeply nested queries
    that could cause performance issues or stack overflow
    """
    
    def __init__(self, max_depth: int):
        self.max_depth = max_depth
        self.current_depth = 0
        self.max_depth_reached = 0
        self.errors = []
    
    def enter_field(self, node: FieldNode, *args):
        """Enter a field selection"""
        self.current_depth += 1
        self.max_depth_reached = max(self.max_depth_reached, self.current_depth)
        
        if self.current_depth > self.max_depth:
            self.errors.append({
                "type": SecurityViolationType.DEPTH_EXCEEDED,
                "message": f"Query depth {self.current_depth} exceeds maximum allowed depth of {self.max_depth}",
                "field": node.name.value,
                "depth": self.current_depth
            })
    
    def leave_field(self, node: FieldNode, *args):
        """Leave a field selection"""
        self.current_depth -= 1


class QueryComplexityAnalyzer(Visitor):
    """
    Analyzes query complexity to prevent expensive queries
    Assigns complexity scores based on field types and arguments
    """
    
    def __init__(self, config: SecurityConfig, schema: GraphQLSchema):
        self.config = config
        self.schema = schema
        self.complexity_score = 0
        self.field_scores = {}
        self.errors = []
    
    def enter_field(self, node: FieldNode, *args):
        """Calculate complexity for a field"""
        field_name = node.name.value
        
        # Base complexity
        base_score = 1
        
        # Check for custom multipliers
        if field_name in self.config.complexity_multipliers:
            base_score = self.config.complexity_multipliers[field_name]
        
        # Multiply by limit arguments (pagination amplification)
        arguments = {arg.name.value: arg.value for arg in (node.arguments or [])}
        
        # Common pagination arguments that multiply complexity
        limit = self._get_arg_value(arguments.get("limit"), 1)
        first = self._get_arg_value(arguments.get("first"), 1)
        last = self._get_arg_value(arguments.get("last"), 1)
        
        # Use the maximum of pagination arguments
        multiplier = max(limit, first, last, 1)
        
        # Calculate field score
        field_score = base_score * multiplier
        
        # Add to total
        self.complexity_score += field_score
        self.field_scores[field_name] = field_score
        
        # Check if complexity exceeded
        if self.complexity_score > self.config.max_complexity:
            self.errors.append({
                "type": SecurityViolationType.COMPLEXITY_EXCEEDED,
                "message": f"Query complexity {self.complexity_score} exceeds maximum allowed complexity of {self.config.max_complexity}",
                "field": field_name,
                "field_score": field_score,
                "total_score": self.complexity_score
            })
    
    def _get_arg_value(self, arg_node, default=1):
        """Extract numeric value from argument node"""
        if not arg_node:
            return default
        
        if hasattr(arg_node, 'value'):
            try:
                return int(arg_node.value)
            except:
                return default
        
        return default


class RateLimiter:
    """
    Rate limiter for GraphQL queries
    Uses sliding window algorithm
    """
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.requests: Dict[str, List[float]] = {}  # user_id -> timestamps
    
    def check_rate_limit(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Check if user has exceeded rate limit"""
        now = time.time()
        window_start = now - self.config.rate_limit_window
        
        # Get user's request timestamps
        if user_id not in self.requests:
            self.requests[user_id] = []
        
        # Remove old timestamps outside window
        self.requests[user_id] = [
            ts for ts in self.requests[user_id]
            if ts > window_start
        ]
        
        # Check limit
        request_count = len(self.requests[user_id])
        if request_count >= self.config.rate_limit_max_requests:
            return {
                "type": SecurityViolationType.RATE_LIMIT_EXCEEDED,
                "message": f"Rate limit exceeded: {request_count} requests in {self.config.rate_limit_window} seconds",
                "limit": self.config.rate_limit_max_requests,
                "window": self.config.rate_limit_window,
                "retry_after": int(self.requests[user_id][0] + self.config.rate_limit_window - now)
            }
        
        # Add current request
        self.requests[user_id].append(now)
        
        # Clean up old users periodically
        if len(self.requests) > 10000:
            self._cleanup_old_users(window_start)
        
        return None
    
    def _cleanup_old_users(self, window_start: float):
        """Remove users with no recent requests"""
        to_remove = []
        for user_id, timestamps in self.requests.items():
            if not timestamps or timestamps[-1] < window_start:
                to_remove.append(user_id)
        
        for user_id in to_remove:
            del self.requests[user_id]


class GraphQLSecurityValidator:
    """
    Main security validator that combines all security checks
    """
    
    def __init__(self, config: SecurityConfig, schema: GraphQLSchema):
        self.config = config
        self.schema = schema
        self.rate_limiter = RateLimiter(config)
    
    def validate_query(
        self,
        query: str,
        user_id: Optional[str] = None,
        user_roles: Optional[List[str]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Validate a GraphQL query against security rules
        Returns list of security violations, or None if valid
        """
        errors = []
        
        # 1. Check query size
        if len(query.encode('utf-8')) > self.config.max_query_size:
            errors.append({
                "type": SecurityViolationType.QUERY_SIZE_EXCEEDED,
                "message": f"Query size exceeds maximum allowed size of {self.config.max_query_size} bytes"
            })
            return errors  # Don't process further if query is too large
        
        # 2. Parse query
        try:
            document = parse(query)
        except Exception as e:
            # Not a security error, but prevents further validation
            return None
        
        # 3. Check for introspection
        if not self.config.enable_introspection and self._has_introspection(document):
            errors.append({
                "type": SecurityViolationType.INTROSPECTION_DISABLED,
                "message": "Introspection queries are disabled"
            })
        
        # 4. Check rate limit
        if user_id:
            rate_limit_error = self.rate_limiter.check_rate_limit(user_id)
            if rate_limit_error:
                errors.append(rate_limit_error)
        
        # 5. Check query depth
        depth_validator = QueryDepthValidator(self.config.max_depth)
        for operation in document.definitions:
            if isinstance(operation, OperationDefinitionNode):
                depth_validator.visit(operation)
        
        errors.extend(depth_validator.errors)
        
        # 6. Check query complexity
        complexity_analyzer = QueryComplexityAnalyzer(self.config, self.schema)
        for operation in document.definitions:
            if isinstance(operation, OperationDefinitionNode):
                complexity_analyzer.visit(operation)
        
        errors.extend(complexity_analyzer.errors)
        
        # 7. Log security events
        if errors:
            logger.warning(
                f"GraphQL security violations for user {user_id}: "
                f"{[e['type'] for e in errors]}"
            )
        
        return errors if errors else None
    
    def _has_introspection(self, document: DocumentNode) -> bool:
        """Check if query contains introspection fields"""
        introspection_fields = {
            "__schema",
            "__type",
            "__typename",
            "__directive",
            "__enumValue",
            "__field",
            "__inputValue"
        }
        
        for operation in document.definitions:
            if isinstance(operation, OperationDefinitionNode):
                if self._check_fields_for_introspection(
                    operation.selection_set.selections,
                    introspection_fields
                ):
                    return True
        
        return False
    
    def _check_fields_for_introspection(
        self,
        selections: List[Any],
        introspection_fields: Set[str]
    ) -> bool:
        """Recursively check fields for introspection"""
        for selection in selections:
            if isinstance(selection, FieldNode):
                if selection.name.value in introspection_fields:
                    return True
                
                if selection.selection_set:
                    if self._check_fields_for_introspection(
                        selection.selection_set.selections,
                        introspection_fields
                    ):
                        return True
        
        return False


class SecurityMiddleware:
    """
    GraphQL middleware that enforces security policies
    """
    
    def __init__(self, config: SecurityConfig, schema: GraphQLSchema):
        self.validator = GraphQLSecurityValidator(config, schema)
    
    async def process_request(self, request, user_context):
        """Process GraphQL request with security checks"""
        # Extract query from request
        query = request.get("query", "")
        
        # Get user info
        user_id = None
        user_roles = []
        if user_context:
            user_id = getattr(user_context, "user_id", None)
            user_roles = getattr(user_context, "roles", [])
        
        # Validate query
        violations = self.validator.validate_query(query, user_id, user_roles)
        
        if violations:
            # Build error response
            return {
                "errors": [
                    {
                        "message": v["message"],
                        "extensions": {
                            "code": v["type"],
                            **{k: v for k, v in v.items() if k not in ["type", "message"]}
                        }
                    }
                    for v in violations
                ]
            }
        
        return None  # No security violations


# Production-ready security configuration
PRODUCTION_SECURITY_CONFIG = SecurityConfig(
    max_depth=7,
    max_complexity=500,
    max_query_size=5000,
    enable_introspection=False,
    rate_limit_window=60,
    rate_limit_max_requests=60,
    complexity_multipliers={
        "search": 20,
        "aggregate": 50,
        "export": 100,
        "bulkOperation": 200,
        "deepSearch": 30,
        "relationships": 10
    }
)

# Development security configuration (more permissive)
DEVELOPMENT_SECURITY_CONFIG = SecurityConfig(
    max_depth=15,
    max_complexity=2000,
    max_query_size=50000,
    enable_introspection=True,
    rate_limit_window=60,
    rate_limit_max_requests=1000
)