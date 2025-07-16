"""
의존성 주입 컨테이너
모든 서비스의 생성과 의존성 관리를 담당
ISP, DIP 원칙에 따라 인터페이스를 통해 의존성 주입
"""

from typing import Optional, Dict, Any
import logging
from functools import lru_cache

from services.core.config import ServiceConfig
from services.core.interfaces import (
    IConnectionManager,
    IDatabaseService,
    IOntologyRepository,
    IOntologyValidator,
    IOntologyMerger,
    IBranchService,
    IBranchMerger,
    IVersionService,
    IQueryService,
    ILabelMapperService
)
from services.core import (
    TerminusConnectionManager,
    TerminusDatabaseService,
    TerminusOntologyRepository,
    TerminusOntologyValidator,
    TerminusOntologyMerger,
    TerminusBranchService,
    TerminusBranchMerger,
    TerminusVersionService,
    TerminusQueryService,
    TerminusLabelMapperService
)

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    서비스 컨테이너
    
    모든 서비스의 생성과 의존성 관리를 담당합니다.
    싱글톤 패턴으로 구현되어 애플리케이션 전체에서 하나의 인스턴스만 존재합니다.
    """
    
    _instance: Optional['ServiceContainer'] = None
    
    def __new__(cls) -> 'ServiceContainer':
        """싱글톤 인스턴스 생성"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """초기화"""
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        self._config: Optional[ServiceConfig] = None
        self._services: Dict[str, Any] = {}
        logger.info("Service container initialized")
    
    def configure(self, config: ServiceConfig) -> None:
        """
        컨테이너 설정
        
        Args:
            config: 서비스 설정
        """
        self._config = config
        logger.info(f"Container configured for {config.environment} environment")
    
    @property
    def config(self) -> ServiceConfig:
        """설정 접근자"""
        if not self._config:
            # 기본 설정 사용
            self._config = ServiceConfig.from_env()
        return self._config
    
    # Connection Services
    
    @lru_cache(maxsize=1)
    def get_connection_manager(self) -> IConnectionManager:
        """연결 관리자 인스턴스 반환"""
        if 'connection_manager' not in self._services:
            self._services['connection_manager'] = TerminusConnectionManager(
                self.config.connection
            )
            logger.debug("Created ConnectionManager instance")
        return self._services['connection_manager']
    
    # Database Services
    
    @lru_cache(maxsize=1)
    def get_database_service(self) -> IDatabaseService:
        """데이터베이스 서비스 인스턴스 반환"""
        if 'database_service' not in self._services:
            self._services['database_service'] = TerminusDatabaseService(
                self.get_connection_manager()
            )
            logger.debug("Created DatabaseService instance")
        return self._services['database_service']
    
    # Ontology Services
    
    @lru_cache(maxsize=1)
    def get_ontology_repository(self) -> IOntologyRepository:
        """온톨로지 저장소 인스턴스 반환"""
        if 'ontology_repository' not in self._services:
            self._services['ontology_repository'] = TerminusOntologyRepository(
                self.get_connection_manager(),
                self.get_database_service(),
                self.get_ontology_validator()
            )
            logger.debug("Created OntologyRepository instance")
        return self._services['ontology_repository']
    
    @lru_cache(maxsize=1)
    def get_ontology_validator(self) -> IOntologyValidator:
        """온톨로지 검증기 인스턴스 반환"""
        if 'ontology_validator' not in self._services:
            self._services['ontology_validator'] = TerminusOntologyValidator()
            logger.debug("Created OntologyValidator instance")
        return self._services['ontology_validator']
    
    @lru_cache(maxsize=1)
    def get_ontology_merger(self) -> IOntologyMerger:
        """온톨로지 병합기 인스턴스 반환"""
        if 'ontology_merger' not in self._services:
            self._services['ontology_merger'] = TerminusOntologyMerger()
            logger.debug("Created OntologyMerger instance")
        return self._services['ontology_merger']
    
    # Branch Services
    
    @lru_cache(maxsize=1)
    def get_branch_service(self) -> IBranchService:
        """브랜치 서비스 인스턴스 반환"""
        if 'branch_service' not in self._services:
            self._services['branch_service'] = TerminusBranchService(
                self.get_connection_manager(),
                self.get_database_service()
            )
            logger.debug("Created BranchService instance")
        return self._services['branch_service']
    
    @lru_cache(maxsize=1)
    def get_branch_merger(self) -> IBranchMerger:
        """브랜치 병합기 인스턴스 반환"""
        if 'branch_merger' not in self._services:
            self._services['branch_merger'] = TerminusBranchMerger(
                self.get_connection_manager(),
                self.get_branch_service(),
                self.get_version_service(),
                self.get_ontology_validator()
            )
            logger.debug("Created BranchMerger instance")
        return self._services['branch_merger']
    
    # Version Services
    
    @lru_cache(maxsize=1)
    def get_version_service(self) -> IVersionService:
        """버전 서비스 인스턴스 반환"""
        if 'version_service' not in self._services:
            self._services['version_service'] = TerminusVersionService(
                self.get_connection_manager(),
                self.get_branch_service(),
                self.get_database_service()
            )
            logger.debug("Created VersionService instance")
        return self._services['version_service']
    
    # Query Services
    
    @lru_cache(maxsize=1)
    def get_query_service(self) -> IQueryService:
        """쿼리 서비스 인스턴스 반환"""
        if 'query_service' not in self._services:
            self._services['query_service'] = TerminusQueryService(
                self.get_connection_manager(),
                self.get_database_service()
            )
            logger.debug("Created QueryService instance")
        return self._services['query_service']
    
    # Label Mapper Service
    
    @lru_cache(maxsize=1)
    def get_label_mapper_service(self) -> ILabelMapperService:
        """레이블 매퍼 서비스 인스턴스 반환"""
        if 'label_mapper_service' not in self._services:
            self._services['label_mapper_service'] = TerminusLabelMapperService(
                self.get_ontology_repository()
            )
            logger.debug("Created LabelMapperService instance")
        return self._services['label_mapper_service']
    
    # Utility Methods
    
    def close_all(self) -> None:
        """모든 서비스 종료"""
        # 연결 관리자 종료
        if 'connection_manager' in self._services:
            try:
                self._services['connection_manager'].close()
                logger.info("ConnectionManager closed")
            except Exception as e:
                logger.error(f"Error closing ConnectionManager: {e}")
        
        # 다른 서비스들 정리
        self._services.clear()
        logger.info("All services closed")
    
    def reset(self) -> None:
        """컨테이너 리셋"""
        self.close_all()
        self._config = None
        logger.info("Container reset")
    
    def get_service_stats(self) -> Dict[str, Any]:
        """서비스 통계 반환"""
        stats = {
            "environment": self.config.environment,
            "services": {
                "total": len(self._services),
                "active": list(self._services.keys())
            }
        }
        
        # 연결 풀 통계 추가
        if 'connection_manager' in self._services:
            conn_mgr = self._services['connection_manager']
            if hasattr(conn_mgr, '_connection_pool') and conn_mgr._connection_pool:
                stats["connection_pool"] = conn_mgr._connection_pool.get_stats()
        
        return stats


# 전역 컨테이너 인스턴스
container = ServiceContainer()


# FastAPI 의존성 함수들

def get_container() -> ServiceContainer:
    """컨테이너 의존성"""
    return container


def get_connection_manager() -> IConnectionManager:
    """연결 관리자 의존성"""
    return container.get_connection_manager()


def get_database_service() -> IDatabaseService:
    """데이터베이스 서비스 의존성"""
    return container.get_database_service()


def get_ontology_repository() -> IOntologyRepository:
    """온톨로지 저장소 의존성"""
    return container.get_ontology_repository()


def get_ontology_validator() -> IOntologyValidator:
    """온톨로지 검증기 의존성"""
    return container.get_ontology_validator()


def get_ontology_merger() -> IOntologyMerger:
    """온톨로지 병합기 의존성"""
    return container.get_ontology_merger()


def get_branch_service() -> IBranchService:
    """브랜치 서비스 의존성"""
    return container.get_branch_service()


def get_branch_merger() -> IBranchMerger:
    """브랜치 병합기 의존성"""
    return container.get_branch_merger()


def get_version_service() -> IVersionService:
    """버전 서비스 의존성"""
    return container.get_version_service()


def get_query_service() -> IQueryService:
    """쿼리 서비스 의존성"""
    return container.get_query_service()


def get_label_mapper_service() -> ILabelMapperService:
    """레이블 매퍼 서비스 의존성"""
    return container.get_label_mapper_service()