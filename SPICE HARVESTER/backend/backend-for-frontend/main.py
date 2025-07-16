"""
BFF (Backend for Frontend) Service
사용자 친화적인 레이블 기반 온톨로지 관리 서비스
"""

from fastapi import FastAPI, HTTPException, status, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional, Any
import logging
from contextlib import asynccontextmanager
import sys
import os

# shared 모델 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.ontology import (
    OntologyCreateRequest,
    OntologyUpdateRequest,
    OntologyResponse,
    QueryRequest,
    QueryResponse
)
from models.common import BaseResponse

# BFF 서비스 import
from services.oms_client import OMSClient
# utils 디렉토리를 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))
from label_mapper import LabelMapper

# 의존성 import
from dependencies import get_terminus_service, get_jsonld_converter, get_label_mapper, set_oms_client
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
    oms_client = OMSClient("http://localhost:8001")
    label_mapper = LabelMapper()
    
    # dependencies에 OMS 클라이언트 설정
    set_oms_client(oms_client)
    
    try:
        # OMS 서비스 연결 테스트
        is_healthy = await oms_client.check_health()
        if is_healthy:
            logger.info("OMS 서비스 연결 성공")
        else:
            logger.warning("OMS 서비스 연결 실패 - 서비스는 계속 시작됩니다")
    except Exception as e:
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
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 의존성 주입
def get_oms_client() -> OMSClient:
    """OMS 클라이언트 의존성"""
    if not oms_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OMS 클라이언트가 초기화되지 않았습니다"
        )
    return oms_client


def get_label_mapper() -> LabelMapper:
    """Label Mapper 의존성"""
    if not label_mapper:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Label Mapper가 초기화되지 않았습니다"
        )
    return label_mapper


def get_accept_language(request: Request) -> str:
    """요청 헤더에서 언어 추출"""
    accept_language = request.headers.get("Accept-Language", "ko")
    # 첫 번째 언어만 추출 (간단한 구현)
    return accept_language.split(",")[0].split("-")[0]


# 에러 핸들러
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"예상치 못한 오류 발생: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "message": "내부 서버 오류가 발생했습니다"}
    )


# API 엔드포인트
@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "BFF (Backend for Frontend) Service",
        "version": "1.0.0",
        "description": "사용자 친화적인 레이블 기반 온톨로지 관리 서비스",
        "features": [
            "사용자 친화적 레이블 기반 API",
            "다국어 레이블 지원",
            "레이블 기반 쿼리",
            "OMS 서비스 연동"
        ]
    }


@app.get("/health")
async def health_check(
    oms: OMSClient = Depends(get_oms_client)
):
    """헬스 체크"""
    try:
        is_oms_connected = await oms.check_health()
        
        return {
            "status": "healthy" if is_oms_connected else "unhealthy",
            "service": "BFF",
            "oms_connected": is_oms_connected,
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"헬스 체크 실패: {e}")
        return {
            "status": "unhealthy",
            "service": "BFF",
            "oms_connected": False,
            "error": str(e)
        }


@app.get("/databases")
async def list_databases(
    terminus: TerminusService = Depends(get_terminus_service)
):
    """데이터베이스 목록 조회"""
    try:
        databases = await terminus.list_databases()
        return {
            "databases": databases,
            "count": len(databases)
        }
    except Exception as e:
        logger.error(f"Failed to list databases: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}")
async def create_database(
    db_name: str,
    description: Optional[str] = None,
    terminus: TerminusService = Depends(get_terminus_service)
):
    """데이터베이스 생성"""
    try:
        result = await terminus.create_database(db_name, description)
        return {
            "status": "success",
            "message": f"데이터베이스 '{db_name}'가 생성되었습니다",
            "data": result
        }
    except Exception as e:
        logger.error(f"Failed to create database: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/ontology", response_model=OntologyResponse)
