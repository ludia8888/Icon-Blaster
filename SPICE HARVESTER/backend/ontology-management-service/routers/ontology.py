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
    OntologyBase,
    QueryRequestInternal,
    QueryResponse
)
from models.common import BaseResponse
from datetime import datetime

# Add shared security module to path
from security.input_sanitizer import (
    validate_db_name, 
    validate_class_id, 
    sanitize_input,
    SecurityViolationError
)

# OMS 서비스 import
from services.async_terminus import AsyncTerminusService
from dependencies import get_terminus_service, get_jsonld_converter, get_label_mapper
from container import get_ontology_validator
from services.core.interfaces.ontology import IOntologyValidator

# shared utils import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from utils.jsonld import JSONToJSONLDConverter

logger = logging.getLogger(__name__)


async def _ensure_database_exists(db_name: str, terminus: AsyncTerminusService):
    """데이터베이스 존재 여부 확인 후 404 예외 발생"""
    # 데이터베이스 이름 보안 검증
    validated_db_name = validate_db_name(db_name)
    
    exists = await terminus.database_exists(validated_db_name)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"데이터베이스 '{validated_db_name}'을(를) 찾을 수 없습니다"
        )




router = APIRouter(
    prefix="/ontology/{db_name}",
    tags=["Ontology Management"]
)

