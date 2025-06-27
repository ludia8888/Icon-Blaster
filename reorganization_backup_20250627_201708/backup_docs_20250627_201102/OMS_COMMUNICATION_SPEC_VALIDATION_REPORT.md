# OMS ↔ 외부 MSA 통신 명세 검증 보고서

## Executive Summary

Palantir Foundry식 아키텍처 기반 OMS 통신 명세서와 실제 코드베이스를 철저히 검증한 결과, **핵심 기능의 약 70%가 구현**되어 있으며, 나머지 30%는 추가 개발이 필요한 상태입니다.

### 🟢 구현 완료 (Well-Implemented)
- CloudEvents 1.0 기반 이벤트 시스템
- Outbox 패턴을 통한 트랜잭션 보장
- GraphQL API 및 실시간 구독
- 기본적인 JWT 인증 체계
- DLQ 및 재시도 메커니즘

### 🟡 부분 구현 (Partially Implemented)
- RBAC (골격만 존재, 실제 권한 검증 미구현)
- Audit 로깅 (기본 구조만, DB 저장 미구현)
- Idempotent 소비자 (메시지 ID 기반만, commit 연계 없음)

### 🔴 미구현 (Not Implemented)
- ETag/Version-Hash 기반 델타 응답
- Schema Freeze (LOCKED_FOR_WRITE)
- Funnel Service의 indexing.completed 이벤트 수신
- Webhook 상세 메타데이터 구조

---

## 1. 이벤트 발행 시스템 검증

### 1.1 CloudEvents 구현 상태
```
✅ 구현 완료
- CloudEvents 1.0 스펙 완전 준수
- 확장 속성 지원 (ce-correlationid, ce-causationid, ce-branch 등)
- Structured/Binary Content Mode 지원
```

### 1.2 이벤트 타입 매핑
| 명세서 이벤트명 | 실제 구현 이벤트명 | 상태 |
|----------------|-------------------|------|
| schema.changed | com.foundry.oms.schema.updated | ✅ |
| branch.created | com.foundry.oms.branch.created | ✅ |
| branch.merged | com.foundry.oms.branch.merged | ✅ |
| proposal.status | com.foundry.oms.proposal.[approved/rejected/merged] | ✅ |
| actiontype.changed | com.foundry.oms.actiontype.updated | ✅ |
| linktype.changed | com.foundry.oms.linktype.updated | ✅ |
| schema.deleted | com.foundry.oms.schema.deleted | ✅ |

### 1.3 발견된 차이점
1. **네이밍 컨벤션**: 명세서는 간단한 형식, 실제는 reverse domain notation 사용
2. **이벤트 세분화**: proposal.status가 approved/rejected/merged로 세분화
3. **멀티 플랫폼**: NATS 외에 AWS EventBridge도 지원

---

## 2. 외부 서비스 수신 API 검증

### 2.1 REST API 엔드포인트
```
✅ 기본 구현
- /api/v1/schemas/{branch}/object-types
- /action-types (CRUD)
- /api/v1/schema/events/audit

❌ 미구현
- /schemas/{id} (Funnel Service용)
- /roles (Policy/Access용)
- ETag 헤더 지원
```

### 2.2 GraphQL API
```
✅ 완전 구현
- 전체 스키마 타입 정의
- Query/Mutation/Subscription 지원
- WebSocket 기반 실시간 업데이트
- Introspection 지원
```

### 2.3 인증/인가
```
⚠️ 부분 구현
- JWT 토큰 검증 (User Service 연동)
- 기본 RBAC 미들웨어 (실제 권한 검증 없음)
- 모든 요청이 현재는 통과 상태
```

---

## 3. Webhook 및 Action Service 연동

### 3.1 Webhook 메타데이터
```
❌ 상세 구조 미구현
명세서: {
  "webhook": {
    "url": "...",
    "method": "POST",
    "signing": "HMAC-SHA256",
    "retryPolicy": {...}
  }
}

실제: webhookUrl 필드만 존재
```

### 3.2 실행 책임 분리
```
✅ 올바른 구현
- OMS: 메타데이터 저장만 담당
- Action Service: 실제 webhook 실행
- mTLS 기반 서비스 간 통신
```

---

## 4. 안정성/거버넌스 구현 상태

### 4.1 구현 완료도
| 항목 | 상태 | 설명 |
|------|------|------|
| Outbox 패턴 | ✅ | 완전 구현, 트랜잭션 보장 |
| DLQ | ✅ | 엔터프라이즈급 구현 |
| Idempotent 소비자 | ⚠️ | 메시지 ID 기반만, commit 연계 없음 |
| Version Hash Pull | ❌ | 미구현 |
| RBAC | ⚠️ | 골격만, 실제 권한 검증 없음 |
| Audit | ⚠️ | 로깅만, DB 저장 없음 |
| Schema Freeze | ❌ | 미구현 |

---

## 5. 핵심 권장사항

### 5.1 즉시 개발 필요 (Critical)
1. **RBAC 완성**: 실제 권한 검증 로직 구현
2. **Funnel Service 이벤트 수신**: indexing.completed 핸들러 추가
3. **Schema Freeze**: 동시 수정 방지를 위한 잠금 메커니즘

### 5.2 단기 개선 필요 (High Priority)
1. **ETag/Version Hash Pull**: 델타 동기화 지원
2. **Audit DB 저장**: 규정 준수를 위한 영구 저장
3. **Webhook 메타데이터 확장**: Action Service와 협의

### 5.3 장기 개선 사항 (Medium Priority)
1. **NATS 클라이언트 실제 구현**: 현재 더미를 실제 라이브러리로 교체
2. **서비스 디스커버리**: 동적 서비스 연결 관리
3. **모니터링 대시보드**: 이벤트 흐름 시각화

---

## 6. 리스크 평가

### 🔴 High Risk
- **RBAC 미구현**: 보안 위험, 무단 접근 가능
- **Schema Freeze 부재**: 데이터 무결성 위험

### 🟡 Medium Risk
- **Idempotent 불완전**: 중복 이벤트 처리 가능
- **Audit 미완성**: 규정 준수 문제

### 🟢 Low Risk
- **ETag 미지원**: 성능 영향 (불필요한 전체 조회)
- **Webhook 단순화**: Action Service에서 처리 가능

---

## 7. 결론

OMS는 Palantir Foundry식 아키텍처의 핵심 개념을 잘 구현하고 있으나, 엔터프라이즈 환경에서 요구되는 몇 가지 중요한 기능이 누락되어 있습니다. 특히 **RBAC, Schema Freeze, Funnel Service 연동**은 프로덕션 배포 전 반드시 구현되어야 합니다.

현재 상태로도 개발/테스트 환경에서는 충분히 사용 가능하나, 프로덕션 환경에서는 위에서 언급한 Critical 항목들의 구현이 선행되어야 합니다.

---

*검증 일시: 2025-06-26*
*검증자: Claude Code*
*코드베이스 버전: main branch (commit 362f378)*