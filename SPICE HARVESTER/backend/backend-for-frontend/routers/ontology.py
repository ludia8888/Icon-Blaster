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
    OntologyResponse,
    OntologyBase
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
        
        # 한글이 포함된 경우 기본 ID 사용
        if not class_id or not class_id.replace('_', '').isalnum():
            # 타임스탬프 기반 고유 ID 생성
            import time
            class_id = f"Class{int(time.time() * 1000) % 1000000}"
            
        ontology_dict["id"] = class_id
        logger.info(f"Generated class_id '{class_id}' from label '{label}'")
        
        # 온톨로지 생성
        result = await terminus.create_class(db_name, ontology_dict)
        logger.info(f"OMS create result: {result}")
        
        # 레이블 매핑 등록
        await mapper.register_class(db_name, class_id, ontology.label, ontology.description)
        
        # 속성 레이블 매핑
        for prop in ontology.properties:
            await mapper.register_property(db_name, class_id, prop.name, prop.label)
        
        # 관계 레이블 매핑
        for rel in ontology.relationships:
            await mapper.register_relationship(db_name, rel.predicate, rel.label)
        
        # OMS 응답에서 생성된 데이터 추출
        if isinstance(result, dict):
            # OMS가 data 필드를 반환하는 경우
            if "data" in result and result.get("status") == "success":
                created_data = result["data"]
                # 생성된 ID 사용
                if "id" in created_data:
                    class_id = created_data["id"]
            elif "id" in result:
                # 직접 데이터 형식인 경우
                created_data = result
                class_id = result["id"]
        
        # 응답 생성
        ontology_base = OntologyBase(
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
        return OntologyResponse(data=ontology_base)
        
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
        # URL 파라미터 디버깅
        logger.info(f"Getting ontology - db_name: {db_name}, class_label: {class_label}, lang: {lang}")
        
        # 레이블로 ID 조회 시도
        class_id = await mapper.get_class_id(db_name, class_label, lang)
        logger.info(f"Mapped label '{class_label}' to class_id: {class_id}")
        
        # ID가 없으면 입력값을 ID로 간주
        if not class_id:
            class_id = class_label
            logger.info(f"No mapping found, using label as ID: {class_id}")
        
        # 온톨로지 조회
        result = await terminus.get_class(db_name, class_id)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"온톨로지 '{class_label}'을(를) 찾을 수 없습니다"
            )
        
        logger.info(f"Raw result from terminus.get_class: {result}")
        
        # Extract ontology data (terminus.get_class already extracts from data field)
        ontology_data = result if isinstance(result, dict) else {}
        
        # 레이블 정보 추가
        ontology_data = await mapper.convert_to_display(db_name, ontology_data, lang)
        logger.info(f"After convert_to_display: {ontology_data}")
        
        # Ensure result has required fields for OntologyResponse
        if not ontology_data.get('id'):
            ontology_data['id'] = class_id
        if not ontology_data.get('label'):
            # Try to get label from the mapper
            label = await mapper.get_class_label(db_name, class_id, lang)
            ontology_data['label'] = label or class_label
        
        # Remove extra fields that are not part of OntologyBase
        ontology_base_data = {
            'id': ontology_data.get('id'),
            'label': ontology_data.get('label'),
            'description': ontology_data.get('description'),
            'properties': ontology_data.get('properties', []),
            'relationships': ontology_data.get('relationships', []),
            'parent_class': ontology_data.get('parent_class'),
            'abstract': ontology_data.get('abstract', False),
            'metadata': ontology_data.get('metadata')
        }
        
        # OntologyResponse expects a 'data' field
        return OntologyResponse(data=OntologyBase(**ontology_base_data))
        
    except HTTPException:
        raise
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
        result = await terminus.update_class(db_name, class_id, update_data)
        
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
        await terminus.delete_class(db_name, class_id)
        
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
        ontologies = await terminus.list_classes(db_name)
        
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
        ontology = await terminus.get_class(db_name, actual_id)
        
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


# 🔥 THINK ULTRA! BFF Enhanced Relationship Management Endpoints

