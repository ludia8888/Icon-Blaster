# Arrakis 프로젝트 근본적 문제 해결 방안

## 1. AppConfig TypeError 해결

### 문제의 본질
- `@lru_cache()` 데코레이터가 AppConfig 객체를 해시하려 시도
- Pydantic BaseSettings는 해시 불가능한 타입
- 이중 캐싱으로 인한 복잡성 증가

### 해결 방안

#### Option A: lru_cache 제거 (권장)
```python
# bootstrap/dependencies.py 수정

# @lru_cache() 제거
def get_database_provider(config: Annotated[AppConfig, Depends(get_config)]) -> DatabaseProvider:
    """Get database provider instance"""
    if _providers["database"] is None:
        _providers["database"] = DatabaseProvider(
            endpoint=config.database.endpoint,
            team=config.database.team,
            db=config.database.db,
            user=config.database.user,
            key=config.database.key
        )
    return _providers["database"]
```

#### Option B: 전체 의존성 주입 재설계
```python
# bootstrap/providers_manager.py 생성
import asyncio
from typing import Dict, Any
from contextvars import ContextVar

class ProvidersManager:
    """Thread-safe providers manager"""
    def __init__(self):
        self._providers: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
    
    async def get_or_create(self, key: str, factory):
        async with self._lock:
            if key not in self._providers:
                self._providers[key] = await factory()
            return self._providers[key]

# 싱글톤 인스턴스
providers_manager = ProvidersManager()
```

## 2. 동시성 처리 개선

### 문제의 본질
- 전역 상태 관리가 thread-safe하지 않음
- 높은 동시 요청 시 리소스 경합
- 비동기 처리와 동기 코드 혼재

### 해결 방안

#### 연결 풀 및 제한 설정
```python
# bootstrap/config.py에 추가
class PerformanceConfig(BaseSettings):
    """Performance configuration"""
    max_connections: int = Field(default=100, env="MAX_CONNECTIONS")
    connection_timeout: int = Field(default=30, env="CONNECTION_TIMEOUT")
    request_timeout: int = Field(default=60, env="REQUEST_TIMEOUT")
    max_concurrent_requests: int = Field(default=50, env="MAX_CONCURRENT_REQUESTS")
```

#### Rate Limiting 구현
```python
# middleware/rate_limiter.py
from fastapi import Request, HTTPException
from collections import defaultdict
import time
import asyncio

class RateLimiter:
    def __init__(self, requests_per_minute: int = 100):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(self, client_id: str):
        async with self._lock:
            now = time.time()
            minute_ago = now - 60
            
            # 1분 이상 지난 요청 제거
            self.requests[client_id] = [
                req_time for req_time in self.requests[client_id]
                if req_time > minute_ago
            ]
            
            if len(self.requests[client_id]) >= self.requests_per_minute:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            
            self.requests[client_id].append(now)
```

## 3. User Info 엔드포인트 수정

### 문제의 본질
- NGINX 라우팅과 실제 엔드포인트 불일치
- 인증 미들웨어 체인 문제

### 해결 방안

#### NGINX 설정 확인 및 수정
```nginx
# nginx.conf 수정 필요 부분
location /auth/userinfo {
    proxy_pass http://user-service:8001/auth/userinfo;
    proxy_set_header Authorization $http_authorization;
}
```

#### User Service 엔드포인트 검증
```python
# user-service/src/api/auth.py 확인
@router.get("/auth/userinfo")
async def get_user_info(
    current_user: User = Depends(get_current_user)
):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "roles": current_user.roles
    }
```

## 4. 아키텍처 개선 사항

### 단기 개선 (즉시 적용 가능)
1. **의존성 주입 단순화**
   - lru_cache 제거
   - FastAPI의 기본 의존성 주입만 사용

2. **에러 핸들링 강화**
   - 전역 예외 핸들러 추가
   - 상세한 에러 로깅

3. **헬스 체크 개선**
   - 각 서비스별 정확한 헬스 체크 엔드포인트
   - 의존성 체크 포함

### 중장기 개선
1. **서비스 메시 도입 검토**
   - Istio 또는 Linkerd로 서비스 간 통신 관리
   - 자동 retry, circuit breaker 등

2. **이벤트 소싱 패턴 강화**
   - CQRS 패턴 완전 구현
   - 이벤트 스토어 분리

3. **모니터링 강화**
   - Distributed tracing 완전 구현
   - 성능 메트릭 수집 및 알림

## 5. 즉시 실행 가능한 수정 사항

### Step 1: AppConfig 오류 수정
```bash
# dependencies.py에서 모든 @lru_cache() 제거
sed -i '/@lru_cache()/d' oms-monolith/bootstrap/dependencies.py
```

### Step 2: Thread-safe 싱글톤 구현
```python
# bootstrap/dependencies.py 상단에 추가
import threading

_providers_lock = threading.Lock()
```

### Step 3: 동시성 제한 설정
```yaml
# docker-compose.yml의 OMS 서비스에 추가
environment:
  - MAX_CONCURRENT_REQUESTS=30
  - CONNECTION_TIMEOUT=60
```

### Step 4: NGINX 버퍼 크기 증가
```nginx
# nginx.conf에 추가
proxy_buffer_size 128k;
proxy_buffers 4 256k;
proxy_busy_buffers_size 256k;
```

## 결론

현재 시스템의 주요 문제는:
1. **과도한 최적화 시도** (이중 캐싱)
2. **동시성 고려 부족** (thread-safety)
3. **복잡한 의존성 체인**

해결 방향:
1. **단순화** - 불필요한 캐싱 제거
2. **명확성** - 각 컴포넌트의 책임 명확화
3. **안정성** - 동시성 및 에러 처리 강화

이러한 수정사항을 적용하면 시스템의 안정성과 성능이 크게 개선될 것입니다.