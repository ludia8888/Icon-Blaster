# Production Deployment Checklist

## 🚀 프로덕션 배포 전 필수 체크리스트

### 1. ✅ EventBridge IAM 정책

#### 최소 권한 정책 검증
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "events:PutEvents"
      ],
      "Resource": "arn:aws:events:*:*:event-bus/oms-events",
      "Condition": {
        "StringEquals": {
          "events:source": "oms"
        }
      }
    }
  ]
}
```

#### DLQ 역할 권한
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl"
      ],
      "Resource": "arn:aws:sqs:*:*:oms-events-dlq"
    }
  ]
}
```

#### 검증 스크립트
```bash
# infrastructure/aws/verify_iam_policies.py
python infrastructure/aws/verify_iam_policies.py --check-least-privilege
```

### 2. ✅ DLQ & 재시도 설정

#### EventBridge 설정
```python
# infrastructure/aws/eventbridge_rules.py
retry_policy = {
    "MaximumRetryAttempts": 3,
    "MaximumEventAge": 3600  # 1 hour
}

dlq_config = {
    "Arn": "arn:aws:sqs:region:account:oms-events-dlq"
}
```

#### NATS JetStream 설정
```python
# core/event_publisher/nats_config.py
stream_config = {
    "max_deliver": 3,  # EventBridge MaximumRetryAttempts와 일치
    "ack_wait": 30,    # seconds
    "max_age": 3600    # EventBridge MaximumEventAge와 일치
}
```

#### 설정 동기화 확인
```bash
python scripts/verify_retry_configs.py --compare-platforms
```

### 3. ✅ 역방향 호환성 (B/C)

#### 이벤트 버전 관리
```python
# core/event_publisher/schema_versioning.py
class VersionedCloudEvent(EnhancedCloudEvent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # data.version 필드 추가
        if 'data' in kwargs:
            kwargs['data']['version'] = kwargs['data'].get('version', '1.0.0')
```

#### SDK Deprecation 마킹
```typescript
// sdks/typescript/types.ts
export interface SchemaCreatedV1 {
  /** @deprecated Use SchemaCreatedV2 instead */
  operation: string;
  resource_type: string;
}

export interface SchemaCreatedV2 {
  operation: string;
  resource_type: string;
  version: string;  // 새 필드
}
```

```python
# sdks/python/oms_event_sdk_py/models.py
from typing import Literal
import warnings

class SchemaCreatedV1(BaseModel):
    """@deprecated: Use SchemaCreatedV2 instead"""
    operation: str
    resource_type: str
    
    def __init__(self, **data):
        warnings.warn("SchemaCreatedV1 is deprecated. Use SchemaCreatedV2", 
                     DeprecationWarning, stacklevel=2)
        super().__init__(**data)
```

### 4. ✅ SDK NPM/PyPI 배포

#### NPM 배포 체크리스트
```bash
# 1. 패키지 이름 충돌 확인
npm search oms-event-sdk

# 2. 버전 확인 및 업데이트
npm version patch  # or minor/major

# 3. 빌드 및 테스트
npm run build
npm test

# 4. Dry run
npm publish --dry-run

# 5. 실제 배포
npm publish --access public

# 6. 태그 관리
npm dist-tag add oms-event-sdk@1.0.0 stable
```

#### PyPI 배포 체크리스트
```bash
# 1. 패키지 이름 충돌 확인
pip search oms-event-sdk  # deprecated, use:
curl https://pypi.org/pypi/oms-event-sdk/json

# 2. 빌드
python setup.py sdist bdist_wheel

# 3. 테스트 PyPI 업로드
twine upload --repository testpypi dist/*

# 4. 테스트 설치
pip install --index-url https://test.pypi.org/simple/ oms-event-sdk

# 5. 프로덕션 배포
twine upload dist/*

# 6. 확인
pip install oms-event-sdk
```

### 5. ✅ Observability

#### EventBridge CloudWatch 알람
```python
# infrastructure/aws/cloudwatch_alarms.py
failed_invocation_alarm = {
    "AlarmName": "oms-eventbridge-failed-invocations",
    "MetricName": "FailedInvocations",
    "Namespace": "AWS/Events",
    "Statistic": "Sum",
    "Period": 300,
    "EvaluationPeriods": 1,
    "Threshold": 5,
    "ComparisonOperator": "GreaterThanThreshold",
    "AlarmActions": ["arn:aws:sns:region:account:oms-alerts"]
}
```

#### NATS Consumer Lag 대시보드
```python
# monitoring/nats_dashboard.py
consumer_lag_metric = {
    "MetricName": "ConsumerLag",
    "Dimensions": [
        {"Name": "Stream", "Value": "OMS_EVENTS"},
        {"Name": "Consumer", "Value": "oms-processor"}
    ],
    "Unit": "Count"
}
```

#### SDK OpenTelemetry 통합
```typescript
// sdks/typescript/client.ts
import { trace, context, SpanStatusCode } from '@opentelemetry/api';

export class OMSEventClient {
  async publishWithTracing(channel: string, payload: any): Promise<PublishResult> {
    const tracer = trace.getTracer('oms-event-sdk', '1.0.0');
    
    return tracer.startActiveSpan(`publish:${channel}`, async (span) => {
      try {
        // traceparent 헤더 추가
        const traceparent = span.spanContext().traceId;
        payload.ce_traceparent = traceparent;
        
        const result = await this.publisher.publish(channel, payload);
        span.setStatus({ code: SpanStatusCode.OK });
        return result;
      } catch (error) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: error.message });
        throw error;
      } finally {
        span.end();
      }
    });
  }
}
```

