"""
Base interfaces for commit hook pipeline components
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime


class ValidationError(Exception):
    """Raised when validation fails"""
    def __init__(self, message: str, errors: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.errors = errors or []


@dataclass
class CommitMeta:
    """Metadata about a commit"""
    author: str
    branch: str
    trace_id: str
    commit_msg: str
    commit_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    database: Optional[str] = None


@dataclass
class DiffContext:
    """Context for diff processing"""
    meta: CommitMeta
    diff: Dict[str, Any]
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    affected_types: Optional[List[str]] = None
    affected_ids: Optional[List[str]] = None


class BaseValidator(ABC):
    """Base class for all validators"""
    
    @abstractmethod
    async def validate(self, context: DiffContext) -> None:
        """
        Validate the diff context.
        Should raise ValidationError if validation fails.
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the validator for logging"""
        pass
    
    @property
    def enabled(self) -> bool:
        """Whether this validator is enabled"""
        return True
    
    async def initialize(self) -> None:
        """Initialize the validator (optional)"""
        pass
    
    async def cleanup(self) -> None:
        """Cleanup resources (optional)"""
        pass


class BaseSink(ABC):
    """Base class for all event sinks"""
    
    @abstractmethod
    async def publish(self, context: DiffContext) -> None:
        """
        Publish the event to the sink.
        Should not raise exceptions - log and continue on failure.
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the sink for logging"""
        pass
    
    @property
    def enabled(self) -> bool:
        """Whether this sink is enabled"""
        return True
    
    async def initialize(self) -> None:
        """Initialize the sink (optional)"""
        pass
    
    async def cleanup(self) -> None:
        """Cleanup resources (optional)"""
        pass


class BaseHook(ABC):
    """Base class for general commit hooks"""
    
    @abstractmethod
    async def execute(self, context: DiffContext) -> Any:
        """Execute the hook logic"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the hook for logging"""
        pass
    
    @property
    def phase(self) -> str:
        """Phase when this hook runs: 'pre-commit', 'post-commit', 'async'"""
        return "post-commit"
    
    @property
    def enabled(self) -> bool:
        """Whether this hook is enabled"""
        return True