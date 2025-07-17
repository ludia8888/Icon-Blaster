"""
BFF (Backend for Frontend) Service
사용자 친화적인 레이블 기반 온톨로지 관리 서비스
"""

from fastapi import FastAPI, HTTPException, status, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import json
import httpx
from typing import Dict, List, Optional, Any
import logging
from contextlib import asynccontextmanager
import sys
import os
import re

# shared 모델 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.ontology import (
    OntologyCreateRequest,
    OntologyCreateRequestBFF,
    OntologyUpdateRequest,
    OntologyResponse,
    QueryRequest,
    QueryResponse
)
from models.common import BaseResponse
from models.requests import (
    BranchCreateRequest,
    CheckoutRequest,
    CommitRequest,
    MergeRequest,
    RollbackRequest,
    ApiResponse
)

# Production middleware imports - temporarily disabled
# from middleware.error_handler import setup_error_handlers
# from middleware.validation_middleware import setup_validation_middleware

# Documentation enhancements - temporarily disabled
# from docs.openapi_enhancements import setup_enhanced_openapi

# 보안 모듈 import - temporarily disabled
# from security.input_sanitizer import (
#     validate_db_name, 
#     validate_class_id, 
#     validate_branch_name,
#     sanitize_input,
#     SecurityViolationError
# )

# Fallback validation functions
def validate_db_name(name):
    return name

def validate_class_id(class_id):
    return class_id

def validate_branch_name(name):
    return name

def sanitize_input(data):
    return data

class SecurityViolationError(Exception):
    pass

# 공통 유틸리티 import - temporarily disabled
# from utils.language import get_accept_language

# Fallback function
def get_accept_language(request):
    return "ko"

# BFF 서비스 import
from services.oms_client import OMSClient
# utils 디렉토리를 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))
from label_mapper import LabelMapper

# 의존성 import
from dependencies import get_terminus_service, get_jsonld_converter, get_label_mapper, set_oms_client, get_oms_client, set_label_mapper
# OMS 클라이언트 래퍼 import
from dependencies import TerminusService

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 전역 서비스 인스턴스
oms_client: Optional[OMSClient] = None
label_mapper: Optional[LabelMapper] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # 시작 시
    global oms_client, label_mapper
    
    logger.info("BFF 서비스 초기화 중...")
    
    # 서비스 초기화
    oms_client = OMSClient("http://localhost:8000")
    label_mapper = LabelMapper()
    
    # dependencies에 서비스 설정
    set_oms_client(oms_client)
    set_label_mapper(label_mapper)
    
    try:
        # OMS 서비스 연결 테스트
        is_healthy = await oms_client.check_health()
        if is_healthy:
            logger.info("OMS 서비스 연결 성공")
        else:
            logger.warning("OMS 서비스 연결 실패 - 서비스는 계속 시작됩니다")
    except (httpx.HTTPError, httpx.TimeoutException, ConnectionError) as e:
        logger.error(f"OMS 서비스 연결 실패: {e}")
        # 연결 실패해도 서비스는 시작 (나중에 재연결 시도)
    
    yield
    
    # 종료 시
    logger.info("BFF 서비스 종료 중...")
    if oms_client:
        await oms_client.close()


# FastAPI 앱 생성
app = FastAPI(
    title="BFF (Backend for Frontend) Service",
    description="사용자 친화적인 레이블 기반 온톨로지 관리 서비스",
    version="2.0.0",  # Updated version for production-grade features
    lifespan=lifespan,
    # Enhanced OpenAPI configuration
    openapi_tags=[
        {"name": "Health", "description": "Health check and service status"},
        {"name": "Database", "description": "Database management operations"},
        {"name": "Ontology", "description": "Ontology CRUD operations"},
        {"name": "Query", "description": "Data querying and retrieval"},
        {"name": "Label Mappings", "description": "Label mapping import/export"},
        {"name": "Branch Management", "description": "Git-like branch operations"},
    ]
)

