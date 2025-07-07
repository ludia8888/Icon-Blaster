"""
SDK Generator from AsyncAPI Specification
AsyncAPI 스펙에서 TypeScript/Python SDK 자동 생성
"""
import json
import re
import logging
from typing import Dict, Any, List, Optional, Set, Union
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SDKConfig:
    """SDK 생성 설정"""
    package_name: str
    version: str = "1.0.0"
    author: str = "OMS Team"
    description: str = "Auto-generated SDK for OMS Event API"
    license: str = "MIT"
    
    # Language specific
    typescript_target: str = "ES2020"
    python_min_version: str = "3.8"


class TypeScriptSDKGenerator:
    """TypeScript SDK 생성기"""
    
    def __init__(self, config: SDKConfig):
        self.config = config
        self.types: Dict[str, str] = {}
        self.interfaces: Dict[str, str] = {}
        self.client_methods: List[str] = []
        
    def generate_sdk(self, asyncapi_spec: Dict[str, Any], output_dir: str) -> str:
        """TypeScript SDK 생성"""
        
        output_path = Path(output_dir) / "typescript"
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 스키마에서 TypeScript 타입 생성
        self._generate_types_from_schemas(asyncapi_spec.get("components", {}).get("schemas", {}))
        
        # 메시지에서 인터페이스 생성
        self._generate_interfaces_from_messages(asyncapi_spec.get("components", {}).get("messages", {}))
        
        # 채널에서 클라이언트 메서드 생성
        self._generate_client_methods_from_channels(asyncapi_spec.get("channels", {}))
        
        # 파일 생성
        self._generate_types_file(output_path)
        self._generate_client_file(output_path, asyncapi_spec)
        self._generate_package_json(output_path)
        self._generate_readme(output_path)
        
        logger.info(f"TypeScript SDK generated at {output_path}")
        return str(output_path)
    
    def _generate_types_from_schemas(self, schemas: Dict[str, Any]):
        """스키마에서 TypeScript 타입 생성"""
        
        for schema_name, schema in schemas.items():
            if isinstance(schema, dict):
                ts_type = self._json_schema_to_typescript(schema, schema_name)
                self.types[schema_name] = ts_type
    
    def _json_schema_to_typescript(self, schema: Dict[str, Any], type_name: str) -> str:
        """JSON Schema를 TypeScript 타입으로 변환"""
        
        if schema.get("type") == "object":
            properties = schema.get("properties", {})
            required = schema.get("required", []) or []
            
            # 인터페이스 생성
            lines = [f"export interface {type_name} {{"]
            
            for prop_name, prop_schema in properties.items():
                prop_type = self._get_typescript_type(prop_schema)
                optional = "" if prop_name in required else "?"
                description = prop_schema.get("description", "")
                
                if description:
                    lines.append(f"  /** {description} */")
                
                lines.append(f"  {prop_name}{optional}: {prop_type};")
            
            lines.append("}")
            return "\n".join(lines)
        
        elif schema.get("type") == "array":
            item_type = self._get_typescript_type(schema.get("items", {}))
            return f"export type {type_name} = {item_type}[];"
        
        elif schema.get("type") == "string" and schema.get("enum"):
            enum_values = schema.get("enum", [])
            enum_entries = " | ".join([f'"{value}"' for value in enum_values])
            return f"export type {type_name} = {enum_entries};"
        
        else:
            base_type = self._get_typescript_type(schema)
            return f"export type {type_name} = {base_type};"
    
    def _get_typescript_type(self, schema: Dict[str, Any]) -> str:
        """JSON Schema 타입을 TypeScript 타입으로 매핑"""
        
        schema_type = schema.get("type", "any")
        
        if schema_type == "string":
            if schema.get("format") == "date-time":
                return "Date"
            elif schema.get("format") == "uuid":
                return "string"
            elif schema.get("enum"):
                enum_values = " | ".join([f'"{v}"' for v in schema.get("enum", [])])
                return enum_values
            else:
                return "string"
        
        elif schema_type == "number" or schema_type == "integer":
            return "number"
        
        elif schema_type == "boolean":
            return "boolean"
        
        elif schema_type == "array":
            item_type = self._get_typescript_type(schema.get("items", {}))
            return f"{item_type}[]"
        
        elif schema_type == "object":
            if schema.get("additionalProperties") is True:
                return "Record<string, any>"
            else:
                # 중첩 객체는 별도 인터페이스로 처리 필요
                return "object"
        
        elif "$ref" in schema:
            ref_path = schema["$ref"]
            # #/components/schemas/SchemaName -> SchemaName
            ref_name = ref_path.split("/")[-1]
            return ref_name
        
        else:
            return "any"
    
    def _generate_interfaces_from_messages(self, messages: Dict[str, Any]):
        """메시지에서 TypeScript 인터페이스 생성"""
        
        for message_name, message in messages.items():
            if isinstance(message, dict):
                payload = message.get("payload", {})
                if payload:
                    interface_name = f"{message_name}Payload"
                    ts_interface = self._json_schema_to_typescript(payload, interface_name)
                    self.interfaces[interface_name] = ts_interface
    
    def _generate_client_methods_from_channels(self, channels: Dict[str, Any]):
        """채널에서 클라이언트 메서드 생성"""
        
        for channel_name, channel in channels.items():
            if isinstance(channel, dict):
                
                # Publish 메서드
                if "publish" in channel:
                    publish_op = channel["publish"]
                    method_name = self._sanitize_method_name(publish_op.get("operationId", f"publish_{channel_name}"))
                    
                    message_ref = publish_op.get("message", {}).get("$ref", "")
                    message_type = message_ref.split("/")[-1] if message_ref else "any"
                    payload_type = f"{message_type}Payload" if message_type != "any" else "any"
                    
                    method = f"""
  /**
   * {publish_op.get('summary', f'Publish to {channel_name}')}
   * Channel: {channel_name}
   */
  async {method_name}(payload: {payload_type}): Promise<PublishResult> {{
    return this.publisher.publish('{channel_name}', payload);
  }}"""
                    self.client_methods.append(method)
                
                # Subscribe 메서드
                if "subscribe" in channel and channel["subscribe"] is not None:
                    subscribe_op = channel["subscribe"]
                    method_name = self._sanitize_method_name(subscribe_op.get("operationId", f"subscribe_{channel_name}"))
                    
                    message_ref = subscribe_op.get("message", {}).get("$ref", "")
                    message_type = message_ref.split("/")[-1] if message_ref else "any"
                    payload_type = f"{message_type}Payload" if message_type != "any" else "any"
                    
                    method = f"""
  /**
   * {subscribe_op.get('summary', f'Subscribe to {channel_name}')}
   * Channel: {channel_name}
   */
  {method_name}(handler: (payload: {payload_type}) => void | Promise<void>): Promise<Subscription> {{
    return this.subscriber.subscribe('{channel_name}', handler);
  }}"""
                    self.client_methods.append(method)
    
    def _sanitize_method_name(self, name: str) -> str:
        """메서드 이름 정규화"""
        # camelCase로 변환
        name = re.sub(r'[^a-zA-Z0-9]', '_', name)
        parts = name.split('_')
        return parts[0].lower() + ''.join(word.capitalize() for word in parts[1:])
    
    def _generate_types_file(self, output_path: Path):
        """types.ts 파일 생성"""
        
        content = f'''/**
 * Auto-generated TypeScript types for {self.config.package_name}
 * Generated at: {datetime.now().isoformat()}
 * DO NOT EDIT - This file is auto-generated
 */

// Common types
export interface PublishResult {{
  success: boolean;
  messageId?: string;
  error?: string;
}}

export interface Subscription {{
  unsubscribe(): Promise<void>;
}}

export interface EventPublisher {{
  publish(channel: string, payload: any): Promise<PublishResult>;
}}

export interface EventSubscriber {{
  subscribe(channel: string, handler: (payload: any) => void | Promise<void>): Promise<Subscription>;
}}

// Generated Types
{chr(10).join(self.types.values())}

// Message Interfaces
{chr(10).join(self.interfaces.values())}
'''
        
        with open(output_path / "types.ts", "w") as f:
            f.write(content)
    
    def _generate_client_file(self, output_path: Path, asyncapi_spec: Dict[str, Any]):
        """client.ts 파일 생성"""
        
        servers = asyncapi_spec.get("servers", {})
        default_urls = {}
        
        for server_name, server_config in servers.items():
            protocol = server_config.get("protocol", "")
            url = server_config.get("url", "")
            default_urls[protocol] = url
        
        content = f'''/**
 * Auto-generated TypeScript client for {self.config.package_name}
 * Generated at: {datetime.now().isoformat()}
 * DO NOT EDIT - This file is auto-generated
 */

import {{ EventPublisher, EventSubscriber, PublishResult, Subscription }} from './types';

export interface ClientConfig {{
  natsUrl?: string;
  websocketUrl?: string;
  httpUrl?: string;
  credentials?: {{
    username?: string;
    password?: string;
    token?: string;
  }};
}}

export class OMSEventClient {{
  private publisher: EventPublisher;
  private subscriber: EventSubscriber;
  
  constructor(
    publisher: EventPublisher,
    subscriber: EventSubscriber
  ) {{
    this.publisher = publisher;
    this.subscriber = subscriber;
  }}
  
  static async connect(config: ClientConfig = {{}}): Promise<OMSEventClient> {{
    // Factory method to create client with appropriate adapters
    const natsUrl = config.natsUrl || '{default_urls.get("nats", "nats://localhost:4222")}';
    const wsUrl = config.websocketUrl || '{default_urls.get("ws", "ws://localhost:8080")}';
    
    // Implementation would depend on the actual transport libraries
    // This is a placeholder for the interface
    throw new Error('Please implement transport-specific adapters');
  }}

  // Generated client methods
{chr(10).join(self.client_methods)}
  
  /**
   * Close all connections and cleanup resources
   */
  async close(): Promise<void> {{
    // Implementation depends on transport
  }}
}}

// Export everything
export * from './types';
'''
        
        with open(output_path / "client.ts", "w") as f:
            f.write(content)
    
    def _generate_package_json(self, output_path: Path):
        """package.json 생성"""
        
        package_json = {
            "name": self.config.package_name,
            "version": self.config.version,
            "description": self.config.description,
            "main": "dist/index.js",
            "types": "dist/index.d.ts",
            "scripts": {
                "build": "tsc",
                "test": "jest",
                "lint": "eslint src/**/*.ts",
                "prepare": "npm run build"
            },
            "keywords": ["oms", "events", "asyncapi", "typescript"],
            "author": self.config.author,
            "license": self.config.license,
            "devDependencies": {
                "typescript": "^5.0.0",
                "@types/node": "^18.0.0",
                "jest": "^29.0.0",
                "@types/jest": "^29.0.0",
                "ts-jest": "^29.0.0",
                "eslint": "^8.0.0",
                "@typescript-eslint/eslint-plugin": "^6.0.0",
                "@typescript-eslint/parser": "^6.0.0"
            },
            "peerDependencies": {
                "@types/ws": "^8.0.0"
            },
            "files": ["dist/**/*"],
            "repository": {
                "type": "git",
                "url": "https://github.com/company/oms-event-sdk-ts.git"
            }
        }
        
        with open(output_path / "package.json", "w") as f:
            json.dump(package_json, f, indent=2)
    
    def _generate_readme(self, output_path: Path):
        """README.md 생성"""
        
        content = f'''# {self.config.package_name}

{self.config.description}

## Installation

```bash
npm install {self.config.package_name}
```

## Usage

```typescript
import {{ OMSEventClient }} from '{self.config.package_name}';

// Create client (implementation depends on transport)
const client = await OMSEventClient.connect({{
  natsUrl: 'nats://localhost:4222',
  websocketUrl: 'ws://localhost:8080'
}});

// Subscribe to events
await client.subscribeObjecttypecreated((event) => {{
  console.log('Object type created:', event);
}});

// Publish events
await client.publishSchemacreated({{
  specversion: '1.0',
  type: 'com.foundry.oms.schema.created',
  source: '/oms/main',
  id: crypto.randomUUID(),
  data: {{
    operation: 'create',
    resource_type: 'schema',
    resource_id: 'example'
  }}
}});

// Cleanup
await client.close();
```

## Transport Adapters

This SDK provides interfaces but requires transport-specific adapters:

- **NATS**: Use with `nats.js` library
- **WebSocket**: Use with native WebSocket or `ws` library  
- **HTTP**: Use with `fetch` or `axios`

## Generated Types

All event types and schemas are automatically generated from the AsyncAPI specification.

## License

{self.config.license}
'''
        
        with open(output_path / "README.md", "w") as f:
            f.write(content)


