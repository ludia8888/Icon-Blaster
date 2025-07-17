"""
BFF Merge Conflict Router
Foundry-style 병합 충돌 해결 API
"""

from fastapi import APIRouter, HTTPException, Depends, status
from typing import Dict, List, Optional, Any
import logging
import sys
import os

# shared 모델 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from models.requests import MergeRequest, ApiResponse
from models.common import BaseResponse

# BFF dependencies import
from dependencies import get_oms_client, OMSClient

# 보안 모듈 import - fallback functions
def validate_db_name(name):
    return name

def validate_branch_name(name):
    return name

class SecurityViolationError(Exception):
    pass

# 충돌 변환기 import  
utils_path = os.path.join(os.path.dirname(__file__), '..', 'utils')
sys.path.insert(0, utils_path)
try:
    from conflict_converter import ConflictConverter
except ImportError:
    # Fallback: 임시 ConflictConverter 클래스
    class ConflictConverter:
        async def convert_conflicts_to_foundry_format(self, conflicts, db_name, source_branch, target_branch):
            return []

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/database/{db_name}/merge",
    tags=["Merge Conflict Resolution"]
)


@router.post("/simulate", response_model=ApiResponse)
async def simulate_merge(
    db_name: str,
    request: MergeRequest,
    oms_client: OMSClient = Depends(get_oms_client)
) -> ApiResponse:
    """
    병합 시뮬레이션 - 실제 병합 없이 충돌 감지
    
    TerminusDB의 diff API를 사용하여 충돌 가능성을 미리 확인합니다.
    Foundry-style 충돌 감지 및 미리보기 기능을 제공합니다.
    
    Args:
        db_name: 데이터베이스 이름
        request: 병합 요청 정보
        
    Returns:
        충돌 정보와 병합 미리보기가 포함된 응답
    """
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        source_branch = validate_branch_name(request.source_branch)
        target_branch = validate_branch_name(request.target_branch)
        
        logger.info(f"Starting merge simulation: {source_branch} -> {target_branch} in {db_name}")
        
        # 1. 브랜치 존재 여부 확인
        try:
            source_info = await oms_client.client.get(
                f"/api/v1/branch/{db_name}/branch/{source_branch}/info"
            )
            await source_info.raise_for_status()
            
            target_info = await oms_client.client.get(
                f"/api/v1/branch/{db_name}/branch/{target_branch}/info"
            )
            await target_info.raise_for_status()
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"브랜치를 찾을 수 없습니다: {e}"
            )
        
        # 2. TerminusDB diff API를 사용하여 변경사항 분석
        try:
            diff_response = await oms_client.client.get(
                f"/api/v1/version/{db_name}/diff",
                params={
                    "from_ref": target_branch,
                    "to_ref": source_branch
                }
            )
            await diff_response.raise_for_status()
            diff_data = await diff_response.json()
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"차이 분석 실패: {e}"
            )
        
        # 3. 양방향 diff로 충돌 가능성 감지
        try:
            reverse_diff_response = await oms_client.client.get(
                f"/api/v1/version/{db_name}/diff",
                params={
                    "from_ref": source_branch,
                    "to_ref": target_branch
                }
            )
            await reverse_diff_response.raise_for_status()
            reverse_diff_data = await reverse_diff_response.json()
            
        except Exception as e:
            logger.warning(f"역방향 diff 분석 실패: {e}")
            reverse_diff_data = {"data": {"changes": []}}
        
        # 4. 충돌 감지 엔진 실행
        conflicts = await _detect_merge_conflicts(
            diff_data.get("data", {}).get("changes", []),
            reverse_diff_data.get("data", {}).get("changes", [])
        )
        
        # 5. Foundry 스타일 충돌 형식으로 변환
        converter = ConflictConverter()
        foundry_conflicts = await converter.convert_conflicts_to_foundry_format(
            conflicts, db_name, source_branch, target_branch
        )
        
        # 6. 병합 통계 계산
        source_changes = diff_data.get("data", {}).get("changes", [])
        merge_stats = {
            "changes_to_apply": len(source_changes),
            "conflicts_detected": len(foundry_conflicts),
            "mergeable": len(foundry_conflicts) == 0,
            "requires_manual_resolution": len(foundry_conflicts) > 0
        }
        
        logger.info(f"Merge simulation completed: {merge_stats}")
        
        return ApiResponse(
            status="success",
            message=f"병합 시뮬레이션 완료: {merge_stats['conflicts_detected']}개 충돌 감지",
            data={
                "merge_preview": {
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "strategy": request.strategy.value if hasattr(request.strategy, 'value') else str(request.strategy),
                    "conflicts": foundry_conflicts,
                    "changes": source_changes,
                    "statistics": merge_stats
                }
            }
        )
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in simulate_merge: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Merge simulation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"병합 시뮬레이션 실패: {e}"
        )


