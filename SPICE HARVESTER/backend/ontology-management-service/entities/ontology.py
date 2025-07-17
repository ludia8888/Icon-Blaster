"""
온톨로지 도메인 엔티티
비즈니스 로직을 포함한 도메인 객체
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from value_objects.multilingual_text import MultiLingualText


@dataclass
class Property:
    """속성 엔티티"""
    name: str
    type: str
    label: MultiLingualText
    required: bool = False
    default: Optional[Any] = None
    description: Optional[MultiLingualText] = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    
    def validate_value(self, value: Any) -> List[str]:
        """값 유효성 검증"""
        errors = []
        
        if self.required and value is None:
            errors.append(f"Property '{self.name}' is required")
        
        # 타입 검증
        if value is not None:
            if self.type == "xsd:string" and not isinstance(value, str):
                errors.append(f"Property '{self.name}' must be a string")
            elif self.type == "xsd:integer" and not isinstance(value, int):
                errors.append(f"Property '{self.name}' must be an integer")
            elif self.type == "xsd:boolean" and not isinstance(value, bool):
                errors.append(f"Property '{self.name}' must be a boolean")
        
        # 제약조건 검증
        if self.constraints and value is not None:
            if "min" in self.constraints and value < self.constraints["min"]:
                errors.append(f"Property '{self.name}' must be >= {self.constraints['min']}")
            if "max" in self.constraints and value > self.constraints["max"]:
                errors.append(f"Property '{self.name}' must be <= {self.constraints['max']}")
            if "pattern" in self.constraints:
                import re
                if not re.match(self.constraints["pattern"], str(value)):
                    errors.append(f"Property '{self.name}' does not match pattern")
        
        return errors


@dataclass
class Relationship:
    """관계 엔티티"""
    predicate: str
    target: str
    label: MultiLingualText
    cardinality: str = "1:n"
    description: Optional[MultiLingualText] = None
    inverse_predicate: Optional[str] = None
    inverse_label: Optional[MultiLingualText] = None
    
    def is_valid_cardinality(self) -> bool:
        """카디널리티 유효성 확인"""
        valid_cardinalities = ["1:1", "1:n", "n:1", "n:m"]
        return self.cardinality in valid_cardinalities


@dataclass
class Ontology:
    """온톨로지 엔티티"""
    id: str
    label: MultiLingualText
    description: Optional[MultiLingualText] = None
    parent_class: Optional[str] = None
    abstract: bool = False
    properties: List[Property] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """초기화 후 처리"""
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()
    
    def add_property(self, property: Property) -> None:
        """속성 추가"""
        if any(p.name == property.name for p in self.properties):
            raise ValueError(f"Property '{property.name}' already exists")
        self.properties.append(property)
        self.updated_at = datetime.utcnow()
    
    def remove_property(self, property_name: str) -> bool:
        """속성 제거"""
        initial_count = len(self.properties)
        self.properties = [p for p in self.properties if p.name != property_name]
        if len(self.properties) < initial_count:
            self.updated_at = datetime.utcnow()
            return True
        return False
    
    def add_relationship(self, relationship: Relationship) -> None:
        """관계 추가"""
        if any(r.predicate == relationship.predicate for r in self.relationships):
            raise ValueError(f"Relationship '{relationship.predicate}' already exists")
        if not relationship.is_valid_cardinality():
            raise ValueError(f"Invalid cardinality: {relationship.cardinality}")
        self.relationships.append(relationship)
        self.updated_at = datetime.utcnow()
    
    def validate(self) -> List[str]:
        """엔티티 유효성 검증"""
        errors = []
        
        if not self.id:
            errors.append("Ontology ID is required")
        
        if not self.label or not self.label.has_any_value():
            errors.append("Ontology label is required")
        
        # 속성 이름 중복 확인
        property_names = [p.name for p in self.properties]
        if len(property_names) != len(set(property_names)):
            errors.append("Duplicate property names found")
        
        # 관계 검증
        for rel in self.relationships:
            if not rel.is_valid_cardinality():
                errors.append(f"Invalid cardinality for relationship '{rel.predicate}'")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "id": self.id,
            "label": self.label.to_dict(),
            "description": self.description.to_dict() if self.description else None,
            "parent_class": self.parent_class,
            "abstract": self.abstract,
            "properties": [
                {
                    "name": p.name,
                    "type": p.type,
                    "label": p.label.to_dict(),
                    "required": p.required,
                    "default": p.default,
                    "description": p.description.to_dict() if p.description else None,
                    "constraints": p.constraints
                }
                for p in self.properties
            ],
            "relationships": [
                {
                    "predicate": r.predicate,
                    "target": r.target,
                    "label": r.label.to_dict(),
                    "cardinality": r.cardinality,
                    "description": r.description.to_dict() if r.description else None,
                    "inverse_predicate": r.inverse_predicate,
                    "inverse_label": r.inverse_label.to_dict() if r.inverse_label else None
                }
                for r in self.relationships
            ],
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }