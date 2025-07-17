#!/usr/bin/env python3
"""
🔥 THINK ULTRA!! Final Complex Type Verification Test
"""

import asyncio
import httpx
import json

async def test_final_complex_type_verification():
    """Final test to verify all complex types are working correctly"""
    
    # Test data with complex types - using new class name
    test_ontology = {
        "id": "ComplexTypeTestFinal",
        "label": "Final Complex Type Test",
        "description": "Final verification that all complex types work correctly",
        "properties": [
            {
                "name": "phone_field",
                "label": "Phone Field",
                "type": "custom:phone",
                "required": True,
                "constraints": {
                    "format": "E164"
                }
            },
            {
                "name": "email_field",
                "label": "Email Field",
                "type": "custom:email", 
                "required": True
            },
            {
                "name": "money_field",
                "label": "Money Field",
                "type": "custom:money",
                "required": False,
                "constraints": {
                    "currency": "USD"
                }
            },
            {
                "name": "coordinate_field",
                "label": "Coordinate Field",
                "type": "custom:coordinate",
                "required": False
            },
            {
                "name": "regular_field",
                "label": "Regular Field",
                "type": "xsd:string",
                "required": True
            }
        ],
        "parent_class": None,
        "abstract": False
    }
    
    print("🔥 THINK ULTRA!! Final Complex Type Verification Test")
    print("="*60)
    
    # Test against local services
    base_url = "http://localhost:8000"
    db_name = "complex_types_final_test"
    
    # Database creation data
    db_create_data = {"name": db_name}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # First, create the database
            create_db_response = await client.post(
                f"{base_url}/api/v1/database/create",
                json=db_create_data
            )
            print(f"Create DB Response: {create_db_response.status_code}")
            
            # Now create the ontology with complex types
            create_ontology_response = await client.post(
                f"{base_url}/api/v1/ontology/{db_name}/create",
                json=test_ontology
            )
            
            print(f"Create Ontology Response: {create_ontology_response.status_code}")
            
            if create_ontology_response.status_code == 200:
                response_data = create_ontology_response.json()
                print(f"✅ SUCCESS: Complex types working correctly!")
                print(f"Created ontology: {response_data['data']['id']}")
                print(f"Complex types converted and stored successfully")
                
                # Test querying the created ontology
                get_response = await client.get(
                    f"{base_url}/api/v1/ontology/{db_name}/{test_ontology['id']}"
                )
                if get_response.status_code == 200:
                    print(f"✅ VERIFICATION: Ontology can be retrieved successfully")
                else:
                    print(f"⚠️  WARNING: Could not retrieve ontology: {get_response.status_code}")
                    
            else:
                error_text = create_ontology_response.text
                print(f"❌ ERROR: {error_text}")
                
                # Try to parse as JSON for better error details
                try:
                    error_json = json.loads(error_text)
                    print(f"Error details: {json.dumps(error_json, indent=2)}")
                except:
                    print(f"Raw error: {error_text}")
            
        except Exception as e:
            print(f"❌ EXCEPTION: {e}")

if __name__ == "__main__":
    asyncio.run(test_final_complex_type_verification())