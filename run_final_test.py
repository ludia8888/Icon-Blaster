#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import httpx
import time
import os
import uuid
import json

# 서비스 URL 설정
USER_SERVICE_URL = "http://localhost:8001"
OMS_SERVICE_URL = "http://localhost:8000"
AUDIT_SERVICE_URL = "http://localhost:8003"

# 테스트용 사용자 정보
TEST_USERNAME = f"trinity_user_final_{uuid.uuid4().hex[:8]}"
TEST_PASSWORD = "ValidPassword123!"
TEST_EMAIL = f"{TEST_USERNAME}@arrakis.dune"

# HTTP 클라이언트 (타임아웃 증가)
http_client = httpx.AsyncClient(timeout=30.0)

def print_request(method, url, headers=None, json_payload=None, data=None, params=None):
    print(f"\n>>> REQUEST ---")
    print(f"  {method} {url}")
    if headers:
        safe_headers = {k: ("Bearer ***" if k.lower() == "authorization" else v) for k, v in headers.items()}
        print(f"  Headers: {json.dumps(safe_headers, indent=2)}")
    if json_payload:
        print(f"  JSON Body: {json.dumps(json_payload, indent=2)}")
    if data:
        print(f"  Form Data: {data}")
    if params:
        print(f"  Params: {params}")
    print("----------------")

def print_response(response):
    print(f"\n<<< RESPONSE ---")
    print(f"  Status: {response.status_code}")
    try:
        print(f"  Body: {json.dumps(response.json(), indent=2)}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"  Body: {response.text}")
    print("----------------")

async def wait_for_service(service_name, url):
    print(f"\nWaiting for {service_name} at {url}...")
    # Health check 엔드포인트가 없는 경우를 대비해 /docs 또는 /health 사용
    health_url = url
    if "docs" not in url and "health" not in url:
        # 기본적으로 /health를 시도하고, 실패 시 /docs로 넘어감
        try:
            await http_client.get(f"{url}/health", timeout=2.0)
            health_url = f"{url}/health"
        except httpx.RequestError:
            health_url = f"{url}/docs" # Fallback to /docs
            
    for i in range(30):
        try:
            response = await http_client.get(health_url, timeout=5.0)
            # 200 (OK), 404 (Not Found, but server is up), 401 (Unauthorized, server is up)
            if response.status_code in [200, 404, 401]:
                print(f"{service_name} is ready!")
                return True
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            print(f".", end="", flush=True)
            await asyncio.sleep(2)
    print(f"\nError: {service_name} not ready after multiple attempts.")
    return False

async def main():
    # --- 0단계: 모든 서비스 준비 확인 ---
    print("--- STEP 0: Verifying all services are ready ---")
    services_ready = all([
        await wait_for_service("User Service", USER_SERVICE_URL),
        await wait_for_service("Audit Service", AUDIT_SERVICE_URL),
        await wait_for_service("OMS Monolith", OMS_SERVICE_URL)
    ])
    
    if not services_ready:
        print("\nIntegration test aborted because not all services are ready.")
        return

    jwt_token = None
    user_id = None
    
    # --- 1단계: User Service에서 사용자 생성 및 토큰 획득 ---
    print("\n--- STEP 1: Create User and Get JWT from User Service ---")
    try:
        # 사용자 생성
        create_user_payload = {"username": TEST_USERNAME, "password": TEST_PASSWORD, "email": TEST_EMAIL}
        print_request("POST", f"{USER_SERVICE_URL}/api/v1/users", json_payload=create_user_payload)
        response = await http_client.post(f"{USER_SERVICE_URL}/api/v1/users", json=create_user_payload)
        print_response(response)
        response.raise_for_status()
        user_id = response.json().get("id")
        print(f"User created successfully with ID: {user_id}")

        # JWT 토큰 획득
        login_payload = {"username": TEST_USERNAME, "password": TEST_PASSWORD}
        print_request("POST", f"{USER_SERVICE_URL}/api/v1/auth/token", data=login_payload)
        response = await http_client.post(f"{USER_SERVICE_URL}/api/v1/auth/token", data=login_payload)
        print_response(response)
        response.raise_for_status()
        jwt_token = response.json().get("access_token")
        print(f"JWT token acquired successfully!")

    except httpx.HTTPStatusError as e:
        print(f"Error in Step 1: {e}")
        print(f"Response body: {e.response.text}")
        return
    except httpx.RequestError as e:
        print(f"Connection error in Step 1: {e}")
        return

    # --- 2단계: OMS Monolith에 인증된 요청 보내기 ---
    print("\n--- STEP 2: Make Authenticated Request to OMS Monolith ---")
    new_branch_name = f"test-branch-{uuid.uuid4().hex[:8]}"
    try:
        headers = {"Authorization": f"Bearer {jwt_token}"}
        create_branch_payload = {"name": new_branch_name, "base_branch": "main"}
        print_request("POST", f"{OMS_SERVICE_URL}/api/v1/branches", headers=headers, json_payload=create_branch_payload)
        
        response = await http_client.post(
            f"{OMS_SERVICE_URL}/api/v1/branches", 
            headers=headers, 
            json=create_branch_payload
        )
        print_response(response)
        response.raise_for_status()
        print(f"Branch '{new_branch_name}' created successfully in OMS.")
        
    except httpx.HTTPStatusError as e:
        print(f"Error in Step 2: {e}")
        print(f"Response body: {e.response.text}")
        # 실패하더라도 3단계는 진행하여 감사로그 확인
    except httpx.RequestError as e:
        print(f"Connection error in Step 2: {e}")
        return

    # --- 3단계: Audit Service에서 감사 로그 확인 ---
    print("\n--- STEP 3: Verify Audit Log in Audit Service ---")
    print("Waiting 5 seconds for event propagation...")
    await asyncio.sleep(5)  # 이벤트가 처리될 시간을 줌

    try:
        params = {"user_id": user_id, "limit": 10}
        print_request("GET", f"{AUDIT_SERVICE_URL}/api/v2/query/events", params=params)
        
        response = await http_client.get(f"{AUDIT_SERVICE_URL}/api/v2/query/events", params=params)
        print_response(response)
        response.raise_for_status()

        events = response.json()
        if not events:
            print("XXX TEST FAILED: No audit events found for the user.")
            return
            
        # 생성된 브랜치에 대한 로그가 있는지 확인
        branch_creation_event_found = any(
            event.get("details", {}).get("entity_name") == new_branch_name and 
            event.get("action") == "BRANCH_CREATE" 
            for event in events
        )

        if branch_creation_event_found:
            print(">>> SUCCESS! Audit log for branch creation is verified. <<<")
            print(">>> The Trinity Protocol is complete! All services are working in harmony. <<<")
        else:
            print(f"XXX TEST FAILED: Could not find audit log for branch '{new_branch_name}' creation.")

    except httpx.HTTPStatusError as e:
        print(f"Error in Step 3: {e}")
        print(f"Response body: {e.response.text}")
    except httpx.RequestError as e:
        print(f"Connection error in Step 3: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 