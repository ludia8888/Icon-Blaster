"""
GraphQL Proxy Layer
Query Passthrough, Mutation Translation, Schema Federation
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from graphql import DocumentNode, parse
from graphql.language import ast
from database.clients.unified_http_client import UnifiedHTTPClient, create_basic_client, HTTPClientConfig

logger = logging.getLogger(__name__)


@dataclass
class GraphQLRequest:
    """GraphQL 요청"""
    query: str
    variables: Optional[Dict[str, Any]] = None
    operation_name: Optional[str] = None


@dataclass
class GraphQLResponse:
    """GraphQL 응답"""
    data: Optional[Dict[str, Any]] = None
    errors: Optional[List[Dict[str, Any]]] = None
    extensions: Optional[Dict[str, Any]] = None


class GraphQLProxy:
    """GraphQL 프록시"""

    def __init__(self, service_endpoints: Dict[str, str]):
        self.service_endpoints = service_endpoints
        self.http_client = create_basic_client(timeout=30.0)
        self.schema_cache = {}
        self._federated_schema = None

    async def execute(
        self,
        request: GraphQLRequest,
        context: Dict[str, Any]
    ) -> GraphQLResponse:
        """GraphQL 요청 실행"""

        try:
            # 쿼리 파싱
            document = parse(request.query)

            # 작업 유형 확인
            operation = self._get_operation(document, request.operation_name)

            if operation.operation == ast.OperationType.QUERY:
                # Query는 passthrough
                return await self._execute_query(request, context)
            elif operation.operation == ast.OperationType.MUTATION:
                # Mutation은 REST로 변환
                return await self._execute_mutation(request, context)
            elif operation.operation == ast.OperationType.SUBSCRIPTION:
                # Subscription은 WebSocket 필요
                return GraphQLResponse(
                    errors=[{
                        "message": "Subscriptions not supported yet",
                        "extensions": {"code": "NOT_IMPLEMENTED"}
                    }]
                )

        except Exception as e:
            logger.error(f"GraphQL execution error: {e}")
            return GraphQLResponse(
                errors=[{
                    "message": str(e),
                    "extensions": {"code": "INTERNAL_ERROR"}
                }]
            )

    def _get_operation(
        self,
        document: DocumentNode,
        operation_name: Optional[str]
    ) -> ast.OperationDefinitionNode:
        """작업 정의 가져오기"""

        operations = [
            node for node in document.definitions
            if isinstance(node, ast.OperationDefinitionNode)
        ]

        if not operations:
            raise ValueError("No operation found in query")

        if operation_name:
            for op in operations:
                if op.name and op.name.value == operation_name:
                    return op
            raise ValueError(f"Operation '{operation_name}' not found")

        if len(operations) > 1:
            raise ValueError("Multiple operations found, operation name required")

        return operations[0]

    async def _execute_query(
        self,
        request: GraphQLRequest,
        context: Dict[str, Any]
    ) -> GraphQLResponse:
        """Query 실행 (Terminus DB로 passthrough)"""

        # Terminus DB GraphQL 엔드포인트로 전달
        endpoint = self.service_endpoints.get("terminus_db_graphql")
        if not endpoint:
            return GraphQLResponse(
                errors=[{
                    "message": "Terminus DB GraphQL endpoint not configured",
                    "extensions": {"code": "CONFIG_ERROR"}
                }]
            )

        try:
            # 헤더 준비
            headers = {
                "Content-Type": "application/json",
                "X-Request-ID": context.get("request_id", ""),
                "X-User-ID": context.get("user_id", "")
            }

            # 요청 전송
            response = await self.http_client.post(
                endpoint,
                json={
                    "query": request.query,
                    "variables": request.variables,
                    "operationName": request.operation_name
                },
                headers=headers
            )

            if response.status_code == 200:
                return GraphQLResponse(**response.json())
            else:
                return GraphQLResponse(
                    errors=[{
                        "message": f"GraphQL query failed: {response.status_code}",
                        "extensions": {
                            "code": "QUERY_ERROR",
                            "status": response.status_code
                        }
                    }]
                )

        except Exception as e:
            logger.error(f"Query execution error: {e}")
            return GraphQLResponse(
                errors=[{
                    "message": f"Query execution failed: {str(e)}",
                    "extensions": {"code": "EXECUTION_ERROR"}
                }]
            )

    async def _execute_mutation(
        self,
        request: GraphQLRequest,
        context: Dict[str, Any]
    ) -> GraphQLResponse:
        """Mutation 실행 (REST API로 변환)"""

        try:
            # 쿼리 파싱
            document = parse(request.query)
            operation = self._get_operation(document, request.operation_name)

            # Mutation 필드 추출
            selections = operation.selection_set.selections
            if not selections:
                raise ValueError("No mutation field found")

            # 첫 번째 mutation 필드 처리 (일반적으로 하나만 있음)
            field = selections[0]
            if not isinstance(field, ast.FieldNode):
                raise ValueError("Invalid mutation field")

            mutation_name = field.name.value
            arguments = self._extract_arguments(field, request.variables)

            # REST API로 매핑
            result = await self._map_mutation_to_rest(
                mutation_name,
                arguments,
                context
            )

            # GraphQL 응답 형식으로 변환
            return GraphQLResponse(
                data={mutation_name: result}
            )

        except Exception as e:
            logger.error(f"Mutation execution error: {e}")
            return GraphQLResponse(
                errors=[{
                    "message": str(e),
                    "extensions": {"code": "MUTATION_ERROR"}
                }]
            )

    def _extract_arguments(
        self,
        field: ast.FieldNode,
        variables: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """필드 인자 추출"""

        args = {}
        if field.arguments:
            for arg in field.arguments:
                arg_name = arg.name.value

                if isinstance(arg.value, ast.VariableNode):
                    # 변수 참조
                    var_name = arg.value.name.value
                    if variables and var_name in variables:
                        args[arg_name] = variables[var_name]
                else:
                    # 리터럴 값
                    args[arg_name] = self._extract_value(arg.value)

        return args

    def _extract_value(self, value_node: ast.ValueNode) -> Any:
        """AST 노드에서 값 추출"""

        if isinstance(value_node, ast.IntValueNode):
            return int(value_node.value)
        elif isinstance(value_node, ast.FloatValueNode):
            return float(value_node.value)
        elif isinstance(value_node, ast.StringValueNode):
            return value_node.value
        elif isinstance(value_node, ast.BooleanValueNode):
            return value_node.value
        elif isinstance(value_node, ast.NullValueNode):
            return None
        elif isinstance(value_node, ast.ListValueNode):
            return [self._extract_value(v) for v in value_node.values]
        elif isinstance(value_node, ast.ObjectValueNode):
            return {
                field.name.value: self._extract_value(field.value)
                for field in value_node.fields
            }
        else:
            return None

    async def _map_mutation_to_rest(
        self,
        mutation_name: str,
        arguments: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Mutation을 REST API 호출로 매핑"""

        # Mutation 매핑 테이블
        mutation_mappings = {
            # Schema mutations
            "createObjectType": {
                "service": "schema-service",
                "method": "POST",
                "path": "/api/v1/schemas/{branch}/object-types",
                "body_field": "input"
            },
            "updateObjectType": {
                "service": "schema-service",
                "method": "PUT",
                "path": "/api/v1/schemas/{branch}/object-types/{id}",
                "body_field": "input"
            },
            "deleteObjectType": {
                "service": "schema-service",
                "method": "DELETE",
                "path": "/api/v1/schemas/{branch}/object-types/{id}"
            },

            # Branch mutations
            "createBranch": {
                "service": "branch-service",
                "method": "POST",
                "path": "/api/v1/branches",
                "body_field": "input"
            },
            "mergeBranch": {
                "service": "branch-service",
                "method": "POST",
                "path": "/api/v1/branches/{source}/merge",
                "body_field": "input"
            },

            # Action mutations
            "executeAction": {
                "service": "action-service",
                "method": "POST",
                "path": "/api/v1/actions/execute",
                "body_field": "input"
            }
        }

        mapping = mutation_mappings.get(mutation_name)
        if not mapping:
            raise ValueError(f"Unknown mutation: {mutation_name}")

        # 서비스 엔드포인트
        service_url = self.service_endpoints.get(mapping["service"])
        if not service_url:
            raise ValueError(f"Service endpoint not configured: {mapping['service']}")

        # 경로 템플릿 처리
        path = mapping["path"]
        for key, value in arguments.items():
            path = path.replace(f"{{{key}}}", str(value))

        # 요청 본문 준비
        body = None
        if mapping.get("body_field"):
            body_data = arguments.get(mapping["body_field"], {})
            body = json.dumps(body_data)

        # 헤더 준비
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": context.get("request_id", ""),
            "X-User-ID": context.get("user_id", ""),
            "Authorization": context.get("auth_header", "")
        }

        # REST API 호출
        url = f"{service_url}{path}"
        response = await self.http_client.request(
            method=mapping["method"],
            url=url,
            content=body,
            headers=headers
        )

        if response.status_code >= 200 and response.status_code < 300:
            return response.json()
        else:
            raise Exception(f"REST API call failed: {response.status_code} - {response.text}")

    async def get_schema(self) -> str:
        """통합 GraphQL 스키마 반환"""

        if not self._federated_schema:
            self._federated_schema = await self._build_federated_schema()

        return self._federated_schema

    async def _build_federated_schema(self) -> str:
        """페더레이션 스키마 구성"""

        # 기본 스키마 정의
        schema_sdl = """
        type Query {
            # Object Types
            objectType(branch: String!, id: ID!): ObjectType
            objectTypes(branch: String!, filter: ObjectTypeFilter): [ObjectType!]!

            # Properties
            property(branch: String!, id: ID!): Property
            properties(branch: String!, objectTypeId: ID): [Property!]!

            # Branches
            branch(name: String!): Branch
            branches: [Branch!]!

            # Validation
            validateSchema(branch: String!, schema: JSON!): ValidationResult
            detectBreakingChanges(source: String!, target: String!): [BreakingChange!]!

            # Actions
            actionJob(id: ID!): ActionJob
            actionJobs(status: JobStatus): [ActionJob!]!
        }

        type Mutation {
            # Object Type mutations
            createObjectType(branch: String!, input: ObjectTypeInput!): ObjectType!
            updateObjectType(branch: String!, id: ID!, input: ObjectTypeUpdate!): ObjectType!
            deleteObjectType(branch: String!, id: ID!): Boolean!

            # Property mutations
            createProperty(branch: String!, objectTypeId: ID!, input: PropertyInput!): Property!
            updateProperty(branch: String!, id: ID!, input: PropertyUpdate!): Property!
            deleteProperty(branch: String!, id: ID!): Boolean!

            # Branch mutations
            createBranch(input: CreateBranchInput!): Branch!
            mergeBranch(source: String!, target: String!, input: MergeInput!): MergeResult!
            deleteBranch(name: String!): Boolean!

            # Action mutations
            executeAction(input: ExecuteActionInput!): ActionJob!
            cancelAction(jobId: ID!): Boolean!
            retryAction(jobId: ID!, objectIds: [ID!]): ActionJob!
        }

        # Types
        type ObjectType {
            id: ID!
            name: String!
            displayName: String!
            pluralDisplayName: String!
            description: String
            status: String!
            typeClass: String!
            properties: [Property!]!
            versionHash: String!
            createdAt: DateTime!
            createdBy: String!
            updatedAt: DateTime
            updatedBy: String
        }

        type Property {
            id: ID!
            name: String!
            displayName: String!
            dataType: DataType!
            isRequired: Boolean!
            isPrimaryKey: Boolean!
            isUnique: Boolean!
            defaultValue: JSON
            validation: JSON
            metadata: JSON
        }

        type Branch {
            name: String!
            headHash: String!
            baseBranch: String
            isProtected: Boolean!
            createdAt: DateTime!
            createdBy: String!
        }

        type ValidationResult {
            isValid: Boolean!
            errors: [ValidationError!]!
        }

        type ValidationError {
            path: String!
            message: String!
            code: String!
        }

        type BreakingChange {
            id: ID!
            changeType: String!
            severity: String!
            resource: String!
            description: String!
            migrationRequired: Boolean!
        }

        type MergeResult {
            success: Boolean!
            mergeCommit: String
            conflicts: [Conflict!]!
        }

        type Conflict {
            path: String!
            conflictType: String!
            baseValue: JSON
            sourceValue: JSON
            targetValue: JSON
        }

        type ActionJob {
            id: ID!
            actionType: String!
            status: JobStatus!
            progress: Int!
            totalObjects: Int!
            completedObjects: Int!
            failedObjects: Int!
            createdAt: DateTime!
            completedAt: DateTime
            error: String
        }

        # Enums
        enum JobStatus {
            PENDING
            RUNNING
            COMPLETED
            FAILED
            CANCELLED
        }

        # Inputs
        input ObjectTypeInput {
            name: String!
            displayName: String!
            pluralDisplayName: String
            description: String
            typeClass: String!
        }

        input ObjectTypeUpdate {
            displayName: String
            pluralDisplayName: String
            description: String
            status: String
        }

        input PropertyInput {
            name: String!
            displayName: String!
            dataTypeId: ID!
            isRequired: Boolean
            isPrimaryKey: Boolean
            isUnique: Boolean
            defaultValue: JSON
            validation: JSON
        }

        input PropertyUpdate {
            displayName: String
            isRequired: Boolean
            defaultValue: JSON
            validation: JSON
        }

        input CreateBranchInput {
            name: String!
            fromBranch: String!
            description: String
        }

        input MergeInput {
            strategy: MergeStrategy!
            conflictResolutions: [ConflictResolution!]
            message: String
        }

        input ConflictResolution {
            path: String!
            resolution: ResolutionChoice!
            customValue: JSON
        }

        input ExecuteActionInput {
            actionType: String!
            objectIds: [ID!]!
            parameters: JSON
            branch: String!
        }

        # Custom Scalars
        scalar DateTime
        scalar JSON

        # Filters
        input ObjectTypeFilter {
            name: String
            status: String
            typeClass: String
        }

        enum MergeStrategy {
            MERGE
            SQUASH
            REBASE
        }

        enum ResolutionChoice {
            USE_SOURCE
            USE_TARGET
            USE_BASE
            USE_CUSTOM
        }
        """

        return schema_sdl

    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.http_client.aclose()


