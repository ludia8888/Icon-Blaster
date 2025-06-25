"""
RBAC (Role-Based Access Control) Middleware
"""
from typing import Callable, Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

class RBACMiddleware:
    """역할 기반 접근 제어 미들웨어"""
    
    def __init__(self, app, permissions_map: dict = None):
        self.app = app
        self.permissions_map = permissions_map or {}
    
    async def __call__(self, request: Request, call_next: Callable):
        # 간단한 RBAC 구현
        # 실제로는 JWT 토큰에서 역할을 추출하고 권한을 확인해야 함
        
        # 현재는 모든 요청을 통과시킴
        response = await call_next(request)
        return response

def create_rbac_middleware(permissions_map: dict = None):
    """RBAC 미들웨어 생성 함수"""
    def middleware(app):
        return RBACMiddleware(app, permissions_map)
    return middleware