@router.post("/ontology-advanced", response_model=OntologyResponse)
async def create_ontology_with_relationship_validation(
    db_name: str,
    ontology: OntologyCreateRequestBFF,
    auto_generate_inverse: bool = Query(True, description="자동 역관계 생성 여부"),
    validate_relationships: bool = Query(True, description="관계 검증 수행 여부"),
    check_circular_references: bool = Query(True, description="순환 참조 체크 여부"),
    mapper: LabelMapper = Depends(get_label_mapper),
    terminus: TerminusService = Depends(get_terminus_service),
    jsonld_conv: JSONToJSONLDConverter = Depends(get_jsonld_converter)
):
    """
    🔥 고급 관계 검증을 포함한 온톨로지 생성 (BFF 레이어)
    
    Features:
    - 레이블 기반 자동 ID 생성
    - 자동 역관계 생성
    - 관계 검증 및 무결성 체크
    - 순환 참조 탐지
    - 다국어 레이블 매핑
    """
    try:
        # 입력 데이터를 딕셔너리로 변환
        ontology_dict = ontology.dict(exclude_unset=True)
        
        # 레이블로부터 ID 생성 (기존 로직 재사용)
        import re
        if isinstance(ontology.label, dict):
            label = ontology.label.get('en') or ontology.label.get('ko') or "UnnamedClass"
        elif isinstance(ontology.label, str):
            label = ontology.label
        else:
            label = getattr(ontology.label, 'en', None) or getattr(ontology.label, 'ko', None) or "UnnamedClass"
        
        class_id = re.sub(r'[^\w\s]', '', label)
        class_id = ''.join(word.capitalize() for word in class_id.split())
        if class_id and class_id[0].isdigit():
            class_id = 'Class' + class_id
        
        if not class_id or not class_id.replace('_', '').isalnum():
            import time
            class_id = f"Class{int(time.time() * 1000) % 1000000}"
            
        ontology_dict["id"] = class_id
        logger.info(f"🔥 Generated class_id '{class_id}' for advanced ontology creation")
        
        # 🔥 OMS에서 고급 관계 관리 기능 호출
        oms_result = await terminus.create_ontology_with_advanced_relationships(
            db_name=db_name,
            ontology_data=ontology_dict,
            auto_generate_inverse=auto_generate_inverse,
            validate_relationships=validate_relationships,
            check_circular_references=check_circular_references
        )
        
        # 레이블 매핑 등록
        await mapper.register_class(db_name, class_id, ontology.label, ontology.description)
        
        # 속성 레이블 매핑
        for prop in ontology.properties:
            await mapper.register_property(db_name, class_id, prop.name, prop.label)
        
        # 관계 레이블 매핑
        for rel in ontology.relationships:
            await mapper.register_relationship(db_name, rel.predicate, rel.label)
        
        # 관계 향상 정보 추출
        relationship_enhancements = oms_result.get("relationship_enhancements", {})
        
        # 응답 생성
        ontology_base = OntologyBase(
            id=class_id,
            label=ontology.label,
            description=ontology.description,
            properties=ontology.properties,
            relationships=ontology.relationships,
            metadata={
                "created_with_advanced_features": True,
                "database": db_name,
                "auto_inverse_generated": auto_generate_inverse,
                "validation_performed": validate_relationships,
                "circular_check_performed": check_circular_references,
                "validation_summary": relationship_enhancements.get("validation_results", []),
                "cycles_detected": len(relationship_enhancements.get("cycle_info", [])),
                "inverse_relationships": relationship_enhancements.get("inverse_relationships_generated", False)
            }
        )
        
        return OntologyResponse(
            data=ontology_base,
            message=f"고급 관계 기능을 포함한 온톨로지 '{class_id}'가 생성되었습니다"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create ontology with advanced relationships: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"고급 온톨로지 생성 실패: {str(e)}"
        )


