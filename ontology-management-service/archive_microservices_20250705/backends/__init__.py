# Event Publisher Core Package

import os

# 전역 기본 서비스 인스턴스
_DEFAULT_SERVICE = None

def get_event_publisher():
    """
    History 모듈 등에서 호출하는 기본 이벤트 퍼블리셔
    싱글톤 패턴으로 동일한 인스턴스 반환
    """
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        # Use HTTP backend as default
        from .http_backend import HTTPEventBackend
        _DEFAULT_SERVICE = HTTPEventBackend()
    return _DEFAULT_SERVICE

# Export for convenience
__all__ = ['get_event_publisher']