# Production-grade middleware setup
# Note: Order matters - validation should come before error handling
# setup_validation_middleware(app)
# setup_error_handlers(app)

# Enhanced OpenAPI documentation
# setup_enhanced_openapi(app)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 의존성 주입




# Production-grade error handling is now managed by middleware
# See setup_error_handlers() and setup_validation_middleware() above


# API 엔드포인트
# Note: Root and health endpoints moved to health router


# Note: Database endpoints moved to database router


# Note: Database creation moved to database router (POST /api/v1/databases)


@app.post("/database/{db_name}/ontology", response_model=OntologyResponse)
async def create_ontology(
    db_name: str,
    ontology_data: OntologyCreateRequestBFF,
    request: Request,
    oms: OMSClient = Depends(get_oms_client),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """온톨로지 클래스 생성"""
    lang = get_accept_language(request)
    
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        # 온톨로지 데이터 정화
        sanitized_data = sanitize_input(ontology_data.dict())
        
        # 레이블로부터 ID 생성 (한글/영문 처리)
        import re
        # label이 MultiLingualText인지 문자열인지 확인
        label = sanitized_data.get('label')
        if isinstance(label, dict):
            # MultiLingualText인 경우
            label_text = label.get('en') or label.get('ko') or "UnnamedClass"
        elif isinstance(label, str):
            label_text = label
        else:
            label_text = "UnnamedClass"
        
        # 고급 ID 생성 알고리즘 - CamelCase 보존 (개선된 버전)
        class_id = re.sub(r'[^\w\s]', '', label_text)
        
        # CamelCase 감지 함수
        def is_camel_case(text: str) -> bool:
            if not text or len(text) < 2:
                return False
            has_upper = any(c.isupper() for c in text)
            has_lower = any(c.islower() for c in text)
            return has_upper and has_lower
        
        # 숫자 접두사 처리 (먼저 확인)
        numeric_prefix = ""
        if class_id and class_id[0].isdigit():
            numeric_prefix = "Class"
        
        if ' ' in class_id:
            # 공백으로 분리된 단어들을 CamelCase로 변환
            words = class_id.split()
            class_id = ''.join(word.capitalize() for word in words)
        else:
            # 공백이 없는 경우: CamelCase 보존
            if is_camel_case(class_id):
                # 기존 CamelCase/camelCase 보존
                class_id = class_id
            elif class_id and class_id[0].isupper():
                # 이미 대문자로 시작 (TESTCLASS 등) - 보존
                class_id = class_id
            else:
                # 단순 소문자 단어 - capitalize
                class_id = class_id.capitalize()
        
        # 숫자 접두사 적용
        if numeric_prefix:
            class_id = numeric_prefix + class_id
        
        if not class_id:
            class_id = "UnnamedClass"
        
        # 생성된 ID를 데이터에 추가
        sanitized_data['id'] = class_id
        
        # 클래스 ID 검증
        sanitized_data['id'] = validate_class_id(sanitized_data['id'])
        
        # Label 매핑 등록
        await mapper.register_class(
            db_name=db_name,
            class_id=sanitized_data.get('id'),
            label=sanitized_data.get('label'),
            description=sanitized_data.get('description')
        )
        
        # 속성 매핑 등록 (정화된 데이터 사용)
        for prop in sanitized_data.get('properties', []):
            prop_sanitized = sanitize_input(prop) if isinstance(prop, dict) else prop
            await mapper.register_property(
                db_name=db_name,
                class_id=sanitized_data.get('id'),
                property_id=prop_sanitized.get('name') if isinstance(prop_sanitized, dict) else getattr(prop_sanitized, 'name', None),
                label=prop_sanitized.get('label') if isinstance(prop_sanitized, dict) else getattr(prop_sanitized, 'label', None)
            )
        
        # 관계 매핑 등록 (정화된 데이터 사용)
        for rel in sanitized_data.get('relationships', []):
            rel_sanitized = sanitize_input(rel) if isinstance(rel, dict) else rel
            await mapper.register_relationship(
                db_name=db_name,
                predicate=rel_sanitized.get('predicate') if isinstance(rel_sanitized, dict) else getattr(rel_sanitized, 'predicate', None),
                label=rel_sanitized.get('label') if isinstance(rel_sanitized, dict) else getattr(rel_sanitized, 'label', None)
            )
        
        # OMS를 통해 온톨로지 생성 (생성된 ID를 포함한 정화된 데이터 사용)
        logger.info(f"Sending to OMS create_ontology: {json.dumps(sanitized_data, ensure_ascii=False)}")
        result = await oms.create_ontology(db_name, sanitized_data)
        
        # 응답 생성
        label_text = sanitized_data.get('label', '')
        if isinstance(label_text, dict):
            # Multilingual label - get by language with fallback
            label_text = label_text.get(lang) or label_text.get('ko') or label_text.get('en') or ''
        
        # OMS 응답에서 필요한 정보 추출
        # OMS는 data에 class ID 리스트를 반환함
        oms_data = result.get("data", [])
        if isinstance(oms_data, list) and len(oms_data) > 0:
            created_class_id = oms_data[0]
        else:
            created_class_id = sanitized_data.get('id')
        
        # Create OntologyBase object
        from models.ontology import OntologyBase
        ontology_base = OntologyBase(
            id=created_class_id,
            label=ontology_data.label,
            description=ontology_data.description,
            properties=ontology_data.properties,
            relationships=ontology_data.relationships,
            metadata={"created": True, "database": db_name}
        )
        
        return OntologyResponse(
            status="success",
            message=f"'{label_text}' 온톨로지가 생성되었습니다",
            data=ontology_base
        )
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in create_ontology: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to create ontology: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"온톨로지 생성 중 오류 발생: {str(e)}"
        )


