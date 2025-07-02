"""
Schema Converters - API 응답을 GraphQL 타입으로 변환하는 공통 함수
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from ...schema import (
    ObjectType, ObjectTypeConnection, Property, SharedProperty,
    StatusEnum, TypeClassEnum, ApplicableObjectType, ParameterSchema
)


def convert_object_type_response(data: Dict[str, Any]) -> ObjectType:
    """API 응답을 ObjectType으로 변환"""
    properties = []
    if data.get("properties"):
        properties = [convert_property(prop) for prop in data["properties"]]
    
    applicable_types = []
    if data.get("applicable_to"):
        applicable_types = [
            ApplicableObjectType(
                object_type=app["object_type"],
                description=app.get("description")
            )
            for app in data["applicable_to"]
        ]
    
    return ObjectType(
        id=data["id"],
        name=data["name"],
        display_name=data.get("display_name", data["name"]),
        description=data.get("description", ""),
        status=StatusEnum(data.get("status", "active")),
        type_class=TypeClassEnum(data.get("type_class", "standard")),
        interfaces=data.get("interfaces", []),
        properties=properties,
        metadata=data.get("metadata", {}),
        version=data.get("version", 1),
        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        created_by=data.get("created_by"),
        updated_by=data.get("updated_by"),
        tags=data.get("tags", []),
        is_deprecated=data.get("is_deprecated", False),
        deprecation_reason=data.get("deprecation_reason"),
        applicable_to=applicable_types
    )


def convert_object_type_connection(data: Dict[str, Any]) -> ObjectTypeConnection:
    """API 응답을 ObjectTypeConnection으로 변환"""
    items = [convert_object_type_response(item) for item in data.get("items", [])]
    
    return ObjectTypeConnection(
        items=items,
        total_count=data.get("total_count", len(items)),
        has_next_page=data.get("has_next_page", False),
        has_previous_page=data.get("has_previous_page", False)
    )


def convert_property(data: Dict[str, Any]) -> Property:
    """API 응답을 Property로 변환"""
    constraints = data.get("constraints", {})
    
    return Property(
        id=data["id"],
        name=data["name"],
        display_name=data.get("display_name", data["name"]),
        description=data.get("description", ""),
        type=data["type"],
        is_required=data.get("is_required", False),
        is_unique=data.get("is_unique", False),
        is_indexed=data.get("is_indexed", False),
        default_value=data.get("default_value"),
        allowed_values=data.get("allowed_values", []),
        min_value=constraints.get("min_value"),
        max_value=constraints.get("max_value"),
        min_length=constraints.get("min_length"),
        max_length=constraints.get("max_length"),
        pattern=constraints.get("pattern"),
        format=data.get("format"),
        metadata=data.get("metadata", {}),
        validation_rules=data.get("validation_rules", []),
        is_deprecated=data.get("is_deprecated", False),
        deprecation_reason=data.get("deprecation_reason")
    )


def convert_shared_property(data: Dict[str, Any]) -> SharedProperty:
    """API 응답을 SharedProperty로 변환"""
    property_data = convert_property(data)
    
    applicable_types = []
    if data.get("applicable_to"):
        applicable_types = [
            ApplicableObjectType(
                object_type=app["object_type"],
                description=app.get("description")
            )
            for app in data["applicable_to"]
        ]
    
    return SharedProperty(
        id=property_data.id,
        name=property_data.name,
        display_name=property_data.display_name,
        description=property_data.description,
        type=property_data.type,
        is_required=property_data.is_required,
        is_unique=property_data.is_unique,
        is_indexed=property_data.is_indexed,
        default_value=property_data.default_value,
        allowed_values=property_data.allowed_values,
        min_value=property_data.min_value,
        max_value=property_data.max_value,
        min_length=property_data.min_length,
        max_length=property_data.max_length,
        pattern=property_data.pattern,
        format=property_data.format,
        metadata=property_data.metadata,
        validation_rules=property_data.validation_rules,
        is_deprecated=property_data.is_deprecated,
        deprecation_reason=property_data.deprecation_reason,
        applicable_to=applicable_types,
        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        created_by=data.get("created_by"),
        updated_by=data.get("updated_by")
    )