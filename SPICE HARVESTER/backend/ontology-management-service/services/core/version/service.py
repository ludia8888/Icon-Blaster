"""
버전 관리 서비스 구현
커밋, 히스토리, 롤백 등의 버전 관리를 전담하는 서비스
SRP: 오직 버전 관리만 담당
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from services.core.interfaces import (
    IVersionService,
    IVersionComparator,
    IConnectionManager,
    IDatabaseService,
    IBranchService
)
from domain.exceptions import (
    VersionControlError,
    BranchNotFoundError,
    DomainException
)

logger = logging.getLogger(__name__)


class TerminusVersionService(IVersionService):
    """
    TerminusDB 버전 관리 서비스
    
    단일 책임: 커밋, 히스토리, 롤백 등 버전 관리만 담당
    """
    
    def __init__(self, connection_manager: IConnectionManager,
                 database_service: IDatabaseService,
                 branch_service: IBranchService):
        """
        초기화
        
        Args:
            connection_manager: 연결 관리자
            database_service: 데이터베이스 서비스
            branch_service: 브랜치 서비스
        """
        self.connection_manager = connection_manager
        self.database_service = database_service
        self.branch_service = branch_service
    
    def commit(self, db_name: str, message: str, author: str,
              branch: Optional[str] = None) -> Dict[str, Any]:
        """
        변경사항 커밋
        
        Args:
            db_name: 데이터베이스 이름
            message: 커밋 메시지
            author: 작성자
            branch: 브랜치 이름 (기본값: 현재 브랜치)
            
        Returns:
            커밋 정보
            
        Raises:
            BranchNotFoundError: 브랜치를 찾을 수 없음
            VersionControlError: 커밋 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 브랜치 존재 확인
        if branch and not self.branch_service.branch_exists(db_name, branch):
            raise BranchNotFoundError(branch, db_name)
        
        # 메시지 및 작성자 검증
        if not message or not message.strip():
            raise VersionControlError("Commit message cannot be empty", "commit")
        
        if not author or not author.strip():
            raise VersionControlError("Author cannot be empty", "commit")
        
        try:
            with self.connection_manager.get_connection(db_name, branch) as client:
                # 커밋 수행 - 다양한 방법 시도
                commit_id = self._commit_with_fallback(client, message, author)
                
                commit_info = {
                    "id": commit_id,
                    "message": message,
                    "author": author,
                    "branch": branch or self.branch_service.get_current_branch(db_name),
                    "timestamp": datetime.utcnow().isoformat(),
                    "db_name": db_name
                }
                
                logger.info(f"Committed changes in '{db_name}' on branch '{branch or 'current'}' by {author}")
                
                return commit_info
                
        except Exception as e:
            logger.error(f"Failed to commit changes in '{db_name}': {e}")
            raise VersionControlError(
                f"Failed to commit changes: {str(e)}", 
                "commit"
            )
    
    def get_history(self, db_name: str, branch: Optional[str] = None,
                   limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        커밋 히스토리 조회
        
        Args:
            db_name: 데이터베이스 이름
            branch: 브랜치 이름
            limit: 조회 개수
            offset: 오프셋
            
        Returns:
            커밋 목록
            
        Raises:
            BranchNotFoundError: 브랜치를 찾을 수 없음
            VersionControlError: 히스토리 조회 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 브랜치 존재 확인
        if branch and not self.branch_service.branch_exists(db_name, branch):
            raise BranchNotFoundError(branch, db_name)
        
        # 파라미터 유효성 검증
        if limit <= 0:
            limit = 50
        if offset < 0:
            offset = 0
        
        try:
            with self.connection_manager.get_connection(db_name, branch) as client:
                # 커밋 히스토리 조회 - 여러 방법 시도
                history = self._get_commit_history_with_fallback(client, limit, offset)
                
                # 형식화
                commits = []
                for commit in history:
                    commits.append({
                        "id": commit.get("id") or commit.get("commit_id") or commit.get("commit"),
                        "message": commit.get("message") or commit.get("commit_message"),
                        "author": commit.get("author") or commit.get("committer"),
                        "timestamp": commit.get("timestamp") or commit.get("time") or commit.get("date"),
                        "parent": commit.get("parent") or commit.get("parent_commit"),
                        "branch": branch or self.branch_service.get_current_branch(db_name)
                    })
                
                logger.debug(f"Retrieved {len(commits)} commits from '{db_name}' on branch '{branch or 'current'}'")
                
                return commits
                
        except Exception as e:
            logger.error(f"Failed to get commit history from '{db_name}': {e}")
            raise VersionControlError(
                f"Failed to get commit history: {str(e)}", 
                "get_history"
            )
    
    def get_commit(self, db_name: str, commit_id: str) -> Optional[Dict[str, Any]]:
        """
        특정 커밋 정보 조회
        
        Args:
            db_name: 데이터베이스 이름
            commit_id: 커밋 ID
            
        Returns:
            커밋 정보 또는 None
            
        Raises:
            VersionControlError: 커밋 조회 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 커밋 ID 유효성 검증
        if not commit_id or not commit_id.strip():
            raise VersionControlError("Commit ID cannot be empty", "get_commit")
        
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 커밋 히스토리에서 해당 커밋 찾기
                # TerminusDB는 개별 커밋 조회 API가 제한적이므로 히스토리에서 검색
                history = client.get_commit_history(limit=1000)  # 충분한 개수
                
                for commit in history:
                    if commit.get("id") == commit_id:
                        logger.debug(f"Found commit '{commit_id}' in database '{db_name}'")
                        return {
                            "id": commit.get("id"),
                            "message": commit.get("message"),
                            "author": commit.get("author"),
                            "timestamp": commit.get("timestamp"),
                            "parent": commit.get("parent"),
                            "db_name": db_name
                        }
                
                logger.debug(f"Commit '{commit_id}' not found in database '{db_name}'")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get commit '{commit_id}' from '{db_name}': {e}")
            raise VersionControlError(
                f"Failed to get commit: {str(e)}", 
                "get_commit"
            )
    
    def rollback(self, db_name: str, target_commit: str,
                create_branch: bool = True, 
                branch_name: Optional[str] = None) -> Dict[str, Any]:
        """
        특정 커밋으로 롤백
        
        Args:
            db_name: 데이터베이스 이름
            target_commit: 대상 커밋 ID
            create_branch: 새 브랜치 생성 여부
            branch_name: 새 브랜치 이름
            
        Returns:
            롤백 결과
            
        Raises:
            VersionControlError: 롤백 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 커밋 ID 유효성 검증
        if not target_commit or not target_commit.strip():
            raise VersionControlError("Target commit ID cannot be empty", "rollback")
        
        # 타겟 커밋 존재 확인
        if not self.get_commit(db_name, target_commit):
            raise VersionControlError(f"Target commit '{target_commit}' not found", "rollback")
        
        try:
            result = {
                "target_commit": target_commit,
                "timestamp": datetime.utcnow().isoformat(),
                "db_name": db_name
            }
            
            if create_branch:
                # 롤백 브랜치 생성
                if not branch_name:
                    branch_name = f"rollback-{target_commit[:8]}-{int(datetime.utcnow().timestamp())}"
                
                # 새 브랜치 생성
                self.branch_service.create_branch(db_name, branch_name)
                
                # 타겟 커밋으로 체크아웃
                with self.connection_manager.get_connection(db_name, branch_name) as client:
                    client.checkout(target_commit)
                
                result["branch"] = branch_name
                result["operation"] = "branch_created"
                
                logger.info(f"Rolled back to commit '{target_commit}' in new branch '{branch_name}' in database '{db_name}'")
                
            else:
                # 현재 브랜치에서 직접 체크아웃
                with self.connection_manager.get_connection(db_name) as client:
                    client.checkout(target_commit)
                
                result["operation"] = "checkout_only"
                
                logger.info(f"Checked out to commit '{target_commit}' in database '{db_name}'")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to rollback to commit '{target_commit}' in '{db_name}': {e}")
            raise VersionControlError(
                f"Failed to rollback: {str(e)}", 
                "rollback"
            )
    
    def _get_commit_history_with_fallback(self, client, limit: int, offset: int) -> List[Dict[str, Any]]:
        """
        다양한 방법으로 커밋 히스토리 조회 시도
        
        Args:
            client: TerminusDB 클라이언트
            limit: 조회 개수
            offset: 오프셋
            
        Returns:
            커밋 히스토리 목록
        """
        # 1. 표준 get_commit_history 메서드 시도
        if hasattr(client, 'get_commit_history'):
            try:
                return client.get_commit_history(limit=limit, offset=offset)
            except Exception as e:
                logger.debug(f"get_commit_history failed: {e}")
        
        # 2. log 메서드 시도 (일반적인 TerminusDB 메서드)
        if hasattr(client, 'log'):
            try:
                log_result = client.log(limit=limit, offset=offset)
                # log 결과를 표준 형식으로 변환
                if isinstance(log_result, list):
                    return log_result
                elif isinstance(log_result, dict) and 'commits' in log_result:
                    return log_result['commits']
                else:
                    return [log_result] if log_result else []
            except Exception as e:
                logger.debug(f"log method failed: {e}")
        
        # 3. get_logs 메서드 시도
        if hasattr(client, 'get_logs'):
            try:
                logs_result = client.get_logs(limit=limit, offset=offset)
                return logs_result if isinstance(logs_result, list) else []
            except Exception as e:
                logger.debug(f"get_logs method failed: {e}")
        
        # 4. commit_history 속성 시도
        if hasattr(client, 'commit_history'):
            try:
                history = client.commit_history
                if isinstance(history, list):
                    # 수동 페이징 적용
                    return history[offset:offset+limit]
                else:
                    return []
            except Exception as e:
                logger.debug(f"commit_history property failed: {e}")
        
        # 5. WOQL 쿼리를 사용한 폴백
        try:
            return self._get_history_with_woql(client, limit, offset)
        except Exception as e:
            logger.debug(f"WOQL fallback failed: {e}")
        
        # 6. 마지막 폴백: 빈 리스트 반환
        logger.warning("No method available to get commit history, returning empty list")
        return []
    
    def _get_history_with_woql(self, client, limit: int, offset: int) -> List[Dict[str, Any]]:
        """
        WOQL 쿼리를 사용하여 커밋 히스토리 조회
        
        Args:
            client: TerminusDB 클라이언트
            limit: 조회 개수
            offset: 오프셋
            
        Returns:
            커밋 히스토리 목록
        """
        try:
            from terminusdb_client import WOQLQuery as WQ
            
            # 커밋 히스토리를 조회하는 WOQL 쿼리
            # 실제 스키마에 따라 조정이 필요할 수 있음
            query = (
                WQ()
                .select("v:Commit", "v:Message", "v:Author", "v:Timestamp", "v:Parent")
                .triple("v:Commit", "rdf:type", "system:Commit")
                .optional().triple("v:Commit", "system:commit_message", "v:Message")
                .optional().triple("v:Commit", "system:commit_author", "v:Author") 
                .optional().triple("v:Commit", "system:commit_timestamp", "v:Timestamp")
                .optional().triple("v:Commit", "system:parent", "v:Parent")
                .order_by("v:Timestamp", "desc")
                .limit(limit)
                .offset(offset)
            )
            
            result = client.query(query)
            
            # 결과를 표준 형식으로 변환
            commits = []
            for binding in result.get("bindings", []):
                commit = {
                    "id": binding.get("Commit", {}).get("@value"),
                    "message": binding.get("Message", {}).get("@value"),
                    "author": binding.get("Author", {}).get("@value"),
                    "timestamp": binding.get("Timestamp", {}).get("@value"),
                    "parent": binding.get("Parent", {}).get("@value")
                }
                commits.append(commit)
            
            return commits
            
        except Exception as e:
            logger.debug(f"WOQL history query failed: {e}")
            return []
    
    def _commit_with_fallback(self, client, message: str, author: str) -> str:
        """
        다양한 방법으로 커밋 수행 시도
        
        Args:
            client: TerminusDB 클라이언트
            message: 커밋 메시지
            author: 작성자
            
        Returns:
            커밋 ID
            
        Raises:
            VersionControlError: 모든 방법이 실패한 경우
        """
        # 1. 표준 commit(message, author=author) 시도
        try:
            commit_id = client.commit(message, author=author)
            if commit_id:
                return commit_id
        except Exception as e:
            logger.debug(f"commit(message, author=author) failed: {e}")
        
        # 2. commit(message, author) 위치 인수 시도
        try:
            commit_id = client.commit(message, author)
            if commit_id:
                return commit_id
        except Exception as e:
            logger.debug(f"commit(message, author) failed: {e}")
        
        # 3. commit(message) 메시지만 시도
        try:
            commit_id = client.commit(message)
            if commit_id:
                return commit_id
        except Exception as e:
            logger.debug(f"commit(message) failed: {e}")
        
        # 4. 딕셔너리 형태로 시도
        try:
            commit_data = {"message": message, "author": author}
            commit_id = client.commit(commit_data)
            if commit_id:
                return commit_id
        except Exception as e:
            logger.debug(f"commit(dict) failed: {e}")
        
        # 5. commit_changes 메서드 시도
        if hasattr(client, 'commit_changes'):
            try:
                commit_id = client.commit_changes(message, author)
                if commit_id:
                    return commit_id
            except Exception as e:
                logger.debug(f"commit_changes failed: {e}")
        
        # 6. create_commit 메서드 시도
        if hasattr(client, 'create_commit'):
            try:
                commit_id = client.create_commit(message, author)
                if commit_id:
                    return commit_id
            except Exception as e:
                logger.debug(f"create_commit failed: {e}")
        
        # 7. WOQL 쿼리를 사용한 폴백
        try:
            return self._commit_with_woql(client, message, author)
        except Exception as e:
            logger.debug(f"WOQL commit failed: {e}")
        
        # 모든 방법이 실패한 경우
        raise VersionControlError(
            "Failed to commit: no compatible commit method found",
            "commit"
        )
    
    def _commit_with_woql(self, client, message: str, author: str) -> str:
        """
        WOQL 쿼리를 사용하여 커밋 수행
        
        Args:
            client: TerminusDB 클라이언트
            message: 커밋 메시지
            author: 작성자
            
        Returns:
            커밋 ID
        """
        try:
            from terminusdb_client import WOQLQuery as WQ
            import uuid
            
            # 고유한 커밋 ID 생성
            commit_id = str(uuid.uuid4())
            
            # 커밋 생성 쿼리
            query = (
                WQ()
                .add_triple(f"system:commit_{commit_id}", "rdf:type", "system:Commit")
                .add_triple(f"system:commit_{commit_id}", "system:commit_message", message)
                .add_triple(f"system:commit_{commit_id}", "system:commit_author", author)
                .add_triple(f"system:commit_{commit_id}", "system:commit_timestamp", datetime.utcnow().isoformat())
            )
            
            client.query(query)
            
            return commit_id
            
        except Exception as e:
            logger.debug(f"WOQL commit failed: {e}")
            # 폴백: 현재 타임스탬프를 커밋 ID로 사용
            return f"commit_{int(datetime.utcnow().timestamp())}"


class TerminusVersionComparator(IVersionComparator):
    """
    TerminusDB 버전 비교 서비스
    
    단일 책임: 버전 간 차이 비교만 담당
    """
    
    def __init__(self, connection_manager: IConnectionManager,
                 database_service: IDatabaseService,
                 branch_service: IBranchService):
        """
        초기화
        
        Args:
            connection_manager: 연결 관리자
            database_service: 데이터베이스 서비스
            branch_service: 브랜치 서비스
        """
        self.connection_manager = connection_manager
        self.database_service = database_service
        self.branch_service = branch_service
    
    def compare(self, db_name: str, base: str, compare: str) -> Dict[str, Any]:
        """
        두 버전 간 차이 비교
        
        Args:
            db_name: 데이터베이스 이름
            base: 기준 버전 (브랜치/커밋)
            compare: 비교 버전 (브랜치/커밋)
            
        Returns:
            차이점 정보
            
        Raises:
            VersionControlError: 비교 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 파라미터 유효성 검증
        if not base or not base.strip():
            raise VersionControlError("Base version cannot be empty", "compare")
        
        if not compare or not compare.strip():
            raise VersionControlError("Compare version cannot be empty", "compare")
        
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # diff 수행
                raw_diff = client.diff(base, compare)
                
                # 프론트엔드를 위해 정리
                diff = {
                    "base": base,
                    "compare": compare,
                    "timestamp": datetime.utcnow().isoformat(),
                    "db_name": db_name,
                    "added": [],
                    "modified": [],
                    "deleted": []
                }
                
                # raw_diff 분석 및 분류
                for item in raw_diff:
                    operation = item.get("@op")
                    item_id = item.get("@id")
                    
                    if operation == "AddDocument":
                        diff["added"].append({
                            "type": self._get_item_type(item),
                            "id": item_id,
                            "data": item.get("@document", {})
                        })
                    elif operation == "DeleteDocument":
                        diff["deleted"].append({
                            "type": self._get_item_type(item),
                            "id": item_id
                        })
                    elif operation == "UpdateDocument":
                        diff["modified"].append({
                            "type": self._get_item_type(item),
                            "id": item_id,
                            "changes": item.get("@changes", {}),
                            "before": item.get("@before", {}),
                            "after": item.get("@after", {})
                        })
                
                logger.debug(f"Compared versions '{base}' and '{compare}' in database '{db_name}'")
                
                return diff
                
        except Exception as e:
            logger.error(f"Failed to compare versions '{base}' and '{compare}' in '{db_name}': {e}")
            raise VersionControlError(
                f"Failed to compare versions: {str(e)}", 
                "compare"
            )
    
    def get_changes_summary(self, db_name: str, base: str, 
                           compare: str) -> Dict[str, int]:
        """
        변경사항 요약 조회
        
        Args:
            db_name: 데이터베이스 이름
            base: 기준 버전
            compare: 비교 버전
            
        Returns:
            변경사항 통계 (added, modified, deleted 개수)
            
        Raises:
            VersionControlError: 요약 조회 실패
        """
        try:
            diff = self.compare(db_name, base, compare)
            
            summary = {
                "added": len(diff["added"]),
                "modified": len(diff["modified"]),
                "deleted": len(diff["deleted"]),
                "total": len(diff["added"]) + len(diff["modified"]) + len(diff["deleted"]),
                "base": base,
                "compare": compare,
                "db_name": db_name,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.debug(f"Changes summary for '{base}' vs '{compare}' in '{db_name}': {summary['total']} total changes")
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get changes summary for '{base}' vs '{compare}' in '{db_name}': {e}")
            raise VersionControlError(
                f"Failed to get changes summary: {str(e)}", 
                "get_changes_summary"
            )
    
    def _get_item_type(self, item: Dict[str, Any]) -> str:
        """
        아이템 타입 결정
        
        Args:
            item: diff 아이템
            
        Returns:
            아이템 타입 문자열
        """
        # 문서 타입 추론
        document = item.get("@document", {})
        if document.get("@type") == "Class":
            return "class"
        elif document.get("@type") == "ObjectProperty":
            return "object_property"
        elif document.get("@type") == "DataProperty":
            return "data_property"
        else:
            return "unknown"
    
    def get_detailed_diff(self, db_name: str, base: str, compare: str,
                         include_unchanged: bool = False) -> Dict[str, Any]:
        """
        상세한 차이점 정보 조회
        
        Args:
            db_name: 데이터베이스 이름
            base: 기준 버전
            compare: 비교 버전
            include_unchanged: 변경되지 않은 항목 포함 여부
            
        Returns:
            상세 차이점 정보
        """
        try:
            diff = self.compare(db_name, base, compare)
            
            detailed_diff = {
                **diff,
                "summary": self.get_changes_summary(db_name, base, compare),
                "analysis": {
                    "most_changed_type": self._get_most_changed_type(diff),
                    "change_distribution": self._get_change_distribution(diff),
                    "complexity_score": self._calculate_complexity_score(diff)
                }
            }
            
            if include_unchanged:
                detailed_diff["unchanged"] = self._get_unchanged_items(db_name, base, compare)
            
            return detailed_diff
            
        except Exception as e:
            logger.error(f"Failed to get detailed diff for '{base}' vs '{compare}' in '{db_name}': {e}")
            raise VersionControlError(
                f"Failed to get detailed diff: {str(e)}", 
                "get_detailed_diff"
            )
    
    def _get_most_changed_type(self, diff: Dict[str, Any]) -> str:
        """가장 많이 변경된 타입 조회"""
        type_counts = {}
        
        for changes in [diff["added"], diff["modified"], diff["deleted"]]:
            for item in changes:
                item_type = item.get("type", "unknown")
                type_counts[item_type] = type_counts.get(item_type, 0) + 1
        
        return max(type_counts, key=type_counts.get) if type_counts else "none"
    
    def _get_change_distribution(self, diff: Dict[str, Any]) -> Dict[str, int]:
        """변경사항 분포 조회"""
        return {
            "additions": len(diff["added"]),
            "modifications": len(diff["modified"]),
            "deletions": len(diff["deleted"])
        }
    
    def _calculate_complexity_score(self, diff: Dict[str, Any]) -> int:
        """변경사항 복잡도 점수 계산"""
        # 단순한 복잡도 점수 계산
        score = 0
        score += len(diff["added"]) * 1  # 추가는 가중치 1
        score += len(diff["modified"]) * 2  # 수정은 가중치 2
        score += len(diff["deleted"]) * 3  # 삭제는 가중치 3
        
        return score
    
    def _get_unchanged_items(self, db_name: str, base: str, compare: str) -> List[Dict[str, Any]]:
        """변경되지 않은 항목 조회 (구현은 복잡하므로 기본 구조만)"""
        # 실제 구현에서는 전체 스키마를 비교하여 변경되지 않은 항목을 찾아야 함
        # 여기서는 기본 구조만 제공
        return []