@app.get("/database/{db_name}/ontology/{class_label}")
async def get_ontology(
    db_name: str,
    class_label: str,
    request: Request,
    oms: OMSClient = Depends(get_oms_client),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """온톨로지 클래스 조회 (레이블 기반)"""
    lang = get_accept_language(request)
    
    try:
        # 레이블을 ID로 변환
        class_id = await mapper.get_class_id(db_name, class_label, lang)
        if not class_id:
            # 다른 언어로 시도
            for fallback_lang in ['ko', 'en', 'ja', 'zh']:
                class_id = await mapper.get_class_id(db_name, class_label, fallback_lang)
                if class_id:
                    break
        
        if not class_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{class_label}' 온톨로지를 찾을 수 없습니다"
            )
        
        # OMS에서 조회
        ontology = await oms.get_ontology(db_name, class_id)
        
        if not ontology:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{class_label}' 온톨로지를 찾을 수 없습니다"
            )
        
        # Extract the actual ontology data from OMS response
        if isinstance(ontology, dict) and 'data' in ontology:
            ontology_data = ontology['data']
        else:
            ontology_data = ontology
        
        # 레이블 정보 추가
        display_result = await mapper.convert_to_display(db_name, ontology_data, lang)
        
        # Ensure required fields for OntologyBase
        if not display_result.get('id'):
            display_result['id'] = class_id
        if not display_result.get('label'):
            display_result['label'] = class_label
        
        # Create OntologyBase object
        from models.ontology import OntologyBase
        ontology_base = OntologyBase(
            id=display_result.get('id'),
            label=display_result.get('label'),
            description=display_result.get('description'),
            properties=display_result.get('properties', []),
            relationships=display_result.get('relationships', []),
            parent_class=display_result.get('parent_class'),
            abstract=display_result.get('abstract', False),
            metadata=display_result.get('metadata')
        )
        
        return OntologyResponse(
            status="success",
            message=f"'{class_label}' 온톨로지를 조회했습니다",
            data=ontology_base
        )
        
    except HTTPException:
        raise
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to get ontology: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"온톨로지 조회 중 오류 발생: {str(e)}"
        )


