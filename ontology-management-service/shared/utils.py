"""
Utility 함수 더미 구현
"""
import functools
from typing import Any, Callable

# 설정 상수
DB_CRITICAL_CONFIG = "critical"
DB_READ_CONFIG = "read"
DB_WRITE_CONFIG = "write"

def with_retry(operation_name: str = "", config: str = DB_READ_CONFIG):
    """재시도 데코레이터"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            return await func(*args, **kwargs)
        return wrapper
    return decorator