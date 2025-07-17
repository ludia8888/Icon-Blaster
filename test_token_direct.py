#!/usr/bin/env python3
"""Test token decoding directly"""

import jwt
import requests
import json

# Get a fresh token
login_response = requests.post(
    "http://localhost:8080/auth/login",
    json={"username": "testuser_correct", "password": "TestPassword123!"}
)

if login_response.status_code == 200:
    challenge_token = login_response.json().get("challenge_token")
    
    complete_response = requests.post(
        "http://localhost:8080/auth/login/complete",
        json={"challenge_token": challenge_token, "mfa_code": None}
    )
    
    if complete_response.status_code == 200:
        token = complete_response.json().get("access_token")
        
        # Decode without verification to see contents
        decoded = jwt.decode(token, options={"verify_signature": False})
        print("Token payload:")
        print(json.dumps(decoded, indent=2))
        
        # Get JWKS
        print("\nFetching JWKS from user-service...")
        jwks_response = requests.get("http://localhost:8080/.well-known/jwks.json")
        if jwks_response.status_code == 200:
            print("JWKS found!")
            print(json.dumps(jwks_response.json(), indent=2))
        else:
            print(f"JWKS not found: {jwks_response.status_code}")
            print(jwks_response.text)