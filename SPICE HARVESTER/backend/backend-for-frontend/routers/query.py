"""
쿼리 라우터
온톨로지 데이터 쿼리를 담당
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query as QueryParam, Request
from typing import Dict, List, Optional, Any
import logging
import sys
import os

# Add shared path for common utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from utils.language import get_accept_language

from models.ontology import QueryInput, QueryResponse
from dependencies import TerminusService, LabelMapper
from dependencies import get_terminus_service, get_label_mapper

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/database/{db_name}",
    tags=["Query"]
)


@router.post("/query", response_model=QueryResponse)
async def execute_query(
    db_name: str,
    query: QueryInput,
    request: Request,
    mapper: LabelMapper = Depends(get_label_mapper),
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    온톨로지 쿼리 실행
    
    레이블 기반 쿼리를 실행하여 온톨로지 데이터를 조회합니다.
    
    예시:
    ```json
    {
        "class_label": "제품",
        "filters": [
            {"field_label": "가격", "operator": ">=", "value": 10000},
            {"field_label": "카테고리", "operator": "=", "value": "전자제품"}
        ],
        "select": ["이름", "가격", "설명"],
        "order_by": "가격",
        "order_direction": "desc",
        "limit": 10
    }
    ```
    """
    lang = get_accept_language(request)
    
    try:
        # 쿼리 입력을 딕셔너리로 변환
        query_dict = query.dict(exclude_unset=True)
        
        # 레이블 기반 쿼리를 내부 ID 기반으로 변환
        internal_query = await mapper.convert_query_to_internal(db_name, query_dict, lang)
        
        # 쿼리 실행
        result = terminus.execute_query(db_name, internal_query)
        
        # 배치 결과를 레이블 기반으로 변환 (N+1 쿼리 문제 해결)
        labeled_results = await mapper.convert_to_display_batch(db_name, result.get("results", []), lang)
        
        # 응답 생성
        return QueryResponse(
            results=labeled_results,
            total=result.get("total", len(labeled_results)),
            query=query_dict
        )
        
    except ValueError as e:
        # 레이블을 찾을 수 없는 경우
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to execute query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"쿼리 실행 실패: {str(e)}"
        )


@router.post("/query/raw")
async def execute_raw_query(
    db_name: str,
    query: Dict[str, Any],
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    원시 쿼리 실행 (제한적 접근)
    
    내부 ID 기반의 원시 쿼리를 실행합니다.
    보안상 매우 제한적인 쿼리만 허용됩니다.
    """
    try:
        # 데이터베이스 이름 검증
        from shared.security.input_sanitizer import validate_db_name, sanitize_input
        validated_db_name = validate_db_name(db_name)
        
        # 쿼리 검증 - 허용된 쿼리 타입만 허용
        allowed_query_types = ['select', 'count', 'exists']
        query_type = query.get('type', '').lower()
        
        if query_type not in allowed_query_types:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"허용되지 않은 쿼리 타입: {query_type}. 허용된 타입: {allowed_query_types}"
            )
        
        # 쿼리 파라미터 정화
        sanitized_query = sanitize_input(query)
        
        # 쿼리 실행
        result = terminus.execute_query(validated_db_name, sanitized_query)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute raw query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"원시 쿼리 실행 실패: {str(e)}"
        )


@router.get("/query/builder")
async def query_builder_info():
    """
    쿼리 빌더 정보
    
    쿼리 작성을 위한 사용 가능한 연산자와 옵션을 반환합니다.
    """
    return {
        "operators": {
            "comparison": ["=", "!=", ">", ">=", "<", "<="],
            "string": ["LIKE", "NOT_LIKE", "STARTS_WITH", "ENDS_WITH", "CONTAINS"],
            "array": ["IN", "NOT_IN"],
            "null": ["IS_NULL", "IS_NOT_NULL"]
        },
        "order_directions": ["asc", "desc"],
        "special_fields": {
            "@id": "문서 ID",
            "@type": "문서 타입",
            "@created": "생성 시간",
            "@modified": "수정 시간"
        },
        "examples": {
            "simple": {
                "class_label": "제품",
                "filters": [
                    {"field_label": "가격", "operator": ">", "value": 10000}
                ],
                "limit": 10
            },
            "complex": {
                "class_label": "주문",
                "filters": [
                    {"field_label": "상태", "operator": "IN", "value_labels": ["배송중", "배송완료"]},
                    {"field_label": "총액", "operator": ">=", "value": 50000}
                ],
                "select": ["주문번호", "고객명", "총액", "상태"],
                "order_by": "주문일시",
                "order_direction": "desc",
                "limit": 20,
                "offset": 0
            }
        }
    }