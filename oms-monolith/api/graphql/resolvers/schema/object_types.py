"""
Object Type Resolver - 객체 타입 관련 Query/Mutation
"""
from typing import List, Optional
import strawberry
from ..base import BaseResolver
from ...schema import (
    ObjectType, ObjectTypeConnection, ObjectTypeInput, 
    ObjectTypeUpdateInput, StatusEnum, TypeClassEnum
)


class ObjectTypeResolver(BaseResolver):
    """객체 타입 리졸버"""
    
    async def get_object_types(
        self,
        info,
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
        user = await self.get_current_user(info)
        
        params = {
            "branch": branch,
            "include_properties": include_properties,
            "include_deprecated": include_deprecated,
            "limit": limit,
            "offset": offset
        }
        
        if status:
            params["status"] = status.value
        if type_class:
            params["type_class"] = type_class.value
        if interface:
            params["interface"] = interface
        if search:
            params["search"] = search
        
        url = f"{self.service_client.schema_service_url}/api/v1/object-types"
        response = await self.service_client.call_service(
            url, 
            method="GET", 
            json_data=params, 
            user=user
        )
        
        return self._convert_to_connection(response)
    
    async def get_object_type(
        self,
        info,
        name: str,
        branch: str = "main",
        include_properties: bool = True,
        include_deprecated: bool = False
    ) -> Optional[ObjectType]:
        """단일 객체 타입 조회"""
        user = await self.get_current_user(info)
        
        params = {
            "branch": branch,
            "include_properties": include_properties,
            "include_deprecated": include_deprecated
        }
        
        url = f"{self.service_client.schema_service_url}/api/v1/object-types/{name}"
        
        try:
            response = await self.service_client.call_service(
                url, 
                method="GET", 
                json_data=params, 
                user=user
            )
            return self._convert_to_object_type(response)
        except Exception as e:
            return await self.handle_service_error(e, f"get_object_type({name})")
    
    async def create_object_type(
        self,
        info,
        input: ObjectTypeInput,
        branch: str = "main"
    ) -> ObjectType:
        """객체 타입 생성"""
        user = await self.get_current_user(info)
        
        data = {
            "branch": branch,
            **input.__dict__
        }
        
        url = f"{self.service_client.schema_service_url}/api/v1/object-types"
        response = await self.service_client.call_service(
            url, 
            method="POST", 
            json_data=data, 
            user=user
        )
        
        self.log_operation("create_object_type", name=input.name, branch=branch)
        return self._convert_to_object_type(response)
    
    async def update_object_type(
        self,
        info,
        name: str,
        input: ObjectTypeUpdateInput,
        branch: str = "main"
    ) -> ObjectType:
        """객체 타입 수정"""
        user = await self.get_current_user(info)
        
        data = {
            "branch": branch,
            **{k: v for k, v in input.__dict__.items() if v is not None}
        }
        
        url = f"{self.service_client.schema_service_url}/api/v1/object-types/{name}"
        response = await self.service_client.call_service(
            url, 
            method="PUT", 
            json_data=data, 
            user=user
        )
        
        self.log_operation("update_object_type", name=name, branch=branch)
        return self._convert_to_object_type(response)
    
    async def delete_object_type(
        self,
        info,
        name: str,
        branch: str = "main"
    ) -> bool:
        """객체 타입 삭제"""
        user = await self.get_current_user(info)
        
        url = f"{self.service_client.schema_service_url}/api/v1/object-types/{name}"
        await self.service_client.call_service(
            url, 
            method="DELETE", 
            json_data={"branch": branch}, 
            user=user
        )
        
        self.log_operation("delete_object_type", name=name, branch=branch)
        return True
    
    def _convert_to_object_type(self, data: dict) -> ObjectType:
        """API 응답을 ObjectType으로 변환"""
        from .converters import convert_object_type_response
        return convert_object_type_response(data)
    
    def _convert_to_connection(self, data: dict) -> ObjectTypeConnection:
        """API 응답을 ObjectTypeConnection으로 변환"""
        from .converters import convert_object_type_connection
        return convert_object_type_connection(data)