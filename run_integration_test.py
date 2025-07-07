#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Arrakis 통합 테스트 스크립트 (Trinity Protocol)

이 스크립트는 Arrakis 시스템의 세 가지 핵심 서비스(User, OMS, Audit)가
유기적으로 연동되는지 검증하는 실제 End-to-End 테스트를 수행합니다.

시나리오:
1. User Service에서 테스트 사용자를 생성하고 JWT 토큰을 발급받습니다.
2. 발급받은 토큰을 사용하여 OMS Monolith에 보호된 리소스를 생성합니다.
3. Audit Service에서 해당 활동이 올바르게 감사 로그로 기록되었는지 확인합니다.
"""

import asyncio
import httpx
import time
import os
import uuid

# --- 테스트 설정 ---
# 이 설정값들은 docker-compose.yml에 정의된 서비스 이름과 포트를 기반으로 합니다.
USER_SERVICE_URL = "http://localhost:8000"
OMS_SERVICE_URL = "http://localhost:8080"
AUDIT_SERVICE_URL = "http://localhost:8001"

# 테스트에 사용할 사용자 정보
TEST_USERNAME = f"trinity_user_{uuid.uuid4().hex[:8]}"
TEST_PASSWORD = "ValidPassword123!"
TEST_EMAIL = f"{TEST_USERNAME}@arrakis.dune"

# HTTP 클라이언트 설정
http_client = httpx.AsyncClient(timeout=30.0)

async def main():
    """통합 테스트 메인 실행 함수"""
    jwt_token = None
    resource_id = None
    try:
        print("--- Arrakis 통합 테스트 시작 ---")

        # 1단계: 사용자 생성 및 인증 토큰 획득
        print("\n[1단계] User Service: 사용자 생성 및 인증")
        jwt_token = await get_auth_token()
        if not jwt_token:
            raise Exception("인증 토큰을 획득하지 못했습니다.")
        print(f"  [성공] JWT 토큰 획득 완료")

        # 2단계: OMS에 리소스 생성
        print("\n[2단계] OMS Monolith: 인증된 리소스 생성 요청")
        resource_id = await create_oms_resource(jwt_token)
        if not resource_id:
            raise Exception("OMS 리소스 생성에 실패했습니다.")
        print(f"  [성공] OMS 리소스 생성 완료 (ID: {resource_id})")

        # 3단계: Audit Service 로그 검증
        print("\n[3단계] Audit Service: 감사 로그 기록 검증")
        # 비동기 이벤트 전파를 위해 잠시 대기
        print("  ... 이벤트 전파 대기 (5초) ...")
        await asyncio.sleep(5)
        
        audit_log_verified = await verify_audit_log(jwt_token, resource_id)
        if not audit_log_verified:
            raise Exception("감사 로그 검증에 실패했습니다.")
        print("  [성공] 감사 로그에서 리소스 생성 기록 확인 완료")

        print("\n--- ✅ Arrakis 통합 테스트 성공 ---")

    except Exception as e:
        print(f"\n--- ❌ Arrakis 통합 테스트 실패 ---")
        print(f"오류: {e}")
    finally:
        if jwt_token:
            # 테스트 정리 단계 추가 가능 (예: 생성된 사용자 삭제)
            pass
        await http_client.aclose()
        print("\n--- 테스트 종료 ---")

async def get_auth_token():
    """
    User Service에 사용자를 생성하고 인증 토큰을 받아옵니다.
    """
    # 1. 사용자 생성
    try:
        print(f"  - 사용자 생성 시도: {TEST_USERNAME}")
        create_user_url = f"{USER_SERVICE_URL}/api/v1/users/"
        user_payload = {
            "username": TEST_USERNAME,
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        }
        response = await http_client.post(create_user_url, json=user_payload)
        response.raise_for_status()
        user_id = response.json().get("id")
        print(f"  - 사용자 생성 완료 (ID: {user_id})")
    except httpx.HTTPStatusError as e:
        print(f"  [오류] 사용자 생성 실패: {e.response.status_code} {e.response.text}")
        return None
    except httpx.RequestError as e:
        print(f"  [오류] User Service 연결 실패: {e}")
        return None

    # 2. 인증 토큰 발급
    try:
        print(f"  - 인증 토큰 요청: {TEST_USERNAME}")
        login_url = f"{USER_SERVICE_URL}/api/v1/auth/token"
        login_payload = {
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        }
        response = await http_client.post(login_url, data=login_payload)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        return access_token
    except httpx.HTTPStatusError as e:
        print(f"  [오류] 로그인 실패: {e.response.status_code} {e.response.text}")
        return None
    except httpx.RequestError as e:
        print(f"  [오류] User Service 연결 실패: {e}")
        return None

async def create_oms_resource(token: str):
    """
    OMS Monolith에 인증된 요청을 보내 새 리소스를 생성합니다.
    """
    try:
        create_branch_url = f"{OMS_SERVICE_URL}/api/v1/branches/"
        branch_name = f"test-branch-{uuid.uuid4().hex[:8]}"
        payload = {
            "name": branch_name,
            "base_branch": "main" 
        }
        headers = {"Authorization": f"Bearer {token}"}
        
        print(f"  - OMS 브랜치 생성 요청: {branch_name}")
        response = await http_client.post(create_branch_url, json=payload, headers=headers)
        
        response.raise_for_status()
        response_data = response.json()
        resource_id = response_data.get("id") or response_data.get("branch_id")
        return resource_id
    except httpx.HTTPStatusError as e:
        print(f"  [오류] OMS 리소스 생성 실패: {e.response.status_code} {e.response.text}")
        return None
    except httpx.RequestError as e:
        print(f"  [오류] OMS Service 연결 실패: {e}")
        return None

async def verify_audit_log(token: str, resource_id: str):
    """
    Audit Service에서 특정 리소스 생성에 대한 로그가 있는지 확인합니다.
    """
    try:
        audit_query_url = f"{AUDIT_SERVICE_URL}/api/v2/query/events"
        params = {
            "resource_id": resource_id,
            "action": "create_branch",
            "service": "ontology-management-service"
        }
        headers = {"Authorization": f"Bearer {token}"}

        print(f"  - Audit Service에 로그 조회 요청 (Resource ID: {resource_id})")
        response = await http_client.get(audit_query_url, params=params, headers=headers)
        
        response.raise_for_status()
        events = response.json()

        if isinstance(events, list) and len(events) > 0:
            print(f"  - 발견된 감사 이벤트 수: {len(events)}")
            event = events[0]
            print(f"  - 이벤트 내용: action={event.get('action')}, result={event.get('result')}")
            if event.get('result') == 'success':
                return True
            else:
                print("  - 감사 이벤트가 성공(success)이 아닙니다.")
                return False
        else:
            print("  - 감사 이벤트가 발견되지 않았거나 응답 형식이 올바르지 않습니다.")
            return False
            
    except httpx.HTTPStatusError as e:
        print(f"  [오류] 감사 로그 조회 실패: {e.response.status_code} {e.response.text}")
        return False
    except httpx.RequestError as e:
        print(f"  [오류] Audit Service 연결 실패: {e}")
        return False


if __name__ == "__main__":
    # 스크립트가 로컬에서 실행될 때 필요한 환경변수를 설정합니다.
    # user-service와 audit-service가 이 SECRET을 공유해야 합니다.
    os.environ['JWT_SECRET'] = 'test-secret-key-for-testing-only'
    asyncio.run(main()) 