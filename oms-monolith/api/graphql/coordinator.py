"""
GraphQL Coordinator - 도메인 리졸버들을 조율하는 Facade 패턴 구현
"""
import strawberry
from typing import Optional
from .resolvers import (
    ObjectTypeResolver, PropertyResolver, LinkTypeResolver,
    InterfaceResolver, ActionTypeResolver, FunctionTypeResolver,
    DataTypeResolver, BranchResolver, HistoryResolver,
    ValidationResolver, SearchResolver
)
from .schema import (
    ObjectType, ObjectTypeConnection, ObjectTypeInput, ObjectTypeUpdateInput,
    Property, SharedProperty, LinkType, Interface, Branch,
    ActionType, ActionTypeInput, ActionTypeUpdateInput,
    FunctionType, FunctionTypeInput, FunctionTypeUpdateInput,
    DataType, DataTypeInput, DataTypeUpdateInput,
    ValidationResult, SearchResult, HistoryEntry,
    StatusEnum, TypeClassEnum, FunctionCategoryEnum, 
    DataTypeCategoryEnum, BranchStatusEnum
)


@strawberry.type
class Query:
    """통합 GraphQL Query - Coordinator 패턴"""
    
    def __init__(self):
        self._object_resolver = ObjectTypeResolver()
        self._property_resolver = PropertyResolver()
        self._link_resolver = LinkTypeResolver()
        self._interface_resolver = InterfaceResolver()
        self._action_resolver = ActionTypeResolver()
        self._function_resolver = FunctionTypeResolver()
        self._data_resolver = DataTypeResolver()
        self._branch_resolver = BranchResolver()
        self._history_resolver = HistoryResolver()
        self._validation_resolver = ValidationResolver()
        self._search_resolver = SearchResolver()
    
    # Object Type Queries
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
        """객체 타입 목록 조회"""
        return await self._object_resolver.get_object_types(
            info, branch, status, type_class, interface, search,
            include_properties, include_deprecated, limit, offset
        )
    
    @strawberry.field
    async def object_type(
        self,
        info: strawberry.Info,
        name: str,
        branch: str = "main",
        include_properties: bool = True,
        include_deprecated: bool = False
    ) -> Optional[ObjectType]:
        """단일 객체 타입 조회"""
        return await self._object_resolver.get_object_type(
            info, name, branch, include_properties, include_deprecated
        )
    
    # Property Queries
    @strawberry.field
    async def properties(
        self,
        info: strawberry.Info,
        object_type: str,
        branch: str = "main",
        include_deprecated: bool = False
    ) -> list[Property]:
        """객체 타입의 속성 목록 조회"""
        return await self._property_resolver.get_properties(
            info, object_type, branch, include_deprecated
        )
    
    @strawberry.field
    async def shared_properties(
        self,
        info: strawberry.Info,
        branch: str = "main",
        include_deprecated: bool = False
    ) -> list[SharedProperty]:
        """공유 속성 목록 조회"""
        return await self._property_resolver.get_shared_properties(
            info, branch, include_deprecated
        )
    
    # Additional queries would follow the same pattern...


@strawberry.type
class Mutation:
    """통합 GraphQL Mutation - Coordinator 패턴"""
    
    def __init__(self):
        self._object_resolver = ObjectTypeResolver()
        self._property_resolver = PropertyResolver()
        self._action_resolver = ActionTypeResolver()
        self._function_resolver = FunctionTypeResolver()
        self._data_resolver = DataTypeResolver()
    
    # Object Type Mutations
    @strawberry.mutation
    async def create_object_type(
        self,
        info: strawberry.Info,
        input: ObjectTypeInput,
        branch: str = "main"
    ) -> ObjectType:
        """객체 타입 생성"""
        return await self._object_resolver.create_object_type(
            info, input, branch
        )
    
    @strawberry.mutation
    async def update_object_type(
        self,
        info: strawberry.Info,
        name: str,
        input: ObjectTypeUpdateInput,
        branch: str = "main"
    ) -> ObjectType:
        """객체 타입 수정"""
        return await self._object_resolver.update_object_type(
            info, name, input, branch
        )
    
    @strawberry.mutation
    async def delete_object_type(
        self,
        info: strawberry.Info,
        name: str,
        branch: str = "main"
    ) -> bool:
        """객체 타입 삭제"""
        return await self._object_resolver.delete_object_type(
            info, name, branch
        )
    
    # Additional mutations would follow the same pattern...


class GraphQLCoordinator:
    """
    도메인 간 조율 및 트랜잭션 관리를 위한 Coordinator
    복잡한 비즈니스 로직이나 여러 도메인에 걸친 작업을 처리
    """
    
    def __init__(self):
        self.resolvers = {
            'object': ObjectTypeResolver(),
            'property': PropertyResolver(),
            'link': LinkTypeResolver(),
            'interface': InterfaceResolver(),
            'action': ActionTypeResolver(),
            'function': FunctionTypeResolver(),
            'data': DataTypeResolver(),
            'branch': BranchResolver(),
            'history': HistoryResolver(),
            'validation': ValidationResolver(),
            'search': SearchResolver()
        }
    
    async def create_object_with_properties(
        self, 
        info: strawberry.Info,
        object_input: ObjectTypeInput,
        properties: list[dict],
        branch: str = "main"
    ) -> ObjectType:
        """
        객체 타입과 속성을 함께 생성하는 트랜잭션
        여러 도메인에 걸친 작업을 조율
        """
        try:
            # 1. 객체 타입 생성
            obj = await self.resolvers['object'].create_object_type(
                info, object_input, branch
            )
            
            # 2. 속성들 생성
            for prop in properties:
                await self.resolvers['property'].create_property(
                    info, obj.name, prop, branch
                )
            
            # 3. 최종 객체 조회 (속성 포함)
            return await self.resolvers['object'].get_object_type(
                info, obj.name, branch, include_properties=True
            )
            
        except Exception as e:
            # 롤백 로직
            await self._rollback_object_creation(info, object_input.name, branch)
            raise e
    
    async def _rollback_object_creation(
        self, 
        info: strawberry.Info,
        object_name: str, 
        branch: str
    ):
        """객체 생성 롤백"""
        try:
            await self.resolvers['object'].delete_object_type(
                info, object_name, branch
            )
        except:
            pass  # 롤백 실패는 무시