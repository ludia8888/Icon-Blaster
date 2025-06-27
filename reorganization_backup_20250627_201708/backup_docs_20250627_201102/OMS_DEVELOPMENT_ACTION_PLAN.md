# OMS 개발 액션플랜

## 개요
검증 보고서를 바탕으로 수립한 단계별 개발 계획입니다. 총 소요 기간은 약 2-3주이며, Critical 항목부터 우선 개발합니다.

---

## Phase 1: Critical Security 🔴 (1-2일)
**목표**: 보안 취약점 즉시 해결

### 1.1 RBAC 실제 권한 검증 구현
```python
# middleware/rbac_middleware.py 개선
- JWT 토큰에서 역할 추출
- 리소스별 권한 매트릭스 정의
- 엔드포인트별 권한 검증 로직
- 권한 부족 시 403 Forbidden 응답
```

### 1.2 권한 매트릭스 구현
```yaml
permissions:
  admin:
    - schema:*
    - branch:*
    - proposal:*
  developer:
    - schema:read
    - branch:create,read,update
    - proposal:create,read
  viewer:
    - schema:read
    - branch:read
    - proposal:read
```

**산출물**:
- `middleware/rbac_middleware.py` 완전 구현
- `models/permissions.py` 권한 매트릭스 정의
- 권한 검증 유닛 테스트

---

## Phase 2: Data Integrity 🔴 (2-3일)
**목표**: 데이터 무결성 보장

### 2.1 Schema Freeze 메커니즘
```python
# models/branch_state.py
class BranchState(Enum):
    ACTIVE = "ACTIVE"
    LOCKED_FOR_WRITE = "LOCKED_FOR_WRITE"
    READY = "READY"
    ARCHIVED = "ARCHIVED"
```

### 2.2 잠금 상태 관리
- Funnel 인덱싱 시작 시 자동 잠금
- 인덱싱 완료 시 잠금 해제
- 잠금 상태에서 읽기만 허용
- 타임아웃 기반 자동 잠금 해제

**산출물**:
- `core/branch/lock_manager.py` 구현
- 브랜치 상태 전이 로직
- 동시성 제어 테스트

---

## Phase 3: Service Integration 🔴 (2-3일)
**목표**: Funnel Service와 완전한 통합

### 3.1 indexing.completed 이벤트 수신
```python
# core/event_consumer/funnel_handler.py
@event_handler("funnel.indexing.completed")
async def handle_indexing_completed(event: CloudEvent):
    # 브랜치 상태를 READY로 변경
    # autoMerge 조건 확인
    # 자동 머지 실행
```

### 3.2 이벤트 구독 설정
- NATS JetStream 구독자 구현
- 이벤트 라우팅 및 핸들러 매핑
- 실패 시 재시도 로직

**산출물**:
- `core/event_consumer/` 디렉토리 구조
- Funnel Service 연동 통합 테스트
- 이벤트 처리 모니터링

---

## Phase 4: Governance 🟡 (3-4일)
**목표**: 규정 준수 및 감사 추적

### 4.1 Audit 로그 DB 저장
```python
# models/audit.py
class AuditLog(BaseModel):
    id: UUID
    timestamp: datetime
    user_id: str
    issue_id: Optional[str]
    action: str
    resource_type: str
    resource_id: str
    old_value: Optional[Dict]
    new_value: Optional[Dict]
    ip_address: str
    user_agent: str
```

### 4.2 Issue 연계 시스템
- 모든 변경사항에 issue ID 필수화
- Jira/GitHub Issues 연동
- 변경 이유 추적

**산출물**:
- `shared/audit/audit_repository.py` 구현
- Audit 테이블 마이그레이션
- 감사 로그 조회 API

---

## Phase 5: Performance Optimization 🟡 (2-3일)
**목표**: 성능 향상 및 중복 방지

### 5.1 ETag/Version-Hash 델타 응답
```python
# api/v1/schemas.py
@router.get("/schemas")
async def get_schemas(since_hash: Optional[str] = None):
    if since_hash:
        return get_delta_changes(since_hash)
    return get_all_schemas()
```

### 5.2 Idempotent 소비자 개선
- Redis 기반 중복 제거
- Event ID + Commit Hash 조합 키
- TTL 기반 자동 만료

**산출물**:
- 델타 응답 엔드포인트
- Redis 통합
- 성능 벤치마크 결과

---

## Phase 6: Production Readiness 🟢 (3-4일)
**목표**: 프로덕션 배포 준비

### 6.1 NATS 클라이언트 실제 구현
- `nats-py` 라이브러리 통합
- JetStream 설정 최적화
- 연결 풀 관리

### 6.2 Webhook 메타데이터 확장
- Action Service와 스펙 협의
- 상세 메타데이터 구조 추가
- 마이그레이션 스크립트

### 6.3 모니터링 및 알림
- Prometheus 메트릭 수집
- Grafana 대시보드
- 장애 알림 설정

**산출물**:
- 프로덕션 준비 체크리스트
- 배포 가이드
- 운영 매뉴얼

---

## 개발 우선순위 및 일정

| 주차 | Phase | 작업 내용 | 리스크 |
|------|-------|----------|--------|
| 1주차 | 1, 2 | RBAC, Schema Freeze | 🔴 High |
| 2주차 | 3, 4 | Funnel 연동, Audit | 🔴 High |
| 3주차 | 5, 6 | 성능 최적화, 프로덕션 준비 | 🟡 Medium |

---

## 성공 기준

### Week 1 완료 시점
- [ ] 모든 API 엔드포인트에 권한 검증 적용
- [ ] 동시 스키마 수정 방지 가능
- [ ] 보안 취약점 제거

### Week 2 완료 시점
- [ ] Funnel Service와 완전 통합
- [ ] 모든 변경사항 감사 추적 가능
- [ ] 규정 준수 요구사항 충족

### Week 3 완료 시점
- [ ] 성능 목표 달성 (델타 응답으로 90% 트래픽 감소)
- [ ] 프로덕션 배포 준비 완료
- [ ] 운영 문서화 완성

---

## 리소스 요구사항

### 개발 환경
- Redis 인스턴스 (Idempotent 소비자용)
- NATS JetStream 클러스터
- 테스트용 Funnel Service 인스턴스

### 인력
- 백엔드 개발자 2명
- DevOps 엔지니어 1명 (Week 3)
- QA 엔지니어 1명

---

## 리스크 관리

### 기술적 리스크
1. **NATS 통합 복잡도**: 단계적 마이그레이션으로 대응
2. **성능 저하**: 캐싱 전략 수립
3. **하위 호환성**: 버전별 API 제공

### 일정 리스크
1. **Funnel Service 의존성**: 목업 서비스로 개발 시작
2. **테스트 환경 구축**: 도커 컴포즈로 로컬 환경 구성

---

*작성일: 2025-06-26*
*승인 필요: CTO, Security Officer, Product Owner*