"""
Observability 더미 구현
"""

def add_span_attributes(**kwargs):
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