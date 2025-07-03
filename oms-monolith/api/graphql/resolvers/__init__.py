"""
GraphQL Resolvers Package - 도메인별로 분리된 리졸버 모듈
"""

from .schema.object_types import ObjectTypeResolver
from .schema.properties import PropertyResolver
from .relationships.links import LinkTypeResolver
from .relationships.interfaces import InterfaceResolver
from .actions.action_types import ActionTypeResolver
from .types.functions import FunctionTypeResolver
from .types.data_types import DataTypeResolver
from .versioning.branches import BranchResolver
from .versioning.history import HistoryResolver
from .utilities.validation import ValidationResolver
from .utilities.search import SearchResolver

# Create placeholder Query and Mutation classes
import strawberry

@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        return "Hello World!"

@strawberry.type
class Mutation:
    @strawberry.field
    def create_test(self, name: str) -> str:
        return f"Created {name}"

# Create schema
schema = strawberry.Schema(query=Query, mutation=Mutation)

__all__ = [
    'ObjectTypeResolver',
    'PropertyResolver',
    'LinkTypeResolver',
    'InterfaceResolver',
    'ActionTypeResolver',
    'FunctionTypeResolver',
    'DataTypeResolver',
    'BranchResolver',
    'HistoryResolver',
    'ValidationResolver',
    'SearchResolver',
    'Query',
    'Mutation',
    'schema',
]