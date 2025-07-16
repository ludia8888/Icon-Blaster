"""
핵심 서비스 모듈
SOLID 원칙에 따라 분리된 모든 서비스를 포함
"""

# 설정
from .config import (
    ConnectionConfig,
    CacheConfig,
    LoggingConfig,
    SecurityConfig,
    ServiceConfig
)

# 연결 관리
from .connection import TerminusConnectionManager

# 데이터베이스 관리
from .database import TerminusDatabaseService

# 온톨로지 관리
from .ontology import (
    TerminusOntologyRepository,
    TerminusOntologyValidator,
    TerminusOntologyMerger
)

# 브랜치 관리
from .branch import (
    TerminusBranchService,
    TerminusBranchMerger
)

# 버전 관리
from .version import (
    TerminusVersionService,
    TerminusVersionComparator
)

# 쿼리 실행
from .query import (
    TerminusQueryService,
    TerminusQueryBuilder,
    TerminusQueryTransformer,
    LabelQueryBuilder
)

# 레이블 매퍼
from .label import TerminusLabelMapperService

__all__ = [
    # Config
    'ConnectionConfig',
    'CacheConfig', 
    'LoggingConfig',
    'SecurityConfig',
    'ServiceConfig',
    
    # Connection
    'TerminusConnectionManager',
    
    # Database
    'TerminusDatabaseService',
    
    # Ontology
    'TerminusOntologyRepository',
    'TerminusOntologyValidator',
    'TerminusOntologyMerger',
    
    # Branch
    'TerminusBranchService',
    'TerminusBranchMerger',
    
    # Version
    'TerminusVersionService',
    'TerminusVersionComparator',
    
    # Query
    'TerminusQueryService',
    'TerminusQueryBuilder',
    'TerminusQueryTransformer',
    'LabelQueryBuilder',
    
    # Label Mapper
    'TerminusLabelMapperService'
]