"""
AsyncAPI Schema Generator
기존 GraphQL 스키마와 CloudEvents에서 AsyncAPI 2.6 스펙 자동 생성
"""
import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Union
from dataclasses import dataclass, asdict
from pathlib import Path

from ..event_publisher.cloudevents_enhanced import EventType, EnhancedCloudEvent
from ..validation.naming_convention import EntityType

logger = logging.getLogger(__name__)


@dataclass
class AsyncAPIChannel:
    """AsyncAPI Channel 정의"""
    description: str
    bindings: Optional[Dict[str, Any]] = None
    subscribe: Optional[Dict[str, Any]] = None
    publish: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None


@dataclass
class AsyncAPIMessage:
    """AsyncAPI Message 정의"""
    name: str
    title: str
    summary: str
    description: str
    contentType: str = "application/json"
    payload: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, Any]] = None
    correlationId: Optional[Dict[str, Any]] = None
    examples: Optional[List[Dict[str, Any]]] = None


@dataclass
class AsyncAPISchema:
    """AsyncAPI 스키마 정의"""
    type: str
    properties: Optional[Dict[str, Any]] = None
    required: Optional[List[str]] = None
    additionalProperties: bool = False
    examples: Optional[List[Any]] = None


class AsyncAPIGenerator:
    """AsyncAPI 2.6 스펙 생성기"""
    
    def __init__(self):
        self.channels: Dict[str, AsyncAPIChannel] = {}
        self.messages: Dict[str, AsyncAPIMessage] = {}
        self.schemas: Dict[str, AsyncAPISchema] = {}
        self.servers: Dict[str, Dict[str, Any]] = {}
        
    def generate_from_cloudevents(
        self,
        event_types: Optional[List[EventType]] = None,
        include_examples: bool = True
    ) -> Dict[str, Any]:
        """
        CloudEvents에서 AsyncAPI 스펙 생성
        
        Args:
            event_types: 포함할 이벤트 타입들 (None이면 모든 타입)
            include_examples: 예제 포함 여부
            
        Returns:
            AsyncAPI 2.6 스펙 딕셔너리
        """
        if event_types is None:
            event_types = list(EventType)
        
        # 서버 정의
        self._add_default_servers()
        
        # 각 이벤트 타입별 채널과 메시지 생성
        for event_type in event_types:
            self._process_event_type(event_type, include_examples)
        
        # 공통 스키마 생성
        self._add_common_schemas()
        
        # AsyncAPI 스펙 조립
        return self._build_asyncapi_spec()
    
    def generate_from_graphql_schema(
        self,
        graphql_schema_path: str,
        include_subscriptions: bool = True
    ) -> Dict[str, Any]:
        """
        GraphQL 스키마에서 AsyncAPI 스펙 생성
        
        Args:
            graphql_schema_path: GraphQL 스키마 파일 경로
            include_subscriptions: 구독 타입 포함 여부
            
        Returns:
            AsyncAPI 스펙 딕셔너리
        """
        # GraphQL 스키마 파싱
        graphql_types = self._parse_graphql_schema(graphql_schema_path)
        
        # 서버 정의
        self._add_default_servers()
        
        # GraphQL Subscription을 AsyncAPI로 변환
        if include_subscriptions:
            self._convert_graphql_subscriptions(graphql_types)
        
        # GraphQL Mutation을 Command 패턴으로 변환
        self._convert_graphql_mutations(graphql_types)
        
        return self._build_asyncapi_spec()
    
    def _add_default_servers(self):
        """기본 서버 설정 추가"""
        self.servers = {
            "nats-local": {
                "url": "nats://localhost:4222",
                "protocol": "nats",
                "description": "Local NATS Server",
                "bindings": {
                    "nats": {
                        "clientId": "oms-client"
                    }
                }
            },
            "nats-production": {
                "url": "nats://nats.oms.company.com:4222",
                "protocol": "nats", 
                "description": "Production NATS Cluster",
                "bindings": {
                    "nats": {
                        "clientId": "oms-client"
                    }
                }
            },
            "eventbridge": {
                "url": "https://events.{region}.amazonaws.com/",
                "protocol": "https",
                "description": "AWS EventBridge",
                "variables": {
                    "region": {
                        "description": "AWS Region",
                        "default": "us-east-1",
                        "enum": ["us-east-1", "us-west-2", "eu-west-1"]
                    }
                }
            }
        }
    
    def _process_event_type(self, event_type: EventType, include_examples: bool = True):
        """개별 이벤트 타입 처리"""
        
        # NATS Subject 생성
        nats_subject = self._get_nats_subject_pattern(event_type)
        
        # EventBridge 채널도 생성
        eventbridge_channel = self._get_eventbridge_channel_pattern(event_type)
        
        # 메시지 스키마 생성
        message_schema = self._create_message_schema(event_type)
        
        # 메시지 정의
        message = AsyncAPIMessage(
            name=self._event_type_to_message_name(event_type),
            title=self._event_type_to_title(event_type),
            summary=self._event_type_to_summary(event_type),
            description=self._event_type_to_description(event_type),
            payload=message_schema,
            headers=self._create_headers_schema(),
            correlationId={
                "description": "Correlation ID for event tracking",
                "location": "$message.header#/ce-correlationid"
            }
        )
        
        if include_examples:
            message.examples = [self._create_message_example(event_type)]
        
        self.messages[message.name] = message
        
        # NATS 채널 정의
        nats_channel = AsyncAPIChannel(
            description=f"NATS channel for {self._event_type_to_title(event_type)}",
            bindings={
                "nats": {
                    "subject": nats_subject
                }
            },
            publish={
                "operationId": f"publish{self._event_type_to_operation_name(event_type)}",
                "summary": f"Publish {self._event_type_to_title(event_type)}",
                "message": {"$ref": f"#/components/messages/{message.name}"}
            }
        )
        
        # Subject 파라미터 추가
        if "{" in nats_subject:
            nats_channel.parameters = self._extract_subject_parameters(nats_subject)
        
        self.channels[nats_subject] = nats_channel
        
        # EventBridge 채널 정의
        eventbridge_channel_def = AsyncAPIChannel(
            description=f"EventBridge channel for {self._event_type_to_title(event_type)}",
            bindings={
                "http": {
                    "type": "request",
                    "method": "POST",
                    "headers": {
                        "type": "object",
                        "properties": {
                            "X-Amz-Target": {
                                "type": "string",
                                "const": "AWSEvents.PutEvents"
                            }
                        }
                    }
                }
            },
            publish={
                "operationId": f"publishEventBridge{self._event_type_to_operation_name(event_type)}",
                "summary": f"Publish {self._event_type_to_title(event_type)} to EventBridge",
                "message": {"$ref": f"#/components/messages/{message.name}EventBridge"}
            }
        )
        
        # EventBridge용 별도 메시지 (변환된 형태)
        eventbridge_message = AsyncAPIMessage(
            name=f"{message.name}EventBridge",
            title=f"{message.title} (EventBridge Format)",
            summary=f"EventBridge formatted {message.summary}",
            description=f"EventBridge formatted version of {message.description}",
            payload=self._create_eventbridge_message_schema(event_type)
        )
        
        self.messages[eventbridge_message.name] = eventbridge_message
        self.channels[eventbridge_channel] = eventbridge_channel_def
    
    def _get_nats_subject_pattern(self, event_type: EventType) -> str:
        """EventType에서 NATS subject 패턴 생성"""
        type_parts = event_type.value.split('.')
        if len(type_parts) >= 4:
            # com.foundry.oms.objecttype.created -> oms.objecttype.created.{branch}.{resource}
            base_subject = '.'.join(type_parts[2:])
            
            # 리소스별 세분화
            if 'objecttype' in base_subject or 'property' in base_subject or 'linktype' in base_subject:
                return f"{base_subject}.{{branch}}.{{resourceId}}"
            elif 'branch' in base_subject:
                return f"{base_subject}.{{branchName}}"
            elif 'action' in base_subject:
                return f"{base_subject}.{{jobId}}"
            else:
                return f"{base_subject}.{{branch}}"
        
        return f"oms.{event_type.name.lower()}"
    
    def _get_eventbridge_channel_pattern(self, event_type: EventType) -> str:
        """EventType에서 EventBridge 채널 패턴 생성"""
        type_parts = event_type.value.split('.')
        if len(type_parts) >= 4:
            resource = type_parts[-2]
            action = type_parts[-1]
            return f"eventbridge/{resource}/{action}"
        return f"eventbridge/{event_type.name.lower()}"
    
    def _create_message_schema(self, event_type: EventType) -> Dict[str, Any]:
        """이벤트 타입별 메시지 스키마 생성"""
        
        # CloudEvents 기본 스키마
        base_schema = {
            "type": "object",
            "properties": {
                "specversion": {
                    "type": "string",
                    "const": "1.0",
                    "description": "CloudEvents specification version"
                },
                "type": {
                    "type": "string",
                    "const": event_type.value,
                    "description": "Event type identifier"
                },
                "source": {
                    "type": "string",
                    "pattern": "^/oms/.*",
                    "description": "Event source identifier"
                },
                "id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Unique event identifier"
                },
                "time": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Event timestamp"
                },
                "datacontenttype": {
                    "type": "string",
                    "const": "application/json"
                },
                "subject": {
                    "type": "string",
                    "description": "Subject of the event"
                },
                "data": {
                    "type": "object",
                    "description": "Event payload data"
                }
            },
            "required": ["specversion", "type", "source", "id", "data"],
            "additionalProperties": True
        }
        
        # 이벤트 타입별 data 스키마 특화
        data_schema = self._create_data_schema_for_event_type(event_type)
        if data_schema:
            base_schema["properties"]["data"] = data_schema
        
        # OMS 확장 속성들
        oms_extensions = {
            "ce_correlationid": {
                "type": "string",
                "description": "Correlation ID for event tracking"
            },
            "ce_causationid": {
                "type": "string", 
                "description": "Causation ID for event chain tracking"
            },
            "ce_branch": {
                "type": "string",
                "description": "Git branch context"
            },
            "ce_commit": {
                "type": "string",
                "description": "Git commit ID"
            },
            "ce_author": {
                "type": "string",
                "description": "Event author"
            },
            "ce_tenant": {
                "type": "string",
                "description": "Tenant identifier"
            }
        }
        
        base_schema["properties"].update(oms_extensions)
        
        return base_schema
    
    def _create_data_schema_for_event_type(self, event_type: EventType) -> Optional[Dict[str, Any]]:
        """이벤트 타입별 data 필드 스키마 생성"""
        
        type_str = event_type.value
        
        if 'objecttype' in type_str:
            return {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["create", "update", "delete"]},
                    "resource_type": {"type": "string", "const": "object_type"},
                    "resource_id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "old_value": {"type": "object"},
                    "new_value": {"type": "object"}
                },
                "required": ["operation", "resource_type", "resource_id"]
            }
        
        elif 'property' in type_str:
            return {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["create", "update", "delete"]},
                    "resource_type": {"type": "string", "const": "property"},
                    "resource_id": {"type": "string"},
                    "property_name": {"type": "string"},
                    "data_type": {"type": "string"},
                    "object_type_id": {"type": "string"},
                    "old_value": {"type": "object"},
                    "new_value": {"type": "object"}
                },
                "required": ["operation", "resource_type", "resource_id"]
            }
        
        elif 'branch' in type_str:
            return {
                "type": "object", 
                "properties": {
                    "operation": {"type": "string", "enum": ["created", "updated", "deleted", "merged"]},
                    "branch_name": {"type": "string"},
                    "author": {"type": "string"},
                    "target_branch": {"type": "string"},
                    "commit_id": {"type": "string"}
                },
                "required": ["operation", "branch_name", "author"]
            }
        
        elif 'action' in type_str:
            return {
                "type": "object",
                "properties": {
                    "action_type": {"type": "string"},
                    "job_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["started", "completed", "failed", "cancelled"]},
                    "progress": {"type": "number", "minimum": 0, "maximum": 1},
                    "result": {"type": "object"},
                    "error": {"type": "string"}
                },
                "required": ["action_type", "job_id", "status"]
            }
        
        elif 'system' in type_str:
            return {
                "type": "object",
                "properties": {
                    "component": {"type": "string"},
                    "status": {"type": "string"},
                    "details": {"type": "object"},
                    "timestamp": {"type": "string", "format": "date-time"}
                },
                "required": ["component", "status"]
            }
        
        # 기본 스키마
        return {
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
                "resource_type": {"type": "string"},
                "resource_id": {"type": "string"}
            },
            "additionalProperties": True
        }
    
    def _create_headers_schema(self) -> Dict[str, Any]:
        """CloudEvents Binary Content Mode 헤더 스키마"""
        return {
            "type": "object",
            "properties": {
                "ce-specversion": {"type": "string", "const": "1.0"},
                "ce-type": {"type": "string"},
                "ce-source": {"type": "string"},
                "ce-id": {"type": "string"},
                "ce-time": {"type": "string", "format": "date-time"},
                "ce-subject": {"type": "string"},
                "content-type": {"type": "string", "const": "application/json"},
                "ce-correlationid": {"type": "string"},
                "ce-branch": {"type": "string"},
                "ce-commit": {"type": "string"},
                "ce-author": {"type": "string"}
            },
            "required": ["ce-specversion", "ce-type", "ce-source", "ce-id"]
        }
    
    def _create_eventbridge_message_schema(self, event_type: EventType) -> Dict[str, Any]:
        """EventBridge 메시지 스키마 생성"""
        return {
            "type": "object",
            "properties": {
                "Source": {
                    "type": "string",
                    "pattern": "^oms\\..*",
                    "description": "EventBridge source"
                },
                "DetailType": {
                    "type": "string",
                    "description": "Human-readable event type"
                },
                "Detail": {
                    "type": "object",
                    "properties": {
                        "cloudEvents": {
                            "$ref": f"#/components/schemas/CloudEvent{self._event_type_to_schema_name(event_type)}"
                        },
                        "omsExtensions": {
                            "type": "object",
                            "description": "OMS-specific extensions"
                        },
                        "eventBridgeMetadata": {
                            "type": "object",
                            "description": "EventBridge conversion metadata"
                        }
                    },
                    "required": ["cloudEvents"]
                },
                "EventBusName": {
                    "type": "string",
                    "description": "EventBridge bus name"
                },
                "Time": {
                    "type": "string",
                    "format": "date-time"
                },
                "Resources": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["Source", "DetailType", "Detail"]
        }
    
    def _create_message_example(self, event_type: EventType) -> Dict[str, Any]:
        """이벤트 타입별 메시지 예제 생성"""
        
        base_example = {
            "name": f"Example {self._event_type_to_title(event_type)}",
            "summary": f"Example of {event_type.value}",
            "payload": {
                "specversion": "1.0",
                "type": event_type.value,
                "source": "/oms/main",
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "time": "2024-01-01T12:00:00Z",
                "datacontenttype": "application/json",
                "subject": self._get_example_subject(event_type),
                "data": self._get_example_data(event_type),
                "ce_correlationid": "corr-123",
                "ce_branch": "main",
                "ce_commit": "abc123",
                "ce_author": "developer@company.com"
            }
        }
        
        return base_example
    
    def _get_example_subject(self, event_type: EventType) -> str:
        """이벤트 타입별 예제 subject"""
        type_str = event_type.value
        
        if 'objecttype' in type_str:
            return "object_type/User"
        elif 'property' in type_str:
            return "property/name"
        elif 'linktype' in type_str:
            return "link_type/userToProduct"
        elif 'branch' in type_str:
            return "branch/feature-xyz"
        elif 'action' in type_str:
            return "action/validate-123"
        else:
            return "resource/example"
    
    def _get_example_data(self, event_type: EventType) -> Dict[str, Any]:
        """이벤트 타입별 예제 data"""
        type_str = event_type.value
        
        if 'objecttype' in type_str and 'created' in type_str:
            return {
                "operation": "create",
                "resource_type": "object_type",
                "resource_id": "User",
                "name": "User",
                "description": "User entity type",
                "new_value": {
                    "name": "User",
                    "description": "User entity type",
                    "properties": ["id", "name", "email"]
                }
            }
        elif 'branch' in type_str and 'created' in type_str:
            return {
                "operation": "created",
                "branch_name": "feature-xyz",
                "author": "developer@company.com",
                "commit_id": "abc123"
            }
        elif 'action' in type_str and 'started' in type_str:
            return {
                "action_type": "validation",
                "job_id": "validate-123",
                "status": "started",
                "progress": 0.0
            }
        else:
            return {
                "operation": "update",
                "resource_type": "unknown",
                "resource_id": "example"
            }
    
    def _extract_subject_parameters(self, subject: str) -> Dict[str, Any]:
        """NATS subject에서 파라미터 추출"""
        parameters = {}
        
        # {branch}, {resourceId} 등의 패턴 찾기
        import re
        param_pattern = r'\{(\w+)\}'
        params = re.findall(param_pattern, subject)
        
        for param in params:
            param_schema = {
                "description": f"Dynamic parameter: {param}",
                "schema": {"type": "string"}
            }
            
            # 파라미터별 특화
            if param == "branch":
                param_schema["description"] = "Git branch name"
                param_schema["schema"]["pattern"] = "^[a-zA-Z0-9_/-]+$"
                param_schema["examples"] = ["main", "feature/new-feature", "dev"]
            elif param == "resourceId":
                param_schema["description"] = "Resource identifier"
                param_schema["examples"] = ["User", "Product", "Order"]
            elif param == "jobId":
                param_schema["description"] = "Job identifier"
                param_schema["schema"]["format"] = "uuid"
            
            parameters[param] = param_schema
        
        return parameters
    
    def _add_common_schemas(self):
        """공통 스키마 추가"""
        
        # CloudEvents 기본 스키마
        self.schemas["CloudEvent"] = AsyncAPISchema(
            type="object",
            properties={
                "specversion": {"type": "string"},
                "type": {"type": "string"},
                "source": {"type": "string"},
                "id": {"type": "string"},
                "time": {"type": "string", "format": "date-time"},
                "datacontenttype": {"type": "string"},
                "subject": {"type": "string"},
                "data": {"type": "object"}
            },
            required=["specversion", "type", "source", "id"]
        )
        
        # OMS Context 스키마
        self.schemas["OMSContext"] = AsyncAPISchema(
            type="object",
            properties={
                "branch": {"type": "string"},
                "commit": {"type": "string"},
                "author": {"type": "string"},
                "tenant": {"type": "string"},
                "correlationId": {"type": "string"},
                "causationId": {"type": "string"}
            }
        )
        
        # EntityType 스키마
        entity_types = [et.value for et in EntityType]
        self.schemas["EntityType"] = AsyncAPISchema(
            type="string",
            examples=entity_types
        )
    
    def _parse_graphql_schema(self, schema_path: str) -> Dict[str, Any]:
        """GraphQL 스키마 파싱 (간단한 구현)"""
        # 실제로는 graphql-core 라이브러리 사용 권장
        # 여기서는 기본 구현만 제공
        
        try:
            with open(schema_path, 'r') as f:
                content = f.read()
            
            # 간단한 정규식 파싱 (실제로는 더 정교한 파서 필요)
            types = {}
            
            # Subscription 타입 추출
            subscription_match = re.search(r'type Subscription \{([^}]+)\}', content, re.DOTALL)
            if subscription_match:
                types['Subscription'] = subscription_match.group(1)
            
            # Mutation 타입 추출  
            mutation_match = re.search(r'type Mutation \{([^}]+)\}', content, re.DOTALL)
            if mutation_match:
                types['Mutation'] = mutation_match.group(1)
            
            return types
            
        except Exception as e:
            logger.error(f"Failed to parse GraphQL schema: {e}")
            return {}
    
    def _convert_graphql_subscriptions(self, graphql_types: Dict[str, Any]):
        """GraphQL Subscription을 AsyncAPI로 변환"""
        if 'Subscription' not in graphql_types:
            return
        
        subscription_content = graphql_types['Subscription']
        
        # 간단한 필드 추출 (실제로는 더 정교한 파싱 필요)
        fields = re.findall(r'(\w+):\s*(\w+)', subscription_content)
        
        for field_name, return_type in fields:
            channel_name = f"graphql/subscription/{field_name}"
            
            channel = AsyncAPIChannel(
                description=f"GraphQL Subscription: {field_name}",
                subscribe={
                    "operationId": f"subscribe{field_name.title()}",
                    "summary": f"Subscribe to {field_name} updates",
                    "message": {
                        "payload": {
                            "type": "object",
                            "properties": {
                                "data": {
                                    "type": "object",
                                    "properties": {
                                        field_name: {"$ref": f"#/components/schemas/{return_type}"}
                                    }
                                }
                            }
                        }
                    }
                }
            )
            
            self.channels[channel_name] = channel
    
    def _convert_graphql_mutations(self, graphql_types: Dict[str, Any]):
        """GraphQL Mutation을 Command 패턴으로 변환"""
        if 'Mutation' not in graphql_types:
            return
        
        mutation_content = graphql_types['Mutation']
        fields = re.findall(r'(\w+)\([^)]*\):\s*(\w+)', mutation_content)
        
        for field_name, return_type in fields:
            channel_name = f"commands/{field_name}"
            
            channel = AsyncAPIChannel(
                description=f"Command: {field_name}",
                publish={
                    "operationId": f"execute{field_name.title()}",
                    "summary": f"Execute {field_name} command",
                    "message": {
                        "payload": {
                            "type": "object",
                            "properties": {
                                "command": {"type": "string", "const": field_name},
                                "args": {"type": "object"},
                                "metadata": {"$ref": "#/components/schemas/OMSContext"}
                            }
                        }
                    }
                }
            )
            
            self.channels[channel_name] = channel
    
    def _build_asyncapi_spec(self) -> Dict[str, Any]:
        """최종 AsyncAPI 스펙 조립"""
        
        spec = {
            "asyncapi": "2.6.0",
            "info": {
                "title": "OMS Event API",
                "version": "1.0.0",
                "description": "Ontology Management System Event-Driven API",
                "contact": {
                    "name": "OMS Team",
                    "email": "oms-team@company.com"
                },
                "license": {
                    "name": "MIT"
                }
            },
            "servers": self.servers,
            "channels": {name: asdict(channel) for name, channel in self.channels.items()},
            "components": {
                "messages": {name: asdict(message) for name, message in self.messages.items()},
                "schemas": {name: asdict(schema) for name, schema in self.schemas.items()}
            },
            "tags": [
                {"name": "schema", "description": "Schema management events"},
                {"name": "branch", "description": "Branch management events"},
                {"name": "action", "description": "Action execution events"},
                {"name": "system", "description": "System monitoring events"}
            ]
        }
        
        return spec
    
    # Helper 메서드들
    def _event_type_to_message_name(self, event_type: EventType) -> str:
        """EventType을 메시지 이름으로 변환"""
        return event_type.name.replace('_', '').title()
    
    def _event_type_to_title(self, event_type: EventType) -> str:
        """EventType을 제목으로 변환"""
        return event_type.name.replace('_', ' ').title()
    
    def _event_type_to_summary(self, event_type: EventType) -> str:
        """EventType을 요약으로 변환"""
        return f"Event: {self._event_type_to_title(event_type)}"
    
    def _event_type_to_description(self, event_type: EventType) -> str:
        """EventType을 설명으로 변환"""
        type_parts = event_type.value.split('.')
        if len(type_parts) >= 4:
            resource = type_parts[-2].replace('_', ' ')
            action = type_parts[-1]
            return f"Notification when {resource} is {action} in the OMS system"
        return f"OMS event: {event_type.value}"
    
    def _event_type_to_operation_name(self, event_type: EventType) -> str:
        """EventType을 operation 이름으로 변환"""
        return event_type.name.replace('_', '').title()
    
    def _event_type_to_schema_name(self, event_type: EventType) -> str:
        """EventType을 스키마 이름으로 변환"""
        return self._event_type_to_message_name(event_type)
    
    def save_to_file(self, spec: Dict[str, Any], file_path: str):
        """AsyncAPI 스펙을 파일로 저장"""
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w') as f:
            json.dump(spec, f, indent=2, default=str)
        
        logger.info(f"AsyncAPI spec saved to {file_path}")


# 편의 함수들
def generate_oms_asyncapi_spec(
    output_file: str = "docs/asyncapi.json",
    include_examples: bool = True,
    include_eventbridge: bool = True
) -> Dict[str, Any]:
    """OMS AsyncAPI 스펙 생성 및 저장"""
    
    generator = AsyncAPIGenerator()
    
    # CloudEvents에서 스펙 생성
    spec = generator.generate_from_cloudevents(include_examples=include_examples)
    
    # 파일 저장
    generator.save_to_file(spec, output_file)
    
    return spec


def generate_from_graphql(
    graphql_schema_path: str,
    output_file: str = "docs/asyncapi-graphql.json"
) -> Dict[str, Any]:
    """GraphQL 스키마에서 AsyncAPI 생성"""
    
    generator = AsyncAPIGenerator()
    spec = generator.generate_from_graphql_schema(graphql_schema_path)
    generator.save_to_file(spec, output_file)
    
    return spec