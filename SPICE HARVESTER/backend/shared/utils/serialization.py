"""
공통 직렬화 유틸리티
중복 제거를 위한 직렬화 믹스인 및 유틸리티
"""

from typing import Dict, Any, Union
from dataclasses import fields, is_dataclass
from datetime import datetime, date


class SerializableMixin:
    """
    직렬화 믹스인 클래스
    dataclass에 추가하여 자동으로 to_dict() 기능 제공
    """
    
    def to_dict(self) -> Dict[str, Any]:
        """
        dataclass를 딕셔너리로 자동 변환
        datetime 객체는 ISO 문자열로 변환
        """
        if not is_dataclass(self):
            raise TypeError(f"{self.__class__.__name__} is not a dataclass")
        
        result = {}
        for field in fields(self):
            value = getattr(self, field.name)
            result[field.name] = self._serialize_value(value)
        
        return result
    
    def _serialize_value(self, value: Any) -> Any:
        """
        값을 직렬화 가능한 형태로 변환
        """
        if value is None:
            return None
        elif isinstance(value, (str, int, float, bool)):
            return value
        elif isinstance(value, (datetime, date)):
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            return [self._serialize_value(item) for item in value]
        elif hasattr(value, 'to_dict'):
            return value.to_dict()
        elif is_dataclass(value):
            # 중첩된 dataclass 처리
            return SerializableMixin.to_dict(value)
        else:
            # 기타 객체는 문자열로 변환
            return str(value)
    
    def to_json_dict(self) -> Dict[str, Any]:
        """
        JSON 직렬화에 최적화된 딕셔너리 반환
        (to_dict의 별칭, 명확성을 위해)
        """
        return self.to_dict()


def serialize_dataclass(obj: Any) -> Dict[str, Any]:
    """
    dataclass 객체를 딕셔너리로 변환하는 함수
    SerializableMixin을 상속하지 않은 클래스에도 사용 가능
    """
    if not is_dataclass(obj):
        raise TypeError(f"{obj.__class__.__name__} is not a dataclass")
    
    result = {}
    for field in fields(obj):
        value = getattr(obj, field.name)
        result[field.name] = _serialize_value_standalone(value)
    
    return result


def _serialize_value_standalone(value: Any) -> Any:
    """
    독립 함수로 사용하는 값 직렬화
    """
    if value is None:
        return None
    elif isinstance(value, (str, int, float, bool)):
        return value
    elif isinstance(value, (datetime, date)):
        return value.isoformat()
    elif isinstance(value, dict):
        return {k: _serialize_value_standalone(v) for k, v in value.items()}
    elif isinstance(value, (list, tuple)):
        return [_serialize_value_standalone(item) for item in value]
    elif hasattr(value, 'to_dict'):
        return value.to_dict()
    elif is_dataclass(value):
        return serialize_dataclass(value)
    else:
        return str(value)


# 하위 호환성을 위한 별칭
ConfigMixin = SerializableMixin