"""
레이블 매핑 스키마 정의
TerminusDB에서 LabelMapping 클래스를 정의하는 스키마
"""

from typing import Dict, Any


def get_label_mapping_schema() -> Dict[str, Any]:
    """
    LabelMapping 클래스 스키마 반환
    
    Returns:
        LabelMapping 클래스 스키마
    """
    return {
        "@id": "LabelMapping",
        "@type": "Class",
        "rdfs:label": {
            "@language": "en",
            "@value": "Label Mapping"
        },
        "rdfs:comment": {
            "@language": "en", 
            "@value": "Stores mappings between user-friendly labels and internal IDs"
        },
        "rdfs:subClassOf": {
            "@id": "system:Document",
            "@type": "@id"
        }
    }


def get_label_mapping_properties() -> list[Dict[str, Any]]:
    """
    LabelMapping 클래스의 속성들 반환
    
    Returns:
        LabelMapping 속성 목록
    """
    return [
        {
            "@id": "db_name",
            "@type": "DataProperty",
            "rdfs:label": {
                "@language": "en",
                "@value": "Database Name"
            },
            "rdfs:comment": {
                "@language": "en",
                "@value": "Name of the database this mapping belongs to"
            },
            "rdfs:domain": {
                "@id": "LabelMapping",
                "@type": "@id"
            },
            "rdfs:range": {
                "@id": "xsd:string",
                "@type": "@id"
            }
        },
        {
            "@id": "mapping_type",
            "@type": "DataProperty",
            "rdfs:label": {
                "@language": "en",
                "@value": "Mapping Type"
            },
            "rdfs:comment": {
                "@language": "en",
                "@value": "Type of mapping: class, property, or relationship"
            },
            "rdfs:domain": {
                "@id": "LabelMapping",
                "@type": "@id"
            },
            "rdfs:range": {
                "@id": "xsd:string",
                "@type": "@id"
            }
        },
        {
            "@id": "target_id",
            "@type": "DataProperty",
            "rdfs:label": {
                "@language": "en",
                "@value": "Target ID"
            },
            "rdfs:comment": {
                "@language": "en",
                "@value": "The internal ID that this label maps to"
            },
            "rdfs:domain": {
                "@id": "LabelMapping",
                "@type": "@id"
            },
            "rdfs:range": {
                "@id": "xsd:string",
                "@type": "@id"
            }
        },
        {
            "@id": "label",
            "@type": "DataProperty",
            "rdfs:label": {
                "@language": "en",
                "@value": "Label"
            },
            "rdfs:comment": {
                "@language": "en",
                "@value": "The user-friendly label text"
            },
            "rdfs:domain": {
                "@id": "LabelMapping",
                "@type": "@id"
            },
            "rdfs:range": {
                "@id": "xsd:string",
                "@type": "@id"
            }
        },
        {
            "@id": "language",
            "@type": "DataProperty",
            "rdfs:label": {
                "@language": "en",
                "@value": "Language"
            },
            "rdfs:comment": {
                "@language": "en",
                "@value": "Language code for the label"
            },
            "rdfs:domain": {
                "@id": "LabelMapping",
                "@type": "@id"
            },
            "rdfs:range": {
                "@id": "xsd:string",
                "@type": "@id"
            }
        },
        {
            "@id": "description",
            "@type": "DataProperty",
            "rdfs:label": {
                "@language": "en",
                "@value": "Description"
            },
            "rdfs:comment": {
                "@language": "en",
                "@value": "Optional description for the mapping"
            },
            "rdfs:domain": {
                "@id": "LabelMapping",
                "@type": "@id"
            },
            "rdfs:range": {
                "@id": "xsd:string",
                "@type": "@id"
            }
        },
        {
            "@id": "class_id",
            "@type": "DataProperty",
            "rdfs:label": {
                "@language": "en",
                "@value": "Class ID"
            },
            "rdfs:comment": {
                "@language": "en",
                "@value": "Class ID for property mappings"
            },
            "rdfs:domain": {
                "@id": "LabelMapping",
                "@type": "@id"
            },
            "rdfs:range": {
                "@id": "xsd:string",
                "@type": "@id"
            }
        },
        {
            "@id": "created_at",
            "@type": "DataProperty",
            "rdfs:label": {
                "@language": "en",
                "@value": "Created At"
            },
            "rdfs:comment": {
                "@language": "en",
                "@value": "Creation timestamp"
            },
            "rdfs:domain": {
                "@id": "LabelMapping",
                "@type": "@id"
            },
            "rdfs:range": {
                "@id": "xsd:dateTime",
                "@type": "@id"
            }
        },
        {
            "@id": "updated_at",
            "@type": "DataProperty",
            "rdfs:label": {
                "@language": "en",
                "@value": "Updated At"
            },
            "rdfs:comment": {
                "@language": "en",
                "@value": "Last update timestamp"
            },
            "rdfs:domain": {
                "@id": "LabelMapping",
                "@type": "@id"
            },
            "rdfs:range": {
                "@id": "xsd:dateTime",
                "@type": "@id"
            }
        }
    ]


def get_label_mapping_ontology() -> Dict[str, Any]:
    """
    LabelMapping 전체 온톨로지 반환
    
    Returns:
        LabelMapping 온톨로지 딕셔너리
    """
    return {
        "@context": {
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "system": "http://terminusdb.com/schema/system#"
        },
        "classes": [get_label_mapping_schema()],
        "properties": get_label_mapping_properties()
    }