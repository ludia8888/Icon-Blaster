"""
공통 설정 모델
모든 서비스에서 사용하는 설정 데이터 클래스
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class ConnectionConfig:
    """데이터베이스 연결 설정 - 모든 서비스 공통"""
    
    server_url: str = "http://localhost:6363"
    user: str = "admin"
    account: str = "admin"
    key: str = "admin123"
    timeout: int = 30
    
    # Connection pool settings
    use_pool: bool = False
    pool_size: int = 10
    pool_timeout: int = 30
    
    # Retry settings
    retry_attempts: int = 3
    retry_delay: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "server_url": self.server_url,
            "user": self.user,
            "account": self.account,
            "key": self.key,
            "timeout": self.timeout,
            "use_pool": self.use_pool,
            "pool_size": self.pool_size,
            "pool_timeout": self.pool_timeout,
            "retry_attempts": self.retry_attempts,
            "retry_delay": self.retry_delay
        }
    
    def to_terminus_format(self) -> Dict[str, Any]:
        """TerminusDB 클라이언트 형식으로 변환"""
        return {
            "server_url": self.server_url,
            "user": self.user,
            "account": self.account,
            "key": self.key
        }
    
    @classmethod
    def from_env(cls) -> 'ConnectionConfig':
        """환경 변수에서 설정 로드"""
        import os
        return cls(
            server_url=os.getenv("TERMINUS_SERVER_URL", "http://localhost:6363"),
            user=os.getenv("TERMINUS_USER", "admin"),
            account=os.getenv("TERMINUS_ACCOUNT", "admin"),
            key=os.getenv("TERMINUS_KEY", "admin123"),
            timeout=int(os.getenv("TERMINUS_TIMEOUT", "30")),
            use_pool=os.getenv("TERMINUS_USE_POOL", "false").lower() == "true",
            pool_size=int(os.getenv("TERMINUS_POOL_SIZE", "10")),
            pool_timeout=int(os.getenv("TERMINUS_POOL_TIMEOUT", "30")),
            retry_attempts=int(os.getenv("TERMINUS_RETRY_ATTEMPTS", "3")),
            retry_delay=float(os.getenv("TERMINUS_RETRY_DELAY", "1.0"))
        )


# 하위 호환성을 위한 별칭
ConnectionInfo = ConnectionConfig
AsyncConnectionInfo = ConnectionConfig