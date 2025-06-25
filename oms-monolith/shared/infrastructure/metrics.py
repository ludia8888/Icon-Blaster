"""
메트릭 수집 더미 구현
"""

class MetricsCollector:
    """메트릭 수집기 더미"""
    
    def __init__(self):
        pass
    
    def increment(self, metric_name: str, value: int = 1, tags: dict = None):
        """카운터 증가"""
        pass
    
    def gauge(self, metric_name: str, value: float, tags: dict = None):
        """게이지 설정"""
        pass
    
    def histogram(self, metric_name: str, value: float, tags: dict = None):
        """히스토그램 기록"""
        pass
    
    def timing(self, metric_name: str, duration: float, tags: dict = None):
        """시간 측정"""
        pass