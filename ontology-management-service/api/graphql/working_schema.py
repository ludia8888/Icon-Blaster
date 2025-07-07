"""Working GraphQL Schema for OMS - Simple approach"""
import strawberry

@strawberry.type
class ObjectType:
    id: str
    name: str
    version: str = "1.0.0"

@strawberry.input
class ObjectTypeInput:
    name: str
    description: str = ""

@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        return "Hello from OMS GraphQL!"
    
    @strawberry.field
    def object_types(self) -> list[ObjectType]:
        """Get all object types"""
        return [
            ObjectType(id="1", name="TestType", version="1.0.0"),
            ObjectType(id="2", name="SampleType", version="1.1.0")
        ]

@strawberry.type
class Mutation:
    @strawberry.field
    def create_object_type(self, input: ObjectTypeInput) -> ObjectType:
        """Create a new object type"""
        return ObjectType(
            id=f"generated_{input.name.lower()}",
            name=input.name,
            version="1.0.0"
        )

@strawberry.type 
class Subscription:
    @strawberry.subscription
    async def object_type_updates(self) -> str:
        """Subscribe to object type updates"""
        yield "Object type updated"

# Create the schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription
)

__all__ = ["schema", "Query", "Mutation", "Subscription"]