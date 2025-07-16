"""
Shared models for OMS and BFF services
"""

from .ontology import (
    OntologyBase,
    OntologyCreateRequest,
    OntologyUpdateRequest,
    OntologyResponse,
    MultiLingualText,
    Property,
    Relationship,
    QueryRequest,
    QueryResponse,
    QueryFilter,
    QueryOperator
)

from .common import (
    BaseModel,
    TimestampMixin,
    PaginationRequest,
    PaginationResponse
)

__all__ = [
    "OntologyBase",
    "OntologyCreateRequest", 
    "OntologyUpdateRequest",
    "OntologyResponse",
    "MultiLingualText",
    "Property",
    "Relationship",
    "QueryRequest",
    "QueryResponse", 
    "QueryFilter",
    "QueryOperator",
    "BaseModel",
    "TimestampMixin",
    "PaginationRequest",
    "PaginationResponse"
]