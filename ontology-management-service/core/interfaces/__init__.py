"""Domain service interfaces using Python protocols"""

from .schema import SchemaServiceProtocol
from .validation import ValidationServiceProtocol
from .event import EventPublisherProtocol
from .database import DatabaseClientProtocol

__all__ = [
    "SchemaServiceProtocol",
    "ValidationServiceProtocol",
    "EventPublisherProtocol",
    "DatabaseClientProtocol"
]