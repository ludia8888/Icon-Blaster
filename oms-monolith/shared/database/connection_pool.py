"""
Connection Pool 더미 구현
TerminusDB 내부 캐싱을 사용하므로 실제 connection pool은 필요없음
"""

class ConnectionConfig:
    """연결 설정"""
    def __init__(self, **kwargs):
        self.config = kwargs

class PoolManager:
    """풀 매니저 더미"""
    def __init__(self):
        pass
    
    def get_pool(self, name: str):
        return None

def get_db_connection(config: str = None):
    """DB 연결 더미"""
    return None

pool_manager = PoolManager()