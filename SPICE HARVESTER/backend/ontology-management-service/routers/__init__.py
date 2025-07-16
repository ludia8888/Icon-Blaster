"""
API 라우터 모듈
도메인별로 분리된 라우터들을 포함
"""

from .database import router as database_router
from .ontology import router as ontology_router
from .branch import router as branch_router
from .version import router as version_router

__all__ = [
    'database_router',
    'ontology_router',
    'branch_router',
    'version_router'
]