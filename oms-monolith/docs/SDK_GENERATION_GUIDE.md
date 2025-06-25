# SDK Generation Guide

## 개요

OMS(Ontology Management System)에서 AsyncAPI 2.6 스펙으로부터 TypeScript와 Python SDK를 자동 생성하는 도구가 구현되었습니다.

## 주요 기능

### ✅ 구현 완료
1. **AsyncAPI Schema Parser** - JSON Schema를 TypeScript/Python 타입으로 변환
2. **TypeScript SDK Generator** - 타입 안전한 클라이언트 생성
3. **Python SDK Generator** - Pydantic 모델 기반 클라이언트 생성
4. **Multi-Language Support** - 일괄 SDK 생성 지원
5. **Channel-based Methods** - AsyncAPI 채널별 publish/subscribe 메서드 자동 생성

## 아키텍처

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ AsyncAPI Spec   │───▶│   SDK Generator  │───▶│ TypeScript SDK  │
│ (JSON 2.6)      │    │   Orchestrator   │    │   + Types       │
└─────────────────┘    │                  │    └─────────────────┘
                       │   ┌──────────────┤    ┌─────────────────┐
                       │   │ Type Mapper  │───▶│   Python SDK    │
                       │   │ • TS Types   │    │ + Pydantic      │
                       │   │ • Pydantic   │    └─────────────────┘
                       └───┴──────────────┘
```

## 생성된 SDK 구조

### TypeScript SDK
```
sdks/typescript/
├── package.json          # NPM 패키지 설정
├── types.ts              # 모든 TypeScript 타입 정의
├── client.ts             # 타입 안전한 클라이언트
└── README.md             # 사용 가이드
```

### Python SDK
```
sdks/python/
├── setup.py              # Python 패키지 설정
├── requirements.txt      # 의존성 정의
├── README.md             # 사용 가이드
└── oms_event_sdk_py/     # 패키지 디렉토리
    ├── __init__.py       # 패키지 초기화
    ├── models.py         # Pydantic 모델들
    └── client.py         # 클라이언트 구현
```

## 사용법

### 1. SDK 생성

#### 단일 언어 생성
```python
from core.schema_generator.sdk_generator import TypeScriptSDKGenerator, PythonSDKGenerator, SDKConfig

# TypeScript SDK
config = SDKConfig(package_name="oms-event-sdk-ts", version="1.0.0")
ts_generator = TypeScriptSDKGenerator(config)
ts_path = ts_generator.generate_sdk(asyncapi_spec, "sdks")

# Python SDK  
py_generator = PythonSDKGenerator(config)
py_path = py_generator.generate_sdk(asyncapi_spec, "sdks")
```

#### 일괄 생성 (권장)
```python
from core.schema_generator.sdk_generator import generate_sdks_from_asyncapi

results = generate_sdks_from_asyncapi(
    asyncapi_spec_path="docs/oms-asyncapi.json",
    output_dir="sdks",
    languages=["typescript", "python"],
    package_name="oms-event-sdk"
)
```

### 2. 생성 테스트
```bash
# 전체 테스트 실행
python test_sdk_generation.py

# 단계별 확인:
# 1. AsyncAPI 스펙 생성
python test_asyncapi_generation.py

# 2. SDK 생성
python test_sdk_generation.py
```

## SDK 사용 예제

### TypeScript SDK

#### 설치 및 빌드
```bash
cd sdks/typescript
npm install
npm run build
```

#### 사용법
```typescript
import { OMSEventClient, ClientConfig } from 'oms-event-sdk-ts';

// 클라이언트 생성 (transport adapter 필요)
const client = await OMSEventClient.connect({
  natsUrl: 'nats://localhost:4222',
  websocketUrl: 'ws://localhost:8080'
});

// 이벤트 발행
await client.publishSchemacreated({
  specversion: '1.0',
  type: 'com.foundry.oms.schema.created',
  source: '/oms/main',
  id: crypto.randomUUID(),
  data: {
    operation: 'create',
    resource_type: 'schema',
    resource_id: 'example'
  }
});

// 정리
await client.close();
```

### Python SDK

#### 설치
```bash
cd sdks/python
pip install -e .
```

#### 사용법
```python
import asyncio
from oms_event_sdk_py import OMSEventClient, ClientConfig

