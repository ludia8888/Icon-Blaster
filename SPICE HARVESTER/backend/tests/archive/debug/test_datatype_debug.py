#!/usr/bin/env python3
"""
🔥 THINK ULTRA!! DataType Debug Test
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'shared'))

from models.common import DataType

def test_complex_type_conversion():
    """Test complex type conversion functions"""
    
    test_types = [
        "custom:phone",
        "custom:email", 
        "custom:array",
        "xsd:string",
        "xsd:integer"
    ]
    
    print("🔥 THINK ULTRA!! Testing DataType complex type handling")
    print("="*60)
    
    for test_type in test_types:
        print(f"\nTesting: {test_type}")
        
        # Test if it's a complex type
        is_complex = DataType.is_complex_type(test_type)
        print(f"  is_complex_type: {is_complex}")
        
        if is_complex:
            # Get base type
            base_type = DataType.get_base_type(test_type)
            print(f"  base_type: {base_type}")
        else:
            print(f"  base_type: {test_type} (unchanged)")

if __name__ == "__main__":
    test_complex_type_conversion()