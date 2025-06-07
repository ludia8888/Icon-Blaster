
## **1. 프로젝트 개요**

### **1.1 배경**

- **이종 시스템 데이터 통합의 중요성**
    
    기업 내 ERP, CRM, CSV, 외부 API 등 이기종 시스템에서 생성된 메타데이터를 통합·관리하지 못할 경우, 데이터 사일로 발생과 의사결정 지연·오류 유발 → 비용 증가 및 경쟁력 약화
    
- **시장 요구 및 레퍼런스**
    
    Palantir Foundry, DataHub, Amundsen 등 온톨로지 기반 메타데이터 관리 플랫폼이 급부상하여, 조직 내 공유 어휘 관리 및 자율적 데이터 거버넌스 수요 증가
    

### **1.2 목적**

- **비개발자 친화적 GUI 제공**
    
    도메인 전문가, PM, 기획자 등이 코드 작성 없이 드래그앤드롭 인터페이스로 Object Type, Property, Link Type, Interface, Action/Function 정의·수정 가능
    
- **엔터프라이즈 레벨의 Palantir Open source 개발을 통해, 사회공헌적 가치 창출**
- **일관된 공유 어휘 확보**
    
    모든 이해관계자가 동일한 온톨로지 기반 메타데이터를 활용하여 데이터 파이프라인, AI 모델, 애플리케이션 개발 전 단계에서 오류 최소화 및 생산성 극대화
    
- **확장 가능한 엔터프라이즈 운영**
    
    RBAC, 감사 로깅, 버전 관리, 외부 색인/그래프 동기화 등을 통해 수백~수천 개 객체의 관리 및 대규모 팀 협업 지원
    

### 1.3 개발 목표(Goal)

엔터프라이즈 레벨의 범용목적 팔란티어 Foundry 를 상회하는 open source 개발.

## **2. 범위 및 아웃-오브-스코프**

### **2.1 포함 기능 (In Scope)**

1. **메타데이터 관리**
    - CRUD: Object Type, Property, Link Type, Interface, Action/Function
    - 상세 속성: Display/API Name, Description, Icon, Color, Group, Visibility, Status
2. **시각적 Canvas UI**
    - 노드 생성·이동·삭제, 링크 연결·편집, Inspector Panel 연동
3. **버전 관리 & 협업**
    - Change Set 생성·Commit·Merge·Rollback, 충돌 탐지·해결, 이력(Lineage) 조회
4. **권한·보안**
    - OAuth2/OpenID Connect 인증, JWT 기반 RBAC, 필드 레벨 권한, 감사(Audit) 로깅
5. **외부 연동**
    - ElasticSearch 색인, Neo4j Graph DB 동기화, Webhook/Event 연계
6. **검색 및 탐색**
    - 풀텍스트 검색, 페이징, Virtualized List, Canvas 포커싱

### **2.2 제외 기능 (Out of Scope)**

- 대규모 ETL·AI 파이프라인 구현
- 모바일 네이티브 앱 (단, 반응형 UI는 포함)
- 커스터마이징 가능한 테마 기능

## **3. 이해관계자 및 역할**

| **역할** | **책임** | **커뮤니케이션 주기** |
| --- | --- | --- |
| Product Owner | 요구사항 우선순위 정의, 승인, 주요 의사결정 | 주간 스프린트 회의 |
| 도메인 전문가 | 메타데이터 모델 유효성 검증, 요구사항 상세화 피드백 | 기능 리뷰 세션 |
| UX/UI 디자이너 | 와이어프레임·프로토타입 작성, 사용자 흐름 검증 | 디자인 스프린트 |
| 프론트엔드 개발자 | Canvas UI, Inspector Panel, 상태관리, 접근성 준수 구현 | 데일리 스탠드업 |
| 백엔드 개발자 | OMS API, 이벤트 버스, 색인/그래프 동기화 모듈 개발 | 데일리 스탠드업 |
| QA 엔지니어 | 단위·통합·E2E·부하·보안 테스트 계획 및 실행 | 스프린트 종료 회고 |
| DevOps 엔지니어 | CI/CD, Kubernetes 인프라, 모니터링·알람 설정 | 월간 운영 회의 |

## **4. 사용자 페르소나 & 시나리오**

### **4.1 페르소나**

| **페르소나** | **설명** |
| --- | --- |
| 도메인 전문가 | 온톨로지 정의 경험 부족, UI 기반 메타데이터 편집 선호 |
| 프로젝트 매니저(PM) | 요구사항 관리와 협업 활동 주도, 검토·승인 프로세스 중요시 |
| 엔터프라이즈 관리자 | 시스템 안정성·보안·규정 준수 필수, 감사 로그·버전 관리 세부 기능 요구 |

### **4.2 주요 시나리오**

1. **신규 온톨로지 생성**
    
    PM이 Canvas에 Object 드래그 → 속성 입력 모달 → ‘Create’ 클릭 → 노드 렌더 → Inspector Panel에서 추가 수정
    
2. **동시 편집 충돌 해결**
    
    사용자 A, B가 동일 Object 편집 → Save 충돌 감지 → Side-by-Side Diff UI 제공 → Merge 선택 → 자동 Commit
    
3. **온톨로지 재사용 및 배포**
    
    기존 ‘Employee’ 검색 → Canvas로 드래그 → 새 Change Set에 Commit → Test/Staging에 배포 → 운영 릴리스
    

