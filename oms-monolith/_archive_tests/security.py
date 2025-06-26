"""
네트워크 및 보안 설정
- TLS/mTLS 설정
- 토큰 관리 및 자동 재발급
"""
import asyncio
import logging
import os
import ssl
from datetime import datetime, timedelta
from typing import Any, Dict

import jwt
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class SecurityConfig:
    """보안 설정 관리"""

    def __init__(self):
        # TLS 인증서 경로
        self.ca_cert = os.getenv("CA_CERT_PATH", "/certs/ca.crt")
        self.client_cert = os.getenv("CLIENT_CERT_PATH", "/certs/client.crt")
        self.client_key = os.getenv("CLIENT_KEY_PATH", "/certs/client.key")

        # JWT 설정
        self.jwt_secret = os.getenv("JWT_SECRET_KEY", "your-secret-key")
        self.jwt_algorithm = "HS256"
        self.jwt_expiry_minutes = 30

        # NATS 보안 설정
        self.nats_user = os.getenv("NATS_USER")
        self.nats_password = os.getenv("NATS_PASSWORD")
        self.nats_token = os.getenv("NATS_TOKEN")

    def create_ssl_context(self) -> ssl.SSLContext:
        """mTLS를 위한 SSL 컨텍스트 생성"""
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

        # CA 인증서 로드
        if os.path.exists(self.ca_cert):
            context.load_verify_locations(self.ca_cert)

        # 클라이언트 인증서 로드 (mTLS)
        if os.path.exists(self.client_cert) and os.path.exists(self.client_key):
            context.load_cert_chain(self.client_cert, self.client_key)

        # 보안 설정 강화
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        return context

class TokenManager:
    """토큰 관리 및 자동 재발급"""

    def __init__(self, security_config: SecurityConfig):
        self.config = security_config
        self._tokens: Dict[str, Dict[str, Any]] = {}
        self._refresh_tasks: Dict[str, asyncio.Task] = {}

    async def get_token(self, user_id: str, force_refresh: bool = False) -> str:
        """토큰 획득 (필요시 자동 재발급)"""
        token_info = self._tokens.get(user_id)

        # 토큰이 없거나 만료 임박
        if not token_info or force_refresh or self._is_expiring_soon(token_info):
            return await self._refresh_token(user_id)

        return token_info["token"]

    def _is_expiring_soon(self, token_info: Dict[str, Any]) -> bool:
        """토큰 만료 5분 전 체크"""
        expiry = token_info.get("expiry")
        if not expiry:
            return True

        return datetime.now() > expiry - timedelta(minutes=5)

    async def _refresh_token(self, user_id: str) -> str:
        """토큰 재발급"""
        try:
            # JWT 토큰 생성
            expiry = datetime.now() + timedelta(minutes=self.config.jwt_expiry_minutes)
            payload = {
                "user_id": user_id,
                "exp": expiry,
                "iat": datetime.now()
            }

            token = jwt.encode(payload, self.config.jwt_secret, algorithm=self.config.jwt_algorithm)

            # 토큰 저장
            self._tokens[user_id] = {
                "token": token,
                "expiry": expiry,
                "created_at": datetime.now()
            }

            # 자동 재발급 스케줄링
            self._schedule_refresh(user_id)

            logger.info(f"Token refreshed for user {user_id}")
            return token

        except Exception as e:
            logger.error(f"Token refresh failed for user {user_id}: {e}")
            raise HTTPException(status_code=500, detail="Token refresh failed")

    def _schedule_refresh(self, user_id: str):
        """토큰 자동 재발급 스케줄링"""
        # 기존 태스크 취소
        if user_id in self._refresh_tasks:
            self._refresh_tasks[user_id].cancel()

        # 만료 10분 전 재발급
        async def refresh_task():
            await asyncio.sleep((self.config.jwt_expiry_minutes - 10) * 60)
            await self._refresh_token(user_id)

        self._refresh_tasks[user_id] = asyncio.create_task(refresh_task())

class NATSSecurityHandler:
    """NATS 보안 연결 핸들러"""

    def __init__(self, security_config: SecurityConfig):
        self.config = security_config
        self.retry_count = 3
        self.retry_delay = 5  # seconds

    async def connect_with_retry(self, nats_url: str):
        """mTLS 핸드셰이크 실패 시 재시도 로직"""
        import nats
        from nats.errors import Error as NATSError

        last_error = None
        ssl_context = self.config.create_ssl_context()

        for attempt in range(self.retry_count):
            try:
                logger.info(f"NATS connection attempt {attempt + 1}/{self.retry_count}")

                # 연결 옵션 설정
                options = {
                    "servers": [nats_url],
                    "tls": ssl_context,
                    "tls_hostname": self._extract_hostname(nats_url),
                    "connect_timeout": 10,
                    "max_reconnect_attempts": 5,
                    "reconnect_time_wait": 2,
                }

                # 인증 정보 추가
                if self.config.nats_user and self.config.nats_password:
                    options["user"] = self.config.nats_user
                    options["password"] = self.config.nats_password
                elif self.config.nats_token:
                    options["token"] = self.config.nats_token

                # 연결 시도
                nc = await nats.connect(**options)

                # 연결 상태 확인
                if nc.is_connected:
                    logger.info("NATS connected successfully with TLS")
                    return nc

            except NATSError as e:
                last_error = e
                logger.warning(f"NATS connection failed (attempt {attempt + 1}): {e}")

                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay)
                    # 지수 백오프
                    self.retry_delay *= 2

        raise Exception(f"Failed to connect to NATS after {self.retry_count} attempts: {last_error}")

    def _extract_hostname(self, nats_url: str) -> str:
        """URL에서 호스트명 추출"""
        from urllib.parse import urlparse
        parsed = urlparse(nats_url)
        return parsed.hostname or "localhost"

# 전역 인스턴스
security_config = SecurityConfig()
token_manager = TokenManager(security_config)
nats_security = NATSSecurityHandler(security_config)
