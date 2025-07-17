"""
온톨로지 CRUD 라우터
온톨로지 생성, 조회, 수정, 삭제를 담당
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Dict, List, Optional, Any
import logging
import sys
import os

# Add shared path for common utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from utils.language import get_accept_language

from models.ontology import (
    OntologyCreateRequestBFF,
    OntologyUpdateInput,
    OntologyResponse
)
from dependencies import TerminusService
from fastapi import HTTPException
from dependencies import JSONToJSONLDConverter
from dependencies import LabelMapper
from dependencies import get_terminus_service, get_jsonld_converter, get_label_mapper

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/database/{db_name}",
    tags=["Ontology Management"]
)


@router.post("/ontology", response_model=OntologyResponse)
async def create_ontology(
    db_name: str,
    ontology: OntologyCreateRequestBFF,
    mapper: LabelMapper = Depends(get_label_mapper),
    terminus: TerminusService = Depends(get_terminus_service),
    jsonld_conv: JSONToJSONLDConverter = Depends(get_jsonld_converter)
):
    """
    온톨로지 생성
    
    새로운 온톨로지 클래스를 생성합니다.
    레이블 기반으로 ID가 자동 생성됩니다.
    """
    try:
        # 입력 데이터를 딕셔너리로 변환
        ontology_dict = ontology.dict(exclude_unset=True)
        
        # 레이블로부터 ID 생성 (한글/영문 처리)
        import re
        # label이 MultiLingualText인지 문자열인지 확인
        if isinstance(ontology.label, dict):
            # MultiLingualText인 경우
            label = ontology.label.get('en') or ontology.label.get('ko') or "UnnamedClass"
        elif isinstance(ontology.label, str):
            label = ontology.label
        else:
            # MultiLingualText 객체인 경우
            label = getattr(ontology.label, 'en', None) or getattr(ontology.label, 'ko', None) or "UnnamedClass"
        
        # 한글/특수문자를 영문으로 변환하고 공백을 CamelCase로
        class_id = re.sub(r'[^\w\s]', '', label)
        class_id = ''.join(word.capitalize() for word in class_id.split())
        # 첫 글자가 숫자인 경우 'Class' 접두사 추가
        if class_id and class_id[0].isdigit():
            class_id = 'Class' + class_id
        ontology_dict["id"] = class_id
        
        # 온톨로지 생성
        result = terminus.create_ontology(db_name, ontology_dict)
        
        # 레이블 매핑 등록
        await mapper.register_class(db_name, class_id, ontology.label, ontology.description)
        
        # 속성 레이블 매핑
        for prop in ontology.properties:
            await mapper.register_property(db_name, class_id, prop.name, prop.label)
        
        # 관계 레이블 매핑
        for rel in ontology.relationships:
            await mapper.register_relationship(db_name, rel.predicate, rel.label)
        
        # 응답 생성
        return OntologyResponse(
            id=class_id,
            label=ontology.label,
            description=ontology.description,
            properties=ontology.properties,
            relationships=ontology.relationships,
            metadata={
                "created": True,
                "database": db_name
            }
        )
        
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"온톨로지 ID '{e.ontology_id}'가 이미 존재합니다"
        )
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"유효성 검증 실패: {e.message}"
        )
    except Exception as e:
        logger.error(f"Failed to create ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"온톨로지 생성 실패: {str(e)}"
        )


@router.get("/ontology/{class_label}", response_model=OntologyResponse)
async def get_ontology(
    db_name: str,
    class_label: str,
    request: Request,
    mapper: LabelMapper = Depends(get_label_mapper),
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    온톨로지 조회
    
    레이블 또는 ID로 온톨로지를 조회합니다.
    """
    lang = get_accept_language(request)
    
    try:
        # 레이블로 ID 조회 시도
        class_id = await mapper.get_class_id(db_name, class_label, lang)
        
        # ID가 없으면 입력값을 ID로 간주
        if not class_id:
            class_id = class_label
        
        # 온톨로지 조회
        result = terminus.get_ontology(db_name, class_id)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"온톨로지 '{class_label}'을(를) 찾을 수 없습니다"
            )
        
        # 레이블 정보 추가
        result = await mapper.convert_to_display(db_name, result, lang)
        
        return OntologyResponse(**result)
        
    except HTTPException:
        raise
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"온톨로지 '{e.ontology_id}'을(를) 찾을 수 없습니다"
        )
    except Exception as e:
        logger.error(f"Failed to get ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"온톨로지 조회 실패: {str(e)}"
        )