class PythonSDKGenerator:
    """Python SDK 생성기"""
    
    def __init__(self, config: SDKConfig):
        self.config = config
        self.models: Dict[str, str] = {}
        self.client_methods: List[str] = []
        
    def generate_sdk(self, asyncapi_spec: Dict[str, Any], output_dir: str) -> str:
        """Python SDK 생성"""
        
        output_path = Path(output_dir) / "python"
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 패키지 구조 생성
        package_path = output_path / self.config.package_name.replace("-", "_")
        package_path.mkdir(exist_ok=True)
        
        # 스키마에서 Pydantic 모델 생성
        self._generate_models_from_schemas(asyncapi_spec.get("components", {}).get("schemas", {}))
        
        # 채널에서 클라이언트 메서드 생성
        self._generate_client_methods_from_channels(asyncapi_spec.get("channels", {}))
        
        # 파일 생성
        self._generate_models_file(package_path)
        self._generate_client_file(package_path, asyncapi_spec)
        self._generate_init_file(package_path)
        self._generate_setup_py(output_path)
        self._generate_requirements_txt(output_path)
        self._generate_readme(output_path)
        
        logger.info(f"Python SDK generated at {output_path}")
        return str(output_path)
    
    def _generate_models_from_schemas(self, schemas: Dict[str, Any]):
        """스키마에서 Pydantic 모델 생성"""
        
        for schema_name, schema in schemas.items():
            if isinstance(schema, dict):
                model = self._json_schema_to_pydantic(schema, schema_name)
                self.models[schema_name] = model
    
    def _json_schema_to_pydantic(self, schema: Dict[str, Any], model_name: str) -> str:
        """JSON Schema를 Pydantic 모델로 변환"""
        
        if schema.get("type") == "object":
            properties = schema.get("properties", {})
            required = schema.get("required", []) or []
            
            lines = [
                f"class {model_name}(BaseModel):",
                f'    """Generated model for {model_name}"""'
            ]
            
            for prop_name, prop_schema in properties.items():
                prop_type = self._get_python_type(prop_schema)
                default = "..." if prop_name in required else "None"
                description = prop_schema.get("description", "")
                
                if description:
                    lines.append(f'    # {description}')
                
                if prop_name in required:
                    lines.append(f"    {prop_name}: {prop_type}")
                else:
                    lines.append(f"    {prop_name}: Optional[{prop_type}] = {default}")
            
            return "\n".join(lines)
        
        elif schema.get("type") == "string" and schema.get("enum"):
            enum_values = schema.get("enum", [])
            lines = [
                f"class {model_name}(str, Enum):",
                f'    """Generated enum for {model_name}"""'
            ]
            
            for value in enum_values:
                enum_name = value.upper().replace("-", "_").replace(".", "_")
                lines.append(f'    {enum_name} = "{value}"')
            
            return "\n".join(lines)
        
        else:
            # 간단한 타입 별칭
            python_type = self._get_python_type(schema)
            return f"{model_name} = {python_type}"
    
    def _get_python_type(self, schema: Dict[str, Any]) -> str:
        """JSON Schema 타입을 Python 타입으로 매핑"""
        
        schema_type = schema.get("type", "Any")
        
        if schema_type == "string":
            if schema.get("format") == "date-time":
                return "datetime"
            elif schema.get("format") == "uuid":
                return "str"
            elif schema.get("enum"):
                return "str"  # 별도 Enum 클래스로 처리
            else:
                return "str"
        
        elif schema_type == "number":
            return "float"
        
        elif schema_type == "integer":
            return "int"
        
        elif schema_type == "boolean":
            return "bool"
        
        elif schema_type == "array":
            item_type = self._get_python_type(schema.get("items", {}))
            return f"List[{item_type}]"
        
        elif schema_type == "object":
            if schema.get("additionalProperties") is True:
                return "Dict[str, Any]"
            else:
                return "Dict[str, Any]"
        
        elif "$ref" in schema:
            ref_path = schema["$ref"]
            ref_name = ref_path.split("/")[-1]
            return ref_name
        
        else:
            return "Any"
    
    def _generate_client_methods_from_channels(self, channels: Dict[str, Any]):
        """채널에서 클라이언트 메서드 생성"""
        
        for channel_name, channel in channels.items():
            if isinstance(channel, dict):
                
                # Publish 메서드
                if "publish" in channel:
                    publish_op = channel["publish"]
                    method_name = self._sanitize_method_name(publish_op.get("operationId", f"publish_{channel_name}"))
                    
                    message_ref = publish_op.get("message", {}).get("$ref", "")
                    message_type = message_ref.split("/")[-1] if message_ref else "Dict[str, Any]"
                    
                    method = f'''
    async def {method_name}(self, payload: {message_type}) -> PublishResult:
        """
        {publish_op.get('summary', f'Publish to {channel_name}')}
        
        Args:
            payload: Message payload
            
        Returns:
            PublishResult with success status
        """
        return await self.publisher.publish("{channel_name}", payload)'''
                    
                    self.client_methods.append(method)
                
                # Subscribe 메서드
                if "subscribe" in channel and channel["subscribe"] is not None:
                    subscribe_op = channel["subscribe"]
                    method_name = self._sanitize_method_name(subscribe_op.get("operationId", f"subscribe_{channel_name}"))
                    
                    message_ref = subscribe_op.get("message", {}).get("$ref", "")
                    message_type = message_ref.split("/")[-1] if message_ref else "Dict[str, Any]"
                    
                    method = f'''
    async def {method_name}(self, handler: Callable[[{message_type}], Awaitable[None]]) -> Subscription:
        """
        {subscribe_op.get('summary', f'Subscribe to {channel_name}')}
        
        Args:
            handler: Async function to handle incoming messages
            
        Returns:
            Subscription object
        """
        return await self.subscriber.subscribe("{channel_name}", handler)'''
                    
                    self.client_methods.append(method)
    
    def _sanitize_method_name(self, name: str) -> str:
        """메서드 이름 정규화 (snake_case)"""
        name = re.sub(r'[^a-zA-Z0-9]', '_', name)
        return name.lower()
    
    def _generate_models_file(self, package_path: Path):
        """models.py 파일 생성"""
        
        content = f'''"""
Auto-generated Pydantic models for {self.config.package_name}
Generated at: {datetime.now().isoformat()}
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
{chr(10).join(self.models.values())}
'''
        
        with open(package_path / "models.py", "w") as f:
            f.write(content)
    
    def _generate_client_file(self, package_path: Path, asyncapi_spec: Dict[str, Any]):
        """client.py 파일 생성"""
        
        servers = asyncapi_spec.get("servers", {})
        default_urls = {}
        
        for server_name, server_config in servers.items():
            protocol = server_config.get("protocol", "")
            url = server_config.get("url", "")
            default_urls[protocol] = url
        
        content = f'''"""
Auto-generated Python client for {self.config.package_name}
Generated at: {datetime.now().isoformat()}
DO NOT EDIT - This file is auto-generated
"""

from typing import Optional, Dict, Any, Callable, Awaitable
from dataclasses import dataclass
from .models import *


@dataclass
class ClientConfig:
    """Client configuration"""
    nats_url: Optional[str] = None
    websocket_url: Optional[str] = None
    http_url: Optional[str] = None
    credentials: Optional[Dict[str, str]] = None


class EventPublisher:
    """Abstract event publisher interface"""
    
    async def publish(self, channel: str, payload: Any) -> PublishResult:
        raise NotImplementedError


class EventSubscriber:
    """Abstract event subscriber interface"""
    
    async def subscribe(self, channel: str, handler: Callable[[Any], Awaitable[None]]) -> Subscription:
        raise NotImplementedError


class OMSEventClient:
    """
    Auto-generated OMS Event API client
    
    This client provides typed methods for all AsyncAPI operations.
    """
    
    def __init__(self, publisher: EventPublisher, subscriber: EventSubscriber):
        self.publisher = publisher
        self.subscriber = subscriber
    
    @classmethod
    async def connect(cls, config: ClientConfig = None) -> 'OMSEventClient':
        """
        Create client with appropriate adapters
        
        Args:
            config: Client configuration
            
        Returns:
            Connected client instance
        """
        if config is None:
            config = ClientConfig()
        
        # Default URLs from AsyncAPI spec
        nats_url = config.nats_url or '{default_urls.get("nats", "nats://localhost:4222")}'
        ws_url = config.websocket_url or '{default_urls.get("ws", "ws://localhost:8080")}'
        
        # Implementation would depend on the actual transport libraries
        # This is a placeholder for the interface
        raise NotImplementedError("Please implement transport-specific adapters")

    # Generated client methods
{chr(10).join(self.client_methods)}
    
    async def close(self) -> None:
        """Close all connections and cleanup resources"""
        # Implementation depends on transport
        pass
'''
        
        with open(package_path / "client.py", "w") as f:
            f.write(content)
    
    def _generate_init_file(self, package_path: Path):
        """__init__.py 파일 생성"""
        
        content = f'''"""
{self.config.package_name} - {self.config.description}
"""

__version__ = "{self.config.version}"
__author__ = "{self.config.author}"

from .client import OMSEventClient, ClientConfig, EventPublisher, EventSubscriber
from .models import *

__all__ = [
    "OMSEventClient",
    "ClientConfig", 
    "EventPublisher",
    "EventSubscriber",
    "PublishResult",
    "Subscription"
]
'''
        
        with open(package_path / "__init__.py", "w") as f:
            f.write(content)
    
    def _generate_setup_py(self, output_path: Path):
        """setup.py 생성"""
        
        package_name_underscore = self.config.package_name.replace("-", "_")
        
        content = f'''"""
Setup script for {self.config.package_name}
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="{self.config.package_name}",
    version="{self.config.version}",
    author="{self.config.author}",
    description="{self.config.description}",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/company/oms-event-sdk-py",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">={self.config.python_min_version}",
    install_requires=requirements,
    keywords=["oms", "events", "asyncapi", "python"],
    project_urls={{
        "Bug Reports": "https://github.com/company/oms-event-sdk-py/issues",
        "Source": "https://github.com/company/oms-event-sdk-py",
    }},
)
'''
        
        with open(output_path / "setup.py", "w") as f:
            f.write(content)
    
    def _generate_requirements_txt(self, output_path: Path):
        """requirements.txt 생성"""
        
        content = '''# Core dependencies
pydantic>=2.0.0
typing-extensions>=4.0.0

# Optional transport dependencies
# Uncomment as needed:
# nats-py>=2.3.0  # For NATS transport
# websockets>=11.0.0  # For WebSocket transport
# httpx>=0.24.0  # For HTTP transport
# aiohttp>=3.8.0  # Alternative HTTP client

# Development dependencies (install with: pip install -e .[dev])
pytest>=7.0.0
pytest-asyncio>=0.21.0
black>=23.0.0
isort>=5.12.0
mypy>=1.0.0
'''
        
        with open(output_path / "requirements.txt", "w") as f:
            f.write(content)
    
    def _generate_readme(self, output_path: Path):
        """README.md 생성"""
        
        content = f'''# {self.config.package_name}

{self.config.description}

## Installation

```bash
pip install {self.config.package_name}
```

## Usage

```python
import asyncio
from {self.config.package_name.replace("-", "_")} import OMSEventClient, ClientConfig

async def main():
    # Create client (implementation depends on transport)
    config = ClientConfig(
        nats_url="nats://localhost:4222",
        websocket_url="ws://localhost:8080"
    )
    
    client = await OMSEventClient.connect(config)
    
    # Subscribe to events
    async def handle_objecttype_created(event):
        print(f"Object type created: {{event}}")
    
    await client.subscribe_objecttypecreated(handle_objecttype_created)
    
    # Publish events
    await client.publish_schemacreated({{
        "specversion": "1.0",
        "type": "com.foundry.oms.schema.created",
        "source": "/oms/main",
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "data": {{
            "operation": "create",
            "resource_type": "schema",
            "resource_id": "example"
        }}
    }})
    
    # Cleanup
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## Transport Adapters

This SDK provides interfaces but requires transport-specific adapters:

- **NATS**: Use with `nats-py` library
- **WebSocket**: Use with `websockets` library
- **HTTP**: Use with `httpx` or `aiohttp`

## Generated Models

All event types and schemas are automatically generated from the AsyncAPI specification using Pydantic models.

## Development

```bash
# Install in development mode
pip install -e .[dev]

# Run tests
pytest

# Format code
black .
isort .

# Type checking
mypy .
```

## License

{self.config.license}
'''
        
        with open(output_path / "README.md", "w") as f:
            f.write(content)


