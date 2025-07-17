#!/usr/bin/env python3
"""
Test ID Generation Mismatch between BFF and OMS
"""

import httpx
import asyncio
import json
import sqlite3
import sys
import os
from test_config import TestConfig

# Add paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
bff_dir = os.path.join(current_dir, 'backend-for-frontend')
shared_dir = os.path.join(current_dir, 'shared')
sys.path.insert(0, bff_dir)
sys.path.insert(0, shared_dir)

try:
    from utils.label_mapper import LabelMapper
except ImportError:
    # If import fails, we'll skip the direct LabelMapper tests
    LabelMapper = None

async def test_id_generation_mismatch():
    """Test ID generation mismatch between BFF and OMS"""
    
    test_db = "idmismatch"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # Clean up any existing test database
        try:
            await client.delete(TestConfig.get_database_delete_url(test_db))
        except (httpx.HTTPError, httpx.TimeoutException, ConnectionError):
            pass
        
        # Create test database
        print("1. Creating test database...")
        response = await client.post(
            TestConfig.get_database_create_url(),
            json={"name": test_db, "description": "ID mismatch test"}
        )
        print(f"   DB creation: {response.status_code}")
        
        # Test different label patterns that might cause mismatches
        test_cases = [
            {"label": "TestClass", "expected_issues": ["Case sensitivity"]},
            {"label": "Test Class", "expected_issues": ["Space handling"]},
            {"label": "test class", "expected_issues": ["Case and space handling"]},
            {"label": "테스트 클래스", "expected_issues": ["Korean characters"]},
            {"label": "TestClass123", "expected_issues": ["Numbers in ID"]},
            {"label": "test-class", "expected_issues": ["Special characters"]},
            {"label": "Test_Class", "expected_issues": ["Underscore handling"]},
        ]
        
        for i, test_case in enumerate(test_cases):
            print(f"\n2.{i+1} Testing label: '{test_case['label']}'")
            
            # Create ontology via BFF
            response = await client.post(
                TestConfig.get_bff_ontology_url(test_db),
                json={
                    "label": test_case['label'],
                    "description": "Test ontology",
                    "properties": []
                }
            )
            
            if response.status_code == 200:
                bff_response = response.json()
                generated_id = bff_response.get('data', {}).get('id')
                print(f"   BFF generated ID: {generated_id}")
                
                # Check what's stored in OMS
                oms_response = await client.get(TestConfig.get_oms_ontology_url(test_db, f"/{generated_id}"))
                print(f"   OMS retrieval: {oms_response.status_code}")
                
                if oms_response.status_code == 200:
                    oms_data = oms_response.json()
                    stored_id = oms_data.get('data', {}).get('id')
                    print(f"   OMS stored ID: {stored_id}")
                    
                    # Check if there's a mismatch
                    if generated_id != stored_id:
                        print(f"   ❌ ID MISMATCH: Generated '{generated_id}' != Stored '{stored_id}'")
                    else:
                        print(f"   ✅ ID Match: '{generated_id}'")
                else:
                    print(f"   ❌ Failed to retrieve from OMS: {oms_response.text}")
                
                # Test retrieval via BFF (using label)
                bff_retrieval = await client.get(TestConfig.get_bff_ontology_url(test_db, f"/{test_case['label']}"))
                print(f"   BFF label retrieval: {bff_retrieval.status_code}")
                
                if bff_retrieval.status_code != 200:
                    print(f"   ❌ BFF can't find by label: {bff_retrieval.text}")
                
            else:
                print(f"   ❌ Failed to create via BFF: {response.text}")
        
        # Check what's in the label mapping database
        print("\n3. Checking label mapping database...")
        db_path = "data/label_mappings.db"
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT db_name, class_id, label, label_lang
                FROM class_mappings 
                WHERE db_name = ?
                ORDER BY created_at DESC
            """, (test_db,))
            
            print("   Label mappings:")
            for row in cursor.fetchall():
                print(f"   - DB: {row[0]}, ID: {row[1]}, Label: {row[2]}, Lang: {row[3]}")
            
            conn.close()
        except Exception as e:
            print(f"   Error reading label mappings: {e}")
        
        # Clean up
        await client.delete(TestConfig.get_database_delete_url(test_db))

async def analyze_id_generation_algorithm():
    """Analyze the ID generation algorithm directly"""
    
    print("\n4. Analyzing ID generation algorithm...")
    
    # Test the BFF ID generation logic directly
    test_labels = [
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
    
    import re
    
    for label in test_labels:
        print(f"\n   Testing label: '{label}'")
        
        # Replicate BFF logic
        if label is None:
            label_text = "UnnamedClass"
        elif isinstance(label, str):
            label_text = label
        else:
            label_text = "UnnamedClass"
        
        # BFF algorithm
        class_id = re.sub(r'[^\w\s]', '', label_text)
        class_id = ''.join(word.capitalize() for word in class_id.split())
        
        if class_id and class_id[0].isdigit():
            class_id = 'Class' + class_id
        if not class_id:
            class_id = "UnnamedClass"
        
        print(f"   Generated ID: '{class_id}'")
        
        # Check for potential issues
        issues = []
        if label and label != class_id:
            issues.append("Label differs from ID")
        if ' ' in (label or ''):
            issues.append("Contains spaces")
        if any(c.islower() for c in (label or '')):
            issues.append("Contains lowercase")
        if any(not c.isalnum() and c != ' ' for c in (label or '')):
            issues.append("Contains special characters")
        
        if issues:
            print(f"   Potential issues: {', '.join(issues)}")

if __name__ == "__main__":
    # Skip the service tests and just run the algorithm analysis
    asyncio.run(analyze_id_generation_algorithm())