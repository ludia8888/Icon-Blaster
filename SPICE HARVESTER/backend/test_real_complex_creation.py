#!/usr/bin/env python3
"""
🔥 THINK ULTRA!! Test Real Complex Type Creation with Services
"""

import asyncio
import httpx
import json

async def test_real_complex_type_creation():
    """Test creating an ontology with complex types through the actual API"""
    
    # Test data with complex types - fixed structure
    test_ontology = {
        "id": "PersonWithComplexTypes",
        "label": "Person with Complex Types",
        "description": "A person class with phone and email fields",
        "properties": [
            {
                "name": "phone_number",
                "label": "Phone Number",
                "type": "custom:phone",
                "required": True,
                "constraints": {
                    "format": "E164"
                }
            },
            {
                "name": "email_address",
                "label": "Email Address",
                "type": "custom:email", 
                "required": True
            },
            {
                "name": "full_name",
                "label": "Full Name",
                "type": "xsd:string",
                "required": True
            }
        ],
        "parent_class": None,
        "abstract": False
    }
    
    print("🔥 THINK ULTRA!! Testing real complex type creation through API")
    print("="*60)
    
    # Test against local services
    base_url = "http://localhost:8000"
    db_name = "test_complex_db"
    
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
            if create_db_response.status_code not in [200, 201, 409]:  # 409 = already exists
                print(f"DB Creation failed: {create_db_response.text}")
            
            # Now create the ontology with complex types
            create_ontology_response = await client.post(
                f"{base_url}/api/v1/ontology/{db_name}/create",
                json=test_ontology
            )
            
            print(f"Create Ontology Response: {create_ontology_response.status_code}")
            
            if create_ontology_response.status_code == 200:
                response_data = create_ontology_response.json()
                print(f"✅ SUCCESS: {response_data}")
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
    asyncio.run(test_real_complex_type_creation())