"""
Enhanced API Schema Generator for OMS

Implements Phase 5 of the Ontology Development Plan.
Generates GraphQL and OpenAPI schemas with automatic link field generation.

IMPORTANT: OMS only generates schema metadata. Actual resolvers and runtime
implementations are handled by external services (Object Set Service, etc.)
"""

from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field
import json
from textwrap import dedent

from models.domain import (
    ObjectType, LinkType, Property, 
    Cardinality, Directionality, Status
)
from models.semantic_types import semantic_type_registry
from models.struct_types import struct_type_registry
from core.graph.metadata_generator import graph_metadata_generator
from common_logging.setup import get_logger

logger = get_logger(__name__)


class LinkFieldMetadata(BaseModel):
    """Metadata for a generated link field"""
    field_name: str
    field_type: str  # "SingleLink" or "LinkSet"
    target_type: str
    link_type_id: str
    is_required: bool = False
    is_bidirectional: bool = False
    description: Optional[str] = None
    
    # Metadata hints for resolvers
    resolver_hints: Dict[str, Any] = Field(default_factory=dict)


class GraphQLSchemaGenerator:
    """
    Generates GraphQL schema definitions for object types with link fields.
    
    This generator creates the schema METADATA only. It does not implement
    resolvers - those are handled by the Object Set Service and other runtime services.
    """
    
    def __init__(self):
        self.generated_types: Dict[str, str] = {}
        self.link_fields: Dict[str, List[LinkFieldMetadata]] = {}
        
    def generate_object_type_schema(
        self, 
        object_type: ObjectType,
        link_types: List[LinkType]
    ) -> str:
        """
        Generate GraphQL type definition for an object type including link fields.
        
        Returns GraphQL SDL (Schema Definition Language) as a string.
        """
        # Start with type definition
        sdl = f"type {object_type.name} {{\n"
        sdl += f"  id: ID!\n"
        
        # Add properties
        for prop in object_type.properties:
            sdl += self._generate_property_field(prop)
        
        # Add link fields
        link_fields = self._generate_link_fields(object_type, link_types)
        self.link_fields[object_type.id] = link_fields
        
        for field in link_fields:
            sdl += self._generate_link_field_sdl(field)
        
        # Add metadata fields
        sdl += "  _metadata: ObjectMetadata!\n"
        sdl += "}\n\n"
        
        # Generate input types
        sdl += self._generate_input_types(object_type, link_fields)
        
        self.generated_types[object_type.id] = sdl
        return sdl
    
    def _generate_property_field(self, prop: Property) -> str:
        """Generate GraphQL field for a property"""
        field_type = self._map_data_type_to_graphql(prop.data_type_id)
        
        if prop.is_array:
            field_type = f"[{field_type}]"
        
        if prop.is_required:
            field_type = f"{field_type}!"
        
        return f'  {prop.name}: {field_type}\n'
    
    def _generate_link_fields(
        self, 
        object_type: ObjectType,
        link_types: List[LinkType]
    ) -> List[LinkFieldMetadata]:
        """Generate link field metadata for an object type"""
        fields = []
        
        # Forward links (this object is the source)
        forward_links = [
            lt for lt in link_types 
            if lt.fromTypeId == object_type.id
        ]
        
        for link in forward_links:
            field = LinkFieldMetadata(
                field_name=self._generate_field_name(link, "forward"),
                field_type=self._determine_field_type(link.cardinality),
                target_type=link.toTypeId,
                link_type_id=link.id,
                is_required=link.isRequired,
                is_bidirectional=link.directionality == Directionality.BIDIRECTIONAL,
                description=link.description,
                resolver_hints={
                    "direction": "forward",
                    "cardinality": link.cardinality.value if link.cardinality else "unknown",
                    "cascade_delete": link.cascadeDelete
                }
            )
            fields.append(field)
        
        # Reverse links (this object is the target)
        reverse_links = [
            lt for lt in link_types 
            if lt.toTypeId == object_type.id and 
            lt.directionality == Directionality.BIDIRECTIONAL
        ]
        
        for link in reverse_links:
            field = LinkFieldMetadata(
                field_name=self._generate_field_name(link, "reverse"),
                field_type=self._determine_reverse_field_type(link.cardinality),
                target_type=link.fromTypeId,
                link_type_id=link.id,
                is_required=False,  # Reverse links are never required
                is_bidirectional=True,
                description=f"Reverse link: {link.description}",
                resolver_hints={
                    "direction": "reverse",
                    "cardinality": link.cardinality.value if link.cardinality else "unknown"
                }
            )
            fields.append(field)
        
        return fields
    
    def _generate_link_field_sdl(self, field: LinkFieldMetadata) -> str:
        """Generate GraphQL SDL for a link field"""
        field_type = field.target_type
        
        if field.field_type == "LinkSet":
            field_type = f"[{field_type}!]"
            
        if field.is_required:
            field_type = f"{field_type}!"
            
        # Add resolver directive hint (for Object Set Service)
        resolver_hint = json.dumps(field.resolver_hints)
        directive = f'@link(metadata: """{resolver_hint}""")'
        
        description = f'"{field.description}"' if field.description else '""'
        
        return f'  {field.field_name}: {field_type} {directive}\n'
    
    def _generate_field_name(self, link: LinkType, direction: str) -> str:
        """Generate field name for a link"""
        if direction == "forward":
            # Use link name or generate from target type
            if link.name:
                return link.name.lower().replace(" ", "_")
            else:
                # Generate from target type if name is empty
                target_name = link.toTypeId.lower()
                return f"{target_name}s" if self._is_many(link.cardinality) else target_name
        else:
            # Reverse link naming
            if link.name:
                return f"inverse_{link.name.lower().replace(' ', '_')}"
            else:
                # Generate from source type if name is empty
                return f"inverse_{link.fromTypeId.lower()}"
    
    def _determine_field_type(self, cardinality: Cardinality) -> str:
        """Determine if field should be SingleLink or LinkSet"""
        if cardinality is None:
            # Default to LinkSet for safety
            return "LinkSet"
        elif cardinality == Cardinality.ONE_TO_ONE:
            return "SingleLink"
        else:
            return "LinkSet"
    
    def _determine_reverse_field_type(self, cardinality: Cardinality) -> str:
        """Determine reverse field type based on cardinality"""
        if cardinality is None:
            # Default to LinkSet for safety
            return "LinkSet"
        # Reverse cardinality logic
        elif cardinality == Cardinality.ONE_TO_ONE:
            return "SingleLink"
        elif cardinality == Cardinality.ONE_TO_MANY:
            return "SingleLink"  # Reverse of one-to-many is many-to-one
        else:
            return "LinkSet"
    
    def _is_many(self, cardinality: Cardinality) -> bool:
        """Check if cardinality represents multiple items"""
        if cardinality is None:
            return True  # Default to many for safety
        return cardinality in [Cardinality.ONE_TO_MANY, Cardinality.MANY_TO_MANY]
    
    def _map_data_type_to_graphql(self, data_type_id: str) -> str:
        """Map OMS data type to GraphQL type"""
        mapping = {
            "string": "String",
            "integer": "Int",
            "long": "BigInt",
            "float": "Float",
            "double": "Float",
            "boolean": "Boolean",
            "date": "Date",
            "datetime": "DateTime",
            "time": "Time",
            "decimal": "Decimal",
            "binary": "Binary",
            "json": "JSON"
        }
        
        # Check if it's a struct type
        if struct_type_registry.exists(data_type_id):
            return data_type_id.title().replace("_", "")
            
        return mapping.get(data_type_id, "String")
    
    def _generate_input_types(
        self, 
        object_type: ObjectType,
        link_fields: List[LinkFieldMetadata]
    ) -> str:
        """Generate input types for mutations"""
        # Create input type
        sdl = f"input {object_type.name}CreateInput {{\n"
        
        # Add property fields
        for prop in object_type.properties:
            if not prop.is_primary_key:  # Skip ID fields
                field_type = self._map_data_type_to_graphql(prop.data_type_id)
                if prop.is_array:
                    field_type = f"[{field_type}]"
                if prop.is_required:
                    field_type = f"{field_type}!"
                sdl += f"  {prop.name}: {field_type}\n"
        
        # Add link connection inputs
        for field in link_fields:
            if field.field_type == "SingleLink":
                sdl += f"  {field.field_name}Id: ID\n"
            else:
                sdl += f"  {field.field_name}Ids: [ID!]\n"
        
        sdl += "}\n\n"
        
        # Update input type
        sdl += f"input {object_type.name}UpdateInput {{\n"
        
        # All fields optional for updates
        for prop in object_type.properties:
            if not prop.is_primary_key:
                field_type = self._map_data_type_to_graphql(prop.data_type_id)
                if prop.is_array:
                    field_type = f"[{field_type}]"
                sdl += f"  {prop.name}: {field_type}\n"
        
        # Link updates
        for field in link_fields:
            if field.field_type == "SingleLink":
                sdl += f"  {field.field_name}Id: ID\n"
            else:
                sdl += f"  {field.field_name}Ids: [ID!]\n"
                sdl += f"  add{field.field_name.title()}Ids: [ID!]\n"
                sdl += f"  remove{field.field_name.title()}Ids: [ID!]\n"
        
        sdl += "}\n\n"
        
        return sdl
    
    def generate_complete_schema(
        self,
        object_types: List[ObjectType],
        link_types: List[LinkType]
    ) -> str:
        """Generate complete GraphQL schema for all types"""
        sdl = """
# Auto-generated GraphQL Schema by OMS
# This schema defines the structure only. Resolvers are implemented by external services.

scalar DateTime
scalar Date
scalar Time
scalar Decimal
scalar BigInt
scalar Binary
scalar JSON

# Directives for metadata
directive @link(metadata: String) on FIELD_DEFINITION

# Common metadata type
type ObjectMetadata {
  id: ID!
  versionHash: String!
  createdAt: DateTime!
  createdBy: String!
  modifiedAt: DateTime!
  modifiedBy: String!
}

"""
        
        # Generate types
        for object_type in object_types:
            if object_type.status == Status.ACTIVE:
                sdl += self.generate_object_type_schema(object_type, link_types)
                sdl += "\n"
        
        # Add queries
        sdl += self._generate_queries(object_types)
        
        # Add mutations
        sdl += self._generate_mutations(object_types)
        
        return sdl
    
    def _generate_queries(self, object_types: List[ObjectType]) -> str:
        """Generate query type"""
        sdl = "type Query {\n"
        
        for obj_type in object_types:
            if obj_type.status == Status.ACTIVE:
                # Single object query
                sdl += f"  {obj_type.name.lower()}(id: ID!): {obj_type.name}\n"
                
                # List query with pagination
                sdl += f"  {obj_type.name.lower()}s(first: Int, after: String, filter: {obj_type.name}Filter): {obj_type.name}Connection!\n"
        
        sdl += "}\n\n"
        
        # Generate filter and connection types
        for obj_type in object_types:
            if obj_type.status == Status.ACTIVE:
                sdl += self._generate_filter_type(obj_type)
                sdl += self._generate_connection_type(obj_type)
        
        return sdl
    
    def _generate_mutations(self, object_types: List[ObjectType]) -> str:
        """Generate mutation type"""
        sdl = "type Mutation {\n"
        
        for obj_type in object_types:
            if obj_type.status == Status.ACTIVE:
                sdl += f"  create{obj_type.name}(input: {obj_type.name}CreateInput!): {obj_type.name}!\n"
                sdl += f"  update{obj_type.name}(id: ID!, input: {obj_type.name}UpdateInput!): {obj_type.name}!\n"
                sdl += f"  delete{obj_type.name}(id: ID!): Boolean!\n"
        
        sdl += "}\n\n"
        return sdl
    
    def _generate_filter_type(self, object_type: ObjectType) -> str:
        """Generate filter input type for queries"""
        sdl = f"input {object_type.name}Filter {{\n"
        
        # Add filters for each property
        for prop in object_type.properties:
            base_type = self._map_data_type_to_graphql(prop.data_type_id)
            
            if base_type in ["String", "Int", "Float", "DateTime"]:
                sdl += f"  {prop.name}: {base_type}\n"
                sdl += f"  {prop.name}_not: {base_type}\n"
                sdl += f"  {prop.name}_in: [{base_type}!]\n"
                sdl += f"  {prop.name}_not_in: [{base_type}!]\n"
                
                if base_type in ["Int", "Float", "DateTime"]:
                    sdl += f"  {prop.name}_lt: {base_type}\n"
                    sdl += f"  {prop.name}_lte: {base_type}\n"
                    sdl += f"  {prop.name}_gt: {base_type}\n"
                    sdl += f"  {prop.name}_gte: {base_type}\n"
                    
                if base_type == "String":
                    sdl += f"  {prop.name}_contains: String\n"
                    sdl += f"  {prop.name}_starts_with: String\n"
                    sdl += f"  {prop.name}_ends_with: String\n"
        
        # Logical operators
        sdl += f"  AND: [{object_type.name}Filter!]\n"
        sdl += f"  OR: [{object_type.name}Filter!]\n"
        sdl += f"  NOT: {object_type.name}Filter\n"
        
        sdl += "}\n\n"
        return sdl
    
    def _generate_connection_type(self, object_type: ObjectType) -> str:
        """Generate connection type for pagination"""
        sdl = f"""type {object_type.name}Connection {{
  edges: [{object_type.name}Edge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}}

type {object_type.name}Edge {{
  node: {object_type.name}!
  cursor: String!
}}

"""
        return sdl
    
    def export_schema_metadata(self) -> Dict[str, Any]:
        """
        Export metadata about the generated schema.
        This is used by Object Set Service and other services to understand
        the link structure and implement resolvers.
        """
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "version": "1.0",
            "link_fields": {
                type_id: [field.model_dump() for field in fields]
                for type_id, fields in self.link_fields.items()
            },
            "generator": "OMS GraphQL Schema Generator"
        }


