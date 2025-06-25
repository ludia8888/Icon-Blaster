"""
GraphQL Resolvers - 섹션 10.2의 GraphQL API 구현
"""
import logging
import os
from typing import List, Optional

import httpx
import strawberry

from api.gateway.auth import User

from api.graphql.schema import (
    ActionCategoryEnum,
    ActionType,
    ActionTypeInput,
    ActionTypeUpdateInput,
    ApplicableObjectType,
    Branch,
    BranchStatusEnum,
    DataType,
    DataTypeCategoryEnum,
    DataTypeFormatEnum,
    DataTypeInput,
    DataTypeUpdateInput,
    FunctionCategoryEnum,
    FunctionRuntimeEnum,
    FunctionType,
    FunctionTypeInput,
    FunctionTypeUpdateInput,
    HistoryEntry,
    Interface,
    LinkType,
    ObjectType,
    ObjectTypeConnection,
    ObjectTypeInput,
    ObjectTypeUpdateInput,
    ParameterSchema,
    Property,
    ResourceTypeEnum,
    SearchResult,
    SharedProperty,
    StatusEnum,
    TransformationTypeEnum,
    TypeClassEnum,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class ServiceClient:
    """마이크로서비스 클라이언트"""

    def __init__(self):
        self.schema_service_url = os.getenv("SCHEMA_SERVICE_URL", "http://schema-service:8000")
        self.branch_service_url = os.getenv("BRANCH_SERVICE_URL", "http://branch-service:8000")
        self.validation_service_url = os.getenv("VALIDATION_SERVICE_URL", "http://validation-service:8000")

    async def get_auth_headers(self, user: Optional[User]) -> dict:
        """인증 헤더 생성"""
        if user and hasattr(user, 'access_token'):
            return {"Authorization": f"Bearer {user.access_token}"}
        elif user:
            # Fallback to user_id for testing
            return {"Authorization": f"Bearer {user.user_id}"}
        return {}

    async def call_service(self, url: str, method: str = "GET", json_data: dict = None, user: Optional[User] = None):
        """서비스 호출"""
        headers = await self.get_auth_headers(user)
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, json=json_data, headers=headers)
            response.raise_for_status()
            return response.json()


service_client = ServiceClient()