```python
# sdks/python/oms_event_sdk_py/client.py
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

class OMSEventClient:
    async def publish_with_tracing(self, channel: str, payload: dict) -> PublishResult:
        tracer = trace.get_tracer("oms-event-sdk", "1.0.0")
        
        with tracer.start_as_current_span(f"publish:{channel}") as span:
            try:
                # traceparent 헤더 추가
                ctx = span.get_span_context()
                payload["ce_traceparent"] = f"{ctx.trace_id:032x}"
                
                result = await self.publisher.publish(channel, payload)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise
```

### 6. ✅ 보안 & PII

#### PII 감지 및 암호화
```python
# core/security/pii_handler.py
import re
from cryptography.fernet import Fernet

class PIIHandler:
    """PII 감지 및 처리"""
    
    PII_PATTERNS = {
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
        'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        'credit_card': r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'
    }
    
    def __init__(self, encryption_key: bytes):
        self.cipher = Fernet(encryption_key)
    
    def detect_pii(self, data: dict) -> List[str]:
        """데이터에서 PII 감지"""
        pii_fields = []
        
        def check_value(key: str, value: Any, path: str = ""):
            current_path = f"{path}.{key}" if path else key
            
            if isinstance(value, str):
                for pii_type, pattern in self.PII_PATTERNS.items():
                    if re.search(pattern, value):
                        pii_fields.append((current_path, pii_type))
            elif isinstance(value, dict):
                for k, v in value.items():
                    check_value(k, v, current_path)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    check_value(f"[{i}]", item, current_path)
        
        for key, value in data.items():
            check_value(key, value)
        
        return pii_fields
    
    def anonymize_pii(self, data: dict) -> dict:
        """PII 익명화"""
        import copy
        anonymized = copy.deepcopy(data)
        
        def anonymize_value(obj: Any, path: List[str]):
            if len(path) == 1:
                if path[0] in obj:
                    # 이메일은 도메인 유지
                    if '@' in str(obj[path[0]]):
                        obj[path[0]] = f"user_{hash(obj[path[0]])%10000}@{obj[path[0]].split('@')[1]}"
                    else:
                        obj[path[0]] = f"REDACTED_{hash(obj[path[0]])%10000}"
            else:
                if path[0] in obj:
                    anonymize_value(obj[path[0]], path[1:])
        
        pii_fields = self.detect_pii(data)
        for field_path, _ in pii_fields:
            path_parts = field_path.split('.')
            anonymize_value(anonymized, path_parts)
        
        return anonymized
    
    def encrypt_pii(self, data: dict) -> dict:
        """PII 암호화"""
        import copy
        encrypted = copy.deepcopy(data)
        
        def encrypt_value(obj: Any, path: List[str]):
            if len(path) == 1:
                if path[0] in obj and isinstance(obj[path[0]], str):
                    obj[path[0]] = self.cipher.encrypt(obj[path[0]].encode()).decode()
            else:
                if path[0] in obj:
                    encrypt_value(obj[path[0]], path[1:])
        
        pii_fields = self.detect_pii(data)
        for field_path, _ in pii_fields:
            path_parts = field_path.split('.')
            encrypt_value(encrypted, path_parts)
        
        return encrypted
```

#### 이벤트 발행 전 PII 검사
```python
# core/event_publisher/secure_publisher.py
class SecureEventPublisher:
    def __init__(self, publisher: EventPublisher, pii_handler: PIIHandler):
        self.publisher = publisher
        self.pii_handler = pii_handler
    
    async def publish_event(self, event: EnhancedCloudEvent) -> None:
        # PII 검사
        pii_fields = self.pii_handler.detect_pii(event.data)
        
        if pii_fields:
            logger.warning(f"PII detected in event: {pii_fields}")
            
            # 설정에 따라 처리
            if config.PII_HANDLING == "BLOCK":
                raise ValueError("PII detected in event data")
            elif config.PII_HANDLING == "ANONYMIZE":
                event.data = self.pii_handler.anonymize_pii(event.data)
            elif config.PII_HANDLING == "ENCRYPT":
                event.data = self.pii_handler.encrypt_pii(event.data)
        
        # 안전한 이벤트 발행
        await self.publisher.publish_event(event)
```

## 📋 배포 전 최종 체크리스트

```bash
# 모든 검증 실행
python scripts/production_readiness_check.py

✓ IAM 최소 권한 정책 확인
✓ DLQ 설정 일치 확인  
✓ 스키마 버전 호환성 확인
✓ SDK 패키지 이름 충돌 없음
✓ CloudWatch 알람 설정 완료
✓ PII 감지 및 처리 활성화

🚀 프로덕션 배포 준비 완료!
```

## 🔐 환경별 설정

### Development
```yaml
pii_handling: "LOG"
retry_attempts: 1
monitoring: "DEBUG"
```

### Staging  
```yaml
pii_handling: "ANONYMIZE"
retry_attempts: 3
monitoring: "INFO"
```

### Production
```yaml
pii_handling: "ENCRYPT"
retry_attempts: 3
monitoring: "WARNING"
encryption_key: "${AWS_KMS_KEY_ID}"
```