## **5. 상세 요구사항**

### **5.1 기능 요구사항**

각 요구사항은 *Use Case ID*, *Description*, *Precondition*, *Steps*, *Postcondition* 및 _Error Handling_을 포함합니다.

### **5.1.1 Object Type CRUD**

- **UC-OBJ-01 생성**
    - Pre: 사용자가 “Node” 탭 선택, Canvas 초기화
    - Steps: 드래그 → 모달 입출력 → POST /api/object-type → 201
    - Post: Canvas에 Object Node 렌더, Change Set에 추가
    - Error: 필수 필드 누락 시 400, 중복 api_name 시 409
- **UC-OBJ-02 조회**
    - GET /api/object-type?page=&limit=
    - 반환: 페이징된 목록 + 전체 Count
- **UC-OBJ-03 수정**
    - PUT /api/object-type/:rid?version= → 200 + Location 헤더
    - ETag mismatch 시 409 + 최신 버전 정보 제공
- **UC-OBJ-04 삭제**
    - DELETE /api/object-type/:rid → 204
    - Soft delete 고려 시 deleted_at 필드 업데이트

### **5.1.2 Property CRUD**

- **UC-PROP-01 생성**
    - POST /api/property { object_rid } → 201
    - Conditional Formatting JSON 구문 검증 → 400 처리

… (Link Type, Interface, Action 정의도 동일 패턴)

### **5.2 비기능 요구사항**

| **유형** | **요구사항 및 수치 기준** |
| --- | --- |
| 성능 | - Canvas 렌더 95% ≤ 200ms (1,000 노드 기준)  - API 95% ≤ 300ms (100 동시) |
| 보안 | - TLS 1.2+, OAuth2/OIDC, CSRF 방어  - OWASP Top10 취약점 없음 |
| 확장성/가용성 | - K8s Auto-Scaling, Replica ≥ 3  - 장애 시 5분 이내 자동 복구 |
| 접근성 | - WCAG 2.1 AA  - 키보드 내비게이션, ARIA 속성 준수 |
| 운영성 | - SLA 99.9% 이상  - 모니터링 및 알람 2분 이내 이상 감지 |

### **5.3 Acceptance Criteria**

- **AC-001**: Object CRUD 시나리오 100% 통과 (Unit/Integration)
- **AC-002**: Canvas 렌더 성능 테스트 통과 (k6)
- **AC-003**: 보안 스캔 결과 High/Critical 이슈 0
- **AC-004**: Accessibility 스캔 AA 이상 준수

## **6. 아키텍처 개요**

- **모듈**: Client UI, OMS API, MetaStore DB, ElasticSearch, Neo4j, Kafka, Redis, CI/CD, Monitoring
- **데이터 흐름**: 사용자 → UI → API → DB → EventBus → Index/Graph Sync → UI 검색
- **다이어그램**: Figma Link 참조 (업데이트 필요)

## **7. 타임라인 & 마일스톤**

| **Phase** | **Duration** | **Deliverables** |
| --- | --- | --- |
| 1. 설계 & PoC | 2주 | PRD, 설계 문서, POC Demo |
| 2. MVP 개발 | 4주 | Object/Property/Link CRUD, Canvas UI, DB schema |
| 3. 버전 관리 → Beta | 4주 | Change Set, Conflict Resolver, Audit Log |
| 4. 보안·권한·테스트 | 3주 | OAuth2, RBAC, Unit/Integration, Security Test |
| 5. 색인·Graph Sync | 3주 | ES 인덱스, Neo4j Sync |
| 6. 최적화·베타 릴리스 | 2주 | 성능 튜닝, 사용자 피드백 반영 |
| 7. 정식 릴리스 | 2주 | 운영 배포, 모니터링, 매뉴얼 공개 |

## **8. 제약 사항 & 가정**

- Keycloak 운영 환경 준비 완료
- ElasticSearch/Neo4j 라이선스 확보
- 외부 API 응답 시간 ≤ 200ms 가정

## **9. 위험 요소 및 완화 방안**

| **위험 요소** | **영향** | **완화 방안** |
| --- | --- | --- |
| 요구사항 변경 | 일정 지연 | MoSCoW 기법, Change Control Board 운영 |
| 동시 편집 충돌 | 데이터 무결성 손상 | Pessimistic Lock, Side-by-side 머지 UI |
| 성능 저하 | 사용자 경험 저하 | Canvas 가상화, 서버 사이드 페이징, CDN 활용 |
| 보안 취약점 | 데이터 유출, 규정 위반 | 정기 보안 스캔, CSP, 입력값 검증, WAF 도입 |
| Graph DB/ES 장애 | 검색·탐색 불가 | 서킷 브레이커, 캐시 우회 모드 |
| CI/CD 실패 | 배포 불능 | 롤백 전략, 블루-그린 배포, Canary Release 운영 |

## **10. 용어 사전**

- **OMS**: Ontology Management System
- **Change Set**: 메타데이터 변경 단위, 브랜치 컨텍스트
- **Canvas**: 시각적 온톨로지 에디터 화면
- **Inspector Panel**: 노드/링크 상세 편집 패널

## **11. 후속 문서 링크**

- [DesignDoc.md]
- [FrontendSpec.md]
- [BackendSpec.md]
- [APISpec.md]
- [InfraSpec.md]
- [CICDSpec.md]
- [QASpec.md]

---