"""
SmartCacheManager - Dummy implementation
TerminusDB의 내부 캐시 기능을 사용하므로 이 클래스는 더미로 구현
"""

class SmartCacheManager:
    """더미 캐시 매니저 - TerminusDB 내부 캐시 사용"""
    
    def __init__(self, *args, **kwargs):
        pass
    
    def get(self, key):
        return None
    
    def set(self, key, value, ttl=None):
        pass
    
    def delete(self, key):
        pass
    
    def clear(self):
        pass
    
    def exists(self, key):
        return False