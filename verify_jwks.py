#!/usr/bin/env python3
"""Verify JWKS and token signature"""

import requests
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import json
import base64

# Get fresh token
print("1. Getting fresh token...")
login_resp = requests.post(
    "http://localhost:8080/auth/login",
    json={"username": "testuser_correct", "password": "TestPassword123!"}
)

if login_resp.status_code == 200:
    challenge = login_resp.json()["challenge_token"]
    
    complete_resp = requests.post(
        "http://localhost:8080/auth/login/complete",
        json={"challenge_token": challenge, "mfa_code": None}
    )
    
    if complete_resp.status_code == 200:
        token = complete_resp.json()["access_token"]
        print("✅ Got token")
        
        # Get JWKS
        print("\n2. Getting JWKS...")
        jwks_resp = requests.get("http://localhost:8080/.well-known/jwks.json")
        if jwks_resp.status_code == 200:
            jwks = jwks_resp.json()
            print("✅ Got JWKS")
            
            # Decode token header to get kid
            header = jwt.get_unverified_header(token)
            kid = header.get('kid')
            print(f"\n3. Token uses key ID: {kid}")
            
            # Find the key
            key_found = False
            for key in jwks['keys']:
                if key['kid'] == kid:
                    print(f"✅ Found matching key in JWKS")
                    key_found = True
                    
                    # Try to verify token with PyJWT and JWKS
                    try:
                        from jwt import PyJWKClient
                        
                        print("\n4. Verifying token with JWKS...")
                        jwks_client = PyJWKClient("http://localhost:8080/.well-known/jwks.json")
                        signing_key = jwks_client.get_signing_key_from_jwt(token)
                        
                        decoded = jwt.decode(
                            token,
                            signing_key.key,
                            algorithms=["RS256"],
                            audience="oms",
                            issuer="user-service"
                        )
                        print("✅ Token verification successful!")
                        print(f"   User: {decoded.get('username')}")
                        print(f"   Expires: {decoded.get('exp')}")
                        
                    except Exception as e:
                        print(f"❌ Token verification failed: {type(e).__name__}: {str(e)}")
                    
                    break
            
            if not key_found:
                print(f"❌ No key with ID {kid} found in JWKS")
                print(f"Available keys: {[k['kid'] for k in jwks['keys']]}")
        else:
            print(f"❌ Failed to get JWKS: {jwks_resp.status_code}")