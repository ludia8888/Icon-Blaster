"""
OMS 온톨로지 라우터 - 내부 ID 기반 온톨로지 관리
"""

from fastapi import APIRouter, HTTPException, Depends, status
from typing import Dict, List, Optional, Any
import logging
import sys
import os

# shared 모델 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from models.ontology import (
    OntologyCreateRequest,
    OntologyUpdateRequest,
    OntologyResponse,
    QueryRequestInternal,
    QueryResponse
)
from models.common import BaseResponse

# OMS 서비스 import
from services.async_terminus import AsyncTerminusService
from dependencies import get_terminus_service, get_jsonld_converter

# shared utils import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from utils.jsonld import JSONToJSONLDConverter

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/create")
async def create_ontology(
    request: dict,
    terminus: AsyncTerminusService = Depends(get_terminus_service),
    converter: JSONToJSONLDConverter = Depends(get_jsonld_converter)
):
    """내부 ID 기반 온톨로지 생성"""
    try:
        # 요청 데이터 검증
        db_name = request.get("db_name")
        if not db_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="데이터베이스 이름이 필요합니다"
            )
        
        # 온톨로지 데이터 추출
        ontology_data = {k: v for k, v in request.items() if k != "db_name"}
        
        # TerminusDB에 직접 저장 (create_ontology_class 사용)
        result = await terminus.create_ontology_class(db_name, ontology_data)
        
        return {
            "status": "success",
            "message": f"온톨로지 '{ontology_data.get('id')}'가 생성되었습니다",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Failed to create ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/get/{class_id}", response_model=OntologyResponse)
async def get_ontology(
    db_name: str,
    class_id: str,
    terminus: AsyncTerminusService = Depends(get_terminus_service),
    converter: JSONToJSONLDConverter = Depends(get_jsonld_converter)
):
    """내부 ID 기반 온톨로지 조회"""
    try:
        # TerminusDB에서 조회
        ontology = await terminus.get_ontology(db_name, class_id)
        
        if not ontology:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"온톨로지 '{class_id}'를 찾을 수 없습니다"
            )
        
        # JSON-LD를 일반 JSON으로 변환
        result = converter.extract_from_jsonld(ontology)
        
        return OntologyResponse(
            status="success",
            message=f"온톨로지 '{class_id}'를 조회했습니다",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.put("/update/{class_id}", response_model=OntologyResponse)
async def update_ontology(
    db_name: str,
    class_id: str,
    ontology_data: OntologyUpdateRequest,
    terminus: AsyncTerminusService = Depends(get_terminus_service),
    converter: JSONToJSONLDConverter = Depends(get_jsonld_converter)
):
    """내부 ID 기반 온톨로지 업데이트"""
    try:
        # 기존 데이터 조회
        existing = await terminus.get_ontology(db_name, class_id)
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"온톨로지 '{class_id}'를 찾을 수 없습니다"
            )
        
        # 업데이트 데이터 병합
        update_dict = ontology_data.dict(exclude_unset=True)
        merged_data = {**converter.extract_from_jsonld(existing), **update_dict}
        merged_data['id'] = class_id  # ID는 변경 불가
        
        # JSON-LD로 변환
        jsonld_data = converter.convert_with_labels(merged_data)
        
        # TerminusDB 업데이트
        result = await terminus.update_ontology(db_name, class_id, jsonld_data)
        
        return OntologyResponse(
            status="success",
            message=f"온톨로지 '{class_id}'가 업데이트되었습니다",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.delete("/delete/{class_id}", response_model=BaseResponse)
async def delete_ontology(
    db_name: str,
    class_id: str,
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """내부 ID 기반 온톨로지 삭제"""
    try:
        # TerminusDB에서 삭제
        success = await terminus.delete_ontology(db_name, class_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"온톨로지 '{class_id}'를 찾을 수 없습니다"
            )
        
        return BaseResponse(
            status="success",
            message=f"온톨로지 '{class_id}'가 삭제되었습니다"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/list")
async def list_ontologies(
    db_name: str,
    class_type: str = "sys:Class",
    limit: Optional[int] = 100,
    offset: int = 0,
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """내부 ID 기반 온톨로지 목록 조회"""
    try:
        # TerminusDB에서 조회
        ontologies = await terminus.list_ontology_classes(db_name)
        
        return {
            "status": "success",
            "message": f"온톨로지 목록 조회 완료 ({len(ontologies)}개)",
            "data": {
                "ontologies": ontologies,
                "count": len(ontologies),
                "limit": limit,
                "offset": offset
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to list ontologies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/query", response_model=QueryResponse)
async def query_ontologies(
    db_name: str,
    query: QueryRequestInternal,
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """내부 ID 기반 온톨로지 쿼리"""
    try:
        # 쿼리 딕셔너리 변환
        query_dict = {
            "class_id": query.class_id,
            "filters": [
                {
                    "field": f.field,
                    "operator": f.operator,
                    "value": f.value
                }
                for f in query.filters
            ],
            "select": query.select,
            "limit": query.limit,
            "offset": query.offset
        }
        
        # 쿼리 실행
        result = await terminus.execute_query(db_name, query_dict)
        
        return QueryResponse(
            status="success",
            message="쿼리가 성공적으로 실행되었습니다",
            data=result.get("results", []),
            count=result.get("total", 0)
        )
        
    except Exception as e:
        logger.error(f"Failed to execute query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )