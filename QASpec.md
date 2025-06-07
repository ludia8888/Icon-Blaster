[QASpec.md]
## **QASpec.md**

### **1. 문서 개요**

본 문서는 Ontology Editor 플랫폼의 QA(Test) 전략과 세부 테스트 케이스를 엔터프라이즈 프로덕션 수준으로 심층 규격화합니다. 모든 테스트 활동은 CI/CD 파이프라인에 통합되며, 테스트 자동화, 보고·알림, 취약점 관리, 지속적 개선을 포함하여 SRE, 보안 팀, 개발팀 모두가 공유하고 실행할 수 있도록 설계되었습니다.

**대상 독자:** QA 팀, SRE, 보안 팀, 개발자

---

### **2. 테스트 전략**

각 테스트 단계는 코드 품질, 기능 정확성, 시스템 신뢰성, 성능, 보안, 접근성을 검증하며, 모든 결과는 중앙 대시보드와 GitHub Actions 워크플로우에 집계됩니다.

1. **단위 테스트 (Unit Test)**
    - **도구**: Jest, React Testing Library, Jest + Supertest for backend
    - **목표**: 커버리지 ≥ 90% (프론트엔드·백엔드)
    - **대상**:
        - Frontend: atoms, molecules, custom hooks, 서비스 유틸
        - Backend: 서비스 로직, 컨트롤러, 유틸 함수
    - **자동화**: GitHub Actions lint-test 단계에 포함
2. **통합 테스트 (Integration Test)**
    - **도구**: Supertest + Jest (backend), React Testing Library + msw (frontend)
    - **대상**: API 인증, DB 연결, 메시지 버스, GraphQL/REST 레이어
    - **환경**: Testcontainers (PostgreSQL, Redis, Kafka, Neo4j)
    - **검증**: 엔드포인트 응답 코드, 스키마, DB 변경, 이벤트 발행 확인
3. **E2E 테스트 (End-to-End)**
    - **도구**: Cypress + cypress-axe
    - **시나리오** (각각 역할별 3개 이상):
        1. 로그인 → 키클록 모킹 → 토큰 획득
        2. 메타데이터 CRUD: Object/Property/Link 생성·수정·삭제
        3. Action 코드 편집 및 테스트
        4. 버전 관리: Change Set 생성 → Merge → Conflict Resolver → Rollback
        5. 검색 기능 및 Canvas 하이라이트
        6. 권한별 접근 제어 (Admin, Editor, Viewer)
    - **환경**: 브라우저 번들, CI 헤드리스 모드, 비주얼 스냅샷 비교
4. **성능 테스트 (Load & Stress Test)**
    - **도구**: k6, Artillery, Lighthouse CI (프론트)
    - **목표**:
        - API: 99% 요청 응답 시간 ≤ 300ms (동시 200 Users)
        - Canvas: 95th percentile 렌더링 시간 ≤ 200ms (1,000 nodes)
    - **시나리오**:
        - 지속 부하 테스트(30분 Techincal Endurance)
        - Burst 모드(2분 최대 부하)
        - 메모리·CPU 사용량 모니터링 (Grafana)
5. **보안 테스트 (Security Test)**
    - **도구**: OWASP ZAP, Snyk, GitHub CodeQL
    - **검증 대상**:
        - 웹 취약점: XSS, CSRF, SQLi, JWT 취약점
        - 종속성: NPM 패키지 취약점
        - 인프라: 컨테이너 이미지(Trivy), IaC 코드 검사(tfsec)
    - **자동화**: GitHub Actions security-scan 단계 + 주기 스캔(매일)
6. **접근성 테스트 (Accessibility Test)**
    - **도구**: axe-core (unit/E2E), Lighthouse CI
    - **목표**: WCAG 2.1 AA 준수, Color Contrast, Keyboard Nav, Screen Reader 호환성
    - **시나리오**:
        - 주요 화면 스캔 → aXe로 장애 요소 리포트
        - Lighthouse AA 점수 ≥ 90 이상
7. **회귀 테스트 (Regression Test)**
    - **대상**: 주요 시나리오(위 E2E), 버전 관리, 검색, 권한, 기능 충돌
    - **자동화**: 릴리스 브랜치 PR에 E2E + 통합 테스트 자동 실행
8. **기능 비활성화(fallback) 검증**
    - **시나리오**: ElasticSearch/Neo4j 장애 상황 시 Graceful Degradation 확인
    - Mock 서비스 중단 → UI/서비스 레벨 fallback 메시지, 캐시된 데이터 제공 검증

---

### **3. 단위 테스트 케이스 상세**

### **3.1 프론트엔드**

