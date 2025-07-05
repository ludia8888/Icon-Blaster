"""
GraphQL to AsyncAPI Converter
기존 GraphQL 스키마를 AsyncAPI 이벤트 스키마로 변환
"""
import re
import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GraphQLField:
    """GraphQL 필드 정의"""
    name: str
    type: str
    args: Dict[str, str]
    description: Optional[str] = None
    is_list: bool = False
    is_non_null: bool = False


@dataclass
class GraphQLType:
    """GraphQL 타입 정의"""
    name: str
    kind: str  # OBJECT, INPUT, ENUM, SCALAR, etc.
    fields: List[GraphQLField]
    description: Optional[str] = None
    enum_values: Optional[List[str]] = None


class GraphQLSchemaParser:
    """GraphQL 스키마 파서"""
    
    def __init__(self):
        self.types: Dict[str, GraphQLType] = {}
        self.subscriptions: List[GraphQLField] = []
        self.mutations: List[GraphQLField] = []
        self.queries: List[GraphQLField] = []
    
    def parse_schema_file(self, file_path: str) -> Dict[str, Any]:
        """GraphQL 스키마 파일 파싱"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return self.parse_schema_content(content)
            
        except Exception as e:
            logger.error(f"Failed to parse GraphQL schema file {file_path}: {e}")
            return {}
    
    def parse_schema_content(self, content: str) -> Dict[str, Any]:
        """GraphQL 스키마 내용 파싱"""
        
        # 주석 제거
        content = self._remove_comments(content)
        
        # 타입 정의들 추출
        self._extract_types(content)
        
        # Query, Mutation, Subscription 추출
        self._extract_root_types(content)
        
        return {
            'types': self.types,
            'subscriptions': self.subscriptions,
            'mutations': self.mutations,
            'queries': self.queries
        }
    
    def _remove_comments(self, content: str) -> str:
        """GraphQL 주석 제거"""
        # # 로 시작하는 주석 제거
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # # 주석 제거 (문자열 내부는 보존)
            in_string = False
            quote_char = None
            result = []
            
            i = 0
            while i < len(line):
                char = line[i]
                
                if not in_string and char == '#':
                    # 주석 시작, 라인 끝까지 무시
                    break
                elif not in_string and char in ['"', "'"]:
                    in_string = True
                    quote_char = char
                    result.append(char)
                elif in_string and char == quote_char:
                    if i > 0 and line[i-1] != '\\':  # 이스케이프되지 않은 경우
                        in_string = False
                        quote_char = None
                    result.append(char)
                else:
                    result.append(char)
                
                i += 1
            
            cleaned_line = ''.join(result).rstrip()
            if cleaned_line:  # 빈 라인 제거
                cleaned_lines.append(cleaned_line)
        
        return '\n'.join(cleaned_lines)
    
    def _extract_types(self, content: str):
        """모든 타입 정의 추출"""
        
        # type, input, enum, scalar 패턴들
        type_patterns = [
            (r'type\s+(\w+)\s*\{([^}]+)\}', 'OBJECT'),
            (r'input\s+(\w+)\s*\{([^}]+)\}', 'INPUT'),
            (r'enum\s+(\w+)\s*\{([^}]+)\}', 'ENUM'),
            (r'scalar\s+(\w+)', 'SCALAR'),
            (r'interface\s+(\w+)\s*\{([^}]+)\}', 'INTERFACE'),
            (r'union\s+(\w+)\s*=\s*([^\\n]+)', 'UNION')
        ]
        
        for pattern, kind in type_patterns:
            matches = re.finditer(pattern, content, re.DOTALL | re.MULTILINE)
            
            for match in matches:
                type_name = match.group(1)
                
                if kind == 'SCALAR':
                    # Scalar은 필드가 없음
                    self.types[type_name] = GraphQLType(
                        name=type_name,
                        kind=kind,
                        fields=[]
                    )
                elif kind == 'ENUM':
                    # Enum 값들 추출
                    enum_content = match.group(2)
                    enum_values = self._extract_enum_values(enum_content)
                    
                    self.types[type_name] = GraphQLType(
                        name=type_name,
                        kind=kind,
                        fields=[],
                        enum_values=enum_values
                    )
                elif kind == 'UNION':
                    # Union 타입들 추출
                    union_content = match.group(2)
                    union_types = [t.strip() for t in union_content.split('|')]
                    
                    self.types[type_name] = GraphQLType(
                        name=type_name,
                        kind=kind,
                        fields=[],
                        description=f"Union of: {', '.join(union_types)}"
                    )
                else:
                    # Object, Input, Interface
                    fields_content = match.group(2)
                    fields = self._extract_fields(fields_content)
                    
                    self.types[type_name] = GraphQLType(
                        name=type_name,
                        kind=kind,
                        fields=fields
                    )
    
    def _extract_enum_values(self, enum_content: str) -> List[str]:
        """Enum 값들 추출"""
        values = []
        lines = enum_content.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # 간단한 enum 값 추출 (더 정교한 파싱 필요할 수 있음)
                value = line.split()[0]
                values.append(value)
        
        return values
    
    def _extract_fields(self, fields_content: str) -> List[GraphQLField]:
        """타입의 필드들 추출"""
        fields = []
        
        # 필드 패턴: fieldName(args): Type
        field_pattern = r'(\w+)(\([^)]*\))?\s*:\s*([^\\n,]+)'
        
        matches = re.finditer(field_pattern, fields_content, re.MULTILINE)
        
        for match in matches:
            field_name = match.group(1)
            args_str = match.group(2) or ""
            type_str = match.group(3).strip()
            
            # 타입 정보 파싱
            is_list = '[' in type_str and ']' in type_str
            is_non_null = type_str.endswith('!')
            
            # ! 와 [] 제거하여 기본 타입 추출
            clean_type = type_str.replace('!', '').replace('[', '').replace(']', '').strip()
            
            # 인자들 파싱
            args = self._parse_args(args_str)
            
            field = GraphQLField(
                name=field_name,
                type=clean_type,
                args=args,
                is_list=is_list,
                is_non_null=is_non_null
            )
            
            fields.append(field)
        
        return fields
    
    def _parse_args(self, args_str: str) -> Dict[str, str]:
        """필드 인자들 파싱"""
        args = {}
        
        if not args_str or args_str == "()":
            return args
        
        # 괄호 제거
        args_content = args_str.strip('()')
        
        # 간단한 인자 파싱: argName: Type
        arg_pattern = r'(\w+)\s*:\s*([^,]+)'
        matches = re.finditer(arg_pattern, args_content)
        
        for match in matches:
            arg_name = match.group(1)
            arg_type = match.group(2).strip()
            args[arg_name] = arg_type
        
        return args
    
    def _extract_root_types(self, content: str):
        """Query, Mutation, Subscription 타입 추출"""
        
        # Query 타입
        query_match = re.search(r'type\s+Query\s*\{([^}]+)\}', content, re.DOTALL)
        if query_match:
            self.queries = self._extract_fields(query_match.group(1))
        
        # Mutation 타입
        mutation_match = re.search(r'type\s+Mutation\s*\{([^}]+)\}', content, re.DOTALL)
        if mutation_match:
            self.mutations = self._extract_fields(mutation_match.group(1))
        
        # Subscription 타입
        subscription_match = re.search(r'type\s+Subscription\s*\{([^}]+)\}', content, re.DOTALL)
        if subscription_match:
            self.subscriptions = self._extract_fields(subscription_match.group(1))


class GraphQLToAsyncAPIConverter:
    """GraphQL 스키마를 AsyncAPI로 변환"""
    
    def __init__(self, parser: GraphQLSchemaParser):
        self.parser = parser
        self.channels: Dict[str, Any] = {}
        self.messages: Dict[str, Any] = {}
        self.schemas: Dict[str, Any] = {}
    
    def convert_to_asyncapi(self) -> Dict[str, Any]:
        """GraphQL 스키마를 AsyncAPI로 변환"""
        
        # GraphQL 타입들을 JSON Schema로 변환
        self._convert_types_to_schemas()
        
        # Subscription을 AsyncAPI Subscribe로 변환
        self._convert_subscriptions_to_channels()
        
        # Mutation을 Command 패턴으로 변환
        self._convert_mutations_to_commands()
        
        # Query를 Request-Reply 패턴으로 변환 (선택적)
        self._convert_queries_to_request_reply()
        
        return self._build_asyncapi_spec()
    
    def _convert_types_to_schemas(self):
        """GraphQL 타입들을 JSON Schema로 변환"""
        
        for type_name, graphql_type in self.parser.types.items():
            
            if graphql_type.kind == 'OBJECT' or graphql_type.kind == 'INPUT':
                schema = {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False
                }
                
                required_fields = []
                
                for field in graphql_type.fields:
                    prop_schema = self._graphql_type_to_json_schema(field.type, field.is_list)
                    
                    if field.description:
                        prop_schema["description"] = field.description
                    
                    schema["properties"][field.name] = prop_schema
                    
                    if field.is_non_null:
                        required_fields.append(field.name)
                
                if required_fields:
                    schema["required"] = required_fields
                
                if graphql_type.description:
                    schema["description"] = graphql_type.description
                
                self.schemas[type_name] = schema
            
            elif graphql_type.kind == 'ENUM':
                schema = {
                    "type": "string",
                    "enum": graphql_type.enum_values or []
                }
                
                if graphql_type.description:
                    schema["description"] = graphql_type.description
                
                self.schemas[type_name] = schema
            
            elif graphql_type.kind == 'SCALAR':
                # 기본 스칼라 타입들
                scalar_mappings = {
                    'String': {"type": "string"},
                    'Int': {"type": "integer"},
                    'Float': {"type": "number"},
                    'Boolean': {"type": "boolean"},
                    'ID': {"type": "string"},
                    'DateTime': {"type": "string", "format": "date-time"},
                    'Date': {"type": "string", "format": "date"},
                    'JSON': {"type": "object", "additionalProperties": True}
                }
                
                self.schemas[type_name] = scalar_mappings.get(type_name, {"type": "string"})
    
    def _graphql_type_to_json_schema(self, graphql_type: str, is_list: bool = False) -> Dict[str, Any]:
        """GraphQL 타입을 JSON Schema로 변환"""
        
        # 기본 타입 매핑
        type_mappings = {
            'String': {"type": "string"},
            'Int': {"type": "integer"},
            'Float': {"type": "number"},
            'Boolean': {"type": "boolean"},
            'ID': {"type": "string"},
            'DateTime': {"type": "string", "format": "date-time"},
            'Date': {"type": "string", "format": "date"}
        }
        
        if graphql_type in type_mappings:
            base_schema = type_mappings[graphql_type]
        else:
            # 사용자 정의 타입 참조
            base_schema = {"$ref": f"#/components/schemas/{graphql_type}"}
        
        if is_list:
            return {
                "type": "array",
                "items": base_schema
            }
        
        return base_schema
    
    def _convert_subscriptions_to_channels(self):
        """GraphQL Subscription을 AsyncAPI Subscribe로 변환"""
        
        for subscription in self.parser.subscriptions:
            channel_name = f"subscription/{subscription.name}"
            
            # 메시지 스키마 생성
            message_schema = {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "properties": {
                            subscription.name: self._graphql_type_to_json_schema(subscription.type, subscription.is_list)
                        }
                    },
                    "errors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string"},
                                "path": {"type": "array", "items": {"type": "string"}},
                                "extensions": {"type": "object"}
                            }
                        }
                    }
                }
            }
            
            # 메시지 정의
            message_name = f"{subscription.name}SubscriptionMessage"
            self.messages[message_name] = {
                "name": message_name,
                "title": f"{subscription.name.title()} Subscription",
                "summary": f"Real-time updates for {subscription.name}",
                "contentType": "application/json",
                "payload": message_schema
            }
            
            # 채널 정의
            self.channels[channel_name] = {
                "description": f"Real-time subscription for {subscription.name}",
                "subscribe": {
                    "operationId": f"subscribe{subscription.name.title()}",
                    "summary": f"Subscribe to {subscription.name} updates",
                    "description": f"Receive real-time updates when {subscription.name} data changes",
                    "message": {"$ref": f"#/components/messages/{message_name}"}
                },
                "bindings": {
                    "ws": {
                        "method": "POST",
                        "headers": {
                            "type": "object",
                            "properties": {
                                "Connection-Id": {
                                    "type": "string",
                                    "description": "WebSocket connection identifier"
                                }
                            }
                        }
                    }
                }
            }
            
            # 인자가 있는 경우 파라미터 추가
            if subscription.args:
                parameters = {}
                for arg_name, arg_type in subscription.args.items():
                    parameters[arg_name] = {
                        "description": f"Subscription parameter: {arg_name}",
                        "schema": self._graphql_type_to_json_schema(arg_type)
                    }
                
                self.channels[channel_name]["parameters"] = parameters
    
    def _convert_mutations_to_commands(self):
        """GraphQL Mutation을 Command 패턴으로 변환"""
        
        for mutation in self.parser.mutations:
            channel_name = f"commands/{mutation.name}"
            
            # Command 메시지 스키마
            command_schema = {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "const": mutation.name,
                        "description": "Command name"
                    },
                    "arguments": {
                        "type": "object",
                        "properties": {},
                        "description": "Command arguments"
                    },
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "correlationId": {"type": "string"},
                            "userId": {"type": "string"},
                            "timestamp": {"type": "string", "format": "date-time"}
                        },
                        "description": "Command metadata"
                    }
                },
                "required": ["command"]
            }
            
            # 인자들을 arguments 스키마에 추가
            for arg_name, arg_type in mutation.args.items():
                command_schema["properties"]["arguments"]["properties"][arg_name] = \
                    self._graphql_type_to_json_schema(arg_type)
            
            # Response 메시지 스키마
            response_schema = {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "data": self._graphql_type_to_json_schema(mutation.type, mutation.is_list),
                    "errors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string"},
                                "code": {"type": "string"}
                            }
                        }
                    },
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "correlationId": {"type": "string"},
                            "timestamp": {"type": "string", "format": "date-time"}
                        }
                    }
                }
            }
            
            # Command 메시지
            command_message_name = f"{mutation.name}Command"
            self.messages[command_message_name] = {
                "name": command_message_name,
                "title": f"{mutation.name.title()} Command",
                "summary": f"Execute {mutation.name} command",
                "contentType": "application/json",
                "payload": command_schema
            }
            
            # Response 메시지
            response_message_name = f"{mutation.name}Response"
            self.messages[response_message_name] = {
                "name": response_message_name,
                "title": f"{mutation.name.title()} Response",
                "summary": f"Response for {mutation.name} command",
                "contentType": "application/json",
                "payload": response_schema
            }
            
            # 채널 정의 (Command)
            self.channels[channel_name] = {
                "description": f"Execute {mutation.name} command",
                "publish": {
                    "operationId": f"execute{mutation.name.title()}",
                    "summary": f"Execute {mutation.name} command",
                    "message": {"$ref": f"#/components/messages/{command_message_name}"}
                }
            }
            
            # Response 채널
            response_channel_name = f"responses/{mutation.name}"
            self.channels[response_channel_name] = {
                "description": f"Response for {mutation.name} command",
                "subscribe": {
                    "operationId": f"receive{mutation.name.title()}Response",
                    "summary": f"Receive {mutation.name} command response",
                    "message": {"$ref": f"#/components/messages/{response_message_name}"}
                }
            }
    
    def _convert_queries_to_request_reply(self):
        """GraphQL Query를 Request-Reply 패턴으로 변환 (선택적)"""
        
        # Query는 일반적으로 동기적이므로 AsyncAPI에서는 선택적
        # 필요한 경우에만 Request-Reply 패턴으로 변환
        
        for query in self.parser.queries:
            if self._should_convert_query_to_async(query):
                channel_name = f"queries/{query.name}"
                
                # Request 메시지
                request_schema = {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "const": query.name},
                        "arguments": {"type": "object"},
                        "metadata": {
                            "type": "object",
                            "properties": {
                                "correlationId": {"type": "string"},
                                "replyTo": {"type": "string"}
                            }
                        }
                    }
                }
                
                # Response 메시지
                response_schema = {
                    "type": "object",
                    "properties": {
                        "data": self._graphql_type_to_json_schema(query.type, query.is_list),
                        "errors": {"type": "array"},
                        "metadata": {"type": "object"}
                    }
                }
                
                request_message_name = f"{query.name}Request"
                response_message_name = f"{query.name}Response"
                
                self.messages[request_message_name] = {
                    "name": request_message_name,
                    "title": f"{query.name.title()} Request",
                    "payload": request_schema
                }
                
                self.messages[response_message_name] = {
                    "name": response_message_name,
                    "title": f"{query.name.title()} Response",
                    "payload": response_schema
                }
                
                self.channels[channel_name] = {
                    "description": f"Request-Reply for {query.name} query",
                    "publish": {
                        "operationId": f"request{query.name.title()}",
                        "message": {"$ref": f"#/components/messages/{request_message_name}"}
                    },
                    "subscribe": {
                        "operationId": f"receive{query.name.title()}Response",
                        "message": {"$ref": f"#/components/messages/{response_message_name}"}
                    }
                }
    
    def _should_convert_query_to_async(self, query: GraphQLField) -> bool:
        """Query를 비동기 패턴으로 변환할지 결정"""
        
        # 대용량 데이터 조회나 시간이 오래 걸리는 작업은 비동기로
        long_running_queries = [
            'exportData',
            'generateReport',
            'searchLarge',
            'aggregateData'
        ]
        
        return query.name in long_running_queries
    
    def _build_asyncapi_spec(self) -> Dict[str, Any]:
        """AsyncAPI 스펙 조립"""
        
        return {
            "asyncapi": "2.6.0",
            "info": {
                "title": "OMS GraphQL Event API",
                "version": "1.0.0",
                "description": "AsyncAPI generated from GraphQL schema"
            },
            "servers": {
                "websocket": {
                    "url": "ws://localhost:8080/graphql-ws",
                    "protocol": "ws",
                    "description": "GraphQL WebSocket subscriptions"
                },
                "nats": {
                    "url": "nats://localhost:4222",
                    "protocol": "nats",
                    "description": "NATS for commands and queries"
                }
            },
            "channels": self.channels,
            "components": {
                "messages": self.messages,
                "schemas": self.schemas
            }
        }


# 편의 함수
def convert_graphql_to_asyncapi(
    graphql_schema_path: str,
    output_path: str = "docs/asyncapi-from-graphql.json"
) -> Dict[str, Any]:
    """GraphQL 스키마를 AsyncAPI로 변환"""
    
    # GraphQL 스키마 파싱
    parser = GraphQLSchemaParser()
    parsed_data = parser.parse_schema_file(graphql_schema_path)
    
    if not parsed_data:
        raise ValueError(f"Failed to parse GraphQL schema: {graphql_schema_path}")
    
    # AsyncAPI로 변환
    converter = GraphQLToAsyncAPIConverter(parser)
    asyncapi_spec = converter.convert_to_asyncapi()
    
    # 파일 저장
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    import json
    with open(output_path, 'w') as f:
        json.dump(asyncapi_spec, f, indent=2)
    
    logger.info(f"Converted GraphQL schema to AsyncAPI: {output_path}")
    
    return asyncapi_spec