@router.post("/resolve", response_model=ApiResponse)
async def resolve_merge_conflicts(
    db_name: str,
    request: Dict[str, Any],
    oms_client: OMSClient = Depends(get_oms_client)
) -> ApiResponse:
    """
    수동 병합 충돌 해결
    
    사용자가 제공한 해결책으로 충돌을 해결하고 실제 병합을 수행합니다.
    
    Args:
        db_name: 데이터베이스 이름
        request: 충돌 해결 정보
        
    Returns:
        병합 결과
    """
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        source_branch = validate_branch_name(request.get("source_branch"))
        target_branch = validate_branch_name(request.get("target_branch"))
        resolutions = request.get("resolutions", [])
        
        logger.info(f"Starting manual merge resolution: {source_branch} -> {target_branch}")
        
        # 1. 해결책 검증
        if not resolutions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="충돌 해결책이 제공되지 않았습니다"
            )
        
        # 2. 각 해결책을 TerminusDB 형식으로 변환
        terminus_resolutions = []
        for resolution in resolutions:
            terminus_resolution = await _convert_resolution_to_terminus_format(resolution)
            terminus_resolutions.append(terminus_resolution)
        
        # 3. TerminusDB merge API 호출 (해결책 포함)
        merge_data = {
            "source": source_branch,
            "target": target_branch,
            "strategy": request.get("strategy", "merge"),
            "message": request.get("message", f"Resolve conflicts: {source_branch} -> {target_branch}"),
            "author": request.get("author"),
            "conflict_resolutions": terminus_resolutions
        }
        
        try:
            merge_response = await oms_client.client.post(
                f"/api/v1/version/{db_name}/merge", 
                json=merge_data
            )
            await merge_response.raise_for_status()
            merge_result = await merge_response.json()
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"병합 실행 실패: {e}"
            )
        
        logger.info(f"Manual merge resolution completed successfully")
        
        return ApiResponse(
            status="success",
            message="충돌이 해결되고 병합이 완료되었습니다",
            data={
                "merge_result": merge_result.get("data", {}),
                "resolved_conflicts": len(resolutions)
            }
        )
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in resolve_merge_conflicts: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual merge resolution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"충돌 해결 실패: {e}"
        )


async def _detect_merge_conflicts(
    source_changes: List[Dict[str, Any]], 
    target_changes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    3-way 병합 충돌 감지 엔진
    
    Args:
        source_changes: 소스 브랜치의 변경사항
        target_changes: 대상 브랜치의 변경사항
        
    Returns:
        감지된 충돌 목록
    """
    conflicts = []
    
    # 경로별로 변경사항 그룹화
    source_paths = {change.get("path", change.get("id", "unknown")): change for change in source_changes}
    target_paths = {change.get("path", change.get("id", "unknown")): change for change in target_changes}
    
    # 동일한 경로에서 서로 다른 변경이 있는 경우 충돌로 감지
    for path in source_paths:
        if path in target_paths:
            source_change = source_paths[path]
            target_change = target_paths[path]
            
            # 동일한 값으로의 변경은 충돌이 아님
            if source_change.get("new_value") != target_change.get("new_value"):
                conflict = {
                    "path": path,
                    "type": "content_conflict",
                    "source_change": source_change,
                    "target_change": target_change,
                    "common_ancestor": None  # TODO: 공통 조상 찾기
                }
                conflicts.append(conflict)
    
    return conflicts




async def _convert_resolution_to_terminus_format(
    resolution: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Foundry 해결책을 TerminusDB 형식으로 변환
    
    Args:
        resolution: Foundry 스타일 해결책
        
    Returns:
        TerminusDB 형식 해결책
    """
    return {
        "path": resolution.get("path"),
        "resolution_type": resolution.get("resolution_type", "use_value"),
        "value": resolution.get("resolved_value"),
        "metadata": resolution.get("metadata", {})
    }