| **컴포넌트/훅** | **테스트 항목** | **기대 결과** |
| --- | --- | --- |
| CanvasArea | 노드 추가/삭제/이동 → 상태 변화 테스트 | nodes 배열 업데이트, 렌더 이벤트 호출 |
|  | Zoom/Pan 이벤트 → zoom 상태, pan 위치 변경 | zoom 값 bounds(0.5–2), pan delta 정확 적용 |
| InspectorPanel | Metadata Form validation → 빈 필드, 잘못된 패턴 오류 처리 | 유효성 에러 메시지 표시, submit 차단 |
| useOntologyStore | 액션(addNode, deleteNode, mergeChangeSet 등) 호출 시 상태 일관성 | immer 기반 불변성 보장, localStorage 동기화 |
| metadataService | 성공, 400, 401, 409 오류 응답 처리 로직 | 적절한 예외 throw 및 메시지 처리 |

### **3.2 백엔드**

| **서비스 메서드** | **테스트 시나리오** | **기대 결과** |
| --- | --- | --- |
| objectService.create | 유효 DTO → DB에 레코드 생성, Kafka 이벤트 발행 | 트랜잭션 커밋, 이벤트 브로커에 메시지 전송 |
|  | 중복 api_name → 409 예외 | ConflictException 코드, 메시지 확인 |
| versionService.merge | 충돌 없음 → master 브랜치 반영 | ChangeSet 상태 merged, 이벤트 발생 |
|  | 충돌 발생(Etag mismatch) → 409 반환, payload 포함 | 클라이언트가 Side-by-Side Merge UI에 사용 |

---

### **4. 통합 테스트 시나리오 상세**

### **4.1 ObjectType API**

1. **생성**: POST → DB, Kafka, ES 인덱스 확인
2. **조회**: GET list + single → 페이징, 필터 쿼리 파라미터
3. **수정**: PUT valid → 버전 증가, AuditLog 레코드 확인
4. **삭제**: DELETE → Soft Delete flag, ES 인덱스 삭제 이벤트

### **4.2 Authentication & Authorization**

- **잘못된 토큰**: 401 응답
- **권한 부족**: 403 응답, 메시지 일관성 검증
- **Role 변경 반영**: Admin -> Viewer 전환 시 API 접근 차단

### **4.3 Property, LinkType, Action Module**

- CRUD 시나리오 동일, payload 스키마 검증, relational integrity 테스트

---

### **5. E2E 테스트 상세 시나리오**

1. **Login Flow**: Redirect, Callback, Token 저장
2. **Node CRUD**: Create → Edit metadata → Delete → 상태 확인
3. **Property/Link**: Modal interaction, inline edit, REST API end-to-end
4. **Action Editor**: CodeEditor load, lint error, save success
5. **Version Control**: ChangeSet timeline, merge conflict simulation
6. **Search & Highlight**: real-time search, list virtualization
7. **RBAC**: 계정별 기능 제한 UI 및 API 검증
8. **Accessibility**: aXe scan within Cypress, keyboard-only navigation

---

### **6. 성능 테스트 시나리오**

- **API Load Test**: k6 스크립트, RPS 200, ramp 0→100→0, 결과 p95 ≤300ms
- **Canvas Stress Test**: headless Chrome + Lighthouse CI, node count 1,000, render ≤200ms
- **Report**: Grafana 대시보드로 집계, 트렌드 분석

---

### **7. 보안 자동화 시나리오**

- **Dependency Scan**: Snyk PR 게이트, 고위험 취약점 차단
- **Static Code Analysis**: CodeQL + ESLint security plugin
- **Dynamic Scan**: OWASP ZAP baseline + full scan, 리포트 아카이빙

---

### **8. 접근성 자동화 시나리오**

- **CI 통합**: axe-core React integration 테스트, cypress-axe로 E2E 스캔, Lighthouse CI
- **WCAG 리포트**: GitHub PR Comment 형식 요약

---

### **9. 테스트 환경 & 데이터 관리**

- **분리된 Test 클러스터**: Kubernetes test 네임스페이스, 동적 프로비저닝
- **데이터 시드**: FactoryGirl / Faker 기반 복합 메타데이터 세트
- **데이터 격리**: 각 CI job별 DB 스키마 격리, 트랜잭션 롤백

---

### **10. 보고서 및 알림**

- **JUnit/XML + Cobertura**: GitHub PR 체크, Coverage Gate
- **Allure Reports**: 통합 리포트, TestOps 연동
- **Slack & Email**: 성공·실패 알림, 주요 리포트 링크 공유

---

### **11. 지속적 개선**

- **Test Flakiness Tracking**: 안정성 지표, flaky test 자동 검출
- **QA Dashboard**: Test Metrics, Failure Trends, Quality Gates 현황
- **정기 리뷰**: 분기별 테스트 커버리지·시나리오 검토 회의