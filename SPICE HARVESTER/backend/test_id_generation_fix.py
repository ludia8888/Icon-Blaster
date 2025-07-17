#!/usr/bin/env python3
"""
Test the fixed ID generation algorithm
"""

import re

def is_camel_case(text: str) -> bool:
    """Check if text is already in CamelCase or camelCase format"""
    if not text or len(text) < 2:
        return False
    
    # Check for mixed case (both upper and lower) - indicates CamelCase
    has_upper = any(c.isupper() for c in text)
    has_lower = any(c.islower() for c in text)
    
    return has_upper and has_lower

def generate_id_from_label(label_text: str) -> str:
    """Fixed ID generation algorithm with improved CamelCase detection"""
    if not label_text:
        return "UnnamedClass"
    
    # Remove special characters but preserve spaces and underscores for now
    class_id = re.sub(r'[^\w\s]', '', label_text)
    
    # Handle numeric prefix first (before other processing)
    numeric_prefix = ""
    if class_id and class_id[0].isdigit():
        numeric_prefix = "Class"
    
    if ' ' in class_id:
        # Space-separated words: convert to CamelCase
        words = class_id.split()
        class_id = ''.join(word.capitalize() for word in words)
    else:
        # No spaces: check if already CamelCase/camelCase
        if is_camel_case(class_id):
            # Preserve existing CamelCase/camelCase
            class_id = class_id
        elif class_id and class_id[0].isupper():
            # Already starts with uppercase (like "TESTCLASS") - preserve
            class_id = class_id
        else:
            # Simple lowercase word - capitalize
            class_id = class_id.capitalize()
    
    # Apply numeric prefix if needed
    if numeric_prefix:
        class_id = numeric_prefix + class_id
    
    if not class_id:
        class_id = "UnnamedClass"
    
    return class_id

def test_id_generation():
    """Comprehensive test cases for ID generation"""
    
    test_cases = [
        # Critical test cases
        ("TestClass", "TestClass"),  # 🎯 MAIN FIX - preserve CamelCase
        ("Test Class", "TestClass"),  # Space-separated words
        ("test class", "TestClass"),  # Lower case words
        ("Test-Class", "TestClass"),  # Hyphenated words
        ("Test_Class", "Test_Class"), # Underscore preserved
        
        # Edge cases
        ("testClass", "testClass"),   # camelCase preserved
        ("TESTCLASS", "TESTCLASS"),   # ALL CAPS preserved
        ("test", "Test"),             # Single lowercase word
        ("TEST", "TEST"),             # Single uppercase word
        ("", "UnnamedClass"),         # Empty string
        ("123Test", "Class123Test"),  # Numeric prefix
        ("Test 123", "Test123"),      # Numeric suffix
        
        # Special characters
        ("Test@Class", "TestClass"),  # Remove special chars
        ("Test#Class", "TestClass"),  # Remove special chars
        ("Test (Class)", "TestClass"), # Remove parentheses
        
        # Multi-word cases
        ("My Test Class", "MyTestClass"),      # Three words
        ("test class name", "TestClassName"),  # All lowercase
        ("TEST CLASS NAME", "TestClassName"),  # All uppercase mixed
        
        # Korean support (if present)
        ("테스트클래스", "테스트클래스"),  # Korean preserved
        ("Test 클래스", "Test클래스"),    # Mixed Korean/English
    ]
    
    print("=== COMPREHENSIVE ID GENERATION TESTS ===\n")
    
    passed = 0
    failed = 0
    
    for input_label, expected in test_cases:
        result = generate_id_from_label(input_label)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
            
        print(f"{status}: '{input_label}' → '{result}' (expected: '{expected}')")
    
    print(f"\n📊 RESULTS: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED! ID generation algorithm fixed successfully!")
        return True
    else:
        print(f"⚠️  {failed} tests failed. Algorithm needs adjustment.")
        return False

if __name__ == "__main__":
    success = test_id_generation()
    exit(0 if success else 1)