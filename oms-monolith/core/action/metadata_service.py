"""
OMS Action Metadata Service
ActionType 메타데이터 관리만 담당 (실행 로직은 별도 Actions Service MSA에서 처리)
"""
import logging
import sys
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

# Add database path for simple client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../database'))

from .models import ActionTypeModel, ActionDefinition
from database.clients.terminus_db_simple import SimpleTerminusDBClient

logger = logging.getLogger(__name__)


class ActionMetadataService:
    """
    OMS 내부 ActionType 메타데이터 서비스
    
    책임:
    - ActionType 정의 CRUD
    - 스키마 검증 
    - 버전 관리
    - 메타데이터 제공 (Actions Service에서 조회)
    
    비책임 (Actions Service MSA가 담당):
    - 실제 액션 실행
    - 사용자 편집 적용
    - Action Log 관리
    - Object DB 쓰기
    """
    
    def __init__(self, tdb_client=None, redis_client=None, terminus_endpoint=None):
        """
        Initialize Action Metadata Service
        
        Args:
            tdb_client: TerminusDB 클라이언트 (레거시, 현재는 사용 안함)
            redis_client: Redis 클라이언트 (캐싱용)
            terminus_endpoint: TerminusDB 엔드포인트 (새로운 직접 연결)
        """
        # 새로운 간단한 TerminusDB 클라이언트 사용 (admin 데이터베이스 사용)
        from database.unified_terminus_client import TerminusDBConfig
        
        config = TerminusDBConfig(
            endpoint=terminus_endpoint,
            db="admin"  # 기존 admin 데이터베이스 사용
        )
        self.tdb = SimpleTerminusDBClient(config)
        self.redis = redis_client
        self.action_types = {}  # 메모리 캐시
        self._initialized = False
    
    async def initialize(self) -> bool:
        """서비스 초기화 - TerminusDB 연결"""
        if self._initialized:
            return True
            
        try:
            connected = await self.tdb.connect()
            if connected:
                self._initialized = True
                logger.info("ActionMetadataService initialized with TerminusDB")
                return True
            else:
                logger.error("Failed to connect to TerminusDB")
                return False
        except Exception as e:
            logger.error(f"ActionMetadataService initialization failed: {e}")
            return False
    
    async def create_action_type(self, action_data: Dict[str, Any]) -> ActionTypeModel:
        """ActionType 정의 생성"""
        action_id = action_data.get('id', f"action_type_{len(self.action_types) + 1}")
        
        action_type = ActionTypeModel(
            id=action_id,
            objectTypeId=action_data.get('objectTypeId', 'default'),
            name=action_data.get('name', 'New Action Type'),
            displayName=action_data.get('displayName', action_data.get('name', 'New Action Type')),
            description=action_data.get('description'),
            inputSchema=action_data.get('inputSchema', {}),
            validationExpression=action_data.get('validationExpression'),
            webhookUrl=action_data.get('webhookUrl'),
            isBatchable=action_data.get('isBatchable', True),
            isAsync=action_data.get('isAsync', False),
            requiresApproval=action_data.get('requiresApproval', False),
            approvalRoles=action_data.get('approvalRoles', []),
            onSuccessFunction=action_data.get('onSuccessFunction'),
            onFailureFunction=action_data.get('onFailureFunction'),
            maxRetries=action_data.get('maxRetries', 3),
            timeoutSeconds=action_data.get('timeoutSeconds', 300),
            batchSize=action_data.get('batchSize', 100),
            continueOnError=action_data.get('continueOnError', False),
            implementation=action_data.get('implementation', 'webhook'),
            status=action_data.get('status', 'active'),
            versionHash=action_data.get('versionHash', 'v1'),
            createdBy=action_data.get('createdBy', 'system'),
            createdAt=datetime.utcnow(),
            modifiedBy=action_data.get('modifiedBy', 'system'),
            modifiedAt=datetime.utcnow()
        )
        
        # 초기화 확인
        if not self._initialized:
            await self.initialize()
            
        # TerminusDB에 저장
        if self.tdb and self._initialized:
            await self._save_to_terminusdb(action_type)
        
        # 메모리 캐시에 저장
        self.action_types[action_id] = action_type
        
        logger.info(f"Created ActionType: {action_id}")
        return action_type
    
    async def get_action_type(self, action_type_id: str) -> Optional[ActionTypeModel]:
        """ActionType 조회 - Actions Service에서 호출"""
        # 메모리 캐시에서 먼저 확인
        if action_type_id in self.action_types:
            return self.action_types[action_type_id]
        
        # 초기화 확인
        if not self._initialized:
            await self.initialize()
            
        # TerminusDB에서 조회
        if self.tdb and self._initialized:
            action_type = await self._load_from_terminusdb(action_type_id)
            if action_type:
                self.action_types[action_type_id] = action_type
                return action_type
        
        return None
    
    async def update_action_type(self, action_type_id: str, updates: Dict[str, Any]) -> ActionTypeModel:
        """ActionType 업데이트"""
        action_type = await self.get_action_type(action_type_id)
        if not action_type:
            raise ValueError(f"ActionType {action_type_id} not found")
        
        # 업데이트 적용
        for key, value in updates.items():
            if hasattr(action_type, key):
                setattr(action_type, key, value)
        
        action_type.modifiedAt = datetime.utcnow()
        
        # 저장
        if self.tdb and self._initialized:
            await self._save_to_terminusdb(action_type)
        
        self.action_types[action_type_id] = action_type
        
        logger.info(f"Updated ActionType: {action_type_id}")
        return action_type
    
    async def delete_action_type(self, action_type_id: str) -> bool:
        """ActionType 삭제"""
        if action_type_id in self.action_types:
            # TerminusDB에서 삭제
            if self.tdb and self._initialized:
                await self._delete_from_terminusdb(action_type_id)
            
            # 메모리에서 삭제
            del self.action_types[action_type_id]
            
            logger.info(f"Deleted ActionType: {action_type_id}")
            return True
        
        return False
    
    async def list_action_types(self, object_type_id: str = None, 
                              status: str = None) -> List[ActionTypeModel]:
        """ActionType 목록 조회"""
        action_types = list(self.action_types.values())
        
        # 필터링
        if object_type_id:
            action_types = [at for at in action_types if at.objectTypeId == object_type_id]
        
        if status:
            action_types = [at for at in action_types if at.status == status]
        
        return action_types
    
    async def validate_action_input(self, action_type_id: str, 
                                  parameters: Dict[str, Any]) -> Dict[str, Any]:
        """ActionType의 inputSchema에 따른 입력 검증"""
        action_type = await self.get_action_type(action_type_id)
        if not action_type:
            return {"valid": False, "errors": ["ActionType not found"]}
        
        # JSON Schema 검증 (간단한 예시)
        input_schema = action_type.inputSchema
        errors = []
        
        # 필수 필드 검증
        required_fields = input_schema.get("required", [])
        for field in required_fields:
            if field not in parameters:
                errors.append(f"Required field '{field}' is missing")
        
        # 타입 검증 (기본적인 예시)
        properties = input_schema.get("properties", {})
        for field, schema in properties.items():
            if field in parameters:
                expected_type = schema.get("type")
                value = parameters[field]
                
                if expected_type == "string" and not isinstance(value, str):
                    errors.append(f"Field '{field}' must be a string")
                elif expected_type == "integer" and not isinstance(value, int):
                    errors.append(f"Field '{field}' must be an integer")
                elif expected_type == "boolean" and not isinstance(value, bool):
                    errors.append(f"Field '{field}' must be a boolean")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    async def _save_to_terminusdb(self, action_type: ActionTypeModel):
        """TerminusDB에 ActionType 저장"""
        if not self.tdb:
            return
        
        try:
            # Pydantic 모델을 dict로 변환
            doc_data = action_type.model_dump()
            doc_data["@type"] = "ActionType"
            
            # datetime 객체를 ISO 문자열로 변환
            if 'createdAt' in doc_data and doc_data['createdAt']:
                doc_data['createdAt'] = doc_data['createdAt'].isoformat()
            if 'modifiedAt' in doc_data and doc_data['modifiedAt']:
                doc_data['modifiedAt'] = doc_data['modifiedAt'].isoformat()
            
            success = await self.tdb.insert_document(
                doc=doc_data,
                doc_id=f"ActionType_{action_type.id}"
            )
            
            if success:
                logger.debug(f"Saved ActionType to TerminusDB: {action_type.id}")
            else:
                logger.warning(f"Failed to save ActionType to TerminusDB: {action_type.id}")
                
        except Exception as e:
            logger.warning(f"Failed to save ActionType to TerminusDB: {e}")
    
    async def _load_from_terminusdb(self, action_type_id: str) -> Optional[ActionTypeModel]:
        """TerminusDB에서 ActionType 로드"""
        if not self.tdb:
            return None
        
        try:
            doc = await self.tdb.get_document(f"ActionType_{action_type_id}")
            if doc:
                # @type 등 TerminusDB 특수 필드 제거
                clean_doc = {k: v for k, v in doc.items() if not k.startswith("@")}
                
                # ISO 문자열을 datetime 객체로 변환
                from datetime import datetime
                if 'createdAt' in clean_doc and isinstance(clean_doc['createdAt'], str):
                    clean_doc['createdAt'] = datetime.fromisoformat(clean_doc['createdAt'].replace('Z', '+00:00'))
                if 'modifiedAt' in clean_doc and isinstance(clean_doc['modifiedAt'], str):
                    clean_doc['modifiedAt'] = datetime.fromisoformat(clean_doc['modifiedAt'].replace('Z', '+00:00'))
                
                return ActionTypeModel(**clean_doc)
        except Exception as e:
            logger.warning(f"Failed to load ActionType from TerminusDB: {e}")
        
        return None
    
    async def _delete_from_terminusdb(self, action_type_id: str):
        """TerminusDB에서 ActionType 삭제"""
        if not self.tdb:
            return
        
        try:
            success = await self.tdb.delete_document(f"ActionType_{action_type_id}")
            if success:
                logger.debug(f"Deleted ActionType from TerminusDB: {action_type_id}")
            else:
                logger.error(f"Failed to delete ActionType from TerminusDB: {action_type_id}")
        except Exception as e:
            logger.error(f"Failed to delete ActionType from TerminusDB: {e}")
    
    async def close(self):
        """서비스 종료 - TerminusDB 연결 해제"""
        if self.tdb:
            await self.tdb.disconnect()
            self._initialized = False
            logger.info("ActionMetadataService closed")