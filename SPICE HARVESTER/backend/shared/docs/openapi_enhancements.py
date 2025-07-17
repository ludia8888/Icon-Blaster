"""
Enhanced OpenAPI Documentation Configuration
Provides comprehensive API documentation with examples, authentication, and detailed schemas
"""

from typing import Dict, Any, List, Optional
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
import json


class OpenAPIEnhancer:
    """
    Enhances FastAPI OpenAPI documentation with production-grade features
    
    Features:
    - Detailed endpoint descriptions
    - Request/response examples
    - Authentication documentation
    - Error response schemas
    - Rate limiting information
    - Security considerations
    """
    
    def __init__(self, app: FastAPI):
        self.app = app
    
    def enhance_openapi_schema(self) -> Dict[str, Any]:
        """Generate enhanced OpenAPI schema"""
        
        if self.app.openapi_schema:
            return self.app.openapi_schema
        
        # Generate base schema
        openapi_schema = get_openapi(
            title="SPICE HARVESTER API",
            version="2.0.0",
            description=self._get_api_description(),
            routes=self.app.routes,
            servers=[
                {
                    "url": "http://localhost:8002",
                    "description": "BFF Development Server"
                },
                {
                    "url": "http://localhost:8000", 
                    "description": "OMS Development Server"
                }
            ]
        )
        
        # Add custom enhancements
        self._add_security_schemes(openapi_schema)
        self._add_examples(openapi_schema)
        self._add_error_responses(openapi_schema)
        self._add_rate_limiting_info(openapi_schema)
        self._add_custom_tags(openapi_schema)
        
        self.app.openapi_schema = openapi_schema
        return openapi_schema
    
    def _get_api_description(self) -> str:
        """Get comprehensive API description"""
        return """
## SPICE HARVESTER - Ontology Management System

A production-grade, microservices-based platform for managing ontologies with multilingual support.

### Key Features

- **Multilingual Ontology Management**: Create and manage ontologies with support for Korean, English, Japanese, and Chinese
- **Git-like Version Control**: Branch, merge, and rollback capabilities for ontology versioning
- **Label-based User Interface**: User-friendly Korean labels mapped to technical identifiers
- **Production-grade Security**: Input validation, rate limiting, and comprehensive error handling
- **Scalable Architecture**: Microservices design with BFF (Backend for Frontend) pattern

### Architecture

The system consists of two main services:

1. **BFF (Backend for Frontend)** - Port 8002
   - User-friendly API with Korean labels
   - Input validation and sanitization
   - Rate limiting and security middleware
   - Label mapping management

2. **OMS (Ontology Management Service)** - Port 8000
   - Core ontology management logic
   - Database operations
   - TerminusDB integration
   - Version control operations

### Authentication

Currently using API key authentication. Future versions will support:
- JWT tokens
- OAuth 2.0
- Role-based access control (RBAC)

### Rate Limiting

- 100 requests per minute per IP
- 1000 requests per hour per IP
- Burst allowance of 50 requests

### Error Handling

All endpoints return standardized error responses with:
- Request ID for tracing
- Detailed error messages (development only)
- Appropriate HTTP status codes
- Security-conscious error handling
        """
    
    def _add_security_schemes(self, schema: Dict[str, Any]) -> None:
        """Add security scheme definitions"""
        if "components" not in schema:
            schema["components"] = {}
        
        schema["components"]["securitySchemes"] = {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "API key for authentication"
            },
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT token authentication (future)"
            }
        }
        
        # Add global security requirement
        schema["security"] = [
            {"ApiKeyAuth": []}
        ]
    
    def _add_examples(self, schema: Dict[str, Any]) -> None:
        """Add request/response examples to endpoints"""
        
        examples = {
            # Database Operations
            "DatabaseCreateRequest": {
                "summary": "Create a new database",
                "value": {
                    "name": "my_ontology_db",
                    "description": "Database for storing product ontologies"
                }
            },
            "DatabaseCreateResponse": {
                "summary": "Successful database creation",
                "value": {
                    "status": "success",
                    "message": "데이터베이스 'my_ontology_db'가 생성되었습니다",
                    "name": "my_ontology_db",
                    "data": {
                        "created_at": "2024-07-17T10:30:00Z",
                        "id": "db_123456"
                    }
                }
            },
            
            # Ontology Operations
            "OntologyCreateRequest": {
                "summary": "Create a new ontology class",
                "value": {
                    "label": {
                        "ko": "제품",
                        "en": "Product"
                    },
                    "description": {
                        "ko": "전자상거래 제품을 나타내는 클래스",
                        "en": "Class representing e-commerce products"
                    },
                    "properties": [
                        {
                            "name": "productName",
                            "type": "xsd:string",
                            "label": {
                                "ko": "제품명",
                                "en": "Product Name"
                            },
                            "required": True
                        },
                        {
                            "name": "price",
                            "type": "xsd:decimal",
                            "label": {
                                "ko": "가격",
                                "en": "Price"
                            },
                            "required": True
                        }
                    ]
                }
            },
            
            # Branch Operations
            "BranchCreateRequest": {
                "summary": "Create a new branch",
                "value": {
                    "branch_name": "feature-new-products",
                    "from_branch": "main"
                }
            },
            "MergeRequest": {
                "summary": "Merge branches",
                "value": {
                    "source_branch": "feature-new-products",
                    "target_branch": "main",
                    "strategy": "merge",
                    "message": "Add new product categories",
                    "author": "developer@company.com"
                }
            },
            
            # Query Operations
            "QueryRequest": {
                "summary": "Query ontology data",
                "value": {
                    "query_type": "list_classes",
                    "filters": {
                        "label_contains": "제품"
                    },
                    "limit": 10,
                    "offset": 0
                }
            },
            
            # Error Responses
            "ValidationError": {
                "summary": "Validation error response",
                "value": {
                    "error": {
                        "type": "validation_error",
                        "message": "Request validation failed",
                        "timestamp": "2024-07-17T10:30:00Z",
                        "status_code": 422,
                        "request_id": "req_123456789",
                        "path": "/api/v1/database"
                    }
                }
            },
            "NotFoundError": {
                "summary": "Resource not found",
                "value": {
                    "error": {
                        "type": "not_found_error",
                        "message": "Database 'invalid_db' not found",
                        "timestamp": "2024-07-17T10:30:00Z",
                        "status_code": 404,
                        "request_id": "req_987654321"
                    }
                }
            },
            "RateLimitError": {
                "summary": "Rate limit exceeded",
                "value": {
                    "error": {
                        "type": "rate_limit_error",
                        "message": "Too many requests. Please try again later.",
                        "timestamp": "2024-07-17T10:30:00Z",
                        "status_code": 429,
                        "request_id": "req_555666777"
                    }
                }
            }
        }
        
        # Add examples to schema components
        if "components" not in schema:
            schema["components"] = {}
        if "examples" not in schema["components"]:
            schema["components"]["examples"] = {}
        
        schema["components"]["examples"].update(examples)
    
    def _add_error_responses(self, schema: Dict[str, Any]) -> None:
        """Add standardized error response schemas"""
        
        if "components" not in schema:
            schema["components"] = {}
        if "schemas" not in schema["components"]:
            schema["components"]["schemas"] = {}
        
        error_schemas = {
            "ErrorResponse": {
                "type": "object",
                "properties": {
                    "error": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "validation_error",
                                    "authentication_error", 
                                    "authorization_error",
                                    "not_found_error",
                                    "conflict_error",
                                    "rate_limit_error",
                                    "external_service_error",
                                    "system_error"
                                ],
                                "description": "Error type category"
                            },
                            "message": {
                                "type": "string",
                                "description": "Human-readable error message"
                            },
                            "timestamp": {
                                "type": "string",
                                "format": "date-time",
                                "description": "Error occurrence timestamp"
                            },
                            "status_code": {
                                "type": "integer",
                                "description": "HTTP status code"
                            },
                            "request_id": {
                                "type": "string",
                                "description": "Unique request identifier for tracing"
                            },
                            "path": {
                                "type": "string",
                                "description": "Request path that caused the error"
                            },
                            "details": {
                                "type": "string",
                                "description": "Detailed error information (development only)"
                            }
                        },
                        "required": ["type", "message", "timestamp", "status_code"]
                    }
                },
                "required": ["error"]
            },
            "ValidationErrorResponse": {
                "type": "object",
                "properties": {
                    "error": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["validation_error"]
                            },
                            "message": {
                                "type": "string"
                            },
                            "field_errors": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "field": {"type": "string"},
                                        "message": {"type": "string"},
                                        "type": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        schema["components"]["schemas"].update(error_schemas)
    
    def _add_rate_limiting_info(self, schema: Dict[str, Any]) -> None:
        """Add rate limiting information to the schema"""
        
        if "info" not in schema:
            schema["info"] = {}
        
        if "x-rateLimit" not in schema["info"]:
            schema["info"]["x-rateLimit"] = {
                "requests_per_minute": 100,
                "requests_per_hour": 1000,
                "burst_allowance": 50,
                "headers": {
                    "X-RateLimit-Remaining": "Number of requests remaining in current window",
                    "X-RateLimit-Reset": "Time when rate limit window resets",
                    "Retry-After": "Seconds to wait before retrying (when rate limited)"
                }
            }
    
    def _add_custom_tags(self, schema: Dict[str, Any]) -> None:
        """Add custom tags with descriptions"""
        
        schema["tags"] = [
            {
                "name": "Health",
                "description": "Service health and status endpoints",
                "externalDocs": {
                    "description": "Health Check Documentation",
                    "url": "https://docs.example.com/health"
                }
            },
            {
                "name": "Database",
                "description": "Database management operations",
                "externalDocs": {
                    "description": "Database Management Guide",
                    "url": "https://docs.example.com/databases"
                }
            },
            {
                "name": "Ontology", 
                "description": "Ontology CRUD operations with multilingual support",
                "externalDocs": {
                    "description": "Ontology Management Guide",
                    "url": "https://docs.example.com/ontologies"
                }
            },
            {
                "name": "Query",
                "description": "Data querying and retrieval operations",
                "externalDocs": {
                    "description": "Query API Reference",
                    "url": "https://docs.example.com/queries"
                }
            },
            {
                "name": "Label Mappings",
                "description": "Label mapping import/export operations",
                "externalDocs": {
                    "description": "Label Mapping Guide",
                    "url": "https://docs.example.com/mappings"
                }
            },
            {
                "name": "Branch Management",
                "description": "Git-like branch operations for version control",
                "externalDocs": {
                    "description": "Version Control Guide",
                    "url": "https://docs.example.com/branching"
                }
            }
        ]


def setup_enhanced_openapi(app: FastAPI) -> None:
    """Setup enhanced OpenAPI documentation for FastAPI app"""
    
    enhancer = OpenAPIEnhancer(app)
    
    # Override the openapi method
    def custom_openapi():
        return enhancer.enhance_openapi_schema()
    
    app.openapi = custom_openapi
    
    # Add custom OpenAPI endpoint descriptions
    _add_endpoint_descriptions(app)


def _add_endpoint_descriptions(app: FastAPI) -> None:
    """Add detailed descriptions to specific endpoints"""
    
    # This would be used to add detailed descriptions to specific endpoints
    # For now, we'll document the pattern for future use
    
    endpoint_descriptions = {
        "/health": {
            "summary": "Health Check",
            "description": """
            Comprehensive health check endpoint that verifies:
            - Service availability
            - Database connectivity
            - External service dependencies
            - System resource status
            
            Returns 200 when all systems are operational, 503 when dependencies are unavailable.
            """
        },
        "/api/v1/database": {
            "summary": "Create Database",
            "description": """
            Creates a new ontology database with the specified name and description.
            
            **Security Considerations:**
            - Database names are validated for SQL injection
            - Rate limiting applies (max 10 database creations per hour)
            - Requires valid API key authentication
            
            **Business Rules:**
            - Database names must be unique
            - Names must start with a letter
            - Only alphanumeric characters, hyphens, and underscores allowed
            """
        },
        "/database/{db_name}/ontology": {
            "summary": "Create Ontology Class",
            "description": """
            Creates a new ontology class within the specified database.
            
            **Multilingual Support:**
            - Labels and descriptions support Korean, English, Japanese, Chinese
            - Automatic ID generation from Korean labels
            - Fallback language handling
            
            **Validation:**
            - Property names must follow camelCase convention
            - Data types must be valid XSD types
            - Circular dependencies are prevented
            """
        }
    }
    
    # Note: In practice, these descriptions would be added to the route decorators
    # or through FastAPI's response_model and other parameters


def generate_api_documentation_json(app: FastAPI) -> str:
    """Generate complete API documentation as JSON"""
    
    enhancer = OpenAPIEnhancer(app)
    schema = enhancer.enhance_openapi_schema()
    
    return json.dumps(schema, indent=2, ensure_ascii=False)


def generate_postman_collection(app: FastAPI) -> Dict[str, Any]:
    """Generate Postman collection from OpenAPI schema"""
    
    enhancer = OpenAPIEnhancer(app)
    schema = enhancer.enhance_openapi_schema()
    
    # Basic Postman collection structure
    collection = {
        "info": {
            "name": "SPICE HARVESTER API",
            "description": schema["info"]["description"],
            "version": schema["info"]["version"],
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "item": [],
        "auth": {
            "type": "apikey",
            "apikey": [
                {
                    "key": "key",
                    "value": "X-API-Key",
                    "type": "string"
                },
                {
                    "key": "value",
                    "value": "{{api_key}}",
                    "type": "string"
                }
            ]
        },
        "variable": [
            {
                "key": "base_url",
                "value": "http://localhost:8002",
                "type": "string"
            },
            {
                "key": "api_key",
                "value": "your_api_key_here",
                "type": "string"
            }
        ]
    }
    
    # Add requests for each endpoint
    for path, methods in schema.get("paths", {}).items():
        for method, details in methods.items():
            if method.upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                request_item = {
                    "name": details.get("summary", f"{method.upper()} {path}"),
                    "request": {
                        "method": method.upper(),
                        "header": [
                            {
                                "key": "Content-Type",
                                "value": "application/json",
                                "type": "text"
                            }
                        ],
                        "url": {
                            "raw": "{{base_url}}" + path,
                            "host": ["{{base_url}}"],
                            "path": path.strip("/").split("/") if path != "/" else []
                        },
                        "description": details.get("description", "")
                    }
                }
                
                # Add request body if applicable
                if method.upper() in ["POST", "PUT", "PATCH"] and "requestBody" in details:
                    request_item["request"]["body"] = {
                        "mode": "raw",
                        "raw": json.dumps({
                            "example": "Add example request body here"
                        }, indent=2),
                        "options": {
                            "raw": {
                                "language": "json"
                            }
                        }
                    }
                
                collection["item"].append(request_item)
    
    return collection


if __name__ == "__main__":
    # Example usage
    from fastapi import FastAPI
    
    app = FastAPI()
    setup_enhanced_openapi(app)
    
    # Generate documentation
    docs_json = generate_api_documentation_json(app)
    postman_collection = generate_postman_collection(app)
    
    print("Enhanced OpenAPI documentation generated successfully!")
    print(f"Documentation size: {len(docs_json)} characters")
    print(f"Postman collection items: {len(postman_collection['item'])}")