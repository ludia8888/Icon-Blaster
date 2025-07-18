#!/usr/bin/env python3
"""
🔥 THINK ULTRA!! Debug TerminusDB Complex Type Conversion
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'shared'))

from models.common import DataType

def test_data_structure():
    """Test the actual data structure that gets passed to create_ontology_class"""
    
    # Simulate the exact data structure from OntologyCreateRequest
    test_ontology_data = {
        "id": "TestClass",
        "label": "Test Class with Complex Types",
        "description": "A test class with phone and email fields",
        "properties": [
            {
                "name": "phone_number",
                "type": "custom:phone",
                "required": True,
                "constraints": {
                    "format": "E164"
                }
            },
            {
                "name": "email_address", 
                "type": "custom:email",
                "required": True
            },
            {
                "name": "name",
                "type": "xsd:string",
                "required": True
            }
        ]
    }
    
    print("🔥 THINK ULTRA!! Testing exact data structure conversion")
    print("="*60)
    print(f"Original data: {test_ontology_data}")
    
    # Simulate the conversion logic from create_ontology_class
    schema_doc = {
        "@type": "Class",
        "@id": test_ontology_data.get("id")
    }
    
    # Process properties exactly like the real method
    if "properties" in test_ontology_data:
        for prop in test_ontology_data["properties"]:
            prop_name = prop.get("name")
            prop_type = prop.get("type", "xsd:string")
            if prop_name:
                # 🔥 The exact conversion logic
                if DataType.is_complex_type(prop_type):
                    base_type = DataType.get_base_type(prop_type)
                    schema_doc[prop_name] = base_type
                    print(f"🔥 CONVERTED: {prop_type} -> {base_type} for {prop_name}")
                else:
                    schema_doc[prop_name] = prop_type
                    print(f"🔥 UNCHANGED: {prop_type} for {prop_name}")
    
    print(f"\nFinal schema_doc sent to TerminusDB:")
    print(f"{schema_doc}")
    
    # Check if any custom: types remain
    has_custom_types = any(
        isinstance(v, str) and v.startswith("custom:") 
        for v in schema_doc.values()
    )
    
    print(f"\n🔥 CRITICAL CHECK: Has custom: types remaining? {has_custom_types}")
    
    return schema_doc

if __name__ == "__main__":
    test_data_structure()