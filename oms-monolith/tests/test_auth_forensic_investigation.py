"""
FORENSIC AUTHENTICATION INVESTIGATION
NO ASSUMPTIONS. NO GUESSING. ONLY TRUTH.

This test will trace EVERY SINGLE STEP of JWT authentication 
with CONCRETE inputs and outputs to find the EXACT root cause.
"""
import os
import jwt as jwt_lib
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
import json

# Set the environment exactly as the failing test
os.environ["JWT_SECRET"] = "test-jwt-secret-for-comprehensive-validation"

class AuthenticationForensics:
    """Forensic investigation of authentication failure"""
    
    def __init__(self):
        self.jwt_secret = "test-jwt-secret-for-comprehensive-validation"
        self.findings = {}
        
    def create_test_jwt(self):
        """Create a JWT token with EXACT same parameters as failing test"""
        payload = {
            "user_id": "test-user-123",
            "username": "test-user", 
            "roles": ["developer"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc)
        }
        
        token = jwt_lib.encode(payload, self.jwt_secret, algorithm="HS256")
        
        print(f"🔍 CREATED JWT TOKEN:")
        print(f"   Secret: {self.jwt_secret}")
        print(f"   Payload: {json.dumps(payload, indent=2, default=str)}")
        print(f"   Token: {token[:50]}...")
        
        return token, payload
    
    def test_jwt_decode_locally(self, token, expected_payload):
        """Test JWT decoding with EXACT same library and parameters"""
        print(f"\\n🔬 TESTING LOCAL JWT DECODE:")
        
        try:
            decoded = jwt_lib.decode(
                token,
                self.jwt_secret, 
                algorithms=["HS256"]
            )
            
            print(f"   ✅ DECODE SUCCESS")
            print(f"   Decoded payload: {json.dumps(decoded, indent=2, default=str)}")
            
            # Verify each field
            for key, expected_value in expected_payload.items():
                if key in ['exp', 'iat']:
                    continue  # Skip timestamp fields
                    
                actual_value = decoded.get(key)
                if actual_value == expected_value:
                    print(f"   ✅ {key}: {actual_value} (matches)")
                else:
                    print(f"   ❌ {key}: got {actual_value}, expected {expected_value}")
                    return False
            
            return True
            
        except Exception as e:
            print(f"   ❌ DECODE FAILED: {e}")
            return False
    
    def test_user_service_client_direct(self, token):
        """Test UserServiceClient DIRECTLY with our token"""
        print(f"\\n🔬 TESTING UserServiceClient DIRECTLY:")
        
        try:
            from core.integrations.user_service_client import UserServiceClient
            
            client = UserServiceClient()
            print(f"   📋 Client created")
            print(f"   📋 Client JWT secret: {client.jwt_secret}")
            print(f"   📋 Client local validation: {client.local_validation}")
            
            # Test the _validate_token_locally method DIRECTLY
            print(f"   🧪 Testing _validate_token_locally method...")
            
            import asyncio
            user_context = asyncio.run(client._validate_token_locally(token))
            
            print(f"   ✅ UserServiceClient validation SUCCESS")
            print(f"   User ID: {user_context.user_id}")
            print(f"   Username: {user_context.username}")
            print(f"   Roles: {user_context.roles}")
            
            return True, user_context
            
        except Exception as e:
            print(f"   ❌ UserServiceClient validation FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False, None
    
    def test_global_validate_function(self, token):
        """Test the global validate_jwt_token function"""
        print(f"\\n🔬 TESTING GLOBAL validate_jwt_token FUNCTION:")
        
        try:
            from core.integrations.user_service_client import validate_jwt_token
            
            print(f"   🧪 Calling validate_jwt_token...")
            user_context = asyncio.run(validate_jwt_token(token))
            
            print(f"   ✅ Global validation SUCCESS")
            print(f"   User ID: {user_context.user_id}")
            print(f"   Username: {user_context.username}")
            print(f"   Roles: {user_context.roles}")
            
            return True, user_context
            
        except Exception as e:
            print(f"   ❌ Global validation FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False, None
    
    def test_auth_middleware_step_by_step(self, token):
        """Simulate EXACT steps that AuthMiddleware takes"""
        print(f"\\n🔬 SIMULATING AuthMiddleware STEP BY STEP:")
        
        try:
            # Step 1: Import the middleware
            from middleware.auth_middleware import AuthMiddleware
            
            # Step 2: Create middleware instance (same as server)
            middleware = AuthMiddleware(app=None, public_paths=["/health", "/metrics", "/docs", "/openapi.json", "/redoc"])
            
            print(f"   📋 Middleware created")
            print(f"   📋 Public paths: {middleware.public_paths}")
            print(f"   📋 Use enhanced validation: {middleware.use_enhanced_validation}")
            
            # Step 3: Simulate token validation path
            print(f"   🧪 Testing middleware token validation path...")
            
            if middleware.use_enhanced_validation:
                print(f"   📍 Using IAM integration path")
                # This would call middleware.iam_integration.validate_jwt_enhanced(token)
                return False, "IAM integration path not tested"
            else:
                print(f"   📍 Using standard User Service path")
                # This calls validate_jwt_token(token) - the global function
                from core.integrations.user_service_client import validate_jwt_token
                user_context = asyncio.run(validate_jwt_token(token))
                
                print(f"   ✅ Middleware validation path SUCCESS")
                print(f"   User: {user_context.username}")
                
                return True, user_context
            
        except Exception as e:
            print(f"   ❌ Middleware simulation FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False, None
    
    async def test_real_http_request_forensics(self, token):
        """Test REAL HTTP request and trace EXACTLY what happens"""
        print(f"\\n🔬 FORENSIC HTTP REQUEST ANALYSIS:")
        
        try:
            # Start a server if needed, or use existing one
            base_url = "http://localhost:8000"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Make the EXACT same request as the failing test
                headers = {"Authorization": f"Bearer {token}"}
                
                print(f"   📍 Making request to: {base_url}/api/v1/schemas")
                print(f"   📍 Headers: {headers}")
                
                try:
                    response = await client.get(f"{base_url}/api/v1/schemas", headers=headers)
                    
                    print(f"   📋 Response status: {response.status_code}")
                    print(f"   📋 Response headers: {dict(response.headers)}")
                    
                    if response.status_code == 401:
                        print(f"   ❌ REQUEST REJECTED (401)")
                        try:
                            error_body = response.text
                            print(f"   📋 Error body: {error_body}")
                        except:
                            pass
                        return False, response.status_code
                    else:
                        print(f"   ✅ REQUEST ACCEPTED ({response.status_code})")
                        return True, response.status_code
                        
                except httpx.ConnectError:
                    print(f"   ⚠️ Server not running - cannot test HTTP flow")
                    return None, "SERVER_NOT_RUNNING"
                    
        except Exception as e:
            print(f"   ❌ HTTP test FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False, str(e)
    
    async def run_complete_forensic_investigation(self):
        """Run COMPLETE forensic investigation"""
        print("🚨 STARTING FORENSIC AUTHENTICATION INVESTIGATION")
        print("=" * 80)
        
        # Step 1: Create token
        token, payload = self.create_test_jwt()
        
        # Step 2: Test local JWT decode
        local_decode_success = self.test_jwt_decode_locally(token, payload)
        self.findings["local_jwt_decode"] = local_decode_success
        
        # Step 3: Test UserServiceClient directly
        client_success, client_user = self.test_user_service_client_direct(token)
        self.findings["user_service_client"] = client_success
        
        # Step 4: Test global function
        global_success, global_user = self.test_global_validate_function(token)
        self.findings["global_validate_function"] = global_success
        
        # Step 5: Test middleware simulation
        middleware_success, middleware_user = self.test_auth_middleware_step_by_step(token)
        self.findings["auth_middleware_simulation"] = middleware_success
        
        # Step 6: Test real HTTP request
        http_success, http_result = await self.test_real_http_request_forensics(token)
        self.findings["real_http_request"] = http_success
        
        # ANALYSIS
        print("\\n" + "=" * 80)
        print("🧑‍⚖️ FORENSIC ANALYSIS RESULTS")
        print("=" * 80)
        
        for test_name, result in self.findings.items():
            status = "✅ PASS" if result else "❌ FAIL" if result is False else "⚠️ SKIP"
            print(f"{status} {test_name}")
        
        # CONCLUSIONS
        print("\\n🎯 ROOT CAUSE ANALYSIS:")
        
        if all(v for v in self.findings.values() if v is not None):
            print("   🤔 ALL INDIVIDUAL COMPONENTS WORK")
            print("   🔍 The failure must be in component integration or HTTP handling")
            
        elif not self.findings.get("local_jwt_decode"):
            print("   💥 CRITICAL: JWT library itself is broken")
            
        elif not self.findings.get("user_service_client"):
            print("   💥 CRITICAL: UserServiceClient is broken")
            
        elif not self.findings.get("global_validate_function"):
            print("   💥 CRITICAL: Global validate function is broken")
            
        elif not self.findings.get("auth_middleware_simulation"):
            print("   💥 CRITICAL: AuthMiddleware logic is broken")
            
        elif self.findings.get("real_http_request") is False:
            print("   💥 CRITICAL: HTTP request handling is broken")
            print("   🔍 Components work individually but fail in HTTP context")
            
        else:
            print("   🤔 INCONCLUSIVE: Need deeper investigation")
        
        return self.findings


async def main():
    """Run the forensic investigation"""
    forensics = AuthenticationForensics()
    results = await forensics.run_complete_forensic_investigation()
    
    print("\\n" + "=" * 80)
    print("🎯 FINAL VERDICT:")
    
    if all(v for v in results.values() if v is not None):
        print("   ✅ AUTHENTICATION SYSTEM IS WORKING")
        print("   🤔 The original test failure may be due to:")
        print("      - Test timing issues")
        print("      - Server startup problems") 
        print("      - Route not existing")
        print("      - Different environment")
    else:
        print("   ❌ AUTHENTICATION SYSTEM HAS REAL BUGS")
        failed_components = [k for k, v in results.items() if v is False]
        print(f"   💥 Failed components: {failed_components}")
        
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())