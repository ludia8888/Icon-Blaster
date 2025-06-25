"""
Auto-generated Pydantic models for oms-event-sdk
Generated at: 2025-06-25T11:15:14.778517
DO NOT EDIT - This file is auto-generated
"""

from typing import Optional, List, Dict, Any, Union, Callable, Awaitable
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class PublishResult(BaseModel):
    """Result of publishing an event"""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class Subscription:
    """Event subscription handle"""
    
    async def unsubscribe(self) -> None:
        """Unsubscribe from events"""
        pass


# Generated Models
class CloudEvent(BaseModel):
    """Generated model for CloudEvent"""
    specversion: str
    type: str
    source: str
    id: str
    time: Optional[datetime] = None
    datacontenttype: Optional[str] = None
    subject: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
class OMSContext(BaseModel):
    """Generated model for OMSContext"""
    branch: Optional[str] = None
    commit: Optional[str] = None
    author: Optional[str] = None
    tenant: Optional[str] = None
    correlationId: Optional[str] = None
    causationId: Optional[str] = None
EntityType = str
