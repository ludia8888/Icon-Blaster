"""integration_test_user_oms_gateway_integration.py
User-Service 와 OMS-Monolith 를 동시에 기동한 뒤, 실제 게이트웨이(nginx) 포트를 경유하여
1) 신규 사용자 회원가입
2) 로그인하여 JWT 획득
3) JWT 를 사용해 OMS 보호 엔드포인트(/health/detailed) 호출
이 모든 과정이 오류 없이 2xx 를 반환하는지 점검한다.

주의: 본 테스트는 docker-compose.integrated.yml 로 전체 스택을 띄운 상태에서 실행해야 한다.
게이트웨이 기본 포트는 8090 이며, 환경 변수 GATEWAY_URL 로 덮어쓸 수 있다.
"""

import asyncio
import os
import uuid
from typing import Dict, Any, Optional

import httpx
import pytest  # type: ignore

# -------------------------
# 설정 값
# -------------------------
# 게이트웨이 기본 주소 (docker-compose.integrated.yml 기준)
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8090")

# HTTP 요청 기본 타임아웃(초)
REQUEST_TIMEOUT = 10.0


# -------------------------
# 헬퍼 함수
# -------------------------
async def _fetch_json(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    """공통 HTTP 호출 래퍼

    Parameters
    ----------
    client : httpx.AsyncClient
        재사용할 HTTP 클라이언트
    method : str
        HTTP 메서드 (GET, POST 등)
    url : str
        호출할 URL (절대경로)
    **kwargs
        httpx 요청 파라미터 (json, data, headers 등)

    Returns
    -------
    httpx.Response
        응답 객체를 그대로 반환. 예외는 여기서 잡아 pytest 에러로 넘김.
    """
    try:
        response: httpx.Response = await client.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
    except httpx.RequestError as exc:
        pytest.fail(f"요청 실패: {exc.request.url} → {exc}")
        raise  # 위 줄이 pytest.fail 로 예외를 던져 테스트를 중단하지만, 일관성을 위해 raise
    return response


async def _wait_for_gateway(max_attempts: int = 24, delay: float = 5.0) -> None:
    """게이트웨이(nginx) 헬스체크가 200 을 돌려줄 때까지 대기.

    보통 컨테이너 부팅 직후에는 dependent 서비스 준비가 덜 되었기 때문에
    2분(24회 × 5초) 동안 재시도한다.
    """
    attempt = 0
    while attempt < max_attempts:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{GATEWAY_URL}/health", timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    return  # 성공적으로 헬스 체크 통과
            except httpx.RequestError:
                # 네트워크 오류는 건너뛰고 재시도
                pass
        attempt += 1
        await asyncio.sleep(delay)
    pytest.fail("게이트웨이가 제한 시간 내 healthy 상태가 되지 않았습니다.")


async def _register_user(client: httpx.AsyncClient, username: str, email: str, password: str) -> Dict[str, Any]:
    """신규 사용자 등록 함수

    Parameters
    ----------
    client : httpx.AsyncClient
        HTTP 클라이언트
    username : str
        사용자 ID
    email : str
        이메일 주소
    password : str
        패스워드

    Returns
    -------
    dict
        등록 응답 JSON (성공 시)
    """
    payload = {
        "username": username,
        "email": email,
        "password": password,
        "full_name": "Test User"
    }
    resp = await _fetch_json(client, "POST", f"{GATEWAY_URL}/auth/register", json=payload)
    if resp.status_code != 200:
        pytest.fail(f"회원가입 실패: {resp.status_code} – {resp.text}")
    return resp.json()


async def _login_user(client: httpx.AsyncClient, username: str, password: str) -> str:
    """로그인하여 access_token 반환

    Returns
    -------
    str
        JWT access token.
    """
    data = {
        "username": username,
        "password": password
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = await _fetch_json(client, "POST", f"{GATEWAY_URL}/auth/login", data=data, headers=headers)
    if resp.status_code != 200:
        pytest.fail(f"로그인 실패: {resp.status_code} – {resp.text}")
    token = resp.json().get("access_token")
    if not token:
        pytest.fail("access_token 이 응답에 없습니다.")
    return token


async def _call_oms_health_detailed(client: httpx.AsyncClient, token: str) -> Dict[str, Any]:
    """OMS 상세 헬스체크 호출 (인증 필요)

    Parameters
    ----------
    token : str
        Bearer 토큰

    Returns
    -------
    dict
        헬스체크 응답 JSON
    """
    headers = {"Authorization": f"Bearer {token}"}
    resp = await _fetch_json(client, "GET", f"{GATEWAY_URL}/health/detailed", headers=headers)
    if resp.status_code != 200:
        pytest.fail(f"OMS /health/detailed 호출 실패: {resp.status_code} – {resp.text}")
    return resp.json()


# -------------------------
# 메인 테스트 케이스
# -------------------------
@pytest.mark.asyncio
async def test_full_user_to_oms_flow():
    """E2E: 회원가입 → 로그인 → OMS 보호 엔드포인트 호출 성공 여부 검사"""

    # 1단계: 게이트웨이가 기동 상태인지 확인 (최대 2분 대기)
    await _wait_for_gateway()

    # 임시 테스트 계정 정보 생성 (UUID 로 중복 방지)
    username = f"test_{uuid.uuid4().hex[:6]}"
    email = f"{username}@example.com"
    password = "Str0ngP@ssw0rd!"

    async with httpx.AsyncClient() as client:
        # 2단계: 회원가입
        _ = await _register_user(client, username, email, password)

        # 3단계: 로그인하여 JWT 취득
        token = await _login_user(client, username, password)

        # 4단계: 토큰으로 OMS 보호 엔드포인트 호출
        health_resp = await _call_oms_health_detailed(client, token)

    # 5단계: 헬스 응답 구조 확인
    assert health_resp.get("status") in {"healthy", "degraded"}, "예상치 못한 health status" 