async def main():
    # 클라이언트 생성 (transport adapter 필요)
    config = ClientConfig(
        nats_url="nats://localhost:4222",
        websocket_url="ws://localhost:8080"
    )
    
    client = await OMSEventClient.connect(config)
    
    # 이벤트 발행
    await client.publish_schemacreated({
        "specversion": "1.0",
        "type": "com.foundry.oms.schema.created",
        "source": "/oms/main",
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "data": {
            "operation": "create",
            "resource_type": "schema",
            "resource_id": "example"
        }
    })
    
    # 정리
    await client.close()

asyncio.run(main())
```

## 생성된 타입 시스템

### TypeScript Types
- **CloudEvent Interfaces**: 모든 OMS 이벤트 타입에 대한 강타입 인터페이스
- **Channel Parameters**: NATS subject 파라미터 타입 안전성
- **Publisher/Subscriber**: 추상화된 transport 인터페이스
- **Error Handling**: 타입 안전한 에러 처리

### Python Models
- **Pydantic Models**: 자동 검증 및 직렬화/역직렬화
- **Type Hints**: 완전한 타입 힌트 지원
- **Async Support**: 비동기 클라이언트 메서드
- **Enum Support**: 제약된 값에 대한 Enum 클래스

## 타입 매핑

### JSON Schema → TypeScript
| JSON Schema | TypeScript |
|-------------|------------|
| `string` | `string` |
| `integer` | `number` |
| `number` | `number` |
| `boolean` | `boolean` |
| `array` | `T[]` |
| `object` | `interface` |
| `enum` | `union type` |
| `date-time` | `Date` |

### JSON Schema → Python
| JSON Schema | Python |
|-------------|--------|
| `string` | `str` |
| `integer` | `int` |
| `number` | `float` |
| `boolean` | `bool` |
| `array` | `List[T]` |
| `object` | `BaseModel` |
| `enum` | `Enum` |
| `date-time` | `datetime` |

## Transport Adapters

생성된 SDK는 인터페이스를 제공하며, 실제 transport 구현이 필요합니다:

### TypeScript Adapters
- **NATS**: `nats.js` 라이브러리 사용
- **WebSocket**: `ws` 또는 네이티브 WebSocket API
- **HTTP**: `fetch` 또는 `axios`

### Python Adapters  
- **NATS**: `nats-py` 라이브러리 사용
- **WebSocket**: `websockets` 라이브러리
- **HTTP**: `httpx` 또는 `aiohttp`

## 확장성

### 새로운 언어 추가
1. `SDKGeneratorOrchestrator`에 새로운 언어 등록
2. 언어별 Generator 클래스 구현:
   - `_json_schema_to_[language]()` 메서드
   - `_generate_client_methods_from_channels()` 메서드
   - 패키지 파일 생성 메서드들

### 커스텀 타입 매핑
`_get_[language]_type()` 메서드를 확장하여 추가 타입 지원

## 성능 및 통계

### 생성 결과 (OMS AsyncAPI 기준)
- **TypeScript SDK**: 4개 파일, ~49KB
  - 64개 인터페이스 생성
  - 29개 publish 메서드
  - 타입 안전한 클라이언트
  
- **Python SDK**: 7개 파일, ~56KB  
  - 4개 Pydantic 모델
  - 29개 publish 메서드
  - 완전한 타입 힌트

### 지원하는 AsyncAPI 기능
- ✅ Channels & Operations
- ✅ Messages & Payloads  
- ✅ Schemas & Components
- ✅ Parameters
- ✅ Servers
- ❌ Bindings (planned)
- ❌ Security (planned)

## 다음 단계

1. **Transport Adapter 구현** - 실제 NATS/WebSocket 연결
2. **Binding Support** - 프로토콜별 바인딩 처리
3. **Code Generation Optimization** - 더 효율적인 타입 생성
4. **더 많은 언어 지원** - Go, Rust, Java 등
5. **IDE Integration** - VSCode extension 등

## 예제 및 테스트

완전한 예제 코드는 다음 파일들을 참조:
- `test_sdk_generation.py` - SDK 생성 테스트
- `sdks/typescript/README.md` - TypeScript 사용 가이드  
- `sdks/python/README.md` - Python 사용 가이드

이 SDK 생성 도구로 OMS는 타입 안전하고 자동 생성된 클라이언트 라이브러리를 통해 이벤트 기반 통합을 크게 단순화했습니다.