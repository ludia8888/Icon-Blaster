# Event Publisher Core Package

from .enhanced_event_service import EnhancedEventService

# 전역 기본 서비스 인스턴스
_DEFAULT_SERVICE = None

def get_event_publisher() -> EnhancedEventService:
    """
    History 모듈 등에서 호출하는 기본 이벤트 퍼블리셔
    싱글톤 패턴으로 동일한 인스턴스 반환
    """
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = EnhancedEventService()
    return _DEFAULT_SERVICE

# Export for convenience
__all__ = ['EnhancedEventService', 'get_event_publisher']