@router.put("/ontology/{class_label}")
async def update_ontology(
    db_name: str,
    class_label: str,
    ontology: OntologyUpdateInput,
    request: Request,
    mapper: LabelMapper = Depends(get_label_mapper),
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    온톨로지 수정
    
    기존 온톨로지를 수정합니다.
    """
    lang = get_accept_language(request)
    
    try:
        # 레이블로 ID 조회
        class_id = await mapper.get_class_id(db_name, class_label, lang)
        if not class_id:
            class_id = class_label
        
        # 업데이트 데이터 준비
        update_data = ontology.dict(exclude_unset=True)
        update_data["id"] = class_id
        
        # 온톨로지 업데이트
        result = terminus.update_ontology(db_name, class_id, update_data)
        
        # 레이블 매핑 업데이트
        await mapper.update_mappings(db_name, update_data)
        
        return {
            "message": f"온톨로지 '{class_label}'이(가) 수정되었습니다",
            "id": class_id,
            "updated_fields": list(update_data.keys())
        }
        
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"온톨로지 '{e.ontology_id}'을(를) 찾을 수 없습니다"
        )
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"유효성 검증 실패: {e.message}"
        )
    except Exception as e:
        logger.error(f"Failed to update ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"온톨로지 수정 실패: {str(e)}"
        )


@router.delete("/ontology/{class_label}")
async def delete_ontology(
    db_name: str,
    class_label: str,
    request: Request,
    mapper: LabelMapper = Depends(get_label_mapper),
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    온톨로지 삭제
    
    온톨로지를 삭제합니다.
    주의: 이 작업은 되돌릴 수 없습니다!
    """
    lang = get_accept_language(request)
    
    try:
        # 레이블로 ID 조회
        class_id = await mapper.get_class_id(db_name, class_label, lang)
        if not class_id:
            class_id = class_label
        
        # 온톨로지 삭제
        terminus.delete_ontology(db_name, class_id)
        
        # 레이블 매핑 삭제
        await mapper.remove_class(db_name, class_id)
        
        return {
            "message": f"온톨로지 '{class_label}'이(가) 삭제되었습니다",
            "id": class_id
        }
        
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"온톨로지 '{e.ontology_id}'을(를) 찾을 수 없습니다"
        )
    except Exception as e:
        logger.error(f"Failed to delete ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"온톨로지 삭제 실패: {str(e)}"
        )


@router.get("/ontologies")
async def list_ontologies(
    db_name: str,
    request: Request,
    class_type: str = Query("sys:Class", description="클래스 타입"),
    limit: Optional[int] = Query(None, description="결과 개수 제한"),
    offset: int = Query(0, description="오프셋"),
    mapper: LabelMapper = Depends(get_label_mapper),
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    온톨로지 목록 조회
    
    데이터베이스의 모든 온톨로지를 조회합니다.
    """
    lang = get_accept_language(request)
    
    try:
        # 온톨로지 목록 조회
        ontologies = terminus.list_ontologies(
            db_name, 
            class_type=class_type,
            limit=limit,
            offset=offset
        )
        
        # 배치 레이블 정보 추가 (N+1 쿼리 문제 해결)
        labeled_ontologies = await mapper.convert_to_display_batch(db_name, ontologies, lang)
        
        return {
            "total": len(labeled_ontologies),
            "ontologies": labeled_ontologies,
            "offset": offset,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Failed to list ontologies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"온톨로지 목록 조회 실패: {str(e)}"
        )


@router.get("/ontology/{class_id}/schema")
async def get_ontology_schema(
    db_name: str,
    class_id: str,
    request: Request,
    format: str = Query("json", description="스키마 형식 (json, jsonld, owl)"),
    mapper: LabelMapper = Depends(get_label_mapper),
    terminus: TerminusService = Depends(get_terminus_service),
    jsonld_conv: JSONToJSONLDConverter = Depends(get_jsonld_converter)
):
    """
    온톨로지 스키마 조회
    
    온톨로지의 스키마를 다양한 형식으로 조회합니다.
    """
    lang = get_accept_language(request)
    
    try:
        # 레이블로 ID 조회
        actual_id = await mapper.get_class_id(db_name, class_id, lang)
        if not actual_id:
            actual_id = class_id
        
        # 온톨로지 조회
        ontology = terminus.get_ontology(db_name, actual_id)
        
        if not ontology:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"온톨로지 '{class_id}'을(를) 찾을 수 없습니다"
            )
        
        # 형식별 변환
        if format == "jsonld":
            schema = jsonld_conv.convert_to_jsonld(ontology, db_name)
        elif format == "owl":
            # OWL 변환 (구현 필요)
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="OWL 형식은 아직 지원되지 않습니다"
            )
        else:
            # 기본 JSON
            schema = ontology
        
        return schema
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get ontology schema: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"온톨로지 스키마 조회 실패: {str(e)}"
        )