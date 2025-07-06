"""
GraphQL Auth Mutations (User Service Proxy)
GraphQL을 통한 인증 mutation들을 user-service로 프록시
"""
import strawberry
from typing import Optional, List
from strawberry.types import Info

from shared.user_service_client import get_user_service_client
from core.monitoring.audit_metrics import record_audit_service_request
from common_logging.setup import get_logger

logger = get_logger(__name__)


@strawberry.type
class AuthResponse:
    """인증 응답"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


@strawberry.type
class UserInfo:
    """사용자 정보"""
    user_id: str
    username: str
    email: str
    full_name: Optional[str] = None
    roles: List[str]
    permissions: List[str]
    teams: List[str]
    mfa_enabled: bool


@strawberry.type
class RegisterResponse:
    """회원가입 응답"""
    user: UserInfo
    message: str = "User registered successfully"


@strawberry.type
class MFASetupResponse:
    """MFA 설정 응답"""
    secret: str
    qr_code: str
    backup_codes: Optional[List[str]] = None


@strawberry.input
class LoginInput:
    """로그인 입력"""
    username: str
    password: str
    mfa_code: Optional[str] = None


@strawberry.input
class RegisterInput:
    """회원가입 입력"""
    username: str
    email: str
    password: str
    full_name: Optional[str] = None


@strawberry.input
class PasswordChangeInput:
    """비밀번호 변경 입력"""
    old_password: str
    new_password: str


@strawberry.input
class MFAEnableInput:
    """MFA 활성화 입력"""
    code: str


@strawberry.input
class MFADisableInput:
    """MFA 비활성화 입력"""
    password: str
    code: str


@strawberry.type
class AuthMutation:
    """인증 관련 GraphQL Mutation (User Service 프록시)"""
    
    @strawberry.mutation
    async def login(self, info: Info, input: LoginInput) -> AuthResponse:
        """
        사용자 로그인
        
        Args:
            input: 로그인 정보
            
        Returns:
            인증 토큰
        """
        client = get_user_service_client()
        
        try:
            async with client:
                result = await client.login(
                    username=input.username,
                    password=input.password,
                    mfa_code=input.mfa_code
                )
                
                # 메트릭 기록
                record_audit_service_request(
                    method="POST",
                    endpoint="/auth/login",
                    status="success",
                    duration=0.1
                )
                
                return AuthResponse(
                    access_token=result["access_token"],
                    refresh_token=result["refresh_token"],
                    token_type=result.get("token_type", "bearer"),
                    expires_in=result.get("expires_in", 1800)
                )
                
        except Exception as e:
            logger.error(f"GraphQL login failed: {e}")
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/login",
                status="error",
                duration=0.1
            )
            
            raise Exception("Authentication failed")
    
    @strawberry.mutation
    async def register(self, info: Info, input: RegisterInput) -> RegisterResponse:
        """
        사용자 회원가입
        
        Args:
            input: 회원가입 정보
            
        Returns:
            생성된 사용자 정보
        """
        client = get_user_service_client()
        
        try:
            async with client:
                result = await client.register(
                    username=input.username,
                    email=input.email,
                    password=input.password,
                    full_name=input.full_name
                )
                
                # 메트릭 기록
                record_audit_service_request(
                    method="POST",
                    endpoint="/auth/register",
                    status="success",
                    duration=0.1
                )
                
                user_data = result["user"]
                return RegisterResponse(
                    user=UserInfo(
                        user_id=user_data["user_id"],
                        username=user_data["username"],
                        email=user_data["email"],
                        full_name=user_data.get("full_name"),
                        roles=user_data.get("roles", []),
                        permissions=user_data.get("permissions", []),
                        teams=user_data.get("teams", []),
                        mfa_enabled=user_data.get("mfa_enabled", False)
                    ),
                    message=result.get("message", "User registered successfully")
                )
                
        except Exception as e:
            logger.error(f"GraphQL registration failed: {e}")
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/register",
                status="error",
                duration=0.1
            )
            
            raise Exception("Registration failed")
    
    @strawberry.mutation
    async def logout(self, info: Info) -> str:
        """
        사용자 로그아웃
        
        Returns:
            로그아웃 메시지
        """
        client = get_user_service_client()
        
        # Authorization 헤더에서 토큰 추출
        request = info.context["request"]
        auth_header = request.headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Bearer "):
            raise Exception("Missing or invalid authorization header")
        
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
                
                return result.get("message", "Logged out successfully")
                
        except Exception as e:
            logger.error(f"GraphQL logout failed: {e}")
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/logout",
                status="error",
                duration=0.1
            )
            
            # 로그아웃은 실패해도 성공 반환
            return "Logged out"
    
    @strawberry.mutation
    async def change_password(self, info: Info, input: PasswordChangeInput) -> str:
        """
        비밀번호 변경
        
        Args:
            input: 비밀번호 변경 정보
            
        Returns:
            변경 결과 메시지
        """
        client = get_user_service_client()
        
        # Authorization 헤더에서 토큰 추출
        request = info.context["request"]
        auth_header = request.headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Bearer "):
            raise Exception("Missing or invalid authorization header")
        
        token = auth_header[7:]  # "Bearer " 제거
        
        try:
            async with client:
                result = await client.change_password(
                    token=token,
                    old_password=input.old_password,
                    new_password=input.new_password
                )
                
                # 메트릭 기록
                record_audit_service_request(
                    method="POST",
                    endpoint="/auth/change-password",
                    status="success",
                    duration=0.1
                )
                
                return result.get("message", "Password changed successfully")
                
        except Exception as e:
            logger.error(f"GraphQL password change failed: {e}")
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/change-password",
                status="error",
                duration=0.1
            )
            
            raise Exception("Password change failed")
    
    @strawberry.mutation
    async def setup_mfa(self, info: Info) -> MFASetupResponse:
        """
        MFA 설정
        
        Returns:
            MFA 설정 정보
        """
        client = get_user_service_client()
        
        # Authorization 헤더에서 토큰 추출
        request = info.context["request"]
        auth_header = request.headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Bearer "):
            raise Exception("Missing or invalid authorization header")
        
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
                
                return MFASetupResponse(
                    secret=result["secret"],
                    qr_code=result["qr_code"],
                    backup_codes=result.get("backup_codes")
                )
                
        except Exception as e:
            logger.error(f"GraphQL MFA setup failed: {e}")
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/mfa/setup",
                status="error",
                duration=0.1
            )
            
            raise Exception("MFA setup failed")
    
    @strawberry.mutation
    async def enable_mfa(self, info: Info, input: MFAEnableInput) -> str:
        """
        MFA 활성화
        
        Args:
            input: MFA 활성화 정보
            
        Returns:
            활성화 결과 메시지
        """
        client = get_user_service_client()
        
        # Authorization 헤더에서 토큰 추출
        request = info.context["request"]
        auth_header = request.headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Bearer "):
            raise Exception("Missing or invalid authorization header")
        
        token = auth_header[7:]  # "Bearer " 제거
        
        try:
            async with client:
                result = await client.enable_mfa(token, input.code)
                
                # 메트릭 기록
                record_audit_service_request(
                    method="POST",
                    endpoint="/auth/mfa/enable",
                    status="success",
                    duration=0.1
                )
                
                return result.get("message", "MFA enabled successfully")
                
        except Exception as e:
            logger.error(f"GraphQL MFA enable failed: {e}")
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/mfa/enable",
                status="error",
                duration=0.1
            )
            
            raise Exception("MFA enable failed")
    
    @strawberry.mutation
    async def disable_mfa(self, info: Info, input: MFADisableInput) -> str:
        """
        MFA 비활성화
        
        Args:
            input: MFA 비활성화 정보
            
        Returns:
            비활성화 결과 메시지
        """
        client = get_user_service_client()
        
        # Authorization 헤더에서 토큰 추출
        request = info.context["request"]
        auth_header = request.headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Bearer "):
            raise Exception("Missing or invalid authorization header")
        
        token = auth_header[7:]  # "Bearer " 제거
        
        try:
            async with client:
                result = await client.disable_mfa(
                    token, 
                    input.password, 
                    input.code
                )
                
                # 메트릭 기록
                record_audit_service_request(
                    method="POST",
                    endpoint="/auth/mfa/disable",
                    status="success",
                    duration=0.1
                )
                
                return result.get("message", "MFA disabled successfully")
                
        except Exception as e:
            logger.error(f"GraphQL MFA disable failed: {e}")
            
            # 메트릭 기록
            record_audit_service_request(
                method="POST",
                endpoint="/auth/mfa/disable",
                status="error",
                duration=0.1
            )
            
            raise Exception("MFA disable failed")


# GraphQL 스키마에 추가할 mutation
auth_mutation = AuthMutation()