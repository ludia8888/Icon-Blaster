"""
Additional GraphQL Mutation Resolvers
완전한 GraphQL API 구현을 위한 추가 Mutation 메서드들
"""
import logging
from typing import Optional

import strawberry

from api.graphql.resolvers import ServiceClient
from api.graphql.schema import (
    Branch,
    BranchStatusEnum,
    CreateBranchInput,
    LinkType,
    LinkTypeInput,
    LinkTypeUpdateInput,
    Property,
    PropertyInput,
    PropertyUpdateInput,
    ProposalInput,
    ProposalUpdateInput,
    SharedProperty,
    SharedPropertyInput,
    StatusEnum,
)

logger = logging.getLogger(__name__)
service_client = ServiceClient()


@strawberry.type
class ExtendedMutation:
    """확장된 GraphQL Mutation 클래스"""

    # Property Mutations
    @strawberry.field
    async def add_property(
        self,
        info: strawberry.Info,
        objectTypeId: str,
        input: PropertyInput,
        branch: str = "main"
    ) -> Property:
        """Property 추가"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/object-types/{objectTypeId}/properties"
        data = {
            "name": input.name,
            "displayName": input.displayName,
            "dataType": input.dataType,
            "isRequired": input.isRequired,
            "isUnique": input.isUnique,
            "isPrimaryKey": input.isPrimaryKey,
            "isSearchable": input.isSearchable,
            "isIndexed": input.isIndexed,
            "defaultValue": input.defaultValue,
            "description": input.description,
            "enumValues": input.enumValues,
            "linkedObjectType": input.linkedObjectType,
            "status": input.status.value,
            "visibility": input.visibility.value,
            "isMutable": input.isMutable
        }

        result = await service_client.call_service(url, "POST", data, user)

        return Property(
            id=result.get('id', ''),
            objectTypeId=result.get('objectTypeId', ''),
            name=result.get('name', ''),
            displayName=result.get('displayName', ''),
            dataType=result.get('dataType', ''),
            isRequired=result.get('isRequired', False),
            isUnique=result.get('isUnique', False),
            isPrimaryKey=result.get('isPrimaryKey', False),
            isSearchable=result.get('isSearchable', False),
            isIndexed=result.get('isIndexed', False),
            defaultValue=result.get('defaultValue'),
            description=result.get('description'),
            enumValues=result.get('enumValues', []),
            linkedObjectType=result.get('linkedObjectType'),
            status=StatusEnum(result.get('status', 'active')),
            versionHash=result.get('versionHash', ''),
            createdBy=result.get('createdBy', ''),
            createdAt=result.get('createdAt'),
            modifiedBy=result.get('modifiedBy', ''),
            modifiedAt=result.get('modifiedAt')
        )

    @strawberry.field
    async def update_property(
        self,
        info: strawberry.Info,
        id: str,
        input: PropertyUpdateInput,
        branch: str = "main"
    ) -> Property:
        """Property 업데이트"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/properties/{id}"
        data = {
            "displayName": input.displayName,
            "isRequired": input.isRequired,
            "isUnique": input.isUnique,
            "isPrimaryKey": input.isPrimaryKey,
            "isSearchable": input.isSearchable,
            "isIndexed": input.isIndexed,
            "defaultValue": input.defaultValue,
            "description": input.description,
            "enumValues": input.enumValues,
            "linkedObjectType": input.linkedObjectType,
            "status": input.status.value if input.status else None,
            "visibility": input.visibility.value if input.visibility else None,
            "isMutable": input.isMutable
        }

        # None 값 제거
        data = {k: v for k, v in data.items() if v is not None}

        result = await service_client.call_service(url, "PUT", data, user)

        return Property(
            id=result.get('id', ''),
            objectTypeId=result.get('objectTypeId', ''),
            name=result.get('name', ''),
            displayName=result.get('displayName', ''),
            dataType=result.get('dataType', ''),
            isRequired=result.get('isRequired', False),
            isUnique=result.get('isUnique', False),
            isPrimaryKey=result.get('isPrimaryKey', False),
            isSearchable=result.get('isSearchable', False),
            isIndexed=result.get('isIndexed', False),
            defaultValue=result.get('defaultValue'),
            description=result.get('description'),
            enumValues=result.get('enumValues', []),
            linkedObjectType=result.get('linkedObjectType'),
            status=StatusEnum(result.get('status', 'active')),
            versionHash=result.get('versionHash', ''),
            createdBy=result.get('createdBy', ''),
            createdAt=result.get('createdAt'),
            modifiedBy=result.get('modifiedBy', ''),
            modifiedAt=result.get('modifiedAt')
        )

    @strawberry.field
    async def remove_property(
        self,
        info: strawberry.Info,
        id: str,
        branch: str = "main"
    ) -> bool:
        """Property 제거"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/properties/{id}"
        await service_client.call_service(url, "DELETE", None, user)
        return True

    # SharedProperty Mutations
    @strawberry.field
    async def create_shared_property(
        self,
        info: strawberry.Info,
        input: SharedPropertyInput,
        branch: str = "main"
    ) -> SharedProperty:
        """SharedProperty 생성"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/shared-properties"
        data = {
            "name": input.name,
            "displayName": input.displayName,
            "description": input.description,
            "dataType": input.dataType,
            "semanticType": input.semanticType,
            "defaultValue": input.defaultValue,
            "enumValues": input.enumValues,
            "status": input.status.value
        }

        result = await service_client.call_service(url, "POST", data, user)

        return SharedProperty(
            id=result.get('id', ''),
            name=result.get('name', ''),
            displayName=result.get('displayName', ''),
            description=result.get('description'),
            dataType=result.get('dataType', ''),
            semanticType=result.get('semanticType'),
            defaultValue=result.get('defaultValue'),
            enumValues=result.get('enumValues', []),
            status=StatusEnum(result.get('status', 'active')),
            versionHash=result.get('versionHash', ''),
            createdBy=result.get('createdBy', ''),
            createdAt=result.get('createdAt'),
            modifiedBy=result.get('modifiedBy', ''),
            modifiedAt=result.get('modifiedAt')
        )

    # LinkType Mutations
    @strawberry.field
    async def create_link_type(
        self,
        info: strawberry.Info,
        input: LinkTypeInput,
        branch: str = "main"
    ) -> LinkType:
        """LinkType 생성"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/link-types"
        data = {
            "name": input.name,
            "displayName": input.displayName,
            "description": input.description,
            "fromObjectType": input.fromObjectType,
            "toObjectType": input.toObjectType,
            "directionality": input.directionality.value,
            "fromCardinality": input.fromCardinality.value,
            "toCardinality": input.toCardinality.value,
            "isInheritable": input.isInheritable,
            "status": input.status.value
        }

        result = await service_client.call_service(url, "POST", data, user)

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

    @strawberry.field
    async def update_link_type(
        self,
        info: strawberry.Info,
        id: str,
        input: LinkTypeUpdateInput,
        branch: str = "main"
    ) -> LinkType:
        """LinkType 업데이트"""
        user = info.context.get("user")

        url = f"{service_client.schema_service_url}/api/v1/schemas/{branch}/link-types/{id}"
        data = {
            "displayName": input.displayName,
            "description": input.description,
            "directionality": input.directionality.value if input.directionality else None,
            "fromCardinality": input.fromCardinality.value if input.fromCardinality else None,
            "toCardinality": input.toCardinality.value if input.toCardinality else None,
            "isInheritable": input.isInheritable,
            "status": input.status.value if input.status else None
        }

        # None 값 제거
        data = {k: v for k, v in data.items() if v is not None}

        result = await service_client.call_service(url, "PUT", data, user)

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

    # Branch Mutations
    @strawberry.field
    async def create_branch(
        self,
        info: strawberry.Info,
        input: CreateBranchInput
    ) -> Branch:
        """Branch 생성"""
        user = info.context.get("user")

        url = f"{service_client.branch_service_url}/api/v1/branches"
        data = {
            "name": input.name,
            "fromBranch": input.fromBranch,
            "description": input.description
        }

        result = await service_client.call_service(url, "POST", data, user)

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

    @strawberry.field
    async def delete_branch(
        self,
        info: strawberry.Info,
        name: str,
        force: bool = False
    ) -> bool:
        """Branch 삭제"""
        user = info.context.get("user")

        url = f"{service_client.branch_service_url}/api/v1/branches/{name}"
        params = {"force": force}

        await service_client.call_service(url, "DELETE", params, user)
        return True

    # Proposal Mutations
    @strawberry.field
    async def create_proposal(
        self,
        info: strawberry.Info,
        input: ProposalInput
    ) -> str:  # Returns proposal ID
        """Change Proposal 생성"""
        user = info.context.get("user")

        url = f"{service_client.branch_service_url}/api/v1/proposals"
        data = {
            "title": input.title,
            "description": input.description,
            "sourceBranch": input.sourceBranch,
            "targetBranch": input.targetBranch,
            "reviewers": input.reviewers
        }

        result = await service_client.call_service(url, "POST", data, user)
        return result.get('id', '')

    @strawberry.field
    async def update_proposal(
        self,
        info: strawberry.Info,
        id: str,
        input: ProposalUpdateInput
    ) -> str:
        """Change Proposal 업데이트"""
        user = info.context.get("user")

        url = f"{service_client.branch_service_url}/api/v1/proposals/{id}"
        data = {
            "title": input.title,
            "description": input.description,
            "reviewers": input.reviewers
        }

        # None 값 제거
        data = {k: v for k, v in data.items() if v is not None}

        result = await service_client.call_service(url, "PUT", data, user)
        return result.get('id', '')

    @strawberry.field
    async def approve_proposal(
        self,
        info: strawberry.Info,
        id: str,
        comment: Optional[str] = None
    ) -> str:
        """Change Proposal 승인"""
        user = info.context.get("user")

        url = f"{service_client.branch_service_url}/api/v1/proposals/{id}/approve"
        data = {"comment": comment} if comment else {}

        result = await service_client.call_service(url, "POST", data, user)
        return result.get('id', '')

    @strawberry.field
    async def reject_proposal(
        self,
        info: strawberry.Info,
        id: str,
        reason: str
    ) -> str:
        """Change Proposal 거부"""
        user = info.context.get("user")

        url = f"{service_client.branch_service_url}/api/v1/proposals/{id}/reject"
        data = {"reason": reason}

        result = await service_client.call_service(url, "POST", data, user)
        return result.get('id', '')

    @strawberry.field
    async def merge_branch(
        self,
        info: strawberry.Info,
        proposalId: str,
        strategy: str = "merge",
        title: Optional[str] = None,
        description: Optional[str] = None,
        autoDeleteSourceBranch: bool = False
    ) -> str:
        """Branch 병합"""
        user = info.context.get("user")

        url = f"{service_client.branch_service_url}/api/v1/proposals/{proposalId}/merge"
        data = {
            "strategy": strategy,
            "title": title,
            "description": description,
            "autoDeleteSourceBranch": autoDeleteSourceBranch
        }

        result = await service_client.call_service(url, "POST", data, user)
        return result.get('mergeCommitHash', '')
