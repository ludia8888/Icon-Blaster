"""
TerminusDB 내부 캐싱을 활용하는 Schema Service
REQ-OMS-F1: 스키마 메타데이터 CRUD
섹션 8.1.2의 SchemaService 클래스 구현 - TERMINUSDB_LRU_CACHE_SIZE 최적화

IMPORTANT - Naming Convention:
- Python Models: ObjectTypeCreate, PropertyCreate는 snake_case 사용
- TerminusDB/API: camelCase 사용 (displayName, isRequired 등)
- 이 서비스에서 명시적 변환 수행 (예: data.display_name → "displayName")

자세한 내용은 Docs/NAMING_CONVENTION_GUIDE.md 참조
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.clients.terminus_db import TerminusDBClient
from shared.models.action_types import (
    ActionCategory,
    ActionType,
    ActionTypeCreate,
    ActionTypeReference,
    ActionTypeUpdate,
    ActionTypeValidator,
    ApplicableObjectType,
    ParameterSchema,
    TransformationType,
)
from shared.models.data_types import (
    DataType,
    DataTypeCategory,
    DataTypeCreate,
    DataTypeFormat,
    DataTypeUpdate,
    TypeConstraint,
)
from shared.models.domain import (
    Cardinality,
    Directionality,
    Interface,
    InterfaceCreate,
    InterfaceUpdate,
    LinkType,
    LinkTypeCreate,
    LinkTypeUpdate,
    ObjectType,
    ObjectTypeCreate,
    ObjectTypeUpdate,
    Property,
    PropertyCreate,
    SharedProperty,
    SharedPropertyCreate,
    SharedPropertyUpdate,
    Status,
    TypeClass,
    Visibility,
)
from shared.models.function_types import (
    FunctionBehavior,
    FunctionCategory,
    FunctionExample,
    FunctionParameter,
    FunctionType,
    FunctionTypeCreate,
    FunctionTypeUpdate,
    FunctionTypeValidator,
    ReturnType,
    RuntimeConfig,
)

logger = logging.getLogger(__name__)


class SchemaService:
    """스키마 관리 핵심 서비스 - TerminusDB 내부 캐싱 활용"""

    def __init__(self, tdb_endpoint: Optional[str] = None, redis_url: Optional[str] = None, event_publisher: Optional[Any] = None):
        self.tdb_endpoint = tdb_endpoint or "http://terminusdb:6363"
        self.db_name = "oms"
        self.tdb = TerminusDBClient(self.tdb_endpoint)
        # TerminusDB 내부 LRU 캐싱 활용 (TERMINUSDB_LRU_CACHE_SIZE 환경변수)
        self.event_publisher = event_publisher

        # Redis URL은 하위 호환성을 위해 받지만 사용하지 않음
        if redis_url:
            logger.warning("Redis URL provided but not used. Using TerminusDB internal caching instead.")

    async def initialize(self):
        """서비스 초기화"""
        # TerminusDB 초기화 (내부 캐싱 자동 활성화)
        try:
            await self.tdb.create_database(self.db_name)
            logger.info(f"Database {self.db_name} initialized with TerminusDB internal caching")

            # 자주 사용되는 문서 타입들을 캐시에 워밍
            await self.cache.warm_cache_for_branch(
                self.db_name,
                "main",
                ["ObjectType", "Property", "LinkType", "Interface", "SharedProperty"]
            )

        except Exception as e:
            logger.warning(f"Database initialization: {e}")

    def _generate_id(self) -> str:
        """고유 ID 생성"""
        return str(uuid.uuid4())

    def _generate_version_hash(self, data: Any) -> str:
        """버전 해시 생성"""
        if hasattr(data, 'model_dump'):
            hash_data = json.dumps(data.model_dump(), sort_keys=True, default=str)
        else:
            hash_data = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(hash_data.encode()).hexdigest()[:16]

    async def create_object_type(
        self,
        branch: str,
        data: ObjectTypeCreate,
        user: Dict[str, Any]  # User 객체 대신 dict 사용
    ) -> ObjectType:
        """
        ObjectType 생성 - 섹션 8.1.2 완전 구현
        문서 설계의도: 권한 확인 → 유효성 검증 → 중복 확인 → 버전 해시 → 트랜잭션 → 캐시 무효화 → 이벤트 발행
        """

        # 1. 권한 확인 (문서 63-65줄)
        if not await self._check_permission(user, "schema:write", branch):
            raise PermissionError(f"User {user.get('id')} cannot write to branch {branch}")

        # 2. 유효성 검증 (문서 67-70줄)
        validation_result = await self._validate_object_type(data)
        if not validation_result.get("is_valid"):
            raise ValueError(validation_result.get("errors"))

        # 3. 중복 확인 (문서 72-75줄)
        existing = await self._check_duplicate_name(branch, data.name)
        if existing:
            raise ValueError(f"ObjectType {data.name} already exists")

        # 4. 버전 해시 생성 (문서 77-78줄)
        version_hash = self._generate_version_hash(data)

        # 5. 문서 생성 (문서 80-102줄)
        doc = {
            "@type": "ObjectType",
            "@id": f"ObjectType_{data.name}",
            "id": self._generate_id(),
            "name": data.name,
            "displayName": data.display_name,  # snake_case → camelCase
            "pluralDisplayName": data.plural_display_name,  # snake_case → camelCase
            "description": data.description,
            "icon": data.icon,
            "color": data.color,
            "status": data.status or "active",
            "typeClass": data.type_class or "object",  # snake_case → camelCase
            "baseInterfaces": [{"@id": f"Interface_{i}"} for i in (data.interfaces or [])],  # interfaces 필드 사용
            "properties": [],  # 초기에는 빈 배열
            "parentTypes": data.parent_types or [],  # snake_case → camelCase
            "isAbstract": data.is_abstract or False,  # snake_case → camelCase
            "titleProperty": getattr(data, 'title_property', None),  # snake_case
            "subtitleProperty": getattr(data, 'subtitle_property', None),  # snake_case
            "docUrl": getattr(data, 'doc_url', None),  # snake_case
            "versionHash": version_hash,
            "createdBy": user.get("id"),
            "createdAt": datetime.utcnow().isoformat(),
            "modifiedBy": user.get("id"),
            "modifiedAt": datetime.utcnow().isoformat()
        }

        # 6. 트랜잭션 실행 (문서 105-117줄)
        async with self.tdb.transaction(branch=branch) as tx:
            await tx.insert_document(doc)

            # 버전 DAG 업데이트 (문서 109-116줄)
            await self._update_version_dag(
                tx, branch, version_hash,
                changed_resources=[f"object_type:{data.name}"],
                author=user.get("id"),
                message=f"Create object type: {data.name}"
            )

            await tx.commit()

        # 7. 캐시 무효화 (문서 119-120줄)
        await self.cache.invalidate_branch(branch)

        # 8. 이벤트 발행 (Outbox 패턴, 문서 122-133줄)
        await self.events.create_outbox_event(
            event_type="schema.changed",
            payload={
                "branch": branch,
                "version_hash": version_hash,
                "changed_resources": [f"object_type:{data.name}"],
                "operation": "create",
                "user": user.get("id"),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

        # 9. 도메인 객체 반환 (문서 135-136줄)
        return ObjectType.from_document(doc)

    async def _check_permission(self, user: Dict[str, Any], permission: str, branch: str) -> bool:
        """권한 확인 - 문서 8.1.2 참조"""
        # 기본 구현: 모든 권한 허용 (실제로는 RBAC 구현 필요)
        user_id = user.get("id")
        if not user_id:
            return False

        # TODO: 실제 권한 시스템과 연동
        # - RBAC 역할 확인
        # - 브랜치별 권한 확인
        # - 리소스별 권한 확인
        return True

    async def _validate_object_type(self, data: ObjectTypeCreate) -> Dict[str, Any]:
        """ObjectType 유효성 검증 - 문서 8.1.2 참조"""
        errors = []

        # 필수 필드 검증
        if not data.name:
            errors.append("Name is required")
        if not data.display_name:  # snake_case
            errors.append("Display name is required")

        # 네이밍 규칙 검증
        import re
        if data.name and not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', data.name):
            errors.append("Name must start with letter and contain only letters, numbers, underscores")

        # 색상 검증
        if data.color and not re.match(r'^#[0-9A-Fa-f]{6}$', data.color):
            errors.append("Color must be valid hex color (#RRGGBB)")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }

    async def _check_duplicate_name(self, branch: str, name: str) -> bool:
        """중복 이름 확인 - 문서 8.1.2 참조"""
        existing = await self.tdb.get_document(
            f"ObjectType_{name}",
            db=self.db_name,
            branch=branch
        )
        return existing is not None

    async def _update_version_dag(
        self,
        tx,
        branch: str,
        version_hash: str,
        changed_resources: List[str],
        author: str,
        message: str
    ):
        """버전 DAG 업데이트 - 문서 8.1.2 참조"""
        # 버전 노드 생성
        version_node = {
            "@type": "Version",
            "@id": f"Version_{version_hash}",
            "hash": version_hash,
            "branch": branch,
            "changedResources": changed_resources,
            "author": author,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "parentVersions": []  # TODO: 부모 버전 관계 구현
        }

        await tx.insert_document(version_node)

    async def get_object_type(
        self,
        branch: str,
        type_name: str
    ) -> Optional[ObjectType]:
        """ObjectType 조회"""
        # TerminusDB 내부 캐시를 활용한 최적화된 조회
        cache_key = f"object_type:{branch}:{type_name}"

        # SmartCacheManager를 통한 최적화된 조회
        return await self.cache.get_with_optimization(
            key=cache_key,
            db=self.db_name,
            branch=branch,
            query_factory=lambda: self._get_object_type_from_db(type_name, branch),
            doc_type="ObjectType"
        )

    async def _get_object_type_from_db(self, type_name: str, branch: str) -> Optional[ObjectType]:
        """DB에서 ObjectType 직접 조회"""
        doc = await self.tdb.get_document(
            f"ObjectType_{type_name}",
            db=self.db_name,
            branch=branch
        )

        if not doc:
            return None

        return self._doc_to_object_type(doc)

    async def list_object_types(
        self,
        branch: str,
        status: Optional[Status] = None,
        type_class: Optional[TypeClass] = None
    ) -> List[ObjectType]:
        """ObjectType 목록 조회 - TerminusDB 내부 캐싱 활용"""
        filter_key = f"{status.value if status else 'all'}_{type_class.value if type_class else 'all'}"
        cache_key = f"object_types:{branch}:list:{filter_key}"

        # SmartCacheManager를 통한 최적화된 조회
        return await self.cache.get_with_optimization(
            key=cache_key,
            db=self.db_name,
            branch=branch,
            query_factory=lambda: self._get_object_types_from_db(branch, status, type_class),
            doc_type="ObjectType"
        )

    async def _get_object_types_from_db(
        self,
        branch: str,
        status: Optional[Status] = None,
        type_class: Optional[TypeClass] = None
    ) -> List[ObjectType]:
        """DB에서 ObjectType 목록 직접 조회"""
        # TerminusDB 내부 캐시가 이 쿼리 결과를 자동으로 캐싱
        docs = await self.tdb.get_all_documents(
            doc_type="ObjectType",
            db=self.db_name,
            branch=branch
        )

        # 도메인 모델로 변환
        object_types = [self._doc_to_object_type(doc) for doc in docs]

        # 필터링
        if status:
            object_types = [ot for ot in object_types if ot.status == status]
        if type_class:
            object_types = [ot for ot in object_types if ot.typeClass == type_class]

        return object_types

    async def update_object_type(
        self,
        branch: str,
        type_name: str,
        data: ObjectTypeUpdate,
        user_id: str = "system"
    ) -> ObjectType:
        """ObjectType 수정"""
        # 설계의도: constructor에서 설정한 self.tdb 사용
        tdb = self.tdb

        # 기존 문서 조회
        doc = await tdb.get_document(
            f"ObjectType_{type_name}",
            db=self.db_name,
            branch=branch
        )

        if not doc:
            raise ValueError(f"ObjectType {type_name} not found")

        # 업데이트할 필드만 변경
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            # CamelCase로 변환
            camel_field = self._to_camel_case(field)
            if value is not None:
                doc[camel_field] = value

        # 메타데이터 업데이트
        doc["modifiedBy"] = user_id
        doc["modifiedAt"] = datetime.utcnow().isoformat()

        # 버전 해시 재생성
        doc["versionHash"] = self._generate_version_hash(doc)

        # TerminusDB에 업데이트 (내부 캐시 자동 무효화)
        await self.tdb.update_document(
            doc,
            db=self.db_name,
            branch=branch,
            author=user_id,
            message=f"Update ObjectType: {type_name}"
        )

        result = self._doc_to_object_type(doc)

        # TerminusDB가 내부적으로 캐시 무효화를 처리하므로 별도 작업 불필요
        logger.debug(f"ObjectType {type_name} updated, TerminusDB internal cache auto-invalidated")

        # 이벤트 발행 - UC-01 요구사항 충족
        if self.event_publisher:
            await self._publish_schema_changed_event(
                branch=branch,
                resource_type="ObjectType",
                resource_id=result.id,
                operation="update",
                author=user_id,
                version_hash=doc["versionHash"],
                changes=update_data
            )

        return result

    async def delete_object_type(
        self,
        branch: str,
        type_name: str,
        user_id: str = "system"
    ) -> bool:
        """ObjectType 삭제"""
        success = await self.tdb.delete_document(
            f"ObjectType_{type_name}",
            db=self.db_name,
            branch=branch,
            author=user_id,
            message=f"Delete ObjectType: {type_name}"
        )

        if success:
            # TerminusDB가 내부적으로 캐시 무효화를 처리
            logger.debug(f"ObjectType {type_name} deleted, TerminusDB internal cache auto-invalidated")

            # 이벤트 발행 - UC-01 요구사항 충족
            if self.event_publisher:
                await self._publish_schema_changed_event(
                    branch=branch,
                    resource_type="ObjectType",
                    resource_id=type_name,  # 삭제된 경우 name을 ID로 사용
                    operation="delete",
                    author=user_id
                )

        return success

    async def add_property(
        self,
        branch: str,
        object_type_id: str,
        data: PropertyCreate,
        user: Dict[str, Any]
    ) -> Property:
        """ObjectType에 Property 추가 - 문서 8.1.2 완전 구현"""

        # 1. ObjectType 조회 (문서 147-150줄)
        obj_type = await self.get_object_type(branch, object_type_id)
        if not obj_type:
            raise ValueError(f"ObjectType {object_type_id} not found")

        # 2. SharedProperty 처리 (문서 152-161줄)
        if data.shared_property_id:  # snake_case
            shared_prop = await self._get_shared_property(data.shared_property_id)
            if not shared_prop:
                raise ValueError(f"SharedProperty {data.shared_property_id} not found")

            # 타입 정보 상속
            data.dataTypeId = shared_prop.dataTypeId
            data.semanticTypeId = shared_prop.semanticTypeId

        # 3. Primary Key 검증 (문서 162-171줄)
        if data.is_primary_key:  # snake_case
            existing_pk = next(
                (p for p in obj_type.properties if p.isPrimaryKey),
                None
            )
            if existing_pk:
                raise ValueError(f"ObjectType already has primary key: {existing_pk.name}")

        # 4. Property 문서 생성 (문서 173-194줄)
        prop_doc = {
            "@type": "Property",
            "@id": f"Property_{obj_type.name}_{data.name}",
            "id": self._generate_id(),
            "objectTypeId": object_type_id,
            "name": data.name,
            "displayName": data.display_name or data.name,  # snake_case → camelCase
            "description": data.description,
            "dataTypeId": data.data_type_id,  # snake_case → camelCase
            "semanticTypeId": getattr(data, 'semantic_type_id', None),  # snake_case → camelCase
            "sharedPropertyId": getattr(data, 'shared_property_id', None),  # snake_case → camelCase
            "isRequired": data.is_required,  # snake_case → camelCase
            "isPrimaryKey": getattr(data, 'is_primary_key', False),  # snake_case → camelCase
            "isIndexed": getattr(data, 'is_indexed', False),  # snake_case → camelCase
            "isUnique": getattr(data, 'is_unique', False),  # snake_case → camelCase
            "isSearchable": getattr(data, 'is_searchable', True),  # snake_case → camelCase
            "defaultValue": getattr(data, 'default_value', None),  # snake_case → camelCase
            "sortOrder": getattr(data, 'sort_order', None) or len(obj_type.properties),  # snake_case → camelCase
            "visibility": data.visibility or "visible",
            "versionHash": self._generate_version_hash(data),
            # 설계의도: Property는 DB 스키마에 audit 필드가 없지만, 도메인 모델 일관성을 위해 추가
            "createdAt": datetime.utcnow().isoformat(),
            "modifiedAt": datetime.utcnow().isoformat()
        }

        # 5. 트랜잭션 실행 (문서 196-225줄)
        async with self.tdb.transaction(branch=branch) as tx:
            # Property 저장
            await tx.insert_document(prop_doc)

            # ObjectType 업데이트
            obj_type_doc = await tx.get_document(f"ObjectType_{obj_type.name}")
            obj_type_doc["properties"].append({"@id": prop_doc["@id"]})
            obj_type_doc["modifiedBy"] = user.get("id")
            obj_type_doc["modifiedAt"] = datetime.utcnow().isoformat()
            obj_type_doc["versionHash"] = self._generate_version_hash(obj_type_doc)

            await tx.update_document(f"ObjectType_{obj_type.name}", obj_type_doc)

            # 버전 DAG 업데이트
            await self._update_version_dag(
                tx, branch,
                self._generate_combined_hash([
                    obj_type_doc["versionHash"],
                    prop_doc["versionHash"]
                ]),
                changed_resources=[
                    f"object_type:{obj_type.name}",
                    f"property:{obj_type.name}.{data.name}"
                ],
                author=user.get("id"),
                message=f"Add property {data.name} to {obj_type.name}"
            )

            await tx.commit()

        # 6. 캐시 무효화 및 이벤트 (문서 227-230줄)
        await self.cache.invalidate_pattern(f"*:{branch}:{object_type_id}*")
        await self._publish_property_added_event(branch, obj_type, prop_doc, user)

        return Property.from_document(prop_doc)

    async def _get_shared_property(self, shared_property_id: str):
        """SharedProperty 조회 헬퍼 메소드"""
        # TODO: SharedProperty 조회 구현
        return None

    def _generate_combined_hash(self, hashes: List[str]) -> str:
        """여러 해시를 결합하여 새로운 해시 생성"""
        combined = "".join(sorted(hashes))
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    async def _publish_property_added_event(self, branch: str, obj_type, prop_doc: Dict, user: Dict):
        """Property 추가 이벤트 발행"""
        if hasattr(self, 'events') and self.events:
            await self.events.create_outbox_event(
                event_type="property.added",
                payload={
                    "branch": branch,
                    "object_type": obj_type.name,
                    "property": prop_doc["name"],
                    "user": user.get("id"),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

    async def remove_property(
        self,
        branch: str,
        type_name: str,
        property_name: str,
        user_id: str = "system"
    ) -> bool:
        """ObjectType에서 Property 제거"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # ObjectType 조회
            doc = await tdb.get_document(
                f"ObjectType_{type_name}",
                db=self.db_name,
                branch=branch
            )

            if not doc:
                raise ValueError(f"ObjectType {type_name} not found")

            # Property 제거
            properties = doc.get("properties", [])
            original_count = len(properties)
            properties = [p for p in properties if p.get("name") != property_name]

            if len(properties) == original_count:
                raise ValueError(f"Property {property_name} not found in {type_name}")

            # 업데이트
            doc["properties"] = properties
            doc["modifiedBy"] = user_id
            doc["modifiedAt"] = datetime.utcnow().isoformat()
            doc["versionHash"] = self._generate_version_hash(doc)

            # Terminus DB에 업데이트
            await tdb.update_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Remove property {property_name} from {type_name}"
            )

            return True

    def _doc_to_object_type(self, doc: Dict[str, Any]) -> ObjectType:
        """Terminus DB 문서를 ObjectType 도메인 모델로 변환"""
        properties = []
        for prop_doc in doc.get("properties", []):
            properties.append(self._doc_to_property(prop_doc))

        return ObjectType(
            id=doc["id"],
            name=doc["name"],
            display_name=doc["displayName"],  # camelCase → snake_case
            plural_display_name=doc.get("pluralDisplayName", ""),  # camelCase → snake_case
            description=doc.get("description", ""),
            status=Status(doc.get("status", "active")),
            type_class=TypeClass(doc.get("typeClass", "object")),  # camelCase → snake_case
            version_hash=doc["versionHash"],  # camelCase → snake_case
            created_by=doc["createdBy"],  # camelCase → snake_case
            created_at=datetime.fromisoformat(doc["createdAt"]),  # camelCase → snake_case
            modified_by=doc["modifiedBy"],  # camelCase → snake_case
            modified_at=datetime.fromisoformat(doc["modifiedAt"]),  # camelCase → snake_case
            properties=properties,
            parent_types=doc.get("parentTypes", []),  # camelCase → snake_case
            interfaces=doc.get("interfaces", []),
            is_abstract=doc.get("isAbstract", False),  # camelCase → snake_case
            icon=doc.get("icon"),
            color=doc.get("color")
        )

    def _doc_to_property(self, doc: Dict[str, Any]) -> Property:
        """Terminus DB 문서를 Property 도메인 모델로 변환"""
        return Property(
            id=doc["id"],
            object_type_id=doc["objectTypeId"],  # camelCase → snake_case
            name=doc["name"],
            display_name=doc["displayName"],  # camelCase → snake_case
            description=doc.get("description", ""),
            data_type_id=doc["dataTypeId"],  # camelCase → snake_case
            semantic_type_id=doc.get("semanticTypeId"),  # camelCase → snake_case
            shared_property_id=doc.get("sharedPropertyId"),  # camelCase → snake_case
            is_required=doc.get("isRequired", False),  # camelCase → snake_case
            is_primary_key=doc.get("isPrimaryKey", False),  # camelCase → snake_case
            is_indexed=doc.get("isIndexed", False),  # camelCase → snake_case
            is_unique=doc.get("isUnique", False),  # camelCase → snake_case
            is_searchable=doc.get("isSearchable", False),  # camelCase → snake_case
            is_array=doc.get("isArray", False),  # camelCase → snake_case
            default_value=doc.get("defaultValue"),  # camelCase → snake_case
            enum_values=doc.get("enumValues", []),  # camelCase → snake_case
            reference_type=doc.get("referenceType"),  # camelCase → snake_case
            sort_order=doc.get("sortOrder", 0),  # camelCase → snake_case
            visibility=Visibility(doc.get("visibility", "visible")),
            validation_rules=doc.get("validationRules", {}),  # camelCase → snake_case
            version_hash=doc["versionHash"],  # camelCase → snake_case
            created_at=datetime.fromisoformat(doc["createdAt"]),  # camelCase → snake_case
            modified_at=datetime.fromisoformat(doc["modifiedAt"])  # camelCase → snake_case
        )

    def _to_camel_case(self, snake_str: str) -> str:
        """snake_case를 camelCase로 변환"""
        components = snake_str.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])

    # LinkType 관련 메소드
    async def create_link_type(
        self,
        branch: str,
        data: LinkTypeCreate,
        user_id: str = "system"
    ) -> LinkType:
        """LinkType 생성"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 중복 체크
            existing = await tdb.get_document(
                f"LinkType_{data.name}",
                db=self.db_name,
                branch=branch
            )
            if existing:
                raise ValueError(f"LinkType {data.name} already exists")

            # From/To ObjectType 존재 확인
            from_type = await tdb.get_document(
                f"ObjectType_{data.fromTypeId}",
                db=self.db_name,
                branch=branch
            )
            if not from_type:
                raise ValueError(f"From ObjectType {data.fromTypeId} not found")

            to_type = await tdb.get_document(
                f"ObjectType_{data.toTypeId}",
                db=self.db_name,
                branch=branch
            )
            if not to_type:
                raise ValueError(f"To ObjectType {data.toTypeId} not found")

            # 버전 해시 생성
            version_hash = self._generate_version_hash(data)

            # Terminus DB 문서 생성
            doc = {
                "@type": "LinkType",
                "@id": f"LinkType_{data.name}",
                "id": self._generate_id(),
                "name": data.name,
                "displayName": data.displayName,
                "description": data.description or "",
                "fromTypeId": data.fromTypeId,
                "toTypeId": data.toTypeId,
                "cardinality": data.cardinality.value,
                "directionality": (data.directionality or Directionality.UNIDIRECTIONAL).value,
                "properties": [],
                "cascadeDelete": data.cascadeDelete,
                "isRequired": data.isRequired,
                "status": (data.status or Status.ACTIVE).value,
                "versionHash": version_hash,
                "createdBy": user_id,
                "createdAt": datetime.utcnow().isoformat(),
                "modifiedBy": user_id,
                "modifiedAt": datetime.utcnow().isoformat()
            }

            # Terminus DB에 저장
            await tdb.insert_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Create LinkType {data.name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"link_types:{branch}")

            result = self._doc_to_link_type(doc)

            # 이벤트 발행 - UC-01 요구사항 충족
            if self.event_publisher:
                await self._publish_schema_changed_event(
                    branch=branch,
                    resource_type="LinkType",
                    resource_id=result.id,
                    operation="create",
                    author=user_id,
                    version_hash=version_hash
                )

            return result

    async def list_link_types(
        self,
        branch: str,
        from_type: Optional[str] = None,
        to_type: Optional[str] = None
    ) -> List[LinkType]:
        """LinkType 목록 조회"""
        cache_key = f"link_types:{branch}:{from_type or 'all'}:{to_type or 'all'}"

        # 캐시 확인
        cached = await self.cache.get(cache_key)
        if cached:
            return [LinkType(**lt) for lt in cached]

        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # WOQL 쿼리로 LinkType 조회
            query = {
                "@type": "LinkType"
            }
            if from_type:
                query["fromTypeId"] = from_type
            if to_type:
                query["toTypeId"] = to_type

            docs = await tdb.query_documents(
                query,
                db=self.db_name,
                branch=branch
            )

            link_types = [self._doc_to_link_type(doc) for doc in docs]

            # 캐시 저장
            await self.cache.set(
                cache_key,
                [lt.model_dump() for lt in link_types],
                version=f"{branch}_link_types"
            )

            return link_types

    async def get_link_type(
        self,
        branch: str,
        link_name: str
    ) -> Optional[LinkType]:
        """특정 LinkType 조회"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            doc = await tdb.get_document(
                f"LinkType_{link_name}",
                db=self.db_name,
                branch=branch
            )

            return self._doc_to_link_type(doc) if doc else None

    async def update_link_type(
        self,
        branch: str,
        link_name: str,
        data: LinkTypeUpdate,
        user_id: str = "system"
    ) -> LinkType:
        """LinkType 수정"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 기존 문서 조회
            doc = await tdb.get_document(
                f"LinkType_{link_name}",
                db=self.db_name,
                branch=branch
            )

            if not doc:
                raise ValueError(f"LinkType {link_name} not found")

            # 업데이트 적용
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                camel_key = self._to_camel_case(key)
                if value is not None:
                    if hasattr(value, 'value'):  # Enum 처리
                        doc[camel_key] = value.value
                    else:
                        doc[camel_key] = value

            doc["modifiedBy"] = user_id
            doc["modifiedAt"] = datetime.utcnow().isoformat()
            doc["versionHash"] = self._generate_version_hash(doc)

            # Terminus DB에 업데이트
            await tdb.update_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Update LinkType {link_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"link_types:{branch}")

            return self._doc_to_link_type(doc)

    async def delete_link_type(
        self,
        branch: str,
        link_name: str,
        user_id: str = "system"
    ) -> bool:
        """LinkType 삭제"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 문서 존재 확인
            doc = await tdb.get_document(
                f"LinkType_{link_name}",
                db=self.db_name,
                branch=branch
            )

            if not doc:
                return False

            # Terminus DB에서 삭제
            await tdb.delete_document(
                f"LinkType_{link_name}",
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Delete LinkType {link_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"link_types:{branch}")

            return True

    def _doc_to_link_type(self, doc: Dict[str, Any]) -> LinkType:
        """Terminus DB 문서를 LinkType 도메인 모델로 변환"""
        properties = []
        for prop_doc in doc.get("properties", []):
            properties.append(self._doc_to_property(prop_doc))

        return LinkType(
            id=doc["id"],
            name=doc["name"],
            displayName=doc["displayName"],
            description=doc.get("description", ""),
            fromTypeId=doc["fromTypeId"],
            toTypeId=doc["toTypeId"],
            cardinality=Cardinality(doc["cardinality"]),
            directionality=Directionality(doc["directionality"]),
            properties=properties,
            cascadeDelete=doc.get("cascadeDelete", False),
            isRequired=doc.get("isRequired", False),
            status=Status(doc.get("status", "active")),
            versionHash=doc["versionHash"],
            createdBy=doc["createdBy"],
            createdAt=datetime.fromisoformat(doc["createdAt"]),
            modifiedBy=doc["modifiedBy"],
            modifiedAt=datetime.fromisoformat(doc["modifiedAt"])
        )

    # Interface 관련 메소드
    async def create_interface(
        self,
        branch: str,
        data: InterfaceCreate,
        user_id: str = "system"
    ) -> Interface:
        """Interface 생성"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 중복 체크
            existing = await tdb.get_document(
                f"Interface_{data.name}",
                db=self.db_name,
                branch=branch
            )
            if existing:
                raise ValueError(f"Interface {data.name} already exists")

            # 부모 인터페이스 확인
            if data.extends:
                for parent in data.extends:
                    parent_doc = await tdb.get_document(
                        f"Interface_{parent}",
                        db=self.db_name,
                        branch=branch
                    )
                    if not parent_doc:
                        raise ValueError(f"Parent Interface {parent} not found")

            # 버전 해시 생성
            version_hash = self._generate_version_hash(data)

            # Terminus DB 문서 생성
            doc = {
                "@type": "Interface",
                "@id": f"Interface_{data.name}",
                "id": self._generate_id(),
                "name": data.name,
                "displayName": data.displayName,
                "description": data.description or "",
                "properties": [],
                "extends": data.extends or [],
                "status": (data.status or Status.ACTIVE).value,
                "versionHash": version_hash,
                "createdBy": user_id,
                "createdAt": datetime.utcnow().isoformat(),
                "modifiedBy": user_id,
                "modifiedAt": datetime.utcnow().isoformat()
            }

            # Terminus DB에 저장
            await tdb.insert_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Create Interface {data.name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"interfaces:{branch}")

            return self._doc_to_interface(doc)

    async def list_interfaces(
        self,
        branch: str,
        extends: Optional[str] = None
    ) -> List[Interface]:
        """Interface 목록 조회"""
        cache_key = f"interfaces:{branch}:{extends or 'all'}"

        # 캐시 확인
        cached = await self.cache.get(cache_key)
        if cached:
            return [Interface(**i) for i in cached]

        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # WOQL 쿼리로 Interface 조회
            query = {
                "@type": "Interface"
            }
            if extends:
                query["extends"] = {"$in": [extends]}

            docs = await tdb.query_documents(
                query,
                db=self.db_name,
                branch=branch
            )

            interfaces = [self._doc_to_interface(doc) for doc in docs]

            # 캐시 저장
            await self.cache.set(
                cache_key,
                [i.model_dump() for i in interfaces],
                version=f"{branch}_interfaces"
            )

            return interfaces

    async def get_interface(
        self,
        branch: str,
        interface_name: str
    ) -> Optional[Interface]:
        """특정 Interface 조회"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            doc = await tdb.get_document(
                f"Interface_{interface_name}",
                db=self.db_name,
                branch=branch
            )

            return self._doc_to_interface(doc) if doc else None

    async def update_interface(
        self,
        branch: str,
        interface_name: str,
        data: InterfaceUpdate,
        user_id: str = "system"
    ) -> Interface:
        """Interface 수정"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 기존 문서 조회
            doc = await tdb.get_document(
                f"Interface_{interface_name}",
                db=self.db_name,
                branch=branch
            )

            if not doc:
                raise ValueError(f"Interface {interface_name} not found")

            # 업데이트 적용
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                camel_key = self._to_camel_case(key)
                if value is not None:
                    if hasattr(value, 'value'):  # Enum 처리
                        doc[camel_key] = value.value
                    else:
                        doc[camel_key] = value

            # 부모 인터페이스 확인
            if "extends" in update_data and update_data["extends"]:
                for parent in update_data["extends"]:
                    parent_doc = await tdb.get_document(
                        f"Interface_{parent}",
                        db=self.db_name,
                        branch=branch
                    )
                    if not parent_doc:
                        raise ValueError(f"Parent Interface {parent} not found")

            doc["modifiedBy"] = user_id
            doc["modifiedAt"] = datetime.utcnow().isoformat()
            doc["versionHash"] = self._generate_version_hash(doc)

            # Terminus DB에 업데이트
            await tdb.update_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Update Interface {interface_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"interfaces:{branch}")

            return self._doc_to_interface(doc)

    async def delete_interface(
        self,
        branch: str,
        interface_name: str,
        user_id: str = "system"
    ) -> bool:
        """Interface 삭제"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 문서 존재 확인
            doc = await tdb.get_document(
                f"Interface_{interface_name}",
                db=self.db_name,
                branch=branch
            )

            if not doc:
                return False

            # 사용중인지 확인 (ObjectType이 구현하고 있는지)
            object_types = await tdb.query_documents(
                {"@type": "ObjectType", "interfaces": {"$in": [interface_name]}},
                db=self.db_name,
                branch=branch
            )

            if object_types:
                raise ValueError(f"Interface {interface_name} is implemented by ObjectTypes")

            # Terminus DB에서 삭제
            await tdb.delete_document(
                f"Interface_{interface_name}",
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Delete Interface {interface_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"interfaces:{branch}")

            return True

    def _doc_to_interface(self, doc: Dict[str, Any]) -> Interface:
        """Terminus DB 문서를 Interface 도메인 모델로 변환"""
        properties = []
        for prop_doc in doc.get("properties", []):
            properties.append(self._doc_to_property(prop_doc))

        return Interface(
            id=doc["id"],
            name=doc["name"],
            displayName=doc["displayName"],
            description=doc.get("description", ""),
            properties=properties,
            extends=doc.get("extends", []),
            status=Status(doc.get("status", "active")),
            versionHash=doc["versionHash"],
            createdBy=doc["createdBy"],
            createdAt=datetime.fromisoformat(doc["createdAt"]),
            modifiedBy=doc["modifiedBy"],
            modifiedAt=datetime.fromisoformat(doc["modifiedAt"])
        )

    # SharedProperty 관련 메소드
    async def create_shared_property(
        self,
        branch: str,
        data: SharedPropertyCreate,
        user_id: str = "system"
    ) -> SharedProperty:
        """SharedProperty 생성"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 중복 체크
            existing = await tdb.get_document(
                f"SharedProperty_{data.name}",
                db=self.db_name,
                branch=branch
            )
            if existing:
                raise ValueError(f"SharedProperty {data.name} already exists")

            # 버전 해시 생성
            version_hash = self._generate_version_hash(data)

            # Terminus DB 문서 생성
            doc = {
                "@type": "SharedProperty",
                "@id": f"SharedProperty_{data.name}",
                "id": self._generate_id(),
                "name": data.name,
                "displayName": data.displayName,
                "description": data.description or "",
                "dataTypeId": data.dataTypeId,
                "semanticTypeId": data.semanticTypeId,
                "defaultValue": data.defaultValue,
                "isRequired": data.isRequired,
                "isIndexed": data.isIndexed,
                "isUnique": data.isUnique,
                "isSearchable": data.isSearchable,
                "validationRules": data.validationRules or {},
                "versionHash": version_hash,
                "createdBy": user_id,
                "createdAt": datetime.utcnow().isoformat(),
                "modifiedBy": user_id,
                "modifiedAt": datetime.utcnow().isoformat()
            }

            # Terminus DB에 저장
            await tdb.insert_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Create SharedProperty {data.name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"shared_properties:{branch}")

            return self._doc_to_shared_property(doc)

    async def list_shared_properties(
        self,
        branch: str,
        semantic_type: Optional[str] = None
    ) -> List[SharedProperty]:
        """SharedProperty 목록 조회"""
        cache_key = f"shared_properties:{branch}:{semantic_type or 'all'}"

        # 캐시 확인
        cached = await self.cache.get(cache_key)
        if cached:
            return [SharedProperty(**sp) for sp in cached]

        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # WOQL 쿼리로 SharedProperty 조회
            query = {
                "@type": "SharedProperty"
            }
            if semantic_type:
                query["semanticTypeId"] = semantic_type

            docs = await tdb.query_documents(
                query,
                db=self.db_name,
                branch=branch
            )

            shared_properties = [self._doc_to_shared_property(doc) for doc in docs]

            # 캐시 저장
            await self.cache.set(
                cache_key,
                [sp.model_dump() for sp in shared_properties],
                version=f"{branch}_shared_properties"
            )

            return shared_properties

    async def get_shared_property(
        self,
        branch: str,
        property_name: str
    ) -> Optional[SharedProperty]:
        """특정 SharedProperty 조회"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            doc = await tdb.get_document(
                f"SharedProperty_{property_name}",
                db=self.db_name,
                branch=branch
            )

            return self._doc_to_shared_property(doc) if doc else None

    async def update_shared_property(
        self,
        branch: str,
        property_name: str,
        data: SharedPropertyUpdate,
        user_id: str = "system"
    ) -> SharedProperty:
        """SharedProperty 수정"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 기존 문서 조회
            doc = await tdb.get_document(
                f"SharedProperty_{property_name}",
                db=self.db_name,
                branch=branch
            )

            if not doc:
                raise ValueError(f"SharedProperty {property_name} not found")

            # 업데이트 적용
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                camel_key = self._to_camel_case(key)
                if value is not None:
                    doc[camel_key] = value

            doc["modifiedBy"] = user_id
            doc["modifiedAt"] = datetime.utcnow().isoformat()
            doc["versionHash"] = self._generate_version_hash(doc)

            # Terminus DB에 업데이트
            await tdb.update_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Update SharedProperty {property_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"shared_properties:{branch}")

            return self._doc_to_shared_property(doc)

    async def delete_shared_property(
        self,
        branch: str,
        property_name: str,
        user_id: str = "system"
    ) -> bool:
        """SharedProperty 삭제"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 문서 존재 확인
            doc = await tdb.get_document(
                f"SharedProperty_{property_name}",
                db=self.db_name,
                branch=branch
            )

            if not doc:
                return False

            # 사용중인지 확인 (Property가 참조하고 있는지)
            properties_using = await tdb.query_documents(
                {"@type": "Property", "sharedPropertyId": property_name},
                db=self.db_name,
                branch=branch
            )

            if properties_using:
                raise ValueError(f"SharedProperty {property_name} is referenced by properties")

            # Terminus DB에서 삭제
            await tdb.delete_document(
                f"SharedProperty_{property_name}",
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Delete SharedProperty {property_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"shared_properties:{branch}")

            return True

    def _doc_to_shared_property(self, doc: Dict[str, Any]) -> SharedProperty:
        """Terminus DB 문서를 SharedProperty 도메인 모델로 변환"""
        return SharedProperty(
            id=doc["id"],
            name=doc["name"],
            displayName=doc["displayName"],
            description=doc.get("description", ""),
            dataTypeId=doc["dataTypeId"],
            semanticTypeId=doc["semanticTypeId"],
            defaultValue=doc.get("defaultValue"),
            isRequired=doc.get("isRequired", False),
            isIndexed=doc.get("isIndexed", False),
            isUnique=doc.get("isUnique", False),
            isSearchable=doc.get("isSearchable", False),
            validationRules=doc.get("validationRules", {}),
            versionHash=doc["versionHash"],
            createdBy=doc["createdBy"],
            createdAt=datetime.fromisoformat(doc["createdAt"]),
            modifiedBy=doc["modifiedBy"],
            modifiedAt=datetime.fromisoformat(doc["modifiedAt"])
        )

    async def _publish_schema_changed_event(
        self,
        branch: str,
        resource_type: str,
        resource_id: str,
        operation: str,
        author: str,
        version_hash: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None
    ):
        """스키마 변경 이벤트 발행 - UC-01 요구사항 구현"""
        if not self.event_publisher:
            logger.warning("Event publisher not configured, skipping event publication")
            return

        try:
            from shared.events.models import OperationType, ResourceType

            # 리소스 타입 매핑
            resource_type_enum = {
                "ObjectType": ResourceType.OBJECT_TYPE,
                "Property": ResourceType.PROPERTY,
                "LinkType": ResourceType.LINK_TYPE,
                "Interface": ResourceType.INTERFACE,
                "SharedProperty": ResourceType.SHARED_PROPERTY
            }.get(resource_type, ResourceType.OBJECT_TYPE)

            # 작업 타입 매핑
            operation_enum = {
                "create": OperationType.CREATE,
                "update": OperationType.UPDATE,
                "delete": OperationType.DELETE
            }.get(operation, OperationType.CREATE)

            # 이벤트 발행
            await self.event_publisher.publish_schema_changed(
                branch=branch,
                resource_type=resource_type_enum.value,
                resource_id=resource_id,
                operation=operation_enum.value,
                author=author,
                changes=changes or {},
                version_hash=version_hash
            )

            logger.info(f"Schema changed event published: {resource_type}/{resource_id} {operation} on branch {branch}")

        except Exception as e:
            # 이벤트 발행 실패는 치명적이지 않으므로 경고만 기록
            logger.warning(f"Failed to publish schema changed event: {e}")
            # 트랜잭션은 계속 진행

    # Action Type 관련 메소드
    async def create_action_type(
        self,
        branch: str,
        data: ActionTypeCreate,
        user_id: str = "system"
    ) -> ActionType:
        """Action Type 생성 - 선언형 메타데이터만 관리"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 중복 체크
            existing = await tdb.get_document(
                f"ActionType_{data.name}",
                db=self.db_name,
                branch=branch
            )
            if existing:
                raise ValueError(f"ActionType {data.name} already exists")

            # 적용 가능한 객체 타입 검증
            for obj_type in data.applicable_object_types:
                if obj_type.object_type_id != "*":
                    obj_doc = await tdb.get_document(
                        f"ObjectType_{obj_type.object_type_id}",
                        db=self.db_name,
                        branch=branch
                    )
                    if not obj_doc:
                        raise ValueError(f"ObjectType {obj_type.object_type_id} not found")

            # 참조된 액션 타입 검증
            if data.referenced_actions:
                for ref in data.referenced_actions:
                    ref_doc = await tdb.get_document(
                        f"ActionType_{ref.action_type_id}",
                        db=self.db_name,
                        branch=branch
                    )
                    if not ref_doc:
                        raise ValueError(f"Referenced ActionType {ref.action_type_id} not found")

            # 버전 해시 생성
            version_hash = self._generate_version_hash(data)

            # Terminus DB 문서 생성
            doc = {
                "@type": "ActionType",
                "@id": f"ActionType_{data.name}",
                "id": self._generate_id(),
                "name": data.name,
                "displayName": data.display_name,
                "description": data.description or "",
                "category": data.category.value,
                "transformationType": data.transformation_type.value,
                "transformationTypeRef": data.transformation_type_ref,
                "applicableObjectTypes": [
                    {
                        "objectTypeId": obj.object_type_id,
                        "role": obj.role,
                        "required": obj.required,
                        "description": obj.description
                    }
                    for obj in data.applicable_object_types
                ],
                "parameterSchema": {
                    "schema": data.parameter_schema.schema,
                    "examples": data.parameter_schema.examples,
                    "uiHints": data.parameter_schema.ui_hints
                } if data.parameter_schema else None,
                "configuration": data.configuration or {},
                "referencedActions": [
                    {
                        "actionTypeId": ref.action_type_id,
                        "version": ref.version,
                        "description": ref.description
                    }
                    for ref in (data.referenced_actions or [])
                ],
                "requiredPermissions": data.required_permissions or [],
                "tags": data.tags or [],
                "metadata": data.metadata or {},
                "isSystem": False,
                "isDeprecated": False,
                "version": 1,
                "versionHash": version_hash,
                "createdBy": user_id,
                "createdAt": datetime.utcnow().isoformat(),
                "modifiedBy": user_id,
                "modifiedAt": datetime.utcnow().isoformat()
            }

            # Terminus DB에 저장
            await tdb.insert_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Create ActionType {data.name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"action_types:{branch}")

            result = self._doc_to_action_type(doc)

            # 이벤트 발행
            if self.event_publisher:
                await self._publish_schema_changed_event(
                    branch=branch,
                    resource_type="ActionType",
                    resource_id=result.id,
                    operation="create",
                    author=user_id,
                    version_hash=version_hash
                )

            return result

    async def list_action_types(
        self,
        branch: str,
        category: Optional[ActionCategory] = None,
        transformation_type: Optional[TransformationType] = None,
        applicable_object_type: Optional[str] = None
    ) -> List[ActionType]:
        """Action Type 목록 조회"""
        cache_key = f"action_types:{branch}:{category or 'all'}:{transformation_type or 'all'}:{applicable_object_type or 'all'}"

        # 캐시 확인
        cached = await self.cache.get(cache_key)
        if cached:
            return [ActionType(**at) for at in cached]

        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 모든 ActionType 조회
            docs = await tdb.get_all_documents(
                doc_type="ActionType",
                db=self.db_name,
                branch=branch
            )

            action_types = []
            for doc in docs:
                at = self._doc_to_action_type(doc)

                # 필터링
                if category and at.category != category:
                    continue
                if transformation_type and at.transformation_type != transformation_type:
                    continue
                if applicable_object_type:
                    obj_types = {obj.object_type_id for obj in at.applicable_object_types}
                    if applicable_object_type not in obj_types and "*" not in obj_types:
                        continue

                action_types.append(at)

            # 캐시 저장
            await self.cache.set(
                cache_key,
                [at.model_dump() for at in action_types],
                version=f"{branch}_action_types"
            )

            return action_types

    async def get_action_type(
        self,
        branch: str,
        action_name: str
    ) -> Optional[ActionType]:
        """특정 Action Type 조회"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            doc = await tdb.get_document(
                f"ActionType_{action_name}",
                db=self.db_name,
                branch=branch
            )

            return self._doc_to_action_type(doc) if doc else None

    async def update_action_type(
        self,
        branch: str,
        action_name: str,
        data: ActionTypeUpdate,
        user_id: str = "system"
    ) -> ActionType:
        """Action Type 수정"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 기존 문서 조회
            doc = await tdb.get_document(
                f"ActionType_{action_name}",
                db=self.db_name,
                branch=branch
            )

            if not doc:
                raise ValueError(f"ActionType {action_name} not found")

            # 업데이트 적용
            update_data = data.model_dump(exclude_unset=True)

            # 간단한 필드 업데이트
            for key in ["display_name", "description", "transformation_type_ref",
                       "configuration", "required_permissions", "tags", "metadata", "is_deprecated"]:
                if key in update_data and update_data[key] is not None:
                    camel_key = self._to_camel_case(key)
                    doc[camel_key] = update_data[key]

            # transformation_type 업데이트
            if "transformation_type" in update_data and update_data["transformation_type"]:
                doc["transformationType"] = update_data["transformation_type"].value

            # applicable_object_types 업데이트
            if "applicable_object_types" in update_data and update_data["applicable_object_types"]:
                doc["applicableObjectTypes"] = [
                    {
                        "objectTypeId": obj.object_type_id,
                        "role": obj.role,
                        "required": obj.required,
                        "description": obj.description
                    }
                    for obj in update_data["applicable_object_types"]
                ]

            # parameter_schema 업데이트
            if "parameter_schema" in update_data and update_data["parameter_schema"]:
                doc["parameterSchema"] = {
                    "schema": update_data["parameter_schema"].schema,
                    "examples": update_data["parameter_schema"].examples,
                    "uiHints": update_data["parameter_schema"].ui_hints
                }

            # referenced_actions 업데이트
            if "referenced_actions" in update_data and update_data["referenced_actions"]:
                doc["referencedActions"] = [
                    {
                        "actionTypeId": ref.action_type_id,
                        "version": ref.version,
                        "description": ref.description
                    }
                    for ref in update_data["referenced_actions"]
                ]

            # 메타데이터 업데이트
            doc["version"] = doc.get("version", 1) + 1
            doc["modifiedBy"] = user_id
            doc["modifiedAt"] = datetime.utcnow().isoformat()
            doc["versionHash"] = self._generate_version_hash(doc)

            # Terminus DB에 업데이트
            await tdb.update_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Update ActionType {action_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"action_types:{branch}")

            result = self._doc_to_action_type(doc)

            # 이벤트 발행
            if self.event_publisher:
                await self._publish_schema_changed_event(
                    branch=branch,
                    resource_type="ActionType",
                    resource_id=result.id,
                    operation="update",
                    author=user_id,
                    version_hash=doc["versionHash"],
                    changes=update_data
                )

            return result

    async def delete_action_type(
        self,
        branch: str,
        action_name: str,
        user_id: str = "system"
    ) -> bool:
        """Action Type 삭제"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 문서 존재 확인
            doc = await tdb.get_document(
                f"ActionType_{action_name}",
                db=self.db_name,
                branch=branch
            )

            if not doc:
                return False

            # 다른 액션 타입이 참조하고 있는지 확인
            all_action_types = await tdb.get_all_documents(
                doc_type="ActionType",
                db=self.db_name,
                branch=branch
            )

            for at_doc in all_action_types:
                if at_doc["@id"] == f"ActionType_{action_name}":
                    continue

                referenced = at_doc.get("referencedActions", [])
                for ref in referenced:
                    if ref.get("actionTypeId") == action_name:
                        raise ValueError(f"ActionType {action_name} is referenced by {at_doc['name']}")

            # Terminus DB에서 삭제
            await tdb.delete_document(
                f"ActionType_{action_name}",
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Delete ActionType {action_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"action_types:{branch}")

            # 이벤트 발행
            if self.event_publisher:
                await self._publish_schema_changed_event(
                    branch=branch,
                    resource_type="ActionType",
                    resource_id=action_name,
                    operation="delete",
                    author=user_id
                )

            return True

    def _doc_to_action_type(self, doc: Dict[str, Any]) -> ActionType:
        """Terminus DB 문서를 ActionType 도메인 모델로 변환"""
        # applicable_object_types 변환
        applicable_object_types = []
        for obj_doc in doc.get("applicableObjectTypes", []):
            applicable_object_types.append(ApplicableObjectType(
                object_type_id=obj_doc["objectTypeId"],
                role=obj_doc.get("role", "primary"),
                required=obj_doc.get("required", True),
                description=obj_doc.get("description")
            ))

        # parameter_schema 변환
        parameter_schema = None
        if doc.get("parameterSchema"):
            ps_doc = doc["parameterSchema"]
            parameter_schema = ParameterSchema(
                schema=ps_doc["schema"],
                examples=ps_doc.get("examples", []),
                ui_hints=ps_doc.get("uiHints")
            )

        # referenced_actions 변환
        referenced_actions = []
        for ref_doc in doc.get("referencedActions", []):
            referenced_actions.append(ActionTypeReference(
                action_type_id=ref_doc["actionTypeId"],
                version=ref_doc.get("version"),
                description=ref_doc.get("description")
            ))

        return ActionType(
            id=doc["id"],
            name=doc["name"],
            display_name=doc["displayName"],
            description=doc.get("description", ""),
            category=ActionCategory(doc["category"]),
            transformation_type=TransformationType(doc["transformationType"]),
            transformation_type_ref=doc.get("transformationTypeRef"),
            applicable_object_types=applicable_object_types,
            parameter_schema=parameter_schema,
            configuration=doc.get("configuration", {}),
            referenced_actions=referenced_actions,
            required_permissions=doc.get("requiredPermissions", []),
            tags=doc.get("tags", []),
            metadata=doc.get("metadata", {}),
            is_system=doc.get("isSystem", False),
            is_deprecated=doc.get("isDeprecated", False),
            version=doc.get("version", 1),
            version_hash=doc["versionHash"],
            created_by=doc["createdBy"],
            created_at=datetime.fromisoformat(doc["createdAt"]),
            modified_by=doc["modifiedBy"],
            modified_at=datetime.fromisoformat(doc["modifiedAt"])
        )

    async def validate_action_type(
        self,
        branch: str,
        data: ActionTypeCreate
    ) -> Dict[str, Any]:
        """Action Type 유효성 검증 - 메타데이터만 검증"""
        # ActionType 생성 데이터로 임시 ActionType 객체 생성
        temp_action_type = ActionType(
            id="temp",
            name=data.name,
            display_name=data.display_name,
            description=data.description or "",
            category=data.category,
            transformation_type=data.transformation_type,
            transformation_type_ref=data.transformation_type_ref,
            applicable_object_types=data.applicable_object_types,
            parameter_schema=data.parameter_schema,
            configuration=data.configuration or {},
            referenced_actions=data.referenced_actions or [],
            required_permissions=data.required_permissions or [],
            tags=data.tags or [],
            metadata=data.metadata or {},
            is_system=False,
            is_deprecated=False,
            version=1,
            version_hash="temp",
            created_by="system",
            created_at=datetime.utcnow(),
            modified_by="system",
            modified_at=datetime.utcnow()
        )

        # 유효성 검증
        errors = ActionTypeValidator.validate(temp_action_type)

        # 추가 검증: 적용 가능한 객체 타입 존재 여부
        for obj_type in data.applicable_object_types:
            if obj_type.object_type_id != "*":
                exists = await self.get_object_type(branch, obj_type.object_type_id)
                if not exists:
                    errors.append(f"ObjectType '{obj_type.object_type_id}' not found")

        # 추가 검증: 참조된 액션 타입 존재 여부
        if data.referenced_actions:
            for ref in data.referenced_actions:
                exists = await self.get_action_type(branch, ref.action_type_id)
                if not exists:
                    errors.append(f"Referenced ActionType '{ref.action_type_id}' not found")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }

    # ===== Function Type CRUD Operations =====

    async def create_function_type(
        self,
        branch: str,
        data: FunctionTypeCreate,
        user_id: str = "system"
    ) -> FunctionType:
        """Function Type 생성"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # ID와 해시 생성
            function_type_id = self._generate_id()
            version_hash = self._generate_version_hash(data)

            # TerminusDB 문서 형식으로 변환
            doc = {
                "@type": "FunctionType",
                "id": function_type_id,
                "name": data.name,
                "displayName": data.display_name,
                "description": data.description or "",
                "category": data.category.value,

                # Function signature
                "parameters": [
                    {
                        "name": param.name,
                        "displayName": param.display_name,
                        "description": param.description,
                        "direction": param.direction.value,
                        "dataTypeId": param.data_type_id,
                        "semanticTypeId": param.semantic_type_id,
                        "structTypeId": param.struct_type_id,
                        "isRequired": param.is_required,
                        "isArray": param.is_array,
                        "defaultValue": param.default_value,
                        "validationRules": param.validation_rules or {},
                        "metadata": param.metadata,
                        "sortOrder": param.sort_order
                    }
                    for param in data.parameters
                ],
                "returnType": {
                    "dataTypeId": data.return_type.data_type_id,
                    "semanticTypeId": data.return_type.semantic_type_id,
                    "structTypeId": data.return_type.struct_type_id,
                    "isArray": data.return_type.is_array,
                    "isNullable": data.return_type.is_nullable,
                    "description": data.return_type.description,
                    "metadata": data.return_type.metadata
                },

                # Runtime configuration
                "runtimeConfig": {
                    "runtime": data.runtime_config.runtime.value,
                    "version": data.runtime_config.version,
                    "timeoutMs": data.runtime_config.timeout_ms,
                    "memoryMb": data.runtime_config.memory_mb,
                    "cpuCores": data.runtime_config.cpu_cores,
                    "maxRetries": data.runtime_config.max_retries,
                    "retryDelayMs": data.runtime_config.retry_delay_ms,
                    "environmentVars": data.runtime_config.environment_vars,
                    "dependencies": data.runtime_config.dependencies,
                    "resourceLimits": data.runtime_config.resource_limits
                },

                # Behavioral characteristics
                "behavior": {
                    "isDeterministic": data.behavior.is_deterministic if data.behavior else True,
                    "isStateless": data.behavior.is_stateless if data.behavior else True,
                    "isCacheable": data.behavior.is_cacheable if data.behavior else True,
                    "isParallelizable": data.behavior.is_parallelizable if data.behavior else True,
                    "hasSideEffects": data.behavior.has_side_effects if data.behavior else False,
                    "isExpensive": data.behavior.is_expensive if data.behavior else False,
                    "cacheTtlSeconds": data.behavior.cache_ttl_seconds if data.behavior else None
                },

                # Implementation and documentation
                "implementationRef": data.implementation_ref,
                "functionBody": data.function_body,
                "examples": [
                    {
                        "name": ex.name,
                        "description": ex.description,
                        "inputValues": ex.input_values,
                        "expectedOutput": ex.expected_output,
                        "explanation": ex.explanation
                    }
                    for ex in (data.examples or [])
                ],
                "tags": data.tags or [],

                # Access control
                "isPublic": data.is_public if data.is_public is not None else True,
                "allowedRoles": data.allowed_roles or [],
                "allowedUsers": data.allowed_users or [],

                # Metadata
                "metadata": data.metadata or {},
                "isSystem": False,
                "isDeprecated": False,

                # Version management
                "version": "1.0.0",
                "versionHash": version_hash,
                "previousVersionId": None,

                # Audit fields
                "createdBy": user_id,
                "createdAt": datetime.utcnow().isoformat(),
                "modifiedBy": user_id,
                "modifiedAt": datetime.utcnow().isoformat(),

                # Branch management
                "branchId": None,
                "isBranchSpecific": False
            }

            # TerminusDB에 저장
            await tdb.insert_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Create FunctionType {data.name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"function_types:{branch}")

            return self._doc_to_function_type(doc)

    async def list_function_types(
        self,
        branch: str,
        category: Optional[FunctionCategory] = None,
        runtime: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[FunctionType]:
        """Function Type 목록 조회"""
        cache_key = f"function_types:{branch}:{category or 'all'}:{runtime or 'all'}:{':'.join(tags or [])}"

        # 캐시 확인
        cached = await self.cache.get(cache_key)
        if cached:
            return [FunctionType(**ft) for ft in cached]

        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # WOQL 쿼리로 Function Type 조회
            query = {
                "@type": "FunctionType"
            }
            if category:
                query["category"] = category.value
            if runtime:
                query["runtimeConfig.runtime"] = runtime
            if tags:
                query["tags"] = {"$in": tags}

            docs = await tdb.query_documents(
                query,
                db=self.db_name,
                branch=branch
            )

            function_types = [self._doc_to_function_type(doc) for doc in docs]

            # 캐시 저장
            await self.cache.set(
                cache_key,
                [ft.model_dump() for ft in function_types],
                version=f"{branch}_function_types"
            )

            return function_types

    async def get_function_type(
        self,
        branch: str,
        function_name: str
    ) -> Optional[FunctionType]:
        """특정 Function Type 조회"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # ID로 조회
            docs = await tdb.query_documents(
                {"@type": "FunctionType", "name": function_name},
                db=self.db_name,
                branch=branch
            )

            return self._doc_to_function_type(docs[0]) if docs else None

    async def update_function_type(
        self,
        branch: str,
        function_name: str,
        data: FunctionTypeUpdate,
        user_id: str = "system"
    ) -> FunctionType:
        """Function Type 수정"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 기존 문서 조회
            docs = await tdb.query_documents(
                {"@type": "FunctionType", "name": function_name},
                db=self.db_name,
                branch=branch
            )

            if not docs:
                raise ValueError(f"FunctionType {function_name} not found")

            doc = docs[0]

            # 업데이트 적용
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                if value is not None:
                    if key == "parameters" and value:
                        doc["parameters"] = [
                            {
                                "name": param.name,
                                "displayName": param.display_name,
                                "description": param.description,
                                "direction": param.direction.value,
                                "dataTypeId": param.data_type_id,
                                "semanticTypeId": param.semantic_type_id,
                                "structTypeId": param.struct_type_id,
                                "isRequired": param.is_required,
                                "isArray": param.is_array,
                                "defaultValue": param.default_value,
                                "validationRules": param.validation_rules or {},
                                "metadata": param.metadata,
                                "sortOrder": param.sort_order
                            }
                            for param in value
                        ]
                    elif key == "return_type" and value:
                        doc["returnType"] = {
                            "dataTypeId": value.data_type_id,
                            "semanticTypeId": value.semantic_type_id,
                            "structTypeId": value.struct_type_id,
                            "isArray": value.is_array,
                            "isNullable": value.is_nullable,
                            "description": value.description,
                            "metadata": value.metadata
                        }
                    elif key == "runtime_config" and value:
                        doc["runtimeConfig"] = {
                            "runtime": value.runtime.value,
                            "version": value.version,
                            "timeoutMs": value.timeout_ms,
                            "memoryMb": value.memory_mb,
                            "cpuCores": value.cpu_cores,
                            "maxRetries": value.max_retries,
                            "retryDelayMs": value.retry_delay_ms,
                            "environmentVars": value.environment_vars,
                            "dependencies": value.dependencies,
                            "resourceLimits": value.resource_limits
                        }
                    elif key == "behavior" and value:
                        doc["behavior"] = {
                            "isDeterministic": value.is_deterministic,
                            "isStateless": value.is_stateless,
                            "isCacheable": value.is_cacheable,
                            "isParallelizable": value.is_parallelizable,
                            "hasSideEffects": value.has_side_effects,
                            "isExpensive": value.is_expensive,
                            "cacheTtlSeconds": value.cache_ttl_seconds
                        }
                    elif key == "examples" and value:
                        doc["examples"] = [
                            {
                                "name": ex.name,
                                "description": ex.description,
                                "inputValues": ex.input_values,
                                "expectedOutput": ex.expected_output,
                                "explanation": ex.explanation
                            }
                            for ex in value
                        ]
                    else:
                        camel_key = self._to_camel_case(key)
                        if hasattr(value, 'value'):  # Enum 처리
                            doc[camel_key] = value.value
                        else:
                            doc[camel_key] = value

            # 버전 정보 업데이트
            doc["versionHash"] = self._generate_version_hash(update_data)
            doc["modifiedBy"] = user_id
            doc["modifiedAt"] = datetime.utcnow().isoformat()

            # TerminusDB에 저장
            await tdb.replace_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Update FunctionType {function_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"function_types:{branch}")

            return self._doc_to_function_type(doc)

    async def delete_function_type(
        self,
        branch: str,
        function_name: str,
        user_id: str = "system"
    ) -> bool:
        """Function Type 삭제"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 기존 문서 조회
            docs = await tdb.query_documents(
                {"@type": "FunctionType", "name": function_name},
                db=self.db_name,
                branch=branch
            )

            if not docs:
                raise ValueError(f"FunctionType {function_name} not found")

            doc = docs[0]

            # 문서 삭제
            await tdb.delete_document(
                doc["@id"],
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Delete FunctionType {function_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"function_types:{branch}")

            return True

    def _doc_to_function_type(self, doc: Dict[str, Any]) -> FunctionType:
        """TerminusDB 문서를 FunctionType 객체로 변환"""

        # Parameters 변환
        parameters = []
        for param_doc in doc.get("parameters", []):
            parameters.append(FunctionParameter(
                name=param_doc["name"],
                display_name=param_doc["displayName"],
                description=param_doc.get("description"),
                direction=param_doc["direction"],
                data_type_id=param_doc["dataTypeId"],
                semantic_type_id=param_doc.get("semanticTypeId"),
                struct_type_id=param_doc.get("structTypeId"),
                is_required=param_doc.get("isRequired", True),
                is_array=param_doc.get("isArray", False),
                default_value=param_doc.get("defaultValue"),
                validation_rules=param_doc.get("validationRules"),
                metadata=param_doc.get("metadata", {}),
                sort_order=param_doc.get("sortOrder", 0)
            ))

        # Return type 변환
        rt_doc = doc["returnType"]
        return_type = ReturnType(
            data_type_id=rt_doc["dataTypeId"],
            semantic_type_id=rt_doc.get("semanticTypeId"),
            struct_type_id=rt_doc.get("structTypeId"),
            is_array=rt_doc.get("isArray", False),
            is_nullable=rt_doc.get("isNullable", True),
            description=rt_doc.get("description"),
            metadata=rt_doc.get("metadata", {})
        )

        # Runtime config 변환
        rc_doc = doc["runtimeConfig"]
        runtime_config = RuntimeConfig(
            runtime=rc_doc["runtime"],
            version=rc_doc.get("version"),
            timeout_ms=rc_doc.get("timeoutMs", 30000),
            memory_mb=rc_doc.get("memoryMb", 512),
            cpu_cores=rc_doc.get("cpuCores", 1.0),
            max_retries=rc_doc.get("maxRetries", 3),
            retry_delay_ms=rc_doc.get("retryDelayMs", 1000),
            environment_vars=rc_doc.get("environmentVars", {}),
            dependencies=rc_doc.get("dependencies", []),
            resource_limits=rc_doc.get("resourceLimits", {})
        )

        # Behavior 변환
        behavior_doc = doc.get("behavior", {})
        behavior = FunctionBehavior(
            is_deterministic=behavior_doc.get("isDeterministic", True),
            is_stateless=behavior_doc.get("isStateless", True),
            is_cacheable=behavior_doc.get("isCacheable", True),
            is_parallelizable=behavior_doc.get("isParallelizable", True),
            has_side_effects=behavior_doc.get("hasSideEffects", False),
            is_expensive=behavior_doc.get("isExpensive", False),
            cache_ttl_seconds=behavior_doc.get("cacheTtlSeconds")
        )

        # Examples 변환
        examples = []
        for ex_doc in doc.get("examples", []):
            examples.append(FunctionExample(
                name=ex_doc["name"],
                description=ex_doc.get("description"),
                input_values=ex_doc["inputValues"],
                expected_output=ex_doc["expectedOutput"],
                explanation=ex_doc.get("explanation")
            ))

        return FunctionType(
            id=doc["id"],
            name=doc["name"],
            display_name=doc["displayName"],
            description=doc.get("description", ""),
            category=FunctionCategory(doc["category"]),
            parameters=parameters,
            return_type=return_type,
            runtime_config=runtime_config,
            behavior=behavior,
            implementation_ref=doc.get("implementationRef"),
            function_body=doc.get("functionBody"),
            examples=examples,
            tags=doc.get("tags", []),
            is_public=doc.get("isPublic", True),
            allowed_roles=doc.get("allowedRoles", []),
            allowed_users=doc.get("allowedUsers", []),
            metadata=doc.get("metadata", {}),
            is_system=doc.get("isSystem", False),
            is_deprecated=doc.get("isDeprecated", False),
            version=doc.get("version", "1.0.0"),
            version_hash=doc["versionHash"],
            previous_version_id=doc.get("previousVersionId"),
            created_by=doc["createdBy"],
            created_at=datetime.fromisoformat(doc["createdAt"].replace('Z', '+00:00')),
            modified_by=doc["modifiedBy"],
            modified_at=datetime.fromisoformat(doc["modifiedAt"].replace('Z', '+00:00')),
            branch_id=doc.get("branchId"),
            is_branch_specific=doc.get("isBranchSpecific", False)
        )

    async def validate_function_type(
        self,
        branch: str,
        data: FunctionTypeCreate
    ) -> Dict[str, Any]:
        """Function Type 유효성 검증"""
        # FunctionType 생성 데이터로 임시 FunctionType 객체 생성
        temp_function_type = FunctionType(
            id="temp",
            name=data.name,
            display_name=data.display_name,
            description=data.description or "",
            category=data.category,
            parameters=data.parameters,
            return_type=data.return_type,
            runtime_config=data.runtime_config,
            behavior=data.behavior or FunctionBehavior(),
            implementation_ref=data.implementation_ref,
            function_body=data.function_body,
            examples=data.examples or [],
            tags=data.tags or [],
            is_public=data.is_public if data.is_public is not None else True,
            allowed_roles=data.allowed_roles or [],
            allowed_users=data.allowed_users or [],
            metadata=data.metadata or {},
            is_system=False,
            is_deprecated=False,
            version="1.0.0",
            version_hash="temp",
            created_by="system",
            created_at=datetime.now(timezone.utc),
            modified_by="system",
            modified_at=datetime.now(timezone.utc)
        )

        # 유효성 검증
        errors = FunctionTypeValidator.validate_function_type(temp_function_type)

        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }

    # ===== Data Type CRUD Operations =====

    async def create_data_type(
        self,
        branch: str,
        data: DataTypeCreate,
        user_id: str = "system"
    ) -> DataType:
        """Data Type 생성"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # ID와 해시 생성
            data_type_id = self._generate_id()
            version_hash = self._generate_version_hash(data)

            # TerminusDB 문서 형식으로 변환
            doc = {
                "@type": "DataType",
                "id": data_type_id,
                "name": data.name,
                "displayName": data.display_name,
                "description": data.description or "",
                "category": data.category.value,
                "format": data.format.value,

                # Type constraints
                "constraints": [
                    {
                        "constraintType": constraint.constraint_type,
                        "value": constraint.value,
                        "message": constraint.message
                    }
                    for constraint in (data.constraints or [])
                ],
                "defaultValue": data.default_value,
                "isNullable": data.is_nullable if data.is_nullable is not None else True,

                # Complex type configuration
                "isArrayType": data.is_array_type if data.is_array_type is not None else False,
                "arrayItemType": data.array_item_type,
                "mapKeyType": data.map_key_type,
                "mapValueType": data.map_value_type,

                # Metadata and operations
                "metadata": data.metadata or {},
                "supportedOperations": data.supported_operations or [],
                "compatibleTypes": data.compatible_types or [],
                "tags": data.tags or [],

                # Access control
                "isPublic": data.is_public if data.is_public is not None else True,
                "allowedRoles": data.allowed_roles or [],
                "allowedUsers": data.allowed_users or [],

                # OMS-specific fields
                "isSystem": False,
                "isDeprecated": False,
                "deprecationMessage": None,

                # Version management
                "version": "1.0.0",
                "versionHash": version_hash,
                "previousVersionId": None,

                # Audit fields
                "createdBy": user_id,
                "createdAt": datetime.utcnow().isoformat(),
                "modifiedBy": user_id,
                "modifiedAt": datetime.utcnow().isoformat(),

                # Branch management
                "branchId": None,
                "isBranchSpecific": False
            }

            # TerminusDB에 저장
            await tdb.insert_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Create DataType {data.name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"data_types:{branch}")

            return self._doc_to_data_type(doc)

    async def list_data_types(
        self,
        branch: str,
        category: Optional[DataTypeCategory] = None,
        format: Optional[DataTypeFormat] = None,
        tags: Optional[List[str]] = None
    ) -> List[DataType]:
        """Data Type 목록 조회"""
        cache_key = f"data_types:{branch}:{category or 'all'}:{format or 'all'}:{':'.join(tags or [])}"

        # 캐시 확인
        cached = await self.cache.get(cache_key)
        if cached:
            return [DataType(**dt) for dt in cached]

        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # WOQL 쿼리로 Data Type 조회
            query = {
                "@type": "DataType"
            }
            if category:
                query["category"] = category.value
            if format:
                query["format"] = format.value
            if tags:
                query["tags"] = {"$in": tags}

            docs = await tdb.query_documents(
                query,
                db=self.db_name,
                branch=branch
            )

            data_types = [self._doc_to_data_type(doc) for doc in docs]

            # 캐시 저장
            await self.cache.set(
                cache_key,
                [dt.model_dump() for dt in data_types],
                version=f"{branch}_data_types"
            )

            return data_types

    async def get_data_type(
        self,
        branch: str,
        data_type_name: str
    ) -> Optional[DataType]:
        """특정 Data Type 조회"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # Name으로 조회
            docs = await tdb.query_documents(
                {"@type": "DataType", "name": data_type_name},
                db=self.db_name,
                branch=branch
            )

            return self._doc_to_data_type(docs[0]) if docs else None

    async def update_data_type(
        self,
        branch: str,
        data_type_name: str,
        data: DataTypeUpdate,
        user_id: str = "system"
    ) -> DataType:
        """Data Type 수정"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 기존 문서 조회
            docs = await tdb.query_documents(
                {"@type": "DataType", "name": data_type_name},
                db=self.db_name,
                branch=branch
            )

            if not docs:
                raise ValueError(f"DataType {data_type_name} not found")

            doc = docs[0]

            # 업데이트 적용
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                if value is not None:
                    if key == "constraints" and value:
                        doc["constraints"] = [
                            {
                                "constraintType": constraint.constraint_type,
                                "value": constraint.value,
                                "message": constraint.message
                            }
                            for constraint in value
                        ]
                    else:
                        camel_key = self._to_camel_case(key)
                        if hasattr(value, 'value'):  # Enum 처리
                            doc[camel_key] = value.value
                        else:
                            doc[camel_key] = value

            # 버전 정보 업데이트
            doc["versionHash"] = self._generate_version_hash(update_data)
            doc["modifiedBy"] = user_id
            doc["modifiedAt"] = datetime.utcnow().isoformat()

            # TerminusDB에 저장
            await tdb.replace_document(
                doc,
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Update DataType {data_type_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"data_types:{branch}")

            return self._doc_to_data_type(doc)

    async def delete_data_type(
        self,
        branch: str,
        data_type_name: str,
        user_id: str = "system"
    ) -> bool:
        """Data Type 삭제"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 기존 문서 조회
            docs = await tdb.query_documents(
                {"@type": "DataType", "name": data_type_name},
                db=self.db_name,
                branch=branch
            )

            if not docs:
                raise ValueError(f"DataType {data_type_name} not found")

            doc = docs[0]

            # 시스템 타입은 삭제 불가
            if doc.get("isSystem", False):
                raise ValueError(f"Cannot delete system DataType {data_type_name}")

            # 문서 삭제
            await tdb.delete_document(
                doc["@id"],
                db=self.db_name,
                branch=branch,
                author=user_id,
                message=f"Delete DataType {data_type_name}"
            )

            # 캐시 무효화
            await self.cache.invalidate(f"data_types:{branch}")

            return True

    def _doc_to_data_type(self, doc: Dict[str, Any]) -> DataType:
        """TerminusDB 문서를 DataType 객체로 변환"""

        # Constraints 변환
        constraints = []
        for constraint_doc in doc.get("constraints", []):
            constraints.append(TypeConstraint(
                constraint_type=constraint_doc["constraintType"],
                value=constraint_doc["value"],
                message=constraint_doc.get("message")
            ))

        return DataType(
            id=doc["id"],
            name=doc["name"],
            display_name=doc["displayName"],
            description=doc.get("description", ""),
            category=DataTypeCategory(doc["category"]),
            format=DataTypeFormat(doc["format"]),
            constraints=constraints,
            default_value=doc.get("defaultValue"),
            is_nullable=doc.get("isNullable", True),
            is_array_type=doc.get("isArrayType", False),
            array_item_type=doc.get("arrayItemType"),
            map_key_type=doc.get("mapKeyType"),
            map_value_type=doc.get("mapValueType"),
            metadata=doc.get("metadata", {}),
            supported_operations=doc.get("supportedOperations", []),
            compatible_types=doc.get("compatibleTypes", []),
            is_system=doc.get("isSystem", False),
            is_deprecated=doc.get("isDeprecated", False),
            deprecation_message=doc.get("deprecationMessage"),
            tags=doc.get("tags", []),
            version=doc.get("version", "1.0.0"),
            version_hash=doc["versionHash"],
            previous_version_id=doc.get("previousVersionId"),
            created_by=doc["createdBy"],
            created_at=datetime.fromisoformat(doc["createdAt"].replace('Z', '+00:00')),
            modified_by=doc["modifiedBy"],
            modified_at=datetime.fromisoformat(doc["modifiedAt"].replace('Z', '+00:00')),
            branch_id=doc.get("branchId"),
            is_branch_specific=doc.get("isBranchSpecific", False),
            is_public=doc.get("isPublic", True),
            allowed_roles=doc.get("allowedRoles", []),
            allowed_users=doc.get("allowedUsers", [])
        )

    async def validate_data_type(
        self,
        branch: str,
        data: DataTypeCreate
    ) -> Dict[str, Any]:
        """Data Type 유효성 검증"""
        # DataType 생성 데이터로 임시 DataType 객체 생성
        temp_data_type = DataType(
            id="temp",
            name=data.name,
            display_name=data.display_name,
            description=data.description or "",
            category=data.category,
            format=data.format,
            constraints=data.constraints or [],
            default_value=data.default_value,
            is_nullable=data.is_nullable if data.is_nullable is not None else True,
            is_array_type=data.is_array_type if data.is_array_type is not None else False,
            array_item_type=data.array_item_type,
            map_key_type=data.map_key_type,
            map_value_type=data.map_value_type,
            metadata=data.metadata or {},
            supported_operations=data.supported_operations or [],
            compatible_types=data.compatible_types or [],
            tags=data.tags or [],
            is_public=data.is_public if data.is_public is not None else True,
            allowed_roles=data.allowed_roles or [],
            allowed_users=data.allowed_users or [],
            is_system=False,
            is_deprecated=False,
            version="1.0.0",
            version_hash="temp",
            created_by="system",
            created_at=datetime.now(timezone.utc),
            modified_by="system",
            modified_at=datetime.now(timezone.utc)
        )

        # 유효성 검증
        errors = temp_data_type.validate_schema()

        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }

