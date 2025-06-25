# Phase 2: TerminusDB 실제 연결 로드맵

## 2.1 TerminusDB 클라이언트 단순화 (2일)

### 현재 문제점
- 과도한 추상화 (connection pool, retry, mtls)
- 복잡한 의존성

### 해결 방안
```python
# database/terminus_client_v2.py
import terminusdb_client

class SimpleTerminusClient:
    def __init__(self, endpoint, user, password):
        self.client = terminusdb_client.Client(endpoint)
        self.client.connect(user=user, key=password)
    
    async def query(self, woql_query):
        # TerminusDB 내부 캐싱 활용
        return self.client.query(woql_query)
```

## 2.2 데이터 모델 매핑 (3일)

### WOQL 스키마 정의
```python
# schemas/terminus_schemas.py
def create_object_type_schema():
    return WOQL().doctype("ObjectType").property("name", "xsd:string")...
```

### Repository 패턴 구현
```python
# repositories/schema_repository.py
class SchemaRepository:
    def __init__(self, db_client):
        self.db = db_client
    
    async def save_object_type(self, obj_type: ObjectType):
        # Python 객체 → WOQL 변환
        query = WOQL().insert(obj_type.to_terminus())
        return await self.db.query(query)
```

## 2.3 마이그레이션 전략 (2일)

### Dual-Mode 운영
```python
class SchemaServiceV3:
    def __init__(self, repository=None):
        self.repo = repository or InMemoryRepository()
        self.mode = "db" if repository else "memory"
```

### 점진적 마이그레이션
1. 메모리 모드로 시작
2. TerminusDB 연결 시 자동 전환
3. 기존 데이터 마이그레이션 스크립트

## 예상 결과물
- TerminusDB 연결된 실제 서비스
- 데이터 영속성 보장
- 백업/복구 기능