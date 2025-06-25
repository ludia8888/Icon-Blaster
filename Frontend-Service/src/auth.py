"""
Frontend Service - Authentication Module
WebSocket 연결 인증 처리
"""
import jwt
from typing import Optional
from datetime import datetime, timedelta

from shared.auth import User

# JWT 설정 (환경변수에서 로드)
JWT_SECRET_KEY = "frontend-service-secret"  # 실제로는 환경변수 사용
JWT_ALGORITHM = "HS256"


def verify_websocket_token(token: str) -> Optional[User]:
    """
    WebSocket 연결용 JWT 토큰 검증
    
    Args:
        token: JWT 토큰 문자열
        
    Returns:
        User 객체 또는 None (인증 실패시)
        
    Raises:
        Exception: 토큰이 유효하지 않은 경우
    """
    try:
        # JWT 토큰 디코딩
        payload = jwt.decode(
            token, 
            JWT_SECRET_KEY, 
            algorithms=[JWT_ALGORITHM]
        )
        
        # 토큰 만료 확인
        exp = payload.get("exp")
        if exp and datetime.utcnow().timestamp() > exp:
            raise Exception("Token expired")
        
        # 사용자 정보 추출
        user_id = payload.get("user_id")
        username = payload.get("username", user_id)
        roles = payload.get("roles", [])
        
        if not user_id:
            raise Exception("Invalid token: missing user_id")
        
        return User(
            user_id=user_id,
            username=username,
            roles=roles
        )
        
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")
    except Exception as e:
        raise Exception(f"Token verification failed: {str(e)}")


def create_websocket_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    """
    WebSocket 연결용 JWT 토큰 생성
    
    Args:
        user: 사용자 객체
        expires_delta: 토큰 만료 시간 (기본: 1시간)
        
    Returns:
        JWT 토큰 문자열
    """
    if expires_delta is None:
        expires_delta = timedelta(hours=1)
    
    expire = datetime.utcnow() + expires_delta
    
    payload = {
        "user_id": user.user_id,
        "username": user.username,
        "roles": user.roles,
        "exp": expire.timestamp(),
        "iat": datetime.utcnow().timestamp(),
        "type": "websocket"
    }
    
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)