@router.post("/create", response_model=OntologyResponse)
async def create_ontology(
    db_name: str,
    request: OntologyCreateRequest,
    terminus: AsyncTerminusService = Depends(get_terminus_service),
    converter: JSONToJSONLDConverter = Depends(get_jsonld_converter),
    label_mapper = Depends(get_label_mapper),
    validator: IOntologyValidator = Depends(get_ontology_validator)
) -> OntologyResponse:
    """내부 ID 기반 온톨로지 생성"""
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        # 요청 데이터를 dict로 변환
        ontology_data = request.model_dump()
        
        # 데이터베이스 존재 여부 확인
        await _ensure_database_exists(db_name, terminus)
        
        # 클래스 ID 검증
        class_id = ontology_data.get('id')
        if class_id:
            ontology_data['id'] = validate_class_id(class_id)
        
        # 속성 타입 유효성 검증 - 통합된 validator 서비스 사용
        validation_errors = validator._validate_data_types(ontology_data)
        if validation_errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid property types: {', '.join(validation_errors)}"
            )
        
        # TerminusDB에 직접 저장 (create_ontology_class 사용)
        result = await terminus.create_ontology_class(db_name, ontology_data)
        
        # 레이블 매핑 등록 (다국어 지원)
        class_id = ontology_data.get('id')
        if class_id:
            try:
                # 레이블 정보 추출 및 등록
                label_info = ontology_data.get('label', ontology_data.get('rdfs:label', class_id))
                description_info = ontology_data.get('description', ontology_data.get('rdfs:comment', ''))
                
                await label_mapper.register_class(db_name, class_id, label_info, description_info)
                
                # 속성 레이블 등록 (있는 경우)
                properties = ontology_data.get('properties', {})
                if isinstance(properties, dict):
                    for prop_name, prop_info in properties.items():
                        if isinstance(prop_info, dict) and 'label' in prop_info:
                            await label_mapper.register_property(db_name, class_id, prop_name, prop_info['label'])
                
                logger.info(f"Registered labels for ontology: {class_id}")
            except Exception as e:
                logger.warning(f"Failed to register labels for {class_id}: {e}")
                # 레이블 등록 실패는 온톨로지 생성을 실패시키지 않음
        
        # 생성된 온톨로지 데이터를 OntologyBase 형식으로 변환
        ontology_response_data = OntologyBase(
            id=ontology_data.get('id'),
            label=ontology_data.get('label', ontology_data.get('rdfs:label', ontology_data.get('id'))),
            description=ontology_data.get('description', ontology_data.get('rdfs:comment')),
            properties=[],  # properties는 별도로 조회 필요
            relationships=[],  # relationships는 별도로 조회 필요
            parent_class=ontology_data.get('parent_class'),
            abstract=ontology_data.get('abstract', False),
            metadata={
                "terminus_response": result,  # 원본 TerminusDB 응답 보존
                "creation_timestamp": datetime.utcnow().isoformat()
            }
        )
        
        return OntologyResponse(
            status="success",
            message=f"온톨로지 '{ontology_data.get('id')}'가 생성되었습니다",
            data=ontology_response_data
        )
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in create_ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create ontology: {e}")
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
    terminus: AsyncTerminusService = Depends(get_terminus_service),
    label_mapper = Depends(get_label_mapper)
):
    """내부 ID 기반 온톨로지 목록 조회"""
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        # class_type = sanitize_input(class_type)  # Temporarily disabled
        
        # 페이징 파라미터 검증
        if limit is not None and (limit < 1 or limit > 1000):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="limit은 1-1000 범위여야 합니다"
            )
        if offset < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="offset은 0 이상이어야 합니다"
            )
        
        # 데이터베이스 존재 여부 확인
        await _ensure_database_exists(db_name, terminus)
        
        # TerminusDB에서 조회
        ontologies = await terminus.list_ontology_classes(db_name)
        
        # 레이블 적용 (다국어 지원)
        labeled_ontologies = []
        if ontologies:
            try:
                labeled_ontologies = await label_mapper.convert_to_display_batch(db_name, ontologies, 'ko')
            except Exception as e:
                logger.warning(f"Failed to apply labels: {e}")
                labeled_ontologies = ontologies  # 레이블 적용 실패 시 원본 데이터 반환
        
        return {
            "status": "success",
            "message": f"온톨로지 목록 조회 완료 ({len(labeled_ontologies)}개)",
            "data": {
                "ontologies": labeled_ontologies,
                "count": len(labeled_ontologies),
                "limit": limit,
                "offset": offset
            }
        }
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in list_ontologies: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list ontologies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/{class_id}", response_model=OntologyResponse)
async def get_ontology(
    db_name: str,
    class_id: str,
    terminus: AsyncTerminusService = Depends(get_terminus_service),
    converter: JSONToJSONLDConverter = Depends(get_jsonld_converter)
):
    """내부 ID 기반 온톨로지 조회"""
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        class_id = validate_class_id(class_id)
        
        # 데이터베이스 존재 여부 확인
        await _ensure_database_exists(db_name, terminus)
        
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
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in get_ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        # AsyncOntologyNotFoundError 확인
        from services.async_terminus import AsyncOntologyNotFoundError
        if isinstance(e, AsyncOntologyNotFoundError) or "not found" in str(e).lower() or "찾을 수 없습니다" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"온톨로지 '{class_id}'를 찾을 수 없습니다"
            )
        
        logger.error(f"Failed to get ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.put("/{class_id}", response_model=OntologyResponse)
async def update_ontology(
    db_name: str,
    class_id: str,
    ontology_data: OntologyUpdateRequest,
    terminus: AsyncTerminusService = Depends(get_terminus_service),
    converter: JSONToJSONLDConverter = Depends(get_jsonld_converter)
):
    """내부 ID 기반 온톨로지 업데이트"""
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        class_id = validate_class_id(class_id)
        
        # 요청 데이터 정화
        sanitized_data = sanitize_input(ontology_data.dict(exclude_unset=True))
        
        # 데이터베이스 존재 여부 확인
        await _ensure_database_exists(db_name, terminus)
        
        # 기존 데이터 조회
        existing = await terminus.get_ontology(db_name, class_id)
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"온톨로지 '{class_id}'를 찾을 수 없습니다"
            )
        
        # 업데이트 데이터 병합
        merged_data = {**converter.extract_from_jsonld(existing), **sanitized_data}
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
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in update_ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.delete("/{class_id}", response_model=BaseResponse)
async def delete_ontology(
    db_name: str,
    class_id: str,
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """내부 ID 기반 온톨로지 삭제"""
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        class_id = validate_class_id(class_id)
        
        # 데이터베이스 존재 여부 확인
        await _ensure_database_exists(db_name, terminus)
        
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
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in delete_ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete ontology: {e}")
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
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        # 쿼리 데이터 정화
        sanitized_query = sanitize_input(query.dict())
        
        # 클래스 ID 검증 (있는 경우)
        if sanitized_query.get('class_id'):
            sanitized_query['class_id'] = validate_class_id(sanitized_query['class_id'])
        
        # 페이징 파라미터 검증
        limit = sanitized_query.get('limit', 50)
        offset = sanitized_query.get('offset', 0)
        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="limit은 1-1000 범위여야 합니다"
            )
        if offset < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="offset은 0 이상이어야 합니다"
            )
        
        # 데이터베이스 존재 여부 확인
        await _ensure_database_exists(db_name, terminus)
        
        # 쿼리 딕셔너리 변환
        query_dict = {
            "class_id": sanitized_query.get('class_id'),
            "filters": [
                {
                    "field": sanitize_input(f.get('field', '')),
                    "operator": sanitize_input(f.get('operator', '')),
                    "value": sanitize_input(f.get('value', ''))
                }
                for f in sanitized_query.get('filters', [])
            ],
            "select": sanitized_query.get('select', []),
            "limit": limit,
            "offset": offset
        }
        
        # 쿼리 실행
        result = await terminus.execute_query(db_name, query_dict)
        
        return QueryResponse(
            status="success",
            message="쿼리가 성공적으로 실행되었습니다",
            data=result.get("results", []),
            count=result.get("total", 0)
        )
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in query_ontologies: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )