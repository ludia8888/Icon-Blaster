"""
🔥 THINK ULTRA! Complex Type Serializer
복합 데이터 타입 직렬화/역직렬화 시스템
"""

import json
from typing import Any, Dict, List, Optional, Union, Tuple
from decimal import Decimal
from datetime import datetime
import base64

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from models.common import DataType


class ComplexTypeSerializer:
    """
    🔥 THINK ULTRA! 복합 타입 직렬화기
    
    TerminusDB 저장을 위한 복합 타입 변환:
    - 복합 타입 → 기본 XSD 타입으로 직렬화
    - 기본 XSD 타입 → 복합 타입으로 역직렬화
    - 메타데이터 보존
    - 타입 안전성 보장
    """
    
    @classmethod
    def serialize(
        cls, 
        value: Any, 
        data_type: str,
        constraints: Optional[Dict[str, Any]] = None
    ) -> Tuple[Any, Dict[str, Any]]:
        """
        복합 타입을 기본 타입으로 직렬화
        
        Args:
            value: 직렬화할 값
            data_type: 데이터 타입
            constraints: 제약조건
            
        Returns:
            (직렬화된 값, 메타데이터)
        """
        
        serializers = {
            DataType.ARRAY.value: cls._serialize_array,
            DataType.OBJECT.value: cls._serialize_object,
            DataType.ENUM.value: cls._serialize_enum,
            DataType.MONEY.value: cls._serialize_money,
            DataType.PHONE.value: cls._serialize_phone,
            DataType.EMAIL.value: cls._serialize_email,
            DataType.COORDINATE.value: cls._serialize_coordinate,
            DataType.ADDRESS.value: cls._serialize_address,
            DataType.IMAGE.value: cls._serialize_image,
            DataType.FILE.value: cls._serialize_file
        }
        
        serializer = serializers.get(data_type)
        if serializer:
            return serializer(value, constraints or {})
        
        # 기본 타입은 그대로 반환
        return value, {"type": data_type}
    
    @classmethod
    def deserialize(
        cls,
        value: Any,
        data_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        기본 타입을 복합 타입으로 역직렬화
        
        Args:
            value: 역직렬화할 값
            data_type: 데이터 타입
            metadata: 메타데이터
            
        Returns:
            역직렬화된 값
        """
        
        deserializers = {
            DataType.ARRAY.value: cls._deserialize_array,
            DataType.OBJECT.value: cls._deserialize_object,
            DataType.ENUM.value: cls._deserialize_enum,
            DataType.MONEY.value: cls._deserialize_money,
            DataType.PHONE.value: cls._deserialize_phone,
            DataType.EMAIL.value: cls._deserialize_email,
            DataType.COORDINATE.value: cls._deserialize_coordinate,
            DataType.ADDRESS.value: cls._deserialize_address,
            DataType.IMAGE.value: cls._deserialize_image,
            DataType.FILE.value: cls._deserialize_file
        }
        
        deserializer = deserializers.get(data_type)
        if deserializer:
            return deserializer(value, metadata or {})
        
        # 기본 타입은 그대로 반환
        return value
    
    @classmethod
    def _serialize_array(cls, value: Any, constraints: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """배열 직렬화"""
        
        # 이미 정규화된 배열이라고 가정
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
        
        metadata = {
            "type": DataType.ARRAY.value,
            "itemCount": len(value),
            "itemType": constraints.get("itemType")
        }
        
        return serialized, metadata
    
    @classmethod
    def _deserialize_array(cls, value: str, metadata: Dict[str, Any]) -> List[Any]:
        """배열 역직렬화"""
        
        if not value:
            return []
        
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    
    @classmethod
    def _serialize_object(cls, value: Any, constraints: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """객체 직렬화"""
        
        # 순환 참조 방지를 위한 기본 직렬화
        def default_serializer(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, datetime):
                return obj.isoformat()
            elif hasattr(obj, "__dict__"):
                return obj.__dict__
            else:
                return str(obj)
        
        serialized = json.dumps(
            value, 
            ensure_ascii=False, 
            sort_keys=True,
            default=default_serializer
        )
        
        metadata = {
            "type": DataType.OBJECT.value,
            "schema": constraints.get("schema", {}),
            "fieldCount": len(value) if isinstance(value, dict) else 0
        }
        
        return serialized, metadata
    
    @classmethod
    def _deserialize_object(cls, value: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """객체 역직렬화"""
        
        if not value:
            return {}
        
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    
    @classmethod
    def _serialize_enum(cls, value: Any, constraints: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """열거형 직렬화"""
        
        metadata = {
            "type": DataType.ENUM.value,
            "allowedValues": constraints.get("enum", [])
        }
        
        return str(value), metadata
    
    @classmethod
    def _deserialize_enum(cls, value: str, metadata: Dict[str, Any]) -> str:
        """열거형 역직렬화"""
        return value
    
    @classmethod
    def _serialize_money(cls, value: Any, constraints: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """통화 직렬화"""
        
        # 정규화된 money 객체
        if isinstance(value, dict):
            amount = value.get("amount", 0)
            currency = value.get("currency", "USD")
            
            # TerminusDB는 decimal을 문자열로 저장
            serialized = json.dumps({
                "amount": str(amount),
                "currency": currency
            })
            
            metadata = {
                "type": DataType.MONEY.value,
                "currency": currency,
                "decimalPlaces": constraints.get("decimalPlaces", 2)
            }
            
            return serialized, metadata
        
        return str(value), {"type": DataType.MONEY.value}
    
    @classmethod
    def _deserialize_money(cls, value: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """통화 역직렬화"""
        
        try:
            data = json.loads(value)
            return {
                "amount": float(data.get("amount", 0)),
                "currency": data.get("currency", "USD"),
                "formatted": f"{float(data.get('amount', 0)):,.2f} {data.get('currency', 'USD')}"
            }
        except (json.JSONDecodeError, ValueError):
            return {"amount": 0, "currency": "USD", "formatted": "0.00 USD"}
    
    @classmethod
    def _serialize_phone(cls, value: Any, constraints: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """전화번호 직렬화"""
        
        # 정규화된 phone 객체
        if isinstance(value, dict):
            serialized = value.get("e164", str(value))
            
            metadata = {
                "type": DataType.PHONE.value,
                "format": "e164",
                "region": value.get("region")
            }
            
            return serialized, metadata
        
        return str(value), {"type": DataType.PHONE.value}
    
    @classmethod
    def _deserialize_phone(cls, value: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """전화번호 역직렬화"""
        
        return {
            "e164": value,
            "region": metadata.get("region"),
            "formatted": value  # 실제로는 phonenumbers 라이브러리로 포맷팅 필요
        }
    
    @classmethod
    def _serialize_email(cls, value: Any, constraints: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """이메일 직렬화"""
        
        # 정규화된 email 객체
        if isinstance(value, dict):
            email = value.get("email", str(value))
            
            metadata = {
                "type": DataType.EMAIL.value,
                "domain": value.get("domain"),
                "local": value.get("local")
            }
            
            return email, metadata
        
        return str(value), {"type": DataType.EMAIL.value}
    
    @classmethod
    def _deserialize_email(cls, value: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """이메일 역직렬화"""
        
        parts = value.split("@")
        return {
            "email": value,
            "local": parts[0] if len(parts) > 1 else value,
            "domain": parts[1] if len(parts) > 1 else ""
        }
    
    @classmethod
    def _serialize_coordinate(cls, value: Any, constraints: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """좌표 직렬화"""
        
        # 정규화된 coordinate 객체
        if isinstance(value, dict):
            lat = value.get("latitude", 0)
            lng = value.get("longitude", 0)
            
            # WKT (Well-Known Text) 형식으로 저장
            serialized = f"POINT({lng} {lat})"
            
            metadata = {
                "type": DataType.COORDINATE.value,
                "format": "wkt",
                "srid": 4326  # WGS84
            }
            
            return serialized, metadata
        
        return str(value), {"type": DataType.COORDINATE.value}
    
    @classmethod
    def _deserialize_coordinate(cls, value: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """좌표 역직렬화"""
        
        # WKT 파싱
        if value.startswith("POINT("):
            coords = value[6:-1].split()
            if len(coords) == 2:
                try:
                    lng = float(coords[0])
                    lat = float(coords[1])
                    return {
                        "latitude": lat,
                        "longitude": lng,
                        "formatted": f"{lat},{lng}",
                        "geojson": {
                            "type": "Point",
                            "coordinates": [lng, lat]
                        }
                    }
                except ValueError:
                    pass
        
        # 기본값
        return {
            "latitude": 0,
            "longitude": 0,
            "formatted": "0,0",
            "geojson": {"type": "Point", "coordinates": [0, 0]}
        }
    
    @classmethod
    def _serialize_address(cls, value: Any, constraints: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """주소 직렬화"""
        
        # 정규화된 address 객체
        if isinstance(value, dict):
            # 구조화된 주소를 JSON으로 저장
            serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
            
            metadata = {
                "type": DataType.ADDRESS.value,
                "country": value.get("country"),
                "hasCoordinates": "latitude" in value and "longitude" in value
            }
            
            return serialized, metadata
        
        return str(value), {"type": DataType.ADDRESS.value}
    
    @classmethod
    def _deserialize_address(cls, value: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """주소 역직렬화"""
        
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"formatted": value}
    
    @classmethod
    def _serialize_image(cls, value: Any, constraints: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """이미지 직렬화"""
        
        # 정규화된 image 객체
        if isinstance(value, dict):
            url = value.get("url", str(value))
            
            metadata = {
                "type": DataType.IMAGE.value,
                "extension": value.get("extension"),
                "width": value.get("width"),
                "height": value.get("height"),
                "size": value.get("size")
            }
            
            return url, metadata
        
        return str(value), {"type": DataType.IMAGE.value}
    
    @classmethod
    def _deserialize_image(cls, value: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """이미지 역직렬화"""
        
        return {
            "url": value,
            "extension": metadata.get("extension"),
            "width": metadata.get("width"),
            "height": metadata.get("height"),
            "size": metadata.get("size")
        }
    
    @classmethod
    def _serialize_file(cls, value: Any, constraints: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """파일 직렬화"""
        
        # 정규화된 file 객체
        if isinstance(value, dict):
            url = value.get("url", str(value))
            
            metadata = {
                "type": DataType.FILE.value,
                "name": value.get("name"),
                "extension": value.get("extension"),
                "mimeType": value.get("mimeType"),
                "size": value.get("size"),
                "uploadedAt": value.get("uploadedAt", datetime.utcnow().isoformat())
            }
            
            return url, metadata
        
        return str(value), {"type": DataType.FILE.value}
    
    @classmethod
    def _deserialize_file(cls, value: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """파일 역직렬화"""
        
        return {
            "url": value,
            "name": metadata.get("name", value.split("/")[-1]),
            "extension": metadata.get("extension"),
            "mimeType": metadata.get("mimeType"),
            "size": metadata.get("size"),
            "uploadedAt": metadata.get("uploadedAt")
        }


class ComplexTypeConverter:
    """
    🔥 THINK ULTRA! 복합 타입 변환기
    
    다양한 형식 간 변환 지원:
    - UI 입력 → 정규화된 형식
    - 정규화된 형식 → DB 저장 형식
    - DB 저장 형식 → API 응답 형식
    """
    
    @staticmethod
    def to_json_ld(value: Any, data_type: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        복합 타입을 JSON-LD 형식으로 변환
        
        TerminusDB 저장을 위한 JSON-LD 구조 생성
        """
        
        base_type = DataType.get_base_type(data_type)
        
        json_ld = {
            "@type": base_type,
            "@value": value
        }
        
        # 복합 타입 메타데이터 추가
        if DataType.is_complex_type(data_type):
            json_ld["@metadata"] = {
                "complexType": data_type,
                **metadata
            }
        
        return json_ld
    
    @staticmethod
    def from_json_ld(json_ld: Dict[str, Any]) -> Tuple[Any, str, Dict[str, Any]]:
        """
        JSON-LD를 복합 타입으로 변환
        
        Returns:
            (값, 데이터타입, 메타데이터)
        """
        
        value = json_ld.get("@value")
        base_type = json_ld.get("@type", DataType.STRING.value)
        
        metadata = json_ld.get("@metadata", {})
        complex_type = metadata.get("complexType", base_type)
        
        return value, complex_type, metadata
    
    @staticmethod
    def to_ui_format(value: Any, data_type: str, locale: str = "en") -> Dict[str, Any]:
        """
        복합 타입을 UI 표시 형식으로 변환
        
        사용자 친화적인 표시 형식 생성
        """
        
        ui_format = {
            "value": value,
            "type": data_type,
            "displayType": data_type.replace("custom:", "").upper()
        }
        
        # 타입별 UI 힌트 추가
        if data_type == DataType.MONEY.value:
            if isinstance(value, dict):
                ui_format["formatted"] = value.get("formatted", "")
                ui_format["inputType"] = "currency"
                ui_format["currencyOptions"] = list(ComplexTypeValidator.SUPPORTED_CURRENCIES)
        
        elif data_type == DataType.PHONE.value:
            ui_format["inputType"] = "tel"
            ui_format["placeholder"] = "+1 (555) 123-4567"
        
        elif data_type == DataType.EMAIL.value:
            ui_format["inputType"] = "email"
            ui_format["placeholder"] = "user@example.com"
        
        elif data_type == DataType.COORDINATE.value:
            ui_format["inputType"] = "coordinate"
            ui_format["mapEnabled"] = True
        
        elif data_type == DataType.ADDRESS.value:
            ui_format["inputType"] = "address"
            ui_format["autocompleteEnabled"] = True
        
        elif data_type == DataType.IMAGE.value:
            ui_format["inputType"] = "image"
            ui_format["previewEnabled"] = True
            ui_format["acceptedFormats"] = list(ComplexTypeValidator.IMAGE_EXTENSIONS)
        
        elif data_type == DataType.FILE.value:
            ui_format["inputType"] = "file"
            ui_format["acceptedFormats"] = list(ComplexTypeValidator.ALLOWED_FILE_EXTENSIONS)
        
        elif data_type == DataType.ARRAY.value:
            ui_format["inputType"] = "array"
            ui_format["addItemEnabled"] = True
        
        elif data_type == DataType.OBJECT.value:
            ui_format["inputType"] = "object"
            ui_format["schemaEditorEnabled"] = True
        
        elif data_type == DataType.ENUM.value:
            ui_format["inputType"] = "select"
            if isinstance(value, dict) and "allowedValues" in value:
                ui_format["options"] = value["allowedValues"]
        
        return ui_format