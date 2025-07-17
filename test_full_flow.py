#!/usr/bin/env python3
"""Test full authentication flow"""

import requests
import json

# Step 1: Login
print("1. Logging in...")
login_response = requests.post(
    "http://localhost:8080/auth/login",
    json={"username": "testuser_correct", "password": "TestPassword123!"}
)
print(f"Login response: {login_response.status_code}")
print(f"Login data: {login_response.json()}")

if login_response.status_code == 200:
    challenge_token = login_response.json().get("challenge_token")
    
    # Step 2: Complete login
    print("\n2. Completing login...")
    complete_response = requests.post(
        "http://localhost:8080/auth/login/complete",
        json={"challenge_token": challenge_token, "mfa_code": None}
    )
    print(f"Complete response: {complete_response.status_code}")
    print(f"Complete data: {complete_response.json()}")
    
    if complete_response.status_code == 200:
        token = complete_response.json().get("access_token")
        print(f"\n3. Got token: {token[:50]}...")
        
        # Step 3: Test userinfo
        print("\n4. Testing userinfo endpoint...")
        userinfo_response = requests.get(
            "http://localhost:8080/auth/account/userinfo",
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"Userinfo response: {userinfo_response.status_code}")
        print(f"Userinfo data: {json.dumps(userinfo_response.json(), indent=2)}")
        
        # Step 4: Test OMS API
        print("\n5. Testing OMS API...")
        oms_response = requests.get(
            "http://localhost:8091/api/v1/property/",
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"OMS response: {oms_response.status_code}")
        print(f"OMS data: {oms_response.json()}")