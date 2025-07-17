#!/usr/bin/env python3
"""
Detailed ID Generation Analysis
"""

import re

def analyze_bff_id_generation():
    """Analyze the BFF ID generation step by step"""
    
    test_cases = [
        "TestClass",
        "Test Class", 
        "test class",
        "테스트 클래스",
        "Test-Class",
        "Test_Class",
        "123Test",
        "",
        None
    ]
    
    print("DETAILED BFF ID GENERATION ANALYSIS")
    print("=" * 60)
    
    for original_label in test_cases:
        print(f"\nInput: '{original_label}'")
        
        # Step 1: Handle None/empty
        if original_label is None:
            label_text = "UnnamedClass"
            print(f"  Step 1 (None check): '{label_text}'")
        elif isinstance(original_label, str):
            label_text = original_label
            print(f"  Step 1 (str check): '{label_text}'")
        else:
            label_text = "UnnamedClass"
            print(f"  Step 1 (else): '{label_text}'")
        
        # Step 2: Remove special characters
        class_id = re.sub(r'[^\w\s]', '', label_text)
        print(f"  Step 2 (remove special chars): '{class_id}'")
        
        # Step 3: Split and capitalize
        words = class_id.split()
        print(f"  Step 3a (split): {words}")
        
        capitalized_words = [word.capitalize() for word in words]
        print(f"  Step 3b (capitalize each): {capitalized_words}")
        
        class_id = ''.join(capitalized_words)
        print(f"  Step 3c (join): '{class_id}'")
        
        # Step 4: Handle digits at start
        if class_id and class_id[0].isdigit():
            class_id = 'Class' + class_id
            print(f"  Step 4 (digit prefix): '{class_id}'")
        
        # Step 5: Handle empty
        if not class_id:
            class_id = "UnnamedClass"
            print(f"  Step 5 (empty check): '{class_id}'")
        
        print(f"  FINAL ID: '{class_id}'")
        
        # Identify the issue
        if original_label == "TestClass" and class_id == "Testclass":
            print("  ❌ ISSUE IDENTIFIED: 'TestClass' -> 'Testclass'")
            print("     The 'C' in 'Class' is getting lowercased!")
            print("     This is because split() splits on spaces, not case boundaries")
            print("     'TestClass' has no spaces, so it's treated as one word")
            print("     word.capitalize() makes only the first letter uppercase")

def propose_fix():
    """Propose a fix for the ID generation issue"""
    
    print("\n\nPROPOSED FIX")
    print("=" * 60)
    
    def fixed_id_generation(label_text):
        """Fixed ID generation that preserves CamelCase"""
        
        if not label_text:
            return "UnnamedClass"
        
        # Remove special characters but preserve spaces
        cleaned = re.sub(r'[^\w\s]', '', label_text)
        
        # If there are spaces, use the original algorithm
        if ' ' in cleaned:
            words = cleaned.split()
            class_id = ''.join(word.capitalize() for word in words)
        else:
            # If no spaces, check if it's already CamelCase
            if cleaned and cleaned[0].isupper():
                # Preserve existing CamelCase
                class_id = cleaned
            else:
                # Apply capitalize to the whole string
                class_id = cleaned.capitalize()
        
        # Handle digits at start
        if class_id and class_id[0].isdigit():
            class_id = 'Class' + class_id
        
        if not class_id:
            class_id = "UnnamedClass"
        
        return class_id
    
    test_cases = [
        "TestClass",
        "Test Class", 
        "test class",
        "테스트 클래스",
        "Test-Class",
        "Test_Class",
        "123Test",
    ]
    
    print("ORIGINAL vs FIXED comparison:")
    
    for label in test_cases:
        # Original algorithm
        original = re.sub(r'[^\w\s]', '', label)
        original = ''.join(word.capitalize() for word in original.split())
        if original and original[0].isdigit():
            original = 'Class' + original
        if not original:
            original = "UnnamedClass"
        
        # Fixed algorithm
        fixed = fixed_id_generation(label)
        
        match = "✅" if original == fixed else "❌"
        print(f"  '{label}' -> Original: '{original}', Fixed: '{fixed}' {match}")

if __name__ == "__main__":
    analyze_bff_id_generation()
    propose_fix()