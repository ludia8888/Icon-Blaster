#!/usr/bin/env python3
"""
Test Label Mapper Directly
"""

import asyncio
import sys
import os

# Add shared path for models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))
from label_mapper import LabelMapper

async def main():
    """Test label mapper registration and retrieval"""
    
    mapper = LabelMapper()
    
    print("1. Testing label registration...")
    test_db = "testdb"
    test_id = "TestClass"
    test_label = "Test Class"
    
    # Register
    await mapper.register_class(
        db_name=test_db,
        class_id=test_id,
        label=test_label,
        description="Test description"
    )
    print(f"   Registered: {test_id} -> {test_label}")
    
    # Retrieve
    print("\n2. Testing retrieval...")
    
    # Should work - exact match
    result = await mapper.get_class_id(test_db, test_label, 'ko')
    print(f"   get_class_id('{test_label}', 'ko') = {result}")
    
    # Try with English
    result = await mapper.get_class_id(test_db, test_label, 'en')
    print(f"   get_class_id('{test_label}', 'en') = {result}")
    
    # Try with the ID itself
    result = await mapper.get_class_id(test_db, test_id, 'ko')
    print(f"   get_class_id('{test_id}', 'ko') = {result}")
    
    # Test multilingual
    print("\n3. Testing multilingual registration...")
    multilingual_label = {
        "ko": "테스트 클래스",
        "en": "Test Class Multi",
        "ja": "テストクラス"
    }
    
    await mapper.register_class(
        db_name=test_db,
        class_id="MultiClass",
        label=multilingual_label,
        description="Multilingual test"
    )
    print("   Registered multilingual class")
    
    # Try different languages
    result = await mapper.get_class_id(test_db, "테스트 클래스", 'ko')
    print(f"   get_class_id('테스트 클래스', 'ko') = {result}")
    
    result = await mapper.get_class_id(test_db, "Test Class Multi", 'en')
    print(f"   get_class_id('Test Class Multi', 'en') = {result}")

if __name__ == "__main__":
    asyncio.run(main())