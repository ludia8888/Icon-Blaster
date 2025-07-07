"""
Authentication Proxy Routes
OMS Monolith에서 User Service로의 인증 프록시 엔드포인트
"""
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, constr

from shared.user_service_client import get_user_service_client
from core.monitoring.audit_metrics import record_audit_service_request
from common_logging.setup import get_logger

logger = get_logger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    username: constr(min_length=1, max_length=255)
    password: constr(min_length=1, max_length=255)
    mfa_code: Optional[str] = None


class RegisterRequest(BaseModel):
    username: constr(min_length=3, max_length=32)
    email: EmailStr
    password: constr(min_length=8, max_length=128)
    full_name: Optional[constr(min_length=2, max_length=100)] = None


class PasswordChangeRequest(BaseModel):
    old_password: constr(min_length=1, max_length=255)
    new_password: constr(min_length=8, max_length=128)


class TokenRefreshRequest(BaseModel):
    refresh_token: constr(min_length=1, max_length=2048)


class MFAEnableRequest(BaseModel):
    code: constr(min_length=6, max_length=6)


class MFADisableRequest(BaseModel):
    password: constr(min_length=1, max_length=255)
    code: constr(min_length=6, max_length=6)


@router.post("/auth/login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    mfa_code: Optional[str] = Form(None)
):
    """
    사용자 로그인 (User Service 프록시)
    
    - OAuth2PasswordRequestForm 지원
    - MFA 코드 선택적 입력
    - User Service로 요청 전달 (2단계 인증 자동 처리)
    """
    client = get_user_service_client()
    
    try:
        async with client:
            result = await client.login(
                username=form_data.username,
                password=form_data.password,
                mfa_code=mfa_code
            )
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/login",
                status="success",
                duration=0.1
            )
            
            return result
            
    except Exception as e:
        logger.error(f"Login proxy failed: {e}")
        
        # 메트릭 기록
        record_audit_service_request(
            method="POST",
            endpoint="/auth/login",
            status="error",
            duration=0.1
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/auth/login/json")
async def login_json(
    request: Request,
    login_data: LoginRequest
):
    """
    사용자 로그인 (JSON 방식)
    
    - JSON 요청 지원
    - MFA 코드 선택적 입력
    - User Service로 요청 전달 (2단계 인증 자동 처리)
    """
    client = get_user_service_client()
    
    try:
        async with client:
            result = await client.login(
                username=login_data.username,
                password=login_data.password,
                mfa_code=login_data.mfa_code
            )
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/login/json",
                status="success",
                duration=0.1
            )
            
            return result
            
    except Exception as e:
        logger.error(f"Login proxy failed: {e}")
        
        # 메트릭 기록
        record_audit_service_request(
            method="POST",
            endpoint="/auth/login/json",
            status="error",
            duration=0.1
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/auth/register")
async def register(
    request: Request,
    register_request: RegisterRequest
):
    """
    사용자 회원가입 (User Service 프록시)
    
    - 사용자 계정 생성
    - User Service로 요청 전달
    """
    client = get_user_service_client()
    
    try:
        async with client:
            result = await client.register(
                username=register_request.username,
                email=register_request.email,
                password=register_request.password,
                full_name=register_request.full_name
            )
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/register",
                status="success",
                duration=0.1
            )
            
            return result
            
    except Exception as e:
        logger.error(f"Registration proxy failed: {e}")
        
        # 메트릭 기록
        record_audit_service_request(
            method="POST",
            endpoint="/auth/register",
            status="error",
            duration=0.1
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed"
        )


@router.post("/auth/logout")
async def logout(request: Request):
    """
    사용자 로그아웃 (User Service 프록시)
    
    - 세션 무효화
    - User Service로 요청 전달
    """
    client = get_user_service_client()
    
    # Authorization 헤더에서 토큰 추출
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = auth_header[7:]  # "Bearer " 제거
    
    try:
        async with client:
            result = await client.logout(token)
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/logout",
                status="success",
                duration=0.1
            )
            
            return result
            
    except Exception as e:
        logger.error(f"Logout proxy failed: {e}")
        
        # 메트릭 기록
        record_audit_service_request(
            method="POST",
            endpoint="/auth/logout",
            status="error",
            duration=0.1
        )
        
        # 로그아웃은 실패해도 성공 반환
        return {"message": "Logged out"}


@router.post("/auth/refresh")
async def refresh_token(
    request: Request,
    token_request: TokenRefreshRequest
):
    """
    토큰 갱신 (User Service 프록시)
    
    - Refresh Token으로 새 Access Token 발급
    - User Service로 요청 전달
    """
    client = get_user_service_client()
    
    try:
        async with client:
            result = await client.refresh_token(token_request.refresh_token)
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/refresh",
                status="success",
                duration=0.1
            )
            
            return result
            
    except Exception as e:
        logger.error(f"Token refresh proxy failed: {e}")
        
        # 메트릭 기록
        record_audit_service_request(
            method="POST",
            endpoint="/auth/refresh",
            status="error",
            duration=0.1
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )


