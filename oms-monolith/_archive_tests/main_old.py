"""
OMS Monolith Application
모든 서비스를 단일 애플리케이션으로 통합
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from pydantic import BaseModel

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 전역 인스턴스
redis_client: Optional[redis.Redis] = None
terminus_client = None  # 나중에 구현

# Pydantic 모델들
class UserContext(BaseModel):
    id: int
    username: str
    email: str
    roles: list[str]

class ObjectTypeCreate(BaseModel):
    name: str
    displayName: Optional[str] = None
    description: Optional[str] = None

class ObjectTypeUpdate(BaseModel):
    displayName: Optional[str] = None
    description: Optional[str] = None

class BranchCreate(BaseModel):
    name: str
    description: Optional[str] = None
    parentBranch: str = "main"

# 인증 시스템 (단순화)
async def get_current_user() -> UserContext:
    """현재 사용자 - 개발용 하드코딩"""
    return UserContext(
        id=1,
        username="admin",
        email="admin@example.com",
        roles=["admin"]
    )

def require_permission(permission: str):
    """권한 체크 데코레이터"""
    async def permission_checker(user: UserContext = Depends(get_current_user)):
        # 단순화: admin은 모든 권한
        if "admin" in user.roles:
            return user

        permission_map = {
            "schema:read": ["user", "developer", "admin"],
            "schema:write": ["developer", "admin"],
            "schema:delete": ["admin"],
            "branch:read": ["user", "developer", "admin"],
            "branch:write": ["developer", "admin"],
            "branch:merge": ["developer", "admin"],
        }

        allowed_roles = permission_map.get(permission, [])
        if any(role in user.roles for role in allowed_roles):
            return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission}"
        )
    return permission_checker

# 의존성
require_schema_read = require_permission("schema:read")
require_schema_write = require_permission("schema:write")
require_schema_delete = require_permission("schema:delete")
require_branch_read = require_permission("branch:read")
require_branch_write = require_permission("branch:write")
require_branch_merge = require_permission("branch:merge")

# 인메모리 저장소 (개발용)
class InMemoryStore:
    def __init__(self):
        self.object_types = {}  # branch -> {id -> object_type}
        self.branches = {"main": {"name": "main", "description": "Main branch"}}
        self.id_counter = 1000

    def generate_id(self) -> str:
        self.id_counter += 1
        return f"obj_{self.id_counter}"

store = InMemoryStore()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기"""
    global redis_client

    logger.info("OMS Monolith starting up...")

    # Redis 연결
    try:
        redis_client = redis.Redis.from_url("redis://localhost:6379", decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        redis_client = None

    yield

    # 정리
    logger.info("OMS Monolith shutting down...")
    if redis_client:
        await redis_client.close()

# FastAPI 앱
app = FastAPI(
    title="OMS Monolith",
    version="1.0.0",
    description="Ontology Management System - Monolithic Version",
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

# Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# === Health & Info ===
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "type": "monolith",
        "redis": redis_client is not None
    }

@app.get("/api/info")
async def api_info():
    return {
        "name": "OMS Monolith API",
        "version": "1.0.0",
        "endpoints": {
            "schemas": "/api/v1/schemas",
            "branches": "/api/v1/branches",
            "validation": "/api/v1/validation",
            "auth": "/api/v1/auth"
        }
    }

# === Authentication ===
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/v1/auth/login")
async def login(request: LoginRequest):
    """로그인 (단순화)"""
    if request.username == "admin" and request.password == "admin":
        return {
            "access_token": "fake-jwt-token",
            "token_type": "bearer",
            "user": {
                "id": 1,
                "username": "admin",
                "email": "admin@example.com",
                "roles": ["admin"]
            }
        }
    raise HTTPException(status_code=401, detail="Invalid credentials")

# === Schema Management ===
@app.get(
    "/api/v1/schemas/{branch:path}/object-types",
    responses={
        200: {"description": "성공"},
        401: {"description": "인증 필요"},
        403: {"description": "권한 없음"},
        404: {"description": "브랜치를 찾을 수 없음"}
    }
)
async def get_object_types(
    branch: str = "main",
    user: UserContext = Depends(require_schema_read)
):
    """ObjectType 목록 조회"""
    if branch not in store.branches:
        raise HTTPException(status_code=404, detail=f"Branch '{branch}' not found")

    branch_objects = store.object_types.get(branch, {})
    return {
        "object_types": list(branch_objects.values()),
        "count": len(branch_objects),
        "branch": branch
    }

@app.post("/api/v1/schemas/{branch:path}/object-types")
async def create_object_type(
    branch: str,
    obj_type: ObjectTypeCreate,
    user: UserContext = Depends(require_schema_write)
):
    """ObjectType 생성"""
    if branch not in store.branches:
        raise HTTPException(status_code=404, detail=f"Branch '{branch}' not found")

    # 중복 체크
    if branch in store.object_types:
        for existing in store.object_types[branch].values():
            if existing["name"] == obj_type.name:
                raise HTTPException(status_code=409, detail="ObjectType already exists")

    # 생성
    obj_id = store.generate_id()
    new_object = {
        "id": obj_id,
        "name": obj_type.name,
        "displayName": obj_type.displayName or obj_type.name,
        "description": obj_type.description,
        "createdBy": user.username,
        "branch": branch
    }

    if branch not in store.object_types:
        store.object_types[branch] = {}
    store.object_types[branch][obj_id] = new_object

    # Redis 캐시 (옵션)
    if redis_client:
        await redis_client.set(f"object_type:{branch}:{obj_id}", str(new_object), ex=3600)

    return new_object

@app.get("/api/v1/schemas/{branch:path}/object-types/{object_type_id}")
async def get_object_type(
    branch: str,
    object_type_id: str,
    user: UserContext = Depends(require_schema_read)
):
    """특정 ObjectType 조회"""
    if branch not in store.branches:
        raise HTTPException(status_code=404, detail=f"Branch '{branch}' not found")

    if branch in store.object_types and object_type_id in store.object_types[branch]:
        return store.object_types[branch][object_type_id]

    raise HTTPException(status_code=404, detail="ObjectType not found")

@app.put("/api/v1/schemas/{branch:path}/object-types/{object_type_id}")
async def update_object_type(
    branch: str,
    object_type_id: str,
    update: ObjectTypeUpdate,
    user: UserContext = Depends(require_schema_write)
):
    """ObjectType 수정"""
    if branch not in store.branches:
        raise HTTPException(status_code=404, detail=f"Branch '{branch}' not found")

    if branch not in store.object_types or object_type_id not in store.object_types[branch]:
        raise HTTPException(status_code=404, detail="ObjectType not found")

    obj = store.object_types[branch][object_type_id]
    if update.displayName is not None:
        obj["displayName"] = update.displayName
    if update.description is not None:
        obj["description"] = update.description
    obj["updatedBy"] = user.username

    return obj

@app.delete("/api/v1/schemas/{branch:path}/object-types/{object_type_id}")
async def delete_object_type(
    branch: str,
    object_type_id: str,
    user: UserContext = Depends(require_schema_delete)
):
    """ObjectType 삭제"""
    if branch not in store.branches:
        raise HTTPException(status_code=404, detail=f"Branch '{branch}' not found")

    if branch not in store.object_types or object_type_id not in store.object_types[branch]:
        raise HTTPException(status_code=404, detail="ObjectType not found")

    del store.object_types[branch][object_type_id]

    return {"success": True, "message": "ObjectType deleted"}

# === Branch Management ===
@app.get("/api/v1/branches")
async def get_branches(user: UserContext = Depends(require_branch_read)):
    """브랜치 목록 조회"""
    return {
        "branches": list(store.branches.values()),
        "count": len(store.branches)
    }

@app.post("/api/v1/branches")
async def create_branch(
    branch: BranchCreate,
    user: UserContext = Depends(require_branch_write)
):
    """브랜치 생성"""
    if branch.name in store.branches:
        raise HTTPException(status_code=409, detail="Branch already exists")

    if branch.parentBranch not in store.branches:
        raise HTTPException(status_code=404, detail="Parent branch not found")

    new_branch = {
        "name": branch.name,
        "description": branch.description,
        "parentBranch": branch.parentBranch,
        "createdBy": user.username
    }
    store.branches[branch.name] = new_branch

    # 부모 브랜치의 스키마 복사
    if branch.parentBranch in store.object_types:
        store.object_types[branch.name] = store.object_types[branch.parentBranch].copy()

    return new_branch

@app.post("/api/v1/branches/{branch_name:path}/merge")
async def merge_branch(
    branch_name: str,
    target_branch: str = "main",
    user: UserContext = Depends(require_branch_merge)
):
    """브랜치 병합"""
    if branch_name not in store.branches:
        raise HTTPException(status_code=404, detail="Source branch not found")

    if target_branch not in store.branches:
        raise HTTPException(status_code=404, detail="Target branch not found")

    # 단순 병합: source를 target으로 덮어쓰기
    if branch_name in store.object_types:
        store.object_types[target_branch] = store.object_types[branch_name].copy()

    return {
        "success": True,
        "message": f"Branch '{branch_name}' merged into '{target_branch}'",
        "mergedBy": user.username
    }

# === Validation ===
@app.post("/api/v1/validation/breaking-changes")
async def check_breaking_changes(
    branch1: str = "main",
    branch2: str = "develop",
    user: UserContext = Depends(require_schema_read)
):
    """Breaking change 검사"""
    changes = []

    objects1 = store.object_types.get(branch1, {})
    objects2 = store.object_types.get(branch2, {})

    # 삭제된 ObjectType 찾기
    for obj_id, obj in objects1.items():
        if obj_id not in objects2:
            changes.append({
                "type": "object_deleted",
                "severity": "breaking",
                "object": obj["name"]
            })

    # 추가된 ObjectType 찾기
    for obj_id, obj in objects2.items():
        if obj_id not in objects1:
            changes.append({
                "type": "object_added",
                "severity": "non-breaking",
                "object": obj["name"]
            })

    return {
        "branch1": branch1,
        "branch2": branch2,
        "changes": changes,
        "has_breaking_changes": any(c["severity"] == "breaking" for c in changes)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
