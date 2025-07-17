"""
서비스 인터페이스 정의
SOLID 원칙에 따라 작은 단위로 분리된 인터페이스들
"""

from .connection import IConnectionManager, IConnectionPool
from ..config import ConnectionConfig
from .database import IDatabaseService
from .ontology import IOntologyRepository, IOntologyValidator, IOntologyMerger
from .branch import IBranchService, IBranchMerger
from .version import IVersionService, IVersionComparator
from .query import IQueryService, IQueryBuilder, IQueryTransformer
from .label_mapper import ILabelMapperService

__all__ = [
    # Connection
    "IConnectionManager",
    "IConnectionPool",
    "ConnectionConfig",
    
    # Database
    "IDatabaseService",
    
    # Ontology
    "IOntologyRepository",
    "IOntologyValidator",
    "IOntologyMerger",
    
    # Branch
    "IBranchService",
    "IBranchMerger",
    
    # Version
    "IVersionService",
    "IVersionComparator",
    
    # Query
    "IQueryService",
    "IQueryBuilder",
    "IQueryTransformer",
    
    # Label Mapper
    "ILabelMapperService",
]