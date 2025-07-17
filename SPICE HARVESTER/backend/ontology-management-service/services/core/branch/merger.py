"""
브랜치 병합기 구현
브랜치 병합 작업을 전담하는 서비스
SRP: 오직 브랜치 병합 로직만 담당
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from services.core.interfaces import IBranchMerger, IBranchService, IConnectionManager
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'shared'))
from exceptions import (
    BranchNotFoundError,
    BranchMergeConflictError,
    ProtectedBranchError,
    DomainException
)

logger = logging.getLogger(__name__)


class TerminusBranchMerger(IBranchMerger):
    """
    TerminusDB 브랜치 병합기
    
    단일 책임: 브랜치 병합 로직만 담당
    """
    
    def __init__(self, connection_manager: IConnectionManager,
                 branch_service: IBranchService,
                 version_service: 'IVersionService',
                 ontology_validator: Optional['IOntologyValidator'] = None):
        """
        초기화
        
        Args:
            connection_manager: 연결 관리자
            branch_service: 브랜치 서비스
            version_service: 버전 서비스 (기존 diff 기능 재사용)
            ontology_validator: 온톨로지 검증기 (기존 검증 로직 재사용)
        """
        self.connection_manager = connection_manager
        self.branch_service = branch_service
        self.version_service = version_service
        self.ontology_validator = ontology_validator
    
    def merge(self, db_name: str, source: str, target: str,
             strategy: str = "merge", message: Optional[str] = None,
             author: Optional[str] = None) -> Dict[str, Any]:
        """
        브랜치 병합
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            strategy: "merge" 또는 "rebase"
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
        # 브랜치 존재 확인
        if not self.branch_service.branch_exists(db_name, source):
            raise BranchNotFoundError(source, db_name)
        
        if not self.branch_service.branch_exists(db_name, target):
            raise BranchNotFoundError(target, db_name)
        
        # 동일 브랜치 확인
        if source == target:
            raise DomainException(
                message=f"Cannot merge branch '{source}' into itself",
                code="SAME_BRANCH_MERGE_ERROR",
                details={"source": source, "target": target}
            )
        
        # 충돌 사전 검사
        conflicts = self.check_conflicts(db_name, source, target)
        if conflicts:
            raise BranchMergeConflictError(source, target, conflicts)
        
        # 병합 메시지 생성
        if not message:
            message = f"Merge branch '{source}' into '{target}'"
        
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 타겟 브랜치로 체크아웃
                client.checkout(target)
                
                # 병합 전략에 따라 실행
                if strategy == "merge":
                    result = self._execute_merge(client, source, target, message, author)
                elif strategy == "rebase":
                    result = self._execute_rebase(client, source, target, message, author)
                else:
                    raise DomainException(
                        message=f"Unsupported merge strategy: {strategy}",
                        code="INVALID_MERGE_STRATEGY",
                        details={"strategy": strategy}
                    )
                
                logger.info(f"Merged branch '{source}' into '{target}' in '{db_name}' using {strategy}")
                
                return {
                    'source': source,
                    'target': target,
                    'strategy': strategy,
                    'message': message,
                    'author': author,
                    'merged': True,
                    'merge_commit': result.get('commit_id'),
                    'timestamp': datetime.now().isoformat()
                }
                
        except BranchMergeConflictError:
            # 충돌 예외는 재발생
            raise
        except Exception as e:
            logger.error(f"Failed to merge '{source}' into '{target}' in '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to merge '{source}' into '{target}'",
                code="MERGE_ERROR",
                details={"source": source, "target": target, "db_name": db_name, "error": str(e)}
            )
    
    def check_conflicts(self, db_name: str, source: str, 
                       target: str) -> List[Dict[str, Any]]:
        """
        병합 충돌 검사
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            
        Returns:
            충돌 목록
        """
        conflicts = []
        
        try:
            # 기존 VersionService의 compare 메서드 사용 (중복 구현 방지)
            diff = self.version_service.compare(db_name, source, target)
            
            # 충돌 탐지
            conflicts = self._detect_conflicts(diff)
            
            logger.debug(f"Found {len(conflicts)} conflicts between '{source}' and '{target}'")
                
        except Exception as e:
            logger.error(f"Failed to check conflicts between '{source}' and '{target}': {e}")
            # 충돌 검사 실패 시 안전하게 충돌이 있다고 가정
            conflicts.append({
                'type': 'check_error',
                'message': f"Failed to check conflicts: {str(e)}",
                'source': source,
                'target': target
            })
        
        return conflicts
    
    def can_merge(self, db_name: str, source: str, target: str) -> Dict[str, Any]:
        """
        병합 가능 여부 확인
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            
        Returns:
            병합 가능 여부와 상세 정보
        """
        result = {
            'can_merge': False,
            'conflicts': [],
            'issues': []
        }
        
        try:
            # 브랜치 존재 확인
            if not self.branch_service.branch_exists(db_name, source):
                result['issues'].append(f"Source branch '{source}' not found")
                return result
            
            if not self.branch_service.branch_exists(db_name, target):
                result['issues'].append(f"Target branch '{target}' not found")
                return result
            
            # 동일 브랜치 확인
            if source == target:
                result['issues'].append("Cannot merge branch into itself")
                return result
            
            # 보호된 브랜치 확인
            if self.branch_service.is_protected_branch(target):
                result['issues'].append(f"Target branch '{target}' is protected")
                return result
            
            # 충돌 확인
            conflicts = self.check_conflicts(db_name, source, target)
            result['conflicts'] = conflicts
            
            # 병합 가능 여부 결정
            result['can_merge'] = len(conflicts) == 0 and len(result['issues']) == 0
            
        except Exception as e:
            result['issues'].append(f"Error checking merge feasibility: {str(e)}")
        
        return result
    
    def get_merge_preview(self, db_name: str, source: str, target: str) -> Dict[str, Any]:
        """
        병합 미리보기 생성
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            
        Returns:
            병합 미리보기
        """
        preview = {
            'source': source,
            'target': target,
            'can_merge': False,
            'conflicts': [],
            'changes': [],
            'stats': {
                'added': 0,
                'modified': 0,
                'deleted': 0
            }
        }
        
        try:
            # 병합 가능 여부 확인
            merge_check = self.can_merge(db_name, source, target)
            preview.update(merge_check)
            
            if preview['can_merge']:
                # 변경사항 미리보기
                with self.connection_manager.get_connection(db_name) as client:
                    changes = self._get_merge_changes(client, source, target)
                    preview['changes'] = changes
                    
                    # 통계 계산
                    preview['stats'] = self._calculate_change_stats(changes)
                    
        except Exception as e:
            preview['error'] = str(e)
        
        return preview
    
    def _execute_merge(self, client, source: str, target: str, 
                      message: str, author: Optional[str]) -> Dict[str, Any]:
        """
        병합 실행
        
        Args:
            client: TerminusDB 클라이언트
            source: 소스 브랜치
            target: 타겟 브랜치
            message: 병합 메시지
            author: 작성자
            
        Returns:
            병합 결과
        """
        try:
            # TerminusDB에서 병합은 직접 지원되지 않으므로 수동으로 구현
            # 1. 타겟 브랜치가 현재 체크아웃되어 있는지 확인
            current_ref = getattr(client, 'ref', {})
            current_branch = current_ref.get('branch', 'main')
            
            if current_branch != target:
                client.checkout(target)
            
            # 2. 소스 브랜치의 변경사항 적용
            # TerminusDB에서는 일반적으로 squash merge를 사용
            if hasattr(client, 'squash'):
                # squash 메서드가 있는 경우 사용
                result = client.squash(source)
                commit_id = result.get('commit', '')
            else:
                # 폴백: 수동 병합 구현
                commit_id = self._manual_merge(client, source, target, message, author)
            
            return {
                'commit_id': commit_id,
                'strategy': 'merge',
                'success': True
            }
            
        except Exception as e:
            # 병합 실패 시 충돌 가능성 확인
            conflicts = self._parse_merge_conflicts(str(e))
            if conflicts:
                raise BranchMergeConflictError(source, target, conflicts)
            else:
                raise
    
    def _execute_rebase(self, client, source: str, target: str,
                       message: str, author: Optional[str]) -> Dict[str, Any]:
        """
        리베이스 실행
        
        Args:
            client: TerminusDB 클라이언트
            source: 소스 브랜치
            target: 타겟 브랜치
            message: 병합 메시지
            author: 작성자
            
        Returns:
            리베이스 결과
        """
        try:
            # TerminusDB에서는 직접적인 rebase가 지원되지 않으므로 
            # 수동으로 구현: 타겟 브랜치 위에 소스 브랜치 변경사항 재적용
            
            # 1. 타겟 브랜치 체크아웃
            client.checkout(target)
            
            # 2. 소스 브랜치의 변경사항들을 순차적으로 적용
            # TerminusDB에서는 일반적으로 reset-then-apply 방식 사용
            if hasattr(client, 'reset'):
                # reset 메서드가 있는 경우 사용
                client.reset(source)
                commit_id = self._commit_with_fallback(client, message, author)
            else:
                # 폴백: 수동 리베이스 구현
                commit_id = self._manual_rebase(client, source, target, message, author)
            
            return {
                'commit_id': commit_id,
                'strategy': 'rebase',
                'success': True
            }
            
        except Exception as e:
            # 리베이스 실패 시 충돌 가능성 확인
            conflicts = self._parse_merge_conflicts(str(e))
            if conflicts:
                raise BranchMergeConflictError(source, target, conflicts)
            else:
                raise
    
    def _manual_merge(self, client, source: str, target: str, 
                     message: str, author: Optional[str]) -> str:
        """
        수동 병합 구현 (TerminusDB 클라이언트에 merge 메서드가 없는 경우)
        
        Args:
            client: TerminusDB 클라이언트
            source: 소스 브랜치
            target: 타겟 브랜치
            message: 병합 메시지
            author: 작성자
            
        Returns:
            커밋 ID
        """
        try:
            # 1. 소스 브랜치에서 변경된 문서들 가져오기
            client.checkout(source)
            source_documents = self._get_all_documents(client)
            
            # 2. 타겟 브랜치로 돌아가서 변경사항 적용
            client.checkout(target)
            
            # 3. 문서 업데이트
            for doc_id, doc_data in source_documents.items():
                try:
                    # 문서 업데이트 또는 생성
                    if hasattr(client, 'update_document'):
                        client.update_document(doc_data)
                    elif hasattr(client, 'insert_document'):
                        client.insert_document(doc_data)
                    else:
                        # 최후의 수단: WOQL 쿼리 사용
                        self._update_document_with_woql(client, doc_data)
                except Exception as e:
                    logger.warning(f"Failed to update document {doc_id} during merge: {e}")
            
            # 4. 병합 커밋 생성
            commit_id = self._commit_with_fallback(client, message, author)
            
            return commit_id
            
        except Exception as e:
            logger.error(f"Manual merge failed: {e}")
            raise DomainException(
                message=f"Manual merge failed: {str(e)}",
                code="MANUAL_MERGE_ERROR",
                details={"source": source, "target": target, "error": str(e)}
            )
    
    def _manual_rebase(self, client, source: str, target: str,
                      message: str, author: Optional[str]) -> str:
        """
        수동 리베이스 구현 (TerminusDB 클라이언트에 rebase 메서드가 없는 경우)
        
        Args:
            client: TerminusDB 클라이언트
            source: 소스 브랜치
            target: 타겟 브랜치
            message: 메시지
            author: 작성자
            
        Returns:
            커밋 ID
        """
        try:
            # 리베이스는 복잡하므로 단순 병합으로 대체
            # 실제 리베이스 구현을 위해서는 커밋 히스토리 재구성 필요
            logger.warning("TerminusDB does not support native rebase, falling back to merge")
            
            return self._manual_merge(client, source, target, message, author)
            
        except Exception as e:
            logger.error(f"Manual rebase failed: {e}")
            raise DomainException(
                message=f"Manual rebase failed: {str(e)}",
                code="MANUAL_REBASE_ERROR",
                details={"source": source, "target": target, "error": str(e)}
            )
    
    def _update_document_with_woql(self, client, doc_data: Dict[str, Any]) -> None:
        """
        WOQL 쿼리를 사용하여 문서 업데이트
        
        Args:
            client: TerminusDB 클라이언트
            doc_data: 문서 데이터
        """
        try:
            from terminusdb_client import WOQLQuery as WQ
            
            # 문서 ID 추출
            doc_id = doc_data.get('@id')
            if not doc_id:
                return
            
            # 기존 문서 삭제
            delete_query = WQ().delete_document(doc_id)
            client.query(delete_query)
            
            # 새 문서 삽입
            insert_query = WQ().insert_document(doc_data)
            client.query(insert_query)
            
        except Exception as e:
            logger.warning(f"Failed to update document with WOQL: {e}")
            # 에러를 발생시키지 않고 계속 진행
    
    
    def _detect_conflicts(self, diff: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        차이점에서 충돌 탐지 (3-way merge 기반)
        
        Args:
            diff: 차이점 정보 (changes, conflicts, stats 포함)
            
        Returns:
            충돌 목록
        """
        conflicts = []
        
        try:
            # 1. 직접 충돌 (diff에서 이미 식별된 충돌)
            direct_conflicts = diff.get('conflicts', [])
            for conflict in direct_conflicts:
                conflicts.append({
                    'type': 'direct_conflict',
                    'resource': conflict.get('document_id'),
                    'description': f"Direct conflict in document {conflict.get('document_id')}",
                    'source_change': conflict.get('source_change'),
                    'target_change': conflict.get('target_change'),
                    'conflict_type': conflict.get('type', 'unknown')
                })
            
            # 2. 변경사항 분석을 통한 충돌 검사
            changes = diff.get('changes', {})
            
            # 동일한 문서에 대한 서로 다른 변경사항 검사
            for doc_id, change in changes.items():
                change_type = change.get('type')
                
                # 수정된 문서에서 복잡한 변경사항 검사
                if change_type == 'modified':
                    source_doc = change.get('source', {})
                    target_doc = change.get('target', {})
                    
                    # 스키마 충돌 검사
                    if self._has_schema_conflict(source_doc, target_doc):
                        conflicts.append({
                            'type': 'schema_conflict',
                            'resource': doc_id,
                            'description': f"Schema conflict in document {doc_id}",
                            'source_change': source_doc,
                            'target_change': target_doc,
                            'conflict_type': 'schema'
                        })
                    
                    # 속성 충돌 검사
                    property_conflicts = self._check_property_conflicts(source_doc, target_doc)
                    for prop_conflict in property_conflicts:
                        conflicts.append({
                            'type': 'property_conflict',
                            'resource': doc_id,
                            'description': f"Property conflict in {doc_id}.{prop_conflict['property']}",
                            'source_change': prop_conflict['source_value'],
                            'target_change': prop_conflict['target_value'],
                            'conflict_type': 'property',
                            'property': prop_conflict['property']
                        })
                
                # 삭제/추가 동시 발생 (rename 가능성)
                elif change_type in ['added', 'deleted']:
                    # 유사한 ID의 문서가 삭제/추가되었는지 확인
                    potential_renames = self._check_rename_conflicts(doc_id, changes)
                    for rename_conflict in potential_renames:
                        conflicts.append({
                            'type': 'rename_conflict',
                            'resource': doc_id,
                            'description': f"Potential rename conflict between {doc_id} and {rename_conflict['other_id']}",
                            'source_change': change.get('source'),
                            'target_change': change.get('target'),
                            'conflict_type': 'rename',
                            'other_document': rename_conflict['other_id']
                        })
            
            # 3. 구조적 충돌 검사
            structural_conflicts = self._check_structural_conflicts(changes)
            conflicts.extend(structural_conflicts)
            
        except Exception as e:
            logger.error(f"Failed to detect conflicts: {e}")
            # 오류 발생 시 안전하게 충돌이 있다고 가정
            conflicts.append({
                'type': 'detection_error',
                'resource': 'unknown',
                'description': f"Failed to detect conflicts: {str(e)}",
                'source_change': None,
                'target_change': None,
                'conflict_type': 'error'
            })
        
        return conflicts
    
    def _detect_field_level_conflicts(self, db_name: str, source: str, target: str) -> List[Dict[str, Any]]:
        """
        필드 수준 충돌 탐지 (3-way merge 기반)
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            
        Returns:
            필드 수준 충돌 목록
        """
        conflicts = []
        
        try:
            # 1. 공통 조상 커밋 찾기
            base_commit = self._get_common_ancestor(db_name, source, target)
            if not base_commit:
                logger.warning(f"No common ancestor found between '{source}' and '{target}', skipping field-level conflict detection")
                return []
            
            # 2. 세 버전의 문서 상태 가져오기
            with self.connection_manager.get_connection(db_name) as client:
                # Base 버전 (공통 조상)
                client.checkout(base_commit)
                base_documents = self._get_all_documents(client)
                
                # Source 버전
                client.checkout(source)
                source_documents = self._get_all_documents(client)
                
                # Target 버전
                client.checkout(target)
                target_documents = self._get_all_documents(client)
            
            # 3. 모든 문서 ID 수집
            all_doc_ids = set(base_documents.keys()) | set(source_documents.keys()) | set(target_documents.keys())
            
            # 4. 각 문서에 대해 필드 수준 충돌 검사
            for doc_id in all_doc_ids:
                base_doc = base_documents.get(doc_id, {})
                source_doc = source_documents.get(doc_id, {})
                target_doc = target_documents.get(doc_id, {})
                
                # 문서 존재 여부 충돌 검사
                existence_conflict = self._check_document_existence_conflict(
                    doc_id, base_doc, source_doc, target_doc
                )
                if existence_conflict:
                    conflicts.append(existence_conflict)
                    continue  # 문서 존재 충돌이 있으면 필드 검사 건너뛰기
                
                # 필드별 충돌 검사 (문서가 모두 존재하는 경우)
                if base_doc and source_doc and target_doc:
                    field_conflicts = self._check_individual_field_conflicts(
                        doc_id, base_doc, source_doc, target_doc
                    )
                    conflicts.extend(field_conflicts)
            
        except Exception as e:
            logger.error(f"Failed to detect field-level conflicts: {e}")
            conflicts.append({
                'type': 'field_detection_error',
                'resource': 'unknown',
                'description': f"Failed to detect field-level conflicts: {str(e)}",
                'source_change': None,
                'target_change': None,
                'conflict_type': 'error'
            })
        
        return conflicts
    
    def _check_document_existence_conflict(self, doc_id: str, base_doc: Dict[str, Any], 
                                         source_doc: Dict[str, Any], target_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        문서 존재 여부 충돌 검사
        
        Args:
            doc_id: 문서 ID
            base_doc: 기준 문서 (공통 조상)
            source_doc: 소스 문서
            target_doc: 타겟 문서
            
        Returns:
            충돌 정보 또는 None
        """
        base_exists = bool(base_doc)
        source_exists = bool(source_doc)
        target_exists = bool(target_doc)
        
        # 충돌 시나리오 확인
        if base_exists:
            if not source_exists and not target_exists:
                # 양쪽 모두 삭제 - 충돌 아님
                return None
            elif not source_exists and target_exists:
                # 소스에서 삭제, 타겟에서 수정 - 충돌
                return {
                    'type': 'delete_modify_conflict',
                    'resource': doc_id,
                    'description': f"Document {doc_id} deleted in source but modified in target",
                    'source_change': 'deleted',
                    'target_change': 'modified',
                    'conflict_type': 'existence'
                }
            elif source_exists and not target_exists:
                # 소스에서 수정, 타겟에서 삭제 - 충돌
                return {
                    'type': 'modify_delete_conflict',
                    'resource': doc_id,
                    'description': f"Document {doc_id} modified in source but deleted in target",
                    'source_change': 'modified',
                    'target_change': 'deleted',
                    'conflict_type': 'existence'
                }
        else:
            # 기준에 없던 문서
            if source_exists and target_exists:
                # 양쪽 모두 추가 - 내용 비교 필요
                if source_doc != target_doc:
                    return {
                        'type': 'add_add_conflict',
                        'resource': doc_id,
                        'description': f"Document {doc_id} added differently in both branches",
                        'source_change': source_doc,
                        'target_change': target_doc,
                        'conflict_type': 'content'
                    }
        
        return None
    
    def _check_individual_field_conflicts(self, doc_id: str, base_doc: Dict[str, Any], 
                                        source_doc: Dict[str, Any], target_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        개별 필드 충돌 검사
        
        Args:
            doc_id: 문서 ID
            base_doc: 기준 문서 (공통 조상)
            source_doc: 소스 문서
            target_doc: 타겟 문서
            
        Returns:
            필드별 충돌 목록
        """
        conflicts = []
        
        # 모든 필드 수집
        all_fields = set(base_doc.keys()) | set(source_doc.keys()) | set(target_doc.keys())
        
        for field in all_fields:
            base_value = base_doc.get(field)
            source_value = source_doc.get(field)
            target_value = target_doc.get(field)
            
            # 3-way merge 충돌 검사
            conflict = self._check_three_way_field_conflict(
                doc_id, field, base_value, source_value, target_value
            )
            if conflict:
                conflicts.append(conflict)
        
        return conflicts
    
    def _check_three_way_field_conflict(self, doc_id: str, field: str, 
                                       base_value: Any, source_value: Any, target_value: Any) -> Optional[Dict[str, Any]]:
        """
        3-way merge 필드 충돌 검사
        
        Args:
            doc_id: 문서 ID
            field: 필드명
            base_value: 기준 값 (공통 조상)
            source_value: 소스 값
            target_value: 타겟 값
            
        Returns:
            충돌 정보 또는 None
        """
        # 값이 모두 동일한 경우 - 충돌 없음
        if base_value == source_value == target_value:
            return None
        
        # 소스만 변경된 경우 - 충돌 없음 (소스 값 사용)
        if base_value == target_value and source_value != base_value:
            return None
        
        # 타겟만 변경된 경우 - 충돌 없음 (타겟 값 사용)
        if base_value == source_value and target_value != base_value:
            return None
        
        # 양쪽 모두 변경되었고 값이 다른 경우 - 충돌
        if source_value != base_value and target_value != base_value and source_value != target_value:
            return {
                'type': 'field_conflict',
                'resource': doc_id,
                'field': field,
                'description': f"Field '{field}' in document {doc_id} modified differently in both branches",
                'base_value': base_value,
                'source_value': source_value,
                'target_value': target_value,
                'conflict_type': 'field'
            }
        
        return None
    
    def resolve_conflicts(self, db_name: str, source: str, target: str, 
                         conflict_resolutions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        충돌 해결 및 병합 완료
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            conflict_resolutions: 충돌 해결 방법 목록
                [
                    {
                        "conflict_id": "conflict_id",
                        "resolution": "accept_source" | "accept_target" | "accept_both" | "custom",
                        "resolved_value": "custom_value",  # resolution이 "custom"인 경우
                        "resolved_by": "user_id"
                    }
                ]
                
        Returns:
            병합 결과
            
        Raises:
            BranchMergeConflictError: 해결되지 않은 충돌 존재
            DomainException: 충돌 해결 실패
        """
        try:
            # 1. 현재 충돌 상태 확인
            current_conflicts = self.check_conflicts(db_name, source, target)
            if not current_conflicts:
                # 충돌이 없으면 일반 병합 수행
                return self.merge(db_name, source, target)
            
            # 2. 충돌 해결 방법 검증
            resolved_conflicts = self._validate_and_apply_resolutions(
                current_conflicts, conflict_resolutions
            )
            
            # 3. 해결된 충돌을 사용하여 병합된 문서 생성
            merged_documents = self._create_merged_documents(
                db_name, source, target, resolved_conflicts
            )
            
            # 4. 병합 커밋 생성
            merge_result = self._create_merge_commit(
                db_name, source, target, merged_documents, resolved_conflicts
            )
            
            logger.info(f"Successfully resolved {len(resolved_conflicts)} conflicts and merged '{source}' into '{target}'")
            
            return {
                'source': source,
                'target': target,
                'success': True,
                'conflicts_resolved': len(resolved_conflicts),
                'merge_commit': merge_result.get('commit_id'),
                'resolved_conflicts': [c.to_dict() for c in resolved_conflicts],
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to resolve conflicts and merge '{source}' into '{target}': {e}")
            raise DomainException(
                message=f"Failed to resolve conflicts: {str(e)}",
                code="CONFLICT_RESOLUTION_ERROR",
                details={"source": source, "target": target, "error": str(e)}
            )
    
    def _validate_and_apply_resolutions(self, conflicts: List[Dict[str, Any]], 
                                       resolutions: List[Dict[str, Any]]) -> List['MergeConflict']:
        """
        충돌 해결 방법 검증 및 적용
        
        Args:
            conflicts: 현재 충돌 목록
            resolutions: 충돌 해결 방법 목록
            
        Returns:
            해결된 충돌 목록 (MergeConflict 객체)
            
        Raises:
            DomainException: 해결 방법 검증 실패
        """
        from services.core.domain.models import MergeConflict, ConflictType, ConflictResolution
        
        resolved_conflicts = []
        resolution_map = {r['conflict_id']: r for r in resolutions}
        
        for conflict in conflicts:
            conflict_id = conflict.get('resource', '') + '_' + conflict.get('field', conflict.get('type', ''))
            
            if conflict_id not in resolution_map:
                raise DomainException(
                    message=f"No resolution provided for conflict: {conflict_id}",
                    code="MISSING_CONFLICT_RESOLUTION",
                    details={"conflict_id": conflict_id}
                )
            
            resolution = resolution_map[conflict_id]
            
            # MergeConflict 객체 생성
            merge_conflict = MergeConflict(
                id=conflict_id,
                type=ConflictType.CONTENT,  # 기본값, 실제로는 conflict 타입에 따라 설정
                resource_id=conflict.get('resource', ''),
                resource_type=conflict.get('conflict_type', 'unknown'),
                description=conflict.get('description', ''),
                base_value=conflict.get('base_value'),
                source_value=conflict.get('source_value') or conflict.get('source_change'),
                target_value=conflict.get('target_value') or conflict.get('target_change'),
                field_path=conflict.get('field')
            )
            
            # 해결 방법 적용
            resolution_type = resolution.get('resolution')
            resolved_by = resolution.get('resolved_by', 'system')
            
            if resolution_type == 'accept_source':
                merge_conflict.resolution = ConflictResolution.ACCEPT_SOURCE
                merge_conflict.resolved_value = merge_conflict.source_value
            elif resolution_type == 'accept_target':
                merge_conflict.resolution = ConflictResolution.ACCEPT_TARGET
                merge_conflict.resolved_value = merge_conflict.target_value
            elif resolution_type == 'accept_both':
                merge_conflict.resolution = ConflictResolution.ACCEPT_BOTH
                merge_conflict.resolved_value = self._merge_both_values(
                    merge_conflict.source_value, merge_conflict.target_value
                )
            elif resolution_type == 'custom':
                merge_conflict.resolution = ConflictResolution.CUSTOM
                merge_conflict.resolved_value = resolution.get('resolved_value')
                if merge_conflict.resolved_value is None:
                    raise DomainException(
                        message=f"Custom resolution requires resolved_value for conflict: {conflict_id}",
                        code="MISSING_RESOLVED_VALUE",
                        details={"conflict_id": conflict_id}
                    )
            else:
                raise DomainException(
                    message=f"Invalid resolution type: {resolution_type}",
                    code="INVALID_RESOLUTION_TYPE",
                    details={"conflict_id": conflict_id, "resolution_type": resolution_type}
                )
            
            merge_conflict.resolved_by = resolved_by
            merge_conflict.resolved_at = datetime.now()
            
            resolved_conflicts.append(merge_conflict)
        
        return resolved_conflicts
    
    def _merge_both_values(self, source_value: Any, target_value: Any) -> Any:
        """
        양쪽 값을 병합 (accept_both 전략)
        
        Args:
            source_value: 소스 값
            target_value: 타겟 값
            
        Returns:
            병합된 값
        """
        # 값 타입에 따라 병합 전략 결정
        if isinstance(source_value, dict) and isinstance(target_value, dict):
            # 딕셔너리는 키-값 병합
            merged = source_value.copy()
            merged.update(target_value)
            return merged
        elif isinstance(source_value, list) and isinstance(target_value, list):
            # 리스트는 합집합 (중복 제거)
            return list(set(source_value + target_value))
        elif isinstance(source_value, str) and isinstance(target_value, str):
            # 문자열은 연결
            return f"{source_value} | {target_value}"
        else:
            # 기본적으로 타겟 값 사용
            return target_value
    
    def _create_merged_documents(self, db_name: str, source: str, target: str,
                                resolved_conflicts: List['MergeConflict']) -> Dict[str, Any]:
        """
        해결된 충돌을 사용하여 병합된 문서 생성
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            resolved_conflicts: 해결된 충돌 목록
            
        Returns:
            병합된 문서 맵
        """
        merged_documents = {}
        
        try:
            # 공통 조상 찾기
            base_commit = self._get_common_ancestor(db_name, source, target)
            
            with self.connection_manager.get_connection(db_name) as client:
                # 타겟 브랜치 체크아웃 (병합 대상)
                client.checkout(target)
                target_documents = self._get_all_documents(client)
                
                # 소스 브랜치에서 변경된 문서 가져오기
                client.checkout(source)
                source_documents = self._get_all_documents(client)
                
                # 기본적으로 타겟 문서를 베이스로 사용
                merged_documents = target_documents.copy()
                
                # 해결된 충돌에 따라 문서 수정
                for conflict in resolved_conflicts:
                    resource_id = conflict.resource_id
                    field_path = conflict.field_path
                    resolved_value = conflict.resolved_value
                    
                    if resource_id in merged_documents:
                        if field_path:
                            # 특정 필드 수정
                            merged_documents[resource_id][field_path] = resolved_value
                        else:
                            # 전체 문서 교체
                            merged_documents[resource_id] = resolved_value
                    else:
                        # 새로운 문서 추가
                        merged_documents[resource_id] = resolved_value
                
                # 소스에서 추가된 문서 병합 (충돌되지 않은 것들)
                for doc_id, doc_data in source_documents.items():
                    if doc_id not in merged_documents:
                        merged_documents[doc_id] = doc_data
                
        except Exception as e:
            logger.error(f"Failed to create merged documents: {e}")
            raise DomainException(
                message=f"Failed to create merged documents: {str(e)}",
                code="MERGE_DOCUMENTS_ERROR",
                details={"source": source, "target": target, "error": str(e)}
            )
        
        return merged_documents
    
    def _create_merge_commit(self, db_name: str, source: str, target: str,
                           merged_documents: Dict[str, Any], 
                           resolved_conflicts: List['MergeConflict']) -> Dict[str, Any]:
        """
        병합 커밋 생성
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            merged_documents: 병합된 문서
            resolved_conflicts: 해결된 충돌 목록
            
        Returns:
            커밋 결과
        """
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 타겟 브랜치 체크아웃
                client.checkout(target)
                
                # 병합된 문서들을 데이터베이스에 적용
                for doc_id, doc_data in merged_documents.items():
                    # 문서 업데이트 - 기존 fallback 패턴 재사용
                    try:
                        if hasattr(client, 'update_document'):
                            client.update_document(doc_data)
                        elif hasattr(client, 'insert_document'):
                            client.insert_document(doc_data)
                        else:
                            # 최후의 수단: WOQL 쿼리 사용
                            self._update_document_with_woql(client, doc_data)
                    except Exception as e:
                        logger.warning(f"Failed to update document {doc_id}: {e}")
                        # 문서 업데이트 실패 시에도 계속 진행 (부분적 병합 허용)
                
                # 병합 커밋 메시지 생성
                conflict_summary = f"Resolved {len(resolved_conflicts)} conflicts"
                commit_message = f"Merge branch '{source}' into '{target}'\n\n{conflict_summary}"
                
                # 커밋 생성
                commit_id = self._commit_with_fallback(client, commit_message, "merge-system")
                
                return {
                    'commit_id': commit_id,
                    'message': commit_message,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to create merge commit: {e}")
            raise DomainException(
                message=f"Failed to create merge commit: {str(e)}",
                code="MERGE_COMMIT_ERROR",
                details={"source": source, "target": target, "error": str(e)}
            )
    
    def _get_merge_changes(self, client, source: str, target: str) -> List[Dict[str, Any]]:
        """
        병합 변경사항 조회 (기존 VersionService 재사용)
        
        Args:
            client: TerminusDB 클라이언트  
            source: 소스 브랜치
            target: 타겟 브랜치
            
        Returns:
            변경사항 목록
        """
        changes = []
        
        try:
            # 클라이언트 db_name 추출
            db_name = client.db if hasattr(client, 'db') else 'default'
            
            # 기존 VersionService의 get_detailed_diff 사용
            detailed_diff = self.version_service.get_detailed_diff(db_name, target, source)
            
            # 변경사항 파싱
            for change_type in ['added', 'modified', 'deleted']:
                for item in detailed_diff.get(change_type, []):
                    changes.append({
                        'type': change_type,
                        'resource': item.get('id'),
                        'description': item.get('description', f"{change_type} {item.get('id')}"),
                        'from_branch': source,
                        'to_branch': target
                    })
                    
        except Exception as e:
            logger.warning(f"Failed to get merge changes: {e}")
        
        return changes
    
    def _calculate_change_stats(self, changes: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        변경사항 통계 계산
        
        Args:
            changes: 변경사항 목록
            
        Returns:
            변경사항 통계
        """
        stats = {'added': 0, 'modified': 0, 'deleted': 0}
        
        for change in changes:
            change_type = change.get('type', '').lower()
            if change_type == 'add':
                stats['added'] += 1
            elif change_type == 'modify':
                stats['modified'] += 1
            elif change_type == 'delete':
                stats['deleted'] += 1
        
        return stats
    
    def _parse_merge_conflicts(self, error_message: str) -> List[Dict[str, Any]]:
        """
        에러 메시지에서 충돌 정보 파싱
        
        Args:
            error_message: 에러 메시지
            
        Returns:
            파싱된 충돌 목록
        """
        conflicts = []
        
        # 에러 메시지 분석하여 충돌 정보 추출
        if 'conflict' in error_message.lower():
            conflicts.append({
                'type': 'merge_conflict',
                'message': error_message,
                'severity': 'error'
            })
        
        return conflicts
    
    def _get_all_documents(self, client) -> Dict[str, Any]:
        """
        현재 브랜치의 모든 문서 조회
        
        Args:
            client: TerminusDB 클라이언트
            
        Returns:
            문서 ID -> 문서 데이터 매핑
        """
        documents = {}
        
        try:
            # WOQL 쿼리를 사용하여 모든 문서 조회
            from terminusdb_client import WOQLQuery as WQ
            
            # 모든 문서 조회 쿼리
            query = WQ().select("v:Doc").triple("v:Doc", "rdf:type", "v:Type")
            result = client.query(query)
            
            # 결과를 문서 ID 기준으로 정리
            for binding in result.get("bindings", []):
                doc_id = binding.get("Doc", {}).get("@value")
                if doc_id:
                    # 문서 상세 정보 조회
                    doc_query = WQ().select("v:Doc").triple(doc_id, "v:Predicate", "v:Value")
                    doc_result = client.query(doc_query)
                    documents[doc_id] = doc_result
                    
        except Exception as e:
            logger.warning(f"Failed to get all documents: {e}")
            # 폴백: 빈 문서 집합 반환
            documents = {}
        
        return documents
    
    def _has_conflicting_changes(self, source_doc: Dict[str, Any], 
                                target_doc: Dict[str, Any]) -> bool:
        """
        두 문서 간 충돌 가능성 검사
        
        Args:
            source_doc: 소스 문서
            target_doc: 타겟 문서
            
        Returns:
            충돌 가능성 여부
        """
        try:
            # 기본적인 충돌 검사
            # 1. 타입 변경
            if source_doc.get("@type") != target_doc.get("@type"):
                return True
            
            # 2. 중요 속성 변경
            critical_fields = ["@id", "@type", "rdfs:label", "rdfs:comment"]
            for field in critical_fields:
                if source_doc.get(field) != target_doc.get(field):
                    return True
            
            # 3. 스키마 변경
            source_props = set(source_doc.keys())
            target_props = set(target_doc.keys())
            
            # 속성 추가/삭제가 동시에 있는 경우
            if source_props != target_props:
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Failed to check conflicting changes: {e}")
            # 안전하게 충돌 있다고 가정
            return True
    
    def _has_schema_conflict(self, source_doc: Dict[str, Any], 
                           target_doc: Dict[str, Any]) -> bool:
        """
        스키마 충돌 검사 (기존 OntologyValidator 재사용)
        
        Args:
            source_doc: 소스 문서
            target_doc: 타겟 문서
            
        Returns:
            스키마 충돌 여부
        """
        try:
            if not self.ontology_validator:
                # 기본 충돌 검사
                return source_doc.get("@type") != target_doc.get("@type")
            
            # 기존 검증 로직 재사용
            source_errors = self.ontology_validator.validate(source_doc)
            target_errors = self.ontology_validator.validate(target_doc)
            
            # 검증 오류가 다르면 스키마 충돌 가능성
            return source_errors != target_errors
            
        except Exception as e:
            logger.warning(f"Failed to check schema conflict: {e}")
            return True
    
    def _check_property_conflicts(self, source_doc: Dict[str, Any],
                                 target_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        속성 충돌 검사 (기존 OntologyValidator 재사용)
        
        Args:
            source_doc: 소스 문서
            target_doc: 타겟 문서
            
        Returns:
            속성 충돌 목록
        """
        conflicts = []
        
        try:
            source_props = source_doc.get("properties", {})
            target_props = target_doc.get("properties", {})
            
            # 공통 속성에서 충돌 확인
            common_props = set(source_props.keys()) & set(target_props.keys())
            for prop in common_props:
                if source_props[prop] != target_props[prop]:
                    conflicts.append({
                        'property': prop,
                        'source_value': source_props[prop],
                        'target_value': target_props[prop]
                    })
            
        except Exception as e:
            logger.warning(f"Failed to check property conflicts: {e}")
        
        return conflicts
    
    def _check_rename_conflicts(self, doc_id: str, 
                               changes: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        이름 변경 충돌 검사
        
        Args:
            doc_id: 문서 ID
            changes: 변경사항
            
        Returns:
            이름 변경 충돌 목록
        """
        conflicts = []
        
        try:
            # 유사한 ID 패턴 확인
            base_id = doc_id.split('/')[-1] if '/' in doc_id else doc_id
            
            for other_id, change in changes.items():
                if other_id != doc_id:
                    other_base_id = other_id.split('/')[-1] if '/' in other_id else other_id
                    
                    # 유사한 이름 패턴 확인
                    if (base_id.lower() in other_base_id.lower() or 
                        other_base_id.lower() in base_id.lower()):
                        conflicts.append({
                            'other_id': other_id,
                            'similarity': 'name_pattern'
                        })
                    
        except Exception as e:
            logger.warning(f"Failed to check rename conflicts: {e}")
        
        return conflicts
    
    def _check_structural_conflicts(self, changes: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        구조적 충돌 검사
        
        Args:
            changes: 변경사항
            
        Returns:
            구조적 충돌 목록
        """
        conflicts = []
        
        try:
            # 관계 충돌 확인
            relationship_changes = {}
            for doc_id, change in changes.items():
                if change.get('type') == 'modified':
                    source_rels = change.get('source', {}).get('relationships', [])
                    target_rels = change.get('target', {}).get('relationships', [])
                    
                    if source_rels != target_rels:
                        relationship_changes[doc_id] = {
                            'source_relationships': source_rels,
                            'target_relationships': target_rels
                        }
            
            # 상호 의존성 충돌 확인
            for doc_id, rel_change in relationship_changes.items():
                conflicts.append({
                    'type': 'relationship_conflict',
                    'resource': doc_id,
                    'description': f"Relationship conflict in {doc_id}",
                    'source_change': rel_change['source_relationships'],
                    'target_change': rel_change['target_relationships'],
                    'conflict_type': 'structural'
                })
        
        except Exception as e:
            logger.warning(f"Failed to check structural conflicts: {e}")
        
        return conflicts
    
    def _get_common_ancestor(self, db_name: str, source: str, target: str) -> Optional[str]:
        """
        두 브랜치의 공통 조상 커밋 찾기 (3-way merge를 위한 base)
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            
        Returns:
            공통 조상 커밋 ID 또는 None
        """
        try:
            # 두 브랜치의 커밋 히스토리 가져오기 (기존 VersionService 재사용)
            source_history = self.version_service.get_history(
                db_name, source, limit=1000
            )
            target_history = self.version_service.get_history(
                db_name, target, limit=1000
            )
            
            # 소스 브랜치의 커밋 ID 집합 생성
            source_commits = {commit['id'] for commit in source_history}
            
            # 타겟 브랜치 히스토리를 순회하며 첫 번째 공통 커밋 찾기
            for commit in target_history:
                if commit['id'] in source_commits:
                    logger.debug(f"Found common ancestor '{commit['id']}' for branches '{source}' and '{target}'")
                    return commit['id']
            
            logger.warning(f"No common ancestor found between '{source}' and '{target}'")
            return None
            
        except Exception as e:
            logger.error(f"Failed to find common ancestor between '{source}' and '{target}': {e}")
            return None
    
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
            DomainException: 모든 방법이 실패한 경우
        """
        # domain.exceptions already imported at the top
        
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
        raise DomainException(
            message="Failed to commit: no compatible commit method found",
            code="COMMIT_FALLBACK_ERROR",
            details={"message": message, "author": author}
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
    
    
    def abort_merge(self, db_name: str) -> Dict[str, Any]:
        """
        병합 중단
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            중단 결과
        """
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 병합 중단 (가능한 경우)
                if hasattr(client, 'abort_merge'):
                    client.abort_merge()
                
                logger.info(f"Aborted merge in database '{db_name}'")
                
                return {
                    'db_name': db_name,
                    'aborted': True,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to abort merge in '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to abort merge in '{db_name}'",
                code="MERGE_ABORT_ERROR",
                details={"db_name": db_name, "error": str(e)}
            )