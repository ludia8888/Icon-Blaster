"""
브랜치 관리 서비스 구현
브랜치 생성, 삭제, 체크아웃, 목록 조회를 담당
SRP: 오직 브랜치 관리만 담당
"""

import logging
from typing import Dict, List, Optional, Any
from functools import lru_cache

from services.core.interfaces import IBranchService, IConnectionManager, IDatabaseService
from domain.exceptions import (
    BranchNotFoundError,
    BranchAlreadyExistsError,
    ProtectedBranchError,
    InvalidBranchNameError,
    DomainException
)

logger = logging.getLogger(__name__)


class TerminusBranchService(IBranchService):
    """
    TerminusDB 브랜치 관리 서비스
    
    단일 책임: 브랜치 관리 작업만 담당
    """
    
    # 보호된 브랜치 목록
    PROTECTED_BRANCHES = {'main', 'master', 'production', 'prod'}
    
    # 브랜치 이름 패턴
    BRANCH_NAME_PATTERN = r'^[a-zA-Z][a-zA-Z0-9_-]*$'
    
    def __init__(self, connection_manager: IConnectionManager, 
                 database_service: IDatabaseService):
        """
        초기화
        
        Args:
            connection_manager: 연결 관리자
            database_service: 데이터베이스 서비스
        """
        self.connection_manager = connection_manager
        self.database_service = database_service
        self._branch_cache: Dict[str, List[str]] = {}
    
    def list_branches(self, db_name: str) -> List[Dict[str, Any]]:
        """
        브랜치 목록 조회
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            브랜치 정보 목록
            
        Raises:
            DomainException: 조회 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        try:
            with self.connection_manager.get_connection(db_name) as client:
                branches = client.get_branches()
                
                # 브랜치 정보 변환
                branch_info = []
                for branch in branches:
                    info = {
                        'name': branch,
                        'current': branch == self.get_current_branch(db_name),
                        'protected': branch in self.PROTECTED_BRANCHES
                    }
                    
                    # 추가 정보 조회
                    try:
                        branch_details = self._get_branch_details(db_name, branch)
                        info.update(branch_details)
                    except Exception as e:
                        logger.warning(f"Failed to get details for branch '{branch}': {e}")
                    
                    branch_info.append(info)
                
                # 캐시 업데이트
                self._branch_cache[db_name] = [b['name'] for b in branch_info]
                
                logger.info(f"Listed {len(branch_info)} branches from database '{db_name}'")
                return branch_info
                
        except Exception as e:
            logger.error(f"Failed to list branches from '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to list branches from '{db_name}'",
                code="BRANCH_LIST_ERROR",
                details={"db_name": db_name, "error": str(e)}
            )
    
    def create_branch(self, db_name: str, branch_name: str,
                     from_branch: Optional[str] = None) -> Dict[str, Any]:
        """
        새 브랜치 생성
        
        Args:
            db_name: 데이터베이스 이름
            branch_name: 새 브랜치 이름
            from_branch: 기준 브랜치 (기본값: 현재 브랜치)
            
        Returns:
            생성된 브랜치 정보
            
        Raises:
            InvalidBranchNameError: 잘못된 브랜치 이름
            BranchAlreadyExistsError: 브랜치가 이미 존재
            BranchNotFoundError: 기준 브랜치를 찾을 수 없음
            DomainException: 생성 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 브랜치 이름 유효성 검증
        self._validate_branch_name(branch_name)
        
        # 중복 확인
        if self.branch_exists(db_name, branch_name):
            raise BranchAlreadyExistsError(branch_name, db_name)
        
        # 기준 브랜치 확인
        if from_branch is None:
            from_branch = self.get_current_branch(db_name)
        
        if from_branch and not self.branch_exists(db_name, from_branch):
            raise BranchNotFoundError(from_branch, db_name)
        
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 기준 브랜치 체크아웃
                if from_branch:
                    client.checkout(from_branch)
                
                # 새 브랜치 생성
                client.branch(branch_name)
                
                # 캐시 갱신
                self._clear_cache(db_name)
                
                logger.info(f"Created branch '{branch_name}' from '{from_branch or 'current'}' in '{db_name}'")
                
                return {
                    'name': branch_name,
                    'db_name': db_name,
                    'from_branch': from_branch,
                    'created': True,
                    'protected': branch_name in self.PROTECTED_BRANCHES
                }
                
        except Exception as e:
            logger.error(f"Failed to create branch '{branch_name}' in '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to create branch '{branch_name}'",
                code="BRANCH_CREATE_ERROR",
                details={"branch_name": branch_name, "db_name": db_name, "error": str(e)}
            )
    
    def delete_branch(self, db_name: str, branch_name: str) -> Dict[str, Any]:
        """
        브랜치 삭제
        
        Args:
            db_name: 데이터베이스 이름
            branch_name: 삭제할 브랜치 이름
            
        Returns:
            삭제 결과
            
        Raises:
            BranchNotFoundError: 브랜치를 찾을 수 없음
            ProtectedBranchError: 보호된 브랜치 삭제 시도
            DomainException: 삭제 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 브랜치 존재 확인
        if not self.branch_exists(db_name, branch_name):
            raise BranchNotFoundError(branch_name, db_name)
        
        # 보호된 브랜치 확인
        if branch_name in self.PROTECTED_BRANCHES:
            raise ProtectedBranchError(branch_name, "delete")
        
        # 현재 브랜치 확인
        current_branch = self.get_current_branch(db_name)
        if current_branch == branch_name:
            raise DomainException(
                message=f"Cannot delete current branch '{branch_name}'",
                code="CURRENT_BRANCH_DELETE_ERROR",
                details={"branch_name": branch_name, "db_name": db_name}
            )
        
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 브랜치 삭제
                client.delete_branch(branch_name)
                
                # 캐시 갱신
                self._clear_cache(db_name)
                
                logger.info(f"Deleted branch '{branch_name}' from database '{db_name}'")
                
                return {
                    'name': branch_name,
                    'db_name': db_name,
                    'deleted': True
                }
                
        except Exception as e:
            logger.error(f"Failed to delete branch '{branch_name}' from '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to delete branch '{branch_name}'",
                code="BRANCH_DELETE_ERROR",
                details={"branch_name": branch_name, "db_name": db_name, "error": str(e)}
            )
    
    def checkout(self, db_name: str, target: str,
                target_type: str = "branch") -> Dict[str, Any]:
        """
        브랜치 또는 커밋으로 체크아웃
        
        Args:
            db_name: 데이터베이스 이름
            target: 브랜치 이름 또는 커밋 ID
            target_type: "branch" 또는 "commit"
            
        Returns:
            체크아웃 결과
            
        Raises:
            BranchNotFoundError: 브랜치를 찾을 수 없음
            DomainException: 체크아웃 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 브랜치 존재 확인 (target_type이 "branch"인 경우)
        if target_type == "branch" and not self.branch_exists(db_name, target):
            raise BranchNotFoundError(target, db_name)
        
        try:
            with self.connection_manager.get_connection(db_name) as client:
                if target_type == "branch":
                    # 브랜치 체크아웃
                    client.checkout(target)
                else:
                    # 커밋 체크아웃
                    client.checkout(target)
                
                logger.info(f"Checked out {target_type} '{target}' in database '{db_name}'")
                
                return {
                    'target': target,
                    'target_type': target_type,
                    'db_name': db_name,
                    'checked_out': True
                }
                
        except Exception as e:
            logger.error(f"Failed to checkout {target_type} '{target}' in '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to checkout {target_type} '{target}'",
                code="CHECKOUT_ERROR",
                details={"target": target, "target_type": target_type, "db_name": db_name, "error": str(e)}
            )
    
    def get_current_branch(self, db_name: str) -> Optional[str]:
        """
        현재 브랜치 조회
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            현재 브랜치 이름
        """
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # TerminusDB 클라이언트에서 현재 브랜치 정보 가져오기
                if hasattr(client, 'ref'):
                    return client.ref.get('branch', 'main')
                else:
                    # 폴백: 기본 브랜치 반환
                    return 'main'
                    
        except Exception as e:
            logger.warning(f"Failed to get current branch for '{db_name}': {e}")
            return None
    
    def _validate_branch_name(self, branch_name: str) -> None:
        """
        브랜치 이름 유효성 검증
        
        Args:
            branch_name: 검증할 브랜치 이름
            
        Raises:
            InvalidBranchNameError: 잘못된 브랜치 이름
        """
        if not branch_name:
            raise InvalidBranchNameError(branch_name, "Branch name cannot be empty")
        
        if not isinstance(branch_name, str):
            raise InvalidBranchNameError(branch_name, "Branch name must be a string")
        
        if len(branch_name) > 64:
            raise InvalidBranchNameError(branch_name, "Branch name cannot exceed 64 characters")
        
        # 특수 문자 확인
        import re
        if not re.match(self.BRANCH_NAME_PATTERN, branch_name):
            raise InvalidBranchNameError(
                branch_name, 
                "Branch name must start with a letter and contain only letters, numbers, underscores, and hyphens"
            )
        
        # 예약어 확인
        reserved_names = {'HEAD', 'ORIG_HEAD', 'FETCH_HEAD', 'MERGE_HEAD'}
        if branch_name.upper() in reserved_names:
            raise InvalidBranchNameError(branch_name, f"'{branch_name}' is a reserved name")
    
    def branch_exists(self, db_name: str, branch_name: str) -> bool:
        """
        브랜치 존재 여부 확인
        
        Args:
            db_name: 데이터베이스 이름
            branch_name: 브랜치 이름
            
        Returns:
            존재 여부
        """
        # 캐시 확인
        if db_name in self._branch_cache:
            return branch_name in self._branch_cache[db_name]
        
        # 실제 확인
        try:
            branches = self.list_branches(db_name)
            return any(branch['name'] == branch_name for branch in branches)
        except Exception:
            return False
    
    def _get_branch_details(self, db_name: str, branch_name: str) -> Dict[str, Any]:
        """
        브랜치 세부 정보 조회
        
        Args:
            db_name: 데이터베이스 이름
            branch_name: 브랜치 이름
            
        Returns:
            브랜치 세부 정보
        """
        try:
            with self.connection_manager.get_connection(db_name, branch_name) as client:
                # 브랜치 정보 조회
                details = {
                    'last_commit': None,
                    'commit_count': 0,
                    'created_at': None,
                    'last_modified': None
                }
                
                # 추가 정보가 있다면 조회
                try:
                    # 커밋 히스토리 조회 (가능한 경우)
                    if hasattr(client, 'log'):
                        log = client.log(limit=1)
                        if log:
                            details['last_commit'] = log[0].get('id')
                            details['last_modified'] = log[0].get('timestamp')
                except Exception:
                    pass
                
                return details
                
        except Exception as e:
            logger.debug(f"Failed to get branch details for '{branch_name}': {e}")
            return {}
    
    def _clear_cache(self, db_name: str) -> None:
        """
        캐시 삭제
        
        Args:
            db_name: 데이터베이스 이름
        """
        if db_name in self._branch_cache:
            del self._branch_cache[db_name]
    
    def get_branch_info(self, db_name: str, branch_name: str) -> Optional[Dict[str, Any]]:
        """
        특정 브랜치 정보 조회
        
        Args:
            db_name: 데이터베이스 이름
            branch_name: 브랜치 이름
            
        Returns:
            브랜치 정보 또는 None
        """
        try:
            branches = self.list_branches(db_name)
            for branch in branches:
                if branch['name'] == branch_name:
                    return branch
            return None
        except Exception:
            return None
    
    def is_protected_branch(self, branch_name: str) -> bool:
        """
        보호된 브랜치 여부 확인
        
        Args:
            branch_name: 브랜치 이름
            
        Returns:
            보호 여부
        """
        return branch_name in self.PROTECTED_BRANCHES
    
    def check_conflicts(self, db_name: str, source: str, 
                       target: str) -> List[Dict[str, Any]]:
        """
        병합 충돌 검사 - BranchMerger에 위임
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            
        Returns:
            충돌 목록
            
        Raises:
            BranchNotFoundError: 브랜치를 찾을 수 없음
            DomainException: 충돌 검사 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 브랜치 존재 확인
        if not self.branch_exists(db_name, source):
            raise BranchNotFoundError(source, db_name)
        
        if not self.branch_exists(db_name, target):
            raise BranchNotFoundError(target, db_name)
        
        # 동일 브랜치 확인
        if source == target:
            raise DomainException(
                message=f"Cannot check conflicts between same branch '{source}'",
                code="SAME_BRANCH_CONFLICT_CHECK",
                details={"source": source, "target": target}
            )
        
        try:
            # BranchMerger 임시 생성하여 충돌 검사 위임 (VersionService, OntologyValidator 필요)
            from services.core.branch.merger import TerminusBranchMerger
            from services.core.version.service import TerminusVersionService
            from services.core.ontology.validator import TerminusOntologyValidator
            
            # VersionService 임시 생성
            version_service = TerminusVersionService(
                self.connection_manager,
                self,
                self.database_service
            )
            
            # OntologyValidator 임시 생성
            ontology_validator = TerminusOntologyValidator()
            
            merger = TerminusBranchMerger(
                self.connection_manager, 
                self, 
                version_service,
                ontology_validator
            )
            return merger.check_conflicts(db_name, source, target)
            
        except Exception as e:
            logger.error(f"Failed to check conflicts between '{source}' and '{target}': {e}")
            raise DomainException(
                message=f"Failed to check conflicts between '{source}' and '{target}'",
                code="CONFLICT_CHECK_ERROR",
                details={"source": source, "target": target, "db_name": db_name, "error": str(e)}
            )
    
    def merge_branches(self, db_name: str, source: str, target: str,
                      strategy: 'MergeStrategy', message: Optional[str] = None,
                      author: Optional[str] = None) -> Dict[str, Any]:
        """
        브랜치 병합 - BranchMerger에 위임
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            strategy: 병합 전략
            message: 병합 커밋 메시지
            author: 작성자
            
        Returns:
            병합 결과
            
        Raises:
            BranchNotFoundError: 브랜치를 찾을 수 없음
            BranchMergeConflictError: 병합 충돌 발생
            ProtectedBranchError: 보호된 브랜치 병합 시도
            DomainException: 병합 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 브랜치 존재 확인
        if not self.branch_exists(db_name, source):
            raise BranchNotFoundError(source, db_name)
        
        if not self.branch_exists(db_name, target):
            raise BranchNotFoundError(target, db_name)
        
        # 타겟 브랜치 보호 확인
        if self.is_protected_branch(target):
            raise ProtectedBranchError(target, "merge")
        
        # 동일 브랜치 확인
        if source == target:
            raise DomainException(
                message=f"Cannot merge branch '{source}' into itself",
                code="SAME_BRANCH_MERGE_ERROR",
                details={"source": source, "target": target}
            )
        
        try:
            # BranchMerger 임시 생성하여 병합 실행 (VersionService, OntologyValidator 필요)
            from services.core.branch.merger import TerminusBranchMerger
            from services.core.version.service import TerminusVersionService
            from services.core.ontology.validator import TerminusOntologyValidator
            
            # VersionService 임시 생성
            version_service = TerminusVersionService(
                self.connection_manager,
                self,
                self.database_service
            )
            
            # OntologyValidator 임시 생성
            ontology_validator = TerminusOntologyValidator()
            
            merger = TerminusBranchMerger(
                self.connection_manager, 
                self, 
                version_service,
                ontology_validator
            )
            
            # 전략 문자열 변환
            strategy_str = strategy.value if hasattr(strategy, 'value') else str(strategy)
            
            result = merger.merge(db_name, source, target, strategy_str, message, author)
            
            # 충돌이 있는 경우 처리
            if result.get("conflicts"):
                return {
                    "success": False,
                    "conflicts": result["conflicts"],
                    "source": source,
                    "target": target,
                    "strategy": strategy_str,
                    "message": "Merge conflicts detected"
                }
            
            return {
                "success": True,
                "source": source,
                "target": target,
                "strategy": strategy_str,
                "message": message or f"Merged '{source}' into '{target}'",
                "author": author,
                "merge_commit": result.get("merge_commit"),
                "timestamp": result.get("timestamp")
            }
            
        except Exception as e:
            logger.error(f"Failed to merge branches '{source}' into '{target}': {e}")
            raise DomainException(
                message=f"Failed to merge branches '{source}' into '{target}'",
                code="BRANCH_MERGE_ERROR",
                details={"source": source, "target": target, "db_name": db_name, "error": str(e)}
            )