async def create_ontology(
    db_name: str,
    ontology_data: OntologyCreateRequest,
    request: Request,
    oms: OMSClient = Depends(get_oms_client),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """온톨로지 클래스 생성"""
    lang = get_accept_language(request)
    
    try:
        # Label 매핑 등록
        await mapper.register_class(
            db_name=db_name,
            class_id=ontology_data.id,
            label=ontology_data.label,
            description=ontology_data.description
        )
        
        # 속성 매핑 등록
        for prop in ontology_data.properties:
            await mapper.register_property(
                db_name=db_name,
                class_id=ontology_data.id,
                property_id=prop.name,
                label=prop.label
            )
        
        # 관계 매핑 등록
        for rel in ontology_data.relationships:
            await mapper.register_relationship(
                db_name=db_name,
                predicate=rel.predicate,
                label=rel.label
            )
        
        # OMS를 통해 온톨로지 생성
        result = await oms.create_ontology(db_name, ontology_data)
        
        # 응답 생성
        label_text = ontology_data.label
        if hasattr(label_text, 'get'):
            label_text = label_text.get(lang, fallback_chain=['ko', 'en'])
        
        # OMS 응답에서 필요한 정보 추출
        created_class_id = result.get("data", {}).get("class_id", ontology_data.id)
        
        response_data = {
            "id": created_class_id,
            "label": label_text,
            "description": ontology_data.description,
            "properties": ontology_data.properties,
            "relationships": ontology_data.relationships,
            "created_at": result.get("data", {}).get("created_at"),
            "oms_result": result  # 디버깅을 위해 OMS 원본 결과도 포함
        }
        
        return OntologyResponse(
            status="success",
            message=f"'{label_text}' 온톨로지가 생성되었습니다",
            data=response_data
        )
        
    except Exception as e:
        logger.error(f"Failed to create ontology: {e}")
        raise


@app.get("/database/{db_name}/ontology/{class_label}", response_model=OntologyResponse)
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
        
        # 레이블 정보 추가
        display_result = await mapper.convert_to_display(db_name, ontology, lang)
        
        return OntologyResponse(
            status="success",
            message=f"'{class_label}' 온톨로지를 조회했습니다",
            data=display_result
        )
        
    except Exception as e:
        logger.error(f"Failed to get ontology: {e}")
        raise


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
        
    except Exception as e:
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
        
    except Exception as e:
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
            except Exception as e:
                logger.warning(f"Failed to convert ontology {ontology.get('id', 'unknown')}: {e}")
                # 변환 실패 시 원본 데이터 사용
                display_results.append(ontology)
        
        return {
            "ontologies": display_results,
            "count": len(display_results),
            "class_type": class_type
        }
        
    except Exception as e:
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
    except Exception as e:
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
        
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
        # TODO: OMS 브랜치 API 구현 필요
        branches = []
        return {
            "branches": branches,
            "count": len(branches)
        }
    except Exception as e:
        logger.error(f"Failed to list branches: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/branch")
async def create_branch(
    db_name: str,
    branch_info: Dict[str, Any],
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    새 브랜치 생성
    
    Body:
    {
        "branch_name": "feature-new-properties",
        "from_branch": "main"  # optional
    }
    """
    # RBAC 검사 (향후 구현)
    # TODO: 사용자 권한 확인
    # - 브랜치 생성 권한 확인
    # - 특정 네이밍 규칙 적용 (예: feature/*, hotfix/*)
    
    try:
        branch_name = branch_info.get("branch_name")
        from_branch = branch_info.get("from_branch")
        
        if not branch_name:
            raise ValueError("branch_name은 필수입니다")
        
        result = await terminus.create_branch(db_name, branch_name, from_branch)
        
        return {
            "status": "success",
            "message": f"브랜치 '{branch_name}'가 생성되었습니다",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
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
    except Exception as e:
        logger.error(f"Failed to delete branch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/checkout")
async def checkout(
    db_name: str,
    checkout_info: Dict[str, Any],
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    브랜치 또는 커밋으로 체크아웃
    
    Body:
    {
        "target": "feature-color",  # branch name or commit id
        "type": "branch"  # "branch" or "commit"
    }
    """
    try:
        target = checkout_info.get("target")
        target_type = checkout_info.get("type", "branch")
        
        if not target:
            raise ValueError("target은 필수입니다")
        
        result = await terminus.checkout(db_name, target, target_type)
        
        return {
            "status": "success",
            "message": f"{target_type} '{target}'로 체크아웃했습니다",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to checkout: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/commit")
async def commit_changes(
    db_name: str,
    commit_info: Dict[str, Any],
    terminus: TerminusService = Depends(get_terminus_service)
):
    """
    현재 변경사항 커밋
    
    Body:
    {
        "message": "속성 추가: 제품 색상 및 크기",
        "author": "user@example.com",
        "branch": "feature-color"  # optional
    }
    """
    # RBAC 검사 (향후 구현)
    # TODO: 커밋 권한 확인
    # - 보호된 브랜치(main, production)에 대한 직접 커밋 방지
    # - 브랜치별 커밋 권한 확인
    
    try:
        message = commit_info.get("message")
        author = commit_info.get("author")
        branch = commit_info.get("branch")
        
        if not message:
            raise ValueError("커밋 메시지는 필수입니다")
        if not author:
            raise ValueError("작성자 정보는 필수입니다")
        
        result = await terminus.commit_changes(db_name, message, author, branch)
        
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        logger.error(f"Failed to get diff: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/merge")
async def merge_branches(
    db_name: str,
    merge_info: Dict[str, Any],
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
        source = merge_info.get("source_branch")
        target = merge_info.get("target_branch")
        strategy = merge_info.get("strategy", "merge")
        message = merge_info.get("message")
        author = merge_info.get("author")
        
        if not source or not target:
            raise ValueError("source_branch와 target_branch는 필수입니다")
        
        result = await terminus.merge_branches(
            db_name, source, target, strategy, message, author
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
    except Exception as e:
        logger.error(f"Failed to merge branches: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/database/{db_name}/rollback")
async def rollback(
    db_name: str,
    rollback_info: Dict[str, Any],
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
        target_commit = rollback_info.get("target_commit")
        create_branch = rollback_info.get("create_branch", True)
        branch_name = rollback_info.get("branch_name")
        
        if not target_commit:
            raise ValueError("target_commit은 필수입니다")
        
        result = await terminus.rollback(
            db_name, target_commit, create_branch, branch_name
        )
        
        return {
            "status": "success",
            "message": f"커밋 '{target_commit}'로 롤백했습니다",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to rollback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_level="info"
    )