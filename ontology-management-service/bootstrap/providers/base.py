"""Base provider interface for dependency injection"""

from abc import ABC, abstractmethod
from typing import Any, TypeVar, Generic

T = TypeVar('T')

class Provider(ABC, Generic[T]):
    """Base provider interface for creating and managing service instances"""
    
    @abstractmethod
    async def provide(self) -> T:
        """Create and return the service instance"""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources when shutting down"""
        pass

class SingletonProvider(Provider[T]):
    """Provider that ensures only one instance is created"""
    
    def __init__(self):
        self._instance: T | None = None
    
    async def provide(self) -> T:
        if self._instance is None:
            self._instance = await self._create()
        return self._instance
    
    @abstractmethod
    async def _create(self) -> T:
        """Create the service instance"""
        pass