@router.get("/auth/userinfo")
async def get_user_info(request: Request):
    """
    사용자 정보 조회 (User Service 프록시)
    
    - JWT 토큰으로 사용자 정보 조회
    - User Service로 요청 전달
    """
    client = get_user_service_client()
    
    # Authorization 헤더에서 토큰 추출
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = auth_header[7:]  # "Bearer " 제거
    
    try:
        async with client:
            result = await client.get_user_info(token)
            
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token"
                )
            
            # 메트릭 기록
            record_audit_service_request(
                method="GET",
                endpoint="/auth/userinfo",
                status="success",
                duration=0.1
            )
            
            return result
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User info proxy failed: {e}")
        
        # 메트릭 기록
        record_audit_service_request(
            method="GET",
            endpoint="/auth/userinfo",
            status="error",
            duration=0.1
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


@router.post("/auth/change-password")
async def change_password(
    request: Request,
    password_request: PasswordChangeRequest
):
    """
    비밀번호 변경 (User Service 프록시)
    
    - 기존 비밀번호 확인 후 새 비밀번호 설정
    - User Service로 요청 전달
    """
    client = get_user_service_client()
    
    # Authorization 헤더에서 토큰 추출
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = auth_header[7:]  # "Bearer " 제거
    
    try:
        async with client:
            result = await client.change_password(
                token=token,
                old_password=password_request.old_password,
                new_password=password_request.new_password
            )
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/change-password",
                status="success",
                duration=0.1
            )
            
            return result
            
    except Exception as e:
        logger.error(f"Password change proxy failed: {e}")
        
        # 메트릭 기록
        record_audit_service_request(
            method="POST",
            endpoint="/auth/change-password",
            status="error",
            duration=0.1
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change failed"
        )


# MFA 관련 엔드포인트

@router.post("/auth/mfa/setup")
async def setup_mfa(request: Request):
    """
    MFA 설정 (User Service 프록시)
    
    - TOTP 시크릿과 QR 코드 생성
    - User Service로 요청 전달
    """
    client = get_user_service_client()
    
    # Authorization 헤더에서 토큰 추출
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = auth_header[7:]  # "Bearer " 제거
    
    try:
        async with client:
            result = await client.setup_mfa(token)
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/mfa/setup",
                status="success",
                duration=0.1
            )
            
            return result
            
    except Exception as e:
        logger.error(f"MFA setup proxy failed: {e}")
        
        # 메트릭 기록
        record_audit_service_request(
            method="POST",
            endpoint="/auth/mfa/setup",
            status="error",
            duration=0.1
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA setup failed"
        )


@router.post("/auth/mfa/enable")
async def enable_mfa(
    request: Request,
    mfa_request: MFAEnableRequest
):
    """
    MFA 활성화 (User Service 프록시)
    
    - TOTP 코드 확인 후 MFA 활성화
    - User Service로 요청 전달
    """
    client = get_user_service_client()
    
    # Authorization 헤더에서 토큰 추출
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = auth_header[7:]  # "Bearer " 제거
    
    try:
        async with client:
            result = await client.enable_mfa(token, mfa_request.code)
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/mfa/enable",
                status="success",
                duration=0.1
            )
            
            return result
            
    except Exception as e:
        logger.error(f"MFA enable proxy failed: {e}")
        
        # 메트릭 기록
        record_audit_service_request(
            method="POST",
            endpoint="/auth/mfa/enable",
            status="error",
            duration=0.1
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA enable failed"
        )


@router.post("/auth/mfa/disable")
async def disable_mfa(
    request: Request,
    mfa_request: MFADisableRequest
):
    """
    MFA 비활성화 (User Service 프록시)
    
    - 비밀번호와 TOTP 코드 확인 후 MFA 비활성화
    - User Service로 요청 전달
    """
    client = get_user_service_client()
    
    # Authorization 헤더에서 토큰 추출
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = auth_header[7:]  # "Bearer " 제거
    
    try:
        async with client:
            result = await client.disable_mfa(
                token, 
                mfa_request.password, 
                mfa_request.code
            )
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/mfa/disable",
                status="success",
                duration=0.1
            )
            
            return result
            
    except Exception as e:
        logger.error(f"MFA disable proxy failed: {e}")
        
        # 메트릭 기록
        record_audit_service_request(
            method="POST",
            endpoint="/auth/mfa/disable",
            status="error",
            duration=0.1
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA disable failed"
        )


@router.get("/.well-known/jwks.json")
async def get_jwks():
    """
    JWKS 키 조회 (User Service 프록시)
    
    - JWT 서명 검증용 공개 키 조회
    - User Service로 요청 전달
    """
    client = get_user_service_client()
    
    try:
        async with client:
            result = await client.get_jwks()
            
            # 메트릭 기록
            record_audit_service_request(
                method="GET",
                endpoint="/.well-known/jwks.json",
                status="success",
                duration=0.1
            )
            
            return result
            
    except Exception as e:
        logger.error(f"JWKS proxy failed: {e}")
        
        # 메트릭 기록
        record_audit_service_request(
            method="GET",
            endpoint="/.well-known/jwks.json",
            status="error",
            duration=0.1
        )
        
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWKS service unavailable"
        )