@router.post("/validate-relationships")
async def validate_ontology_relationships_bff(
    db_name: str,
    ontology: OntologyCreateRequestBFF,
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    🔥 온톨로지 관계 검증 (BFF 레이어)
    
    실제 생성 없이 관계의 유효성만 검증하고 사용자 친화적 결과 반환
    """
    try:
        # 입력 데이터 준비
        ontology_dict = ontology.dict(exclude_unset=True)
        
        # 임시 ID 생성 (검증용)
        import re
        if isinstance(ontology.label, dict):
            label = ontology.label.get('en') or ontology.label.get('ko') or "TempClass"
        elif isinstance(ontology.label, str):
            label = ontology.label
        else:
            label = getattr(ontology.label, 'en', None) or getattr(ontology.label, 'ko', None) or "TempClass"
        
        class_id = re.sub(r'[^\w\s]', '', label)
        class_id = ''.join(word.capitalize() for word in class_id.split())
        if not class_id or class_id[0].isdigit():
            class_id = 'TempClass'
            
        ontology_dict["id"] = class_id
        
        # 관계 검증 수행
        validation_result = await terminus.validate_relationships(db_name, ontology_dict)
        
        # 사용자 친화적 형태로 변환
        summary = validation_result.get("validation_summary", {})
        validation_issues = validation_result.get("validation_results", [])
        
        # 심각도별 분류
        errors = [issue for issue in validation_issues if issue.get("severity") == "error"]
        warnings = [issue for issue in validation_issues if issue.get("severity") == "warning"] 
        info = [issue for issue in validation_issues if issue.get("severity") == "info"]
        
        return {
            "status": "success",
            "message": "관계 검증이 완료되었습니다",
            "validation_summary": {
                "can_create": summary.get("can_proceed", True),
                "total_issues": summary.get("total_issues", 0),
                "errors": len(errors),
                "warnings": len(warnings),
                "info": len(info)
            },
            "issues": {
                "critical_errors": [
                    {
                        "field": issue.get("field"),
                        "message": issue.get("message"),
                        "code": issue.get("code")
                    }
                    for issue in errors
                ],
                "warnings": [
                    {
                        "field": issue.get("field"),
                        "message": issue.get("message"),
                        "code": issue.get("code")
                    }
                    for issue in warnings
                ],
                "recommendations": [
                    {
                        "field": issue.get("field"),
                        "message": issue.get("message"),
                        "code": issue.get("code")
                    }
                    for issue in info
                ]
            },
            "metadata": {
                "ontology_label": label,
                "temp_class_id": class_id,
                "validation_timestamp": validation_result.get("timestamp")
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to validate relationships: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"관계 검증 실패: {str(e)}"
        )


@router.post("/check-circular-references")
async def check_circular_references_bff(
    db_name: str,
    ontology: Optional[OntologyCreateRequestBFF] = None,
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    🔥 순환 참조 탐지 (BFF 레이어)
    
    기존 온톨로지들과 새 온톨로지(선택사항) 간의 순환 참조를 탐지하고
    사용자 친화적 결과 반환
    """
    try:
        # 새 온톨로지 데이터 준비
        new_ontology_data = None
        if ontology:
            ontology_dict = ontology.dict(exclude_unset=True)
            
            # 임시 ID 생성
            import re
            if isinstance(ontology.label, dict):
                label = ontology.label.get('en') or ontology.label.get('ko') or "TempClass"
            elif isinstance(ontology.label, str):
                label = ontology.label
            else:
                label = getattr(ontology.label, 'en', None) or getattr(ontology.label, 'ko', None) or "TempClass"
            
            class_id = re.sub(r'[^\w\s]', '', label)
            class_id = ''.join(word.capitalize() for word in class_id.split())
            if not class_id or class_id[0].isdigit():
                class_id = 'TempClass'
                
            ontology_dict["id"] = class_id
            new_ontology_data = ontology_dict
        
        # 순환 참조 탐지 수행
        cycle_result = await terminus.detect_circular_references(
            db_name, 
            include_new_ontology=new_ontology_data
        )
        
        # 사용자 친화적 형태로 변환
        report = cycle_result.get("cycle_analysis_report", {})
        detected_cycles = cycle_result.get("detected_cycles", [])
        
        # 심각도별 분류
        critical_cycles = [cycle for cycle in detected_cycles if cycle.get("severity") == "critical"]
        warning_cycles = [cycle for cycle in detected_cycles if cycle.get("severity") == "warning"]
        info_cycles = [cycle for cycle in detected_cycles if cycle.get("severity") == "info"]
        
        return {
            "status": "success",
            "message": "순환 참조 탐지가 완료되었습니다",
            "cycle_summary": {
                "safe_to_create": len(critical_cycles) == 0,
                "total_cycles": report.get("total_cycles", 0),
                "critical_cycles": len(critical_cycles),
                "warning_cycles": len(warning_cycles),
                "info_cycles": len(info_cycles),
                "average_cycle_length": report.get("average_cycle_length", 0)
            },
            "cycles": {
                "critical": [
                    {
                        "type": cycle.get("type"),
                        "path": " → ".join(cycle.get("path", [])),
                        "predicates": cycle.get("predicates", []),
                        "message": cycle.get("message"),
                        "solutions": cycle.get("resolution_suggestions", [])
                    }
                    for cycle in critical_cycles
                ],
                "warnings": [
                    {
                        "type": cycle.get("type"),
                        "path": " → ".join(cycle.get("path", [])),
                        "predicates": cycle.get("predicates", []),
                        "message": cycle.get("message"),
                        "solutions": cycle.get("resolution_suggestions", [])
                    }
                    for cycle in warning_cycles
                ]
            },
            "recommendations": report.get("recommendations", []),
            "metadata": {
                "analysis_includes_new_ontology": new_ontology_data is not None,
                "new_ontology_label": label if ontology else None
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to check circular references: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"순환 참조 탐지 실패: {str(e)}"
        )


@router.get("/relationship-network/analyze")
async def analyze_relationship_network_bff(
    db_name: str,
    request: Request,
    terminus: TerminusService = Depends(get_terminus_service),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """
    🔥 관계 네트워크 분석 (BFF 레이어)
    
    전체 관계 네트워크의 건강성을 분석하고 사용자 친화적 결과 반환
    """
    lang = get_accept_language(request)
    
    try:
        # 네트워크 분석 수행
        analysis_result = await terminus.analyze_relationship_network(db_name)
        
        # 사용자 친화적 형태로 변환
        summary = analysis_result.get("relationship_summary", {})
        validation = analysis_result.get("validation_summary", {})
        cycles = analysis_result.get("cycle_analysis", {})
        graph = analysis_result.get("graph_summary", {})
        recommendations = analysis_result.get("recommendations", [])
        
        # 건강성 점수 계산 (0-100)
        health_score = 100
        if validation.get("errors", 0) > 0:
            health_score -= validation["errors"] * 10
        if cycles.get("critical_cycles", 0) > 0:
            health_score -= cycles["critical_cycles"] * 15
        if validation.get("warnings", 0) > 0:
            health_score -= validation["warnings"] * 2
        health_score = max(0, min(100, health_score))
        
        # 건강성 등급 결정
        if health_score >= 90:
            health_grade = "Excellent"
            health_color = "green"
        elif health_score >= 70:
            health_grade = "Good"
            health_color = "blue"
        elif health_score >= 50:
            health_grade = "Fair"
            health_color = "yellow"
        else:
            health_grade = "Poor"
            health_color = "red"
        
        return {
            "status": "success",
            "message": "관계 네트워크 분석이 완료되었습니다",
            "network_health": {
                "score": health_score,
                "grade": health_grade,
                "color": health_color,
                "description": f"네트워크 건강성이 {health_grade.lower()} 상태입니다"
            },
            "statistics": {
                "total_ontologies": analysis_result.get("ontology_count", 0),
                "total_relationships": summary.get("total_relationships", 0),
                "relationship_types": len(graph.get("relationship_types", [])),
                "total_entities": graph.get("total_entities", 0),
                "average_connections": round(graph.get("average_connections_per_entity", 0), 2)
            },
            "quality_metrics": {
                "validation_errors": validation.get("errors", 0),
                "validation_warnings": validation.get("warnings", 0),
                "critical_cycles": cycles.get("critical_cycles", 0),
                "total_cycles": cycles.get("total_cycles", 0),
                "inverse_coverage": summary.get("inverse_coverage", "0/0 (0%)")
            },
            "recommendations": [
                {
                    "priority": "high" if "❌" in rec else "medium" if "⚠️" in rec else "low",
                    "message": rec.replace("❌ ", "").replace("⚠️ ", "").replace("📝 ", "").replace("🔄 ", "")
                }
                for rec in recommendations
            ],
            "metadata": {
                "analysis_timestamp": analysis_result.get("analysis_timestamp"),
                "database": db_name,
                "language": lang
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze relationship network: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"관계 네트워크 분석 실패: {str(e)}"
        )


@router.get("/relationship-paths")
async def find_relationship_paths_bff(
    request: Request,
    db_name: str,
    start_entity: str,
    end_entity: Optional[str] = Query(None, description="목표 엔티티 (없으면 모든 도달 가능한 엔티티)"),
    max_depth: int = Query(3, ge=1, le=5, description="최대 탐색 깊이"),
    path_type: str = Query("shortest", description="경로 타입 (shortest, all, weighted, semantic)"),
    terminus: TerminusService = Depends(get_terminus_service),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """
    🔥 관계 경로 탐색 (BFF 레이어)
    
    엔티티 간의 관계 경로를 찾아 사용자 친화적 형태로 반환
    """
    lang = get_accept_language(request)
    
    try:
        # 레이블을 ID로 변환
        start_id = await mapper.get_class_id(db_name, start_entity, lang)
        if not start_id:
            start_id = start_entity
            
        end_id = None
        if end_entity:
            end_id = await mapper.get_class_id(db_name, end_entity, lang)
            if not end_id:
                end_id = end_entity
        
        # 경로 탐색 수행
        path_result = await terminus.find_relationship_paths(
            db_name=db_name,
            start_entity=start_id,
            end_entity=end_id,
            max_depth=max_depth,
            path_type=path_type
        )
        
        # ID를 레이블로 변환하여 사용자 친화적 결과 생성
        paths = path_result.get("paths", [])
        user_friendly_paths = []
        
        for path in paths:
            # 엔티티 ID들을 레이블로 변환
            entity_labels = []
            for entity_id in path.get("entities", []):
                label = await mapper.get_class_label(db_name, entity_id, lang)
                entity_labels.append(label or entity_id)
            
            user_friendly_paths.append({
                "start": entity_labels[0] if entity_labels else start_entity,
                "end": entity_labels[-1] if len(entity_labels) > 1 else entity_labels[0] if entity_labels else "",
                "path": " → ".join(entity_labels),
                "predicates": path.get("predicates", []),
                "length": path.get("length", 0),
                "weight": round(path.get("total_weight", 0), 2),
                "confidence": path.get("confidence", 1.0),
                "path_type": path.get("path_type", "unknown")
            })
        
        statistics = path_result.get("statistics", {})
        
        return {
            "status": "success", 
            "message": f"관계 경로 탐색이 완료되었습니다 ({len(user_friendly_paths)}개 경로 발견)",
            "query": {
                "start_entity": start_entity,
                "end_entity": end_entity,
                "max_depth": max_depth,
                "path_type": path_type
            },
            "paths": user_friendly_paths[:10],  # 최대 10개만 반환
            "statistics": {
                "total_paths_found": len(paths),
                "displayed_paths": min(len(user_friendly_paths), 10),
                "average_length": statistics.get("average_length", 0),
                "shortest_path_length": statistics.get("min_length", 0),
                "longest_path_length": statistics.get("max_length", 0)
            },
            "metadata": {
                "language": lang,
                "start_id": start_id,
                "end_id": end_id
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to find relationship paths: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"관계 경로 탐색 실패: {str(e)}"
        )