"""
Observability 더미 구현
"""

class DummyMetrics:
    """더미 메트릭스 클래스"""
    def increment(self, *args, **kwargs):
        pass
    
    def histogram(self, *args, **kwargs):
        pass
    
    def gauge(self, *args, **kwargs):
        pass

class DummyTracing:
    """더미 트레이싱 클래스"""
    def get_tracer(self, name):
        return self
    
    def start_span(self, *args, **kwargs):
        return self
        
    def __enter__(self):
        return self
        
    def __exit__(self, *args):
        pass

metrics = DummyMetrics()
tracing = DummyTracing()

def add_span_attributes(attributes=None):
    """span 속성 추가 더미"""
    pass

def inject_trace_context(headers):
    """trace context 주입 더미"""
    return headers

def trace_method(operation_name: str = "", kind=None):
    """메서드 추적 데코레이터 더미"""
    def decorator(func):
        return func
    return decorator