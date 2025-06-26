"""
OMS 간단한 실행 가능 버전
복잡한 의존성 없이 핵심 기능만 구현
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === 도메인 모델 ===
class ObjectTypeCreate(BaseModel):
    name: str
    displayName: Optional[str] = None
    description: Optional[str] = None
    properties: List[Dict] = []

class PropertyCreate(BaseModel):
    name: str
    displayName: Optional[str] = None
    dataType: str
    isRequired: bool = False
    description: Optional[str] = None

class ValidationRequest(BaseModel):
    sourceObject: Dict
    targetObject: Dict
    branch: str = "main"

# === 간단한 서비스 구현 ===
class SimpleSchemaService:
    """스키마 관리 서비스 - 메모리 기반"""
    def __init__(self):
        self.schemas = {}  # branch -> {name -> schema}
    
    def create_object_type(self, branch: str, obj_type: ObjectTypeCreate):
        if branch not in self.schemas:
            self.schemas[branch] = {}
        
        if obj_type.name in self.schemas[branch]:
            raise ValueError(f"ObjectType {obj_type.name} already exists")
        
        schema = {
            "name": obj_type.name,
            "displayName": obj_type.displayName or obj_type.name,
            "description": obj_type.description,
            "properties": obj_type.properties,
            "branch": branch
        }
        self.schemas[branch][obj_type.name] = schema
        return schema
    
    def get_object_types(self, branch: str):
        return list(self.schemas.get(branch, {}).values())
    
    def get_object_type(self, branch: str, name: str):
        if branch not in self.schemas or name not in self.schemas[branch]:
            return None
        return self.schemas[branch][name]

class SimpleValidationService:
    """검증 서비스 - Breaking Change 감지"""
    def validate(self, request: ValidationRequest):
        source = request.sourceObject
        target = request.targetObject
        breaking_changes = []
        
        # 1. 필수 속성 제거 검사
        source_props = {p['name']: p for p in source.get('properties', [])}
        target_props = {p['name']: p for p in target.get('properties', [])}
        
        for prop_name, prop in source_props.items():
            if prop.get('isRequired') and prop_name not in target_props:
                breaking_changes.append({
                    "type": "required_property_removed",
                    "severity": "critical",
                    "property": prop_name,
                    "message": f"Required property '{prop_name}' was removed"
                })
        
        # 2. 타입 변경 검사
        for prop_name in source_props:
            if prop_name in target_props:
                source_type = source_props[prop_name].get('dataType')
                target_type = target_props[prop_name].get('dataType')
                if source_type != target_type:
                    breaking_changes.append({
                        "type": "type_changed",
                        "severity": "high",
                        "property": prop_name,
                        "from": source_type,
                        "to": target_type,
                        "message": f"Property '{prop_name}' type changed from {source_type} to {target_type}"
                    })
        
        return {
            "isValid": len(breaking_changes) == 0,
            "breakingChanges": breaking_changes,
            "hasBreakingChanges": len(breaking_changes) > 0
        }

# === 전역 서비스 인스턴스 ===
schema_service = SimpleSchemaService()
validation_service = SimpleValidationService()

# === FastAPI 앱 ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("OMS Simple starting up...")
    yield
    logger.info("OMS Simple shutting down...")

app = FastAPI(
    title="OMS Simple",
    version="1.0.0",
    description="Ontology Management System - Simple Working Version",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === API 엔드포인트 ===
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "type": "simple"
    }

@app.post("/api/v1/schemas/{branch}/object-types")
async def create_object_type(branch: str, obj_type: ObjectTypeCreate):
    """ObjectType 생성"""
    try:
        result = schema_service.create_object_type(branch, obj_type)
        return result
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.get("/api/v1/schemas/{branch}/object-types")
async def get_object_types(branch: str):
    """ObjectType 목록 조회"""
    return {
        "objectTypes": schema_service.get_object_types(branch),
        "branch": branch
    }

@app.get("/api/v1/schemas/{branch}/object-types/{name}")
async def get_object_type(branch: str, name: str):
    """특정 ObjectType 조회"""
    obj_type = schema_service.get_object_type(branch, name)
    if not obj_type:
        raise HTTPException(status_code=404, detail="ObjectType not found")
    return obj_type

@app.post("/api/v1/validation/breaking-changes")
async def validate_breaking_changes(request: ValidationRequest):
    """Breaking Change 검증"""
    result = validation_service.validate(request)
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8889)