@strawberry.type
class Query:
    """GraphQL Query 루트"""

    @strawberry.field
    async def object_types(
        self,
        info: strawberry.Info,
        branch: str = "main",
        status: Optional[StatusEnum] = None,
        type_class: Optional[TypeClassEnum] = None,
        interface: Optional[str] = None,
        search: Optional[str] = None,
        include_properties: bool = True,
        include_deprecated: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> ObjectTypeConnection:
        """ObjectType 목록 조회"""
        user = info.context.get("user")

        params = {
            "status": status.value if status else None,
            "type_class": type_class.value if type_class else None,
            "limit": limit,
            "offset": offset
        }

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/object-types"
        result = await service_client.call_service(url, "GET", params, user)

        # 데이터 변환
        object_types = []
        for item in result.get('data', []):
            object_type = ObjectType(
                id=item.get('id', ''),
                name=item.get('name', ''),
                displayName=item.get('displayName', ''),
                pluralDisplayName=item.get('pluralDisplayName'),
                description=item.get('description'),
                status=StatusEnum(item.get('status', 'active')),
                typeClass=TypeClassEnum(item.get('typeClass', 'object')),
                versionHash=item.get('versionHash', ''),
                createdBy=item.get('createdBy', ''),
                createdAt=item.get('createdAt'),
                modifiedBy=item.get('modifiedBy', ''),
                modifiedAt=item.get('modifiedAt'),
                parentTypes=item.get('parentTypes', []),
                interfaces=item.get('interfaces', []),
                isAbstract=item.get('isAbstract', False),
                icon=item.get('icon'),
                color=item.get('color')
            )

            # Properties 포함
            if include_properties and item.get('properties'):
                object_type.properties = [
                    Property(
                        id=prop.get('id', ''),
                        objectTypeId=prop.get('objectTypeId', ''),
                        name=prop.get('name', ''),
                        displayName=prop.get('displayName', ''),
                        dataType=prop.get('dataType', ''),
                        isRequired=prop.get('isRequired', False),
                        isUnique=prop.get('isUnique', False),
                        isPrimaryKey=prop.get('isPrimaryKey', False),
                        isSearchable=prop.get('isSearchable', False),
                        isIndexed=prop.get('isIndexed', False),
                        defaultValue=prop.get('defaultValue'),
                        description=prop.get('description'),
                        enumValues=prop.get('enumValues', []),
                        linkedObjectType=prop.get('linkedObjectType'),
                        status=StatusEnum(prop.get('status', 'active')),
                        versionHash=prop.get('versionHash', ''),
                        createdBy=prop.get('createdBy', ''),
                        createdAt=prop.get('createdAt'),
                        modifiedBy=prop.get('modifiedBy', ''),
                        modifiedAt=prop.get('modifiedAt')
                    ) for prop in item.get('properties', [])
                ]

            object_types.append(object_type)

        total_count = result.get('totalCount', len(object_types))
        has_next = offset + limit < total_count
        has_prev = offset > 0

        return ObjectTypeConnection(
            data=object_types,
            totalCount=total_count,
            hasNextPage=has_next,
            hasPreviousPage=has_prev
        )

    @strawberry.field
    async def object_type(
        self,
        info: strawberry.Info,
        id: str,
        branch: str = "main",
        include_properties: bool = True,
        include_actions: bool = False,
        include_metrics: bool = False
    ) -> Optional[ObjectType]:
        """ObjectType 상세 조회"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/object-types/{id}"
        try:
            result = await service_client.call_service(url, "GET", None, user)

            # 데이터 변환
            object_type = ObjectType(
                id=result.get('id', ''),
                name=result.get('name', ''),
                displayName=result.get('displayName', ''),
                pluralDisplayName=result.get('pluralDisplayName'),
                description=result.get('description'),
                status=StatusEnum(result.get('status', 'active')),
                typeClass=TypeClassEnum(result.get('typeClass', 'object')),
                versionHash=result.get('versionHash', ''),
                createdBy=result.get('createdBy', ''),
                createdAt=result.get('createdAt'),
                modifiedBy=result.get('modifiedBy', ''),
                modifiedAt=result.get('modifiedAt'),
                parentTypes=result.get('parentTypes', []),
                interfaces=result.get('interfaces', []),
                isAbstract=result.get('isAbstract', False),
                icon=result.get('icon'),
                color=result.get('color')
            )

            # Properties 포함
            if include_properties and result.get('properties'):
                object_type.properties = [
                    Property(
                        id=prop.get('id', ''),
                        objectTypeId=prop.get('objectTypeId', ''),
                        name=prop.get('name', ''),
                        displayName=prop.get('displayName', ''),
                        dataType=prop.get('dataType', ''),
                        isRequired=prop.get('isRequired', False),
                        isUnique=prop.get('isUnique', False),
                        isPrimaryKey=prop.get('isPrimaryKey', False),
                        isSearchable=prop.get('isSearchable', False),
                        isIndexed=prop.get('isIndexed', False),
                        defaultValue=prop.get('defaultValue'),
                        description=prop.get('description'),
                        enumValues=prop.get('enumValues', []),
                        linkedObjectType=prop.get('linkedObjectType'),
                        status=StatusEnum(prop.get('status', 'active')),
                        versionHash=prop.get('versionHash', ''),
                        createdBy=prop.get('createdBy', ''),
                        createdAt=prop.get('createdAt'),
                        modifiedBy=prop.get('modifiedBy', ''),
                        modifiedAt=prop.get('modifiedAt')
                    ) for prop in result.get('properties', [])
                ]

            return object_type

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    @strawberry.field
    async def properties(
        self,
        info: strawberry.Info,
        object_type_id: str,
        branch: str = "main",
        include_inherited: bool = False
    ) -> List[Property]:
        """Property 목록 조회"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/object-types/{object_type_id}/properties"
        result = await service_client.call_service(url, "GET", None, user)

        # 데이터 변환
        properties = []
        for prop in result.get('data', []):
            property_obj = Property(
                id=prop.get('id', ''),
                objectTypeId=prop.get('objectTypeId', ''),
                name=prop.get('name', ''),
                displayName=prop.get('displayName', ''),
                dataType=prop.get('dataType', ''),
                isRequired=prop.get('isRequired', False),
                isUnique=prop.get('isUnique', False),
                isPrimaryKey=prop.get('isPrimaryKey', False),
                isSearchable=prop.get('isSearchable', False),
                isIndexed=prop.get('isIndexed', False),
                defaultValue=prop.get('defaultValue'),
                description=prop.get('description'),
                enumValues=prop.get('enumValues', []),
                linkedObjectType=prop.get('linkedObjectType'),
                status=StatusEnum(prop.get('status', 'active')),
                versionHash=prop.get('versionHash', ''),
                createdBy=prop.get('createdBy', ''),
                createdAt=prop.get('createdAt'),
                modifiedBy=prop.get('modifiedBy', ''),
                modifiedAt=prop.get('modifiedAt')
            )
            properties.append(property_obj)

        return properties

    @strawberry.field
    async def shared_properties(
        self,
        info: strawberry.Info,
        branch: str = "main",
        data_type: Optional[str] = None,
        semantic_type: Optional[str] = None
    ) -> List[SharedProperty]:
        """SharedProperty 목록 조회"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/shared-properties"
        params = {}
        if data_type:
            params['data_type'] = data_type
        if semantic_type:
            params['semantic_type'] = semantic_type

        result = await service_client.call_service(url, "GET", params, user)

        # 데이터 변환
        shared_properties = []
        for sp in result.get('data', []):
            shared_prop = SharedProperty(
                id=sp.get('id', ''),
                name=sp.get('name', ''),
                displayName=sp.get('displayName', ''),
                description=sp.get('description'),
                dataType=sp.get('dataType', ''),
                semanticType=sp.get('semanticType'),
                defaultValue=sp.get('defaultValue'),
                enumValues=sp.get('enumValues', []),
                status=StatusEnum(sp.get('status', 'active')),
                versionHash=sp.get('versionHash', ''),
                createdBy=sp.get('createdBy', ''),
                createdAt=sp.get('createdAt'),
                modifiedBy=sp.get('modifiedBy', ''),
                modifiedAt=sp.get('modifiedAt')
            )
            shared_properties.append(shared_prop)

        return shared_properties

    @strawberry.field
    async def link_types(
        self,
        info: strawberry.Info,
        branch: str = "main",
        from_type: Optional[str] = None,
        to_type: Optional[str] = None,
        status: Optional[StatusEnum] = None
    ) -> List[LinkType]:
        """LinkType 목록 조회"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/link-types"
        params = {}
        if from_type:
            params['from_type'] = from_type
        if to_type:
            params['to_type'] = to_type
        if status:
            params['status'] = status.value

        result = await service_client.call_service(url, "GET", params, user)

        # 데이터 변환
        link_types = []
        for lt in result.get('data', []):
            link_type = LinkType(
                id=lt.get('id', ''),
                name=lt.get('name', ''),
                displayName=lt.get('displayName', ''),
                description=lt.get('description'),
                fromObjectType=lt.get('fromObjectType', ''),
                toObjectType=lt.get('toObjectType', ''),
                directionality=lt.get('directionality', 'directional'),
                fromCardinality=lt.get('fromCardinality', 'many'),
                toCardinality=lt.get('toCardinality', 'many'),
                status=StatusEnum(lt.get('status', 'active')),
                versionHash=lt.get('versionHash', ''),
                createdBy=lt.get('createdBy', ''),
                createdAt=lt.get('createdAt'),
                modifiedBy=lt.get('modifiedBy', ''),
                modifiedAt=lt.get('modifiedAt')
            )
            link_types.append(link_type)

        return link_types

    @strawberry.field
    async def link_type(
        self,
        info: strawberry.Info,
        id: str,
        branch: str = "main"
    ) -> Optional[LinkType]:
        """LinkType 상세 조회"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/link-types/{id}"
        try:
            result = await service_client.call_service(url, "GET", None, user)

            # 데이터 변환
            return LinkType(
                id=result.get('id', ''),
                name=result.get('name', ''),
                displayName=result.get('displayName', ''),
                description=result.get('description'),
                fromObjectType=result.get('fromObjectType', ''),
                toObjectType=result.get('toObjectType', ''),
                directionality=result.get('directionality', 'directional'),
                fromCardinality=result.get('fromCardinality', 'many'),
                toCardinality=result.get('toCardinality', 'many'),
                status=StatusEnum(result.get('status', 'active')),
                versionHash=result.get('versionHash', ''),
                createdBy=result.get('createdBy', ''),
                createdAt=result.get('createdAt'),
                modifiedBy=result.get('modifiedBy', ''),
                modifiedAt=result.get('modifiedAt')
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    @strawberry.field
    async def interfaces(
        self,
        info: strawberry.Info,
        branch: str = "main",
        search: Optional[str] = None
    ) -> List[Interface]:
        """Interface 목록 조회"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/interfaces"
        params = {}
        if search:
            params['search'] = search

        result = await service_client.call_service(url, "GET", params, user)

        # 데이터 변환
        interfaces = []
        for iface in result.get('data', []):
            interface = Interface(
                id=iface.get('id', ''),
                name=iface.get('name', ''),
                displayName=iface.get('displayName', ''),
                description=iface.get('description'),
                status=StatusEnum(iface.get('status', 'active')),
                versionHash=iface.get('versionHash', ''),
                createdBy=iface.get('createdBy', ''),
                createdAt=iface.get('createdAt'),
                modifiedBy=iface.get('modifiedBy', ''),
                modifiedAt=iface.get('modifiedAt')
            )

            # Properties 포함
            if iface.get('properties'):
                interface.properties = [
                    Property(
                        id=prop.get('id', ''),
                        objectTypeId=prop.get('objectTypeId', ''),
                        name=prop.get('name', ''),
                        displayName=prop.get('displayName', ''),
                        dataType=prop.get('dataType', ''),
                        isRequired=prop.get('isRequired', False),
                        isUnique=prop.get('isUnique', False),
                        isPrimaryKey=prop.get('isPrimaryKey', False),
                        isSearchable=prop.get('isSearchable', False),
                        isIndexed=prop.get('isIndexed', False),
                        defaultValue=prop.get('defaultValue'),
                        description=prop.get('description'),
                        enumValues=prop.get('enumValues', []),
                        linkedObjectType=prop.get('linkedObjectType'),
                        status=StatusEnum(prop.get('status', 'active')),
                        versionHash=prop.get('versionHash', ''),
                        createdBy=prop.get('createdBy', ''),
                        createdAt=prop.get('createdAt'),
                        modifiedBy=prop.get('modifiedBy', ''),
                        modifiedAt=prop.get('modifiedAt')
                    ) for prop in iface.get('properties', [])
                ]

            interfaces.append(interface)

        return interfaces

    @strawberry.field
    async def interface(
        self,
        info: strawberry.Info,
        id: str,
        branch: str = "main"
    ) -> Optional[Interface]:
        """Interface 상세 조회"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/interfaces/{id}"
        try:
            # TODO: 실제 데이터 변환 로직 구현
            _ = await service_client.call_service(url, "GET", None, user)
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    @strawberry.field
    async def branches(
        self,
        info: strawberry.Info,
        include_system: bool = False,
        status: Optional[BranchStatusEnum] = None
    ) -> List[Branch]:
        """Branch 목록 조회"""
        user = info.context.get("user")

        url = f"{service_client.branch_service_url}/api/v1/branches"
        params = {}
        if status:
            params['status'] = status.value
        if not include_system:
            params['exclude_system'] = True

        result = await service_client.call_service(url, "GET", params, user)

        # 데이터 변환
        branches = []
        for branch_data in result.get('data', []):
            branch = Branch(
                name=branch_data.get('name', ''),
                fromBranch=branch_data.get('fromBranch'),
                headHash=branch_data.get('headHash', ''),
                description=branch_data.get('description'),
                status=BranchStatusEnum(branch_data.get('status', 'active')),
                isProtected=branch_data.get('isProtected', False),
                createdBy=branch_data.get('createdBy', ''),
                createdAt=branch_data.get('createdAt'),
                lastModified=branch_data.get('lastModified'),
                commitsAhead=branch_data.get('commitsAhead', 0),
                commitsBehind=branch_data.get('commitsBehind', 0),
                hasPendingChanges=branch_data.get('hasPendingChanges', False)
            )
            branches.append(branch)

        return branches

    @strawberry.field
    async def branch(
        self,
        info: strawberry.Info,
        name: str
    ) -> Optional[Branch]:
        """Branch 상세 조회"""
        user = info.context.get("user")

        url = f"{service_client.branch_service_url}/api/v1/branches/{name}"
        try:
            result = await service_client.call_service(url, "GET", None, user)

            # 데이터 변환
            return Branch(
                name=result.get('name', ''),
                fromBranch=result.get('fromBranch'),
                headHash=result.get('headHash', ''),
                description=result.get('description'),
                status=BranchStatusEnum(result.get('status', 'active')),
                isProtected=result.get('isProtected', False),
                createdBy=result.get('createdBy', ''),
                createdAt=result.get('createdAt'),
                lastModified=result.get('lastModified'),
                commitsAhead=result.get('commitsAhead', 0),
                commitsBehind=result.get('commitsBehind', 0),
                hasPendingChanges=result.get('hasPendingChanges', False)
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    @strawberry.field
    async def history(
        self,
        info: strawberry.Info,
        branch: str = "main",
        resource_type: Optional[ResourceTypeEnum] = None,
        resource_id: Optional[str] = None,
        limit: int = 50
    ) -> List[HistoryEntry]:
        """버전 히스토리 조회"""
        user = info.context.get("user")

        # 히스토리 서비스 호출
        url = f"{service_client.branch_service_url}/api/v1/branches/{branch}/history"
        params = {
            'limit': limit
        }
        if resource_type:
            params['resource_type'] = resource_type.value
        if resource_id:
            params['resource_id'] = resource_id

        try:
            result = await service_client.call_service(url, "GET", params, user)

            # 데이터 변환
            history_entries = []
            for entry in result.get('data', []):
                history_entry = HistoryEntry(
                    id=entry.get('id', ''),
                    hash=entry.get('hash', ''),
                    message=entry.get('message', ''),
                    author=entry.get('author', ''),
                    timestamp=entry.get('timestamp'),
                    resourceType=ResourceTypeEnum(entry.get('resourceType', 'object_type')),
                    resourceId=entry.get('resourceId'),
                    operation=entry.get('operation', 'update'),
                    changes=entry.get('changes', {})
                )
                history_entries.append(history_entry)

            return history_entries

        except httpx.HTTPStatusError:
            # 히스토리 서비스가 사용할 수 없으면 빈 리스트 반환
            return []

    @strawberry.field
    async def validate_changes(
        self,
        info: strawberry.Info,
        source_branch: str,
        target_branch: str = "main"
    ) -> ValidationResult:
        """변경사항 검증"""
        user = info.context.get("user")

        url = f"{service_client.validation_service_url}/api/v1/validate"
        data = {
            "source_branch": source_branch,
            "target_branch": target_branch
        }
        result = await service_client.call_service(url, "POST", data, user)

        # 데이터 변환
        from api.graphql.schema import BreakingChange, ImpactAnalysis, SuggestedMigration, ValidationWarning

        breaking_changes = []
        for bc in result.get('breakingChanges', []):
            breaking_changes.append(BreakingChange(
                type=bc.get('type', ''),
                description=bc.get('description', ''),
                resourceType=ResourceTypeEnum(bc.get('resourceType', 'object_type')),
                resourceId=bc.get('resourceId', ''),
                severity=bc.get('severity', 'high'),
                mitigation=bc.get('mitigation')
            ))

        warnings = []
        for warning in result.get('warnings', []):
            warnings.append(ValidationWarning(
                type=warning.get('type', ''),
                message=warning.get('message', ''),
                resourceType=ResourceTypeEnum(warning.get('resourceType', 'object_type')),
                resourceId=warning.get('resourceId', ''),
                recommendation=warning.get('recommendation')
            ))

        suggested_migrations = []
        for migration in result.get('suggestedMigrations', []):
            suggested_migrations.append(SuggestedMigration(
                type=migration.get('type', ''),
                description=migration.get('description', ''),
                script=migration.get('script', ''),
                reversible=migration.get('reversible', False),
                estimatedTime=migration.get('estimatedTime')
            ))

        impact_analysis = None
        if result.get('impactAnalysis'):
            ia = result['impactAnalysis']
            impact_analysis = ImpactAnalysis(
                affectedObjectTypes=ia.get('affectedObjectTypes', []),
                affectedProperties=ia.get('affectedProperties', []),
                affectedLinkTypes=ia.get('affectedLinkTypes', []),
                estimatedDowntime=ia.get('estimatedDowntime'),
                migrationComplexity=ia.get('migrationComplexity', 'low'),
                riskLevel=ia.get('riskLevel', 'low')
            )

        return ValidationResult(
            isValid=result.get('isValid', True),
            breakingChanges=breaking_changes,
            warnings=warnings,
            impactAnalysis=impact_analysis,
            suggestedMigrations=suggested_migrations,
            validationTime=result.get('validationTime')
        )

    @strawberry.field
    async def search(
        self,
        info: strawberry.Info,
        query: str,
        branch: str = "main",
        types: Optional[List[ResourceTypeEnum]] = None,
        limit: int = 20
    ) -> SearchResult:
        """통합 검색"""
        user = info.context.get("user")

        # 검색 서비스 호출 (가용한 경우)
        try:
            # 스키마 서비스에서 검색 기능 사용
            url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/search"
            params = {
                'query': query,
                'limit': limit
            }
            if types:
                params['types'] = [t.value for t in types]

            result = await service_client.call_service(url, "GET", params, user)

            # 데이터 변환
            from api.graphql.schema import SearchItem

            search_items = []
            for item in result.get('items', []):
                search_item = SearchItem(
                    id=item.get('id', ''),
                    type=ResourceTypeEnum(item.get('type', 'object_type')),
                    name=item.get('name', ''),
                    displayName=item.get('displayName', ''),
                    description=item.get('description'),
                    score=item.get('score', 0.0),
                    branch=item.get('branch', branch),
                    path=item.get('path', ''),
                    highlights=item.get('highlights', {})
                )
                search_items.append(search_item)

            return SearchResult(
                items=search_items,
                totalCount=result.get('totalCount', len(search_items)),
                facets=result.get('facets', {})
            )

        except httpx.HTTPStatusError:
            # 검색 서비스가 사용할 수 없으면 빈 결과 반환
            return SearchResult(
                items=[],
                totalCount=0,
                facets={}
            )

    @strawberry.field
    async def action_types(
        self,
        info: strawberry.Info,
        branch: str = "main",
        category: Optional[ActionCategoryEnum] = None,
        transformation_type: Optional[TransformationTypeEnum] = None,
        applicable_object_type: Optional[str] = None
    ) -> List[ActionType]:
        """ActionType 목록 조회"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/action-types"
        params = {}
        if category:
            params['category'] = category.value
        if transformation_type:
            params['transformation_type'] = transformation_type.value
        if applicable_object_type:
            params['applicable_object_type'] = applicable_object_type

        result = await service_client.call_service(url, "GET", params, user)

        # 데이터 변환
        action_types = []
        for at in result:
            # ApplicableObjectType 변환
            applicable_object_types = []
            for obj in at.get('applicableObjectTypes', []):
                applicable_object_types.append(ApplicableObjectType(
                    objectTypeId=obj.get('objectTypeId', ''),
                    role=obj.get('role', 'primary'),
                    required=obj.get('required', True),
                    description=obj.get('description')
                ))

            # ParameterSchema 변환
            parameter_schema = None
            if at.get('parameterSchema'):
                ps = at['parameterSchema']
                parameter_schema = ParameterSchema(
                    schema=ps.get('schema', {}),
                    examples=ps.get('examples', []),
                    uiHints=ps.get('uiHints')
                )

            # ActionTypeReference 변환
            from api.graphql.schema import ActionTypeReference
            referenced_actions = []
            for ref in at.get('referencedActions', []):
                referenced_actions.append(ActionTypeReference(
                    actionTypeId=ref.get('actionTypeId', ''),
                    version=ref.get('version'),
                    description=ref.get('description')
                ))

            action_type = ActionType(
                id=at.get('id', ''),
                name=at.get('name', ''),
                displayName=at.get('displayName', ''),
                description=at.get('description'),
                category=ActionCategoryEnum(at.get('category', 'custom')),
                transformationType=TransformationTypeEnum(at.get('transformationType', 'custom')),
                transformationTypeRef=at.get('transformationTypeRef'),
                applicableObjectTypes=applicable_object_types,
                parameterSchema=parameter_schema,
                configuration=at.get('configuration', {}),
                referencedActions=referenced_actions,
                requiredPermissions=at.get('requiredPermissions', []),
                tags=at.get('tags', []),
                metadata=at.get('metadata', {}),
                isSystem=at.get('isSystem', False),
                isDeprecated=at.get('isDeprecated', False),
                version=at.get('version', 1),
                versionHash=at.get('versionHash', ''),
                createdBy=at.get('createdBy', ''),
                createdAt=at.get('createdAt'),
                modifiedBy=at.get('modifiedBy', ''),
                modifiedAt=at.get('modifiedAt')
            )
            action_types.append(action_type)

        return action_types

    @strawberry.field
    async def action_type(
        self,
        info: strawberry.Info,
        id: str,
        branch: str = "main"
    ) -> Optional[ActionType]:
        """ActionType 상세 조회"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/action-types/{id}"
        try:
            result = await service_client.call_service(url, "GET", None, user)

            # ApplicableObjectType 변환
            applicable_object_types = []
            for obj in result.get('applicableObjectTypes', []):
                applicable_object_types.append(ApplicableObjectType(
                    objectTypeId=obj.get('objectTypeId', ''),
                    role=obj.get('role', 'primary'),
                    required=obj.get('required', True),
                    description=obj.get('description')
                ))

            # ParameterSchema 변환
            parameter_schema = None
            if result.get('parameterSchema'):
                ps = result['parameterSchema']
                parameter_schema = ParameterSchema(
                    schema=ps.get('schema', {}),
                    examples=ps.get('examples', []),
                    uiHints=ps.get('uiHints')
                )

            # ActionTypeReference 변환
            from api.graphql.schema import ActionTypeReference
            referenced_actions = []
            for ref in result.get('referencedActions', []):
                referenced_actions.append(ActionTypeReference(
                    actionTypeId=ref.get('actionTypeId', ''),
                    version=ref.get('version'),
                    description=ref.get('description')
                ))

            return ActionType(
                id=result.get('id', ''),
                name=result.get('name', ''),
                displayName=result.get('displayName', ''),
                description=result.get('description'),
                category=ActionCategoryEnum(result.get('category', 'custom')),
                transformationType=TransformationTypeEnum(result.get('transformationType', 'custom')),
                transformationTypeRef=result.get('transformationTypeRef'),
                applicableObjectTypes=applicable_object_types,
                parameterSchema=parameter_schema,
                configuration=result.get('configuration', {}),
                referencedActions=referenced_actions,
                requiredPermissions=result.get('requiredPermissions', []),
                tags=result.get('tags', []),
                metadata=result.get('metadata', {}),
                isSystem=result.get('isSystem', False),
                isDeprecated=result.get('isDeprecated', False),
                version=result.get('version', 1),
                versionHash=result.get('versionHash', ''),
                createdBy=result.get('createdBy', ''),
                createdAt=result.get('createdAt'),
                modifiedBy=result.get('modifiedBy', ''),
                modifiedAt=result.get('modifiedAt')
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    # ===== Function Type Queries =====

    @strawberry.field
    async def function_types(
        self,
        info: strawberry.Info,
        branch: str = "main",
        category: Optional[FunctionCategoryEnum] = None,
        runtime: Optional[FunctionRuntimeEnum] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[FunctionType]:
        """Function Type 목록 조회"""
        user = info.context.get("user")

        params = {
            "category": category.value if category else None,
            "runtime": runtime.value if runtime else None,
            "tags": ",".join(tags) if tags else None,
            "limit": limit,
            "offset": offset
        }

        # None 값 제거
        params = {k: v for k, v in params.items() if v is not None}

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/function-types"
        result = await service_client.call_service(url, "GET", None, user, params)

        function_types = []
        for ft in result:
            function_types.append(self._convert_to_function_type_query(ft))

        return function_types

    @strawberry.field
    async def function_type(
        self,
        info: strawberry.Info,
        id: str,
        branch: str = "main"
    ) -> Optional[FunctionType]:
        """특정 Function Type 조회"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/function-types/{id}"
        try:
            result = await service_client.call_service(url, "GET", None, user)
            return self._convert_to_function_type_query(result)
        except Exception as e:
            if "404" in str(e):
                return None
            raise

    # ===== Data Type Queries =====

    @strawberry.field
    async def data_types(
        self,
        info: strawberry.Info,
        branch: str = "main",
        category: Optional[DataTypeCategoryEnum] = None,
        format: Optional[DataTypeFormatEnum] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[DataType]:
        """Data Type 목록 조회"""
        user = info.context.get("user")

        params = {
            "category": category.value if category else None,
            "format": format.value if format else None,
            "tags": ",".join(tags) if tags else None,
            "limit": limit,
            "offset": offset
        }

        # None 값 제거
        params = {k: v for k, v in params.items() if v is not None}

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/data-types"
        result = await service_client.call_service(url, "GET", None, user, params)

        data_types = []
        for dt in result:
            data_types.append(self._convert_to_data_type_query(dt))

        return data_types

    @strawberry.field
    async def data_type(
        self,
        info: strawberry.Info,
        id: str,
        branch: str = "main"
    ) -> Optional[DataType]:
        """특정 Data Type 조회"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/data-types/{id}"
        try:
            result = await service_client.call_service(url, "GET", None, user)
            return self._convert_to_data_type_query(result)
        except Exception as e:
            if "404" in str(e):
                return None
            raise

    def _convert_to_function_type_query(self, result: dict) -> FunctionType:
        """Query용 FunctionType 변환 (Mutation의 변환과 동일)"""
        from api.graphql.schema import (
            FunctionBehavior,
            FunctionCategoryEnum,
            FunctionExample,
            FunctionParameter,
            FunctionRuntimeEnum,
            ParameterDirectionEnum,
            ReturnType,
            RuntimeConfig,
        )

        # Parameters 변환
        parameters = []
        for param in result.get('parameters', []):
            parameters.append(FunctionParameter(
                name=param.get('name', ''),
                displayName=param.get('displayName', ''),
                description=param.get('description'),
                direction=ParameterDirectionEnum(param.get('direction', 'input')),
                dataTypeId=param.get('dataTypeId', ''),
                semanticTypeId=param.get('semanticTypeId'),
                structTypeId=param.get('structTypeId'),
                isRequired=param.get('isRequired', True),
                isArray=param.get('isArray', False),
                defaultValue=param.get('defaultValue'),
                validationRules=param.get('validationRules'),
                metadata=param.get('metadata'),
                sortOrder=param.get('sortOrder', 0)
            ))

        # Return type 변환
        rt = result.get('returnType', {})
        return_type = ReturnType(
            dataTypeId=rt.get('dataTypeId', ''),
            semanticTypeId=rt.get('semanticTypeId'),
            structTypeId=rt.get('structTypeId'),
            isArray=rt.get('isArray', False),
            isNullable=rt.get('isNullable', True),
            description=rt.get('description'),
            metadata=rt.get('metadata')
        )

        # Runtime config 변환
        rc = result.get('runtimeConfig', {})
        runtime_config = RuntimeConfig(
            runtime=FunctionRuntimeEnum(rc.get('runtime', 'python')),
            version=rc.get('version'),
            timeoutMs=rc.get('timeoutMs', 30000),
            memoryMb=rc.get('memoryMb', 512),
            cpuCores=rc.get('cpuCores', 1.0),
            maxRetries=rc.get('maxRetries', 3),
            retryDelayMs=rc.get('retryDelayMs', 1000),
            environmentVars=rc.get('environmentVars'),
            dependencies=rc.get('dependencies', []),
            resourceLimits=rc.get('resourceLimits')
        )

        # Behavior 변환
        bh = result.get('behavior', {})
        behavior = FunctionBehavior(
            isDeterministic=bh.get('isDeterministic', True),
            isStateless=bh.get('isStateless', True),
            isCacheable=bh.get('isCacheable', True),
            isParallelizable=bh.get('isParallelizable', True),
            hasSideEffects=bh.get('hasSideEffects', False),
            isExpensive=bh.get('isExpensive', False),
            cacheTtlSeconds=bh.get('cacheTtlSeconds')
        )

        # Examples 변환
        examples = []
        for ex in result.get('examples', []):
            examples.append(FunctionExample(
                name=ex.get('name', ''),
                description=ex.get('description'),
                inputValues=ex.get('inputValues', {}),
                expectedOutput=ex.get('expectedOutput'),
                explanation=ex.get('explanation')
            ))

        return FunctionType(
            id=result.get('id', ''),
            name=result.get('name', ''),
            displayName=result.get('displayName', ''),
            description=result.get('description'),
            category=FunctionCategoryEnum(result.get('category', 'custom')),
            parameters=parameters,
            returnType=return_type,
            runtimeConfig=runtime_config,
            behavior=behavior,
            implementationRef=result.get('implementationRef'),
            functionBody=result.get('functionBody'),
            examples=examples,
            tags=result.get('tags', []),
            isPublic=result.get('isPublic', True),
            allowedRoles=result.get('allowedRoles', []),
            allowedUsers=result.get('allowedUsers', []),
            metadata=result.get('metadata'),
            isSystem=result.get('isSystem', False),
            isDeprecated=result.get('isDeprecated', False),
            version=result.get('version', '1.0.0'),
            versionHash=result.get('versionHash', ''),
            previousVersionId=result.get('previousVersionId'),
            createdBy=result.get('createdBy', ''),
            createdAt=result.get('createdAt'),
            modifiedBy=result.get('modifiedBy', ''),
            modifiedAt=result.get('modifiedAt'),
            branchId=result.get('branchId'),
            isBranchSpecific=result.get('isBranchSpecific', False)
        )

    def _convert_to_data_type_query(self, result: dict) -> DataType:
        """Query용 DataType 변환 (Mutation의 변환과 동일)"""
        from api.graphql.schema import DataTypeCategoryEnum, DataTypeFormatEnum, TypeConstraint

        # Constraints 변환
        constraints = []
        for constraint in result.get('constraints', []):
            constraints.append(TypeConstraint(
                constraintType=constraint.get('constraintType', ''),
                value=constraint.get('value'),
                message=constraint.get('message')
            ))

        return DataType(
            id=result.get('id', ''),
            name=result.get('name', ''),
            displayName=result.get('displayName', ''),
            description=result.get('description'),
            category=DataTypeCategoryEnum(result.get('category', 'primitive')),
            format=DataTypeFormatEnum(result.get('format', 'xsd:string')),
            constraints=constraints,
            defaultValue=result.get('defaultValue'),
            isNullable=result.get('isNullable', True),
            isArrayType=result.get('isArrayType', False),
            arrayItemType=result.get('arrayItemType'),
            mapKeyType=result.get('mapKeyType'),
            mapValueType=result.get('mapValueType'),
            metadata=result.get('metadata'),
            supportedOperations=result.get('supportedOperations', []),
            compatibleTypes=result.get('compatibleTypes', []),
            isSystem=result.get('isSystem', False),
            isDeprecated=result.get('isDeprecated', False),
            deprecationMessage=result.get('deprecationMessage'),
            tags=result.get('tags', []),
            version=result.get('version', '1.0.0'),
            versionHash=result.get('versionHash', ''),
            previousVersionId=result.get('previousVersionId'),
            createdBy=result.get('createdBy', ''),
            createdAt=result.get('createdAt'),
            modifiedBy=result.get('modifiedBy', ''),
            modifiedAt=result.get('modifiedAt'),
            branchId=result.get('branchId'),
            isBranchSpecific=result.get('isBranchSpecific', False),
            isPublic=result.get('isPublic', True),
            allowedRoles=result.get('allowedRoles', []),
            allowedUsers=result.get('allowedUsers', [])
        )


@strawberry.type
class Mutation:
    """GraphQL Mutation 루트"""

    @strawberry.field
    async def create_object_type(
        self,
        info: strawberry.Info,
        input: ObjectTypeInput,
        branch: str = "main"
    ) -> ObjectType:
        """ObjectType 생성"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/object-types"
        data = {
            "name": input.name,
            "displayName": input.displayName,
            "pluralDisplayName": input.pluralDisplayName,
            "description": input.description,
            "status": input.status.value if input.status else None,
            "typeClass": input.typeClass.value if input.typeClass else None,
            "parentTypes": input.parentTypes,
            "interfaces": input.interfaces,
            "isAbstract": input.isAbstract,
            "icon": input.icon,
            "color": input.color
        }

        result = await service_client.call_service(url, "POST", data, user)

        # 데이터 변환
        return ObjectType(
            id=result.get('id', ''),
            name=result.get('name', ''),
            displayName=result.get('displayName', ''),
            pluralDisplayName=result.get('pluralDisplayName'),
            description=result.get('description'),
            status=StatusEnum(result.get('status', 'active')),
            typeClass=TypeClassEnum(result.get('typeClass', 'object')),
            versionHash=result.get('versionHash', ''),
            createdBy=result.get('createdBy', ''),
            createdAt=result.get('createdAt'),
            modifiedBy=result.get('modifiedBy', ''),
            modifiedAt=result.get('modifiedAt'),
            parentTypes=result.get('parentTypes', []),
            interfaces=result.get('interfaces', []),
            isAbstract=result.get('isAbstract', False),
            icon=result.get('icon'),
            color=result.get('color')
        )

    @strawberry.field
    async def update_object_type(
        self,
        info: strawberry.Info,
        id: str,
        input: ObjectTypeUpdateInput,
        branch: str = "main"
    ) -> ObjectType:
        """ObjectType 업데이트"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/object-types/{id}"
        data = {
            "displayName": input.displayName,
            "pluralDisplayName": input.pluralDisplayName,
            "description": input.description,
            "status": input.status.value if input.status else None,
            "parentTypes": input.parentTypes,
            "interfaces": input.interfaces,
            "isAbstract": input.isAbstract,
            "icon": input.icon,
            "color": input.color
        }

        result = await service_client.call_service(url, "PUT", data, user)

        # 데이터 변환
        return ObjectType(
            id=result.get('id', ''),
            name=result.get('name', ''),
            displayName=result.get('displayName', ''),
            pluralDisplayName=result.get('pluralDisplayName'),
            description=result.get('description'),
            status=StatusEnum(result.get('status', 'active')),
            typeClass=TypeClassEnum(result.get('typeClass', 'object')),
            versionHash=result.get('versionHash', ''),
            createdBy=result.get('createdBy', ''),
            createdAt=result.get('createdAt'),
            modifiedBy=result.get('modifiedBy', ''),
            modifiedAt=result.get('modifiedAt'),
            parentTypes=result.get('parentTypes', []),
            interfaces=result.get('interfaces', []),
            isAbstract=result.get('isAbstract', False),
            icon=result.get('icon'),
            color=result.get('color')
        )

    @strawberry.field
    async def delete_object_type(
        self,
        info: strawberry.Info,
        id: str,
        branch: str = "main",
        force: bool = False
    ) -> bool:
        """ObjectType 삭제"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/object-types/{id}"
        params = {"force": force}

        await service_client.call_service(url, "DELETE", params, user)
        return True

    @strawberry.field
    async def create_action_type(
        self,
        info: strawberry.Info,
        input: ActionTypeInput,
        branch: str = "main"
    ) -> ActionType:
        """ActionType 생성"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/action-types"

        # Input 데이터 변환
        data = {
            "name": input.name,
            "displayName": input.displayName,
            "description": input.description,
            "category": input.category.value,
            "transformationType": input.transformation_type.value,
            "transformationTypeRef": input.transformation_type_ref,
            "applicableObjectTypes": [
                {
                    "objectTypeId": obj.object_type_id,
                    "role": obj.role,
                    "required": obj.required,
                    "description": obj.description
                }
                for obj in input.applicable_object_types
            ],
            "parameterSchema": {
                "schema": input.parameter_schema.schema,
                "examples": input.parameter_schema.examples,
                "uiHints": input.parameter_schema.ui_hints
            } if input.parameter_schema else None,
            "configuration": input.configuration or {},
            "referencedActions": [
                {
                    "actionTypeId": ref.action_type_id,
                    "version": ref.version,
                    "description": ref.description
                }
                for ref in (input.referenced_actions or [])
            ],
            "requiredPermissions": input.required_permissions or [],
            "tags": input.tags or [],
            "metadata": input.metadata or {}
        }

        result = await service_client.call_service(url, "POST", data, user)

        # 결과 변환
        # ApplicableObjectType 변환
        applicable_object_types = []
        for obj in result.get('applicableObjectTypes', []):
            applicable_object_types.append(ApplicableObjectType(
                objectTypeId=obj.get('objectTypeId', ''),
                role=obj.get('role', 'primary'),
                required=obj.get('required', True),
                description=obj.get('description')
            ))

        # ParameterSchema 변환
        parameter_schema = None
        if result.get('parameterSchema'):
            ps = result['parameterSchema']
            parameter_schema = ParameterSchema(
                schema=ps.get('schema', {}),
                examples=ps.get('examples', []),
                uiHints=ps.get('uiHints')
            )

        # ActionTypeReference 변환
        from api.graphql.schema import ActionTypeReference
        referenced_actions = []
        for ref in result.get('referencedActions', []):
            referenced_actions.append(ActionTypeReference(
                actionTypeId=ref.get('actionTypeId', ''),
                version=ref.get('version'),
                description=ref.get('description')
            ))

        return ActionType(
            id=result.get('id', ''),
            name=result.get('name', ''),
            displayName=result.get('displayName', ''),
            description=result.get('description'),
            category=ActionCategoryEnum(result.get('category', 'custom')),
            transformationType=TransformationTypeEnum(result.get('transformationType', 'custom')),
            transformationTypeRef=result.get('transformationTypeRef'),
            applicableObjectTypes=applicable_object_types,
            parameterSchema=parameter_schema,
            configuration=result.get('configuration', {}),
            referencedActions=referenced_actions,
            requiredPermissions=result.get('requiredPermissions', []),
            tags=result.get('tags', []),
            metadata=result.get('metadata', {}),
            isSystem=result.get('isSystem', False),
            isDeprecated=result.get('isDeprecated', False),
            version=result.get('version', 1),
            versionHash=result.get('versionHash', ''),
            createdBy=result.get('createdBy', ''),
            createdAt=result.get('createdAt'),
            modifiedBy=result.get('modifiedBy', ''),
            modifiedAt=result.get('modifiedAt')
        )

    @strawberry.field
    async def update_action_type(
        self,
        info: strawberry.Info,
        id: str,
        input: ActionTypeUpdateInput,
        branch: str = "main"
    ) -> ActionType:
        """ActionType 업데이트"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/action-types/{id}"

        # Update input 데이터 변환
        data = {}
        if input.display_name:
            data["displayName"] = input.display_name
        if input.description is not None:
            data["description"] = input.description
        if input.transformation_type:
            data["transformationType"] = input.transformation_type.value
        if input.transformation_type_ref is not None:
            data["transformationTypeRef"] = input.transformation_type_ref
        if input.applicable_object_types:
            data["applicableObjectTypes"] = [
                {
                    "objectTypeId": obj.object_type_id,
                    "role": obj.role,
                    "required": obj.required,
                    "description": obj.description
                }
                for obj in input.applicable_object_types
            ]
        if input.parameter_schema:
            data["parameterSchema"] = {
                "schema": input.parameter_schema.schema,
                "examples": input.parameter_schema.examples,
                "uiHints": input.parameter_schema.ui_hints
            }
        if input.configuration is not None:
            data["configuration"] = input.configuration
        if input.referenced_actions is not None:
            data["referencedActions"] = [
                {
                    "actionTypeId": ref.action_type_id,
                    "version": ref.version,
                    "description": ref.description
                }
                for ref in input.referenced_actions
            ]
        if input.required_permissions is not None:
            data["requiredPermissions"] = input.required_permissions
        if input.tags is not None:
            data["tags"] = input.tags
        if input.metadata is not None:
            data["metadata"] = input.metadata
        if input.is_deprecated is not None:
            data["isDeprecated"] = input.is_deprecated

        result = await service_client.call_service(url, "PUT", data, user)

        # 결과 변환 (생성과 동일한 로직)
        # ApplicableObjectType 변환
        applicable_object_types = []
        for obj in result.get('applicableObjectTypes', []):
            applicable_object_types.append(ApplicableObjectType(
                objectTypeId=obj.get('objectTypeId', ''),
                role=obj.get('role', 'primary'),
                required=obj.get('required', True),
                description=obj.get('description')
            ))

        # ParameterSchema 변환
        parameter_schema = None
        if result.get('parameterSchema'):
            ps = result['parameterSchema']
            parameter_schema = ParameterSchema(
                schema=ps.get('schema', {}),
                examples=ps.get('examples', []),
                uiHints=ps.get('uiHints')
            )

        # ActionTypeReference 변환
        from api.graphql.schema import ActionTypeReference
        referenced_actions = []
        for ref in result.get('referencedActions', []):
            referenced_actions.append(ActionTypeReference(
                actionTypeId=ref.get('actionTypeId', ''),
                version=ref.get('version'),
                description=ref.get('description')
            ))

        return ActionType(
            id=result.get('id', ''),
            name=result.get('name', ''),
            displayName=result.get('displayName', ''),
            description=result.get('description'),
            category=ActionCategoryEnum(result.get('category', 'custom')),
            transformationType=TransformationTypeEnum(result.get('transformationType', 'custom')),
            transformationTypeRef=result.get('transformationTypeRef'),
            applicableObjectTypes=applicable_object_types,
            parameterSchema=parameter_schema,
            configuration=result.get('configuration', {}),
            referencedActions=referenced_actions,
            requiredPermissions=result.get('requiredPermissions', []),
            tags=result.get('tags', []),
            metadata=result.get('metadata', {}),
            isSystem=result.get('isSystem', False),
            isDeprecated=result.get('isDeprecated', False),
            version=result.get('version', 1),
            versionHash=result.get('versionHash', ''),
            createdBy=result.get('createdBy', ''),
            createdAt=result.get('createdAt'),
            modifiedBy=result.get('modifiedBy', ''),
            modifiedAt=result.get('modifiedAt')
        )

    @strawberry.field
    async def delete_action_type(
        self,
        info: strawberry.Info,
        id: str,
        branch: str = "main"
    ) -> bool:
        """ActionType 삭제"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/action-types/{id}"

        await service_client.call_service(url, "DELETE", None, user)
        return True

    # ===== Function Type Mutations =====

    @strawberry.field
    async def create_function_type(
        self,
        info: strawberry.Info,
        input: FunctionTypeInput,
        branch: str = "main"
    ) -> FunctionType:
        """Function Type 생성"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/function-types"
        result = await service_client.call_service(url, "POST", input, user)

        return self._convert_to_function_type(result)

    @strawberry.field
    async def update_function_type(
        self,
        info: strawberry.Info,
        id: str,
        input: FunctionTypeUpdateInput,
        branch: str = "main"
    ) -> FunctionType:
        """Function Type 수정"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/function-types/{id}"
        result = await service_client.call_service(url, "PUT", input, user)

        return self._convert_to_function_type(result)

    @strawberry.field
    async def delete_function_type(
        self,
        info: strawberry.Info,
        id: str,
        branch: str = "main"
    ) -> bool:
        """Function Type 삭제"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/function-types/{id}"

        await service_client.call_service(url, "DELETE", None, user)
        return True

    # ===== Data Type Mutations =====

    @strawberry.field
    async def create_data_type(
        self,
        info: strawberry.Info,
        input: DataTypeInput,
        branch: str = "main"
    ) -> DataType:
        """Data Type 생성"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/data-types"
        result = await service_client.call_service(url, "POST", input, user)

        return self._convert_to_data_type(result)

    @strawberry.field
    async def update_data_type(
        self,
        info: strawberry.Info,
        id: str,
        input: DataTypeUpdateInput,
        branch: str = "main"
    ) -> DataType:
        """Data Type 수정"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/data-types/{id}"
        result = await service_client.call_service(url, "PUT", input, user)

        return self._convert_to_data_type(result)

    @strawberry.field
    async def delete_data_type(
        self,
        info: strawberry.Info,
        id: str,
        branch: str = "main"
    ) -> bool:
        """Data Type 삭제"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/data-types/{id}"

        await service_client.call_service(url, "DELETE", None, user)
        return True

    def _convert_to_function_type(self, result: dict) -> FunctionType:
        """API 응답을 GraphQL FunctionType으로 변환"""
        from api.graphql.schema import (
            FunctionBehavior,
            FunctionCategoryEnum,
            FunctionExample,
            FunctionParameter,
            FunctionRuntimeEnum,
            ParameterDirectionEnum,
            ReturnType,
            RuntimeConfig,
        )

        # Parameters 변환
        parameters = []
        for param in result.get('parameters', []):
            parameters.append(FunctionParameter(
                name=param.get('name', ''),
                displayName=param.get('displayName', ''),
                description=param.get('description'),
                direction=ParameterDirectionEnum(param.get('direction', 'input')),
                dataTypeId=param.get('dataTypeId', ''),
                semanticTypeId=param.get('semanticTypeId'),
                structTypeId=param.get('structTypeId'),
                isRequired=param.get('isRequired', True),
                isArray=param.get('isArray', False),
                defaultValue=param.get('defaultValue'),
                validationRules=param.get('validationRules'),
                metadata=param.get('metadata'),
                sortOrder=param.get('sortOrder', 0)
            ))

        # Return type 변환
        rt = result.get('returnType', {})
        return_type = ReturnType(
            dataTypeId=rt.get('dataTypeId', ''),
            semanticTypeId=rt.get('semanticTypeId'),
            structTypeId=rt.get('structTypeId'),
            isArray=rt.get('isArray', False),
            isNullable=rt.get('isNullable', True),
            description=rt.get('description'),
            metadata=rt.get('metadata')
        )

        # Runtime config 변환
        rc = result.get('runtimeConfig', {})
        runtime_config = RuntimeConfig(
            runtime=FunctionRuntimeEnum(rc.get('runtime', 'python')),
            version=rc.get('version'),
            timeoutMs=rc.get('timeoutMs', 30000),
            memoryMb=rc.get('memoryMb', 512),
            cpuCores=rc.get('cpuCores', 1.0),
            maxRetries=rc.get('maxRetries', 3),
            retryDelayMs=rc.get('retryDelayMs', 1000),
            environmentVars=rc.get('environmentVars'),
            dependencies=rc.get('dependencies', []),
            resourceLimits=rc.get('resourceLimits')
        )

        # Behavior 변환
        bh = result.get('behavior', {})
        behavior = FunctionBehavior(
            isDeterministic=bh.get('isDeterministic', True),
            isStateless=bh.get('isStateless', True),
            isCacheable=bh.get('isCacheable', True),
            isParallelizable=bh.get('isParallelizable', True),
            hasSideEffects=bh.get('hasSideEffects', False),
            isExpensive=bh.get('isExpensive', False),
            cacheTtlSeconds=bh.get('cacheTtlSeconds')
        )

        # Examples 변환
        examples = []
        for ex in result.get('examples', []):
            examples.append(FunctionExample(
                name=ex.get('name', ''),
                description=ex.get('description'),
                inputValues=ex.get('inputValues', {}),
                expectedOutput=ex.get('expectedOutput'),
                explanation=ex.get('explanation')
            ))

        return FunctionType(
            id=result.get('id', ''),
            name=result.get('name', ''),
            displayName=result.get('displayName', ''),
            description=result.get('description'),
            category=FunctionCategoryEnum(result.get('category', 'custom')),
            parameters=parameters,
            returnType=return_type,
            runtimeConfig=runtime_config,
            behavior=behavior,
            implementationRef=result.get('implementationRef'),
            functionBody=result.get('functionBody'),
            examples=examples,
            tags=result.get('tags', []),
            isPublic=result.get('isPublic', True),
            allowedRoles=result.get('allowedRoles', []),
            allowedUsers=result.get('allowedUsers', []),
            metadata=result.get('metadata'),
            isSystem=result.get('isSystem', False),
            isDeprecated=result.get('isDeprecated', False),
            version=result.get('version', '1.0.0'),
            versionHash=result.get('versionHash', ''),
            previousVersionId=result.get('previousVersionId'),
            createdBy=result.get('createdBy', ''),
            createdAt=result.get('createdAt'),
            modifiedBy=result.get('modifiedBy', ''),
            modifiedAt=result.get('modifiedAt'),
            branchId=result.get('branchId'),
            isBranchSpecific=result.get('isBranchSpecific', False)
        )

    def _convert_to_data_type(self, result: dict) -> DataType:
        """API 응답을 GraphQL DataType으로 변환"""
        from api.graphql.schema import DataTypeCategoryEnum, DataTypeFormatEnum, TypeConstraint

        # Constraints 변환
        constraints = []
        for constraint in result.get('constraints', []):
            constraints.append(TypeConstraint(
                constraintType=constraint.get('constraintType', ''),
                value=constraint.get('value'),
                message=constraint.get('message')
            ))

        return DataType(
            id=result.get('id', ''),
            name=result.get('name', ''),
            displayName=result.get('displayName', ''),
            description=result.get('description'),
            category=DataTypeCategoryEnum(result.get('category', 'primitive')),
            format=DataTypeFormatEnum(result.get('format', 'xsd:string')),
            constraints=constraints,
            defaultValue=result.get('defaultValue'),
            isNullable=result.get('isNullable', True),
            isArrayType=result.get('isArrayType', False),
            arrayItemType=result.get('arrayItemType'),
            mapKeyType=result.get('mapKeyType'),
            mapValueType=result.get('mapValueType'),
            metadata=result.get('metadata'),
            supportedOperations=result.get('supportedOperations', []),
            compatibleTypes=result.get('compatibleTypes', []),
            isSystem=result.get('isSystem', False),
            isDeprecated=result.get('isDeprecated', False),
            deprecationMessage=result.get('deprecationMessage'),
            tags=result.get('tags', []),
            version=result.get('version', '1.0.0'),
            versionHash=result.get('versionHash', ''),
            previousVersionId=result.get('previousVersionId'),
            createdBy=result.get('createdBy', ''),
            createdAt=result.get('createdAt'),
            modifiedBy=result.get('modifiedBy', ''),
            modifiedAt=result.get('modifiedAt'),
            branchId=result.get('branchId'),
            isBranchSpecific=result.get('isBranchSpecific', False),
            isPublic=result.get('isPublic', True),
            allowedRoles=result.get('allowedRoles', []),
            allowedUsers=result.get('allowedUsers', [])
        )


# Import subscriptions
from api.graphql.subscriptions import Subscription

# Create the schema with subscriptions
schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