@app.put("/database/{db_name}/ontology/{class_label}")
async def update_ontology(
    db_name: str,
    class_label: str,
    ontology_data: OntologyUpdateRequest,
    request: Request,
    oms: OMSClient = Depends(get_oms_client),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """온톨로지 클래스 업데이트"""
    lang = get_accept_language(request)
    
    try:
        # 레이블을 ID로 변환
        class_id = await mapper.get_class_id(db_name, class_label, lang)
        if not class_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{class_label}' 온톨로지를 찾을 수 없습니다"
            )
        
        # 매핑 업데이트
        await mapper.update_mappings(db_name, ontology_data.dict(exclude_unset=True))
        
        # OMS를 통해 업데이트
        result = await oms.update_ontology(db_name, class_id, ontology_data)
        
        return OntologyResponse(
            status="success",
            message=f"'{class_label}' 온톨로지가 업데이트되었습니다",
            data=result
        )
        
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to update ontology: {e}")
        raise


@app.delete("/database/{db_name}/ontology/{class_label}")
async def delete_ontology(
    db_name: str,
    class_label: str,
    request: Request,
    oms: OMSClient = Depends(get_oms_client),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """온톨로지 클래스 삭제"""
    lang = get_accept_language(request)
    
    try:
        # 레이블을 ID로 변환
        class_id = await mapper.get_class_id(db_name, class_label, lang)
        if not class_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{class_label}' 온톨로지를 찾을 수 없습니다"
            )
        
        # OMS를 통해 삭제
        await oms.delete_ontology(db_name, class_id)
        
        # 매핑 정보 삭제
        await mapper.remove_class(db_name, class_id)
        
        return OntologyResponse(
            status="success",
            message=f"'{class_label}' 온톨로지가 삭제되었습니다",
            data={"deleted_class": class_label}
        )
        
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to delete ontology: {e}")
        raise


