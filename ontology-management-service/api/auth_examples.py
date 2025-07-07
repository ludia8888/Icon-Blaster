"""
Auth Integration Examples
권한 체크가 적용된 API 엔드포인트 예시
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.auth import ResourceType, Action, UserContext
from middleware.auth_middleware import get_current_user, require_permission
from core.auth import get_permission_checker

router = APIRouter(prefix="/api/v1", tags=["auth-examples"])


class SchemaCreate(BaseModel):
    name: str
    description: str


class SchemaResponse(BaseModel):
    id: str
    name: str
    description: str
    created_by: str


# 예시 1: 단순 인증만 필요한 엔드포인트
@router.get("/me")
async def get_current_user_info(
    user: UserContext = Depends(get_current_user)
):
    """현재 사용자 정보 조회"""
    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "roles": user.roles,
        "teams": user.teams
    }


# 예시 2: 특정 권한이 필요한 엔드포인트
@router.post("/schemas", response_model=SchemaResponse)
async def create_schema(
    schema: SchemaCreate,
    request: Request,
    user: UserContext = Depends(get_current_user)
):
    """스키마 생성 (CREATE 권한 필요)"""
    # 권한 체크
    checker = get_permission_checker()
    if not checker.check_permission(user, ResourceType.SCHEMA, "*", Action.CREATE):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # 실제 스키마 생성 로직
    new_schema = SchemaResponse(
        id="schema-123",
        name=schema.name,
        description=schema.description,
        created_by=user.username
    )
    
    return new_schema


# 예시 3: 리소스별 권한 체크
@router.get("/schemas/{schema_id}")
async def get_schema(
    schema_id: str,
    user: UserContext = Depends(get_current_user)
):
    """특정 스키마 조회 (READ 권한 필요)"""
    # 권한 체크
    checker = get_permission_checker()
    if not checker.check_permission(user, ResourceType.SCHEMA, schema_id, Action.READ):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # 실제 스키마 조회 로직
    return {
        "id": schema_id,
        "name": "Example Schema",
        "description": "Example description"
    }


# 예시 4: 사용자가 접근 가능한 리소스 목록
@router.get("/my-schemas")
async def get_my_schemas(
    user: UserContext = Depends(get_current_user)
):
    """사용자가 읽을 수 있는 스키마 목록"""
    checker = get_permission_checker()
    allowed_schemas = checker.get_user_resources(
        user, 
        ResourceType.SCHEMA, 
        Action.READ
    )
    
    if "*" in allowed_schemas:
        # 모든 스키마 접근 가능
        return {
            "schemas": [
                {"id": "schema-1", "name": "Schema 1"},
                {"id": "schema-2", "name": "Schema 2"},
                {"id": "schema-3", "name": "Schema 3"}
            ],
            "total": 3
        }
    else:
        # 특정 스키마만 접근 가능
        return {
            "schemas": [
                {"id": sid, "name": f"Schema {sid}"} 
                for sid in allowed_schemas
            ],
            "total": len(allowed_schemas)
        }


# 예시 5: 복합 권한 체크 (브랜치 머지)
@router.post("/branches/{branch_id}/merge")
async def merge_branch(
    branch_id: str,
    target_branch: str,
    user: UserContext = Depends(get_current_user)
):
    """브랜치 머지 (MERGE 권한 + APPROVE 권한 필요)"""
    checker = get_permission_checker()
    
    # 머지 권한 체크
    can_merge = checker.check_permission(
        user, ResourceType.BRANCH, branch_id, Action.MERGE
    )
    
    # Approve 권한 체크 (reviewer 이상)
    can_approve = checker.check_permission(
        user, ResourceType.BRANCH, branch_id, Action.APPROVE
    )
    
    if not can_merge:
        raise HTTPException(status_code=403, detail="Merge permission denied")
    
    # Auto-approve if user has approve permission
    auto_approved = can_approve
    
    return {
        "branch_id": branch_id,
        "target_branch": target_branch,
        "merged_by": user.username,
        "auto_approved": auto_approved,
        "status": "merged" if auto_approved else "pending_approval"
    }


# 예시 6: Team 기반 권한
@router.get("/teams/{team_id}/resources")
async def get_team_resources(
    team_id: str,
    user: UserContext = Depends(get_current_user)
):
    """팀 리소스 조회 (팀 멤버만 가능)"""
    if team_id not in user.teams and "admin" not in user.roles:
        raise HTTPException(
            status_code=403, 
            detail=f"Not a member of team {team_id}"
        )
    
    return {
        "team_id": team_id,
        "resources": [
            {"type": "schema", "id": "team-schema-1"},
            {"type": "branch", "id": "team-branch-1"}
        ]
    }