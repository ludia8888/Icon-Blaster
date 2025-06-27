"""
Safe JSON encoder that handles circular references and special values
"""
import json
from typing import Any, Set, Optional
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID
from enum import Enum
import math


class CircularReferenceError(ValueError):
    """Raised when circular reference is detected"""
    pass


def safe_dict_conversion(obj: Any, _seen: Optional[Set[int]] = None, max_depth: int = 100) -> Any:
    """
    Safely convert objects to JSON-serializable format with circular reference detection
    
    Args:
        obj: Object to convert
        _seen: Set of object IDs already seen (for circular reference detection)
        max_depth: Maximum nesting depth to prevent stack overflow
        
    Returns:
        JSON-serializable representation of the object
    """
    if _seen is None:
        _seen = set()
    
    if max_depth <= 0:
        return "***MAX_DEPTH_EXCEEDED***"
    
    # Handle None
    if obj is None:
        return None
    
    # Handle primitives
    if isinstance(obj, (str, int, bool)):
        return obj
    
    # Handle float special values
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        elif math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj
    
    # Handle datetime
    if isinstance(obj, datetime):
        return obj.isoformat()
    
    if isinstance(obj, date):
        return obj.isoformat()
    
    # Handle UUID
    if isinstance(obj, UUID):
        return str(obj)
    
    # Handle Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    
    # Handle Enum
    if isinstance(obj, Enum):
        return obj.value
    
    # Handle bytes
    if isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    
    # Handle dict
    if isinstance(obj, dict):
        obj_id = id(obj)
        if obj_id in _seen:
            return {"***CIRCULAR_REFERENCE***": True}
        
        _seen.add(obj_id)
        try:
            result = {}
            for key, value in obj.items():
                # Ensure key is string
                str_key = str(key) if not isinstance(key, str) else key
                result[str_key] = safe_dict_conversion(value, _seen, max_depth - 1)
            return result
        finally:
            _seen.discard(obj_id)
    
    # Handle list/tuple
    if isinstance(obj, (list, tuple)):
        obj_id = id(obj)
        if obj_id in _seen:
            return ["***CIRCULAR_REFERENCE***"]
        
        _seen.add(obj_id)
        try:
            return [safe_dict_conversion(item, _seen, max_depth - 1) for item in obj]
        finally:
            _seen.discard(obj_id)
    
    # Handle set
    if isinstance(obj, set):
        return list(obj)  # Convert to list
    
    # Handle Pydantic models
    if hasattr(obj, 'model_dump'):
        # Use model_dump for Pydantic v2
        try:
            return safe_dict_conversion(obj.model_dump(), _seen, max_depth - 1)
        except Exception:
            pass
    
    if hasattr(obj, 'dict'):
        # Fallback to dict() for Pydantic v1
        try:
            return safe_dict_conversion(obj.dict(), _seen, max_depth - 1)
        except Exception:
            pass
    
    # Handle objects with __dict__
    if hasattr(obj, '__dict__'):
        obj_id = id(obj)
        if obj_id in _seen:
            return {"***CIRCULAR_REFERENCE***": True}
        
        _seen.add(obj_id)
        try:
            return safe_dict_conversion(vars(obj), _seen, max_depth - 1)
        finally:
            _seen.discard(obj_id)
    
    # Last resort - convert to string
    try:
        return str(obj)
    except Exception:
        return f"***UNSERIALIZABLE: {type(obj).__name__}***"


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """
    Safely serialize object to JSON string handling circular references
    
    Args:
        obj: Object to serialize
        **kwargs: Additional arguments for json.dumps
        
    Returns:
        JSON string
    """
    safe_obj = safe_dict_conversion(obj)
    return json.dumps(safe_obj, **kwargs)


def make_json_safe(data: Any) -> Any:
    """
    Make data JSON-safe by handling circular references and special values
    
    Args:
        data: Data to make JSON-safe
        
    Returns:
        JSON-safe version of the data
    """
    return safe_dict_conversion(data)