class GraphQLSchemaFederation:
    """GraphQL 스키마 페더레이션"""

    def __init__(self):
        self.service_schemas = {}

    def add_service_schema(self, service_name: str, schema: str):
        """서비스 스키마 추가"""
        self.service_schemas[service_name] = schema

    def build_federated_schema(self) -> str:
        """페더레이션 스키마 구성"""

        # Apollo Federation 스타일로 스키마 병합
        # 실제 구현은 더 복잡하지만, 기본 구조만 제공

        federated_parts = []

        # 각 서비스 스키마를 @key 디렉티브로 확장
        for service_name, schema in self.service_schemas.items():
            extended_schema = self._extend_with_federation(service_name, schema)
            federated_parts.append(extended_schema)

        # 루트 스키마 추가
        root_schema = """
        extend type Query {
            _service: _Service!
            _entities(representations: [_Any!]!): [_Entity]!
        }

        type _Service {
            sdl: String!
        }

        scalar _Any
        scalar _Entity
        """

        federated_parts.append(root_schema)

        return "\n\n".join(federated_parts)

    def _extend_with_federation(self, service_name: str, schema: str) -> str:
        """페더레이션 디렉티브 추가"""

        # 간단한 예시 - 실제로는 파싱하여 처리 필요
        return f"""
        # Service: {service_name}
        {schema}
        """