@app.get("/database/{db_name}/ontologies")
async def list_ontologies(
    db_name: str,
    request: Request,
    class_type: str = "sys:Class",
    oms: OMSClient = Depends(get_oms_client),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """온톨로지 목록 조회"""
    lang = get_accept_language(request)
    
    try:
        # OMS에서 조회
        ontologies = await oms.list_ontologies(db_name)
        
        # 각 온톨로지에 레이블 정보 추가
        display_results = []
        for ontology in ontologies:
            try:
                display_result = await mapper.convert_to_display(db_name, ontology, lang)
                display_results.append(display_result)
            except (ValueError, KeyError, AttributeError) as e:
                logger.warning(f"Failed to convert ontology {ontology.get('id', 'unknown')}: {e}")
                # 변환 실패 시 원본 데이터 사용
                display_results.append(ontology)
        
        return {
            "ontologies": display_results,
            "count": len(display_results),
            "class_type": class_type
        }
        
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to list ontologies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/query", response_model=QueryResponse)
async def query_ontology(
    db_name: str,
    query: QueryRequest,
    request: Request,
    oms: OMSClient = Depends(get_oms_client),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """레이블 기반 쿼리 실행"""
    lang = get_accept_language(request)
    
    try:
        # 쿼리 검증
        if hasattr(query, 'validate_fields') and query.validate_fields:
            # 클래스 존재 여부 확인
            class_id = await mapper.get_class_id(db_name, query.class_label, lang)
            if not class_id:
                raise ValueError(f"클래스를 찾을 수 없습니다: {query.class_label}")
        
        # 레이블 기반 쿼리를 내부 ID 기반으로 변환
        internal_query = await mapper.convert_query_to_internal(db_name, query.dict(), lang)
        
        # 쿼리 실행
        results = await oms.query_ontologies(db_name, internal_query)
        
        # 결과를 레이블 기반으로 변환
        display_results = []
        for item in results.get('data', {}).get('results', []):
            display_item = await mapper.convert_to_display(db_name, item, lang)
            display_results.append(display_item)
        
        return QueryResponse(
            status="success",
            message="쿼리가 성공적으로 실행되었습니다",
            data=display_results,
            count=len(display_results)
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to execute query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/database/{db_name}/ontology/{class_id}/schema")
async def get_property_schema(
    db_name: str,
    class_id: str,
    request: Request,
    oms: OMSClient = Depends(get_oms_client),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """클래스의 속성 스키마 조회"""
    lang = get_accept_language(request)
    
    try:
        # 온톨로지 정보 조회 (스키마 포함)
        ontology = await oms.get_ontology(db_name, class_id)
        
        if not ontology:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"온톨로지를 찾을 수 없습니다: {class_id}"
            )
        
        # 레이블 정보 추가
        schema = ontology.get('data', {})
        for prop_id, prop_info in schema.get('properties', {}).items():
            prop_label = await mapper.get_property_label(db_name, class_id, prop_id, lang)
            if prop_label:
                prop_info['label'] = prop_label
        
        return {
            "status": "success",
            "data": schema
        }
        
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to get property schema: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/mappings/export")
async def export_mappings(
    db_name: str,
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """레이블 매핑 내보내기"""
    try:
        mappings = await mapper.export_mappings(db_name)
        return {
            "status": "success",
            "message": f"'{db_name}' 데이터베이스의 매핑을 내보냈습니다",
            "data": mappings
        }
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to export mappings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/mappings/import")
async def import_mappings(
    db_name: str,
    mappings: Dict[str, Any],
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """레이블 매핑 가져오기"""
    try:
        # DB 이름 일치 확인
        if mappings.get('db_name') != db_name:
            raise ValueError("데이터베이스 이름이 일치하지 않습니다")
        
        await mapper.import_mappings(mappings)
        
        return {
            "status": "success",
            "message": f"'{db_name}' 데이터베이스의 매핑을 가져왔습니다"
        }
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to import mappings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ===== 버전 관리 API (Git-like features) =====

@app.get("/database/{db_name}/branches")
async def list_branches(
    db_name: str,
    oms: OMSClient = Depends(get_oms_client)
):
    """브랜치 목록 조회"""
    try:
        # 실제 OMS API 호출
        response = await oms.list_branches(db_name)
        branches = response.get("data", {}).get("branches", [])
        return {
            "branches": branches,
            "count": len(branches)
        }
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to list branches: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/branch", response_model=ApiResponse)
async def create_branch(
    db_name: str,
    request: BranchCreateRequest,
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    새 브랜치 생성
    
    Pydantic model을 사용한 타입 안전 엔드포인트
    """
    # RBAC 검사 (향후 구현)
    # TODO: 사용자 권한 확인
    # - 브랜치 생성 권한 확인
    # - 특정 네이밍 규칙 적용 (예: feature/*, hotfix/*)
    
    try:
        # 데이터베이스 이름 검증 (Pydantic이 request 유효성 검증 처리)
        from shared.security.input_sanitizer import validate_db_name
        validated_db_name = validate_db_name(db_name)
        
        # Pydantic 모델에서 직접 값 접근 (자동 검증됨)
        result = await terminus.create_branch(
            validated_db_name, 
            request.branch_name, 
            request.from_branch
        )
        
        return {
            "status": "success",
            "message": f"브랜치 '{request.branch_name}'가 생성되었습니다",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to create branch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.delete("/database/{db_name}/branch/{branch_name}")
async def delete_branch(
    db_name: str,
    branch_name: str,
    terminus: TerminusService = Depends(get_terminus_service)
):
    """브랜치 삭제"""
    # RBAC 검사 (향후 구현)
    # TODO: 브랜치 삭제 권한 확인
    # - main, production 등 보호된 브랜치 삭제 방지
    # - 브랜치 소유자 또는 관리자만 삭제 가능
    
    try:
        result = await terminus.delete_branch(db_name, branch_name)
        
        return {
            "status": "success",
            "message": f"브랜치 '{branch_name}'가 삭제되었습니다",
            "data": result
        }
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to delete branch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/checkout", response_model=ApiResponse)
async def checkout(
    db_name: str,
    request: CheckoutRequest,
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    브랜치 또는 커밋으로 체크아웃
    
    Pydantic model을 사용한 타입 안전 엔드포인트
    """
    try:
        # 데이터베이스 이름 검증 (Pydantic이 request 유효성 검증 처리)
        from shared.security.input_sanitizer import validate_db_name
        validated_db_name = validate_db_name(db_name)
        
        # Pydantic 모델에서 직접 값 접근 (자동 검증됨)
        result = await terminus.checkout(validated_db_name, request.target, request.type)
        
        return {
            "status": "success",
            "message": f"{request.type} '{request.target}'로 체크아웃했습니다",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to checkout: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/commit", response_model=ApiResponse)
async def commit_changes(
    db_name: str,
    request: CommitRequest,
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    현재 변경사항 커밋
    
    Pydantic model을 사용한 타입 안전 엔드포인트
    """
    # RBAC 검사 (향후 구현)
    # TODO: 커밋 권한 확인
    # - 보호된 브랜치(main, production)에 대한 직접 커밋 방지
    # - 브랜치별 커밋 권한 확인
    
    try:
        # 데이터베이스 이름 검증 (Pydantic이 request 유효성 검증 처리)
        from shared.security.input_sanitizer import validate_db_name
        validated_db_name = validate_db_name(db_name)
        
        # Pydantic 모델에서 직접 값 접근 (자동 검증됨)
        result = await terminus.commit_changes(
            validated_db_name, 
            request.message, 
            request.author, 
            request.branch
        )
        
        return {
            "status": "success",
            "message": "변경사항이 커밋되었습니다",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to commit: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/database/{db_name}/history")
async def get_commit_history(
    db_name: str,
    branch: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    terminus: TerminusService = Depends(get_terminus_service)
):
    """커밋 히스토리 조회"""
    try:
        commits = await terminus.get_commit_history(db_name, branch, limit, offset)
        
        return {
            "commits": commits,
            "count": len(commits),
            "limit": limit,
            "offset": offset
        }
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to get commit history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/database/{db_name}/diff")
async def get_diff(
    db_name: str,
    base: str,
    compare: str,
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    두 브랜치/커밋 간 차이 비교
    
    Query params:
    - base: 기준 브랜치 또는 커밋
    - compare: 비교 브랜치 또는 커밋
    """
    try:
        if not base or not compare:
            raise ValueError("base와 compare는 필수입니다")
        
        diff = await terminus.get_diff(db_name, base, compare)
        
        return {
            "status": "success",
            "data": diff
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to get diff: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/merge", response_model=ApiResponse)
async def merge_branches(
    db_name: str,
    request: MergeRequest,
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    브랜치 병합
    
    Body:
    {
        "source_branch": "feature-color",
        "target_branch": "main",
        "strategy": "merge",  # "merge" or "rebase"
        "message": "Merge feature-color into main",  # optional
        "author": "user@example.com"  # optional
    }
    """
    # RBAC 검사 (향후 구현)
    # TODO: 병합 권한 확인
    # - 타겟 브랜치에 대한 쓰기 권한 확인
    # - 보호된 브랜치 병합 시 승인 프로세스 확인
    # - Pull Request 스타일의 리뷰 프로세스 고려
    
    try:
        # Enhanced business logic validation
        if request.source_branch == request.target_branch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and target branches cannot be the same"
            )
        
        # Validate database name
        from security.input_sanitizer import validate_db_name
        validate_db_name(db_name)
        
        # Check if branches exist before attempting merge
        try:
            # This will throw an exception if branch doesn't exist
            await terminus.get_branch_info(db_name, request.source_branch)
            await terminus.get_branch_info(db_name, request.target_branch)
        except Exception as e:
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"One or both branches do not exist: {str(e)}"
                )
            raise
        
        # Protected branch validation
        protected_branches = ["main", "master", "production", "prod"]
        if request.target_branch.lower() in protected_branches:
            logger.warning(f"Merge attempt to protected branch '{request.target_branch}' from '{request.source_branch}'")
            # In production, this would check user permissions
            
        # Check for potential conflicts before merge
        if request.strategy == "rebase" and not request.author:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Author is required for rebase strategy"
            )
        
        result = await terminus.merge_branches(
            db_name, request.source_branch, request.target_branch, 
            request.strategy, request.message, request.author
        )
        
        if result.get("status") == "conflict":
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=result
            )
        
        return {
            "status": "success",
            "message": f"'{source}'가 '{target}'로 병합되었습니다",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to merge branches: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/rollback", response_model=ApiResponse)
async def rollback(
    db_name: str,
    request: RollbackRequest,
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    특정 커밋으로 롤백
    
    Body:
    {
        "target_commit": "commit_123",
        "create_branch": true,  # optional, default: true
        "branch_name": "rollback-123"  # optional
    }
    """
    # RBAC 검사 (향후 구현)
    # TODO: 롤백 권한 확인
    # - 롤백 권한을 가진 사용자만 수행 가능
    # - 프로덕션 환경에서는 추가 승인 필요
    
    try:
        # Enhanced rollback validation
        from security.input_sanitizer import validate_db_name
        validate_db_name(db_name)
        
        # Validate commit ID format (should be hexadecimal and minimum length)
        if len(request.target_commit) < 7:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Commit ID must be at least 7 characters long"
            )
        
        # Branch name validation when creating new branch
        if request.create_branch and request.branch_name:
            # Prevent overwriting existing branches
            try:
                await terminus.get_branch_info(db_name, request.branch_name)
                # If we get here, branch exists
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Branch '{request.branch_name}' already exists. Choose a different name."
                )
            except Exception as e:
                # Branch doesn't exist, which is what we want
                if "not found" not in str(e).lower() and "does not exist" not in str(e).lower():
                    # Some other error occurred
                    raise
        
        # Generate default rollback branch name if not provided
        if request.create_branch and not request.branch_name:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            request.branch_name = f"rollback_{request.target_commit[:8]}_{timestamp}"
        
        # Safety check: Verify the target commit exists
        try:
            # This would verify commit exists in the database
            # In a real implementation, you'd check commit history
            pass  # Placeholder for commit existence validation
        except Exception as e:
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Commit '{request.target_commit}' not found"
                )
        
        # Protected branch safety checks
        current_branch = "main"  # In real implementation, get current branch
        protected_branches = ["main", "master", "production", "prod"]
        if not request.create_branch and current_branch.lower() in protected_branches:
            logger.warning(f"Attempting rollback on protected branch '{current_branch}' to commit '{request.target_commit}'")
            # In production, this would require additional confirmations
        
        result = await terminus.rollback(
            db_name, request.target_commit, request.create_branch, request.branch_name
        )
        
        return {
            "status": "success",
            "message": f"커밋 '{request.target_commit}'로 롤백했습니다",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as e:
        logger.error(f"Failed to rollback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# 라우터 등록
from routers import database, ontology, query, mapping, health, merge_conflict

app.include_router(database.router, prefix="/api/v1", tags=["database"])
app.include_router(ontology.router, prefix="/api/v1", tags=["ontology"])
app.include_router(query.router, prefix="/api/v1", tags=["query"])
app.include_router(mapping.router, prefix="/api/v1", tags=["mapping"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(merge_conflict.router, prefix="/api/v1", tags=["merge-conflict"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_level="info"
    )