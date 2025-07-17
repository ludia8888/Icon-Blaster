#!/usr/bin/env python3
"""
Test BFF Internal Data Processing
"""

import re
from shared.security.input_sanitizer import sanitize_input

def test_data_processing():
    """Test the data processing logic from BFF"""
    
    # Test data similar to what BFF receives
    test_ontology = {
        "label": "Test Class",
        "description": "Test description",
        "properties": []
    }
    
    print("Original data:")
    print(f"  {test_ontology}")
    
    # Simulate BFF processing
    print("\n1. After .dict() conversion (simulated):")
    ontology_dict = test_ontology  # Already a dict
    print(f"  {ontology_dict}")
    
    print("\n2. After sanitization:")
    sanitized_data = sanitize_input(ontology_dict)
    print(f"  {sanitized_data}")
    
    print("\n3. ID generation from label:")
    label = sanitized_data.get('label')
    if isinstance(label, dict):
        label_text = label.get('en') or label.get('ko') or "UnnamedClass"
    elif isinstance(label, str):
        label_text = label
    else:
        label_text = "UnnamedClass"
    
    print(f"  Label text: {label_text}")
    
    # Generate ID
    class_id = re.sub(r'[^\w\s]', '', label_text)
    class_id = ''.join(word.capitalize() for word in class_id.split())
    if class_id and class_id[0].isdigit():
        class_id = 'Class' + class_id
    if not class_id:
        class_id = "UnnamedClass"
    
    print(f"  Generated ID: {class_id}")
    
    sanitized_data['id'] = class_id
    
    print("\n4. Final data to send to OMS:")
    print(f"  {sanitized_data}")
    
    # Test with multilingual label
    print("\n\n=== Testing with multilingual label ===")
    multilingual_ontology = {
        "label": {"ko": "테스트", "en": "Test"},
        "description": {"ko": "설명", "en": "Description"},
        "properties": [
            {
                "name": "prop1",
                "type": "xsd:string",
                "label": {"en": "Property 1"}
            }
        ]
    }
    
    print("Original multilingual data:")
    print(f"  {multilingual_ontology}")
    
    sanitized_multi = sanitize_input(multilingual_ontology)
    print("\nAfter sanitization:")
    print(f"  {sanitized_multi}")
    
    # Check if sanitization is corrupting the data
    if 'properties' in sanitized_multi:
        print(f"\nProperties type: {type(sanitized_multi['properties'])}")
        if isinstance(sanitized_multi['properties'], list) and len(sanitized_multi['properties']) > 0:
            print(f"First property: {sanitized_multi['properties'][0]}")

if __name__ == "__main__":
    test_data_processing()