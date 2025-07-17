"""
언어 관련 유틸리티 함수들
중복 구현 방지를 위한 공통 모듈
"""

from fastapi import Request


def get_accept_language(request: Request) -> str:
    """
    요청 헤더에서 언어 추출
    
    Args:
        request: FastAPI Request 객체
        
    Returns:
        추출된 언어 코드 (기본값: 'ko')
    """
    accept_language = request.headers.get("Accept-Language", "ko")
    # 첫 번째 언어만 추출 (간단한 구현)
    # 예: "en-US,en;q=0.9,ko;q=0.8" -> "en"
    result = accept_language.split(",")[0].split("-")[0]
    return result