class SDKGeneratorOrchestrator:
    """SDK 생성 오케스트레이터"""
    
    def __init__(self):
        self.generators = {
            "typescript": TypeScriptSDKGenerator,
            "python": PythonSDKGenerator
        }
    
    def generate_all_sdks(
        self,
        asyncapi_spec_path: str,
        output_dir: str,
        languages: List[str] = None,
        config: SDKConfig = None
    ) -> Dict[str, str]:
        """모든 언어의 SDK 생성"""
        
        if languages is None:
            languages = ["typescript", "python"]
        
        if config is None:
            config = SDKConfig(package_name="oms-event-sdk")
        
        # AsyncAPI 스펙 로드
        with open(asyncapi_spec_path, 'r') as f:
            asyncapi_spec = json.load(f)
        
        results = {}
        
        for language in languages:
            if language in self.generators:
                logger.info(f"Generating {language} SDK...")
                
                generator_class = self.generators[language]
                generator = generator_class(config)
                
                output_path = generator.generate_sdk(asyncapi_spec, output_dir)
                results[language] = output_path
                
                logger.info(f"{language} SDK generated successfully at {output_path}")
            else:
                logger.warning(f"Unsupported language: {language}")
        
        return results


# 편의 함수
def generate_sdks_from_asyncapi(
    asyncapi_spec_path: str,
    output_dir: str = "sdks",
    languages: List[str] = None,
    package_name: str = "oms-event-sdk"
) -> Dict[str, str]:
    """AsyncAPI 스펙에서 SDK 생성"""
    
    config = SDKConfig(package_name=package_name)
    orchestrator = SDKGeneratorOrchestrator()
    
    return orchestrator.generate_all_sdks(
        asyncapi_spec_path=asyncapi_spec_path,
        output_dir=output_dir,
        languages=languages,
        config=config
    )