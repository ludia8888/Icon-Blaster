"""
LCS 기반 리스트 병합 알고리즘

순서가 중요한 리스트의 3-way merge를 지원합니다.
"""

from typing import List, Dict, Any, Optional, Tuple, TypeVar, Callable
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ListOperation(Enum):
    """리스트 변경 작업 타입"""
    ADD = "add"
    DELETE = "delete"
    MODIFY = "modify"
    REORDER = "reorder"


@dataclass
class ListChange:
    """리스트 변경사항"""
    operation: ListOperation
    item_id: str  # 항목 식별자
    index: Optional[int] = None  # 위치
    old_index: Optional[int] = None  # 이전 위치 (REORDER의 경우)
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None


@dataclass
class ListMergeResult:
    """리스트 병합 결과"""
    merged: List[Dict[str, Any]]
    conflicts: List[ListChange]
    has_conflicts: bool


class LCSListMerger:
    """
    Longest Common Subsequence 알고리즘을 사용한 리스트 병합
    
    순서 변경과 내용 변경을 독립적으로 처리합니다.
    """
    
    def __init__(self, identity_key: str = "name"):
        """
        Args:
            identity_key: 리스트 항목을 식별하는 키 (기본값: "name")
        """
        self.identity_key = identity_key
    
    def merge(
        self,
        base: List[Dict[str, Any]],
        source: List[Dict[str, Any]],
        target: List[Dict[str, Any]]
    ) -> ListMergeResult:
        """
        3-way 리스트 병합
        
        Args:
            base: 공통 조상 리스트
            source: 소스 브랜치 리스트
            target: 타겟 브랜치 리스트
            
        Returns:
            병합 결과
        """
        # 1. 각 리스트의 변경사항 분석
        source_changes = self._analyze_changes(base, source)
        target_changes = self._analyze_changes(base, target)
        
        # 2. 충돌 감지
        conflicts = self._detect_conflicts(source_changes, target_changes)
        
        # 3. 변경사항 병합
        if conflicts:
            # 충돌이 있으면 병합 실패
            return ListMergeResult(
                merged=[],
                conflicts=conflicts,
                has_conflicts=True
            )
        
        # 4. 최종 리스트 구성
        merged_list = self._apply_changes(base, source_changes, target_changes)
        
        return ListMergeResult(
            merged=merged_list,
            conflicts=[],
            has_conflicts=False
        )
    
    def _analyze_changes(
        self,
        base_list: List[Dict[str, Any]],
        modified_list: List[Dict[str, Any]]
    ) -> List[ListChange]:
        """리스트 변경사항 분석"""
        changes = []
        
        # ID로 인덱싱
        base_by_id = {item[self.identity_key]: (idx, item) 
                     for idx, item in enumerate(base_list)}
        modified_by_id = {item[self.identity_key]: (idx, item) 
                         for idx, item in enumerate(modified_list)}
        
        # 추가된 항목
        for item_id in modified_by_id:
            if item_id not in base_by_id:
                idx, item = modified_by_id[item_id]
                changes.append(ListChange(
                    operation=ListOperation.ADD,
                    item_id=item_id,
                    index=idx,
                    new_value=item
                ))
        
        # 삭제된 항목
        for item_id in base_by_id:
            if item_id not in modified_by_id:
                idx, item = base_by_id[item_id]
                changes.append(ListChange(
                    operation=ListOperation.DELETE,
                    item_id=item_id,
                    old_value=item
                ))
        
        # 수정되거나 순서가 변경된 항목
        for item_id in base_by_id:
            if item_id in modified_by_id:
                base_idx, base_item = base_by_id[item_id]
                mod_idx, mod_item = modified_by_id[item_id]
                
                # 내용 변경 확인
                content_changed = self._has_content_changed(base_item, mod_item)
                order_changed = base_idx != mod_idx
                
                if content_changed and order_changed:
                    # 내용과 순서 모두 변경
                    changes.append(ListChange(
                        operation=ListOperation.MODIFY,
                        item_id=item_id,
                        index=mod_idx,
                        old_index=base_idx,
                        old_value=base_item,
                        new_value=mod_item
                    ))
                elif content_changed:
                    # 내용만 변경
                    changes.append(ListChange(
                        operation=ListOperation.MODIFY,
                        item_id=item_id,
                        index=mod_idx,
                        old_value=base_item,
                        new_value=mod_item
                    ))
                elif order_changed:
                    # 순서만 변경
                    changes.append(ListChange(
                        operation=ListOperation.REORDER,
                        item_id=item_id,
                        index=mod_idx,
                        old_index=base_idx,
                        new_value=mod_item
                    ))
        
        return changes
    
    def _has_content_changed(self, item1: Dict[str, Any], item2: Dict[str, Any]) -> bool:
        """내용 변경 여부 확인 (ID와 순서 정보 제외)"""
        # 복사본 생성
        item1_copy = item1.copy()
        item2_copy = item2.copy()
        
        # ID와 순서 관련 필드 제거
        for key in [self.identity_key, "order", "sortOrder", "index"]:
            item1_copy.pop(key, None)
            item2_copy.pop(key, None)
        
        return item1_copy != item2_copy
    
    def _detect_conflicts(
        self,
        source_changes: List[ListChange],
        target_changes: List[ListChange]
    ) -> List[ListChange]:
        """충돌 감지"""
        conflicts = []
        
        # 변경사항을 item_id로 그룹화
        source_by_id = {c.item_id: c for c in source_changes}
        target_by_id = {c.item_id: c for c in target_changes}
        
        for item_id in source_by_id:
            if item_id in target_by_id:
                source_change = source_by_id[item_id]
                target_change = target_by_id[item_id]
                
                # 같은 항목에 대한 다른 종류의 작업은 병합 가능
                if source_change.operation != target_change.operation:
                    # 예: source는 REORDER, target은 MODIFY
                    continue
                
                # 같은 종류의 작업이지만 결과가 다른 경우만 충돌
                if source_change.operation == ListOperation.MODIFY:
                    # 내용이 다르게 수정된 경우
                    if source_change.new_value != target_change.new_value:
                        conflicts.append(source_change)
                        conflicts.append(target_change)
                
                elif source_change.operation == ListOperation.REORDER:
                    # 다른 위치로 이동한 경우
                    if source_change.index != target_change.index:
                        conflicts.append(source_change)
                        conflicts.append(target_change)
        
        return conflicts
    
    def _apply_changes(
        self,
        base_list: List[Dict[str, Any]],
        source_changes: List[ListChange],
        target_changes: List[ListChange]
    ) -> List[Dict[str, Any]]:
        """변경사항을 적용하여 최종 리스트 생성"""
        # 기본 리스트로 시작
        result_by_id = {item[self.identity_key]: item.copy() 
                       for item in base_list}
        
        # 모든 변경사항 수집
        all_changes = source_changes + target_changes
        
        # 변경사항 적용
        for change in all_changes:
            if change.operation == ListOperation.ADD:
                result_by_id[change.item_id] = change.new_value
            
            elif change.operation == ListOperation.DELETE:
                result_by_id.pop(change.item_id, None)
            
            elif change.operation == ListOperation.MODIFY:
                if change.item_id in result_by_id:
                    result_by_id[change.item_id] = change.new_value
        
        # 순서 재구성
        # 1. 최종 순서 결정 (source와 target의 순서 변경 모두 고려)
        final_order = self._determine_final_order(
            base_list, source_changes, target_changes, result_by_id
        )
        
        # 2. 순서에 따라 최종 리스트 생성
        result = []
        for item_id in final_order:
            if item_id in result_by_id:
                result.append(result_by_id[item_id])
        
        return result
    
    def _determine_final_order(
        self,
        base_list: List[Dict[str, Any]],
        source_changes: List[ListChange],
        target_changes: List[ListChange],
        result_items: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """최종 순서 결정"""
        # LCS 알고리즘을 사용하여 최적의 순서 결정
        # 여기서는 간단한 구현을 위해 다음 규칙 사용:
        # 1. REORDER 작업이 있으면 그 순서를 따름
        # 2. 충돌하는 REORDER가 없으면 source의 순서 우선
        
        # 순서 변경 수집
        reorders = {}
        for change in source_changes + target_changes:
            if change.operation == ListOperation.REORDER:
                reorders[change.item_id] = change.index
        
        # 최종 순서 구성
        ordered_items = []
        for item_id, pos in sorted(reorders.items(), key=lambda x: x[1]):
            if item_id in result_items:
                ordered_items.append(item_id)
        
        # 순서가 지정되지 않은 항목 추가
        for item_id in result_items:
            if item_id not in ordered_items:
                ordered_items.append(item_id)
        
        return ordered_items


def merge_with_lcs(
    base: List[Dict[str, Any]],
    source: List[Dict[str, Any]],
    target: List[Dict[str, Any]],
    identity_key: str = "name"
) -> ListMergeResult:
    """LCS 기반 리스트 병합 헬퍼 함수"""
    merger = LCSListMerger(identity_key)
    return merger.merge(base, source, target)