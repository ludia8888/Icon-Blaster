"""
BFF Dependencies
실제 OMS 클라이언트 사용
"""

import sys
import os
from typing import Optional
from fastapi import HTTPException, status

# shared 모듈 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

# 실제 OMS 클라이언트 import
from services.oms_client import OMSClient

# 전역 OMS 클라이언트 인스턴스 (main.py에서 초기화)
oms_client: Optional[OMSClient] = None

def set_oms_client(client: OMSClient):
    """OMS 클라이언트 설정"""
    global oms_client
    oms_client = client

def get_oms_client() -> OMSClient:
    """OMS 클라이언트 반환"""
    if not oms_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OMS 클라이언트가 초기화되지 않았습니다"
        )
    return oms_client

# OMS 클라이언트를 래핑하는 TerminusService 호환 클래스
class TerminusService:
    """OMS 클라이언트를 래핑하는 TerminusService 호환 클래스"""
    
    def __init__(self):
        self.connected = False
    
    async def list_databases(self):
        """데이터베이스 목록 조회"""
        client = get_oms_client()
        response = await client.list_databases()
        if isinstance(response, dict) and response.get("status") == "success":
            databases = response.get("data", {}).get("databases", [])
            return [db.get("name") for db in databases if db.get("name")]
        elif isinstance(response, list):
            # 직접 리스트가 반환된 경우
            return [db.get("name") for db in response if isinstance(db, dict) and db.get("name")]
        return []
    
    async def create_database(self, db_name: str, description: Optional[str] = None):
        """데이터베이스 생성"""
        client = get_oms_client()
        response = await client.create_database(db_name, description)
        return response
    
    async def delete_database(self, db_name: str):
        """데이터베이스 삭제"""
        client = get_oms_client()
        response = await client.delete_database(db_name)
        return response
    
    async def get_database_info(self, db_name: str):
        """데이터베이스 정보 조회"""
        client = get_oms_client()
        response = await client.check_database_exists(db_name)
        return response
    
    async def list_classes(self, db_name: str):
        """클래스 목록 조회"""
        client = get_oms_client()
        response = await client.list_ontologies(db_name)
        if response.get("status") == "success":
            ontologies = response.get("data", {}).get("ontologies", [])
            return ontologies
        return []
    
    async def create_class(self, db_name: str, class_data: dict):
        """클래스 생성"""
        client = get_oms_client()
        create_data = {"db_name": db_name, **class_data}
        response = await client.create_ontology(create_data)
        return response
    
    async def get_class(self, db_name: str, class_id: str):
        """클래스 조회"""
        client = get_oms_client()
        response = await client.get_ontology(class_id, db_name)
        return response
    
    async def update_class(self, db_name: str, class_id: str, class_data: dict):
        """클래스 업데이트"""
        client = get_oms_client()
        response = await client.update_ontology(class_id, class_data, db_name)
        return response
    
    async def delete_class(self, db_name: str, class_id: str):
        """클래스 삭제"""
        client = get_oms_client()
        response = await client.delete_ontology(db_name, class_id)
        return response
    
    async def query_database(self, db_name: str, query: str):
        """데이터베이스 쿼리"""
        client = get_oms_client()
        response = await client.query_ontologies(db_name, query)
        return response
    
    # 브랜치 관리 메서드들 (실제 OMS API 호출)
    async def create_branch(self, db_name: str, branch_name: str, from_branch: Optional[str] = None):
        """브랜치 생성 - 실제 OMS API 호출"""
        client = get_oms_client()
        branch_data = {
            "branch_name": branch_name
        }
        if from_branch:
            branch_data["from_branch"] = from_branch
        
        response = await client.create_branch(db_name, branch_data)
        return response
    
    async def delete_branch(self, db_name: str, branch_name: str):
        """브랜치 삭제 - 실제 OMS API 호출"""
        client = get_oms_client()
        # OMS 클라이언트에 delete_branch 메서드 추가 필요
        try:
            response = await client.client.delete(f"/api/v1/branch/{db_name}/{branch_name}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"브랜치 삭제 실패 ({db_name}/{branch_name}): {e}")
    
    async def checkout(self, db_name: str, target: str, target_type: str):
        """체크아웃 - 실제 OMS API 호출"""
        client = get_oms_client()
        checkout_data = {
            "target": target,
            "target_type": target_type
        }
        try:
            response = await client.client.post(f"/api/v1/branch/{db_name}/checkout", json=checkout_data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"체크아웃 실패 ({db_name}): {e}")
    
    async def commit_changes(self, db_name: str, message: str, author: str, branch: Optional[str] = None):
        """변경사항 커밋 - 실제 OMS API 호출"""
        client = get_oms_client()
        commit_data = {
            "message": message,
            "author": author
        }
        if branch:
            commit_data["branch"] = branch
        
        try:
            response = await client.client.post(f"/api/v1/version/{db_name}/commit", json=commit_data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"커밋 실패 ({db_name}): {e}")
    
    async def get_commit_history(self, db_name: str, branch: Optional[str] = None, limit: int = 50, offset: int = 0):
        """커밋 히스토리 조회 - 실제 OMS API 호출"""
        client = get_oms_client()
        response = await client.get_version_history(db_name)
        return response
    
    async def get_diff(self, db_name: str, base: str, compare: str):
        """차이 비교 - 실제 OMS API 호출"""
        client = get_oms_client()
        diff_data = {
            "base": base,
            "compare": compare
        }
        try:
            response = await client.client.post(f"/api/v1/version/{db_name}/diff", json=diff_data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"차이 비교 실패 ({db_name}): {e}")
    
    async def merge_branches(self, db_name: str, source: str, target: str, strategy: str = "merge", message: Optional[str] = None, author: Optional[str] = None):
        """브랜치 병합 - 실제 OMS API 호출"""
        client = get_oms_client()
        merge_data = {
            "source": source,
            "target": target,
            "strategy": strategy
        }
        if message:
            merge_data["message"] = message
        if author:
            merge_data["author"] = author
            
        try:
            response = await client.client.post(f"/api/v1/branch/{db_name}/merge", json=merge_data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"브랜치 병합 실패 ({db_name}): {e}")
    
    async def rollback(self, db_name: str, target_commit: str, create_branch: bool = True, branch_name: Optional[str] = None):
        """롤백 - 실제 OMS API 호출"""
        client = get_oms_client()
        rollback_data = {
            "target_commit": target_commit,
            "create_branch": create_branch
        }
        if branch_name:
            rollback_data["branch_name"] = branch_name
            
        try:
            response = await client.client.post(f"/api/v1/version/{db_name}/rollback", json=rollback_data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"롤백 실패 ({db_name}): {e}")


# JSON-LD 변환기
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared', 'utils'))
from jsonld import JSONToJSONLDConverter

# 의존성 제공 함수들
def get_terminus_service() -> TerminusService:
    """TerminusService 의존성 제공"""
    return TerminusService()

def get_jsonld_converter() -> JSONToJSONLDConverter:
    """JSON-LD 변환기 의존성 제공"""
    return JSONToJSONLDConverter()

# Label Mapper 의존성 제공
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))
from label_mapper import LabelMapper

# 전역 Label Mapper 인스턴스 (main.py에서 초기화)
label_mapper: Optional[LabelMapper] = None

def set_label_mapper(mapper: LabelMapper):
    """Label Mapper 설정"""
    global label_mapper
    label_mapper = mapper

def get_label_mapper() -> LabelMapper:
    """Label Mapper 의존성 제공"""
    if not label_mapper:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Label Mapper가 초기화되지 않았습니다"
        )
    return label_mapper