class OpenAPISchemaGenerator:
    """
    Generates OpenAPI 3.0 schemas for REST endpoints.
    
    Focuses on generating schemas that include link relationships
    as nested resources or HAL-style links.
    """
    
    def __init__(self):
        self.components: Dict[str, Any] = {
            "schemas": {},
            "parameters": {},
            "responses": {}
        }
    
    def generate_object_schema(
        self,
        object_type: ObjectType,
        link_types: List[LinkType]
    ) -> Dict[str, Any]:
        """Generate OpenAPI schema for an object type"""
        schema = {
            "type": "object",
            "title": object_type.display_name,
            "description": object_type.description,
            "properties": {
                "id": {
                    "type": "string",
                    "format": "uuid",
                    "readOnly": True
                }
            },
            "required": ["id"]
        }
        
        # Add properties
        for prop in object_type.properties:
            prop_schema = self._generate_property_schema(prop)
            schema["properties"][prop.name] = prop_schema
            
            if prop.is_required:
                schema["required"].append(prop.name)
        
        # Add link fields as _links (HAL style)
        links_schema = self._generate_links_schema(object_type, link_types)
        if links_schema:
            schema["properties"]["_links"] = links_schema
        
        # Add embedded resources
        embedded_schema = self._generate_embedded_schema(object_type, link_types)
        if embedded_schema:
            schema["properties"]["_embedded"] = embedded_schema
        
        # Add metadata
        schema["properties"]["_metadata"] = {
            "type": "object",
            "properties": {
                "versionHash": {"type": "string"},
                "createdAt": {"type": "string", "format": "date-time"},
                "createdBy": {"type": "string"},
                "modifiedAt": {"type": "string", "format": "date-time"},
                "modifiedBy": {"type": "string"}
            },
            "readOnly": True
        }
        
        self.components["schemas"][object_type.name] = schema
        return schema
    
    def _generate_property_schema(self, prop: Property) -> Dict[str, Any]:
        """Generate OpenAPI schema for a property"""
        schema = {
            "description": prop.description
        }
        
        # Map data type
        base_schema = self._map_data_type_to_openapi(prop.data_type_id)
        
        if prop.is_array:
            schema["type"] = "array"
            schema["items"] = base_schema
        else:
            schema.update(base_schema)
        
        # Add constraints from semantic type
        if prop.semantic_type_id:
            semantic_type = semantic_type_registry.get(prop.semantic_type_id)
            if semantic_type:
                for rule in semantic_type.validation_rules:
                    if rule.type == "pattern":
                        schema["pattern"] = rule.value
                    elif rule.type == "min_value":
                        schema["minimum"] = rule.value
                    elif rule.type == "max_value":
                        schema["maximum"] = rule.value
                    elif rule.type == "enum":
                        schema["enum"] = rule.value
        
        # Add default value
        if prop.default_value is not None:
            schema["default"] = prop.default_value
        
        return schema
    
    def _generate_links_schema(
        self,
        object_type: ObjectType,
        link_types: List[LinkType]
    ) -> Optional[Dict[str, Any]]:
        """Generate HAL-style _links schema"""
        links = {}
        
        # Self link
        links["self"] = {
            "type": "object",
            "properties": {
                "href": {"type": "string", "format": "uri"}
            }
        }
        
        # Add links for relationships
        forward_links = [
            lt for lt in link_types 
            if lt.fromTypeId == object_type.id
        ]
        
        for link in forward_links:
            link_name = link.name.lower().replace(" ", "_")
            if self._is_many(link.cardinality):
                links[link_name] = {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "href": {"type": "string", "format": "uri"},
                            "title": {"type": "string"}
                        }
                    }
                }
            else:
                links[link_name] = {
                    "type": "object",
                    "properties": {
                        "href": {"type": "string", "format": "uri"},
                        "title": {"type": "string"}
                    }
                }
        
        if len(links) > 1:  # More than just self link
            return {
                "type": "object",
                "properties": links,
                "readOnly": True
            }
        
        return None
    
    def _generate_embedded_schema(
        self,
        object_type: ObjectType,
        link_types: List[LinkType]
    ) -> Optional[Dict[str, Any]]:
        """Generate _embedded schema for expandable resources"""
        embedded = {}
        
        # Forward links that might be embedded
        forward_links = [
            lt for lt in link_types 
            if lt.fromTypeId == object_type.id
        ]
        
        for link in forward_links:
            link_name = link.name.lower().replace(" ", "_")
            target_ref = f"#/components/schemas/{link.toTypeId}"
            
            if self._is_many(link.cardinality):
                embedded[link_name] = {
                    "type": "array",
                    "items": {"$ref": target_ref}
                }
            else:
                embedded[link_name] = {"$ref": target_ref}
        
        if embedded:
            return {
                "type": "object",
                "properties": embedded,
                "readOnly": True
            }
        
        return None
    
    def _map_data_type_to_openapi(self, data_type_id: str) -> Dict[str, Any]:
        """Map OMS data type to OpenAPI type"""
        mapping = {
            "string": {"type": "string"},
            "integer": {"type": "integer", "format": "int32"},
            "long": {"type": "integer", "format": "int64"},
            "float": {"type": "number", "format": "float"},
            "double": {"type": "number", "format": "double"},
            "boolean": {"type": "boolean"},
            "date": {"type": "string", "format": "date"},
            "datetime": {"type": "string", "format": "date-time"},
            "time": {"type": "string", "format": "time"},
            "decimal": {"type": "string", "format": "decimal"},
            "binary": {"type": "string", "format": "binary"},
            "json": {"type": "object"}
        }
        
        # Check if it's a struct type
        if struct_type_registry.exists(data_type_id):
            struct_type = struct_type_registry.get(data_type_id)
            return {"$ref": f"#/components/schemas/{struct_type.name}"}
        
        return mapping.get(data_type_id, {"type": "string"})
    
    def _is_many(self, cardinality: Cardinality) -> bool:
        """Check if cardinality represents multiple items"""
        if cardinality is None:
            return True  # Default to many for safety
        return cardinality in [Cardinality.ONE_TO_MANY, Cardinality.MANY_TO_MANY]
    
    def generate_paths(
        self,
        object_types: List[ObjectType],
        link_types: List[LinkType]
    ) -> Dict[str, Any]:
        """Generate OpenAPI paths for all object types"""
        paths = {}
        
        for obj_type in object_types:
            if obj_type.status == Status.ACTIVE:
                base_path = f"/{obj_type.name.lower()}s"
                
                # Collection endpoints
                paths[base_path] = {
                    "get": self._generate_list_operation(obj_type),
                    "post": self._generate_create_operation(obj_type)
                }
                
                # Item endpoints
                item_path = f"{base_path}/{{id}}"
                paths[item_path] = {
                    "get": self._generate_get_operation(obj_type),
                    "put": self._generate_update_operation(obj_type),
                    "delete": self._generate_delete_operation(obj_type)
                }
                
                # Link endpoints
                forward_links = [
                    lt for lt in link_types 
                    if lt.fromTypeId == obj_type.id
                ]
                
                for link in forward_links:
                    link_path = f"{item_path}/{link.name.lower().replace(' ', '_')}"
                    paths[link_path] = self._generate_link_operations(obj_type, link)
        
        return paths
    
    def _generate_list_operation(self, object_type: ObjectType) -> Dict[str, Any]:
        """Generate list operation"""
        return {
            "summary": f"List {object_type.display_name}s",
            "operationId": f"list{object_type.name}s",
            "tags": [object_type.name],
            "parameters": [
                {"$ref": "#/components/parameters/limit"},
                {"$ref": "#/components/parameters/offset"},
                {"$ref": "#/components/parameters/sort"},
                {"$ref": "#/components/parameters/filter"}
            ],
            "responses": {
                "200": {
                    "description": "Success",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "data": {
                                        "type": "array",
                                        "items": {"$ref": f"#/components/schemas/{object_type.name}"}
                                    },
                                    "meta": {
                                        "type": "object",
                                        "properties": {
                                            "total": {"type": "integer"},
                                            "limit": {"type": "integer"},
                                            "offset": {"type": "integer"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def _generate_create_operation(self, object_type: ObjectType) -> Dict[str, Any]:
        """Generate create operation"""
        return {
            "summary": f"Create {object_type.display_name}",
            "operationId": f"create{object_type.name}",
            "tags": [object_type.name],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{object_type.name}Create"}
                    }
                }
            },
            "responses": {
                "201": {
                    "description": "Created",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{object_type.name}"}
                        }
                    }
                }
            }
        }
    
    def _generate_get_operation(self, object_type: ObjectType) -> Dict[str, Any]:
        """Generate get operation"""
        return {
            "summary": f"Get {object_type.display_name}",
            "operationId": f"get{object_type.name}",
            "tags": [object_type.name],
            "parameters": [
                {
                    "name": "id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"}
                },
                {"$ref": "#/components/parameters/expand"}
            ],
            "responses": {
                "200": {
                    "description": "Success",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{object_type.name}"}
                        }
                    }
                },
                "404": {"description": "Not Found"}
            }
        }
    
    def _generate_update_operation(self, object_type: ObjectType) -> Dict[str, Any]:
        """Generate update operation"""
        return {
            "summary": f"Update {object_type.display_name}",
            "operationId": f"update{object_type.name}",
            "tags": [object_type.name],
            "parameters": [
                {
                    "name": "id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"}
                }
            ],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{object_type.name}Update"}
                    }
                }
            },
            "responses": {
                "200": {
                    "description": "Success",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{object_type.name}"}
                        }
                    }
                },
                "404": {"description": "Not Found"}
            }
        }
    
    def _generate_delete_operation(self, object_type: ObjectType) -> Dict[str, Any]:
        """Generate delete operation"""
        return {
            "summary": f"Delete {object_type.display_name}",
            "operationId": f"delete{object_type.name}",
            "tags": [object_type.name],
            "parameters": [
                {
                    "name": "id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"}
                }
            ],
            "responses": {
                "204": {"description": "Deleted"},
                "404": {"description": "Not Found"}
            }
        }
    
    def _generate_link_operations(
        self,
        object_type: ObjectType,
        link_type: LinkType
    ) -> Dict[str, Any]:
        """Generate operations for link endpoints"""
        operations = {}
        
        if self._is_many(link_type.cardinality):
            # List linked objects
            operations["get"] = {
                "summary": f"Get {link_type.displayName} for {object_type.display_name}",
                "operationId": f"get{object_type.name}{link_type.name}",
                "tags": [object_type.name],
                "parameters": [
                    {"$ref": "#/components/parameters/limit"},
                    {"$ref": "#/components/parameters/offset"}
                ],
                "responses": {
                    "200": {
                        "description": "Success",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": f"#/components/schemas/{link_type.toTypeId}"}
                                }
                            }
                        }
                    }
                }
            }
            
            # Add/remove operations
            operations["post"] = {
                "summary": f"Add {link_type.displayName}",
                "operationId": f"add{object_type.name}{link_type.name}",
                "tags": [object_type.name],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "ids": {
                                        "type": "array",
                                        "items": {"type": "string", "format": "uuid"}
                                    }
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {"description": "Success"}
                }
            }
        else:
            # Single link
            operations["get"] = {
                "summary": f"Get {link_type.displayName} for {object_type.display_name}",
                "operationId": f"get{object_type.name}{link_type.name}",
                "tags": [object_type.name],
                "responses": {
                    "200": {
                        "description": "Success",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{link_type.toTypeId}"}
                            }
                        }
                    },
                    "404": {"description": "Not Found"}
                }
            }
        
        return operations
    
    def generate_complete_spec(
        self,
        object_types: List[ObjectType],
        link_types: List[LinkType],
        api_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate complete OpenAPI specification"""
        # Generate schemas for all types
        for obj_type in object_types:
            if obj_type.status == Status.ACTIVE:
                self.generate_object_schema(obj_type, link_types)
                self._generate_create_update_schemas(obj_type)
        
        # Add common parameters
        self.components["parameters"] = {
            "limit": {
                "name": "limit",
                "in": "query",
                "schema": {"type": "integer", "default": 20, "maximum": 100}
            },
            "offset": {
                "name": "offset",
                "in": "query",
                "schema": {"type": "integer", "default": 0}
            },
            "sort": {
                "name": "sort",
                "in": "query",
                "schema": {"type": "string"},
                "description": "Sort field and order (e.g., 'name' or '-created_at')"
            },
            "filter": {
                "name": "filter",
                "in": "query",
                "schema": {"type": "string"},
                "description": "Filter expression"
            },
            "expand": {
                "name": "expand",
                "in": "query",
                "schema": {"type": "string"},
                "description": "Comma-separated list of relationships to expand"
            }
        }
        
        # Generate paths
        paths = self.generate_paths(object_types, link_types)
        
        # Complete spec
        spec = {
            "openapi": "3.0.3",
            "info": api_info,
            "servers": [
                {"url": "/api/v1", "description": "API v1"}
            ],
            "paths": paths,
            "components": self.components
        }
        
        return spec
    
    def _generate_create_update_schemas(self, object_type: ObjectType):
        """Generate create and update schemas"""
        # Create schema (no ID, required fields)
        create_schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # Update schema (all optional)
        update_schema = {
            "type": "object",
            "properties": {}
        }
        
        for prop in object_type.properties:
            if not prop.is_primary_key:
                prop_schema = self._generate_property_schema(prop)
                create_schema["properties"][prop.name] = prop_schema
                update_schema["properties"][prop.name] = prop_schema
                
                if prop.is_required:
                    create_schema["required"].append(prop.name)
        
        self.components["schemas"][f"{object_type.name}Create"] = create_schema
        self.components["schemas"][f"{object_type.name}Update"] = update_schema


# Global instances
graphql_generator = GraphQLSchemaGenerator()
openapi_generator = OpenAPISchemaGenerator()