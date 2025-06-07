**1.1. 배경 및 목적**

**1. 프로젝트 개요**

- **배경**
  - 현대 기업은 ERP, CRM, CSV, 외부 API 등 이기종 시스템에서 발생하는 데이터를 통합하고, 이들 간의 의미 있는 관계(예: 고객 → 주문 → 제품 → 재고 등)를 명확하게 정의·관리할 필요가 점점 커지고 있음.
  - Palantir Foundry는 온톨로지 기반 메타데이터 관리(OMS)와 직관적인 온톨로지 에디터(드래그앤드롭 GUI)를 제공하여, 비개발자도 도메인 모델을 쉽게 정의·수정할 수 있도록 지원함.
- **목적**
  - Palantir Foundry의 온톨로지 에디터 수준의 기능을, React + BlueprintJS 기반 프런트엔드와 Node.js/TypeScript 기반 백엔드(OMS API)로 구현.
  - 도메인 전문가·기획자·PM 등 비개발자도 **Object Type, Property, Link Type, Interface, Action/Function** 등을 시각적으로 정의·관리할 수 있는 GUI 제공.
  - 조직 내 모든 이해관계자가 동일한 **공유 어휘(shared vocabulary)**로 메타데이터를 활용할 수 있게 하여, 이후 데이터 파이프라인·AI 모델·어플리케이션 개발 단계에서 일관성 유지.

**1.2. 기획 범위**

1. **온톨로지 메타데이터 정의·수정**
   - Object Type, Property, Link Type, Interface, Action/Function 등의 메타데이터 CRUD
2. **시각적 인터페이스(UI/UX) 설계**
   - 드래그앤드롭 Canvas: 노드 생성 → 관계선 연결 → 속성 패널 편집 → 액션·함수 정의
3. **버전 관리 및 협업 기능**
   - Change Set 단위 버전 관리 → 동시 편집 충돌 방지(Locking·Merge) → 이력 조회(Lineage)
4. **권한·보안 제어**
   - Role 기반 세부 권한(RBAC) → 필드 레벨 권한 제어 → 감사 로깅(Audit Log)
5. **외부 시스템 연동**
   - ElasticSearch(또는 Phonograph) 색인 → Neo4j Graph DB 동기화 → ETL/AI 워크플로우 연계
6. **테스트·배포 로드맵**
   - 단계별 점진적 출시:
     1. MVP (핵심 Object/Property/Link 편집 기능)
     2. Beta (버전 관리·Action 정의)
     3. 정식 (권한·보안·외부 동기화)

## **2. 핵심 요구사항 정리**

### **2.1. 기능적 요구사항 (Functional Requirements)**

1. **Object Type 정의**
   - **생성/삭제/수정**
     - 화면에서 “New Object” 버튼 클릭 → 모달 팝업 → Display Name, API Name, Description, Icon, Color, Group, Visibility, Status 입력 → 저장 → OMS API POST /api/object-type 호출
     - 수정 시 노드를 선택 → Inspector Panel 탭 내 수정 가능한 필드 클릭 → 변경 → OMS API PUT /api/object-type/:rid 호출
     - 삭제 시 노드 우클릭 메뉴 → “Delete Object” → 삭제 확인 모달 → OMS API DELETE /api/object-type/:rid 호출
   - **속성(Property) 관리**
     - Inspector Panel 내 Properties 탭: 속성 목록 테이블 표시 → “Add Property” 버튼 클릭 → 모달 팝업 → API Name, Display Name, Base Type, Title Key, Primary Key, Visibility, Status, Render Hints, Value Format, Conditional Formatting 등 입력 → 저장 → OMS API POST /api/property 호출
     - 수정/삭제: 속성 목록에서 개별 Row 클릭 → 인라인 편집 또는 삭제 아이콘 클릭 → OMS API PUT/DELETE /api/property/:rid 호출
   - **Display Name, API Name, Description, Icon/Color, Groups 설정**
     - Icon: BlueprintJS Icon Picker 컴포넌트 활용 (문자열로 아이콘 이름 저장)
     - Color: 컬러 피커 컴포넌트(예: react-color 패키지) 사용 후 HEX 코드 저장
     - Groups: 태그 입력 컴포넌트(예: BlueprintJS MultiSelect)로 복수 그룹 저장 (배열)
   - **Visibility 설정**
     - Enum 세 가지(pronounced/prominent, normal, hidden) 중 선택 → OMS에 저장
   - **Status 관리**
     - Enum 세 가지(active, experimental, deprecated) 중 선택 → 색상/스타일 차별화
   - **Inspector Panel**
     - 노드 클릭 시 우측에 슬라이딩 패널로 등장
     - 상단에 Object Type 기본 메타데이터(메타 ID, 생성자, 수정자, 생성/수정 일시, Display/API Name, Description, Icon, Color, Groups, Visibility, Status) 표기
     - 하단 탭으로 분리:
       - Metadata 탭 (기본 정보)
       - Properties 탭 (속성 목록 + 편집)
       - Links 탭 (해당 노드와 연결된 Link Type 목록)
       - Help 탭 (해당 노드 문서, 툴팁)
2. **Property 정의**
   - **Base Type 선택**
     - 드롭다운: string, integer, boolean, date, decimal
   - **Keys 설정**
     - Title Key 체크박스: 객체 대표값
     - Primary Key 체크박스: 고유 식별자
   - **Render Hints**
     - 체크박스 멀티셀렉트: searchable, sortable, filterable
   - **Conditional Formatting**
     - JSON 에디터(예: Monaco Editor의 JSON 모드) → { "lte": 10, "color": "red" } 형식
   - **Value Formatting**
     - 텍스트 입력 또는 드롭다운: 날짜 포맷(YYYY-MM-DD), 숫자 포맷(#,###), 사용자 ID 렌더링 등
3. **Link Type 정의**
   - **Source Object / Target Object 연결**
     - Sidebar의 Link 아이콘(화살표 모양) 드래그 → Canvas 상에서 Source Node 클릭 → Target Node 클릭 → Link 생성 모달 팝업
   - **Cardinality**
     - 드롭다운: ONE_TO_ONE, ONE_TO_MANY, MANY_TO_MANY
   - **Bidirectional/Unidirectional 표시**
     - 체크박스 “Bidirectional” 또는 드롭다운 “Direction”: Unidirectional(단방향) / Bidirectional(양방향)
   - **Relationship Label (API Name)**
     - 텍스트 입력: employs, isEmployedBy 등
   - **Description, Status, Visibility**
     - 링크 설명 입력, Enum 선택, Visibility 설정
   - **저장** → OMS API POST /api/link-type 호출 → 캔버스에 방향성 있는 화살표로 렌더
4. **Interface 정의**
   - **Interface 생성**
     - Sidebar의 Interface 아이콘(육각형) 드래그 → Canvas 드롭 → 팝업: Display Name, API Name, Description, Icon, Color, Status, Visibility 입력 → 저장 → OMS API POST /api/interface 호출
   - **Implemented By 목록 관리**
     - Inspector Panel 내 ImplementedBy 탭 → MultiSelect 컴포넌트로 Object Type ID 배열 입력
     - 저장 시 OMS API PUT /api/interface/:rid 호출
5. **Action/Function 정의**
   - **Action 생성**
     - Sidebar의 Action 아이콘(기어 모양) 드래그 → Canvas 드롭 → 팝업: Display Name, API Name, Description, Input Schema(JSON), Output Schema(JSON), Security Rules(JSON) 입력 → 저장 → OMS API POST /api/action-type 호출
   - **Function 코드 편집기 (TypeScript/JavaScript)**
     - Canvas 상 Action 노드 클릭 → 오른쪽 Inspector Panel의 “Code” 탭 클릭 → 내장 Monaco Editor 컴포넌트 오픈
       - TypeScript 문법 하이라이팅, LSP(Language Server) 자동완성 지원
       - 상단에는 Action 이름, 입력/출력 스키마 요약 표시
       - 우측에는 Security Rules JSON 편집기
       - 하단에 “Save” 버튼: 코드 변경 시 PUT /api/action-type/:rid 호출
   - **Security Rules**
     - JSON 형식으로 역할 배열 입력 예시: { "roles": ["Admin","Editor"] }
   - **버전 관리 (Function 버전)**
     - 함수 Body 변경 시 Change Set 단위로 자동 버전 기록 → POST /api/version/function/:rid
     - Inspector Panel 내 Version History 탭에서 이전 코드 확인 및 Rollback
6. **드래그앤드롭 기반 UI**
   - **Canvas**
     - Grid 배경선 표시(50px 단위)
     - 줌/팬 기능: 마우스 휠로 줌 인·아웃, 드래그로 이동
     - 노드 해상도 제한: 최소 80×40px, 최대 200×100px
   - **노드(Node)**
     - **Object Node**
       - 상단: Display Name (텍스트, Bold, BlueprintJS Typography)
       - 중앙: 속성 요약 (예: name: String, age: Integer → 최대 3개 까지만 노출, 더 있으면 “+N more” 표시)
       - 하단: Inspector Panel 호출 버튼(펜 아이콘)
       - 색상: Status별 색상 배경 (active=파랑 계열, experimental=노랑 계열, deprecated=회색 계열)
       - 테두리: Outline color 로 Visibility 강조 (prominent=두꺼운 테두리, normal=기본, hidden=희미한 테두리)
     - **Interface Node**
       - Object Node와 유사하나, 상단에 “Interface” 라벨 표시 및 육각형 테두리
     - **Action Node**
       - 원형 노드 형태
       - 중앙: Action 이름 표시
       - 클릭 시 Inspector Panel 내 CodeEditor 열림
     - **링크(Edge)**
       - Arrowhead: 단방향/양방향 표시
       - 라벨: API Name (화면에 축소되어 보이다가, 마우스 오버 시 툴팁으로 전체 보이기)
       - 색상: Status별 색상 적용 (active=파랑, experimental=노랑, deprecated=회색)
       - 두께: Cardinality에 따라 다르게(ONE_TO_ONE=1px, ONE_TO_MANY=2px, MANY_TO_MANY=3px)
7. **버전 관리 및 협업**
   - **Change Set 생성**
     - 사용자가 편집을 시작하면 자동으로 “Change Set A” 생성 (auto-save)
     - 5분 간격으로 또는 사용자가 명시적으로 “Save Change Set” 버튼 클릭 시 커밋 발생 → OMS API POST /api/change-set 호출
   - **Change Set 이력 뷰어**
     - Inspector Panel 또는 별도 하단 패널(VersionControl Component)에서 Change Set 리스트 표시
       - 각 Change Set: 이름, 작성자, 생성일, 상태(open/merged/closed)
       - 클릭 시 상세 변경 내역(“Property 추가됨”, “LinkType 삭제됨” 등) 표시
   - **충돌 감지(Collision Detection)**
     - A, B 사용자가 동일 Object를 동시에 수정하려고 할 때:
       - Object Type 로드 시 ETag(Header) 또는 Version Field를 가져옴
       - 수정 → PUT /api/object-type/:rid?version=<currentVersion> → 버전 불일치 시 409 Conflict 반환
       - UI: 충돌 감지 팝업 모달 (A와 B의 변경 내용을 Side-by-Side Diff 형식으로 보여주고, Merge/Discard 선택)
   - **Locking**
     - 사용자가 Change Set 생성 후 특정 Object를 편집 중일 때, 저장 전까지 해당 Object에 대해 Pessimistic Lock 적용
     - Lock 정보는 Redis 기반으로 관리(키: object_rid, 값: userId, TTL 10분)
     - 다른 사용자가 편집 시 “Locked by ” 메시지 표시
   - **롤백 기능**
     - Change Set History에서 특정 Change Set 선택 후 “Rollback to This Version” 클릭 → OMS API POST /api/change-set/:id/rollback 호출 → 해당 시점으로 메타데이터 복원
8. **권한·보안 제어 (RBAC)**
   - **Role 정의**
     - Ontology Admin: 모든 메타데이터 생성·삭제·수정 가능
     - Ontology Editor: Object/Property/Link/Action 생성·수정 가능, 삭제 제한
     - Ontology Viewer: 메타데이터 조회만 가능
   - **필드 레벨 권한 설정**
     - Inspector Panel 내 필드별 “Field Permission” 버튼 클릭 → 모달: 특정 Property나 Node-Level Permission 지정 (예: Admin만 볼 수 있음, Editor만 수정 가능 등) → 저장 시 OMS API PUT /api/permission/field 호출
   - **감사 로깅(Audit Logging)**
     - 모든 CRUD 이벤트: Object Type, Property, Link Type, Interface, Action Type, Change Set, Permission 변경, 사용자 로그인/로그아웃 등
     - 백엔드 Level에서 이벤트 발생 시 AuditService 호출 → PostgreSQL audit_log 테이블에 레코드 삽입
   - **데이터 암호화**
     - **전송 계층 암호화**: TLS 1.2 이상 적용 (로드밸런서 → OMS API 서버)
     - **저장 암호화(Optional)**: Aurora PostgreSQL TDE 지원 또는 application-level encryption (예: pgcrypto)
   - **인증(Authentication)**
     - OAuth 2.0 기반 OpenID Connect (Keycloak) 연동
       - OMS API 서버는 Access Token(JWT)을 Authorization 헤더로 수신 → 검증 (JWKS)
       - 프런트엔드는 @auth0/auth0-react 라이브러리 또는 react-oauth2-hook 사용하여 로그인 흐름 처리
   - **권한 부여(Authorization)**
     - JWT 내부의 Role Claim 검사 → API 접근 제어
     - React Router 기반 도메인 라우트 보호 → 권한 없는 경우 “403 Forbidden” 화면
9. **외부 시스템 연동**
   - **색인(Indexing)**
     - CRUD 이벤트 발생 시, 내부 EventEmitter(또는 Kafka) 발행
     - IndexingService (Node.js) 구독 → ElasticSearch/Phonograph로 변경 내용 전송
     - ElasticSearch 인덱스 스키마 예시 (Object Index):

{

"rid": "uuid-1234",

"object_id": "Employee",

"display_name": "Employee",

"groups": ["HR","Employee360"],

"status": "active",

"visibility": "prominent",

"properties": ["fullName","startDate","employeeNumber"],

"link_count": 5

}

-
- GraphQL 또는 REST 기반 색인 조회 API 제공 (GET /api/index-search?query=...)
- **Graph DB 동기화 (Neo4j)**
  - **Full Sync**
    - 주요 릴리스 직후 또는 일정 스케줄(Kubernetes CronJob, 매일 새벽 2시)
    - OMS API GET /api/object-type, GET /api/link-type → 전체 데이터를 Cypher 스크립트로 변환 후 Neo4j에 반영 (Bolt 프로토콜 사용)
  - **Incremental Sync**
    - Change Set이 Master 브랜치에 Merge될 때마다
    - 변경된 Object/Link 정보만 추출하여 Cypher MERGE 문 생성 및 Neo4j 실행
    - 오류 발생 시 Retry 로직 3회 수행 후 실패 시 알림 (이메일, Slack)
  - **서킷 브레이커 패턴**
    - Neo4j Connection 장애 시, 일정 시간(예: 5분) 동안 Neo4j Sync를 중단하고, OMS 내 색인(ElasticSearch)을 우선 사용하도록 Graceful Degradation
- **ETL 파이프라인·AI 워크플로우 인터페이스**
  - **API (REST/gRPC)**
    - GET /api/ontology-schema → 최신 온톨로지 스키마 반환 (JSON)
    - POST /api/ontology-validate → 입력된 데이터(JSON)를 현 온톨로지 기준으로 검증 → 오류 목록 반환
  - **Webhook/Event**
    - “OntologyUpdated” 이벤트 발생 시 등록된 외부 엔드포인트(예: 데이터 오케스트레이터)로 POST 요청 전송 (Payload: 변경된 메타데이터 요약)

1. **테스트 케이스 및 배포 요건**
   - **유닛 테스트(Unit Test)**
     - 모든 React 컴포넌트(src/components/**/\*.tsx), 유틸 함수(src/utils/**/\*.ts)에 대해 Jest + React Testing Library로 테스트 커버리지 80% 이상 달성
     - OMS API의 핵심 비즈니스 로직(Controller, Service Layer)에 대해 Jest로 단위 테스트
     - 예:
       - CanvasArea.test.tsx: 노드 생성, 노드 삭제, NODE_PROP 업데이트 시 올바른 Canvas 상태 변화 보장
       - ObjectService.test.ts: 객체 생성 시 Database에 레코드가 올바르게 삽입되는지, 중복 API Name 오류 시 예외 발생 보장
   - **통합 테스트(Integration Test)**
     - React E2E(End-to-End) 테스트: Cypress 사용
       - 시나리오 예시:
         - 로그인 → Keycloak 로그인 팝업 → 성공 → 토큰 발급 → Ontology Editor 진입
         - Sidebar에서 Object Drag & Drop → 모달 팝업 → 정보 입력 → 저장 → 캔버스에 노드 렌더 확인
         - 노드 클릭 → Inspector Panel에 속성 목록 확인 → 속성 추가 → 저장 후 속성 목록에 반영 확인
         - Link 생성: 두 노드 선택 → 모달 팝업 → 정보 입력 → 캔버스에 화살표 렌더 확인
         - Change Set 생성 → VersionControl 패널에서 Change Set 목록 확인 → Merge 테스트 → 노드 충돌 시 머지 UI 확인
     - OMS API + DB 통합 테스트: Supertest + Jest
       - 예: test/objectType.e2e.ts
         - POST /api/object-type 호출 시 201 Created 반환 및 DB에 레코드 존재 확인
         - PUT /api/object-type/:rid 호출 시 버전 불일치인 경우 409 Conflict 반환
         - DELETE /api/object-type/:rid 호출 시 204 No Content 반환 및 DB에서 삭제 확인
   - **부하 테스트(Load Test)**
     - k6 또는 Apache JMeter 사용
       - **UI 부하 테스트**: 최대 1,000개의 Object Node + 5,000개의 Property + 2,000개의 Link를 Canvas에 렌더 시도
         - 반응 속도 200ms 이하 달성
         - 메모리 사용량 모니터링(Chrome DevTools → Performance)
       - **API 부하 테스트**: 동시 100명의 사용자 →
         - GET /api/object-type (500개 이상의 객체 조회) → 응답 시간 300ms 이하
         - POST /api/property (동시 50건) → 성공률 99% 이상
   - **보안 테스트(Security Test)**
     - OWASP Top10 취약점 점검(정적 분석 + 동적 분석)
       - **SQL Injection**
         - 특수문자가 포함된 API 요청(예: ' OR 1=1--) 시 Prepared Statement로 안전하게 처리
       - **XSS (Cross-Site Scripting)**
         - React 내 모든 사용자 입력은 자동으로 이스케이프 처리됨(예: {userInput})
         - Inspector Panel 등의 JSONB 편집기에도 <script> 삽입 시 sanitize-js를 통해 무해화
       - **CSRF (Cross-Site Request Forgery)**
         - 모든 상태 변경 요청(POST, PUT, DELETE 등)에 대해 CSRF 토큰 검사(Express csurf 미들웨어)
       - **권한 우회(Privilege Escalation)**
         - API 레벨에서 JWT Role Claim 검증(예: req.user.roles.includes('Ontology Admin'))
     - **취약점 스캐너**(OWASP ZAP) 자동화 스크립트 작성 → CI Pipeline에 통합
   - **배포 인프라**
     - **Container 기반 배포**
       - Frontend: React 앱 → Dockerfile 작성 → Nginx 서빙
       - Backend (OMS API): Node.js/TypeScript 앱 → Dockerfile 작성 → Express 서버
       - Taillwind CSS 빌드 결과물은 React 앱에 번들링되어 제공
     - **Kubernetes 배포**
       - **Namespace**: ontology-editor
       - **Deployments**:
         - frontend-deployment (Replica 3) → React 서비스
         - backend-deployment (Replica 3) → OMS API 서버
         - indexer-deployment (Replica 1) → IndexingService
         - graph-sync-deployment (Replica 1) → GraphSyncService
       - **Services**:
         - frontend-service (ClusterIP → Ingress)
         - backend-service (ClusterIP)
       - **Ingress**:
         - 도메인: onto.company.com
         - HTTPS 설정: Cert-Manager로 Let’s Encrypt 인증서 자동 갱신
     - **CI/CD 파이프라인** (GitHub Actions)
       - **빌드 단계**
         - checkout → npm ci → npm run lint → npm run test:unit
         - npm run build (React) → Docker 이미지 빌드 → docker push
         - npm run build:backend → Docker 이미지 빌드 → docker push
       - **스테이징 배포**
         - 브랜치 develop 푸시 시 트리거 → 스테이징(K8s) 네임스페이스에 배포 → Smoke Test
       - **운영 배포**
         - 브랜치 release/\* 또는 main에 Merge/Pull Request 시 트리거 → 프로덕션 배포 → Health Check → Canary Release(Optional)
     - **버전 태깅**
       - Semantic Versioning: v1.0.0, v1.1.0 등
       - GitHub Release 페이지에 릴리스 노트 자동 생성 (GitHub Action)

## **3. 시스템 아키텍처 설계**

아래 아키텍처 다이어그램은 React + BlueprintJS 기반 온톨로지 에디터를 포함한 전체 플랫폼 모듈 구조를 나타냄.

> 주의: 실제 다이어그램 이미지는 포함되지 않지만, 모듈 간 연동 관계를 상세히 설명함.

┌────────────────────────────────────────────────────────────────────────────────┐

│ Client (Browser) │

│ ┌────────────────────────────┐ ┌───────────────────────────────────────────┐ │

│ │ 1. Ontology Editor UI │──▶│ 2. OMS API Server (Node.js/Express) │ │

│ │ (React + BlueprintJS) │ │ ├── AuthModule (OAuth2/OIDC) │ │

│ │ │ │ ├── MetadataController (CRUD API) │ │

│ │ - CanvasArea.jsx │ │ ├── VersionController │ │

│ │ - Toolbox.jsx │ │ ├── AuditController │ │

│ │ - InspectorPanel.jsx │ │ ├── IndexingService (ElasticSearch) │ │

│ │ - CodeEditor.jsx (Monaco) │ │ ├── GraphSyncService (Neo4j) │ │

│ │ - VersionControl.jsx │ │ └── NotificationService (Kafka/Redis) │ │

│ │ - AuthWrapper.jsx │ └───────────────────────────────────────────┘ │

│ │ │ │

│ │ │ ┌───────────────────────────────────────────┐ │

│ │ │ │ 3. MetaStore DB (PostgreSQL) │ │

│ │ │ │ ├─ object_type table │ │

│ │ │ │ ├─ property table │ │

│ │ │ │ ├─ link_type table │ │

│ │ │ │ ├─ interface table │ │

│ │ │ │ ├─ action_type table │ │

│ │ │ │ └─ audit_log table │ │

│ │ │ └───────────────────────────────────────────┘ │

│ │ │ │

│ │ │ ┌───────────────────────────────────────────┐ │

│ │ │ │ 4. Indexing Service │ │

│ │ │ │ (ElasticSearch or Phonograph) │ │

│ │ │ │ └─ 빠른 검색, 필터링 제공 │ │

│ │ │ └───────────────────────────────────────────┘ │

│ │ │ │

│ │ │ ┌───────────────────────────────────────────┐ │

│ │ │ │ 5. Graph DB (Neo4j) │ │

│ │ │ │ └─ 그래프 탐색, 알고리즘 제공 │ │

│ │ │ └───────────────────────────────────────────┘ │

│ │ │ │

│ │ │ ┌───────────────────────────────────────────┐ │

│ │ │ │ 6. ETL/AI Workflow Engine │ │

│ │ │ │ (Spark, Airflow/Argo, Python Scripts) │ │

│ │ │ │ └─ 데이터 변환 및 AI 모델 학습/추론 │ │

│ │ │ └───────────────────────────────────────────┘ │

│ │ │ │

│ │ │ ┌───────────────────────────────────────────┐ │

│ │ │ │ 7. Notification Queue (Kafka or Redis) │ │

│ │ │ │ └─ 이벤트 버스 (메타데이터 변경, 색인, 동기화 등) │ │

│ │ │ └───────────────────────────────────────────┘ │

│ └────────────────────────────┘ │

└────────────────────────────────────────────────────────────────────────────────┘

### **3.1. 주요 컴포넌트 설명**

1. **Ontology Editor UI (Client Side)**
   - **기술 스택**: React (TypeScript) + BlueprintJS + BlueprintJS-icons + React Router + Zustand(또는 Redux Toolkit) 상태 관리
   - **폴더 구조** (예시):

src/

├─ components/

│ ├─ CanvasArea.tsx

│ ├─ Toolbox.tsx

│ ├─ InspectorPanel.tsx

│ ├─ CodeEditor.tsx

│ ├─ VersionControl.tsx

│ ├─ AuthWrapper.tsx

│ ├─ LoginForm.tsx

│ └─ Shared/

│ ├─ Button.tsx

│ ├─ Modal.tsx

│ ├─ IconPicker.tsx

│ └─ ColorPicker.tsx

├─ hooks/

│ ├─ useOntologyStore.ts

│ ├─ useAuth.ts

│ └─ useWebSocket.ts

├─ pages/

│ ├─ OntologyEditorPage.tsx

│ └─ LoginPage.tsx

├─ routes/

│ └─ AppRouter.tsx

├─ services/

│ ├─ api.ts

│ ├─ authService.ts

│ ├─ metadataService.ts

│ ├─ versionService.ts

│ ├─ indexingService.ts

│ └─ graphSyncService.ts

├─ utils/

│ ├─ constants.ts

│ ├─ helpers.ts

│ └─ types.ts

├─ App.tsx

└─ index.tsx

-
- **핵심 컴포넌트**:
  1. **CanvasArea.tsx**
     - **역할**:
       - BlueprintJS Overlay 위에 SVG 기반 Canvas 렌더링
       - React-Flow 또는 커스텀 D3 연동 가능하지만, 유지보수성과 BlueprintJS 호환성을 위해 SVG 직접 제어 권장
     - **기능**:
       - 노드(Node) 추가/삭제/이동/선택
       - 링크(Edge) 연결/삭제/선택
       - Zoom/Pan 이벤트 처리 (SVG viewBox 조정)
       - 선택된 노드를 클릭 시 InspectorPanel로 상태 전달 (상태 관리 훅 사용)
     - **Props & State**:

interface CanvasAreaProps {

ontologyData: OntologyData;

selectedNodeId: string | null;

onNodeSelect: (nodeId: string) => void;

onLinkSelect: (linkId: string) => void;

onCanvasClick: () => void;

}

const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

const [zoom, setZoom] = useState<number>(1);

-
- **이벤트 처리**:
  - onMouseDown, onMouseMove, onMouseUp → Pan 처리
  - onWheel → Zoom 처리 (배율 min 0.5, max 2)
  - onClick 빈 공간 클릭 시 선택 해제 → InspectorPanel 닫기
  - 노드/링크 클릭 시 개별 핸들러 호출 → InspectorPanel 열기

1. **Toolbox.tsx**
   - **역할**:
     - 좌측 Sidebar 역할
     - 탭별 노드/링크/검색 기능 제공
   - **기능**:
     - **Node 탭**: Object, Interface, Action Type 아이콘 리스트
     - **Link 탭**: Link Type 아이콘
     - **Search 탭**: 입력 필드 → 자동완성 검색(ElasticSearch 연동) → 결과 리스트 표시
   - **구현**:
     - BlueprintJS Tabs 컴포넌트로 탭 전환
     - 각 탭 내용은 BlueprintJS Icon + Button + InputGroup 조합
     - 검색 시 디바운스(300ms) 적용 → indexingService.search(query) 호출 → 결과 상태 저장 → 리스트 렌더
2. **InspectorPanel.tsx**
   - **역할**:
     - 우측에 슬라이딩 형태로 나타나는 상세 편집 패널
     - 노드/링크/Action/Interface 선택 시 해당 메타데이터 편집 UI 제공
   - **기능**:
     - **Metadata 탭**: Display Name, API Name, Description, Icon Picker, Color Picker, Visibility, Status 편집
     - **Properties 탭**: 속성 목록 테이블 + “Add Property” 버튼 → PropertyModal 열기
     - **Links 탭**: 해당 노드와 연결된 Link Type 리스트 + 삭제/편집 아이콘
     - **Help 탭**: 선택된 노드/링크 설명, 문서 링크, 툴팁 제공
   - **구현**:
     - BlueprintJS Drawer 컴포넌트 사용 (side=“right”, isOpen={Boolean(selectedNodeId)})
     - 내부 탭은 BlueprintJS Tab 컴포넌트로 구성
     - 테이블은 BlueprintJS HTMLTable 컴포넌트 사용 (속성 목록 렌더)
     - IconPicker, ColorPicker는 Shared 컴포넌트로 분리하여 재사용
3. **CodeEditor.tsx**
   - **역할**:
     - Monaco Editor를 통해 Action/Function 코드 편집
   - **기능**:
     - TypeScript 하이라이팅, 자동완성(LSP), 오류 표시
     - 우측 Security Rules JSON 편집기(간단한 JSON 에디터)
     - 하단 “Save” 버튼 → actionService.updateFunction(rid, functionBody) 호출 후 저장 알림
     - “Test” 버튼 → 샌드박스 Node 환경에서 간단 Unit Test 실행 (추후 확장)
   - **구현**:
     - react-monaco-editor 패키지 사용 → language="typescript", theme="vs-dark"
     - JSON 에디터는 Monaco Editor의 JSON 모드 사용
4. **VersionControl.tsx**
   - **역할**:
     - 화면 하단 고정 영역으로 현재 브랜치 정보 및 변경 사항 요약 표시
     - Change Set 생성, 목록, Merge/Conflict 해결 UI 제공
   - **기능**:
     - “Create Change Set” 버튼 → versionService.createChangeSet() 호출 → 새 Change Set 생성 → WebSocket으로 실시간 알림
     - Change Set 목록: BlueprintJS Menu 또는 Table로 렌더 → 클릭 시 상세 변경 내역(텍스트 차이, JSON 다이프) Modal로 표시
     - “Merge” 버튼 → versionService.mergeChangeSet(changeSetId) 호출 → 충돌 시 서버에서 409 Conflict 반환 → 충돌 해결 모달(ConflictResolver 컴포넌트) 오픈
   - **구현**:
     - 상태 관리: Zustand 사용하여 changeSetList, currentBranch, mergeConflicts 상태 전역 관리
     - WebSocket 또는 Socket.IO로 서버에서 버전 이벤트 수신 → UI 업데이트
5. **AuthWrapper.tsx**
   - **역할**:
     - 전체 애플리케이션을 감싸는 인증/인가 컴포넌트
     - 비로그인 시 LoginPage로 리디렉션, 로그인 완료 시 OntologyEditorPage 렌더
   - **기능**:
     - React Router PrivateRoute 형태로 구현 → 로그인 상태 확인 → 권한 검사 → 해당 페이지 접근 허용/차단
     - useAuth 훅으로 Keycloak 연동: 로그인, 토큰 갱신, 로그아웃 처리
   - **구현**:
     - @react-keycloak/web 라이브러리 사용 → ReactKeycloakProvider 설정
     - 권한 체크: keycloak.hasRealmRole('Ontology Admin') 등
6. **OMS API 서버 (Backend Side)**
   - **기술 스택**: Node.js (TypeScript) + Express + TypeORM (또는 Prisma) + Redis + Kafka(또는 내부 EventEmitter) + Bull(Queue)
   - **폴더 구조** (예시):

server/

├─ src/

│ ├─ controllers/

│ │ ├─ authController.ts

│ │ ├─ metadataController.ts

│ │ ├─ versionController.ts

│ │ ├─ auditController.ts

│ │ └─ healthController.ts

│ ├─ services/

│ │ ├─ authService.ts

│ │ ├─ objectService.ts

│ │ ├─ propertyService.ts

│ │ ├─ linkService.ts

│ │ ├─ interfaceService.ts

│ │ ├─ actionService.ts

│ │ ├─ versionService.ts

│ │ ├─ auditService.ts

│ │ ├─ indexingService.ts

│ │ └─ graphSyncService.ts

│ ├─ models/

│ │ ├─ ObjectType.ts

│ │ ├─ Property.ts

│ │ ├─ LinkType.ts

│ │ ├─ InterfaceEntity.ts

│ │ ├─ ActionType.ts

│ │ ├─ User.ts

│ │ └─ AuditLog.ts

│ ├─ repositories/

│ │ ├─ objectRepository.ts

│ │ ├─ propertyRepository.ts

│ │ ├─ linkRepository.ts

│ │ ├─ interfaceRepository.ts

│ │ ├─ actionRepository.ts

│ │ └─ auditRepository.ts

│ ├─ middlewares/

│ │ ├─ authMiddleware.ts

│ │ ├─ errorMiddleware.ts

│ │ ├─ validationMiddleware.ts

│ │ └─ rateLimiter.ts

│ ├─ utils/

│ │ ├─ logger.ts

│ │ ├─ kafkaProducer.ts

│ │ └─ constants.ts

│ ├─ config/

│ │ ├─ dbConfig.ts

│ │ ├─ redisConfig.ts

│ │ └─ index.ts

│ ├─ app.ts

│ └─ server.ts

├─ test/

│ ├─ unit/

│ └─ integration/

└─ Dockerfile

-
- **주요 모듈 설명**:
  - **AuthModule (authService.ts + authController.ts + authMiddleware.ts)**
    1. **역할**:
       - Keycloak OAuth2/OpenID Connect 연동
       - JWT Access Token 검증, 사용자 정보(User 엔터티) 조회/생성
    2. **구현**:
       - passport-keycloak 또는 keycloak-connect 라이브러리 사용
       - authMiddleware.ts: 모든 보호된 라우트 앞에 JWT 검증 미들웨어 적용
  - **MetadataController & Service**
    1. **역할**:
       - ObjectType, Property, LinkType, Interface, ActionType의 CRUD API 처리
    2. **구현**:
       - **objectService.ts**:
         - createObjectType(dto): 신규 ObjectType 생성 후 DB 저장 → Kafka ontology.object.created 이벤트 발행 → indexingService.indexObject(obj) 호출
         - updateObjectType(rid, dto, version): 버전 검사 후 업데이트 → AuditService 기록 → Kafka 이벤트 발행 → Indexing 및 GraphSync 트리거
         - deleteObjectType(rid): Soft Delete(필요 시) 또는 Hard Delete 후 이벤트 발행
       - **propertyService.ts**, **linkService.ts**, **interfaceService.ts**, **actionService.ts**도 유사 패턴
       - 각 서비스는 TypeORM(또는 Prisma) Repository를 활용하여 DB 연동
  - **VersionController & Service**
    1. **역할**:
       - Change Set 생성, 조회, Merge, Rollback, Conflict Resolution
    2. **구현**:
       - createChangeSet(userId, changes): DB에 Change Set 레코드 저장 → version_set 테이블에 변경 내역(JSONB) 삽입 → Kafka version.changeset.created 발행
       - mergeChangeSet(changeSetId): 해당 Change Set과 Master Branch 버전 비교 → 충돌 감지 로직 (버전 숫자 또는 ETag) → 충돌 없으면 Master에 머지 → 모든 관련 엔티티 업데이트 → Audit Log 기록 → Kafka 이벤트 발행 → 성공 응답
       - rollbackChangeSet(changeSetId): 해당 Change Set 이전 시점으로 복원 (Change Set 내역 순차 적용 역순으로 반영) → Audit Log 기록
  - **AuditController & Service**
    1. **역할**:
       - 모든 CRUD 이벤트를 audit_log 테이블에 기록 및 조회 API 제공
    2. **구현**:
       - auditService.logChange(entityType, entityRid, changeType, changedBy, changeDetail) → INSERT INTO audit_log ...
       - getAuditLogs(filterOptions) → 페이징된 감사 로그 반환
  - **IndexingService**
    1. **역할**:
       - Kafka 또는 내부 EventEmitter로부터 메타데이터 변경 이벤트 수신 → ElasticSearch 또는 Phonograph에 색인 수행
    2. **구현**:
       - Kafka Consumer 설정 → 각 이벤트 종류(ontology.object.created, ontology.link.updated 등) 구독
       - 색인 로직:
         - 해당 Object/Link 데이터를 조회 → ElasticSearch Client로 index({ index: 'object', id: rid, body: {...} })
         - 실패 시 3회 재시도 → 계속 실패 시 DevOps 팀 Slack 알림 및 DB에 index_status = 'failed' 업데이트
  - **GraphSyncService**
    1. **역할**:
       - Neo4j Full Sync 및 Incremental Sync 수행
    2. **구현**:
       - **Full Sync**:
         - 주기 스케줄러(CronJob 또는 Kubernetes CronJob) → graphSyncService.fullSync() 실행
         - PostgreSQL object_type, link_type 전체 조회 → Cypher 스크립트(MERGE (n:ObjectType {rid:$rid, name:$apiName, ...})) 실행
       - **Incremental Sync**:
         - Kafka version.changeset.merged 이벤트 수신 → 이벤트 Payload에 변경된 Entity 목록 포함
         - graphSyncService.incrementalSync(changedEntities) → 각 Entity별 Cypher MERGE 또는 DETACH DELETE 수행
         - 실패 시 Retry 로직 적용 → 실패 지속 시 알림
  - **NotificationService**
    1. **역할**:
       - Kafka Producer 사용 → 프런트엔드 WebSocket 푸시, Slack/Email 알림 전송
    2. **구현**:
       - 메타데이터 변경, 버전 Merge/Conflict 발생 시 Kafka에 메시지 발행
       - WebSocket 서버(Node.js + Socket.IO) 구동 → 클라이언트 연결 유지 → socket.emit('ontologyUpdated', payload)
- **Database (MetaStore DB)**
  - **PostgreSQL** (또는 Aurora)
  - **테이블 설계**:
    1. **object_type**

| **컬럼명**          | **타입**                 | **제약 조건**                  | **설명**                                              |
| ------------------- | ------------------------ | ------------------------------ | ----------------------------------------------------- |
| rid                 | UUID                     | PK, NOT NULL                   | 내부 고유 식별자                                      |
| id                  | VARCHAR(100)             | UNIQUE, NOT NULL               | 외부 노출용 식별자 (예: Employee)                     |
| display_name        | VARCHAR(200)             | NOT NULL                       | UI 표기용 이름                                        |
| plural_display_name | VARCHAR(200)             | NOT NULL                       | 복수형 UI 표기 (예: Employees)                        |
| description         | TEXT                     |                                | 객체 설명                                             |
| icon                | VARCHAR(100)             |                                | 아이콘 이름                                           |
| color               | VARCHAR(7)               |                                | 아이콘/노드 색상 (HEX)                                |
| groups              | TEXT[]                   |                                | 카테고리 라벨 배열                                    |
| api_name            | VARCHAR(200)             | NOT NULL                       | API 호출용 이름                                       |
| visibility          | VARCHAR(20)              | NOT NULL, DEFAULT ‘normal’     | UI 표시 우선순위 (prominent, normal, hidden)          |
| status              | VARCHAR(20)              | NOT NULL, DEFAULT ‘active’     | 온톨로지 개발 상태 (active, experimental, deprecated) |
| index_status        | VARCHAR(20)              | NOT NULL, DEFAULT ‘notStarted’ | 색인 상태 (success, failed, notStarted)               |
| writeback           | VARCHAR(20)              | NOT NULL, DEFAULT ‘enabled’    | 사용자 편집 활성화 여부 (enabled, disabled)           |
| created_by          | VARCHAR(100)             | NOT NULL                       | 생성자                                                |
| created_at          | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now()        | 생성 일자                                             |
| updated_by          | VARCHAR(100)             |                                | 최종 수정자                                           |
| updated_at          | TIMESTAMP WITH TIME ZONE |                                | 최종 수정 일자                                        |

1.
2. **property**

| **컬럼명**         | **타입**                 | **제약 조건**              | **설명**                                              |
| ------------------ | ------------------------ | -------------------------- | ----------------------------------------------------- |
| rid                | UUID                     | PK, NOT NULL               | 속성 고유 식별자                                      |
| object_rid         | UUID                     | FK → object_type.rid       | 속성이 속한 Object Type 식별자                        |
| api_name           | VARCHAR(200)             | NOT NULL                   | 속성 호출용 이름                                      |
| display_name       | VARCHAR(200)             | NOT NULL                   | UI 표기용 이름                                        |
| description        | TEXT                     |                            | 속성 설명                                             |
| base_type          | VARCHAR(20)              | NOT NULL                   | 데이터 타입 (string, integer, boolean, date, decimal) |
| is_title_key       | BOOLEAN                  | NOT NULL, DEFAULT false    | 대표값 여부                                           |
| is_primary_key     | BOOLEAN                  | NOT NULL, DEFAULT false    | 고유 식별자 여부                                      |
| value_format       | VARCHAR(100)             |                            | 값 형식 지정 (예: YYYY-MM-DD)                         |
| conditional_format | JSONB                    |                            | 조건부 강조 규칙                                      |
| render_hints       | TEXT[]                   |                            | UI 힌트 (searchable, sortable 등)                     |
| visibility         | VARCHAR(20)              | NOT NULL, DEFAULT ‘normal’ | UI 표시 우선순위                                      |
| status             | VARCHAR(20)              | NOT NULL, DEFAULT ‘active’ | 개발 상태                                             |
| created_by         | VARCHAR(100)             | NOT NULL                   | 생성자                                                |
| created_at         | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now()    | 생성 일자                                             |
| updated_by         | VARCHAR(100)             |                            | 최종 수정자                                           |
| updated_at         | TIMESTAMP WITH TIME ZONE |                            | 최종 수정 일자                                        |

1.
2. **link_type**

| **컬럼명**        | **타입**                 | **제약 조건**              | **설명**                                            |
| ----------------- | ------------------------ | -------------------------- | --------------------------------------------------- |
| rid               | UUID                     | PK, NOT NULL               | 관계 유형 고유 식별자                               |
| id                | VARCHAR(100)             | UNIQUE, NOT NULL           | 외부 노출용 식별자                                  |
| source_object_rid | UUID                     | FK → object_type.rid       | 출발 Object Type 식별자                             |
| target_object_rid | UUID                     | FK → object_type.rid       | 도착 Object Type 식별자                             |
| api_name          | VARCHAR(200)             | NOT NULL                   | 관계 호출용 이름                                    |
| description       | TEXT                     |                            | 관계 설명                                           |
| cardinality       | VARCHAR(20)              | NOT NULL                   | Cardinality (ONE_TO_ONE, ONE_TO_MANY, MANY_TO_MANY) |
| visibility        | VARCHAR(20)              | NOT NULL, DEFAULT ‘normal’ | UI 표시 우선순위                                    |
| status            | VARCHAR(20)              | NOT NULL, DEFAULT ‘active’ | 개발 상태                                           |
| created_by        | VARCHAR(100)             | NOT NULL                   | 생성자                                              |
| created_at        | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now()    | 생성 일자                                           |
| updated_by        | VARCHAR(100)             |                            | 최종 수정자                                         |
| updated_at        | TIMESTAMP WITH TIME ZONE |                            | 최종 수정 일자                                      |

1.
2. **interface**

| **컬럼명**     | **타입**                 | **제약 조건**              | **설명**                       |
| -------------- | ------------------------ | -------------------------- | ------------------------------ |
| rid            | UUID                     | PK, NOT NULL               | 인터페이스 고유 식별자         |
| display_name   | VARCHAR(200)             | NOT NULL                   | UI 표기용 이름                 |
| description    | TEXT                     |                            | 인터페이스 설명                |
| icon           | VARCHAR(100)             |                            | 아이콘                         |
| color          | VARCHAR(7)               |                            | 아이콘/노드 색상 (HEX)         |
| implemented_by | VARCHAR(100)[]           |                            | 구현된 Object Type 목록 (배열) |
| status         | VARCHAR(20)              | NOT NULL, DEFAULT ‘active’ | 개발 상태                      |
| visibility     | VARCHAR(20)              | NOT NULL, DEFAULT ‘normal’ | UI 표시 우선순위               |
| created_by     | VARCHAR(100)             | NOT NULL                   | 생성자                         |
| created_at     | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now()    | 생성 일자                      |
| updated_by     | VARCHAR(100)             |                            | 최종 수정자                    |
| updated_at     | TIMESTAMP WITH TIME ZONE |                            | 최종 수정 일자                 |

1.
2. **action_type**

| **컬럼명**     | **타입**                 | **제약 조건**              | **설명**                             |
| -------------- | ------------------------ | -------------------------- | ------------------------------------ |
| rid            | UUID                     | PK, NOT NULL               | Action Type 고유 식별자              |
| id             | VARCHAR(100)             | UNIQUE, NOT NULL           | 외부 노출용 식별자                   |
| display_name   | VARCHAR(200)             | NOT NULL                   | UI 표기용 이름                       |
| description    | TEXT                     |                            | Action 설명                          |
| api_name       | VARCHAR(200)             | NOT NULL                   | Action 호출용 이름                   |
| input_schema   | JSONB                    |                            | 입력 스키마                          |
| output_schema  | JSONB                    |                            | 출력 스키마                          |
| security_rules | JSONB                    |                            | 역할 기반 권한 정의                  |
| function_body  | TEXT                     |                            | 실제 비즈니스 로직 코드 (TypeScript) |
| status         | VARCHAR(20)              | NOT NULL, DEFAULT ‘active’ | 개발 상태                            |
| visibility     | VARCHAR(20)              | NOT NULL, DEFAULT ‘normal’ | UI 표시 우선순위                     |
| created_by     | VARCHAR(100)             | NOT NULL                   | 생성자                               |
| created_at     | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now()    | 생성 일자                            |
| updated_by     | VARCHAR(100)             |                            | 최종 수정자                          |
| updated_at     | TIMESTAMP WITH TIME ZONE |                            | 최종 수정 일자                       |

1.
2. **audit_log**

| **컬럼명**       | **타입**                 | **제약 조건**           | **설명**                                                                            |
| ---------------- | ------------------------ | ----------------------- | ----------------------------------------------------------------------------------- |
| id               | SERIAL                   | PK, NOT NULL            | 감사 로그 고유 식별자                                                               |
| entity_type      | VARCHAR(50)              | NOT NULL                | 변경 대상 엔티티 종류 (object_type, property, link_type, interface, action_type 등) |
| entity_rid       | UUID                     | NOT NULL                | 변경된 엔티티의 RID                                                                 |
| change_type      | VARCHAR(10)              | NOT NULL                | 변경 종류 (CREATE, UPDATE, DELETE)                                                  |
| changed_by       | VARCHAR(100)             | NOT NULL                | 변경자 (사용자 ID)                                                                  |
| change_timestamp | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now() | 변경 시각                                                                           |
| change_detail    | JSONB                    |                         | 변경 전/후 스냅샷 (예: { "before": {...}, "after": {...} })                         |

-
- **커밋 포인트**
  1. DB 마이그레이션 파일은 server/src/migrations/ 디렉토리에 작성 → npm run migration:generate → npm run migration:run로 커밋
  2. 각 Entity 모델(models/\*.ts) 또는 Prisma Schema(prisma/schema.prisma) 변경 시 반드시 마이그레이션 파일 생성 후 커밋

1. **색인 서비스 (ElasticSearch 또는 Phonograph)**
   - **기술 스택**:
     1. ElasticSearch 7.x 이상 (Docker Compose 또는 AWS ElasticSearch Service)
     2. Node.js IndexingService (Express의 서브 서비스)
     3. Kafka (또는 RabbitMQ, Redis Streams) = 메시지 버스
   - **구현**:
     1. **Kafka Producer (server/utils/kafkaProducer.ts)**

import { Kafka } from 'kafkajs';

const kafka = new Kafka({ brokers: [process.env.KAFKA_BROKER] });

const producer = kafka.producer();

export async function initProducer() {

await producer.connect();

}

export async function sendIndexEvent(topic: string, payload: any) {

await producer.send({

topic,

messages: [{ value: JSON.stringify(payload) }],

});

}

1.
2. **IndexingService (server/services/indexingService.ts)**

import { Client as ESClient } from '@elastic/elasticsearch';

import { Kafka } from 'kafkajs';

const esClient = new ESClient({ node: process.env.ELASTIC_URL });

const kafka = new Kafka({ brokers: [process.env.KAFKA_BROKER] });

export class IndexingService {

private consumer;

constructor() {

this.consumer = kafka.consumer({ groupId: 'indexing-group' });

}

async init() {

await this.consumer.connect();

await this.consumer.subscribe({ topic: 'ontology.object.created' });

await this.consumer.subscribe({ topic: 'ontology.object.updated' });

// 추가 토픽 구독

await this.consumer.run({ eachMessage: this.handleMessage.bind(this) });

}

async handleMessage({ topic, message }) {

const payload = JSON.parse(message.value.toString());

switch (topic) {

case 'ontology.object.created':

case 'ontology.object.updated':

await this.indexObject(payload);

break;

// link, action, interface 등 처리

}

}

async indexObject(obj: any) {

try {

await esClient.index({

index: 'object',

id: obj.rid,

body: {

object_id: obj.id,

display_name: obj.display_name,

groups: obj.groups,

status: obj.status,

visibility: obj.visibility,

properties: obj.properties,

link_count: obj.link_count,

},

});

} catch (err) {

// 색인 실패 시 Retry 또는 DB 상태 업데이트

console.error('Indexing failed for object:', obj.rid, err);

}

}

}

1.
2. **ElasticSearch 인덱스 매핑 예시 (PUT /object 인덱스)**

{

"mappings": {

"properties": {

"object_id": { "type": "keyword" },

"display_name": { "type": "text", "analyzer": "standard" },

"groups": { "type": "keyword" },

"status": { "type": "keyword" },

"visibility": { "type": "keyword" },

"properties": { "type": "keyword" },

"link_count": { "type": "integer" }

}

}

}

1.
2. **Graph DB (Neo4j)**
   - **기술 스택**:
     1. Neo4j 4.x 이상 (Docker 또는 AuraDB)
     2. Node.js Neo4j Driver (neo4j-driver)
   - **구현**:
     1. **GraphSyncService (server/services/graphSyncService.ts)**

import neo4j from 'neo4j-driver';

import { getRepository } from 'typeorm';

import { ObjectType } from '../models/ObjectType';

import { LinkType } from '../models/LinkType';

export class GraphSyncService {

private driver;

constructor() {

this.driver = neo4j.driver(

process.env.NEO4J_URI,

neo4j.auth.basic(process.env.NEO4J_USER, process.env.NEO4J_PASSWORD)

);

}

async fullSync() {

const session = this.driver.session();

try {

// ObjectType 전체 조회

const objects = await getRepository(ObjectType).find({ relations: ['properties','links'] });

for (const obj of objects) {

await session.run(

`MERGE (n:ObjectType {rid: $rid})

SET n.id = $id, n.display_name = $display_name, n.status = $status, n.visibility = $visibility`,

{

rid: obj.rid,

id: obj.id,

display_name: obj.displayName,

status: obj.status,

visibility: obj.visibility

}

);

}

// LinkType 전체 조회 후 관계 생성

const links = await getRepository(LinkType).find();

for (const link of links) {

await session.run(

`MATCH (src:ObjectType {rid: $srcRid}), (tgt:ObjectType {rid: $tgtRid})

MERGE (src)-[r:RELATION {rid: $rid}]->(tgt)

SET r.api_name = $apiName, r.cardinality = $cardinality`,

{

rid: link.rid,

srcRid: link.sourceObjectRid,

tgtRid: link.targetObjectRid,

apiName: link.apiName,

cardinality: link.cardinality

}

);

}

} catch (err) {

console.error('Full Sync Error:', err);

} finally {

await session.close();

}

}

async incrementalSync(changedEntities: { type: string; rid: string }[]) {

const session = this.driver.session();

try {

for (const ent of changedEntities) {

if (ent.type === 'object_type') {

const obj = await getRepository(ObjectType).findOne(ent.rid);

if (obj) {

await session.run(

`MERGE (n:ObjectType {rid: $rid})

SET n.id = $id, n.display_name = $display_name, n.status = $status, n.visibility = $visibility`,

{

rid: obj.rid,

id: obj.id,

display_name: obj.displayName,

status: obj.status,

visibility: obj.visibility

}

);

} else {

// 삭제된 경우

await session.run(

`MATCH (n:ObjectType {rid: $rid}) DETACH DELETE n`,

{ rid: ent.rid }

);

}

} else if (ent.type === 'link_type') {

const link = await getRepository(LinkType).findOne(ent.rid);

if (link) {

// 관계 MERGE

await session.run(

`MATCH (src:ObjectType {rid: $srcRid}), (tgt:ObjectType {rid: $tgtRid})

MERGE (src)-[r:RELATION {rid: $rid}]->(tgt)

SET r.api_name = $apiName, r.cardinality = $cardinality`,

{

rid: link.rid,

srcRid: link.sourceObjectRid,

tgtRid: link.targetObjectRid,

apiName: link.apiName,

cardinality: link.cardinality

}

);

} else {

// 삭제된 관계

await session.run(

`MATCH ()-[r:RELATION {rid: $rid}]-() DELETE r`,

{ rid: ent.rid }

);

}

}

// Interface, Action 등 추가 구현

}

} catch (err) {

console.error('Incremental Sync Error:', err);

} finally {

await session.close();

}

}

}

1.
2. **Sync 트리거**
   - 서버 부팅 시 graphSyncService.fullSync() 호출 (초기 데이터 동기)
   - Kafka version.changeset.merged 이벤트 구독 → incrementalSync() 호출
   - Neo4j Sync 실패 시 3회 재시도 → 실패 시 Slack/Email 알림
3. **ETL/AI 워크플로우 엔진**
   - **기술 스택**:
     1. Apache Spark (PySpark + Spark MLlib)
     2. Airflow (또는 Argo Workflows)
     3. Python 스크립트
   - **역할**:
     1. 온톨로지 객체를 활용한 데이터 변환 파이프라인 (예: CSV → 정제된 JSON → RDB 적재)
     2. AI 모델 (수요 예측, 이상 탐지) 학습/추론
   - **구현**:
     1. **Airflow DAG 정의**

from airflow import DAG

from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

from airflow.operators.python import PythonOperator

from datetime import datetime, timedelta

default_args = {

'owner': 'airflow',

'depends_on_past': False,

'email_on_failure': True,

'email': ['data-team@company.com'],

'retries': 1,

'retry_delay': timedelta(minutes=5)

}

dag = DAG(

'ontology_data_pipeline',

default_args=default_args,

schedule_interval='@daily',

start_date=datetime(2025, 1, 1),

catchup=False

)

def fetch_ontology_schema(\*\*kwargs):

import requests

response = requests.get('https://onto.company.com/api/ontology-schema')

schema = response.json()

# S3 또는 HDFS에 저장

with open('/opt/airflow/data/ontology_schema.json', 'w') as f:

json.dump(schema, f)

t1 = PythonOperator(

task_id='fetch_ontology_schema',

python_callable=fetch_ontology_schema,

dag=dag

)

t2 = SparkSubmitOperator(

task_id='spark_data_transform',

application='/opt/airflow/scripts/data_transform.py',

name='DataTransform',

conn_id='spark_default',

dag=dag

)

t3 = SparkSubmitOperator(

task_id='spark_model_train',

application='/opt/airflow/scripts/model_train.py',

name='ModelTrain',

conn_id='spark_default',

dag=dag

)

t1 >> t2 >> t3

1.
2. **PySpark 변환 스크립트 (data_transform.py)**

from pyspark.sql import SparkSession

import json

spark = SparkSession.builder.appName('OntoDataTransform').getOrCreate()

# 온톨로지 스키마 로드

with open('/opt/airflow/data/ontology_schema.json', 'r') as f:

schema = json.load(f)

# CSV 데이터 로드

df = spark.read.csv('/data/input/data.csv', header=True)

# 온톨로지 기반 매핑

# 예: schema['objectTypes']를 참조하여 DataFrame 컬럼 매핑/정규화 로직 구현

# …

# 결과 저장 (Parquet 또는 JSON)

df.write.mode('overwrite').parquet('/data/output/transformed_data.parquet')

spark.stop()

1.
2. **PySpark 모델 학습 스크립트 (model_train.py)**

from pyspark.sql import SparkSession

from pyspark.ml.feature import VectorAssembler

from pyspark.ml.regression import RandomForestRegressor

spark = SparkSession.builder.appName('OntoModelTrain').getOrCreate()

# 정제된 데이터 로드

df = spark.read.parquet('/data/output/transformed_data.parquet')

# 피처 벡터 생성

featureCols = ['feature1', 'feature2', 'feature3']

assembler = VectorAssembler(inputCols=featureCols, outputCol='features')

data = assembler.transform(df)

# 모델 학습 (예: 수요 예측)

rf = RandomForestRegressor(featuresCol='features', labelCol='label', numTrees=50)

model = rf.fit(data)

# 모델 저장 (MLflow 또는 HDFS)

model.write().overwrite().save('/models/onto_demand_predictor')

spark.stop()

## **4. UI/UX 상세 설계**

### **4.1. 메인 화면 구성**

1. **헤더(Header) 영역** (상단 60px)
   - **좌측**: 로고 및 프로젝트 명칭 “OntoDesigner” (BlueprintJS Navbar 컴포넌트 사용)
   - **중앙**: 글로벌 네비게이션 메뉴 (BlueprintJS Tabs 또는 Navbar.Group)
     - Ontology
     - Version Control
     - Access Control
     - Help
     - Settings (향후 확장)
   - **우측**:
     - 사용자 프로필: Avatar (BlueprintJS UserMenu), 드롭다운으로 “Profile”, “Settings”, “Logout” 메뉴
     - 알림 아이콘: 변경 이벤트(새 ChangeSet, 충돌 발생 등) 표시 → 클릭 시 Notification Panel 열림
2. **사이드바(Sidebar) / 툴박스(Toolbox)** (좌측 240px 폭)
   - **탭 형태** (BlueprintJS Tabs)
     - **Node 탭**
       - Object Type, Interface, Action Type 등 드래그 가능한 아이콘 목록 (BlueprintJS Icon + Draggable 라이브러리 사용)
     - **Link 탭**
       - 일반 관계(Link Type), 집합 관계(Set Relation) 등 아이콘
     - **Search 탭**
       - 검색 입력 필드 (BlueprintJS InputGroup) + 필터 아이콘 (BlueprintJS Button + Popover)
       - 검색 결과: React Virtualized List 사용 → 다수 결과 빠르게 스크롤 가능
   - **아이콘**
     - **Object Type**: 정사각형 모양 + 대표 아이콘(예: BlueprintIconsEnum.PANEL_TABLE)
     - **Interface**: 육각형 모양 (커스텀 SVG 또는 CSS) + 아이콘 (예: BlueprintIconsEnum.LAYERS)
     - **Action**: 원형 모양 + 기어 아이콘 (BlueprintIconsEnum.COG)
     - **Link**: 실선 화살표 아이콘 (BlueprintIconsEnum.ARROW_RIGHT)
3. **캔버스(Canvas)** (메인 영역)
   - **배경**: 50px 간격 그리드 (SVG <pattern> 사용)
   - **줌/팬**:
     - 컨트롤 버튼: 우측 상단에 BlueprintJS ButtonGroup으로 Zoom In, Zoom Out, Reset Zoom
     - 마우스 휠로 Zoom 단계 조정 (0.5x ~ 2x)
     - 마우스 드래그로 Pan (SVG transform 속성 변경)
   - **노드(Node)**
     - **Object Node**:
       - div 요소 대신 SVG <g> 그룹으로 구성 → SVG <rect> 배경 + <text>로 Display Name, 속성 요약
       - 클릭 시 onNodeClick(nodeId) 호출 → InspectorPanel 오픈
       - 우클릭 시 BlueprintJS Menu 팝업 (Rename, Delete, Lock/Unlock)
     - **Interface Node**:
       - 육각형 SVG <polygon> + <text>로 Display Name
       - 클릭/우클릭 이벤트 동일 처리
     - **Action Node**:
       - SVG <circle> + <text>로 Action 이름
       - 클릭 시 InspectorPanel 내 Code 탭으로 스크롤, CodeEditor 팝업 오픈
   - **링크(Edge)**
     - SVG <path>로 선 그리기 (Bezier Curve) → marker-end 속성으로 Arrowhead 표시
     - 라벨: SVG <text> (Edge 중간 위치) → 상태별 색상(파랑/노랑/회색)
     - 클릭 시 onLinkClick(linkId) 호출 → InspectorPanel 오픈
4. **인스펙터 패널(Inspector Panel)** (우측 300px 폭, 숨김 가능)
   - **컴포넌트**: BlueprintJS Drawer
     - isOpen={Boolean(selectedNodeId)}
     - onClose={() => onDeselect()}
   - **구조**:
     - **Tabs**: BlueprintJS Tabs (Metadata, Properties, Links, Help)
       - **Metadata 탭**
         - BlueprintJS FormGroup + InputGroup/TextArea로 Display Name, API Name, Description 입력
         - IconPicker 컴포넌트: BlueprintJS Icon 목록 렌더 → 선택 시 icon 저장
         - ColorPicker 컴포넌트: react-color SketchPicker 사용 → HEX 코드 저장
         - Select 컴포넌트(BlueprintJS)로 Visibility, Status 선택
         - MultiSelect 컴포넌트(BlueprintJS)로 Groups 관리
         - “Save Metadata” 버튼 (BlueprintJS Button intent="primary") → metadataService.updateObjectType() 호출
       - **Properties 탭**
         - BlueprintJS HTMLTable로 속성 리스트: 컬럼 → Property Name, Type, Is Title Key, Is Primary Key, Visibility, Status, Actions(Edit/Delete)
         - “Add Property” 버튼 → PropertyModal 오픈
           - PropertyModal.tsx: BlueprintJS Dialog
             - Form Fields: Property Name (InputGroup), Base Type (Select), Title Key (Checkbox), Primary Key (Checkbox), Visibility (Select), Status (Select), Value Format (InputGroup), Conditional Formatting (monaco-editor JSON 모드), Render Hints (MultiSelect)
             - “Save” → metadataService.createProperty(objectRid, dto) 호출 → 테이블 리로드
       - **Links 탭**
         - BlueprintJS HTMLTable로 Link 목록: 컬럼 → Relationship Label, Cardinality, Direction, Visibility, Status, Actions(Edit/Delete)
         - 편집 아이콘 클릭 → LinkModal 오픈 (BlueprintJS Dialog)
           - Fields: Source Object (고정), Target Object (Select), API Name, Cardinality, Direction (Select), Visibility, Status
           - “Save” → metadataService.updateLinkType(rid, dto) 호출 → 테이블 리로드
       - **Help 탭**
         - 선택된 노드/링크에 대한 문서화된 도움말 표시 → Markdown 렌더러 사용 (react-markdown)
         - 툴팁 링크, 문서 URL 버튼
5. **버전 관리 패널(Version Control Panel)** (하단 40px 고정)
   - **컴포넌트**: BlueprintJS Navbar 하단 고정 또는 React Portal을 사용하여 메인 화면 위에 고정 렌더
   - **내용**:
     - 좌측: 현재 체크아웃된 브랜치 이름(useVersionStore.currentBranch)
     - 중앙: 변경사항 개수 (예: “3 changes pending”)
     - 우측:
       - “Create Change Set” 버튼 (Button intent="success") → versionService.createChangeSet() 호출
       - “Merge” 버튼 (Button intent="primary") → versionService.mergeChangeSet() 호출 → 충돌 시 Conflict Resolver Dialog open
       - “Rollback” 버튼 (Button intent="warning") → versionService.getChangeSets() → 목록 Modal 오픈 → 선택 후 versionService.rollbackChangeSet(id) 호출
6. **검색(Search) 기능**
   - **컴포넌트**: Sidebar Search 탭 내
   - **구현**:
     - BlueprintJS InputGroup + Button → 디바운스 적용 (lodash.debounce) → indexingService.search({ query, type }) 호출
     - 검색 결과: React Virtualized List로 렌더 (결과별 아이콘 + 이름 + 그룹 정보 표시)
     - 리스트 항목 클릭 시 CanvasArea.centerAndHighlight(id) 호출 → Canvas 중앙에 포커싱, 하이라이트 효과 적용(노드 외각 색상 일시 변경)

### **4.2. 주요 사용자 흐름(User Flows)**

1. **새 Object Type 생성**
   1. Sidebar → Node 탭 → Object 아이콘 드래그 → Canvas에 드롭
   2. CreateObjectModal 열림 → Display Name, API Name, Description, Icon, Color, Groups, Visibility, Status 입력
   3. “Create” 클릭 → metadataService.createObjectType(dto) 호출 (POST /api/object-type) → 성공 시 CanvasArea에서 노드 렌더
   4. Inspector Panel 열기: 새로 생성된 노드를 클릭 → InspectorPanel의 Metadata 탭에서 추가 수정 가능
   5. 속성 추가: InspectorPanel → Properties 탭 → “Add Property” 클릭 → PropertyModal 열림 → 속성 입력 → “Save” 클릭 → metadataService.createProperty(objectRid, dto) 호출 → InspectorPanel 속성 목록 업데이트
2. **Property 추가/편집**
   1. Canvas → Node 클릭 → InspectorPanel 열림 → Properties 탭 선택
   2. “Add Property” 버튼 클릭 → PropertyModal 오픈
      - Fields: Name, Base Type, Title Key, Primary Key, Visibility, Status, Value Format, Conditional Formatting, Render Hints
   3. “Save” 클릭 → metadataService.createProperty() 호출 (POST /api/property) → 성공 시 속성 목록에 항목 추가
   4. 속성 편집 시 속성 리스트의 Edit 아이콘 클릭 → 속성 인라인 에디터 또는 PropertyModal 호출 → metadataService.updateProperty(rid, dto) (PUT /api/property/:rid) 호출 → 목록 업데이트
   5. 속성 삭제 시 Delete 아이콘 클릭 → Confirm Dialog → metadataService.deleteProperty(rid) (DELETE /api/property/:rid) 호출 → 목록에서 제거
3. **Link Type 정의 (객체 간 관계 생성)**
   1. Sidebar → Link 탭 → Link 아이콘 클릭 → Canvas 상 Source Node 클릭 → Target Node 클릭 → CreateLinkModal 호출
   2. Modal → Cardinality(ONE_TO_MANY 등), API Name, Description, Direction(Unidirectional/Bidirectional), Visibility, Status 입력
   3. “Save” 클릭 → metadataService.createLinkType(dto) 호출 (POST /api/link-type) → 성공 시 CanvasArea에 화살표 렌더
   4. 링크를 클릭 → InspectorPanel 열림 → Metadata 탭에서 수정 또는 Properties 탭에서 삭제 가능
4. **Action/Function 정의**
   1. Sidebar → Node 탭 → Action 아이콘 드래그 → Canvas 드롭 → CreateActionModal 호출
   2. Modal → Display Name, API Name, Description, Input Schema(JSON), Output Schema(JSON), Security Rules(JSON) 입력 → “Create” 클릭 → metadataService.createActionType(dto) 호출 (POST /api/action-type) → CanvasArea에 원형 노드 렌더
   3. Canvas → Action Node 클릭 → InspectorPanel 열림 → “Code” 탭 선택 → CodeEditor 팝업으로 전환 → TypeScript 코드 작성 → “Save” 클릭 → metadataService.updateActionType(rid, { function_body }) 호출 (PUT /api/action-type/:rid)
   4. “Test” 버튼 클릭 → Sandbox 환경에서 간단한 Unit Test 실행 → 결과 로그 표시 → 필요 시 코드 수정
5. **버전 관리 작업 흐름**
   1. 사용자가 에디팅을 시작하면 Zustand의 versionStore.currentChangeSet에 임시 Change Set 객체 생성 → “ChangeSet A”라는 이름 지정(자동 생성)
   2. 5분 경과 또는 사용자가 “Save Change Set” 버튼 클릭 시 → versionService.createChangeSet() 호출 → DB에 Change Set 레코드 커밋 → Kafka version.changeset.created 이벤트 발생
   3. 다른 사용자가 같은 Object 수정 시 → Locking 로직에 의해 “현재 가 편집 중” 알림 → 충돌 방지
   4. 작업 완료 후 “Merge” 버튼 클릭 → versionService.mergeChangeSet(currentChangeSetId) 호출 → 서버에서 충돌 검사
      - 충돌 없으면 Master 브랜치에 Merge → Kafka version.changeset.merged 이벤트 발생 → GraphSyncService에서 Incremental Sync 수행
      - 충돌 발생 시 → 서버 409 반환 → UI에서 ConflictResolver Dialog 열림 → A와 B의 변경 내용을 Side-by-Side로 Diff → 사용자가 Merge 로직 직접 선택 → “Resolve & Merge” 클릭 → versionService.resolveConflictAndMerge() 호출
   5. Merge 완료 시 “Merge Successful” Toast 알림 및 버전 제어 패널에서 Change Set 상태 “merged”로 업데이트
6. **검색 및 탐색**
   1. Sidebar → Search 탭 클릭 → 검색어 입력 → 디바운스 (300ms) 후 indexingService.search({ query, type }) 호출
   2. 검색 결과 리스트 → React Virtualized List로 렌더 → 각 아이템: 아이콘 + 이름 + 그룹 정보
   3. 결과 클릭 시 → CanvasArea.centerAndHighlight(id) 호출 → Canvas 중앙 포커싱 + 노드 잠시 하이라이트 (스타일 변경)

### **4.3. 화면별 와이어프레임 예시 (텍스트 설명)**

1. **캔버스 화면**
   - **헤더 (상단 60px)**
     - 왼쪽: 로고(“OntoDesigner”)
     - 중앙: 탭(‘Ontology’, ‘Version Control’, ‘Access Control’, ‘Help’)
     - 오른쪽: 프로필 Avatar, 알림 아이콘
   - **사이드바 (좌측 240px)**
     - 탭 메뉴(노드, 링크, 검색)
     - 각 탭별 내용 영역:
       - Node 탭: Object/Interface/Action 아이콘 + 드래그 안내 툴팁
       - Link 탭: Link 아이콘 + 드래그 안내 툴팁
       - Search 탭: 검색 입력 필드 + 결과 리스트
   - **메인 캔버스 (나머지 영역)**
     - 그리드 배경(50px 간격)
     - 노드(Node) 및 링크(Edge) 렌더
     - 우측 상단 Zoom 컨트롤(± 버튼, Reset)
   - **인스펙터 패널 (우측 300px, 숨김 가능)**
     - 슬라이딩 형태로 나타남
     - 탭(‘Metadata’, ‘Properties’, ‘Links’, ‘Help’) + 내부 폼/테이블
   - **버전 관리 바 (하단 40px 고정)**
     - 왼쪽: 브랜치 이름
     - 중앙: 변경사항 개수 (“3 changes pending”)
     - 오른쪽: ‘Create Change Set’, ‘Merge’, ‘Rollback’ 버튼
2. **속성 생성 모달 (PropertyModal)**
   - **모달 상단 (BlueprintJS Dialog)**
     - 제목: “Create Property” 또는 “Edit Property”
   - **폼 필드**
     - Property Name (InputGroup, placeholder: “e.g., fullName”)
     - Base Type (Select with options: string, integer, boolean, date, decimal)
     - Is Title Key (Checkbox)
     - Is Primary Key (Checkbox)
     - Visibility (Select: prominent, normal, hidden)
     - Status (Select: active, experimental, deprecated)
     - Value Formatting (InputGroup, placeholder: “e.g., YYYY-MM-DD”)
     - Conditional Formatting (MonacoEditor JSON 모드, height: 120px)
     - Render Hints (MultiSelect with options: searchable, sortable, filterable)
   - **모달 하단**
     - ButtonGroup: ‘Save’ (intent="primary"), ‘Cancel’ (intent="none")
3. **Link 생성 모달 (LinkModal)**
   - **모달 상단**
     - 제목: “Create Link” 또는 “Edit Link”
   - **폼 필드**
     - Source Object (자동 입력, 비활성화 된 InputGroup)
     - Target Object (Select 드롭다운: Object Type 목록)
     - API Name (InputGroup)
     - Cardinality (Select: ONE_TO_ONE, ONE_TO_MANY, MANY_TO_MANY)
     - Direction (Select: Unidirectional, Bidirectional)
     - Visibility (Select: prominent, normal, hidden)
     - Status (Select: active, experimental, deprecated)
     - Description (TextArea)
   - **모달 하단**
     - ButtonGroup: ‘Save’ (intent="primary"), ‘Cancel’ (intent="none")
4. **Action 코드 편집기 팝업 (CodeEditor)**
   - **헤더 영역**
     - Action 이름: 큰 텍스트
     - 입력 스키마 요약: “Input: { employeeId: string }”
     - 출력 스키마 요약: “Output: { success: boolean }”
   - **본체 영역**
     - 좌측: Monaco Editor (TypeScript 모드, theme: vs-dark, height: 400px, width: 70%)
     - 우측: Security Rules JSON 에디터 (Monaco Editor JSON 모드, height: 400px, width: 25%)
   - **하단**
     - ButtonGroup: ‘Save’ (intent="primary"), ‘Test’ (intent="warning"), ‘Cancel’ (intent="none")

## **5. 데이터 모델 설계**

### **5.1. ERD (Entity-Relationship Diagram) 개요**

┌───────────────────┐ ┌───────────────────┐

│ object_type │◀───────│ property │

│ (rid PK, id, ...) │ 1 N│(rid PK, object_rid FK, base_type, ...)│

└───────────────────┘ └───────────────────┘

│ ▲

│ │

│ │

│ │

│ │

│ │ ┌───────────────────┐

│ └───────▶│ link_type │

│ N 1 │(rid PK, source_object_rid FK, target_object_rid FK, ...)│

│ └───────────────────┘

│

│

│ 1

└────▶┌───────────────────┐

│ interface │

│(rid PK, display_name, implemented_by[], ...)│

└───────────────────┘

┌───────────────────┐ ┌───────────────────┐

│ action_type │ │ audit_log │

│(rid PK, id, ...) │ │(id PK, entity_type, entity_rid, ...)│

└───────────────────┘ └───────────────────┘

▲ ▲

│ │

│ └────────────▶│ (연결: Action 실행 시 변경 이력 연결)

- **object_type ↔︎ property (1:N)**
  - 하나의 Object Type은 여러 Property를 가질 수 있음.
- **object_type ↔︎ link_type (1:N 출발 / 1:N 도착)**
  - 하나의 Object Type은 여러 Link Type의 출발지/도착지가 될 수 있음.
- **interface ↔︎ object_type (N:M)**
  - 여러 Object Type이 하나의 Interface를 구현할 수 있음(implemented_by 배열로 관리).
- **action_type**
  - Object Type과 직접 연결되지는 않으나 Action 실행 시 특정 Object Type의 속성에 접근하거나, Object 간 관계를 조회하는 로직을 포함.
- **audit_log**
  - 모든 Entity(object_type, property, link_type, interface, action_type)의 변경 이벤트를 기록.

### **5.2. 주요 테이블 스키마 상세**

### **5.2.1. object_type 테이블**

| **컬럼명**          | **데이터 타입**          | **제약 조건**                  | **설명**                                     |
| ------------------- | ------------------------ | ------------------------------ | -------------------------------------------- |
| rid                 | UUID                     | PK, NOT NULL                   | 내부 고유 식별자                             |
| id                  | VARCHAR(100)             | UNIQUE, NOT NULL               | 외부 노출용 식별자 (예: Employee)            |
| display_name        | VARCHAR(200)             | NOT NULL                       | UI 표기용 이름                               |
| plural_display_name | VARCHAR(200)             | NOT NULL                       | 복수형 UI 표기 (예: Employees)               |
| description         | TEXT                     |                                | 객체 설명                                    |
| icon                | VARCHAR(100)             |                                | UI 아이콘 식별자                             |
| color               | VARCHAR(7)               |                                | 아이콘/노드 색깔 (HEX)                       |
| groups              | TEXT[]                   |                                | 카테고리 라벨 배열                           |
| api_name            | VARCHAR(200)             | NOT NULL                       | API 호출용 이름                              |
| visibility          | VARCHAR(20)              | NOT NULL, DEFAULT ‘normal’     | UI 표시 우선순위 (prominent, normal, hidden) |
| status              | VARCHAR(20)              | NOT NULL, DEFAULT ‘active’     | 개발 상태 (active, experimental, deprecated) |
| index_status        | VARCHAR(20)              | NOT NULL, DEFAULT ‘notStarted’ | 색인 상태 (success, failed, notStarted)      |
| writeback           | VARCHAR(20)              | NOT NULL, DEFAULT ‘enabled’    | 사용자 편집 활성화 여부 (enabled, disabled)  |
| created_by          | VARCHAR(100)             | NOT NULL                       | 생성자                                       |
| created_at          | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now()        | 생성 일자                                    |
| updated_by          | VARCHAR(100)             |                                | 최종 수정자                                  |
| updated_at          | TIMESTAMP WITH TIME ZONE |                                | 최종 수정 일자                               |

### **5.2.2. property 테이블**

| **컬럼명**         | **데이터 타입**          | **제약 조건**              | **설명**                                              |
| ------------------ | ------------------------ | -------------------------- | ----------------------------------------------------- |
| rid                | UUID                     | PK, NOT NULL               | 속성 고유 식별자                                      |
| object_rid         | UUID                     | FK → object_type.rid       | 속성이 속한 Object Type 식별자                        |
| api_name           | VARCHAR(200)             | NOT NULL                   | 속성 호출용 이름                                      |
| display_name       | VARCHAR(200)             | NOT NULL                   | UI 표기용 이름                                        |
| description        | TEXT                     |                            | 속성 설명                                             |
| base_type          | VARCHAR(20)              | NOT NULL                   | 데이터 타입 (string, integer, boolean, date, decimal) |
| is_title_key       | BOOLEAN                  | NOT NULL, DEFAULT false    | 대표값 여부                                           |
| is_primary_key     | BOOLEAN                  | NOT NULL, DEFAULT false    | 고유 식별자 여부                                      |
| value_format       | VARCHAR(100)             |                            | 값 형식 지정 (예: YYYY-MM-DD)                         |
| conditional_format | JSONB                    |                            | 조건부 강조 규칙 (예: { "lte":10, "color":"red" })    |
| render_hints       | TEXT[]                   |                            | UI 힌트 (searchable, sortable 등)                     |
| visibility         | VARCHAR(20)              | NOT NULL, DEFAULT ‘normal’ | UI 표시 우선순위                                      |
| status             | VARCHAR(20)              | NOT NULL, DEFAULT ‘active’ | 개발 상태                                             |
| created_by         | VARCHAR(100)             | NOT NULL                   | 생성자                                                |
| created_at         | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now()    | 생성 일자                                             |
| updated_by         | VARCHAR(100)             |                            | 최종 수정자                                           |
| updated_at         | TIMESTAMP WITH TIME ZONE |                            | 최종 수정 일자                                        |

### **5.2.3. link_type 테이블**

| **컬럼명**        | **데이터 타입**          | **제약 조건**              | **설명**                                            |
| ----------------- | ------------------------ | -------------------------- | --------------------------------------------------- |
| rid               | UUID                     | PK, NOT NULL               | 관계 유형 고유 식별자                               |
| id                | VARCHAR(100)             | UNIQUE, NOT NULL           | 외부 노출용 식별자                                  |
| source_object_rid | UUID                     | FK → object_type.rid       | 출발 Object Type 식별자                             |
| target_object_rid | UUID                     | FK → object_type.rid       | 도착 Object Type 식별자                             |
| api_name          | VARCHAR(200)             | NOT NULL                   | 관계 호출용 이름                                    |
| description       | TEXT                     |                            | 관계 설명                                           |
| cardinality       | VARCHAR(20)              | NOT NULL                   | Cardinality (ONE_TO_ONE, ONE_TO_MANY, MANY_TO_MANY) |
| visibility        | VARCHAR(20)              | NOT NULL, DEFAULT ‘normal’ | UI 표시 우선순위                                    |
| status            | VARCHAR(20)              | NOT NULL, DEFAULT ‘active’ | 개발 상태                                           |
| created_by        | VARCHAR(100)             | NOT NULL                   | 생성자                                              |
| created_at        | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now()    | 생성 일자                                           |
| updated_by        | VARCHAR(100)             |                            | 최종 수정자                                         |
| updated_at        | TIMESTAMP WITH TIME ZONE |                            | 최종 수정 일자                                      |

### **5.2.4. interface 테이블**

| **컬럼명**     | **데이터 타입**          | **제약 조건**              | **설명**                              |
| -------------- | ------------------------ | -------------------------- | ------------------------------------- |
| rid            | UUID                     | PK, NOT NULL               | 인터페이스 고유 식별자                |
| display_name   | VARCHAR(200)             | NOT NULL                   | UI 표기용 이름                        |
| description    | TEXT                     |                            | 인터페이스 설명                       |
| icon           | VARCHAR(100)             |                            | 아이콘                                |
| color          | VARCHAR(7)               |                            | 아이콘/노드 색상 (HEX)                |
| implemented_by | VARCHAR(100)[]           |                            | 구현된 Object Type 목록 (array of id) |
| status         | VARCHAR(20)              | NOT NULL, DEFAULT ‘active’ | 개발 상태                             |
| visibility     | VARCHAR(20)              | NOT NULL, DEFAULT ‘normal’ | UI 표시 우선순위                      |
| created_by     | VARCHAR(100)             | NOT NULL                   | 생성자                                |
| created_at     | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now()    | 생성 일자                             |
| updated_by     | VARCHAR(100)             |                            | 최종 수정자                           |
| updated_at     | TIMESTAMP WITH TIME ZONE |                            | 최종 수정 일자                        |

### **5.2.5. action_type 테이블**

| **컬럼명**     | **데이터 타입**          | **제약 조건**              | **설명**                             |
| -------------- | ------------------------ | -------------------------- | ------------------------------------ |
| rid            | UUID                     | PK, NOT NULL               | Action Type 고유 식별자              |
| id             | VARCHAR(100)             | UNIQUE, NOT NULL           | 외부 노출용 식별자                   |
| display_name   | VARCHAR(200)             | NOT NULL                   | UI 표기용 이름                       |
| description    | TEXT                     |                            | Action 설명                          |
| api_name       | VARCHAR(200)             | NOT NULL                   | Action 호출용 이름                   |
| input_schema   | JSONB                    |                            | 입력 스키마                          |
| output_schema  | JSONB                    |                            | 출력 스키마                          |
| security_rules | JSONB                    |                            | 역할 기반 권한 정의                  |
| function_body  | TEXT                     |                            | 실제 비즈니스 로직 코드 (TypeScript) |
| status         | VARCHAR(20)              | NOT NULL, DEFAULT ‘active’ | 개발 상태                            |
| visibility     | VARCHAR(20)              | NOT NULL, DEFAULT ‘normal’ | UI 표시 우선순위                     |
| created_by     | VARCHAR(100)             | NOT NULL                   | 생성자                               |
| created_at     | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now()    | 생성 일자                            |
| updated_by     | VARCHAR(100)             |                            | 최종 수정자                          |
| updated_at     | TIMESTAMP WITH TIME ZONE |                            | 최종 수정 일자                       |

### **5.2.6. audit_log 테이블**

| **컬럼명**       | **데이터 타입**          | **제약 조건**           | **설명**                           |
| ---------------- | ------------------------ | ----------------------- | ---------------------------------- |
| id               | SERIAL                   | PK, NOT NULL            | 감사 로그 고유 식별자              |
| entity_type      | VARCHAR(50)              | NOT NULL                | 변경 대상 엔티티 종류              |
| entity_rid       | UUID                     | NOT NULL                | 변경된 엔티티 RID                  |
| change_type      | VARCHAR(10)              | NOT NULL                | 변경 종류 (CREATE, UPDATE, DELETE) |
| changed_by       | VARCHAR(100)             | NOT NULL                | 변경자 (사용자 ID)                 |
| change_timestamp | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now() | 변경 시각                          |
| change_detail    | JSONB                    |                         | 변경 전/후 스냅샷                  |

## **6. 기술 스택 및 도구 선정 근거**

1. **프론트엔드(온톨로지 에디터 UI)**
   - **React (TypeScript)**
     - **이유**: 컴포넌트 기반 구조로 복잡한 UI 관리에 용이하며, TypeScript와 함께 사용 시 코드 안정성 증대
     - React Hooks, Context API, Suspense 등 최신 기능 활용 가능
   - **BlueprintJS**
     - **이유**: 엔터프라이즈 애플리케이션에 최적화된 UI 컴포넌트 라이브러리로, 메뉴, 버튼, 테이블, 폼 등 다양한 UI 요소 제공
     - React 호환성 우수, 커스터마이징 가능
   - **Monaco Editor**
     - **이유**: VSCode의 코드 에디터 엔진으로, TypeScript 코드 하이라이팅, 자동 완성, LSP 지원 가능
     - 대용량 코드 편집에 최적화
   - **Tailwind CSS**
     - **이유**: 유틸리티 기반 CSS 프레임워크로, 빠르게 일관된 디자인 구현 가능
     - CSS 클래스 재사용성 높고 유지보수가 쉬움
   - **Zustand (또는 Redux Toolkit)**
     - **이유**: 전역 상태 관리 간편화, 규모에 따라 Context API로 대체 가능
     - 비동기 상태 로직 처리 및 DevTools 지원
   - **React Router**
     - **이유**: SPA 내 페이지 전환 및 인증 라우팅(Control)이 용이
2. **백엔드(OMS API 서버)**
   - **Node.js (TypeScript) + Express**
     - **이유**: 프론트엔드와 동일한 언어 스택(JavaScript/TypeScript)으로 코드 재사용성 증대
     - Express는 경량화된 프레임워크로, 필요한 미들웨어를 자유롭게 구성 가능
   - **TypeORM (또는 Prisma)**
     - **이유**: TypeScript ORM으로 엔티티 기반 모델링 및 마이그레이션 관리 용이
     - 관계형 DB(PostgreSQL)와 자연스럽게 매핑
   - **PostgreSQL**
     - **이유**: 안정적인 RDBMS로 JSONB 컬럼, 파티셔닝, 샤딩 지원
     - 트랜잭션 관리가 뛰어나 메타데이터 무결성 보장
   - **Redis**
     - **이유**: Pessimistic Locking을 위한 분산 잠금, 캐시(짧은 TTL)로 빈번 조회 데이터 성능 향상
   - **Kafka (또는 RabbitMQ, Redis Streams)**
     - **이유**: Event-Driven 아키텍처 구현 위해 메시지 버스 필요
     - 메타데이터 변경 이벤트, 버전 관리 이벤트 등 비동기 처리
   - **Bull (Queue)**
     - **이유**: Node.js 기반 Redis Queue로 백그라운드 작업(Full Sync, Incremental Sync, 인덱싱 재시도 등)을 안정적으로 처리
3. **색인 서비스**
   - **ElasticSearch**
     - **이유**: 텍스트 기반 검색, 집계(Aggregation), 필터링 기능 우수
     - JSON 문서 형태로 색인 가능 → 메타데이터 탐색 효율 증대
   - **Phonograph** (Palantir 내부 색인 엔진, 오픈소스 불가 시 대체)
     - **이유**: Foundry에서 실제 사용하는 색인 엔진으로 Graph 인덱싱 및 검색 최적화 내장 → Neo4j와 연계 가능
4. **그래프 DB**
   - **Neo4j**
     - **이유**: Cypher 쿼리 언어 및 Graph Data Science 라이브러리 제공 → 온톨로지 탐색, 최단 경로, 커뮤니티 탐지 등 복잡한 그래프 분석 지원
   - **대안**: JanusGraph + Cassandra/HBase, Amazon Neptune 등 프로젝트 예산 및 운영 여건에 따라 검토 가능
5. **ETL/AI 워크플로우**
   - **Apache Spark (PySpark, Spark MLlib)**
     - **이유**: 대용량 데이터 처리 성능 우수, Python으로 알고리즘 개발 가능 → OMS API와 결합 용이
   - **Airflow (또는 Argo Workflows)**
     - **이유**: DAG(Directed Acyclic Graph) 기반 워크플로우 정의 및 스케줄링 관리
     - 커스텀 PythonOperator, SparkSubmitOperator 등으로 유연한 파이프라인 구성
6. **인프라/배포**
   - **Docker + Kubernetes**
     - **이유**: 컨테이너 기반 마이크로서비스 아키텍처 구현 → 확장성, 가용성, 자동 복구 지원
   - **GitHub Actions (또는 Jenkins)**
     - **이유**: 코드 Push 시 자동 빌드, 테스트, 스테이징 배포, 프로덕션 배포 파이프라인 구현 가능 → 릴리스 품질 및 속도 보장
   - **Cert-Manager + Let’s Encrypt**
     - **이유**: 자동 SSL/TLS 인증서 발급 및 갱신
   - **Prometheus + Grafana**
     - **이유**: API 응답 시간, 에러율, DB 커넥션 사용량 등 모니터링 및 알람 설정 → 서비스 안정성 유지

## **7. 개발 로드맵 및 일정**

### **7.1. 단계별 로드맵**

| **단계**                            | **기간 (주)** | **주요 목표**                                                                                                                               | **산출물 및 검증 기준**                                                                                                    |
| ----------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| 1. 요구 분석 & 설계                 | 2주           | - 상세 기능 요구사항 확정- 데이터 모델(ERD) 설계- UI/UX 와이어프레임 완성                                                                   | - 요구사항 명세서 - ERD 다이어그램 (PDF/Markdown)- 와이어프레임 문서 (Figma 또는 HTML 목업)                                |
| 2. 기본 플랫폼 구축 (MVP)           | 4주           | - OMS API 기본 CRUD (Object/Property/Link/Interface/Action)- React Canvas 기반 Ontology Editor UI 기초 개발- DB 마이그레이션 및 연동        | - Swagger/OpenAPI 문서- React 앱에서 기본 CRUD 시나리오 (Create/Read/Update/Delete) 정상 동작- DB 인덱스 및 제약 조건 확인 |
| 3. 버전 관리 & 협업 기능            | 3주           | - Change Set 기능 구현 (생성, 조회, Merge, Rollback)- 충돌 감지 및 Conflict Resolver UI- Audit Log 기록                                     | - Change Set 생성→병합 시나리오 테스트 통과- 동시 편집 충돌 테스트 통과- Audit Log 조회 API 테스트 통과                    |
| 4. Action/Function & Interface      | 3주           | - Action/Function CRUD, CodeEditor (Monaco) 연동- Interface 생성/편집 기능 구현- OMS API 연동                                               | - Action 생성 후 코드 저장 및 로컬 테스트 시나리오 통과- Interface 연결 시 다형성 테스트 통과                              |
| 5. 권한·보안 및 인증                | 2주           | - OAuth2/OIDC 연동 (Keycloak)- RBAC 구현 (Admin/Editor/Viewer 권한 분리)- TLS 설정 및 데이터 암호화                                         | - 역할별 권한 테스트 통과 (Viewer는 수정 불가 등)- HTTPS 접속 가능 확인- 감사 로그에 권한 변경 기록                        |
| 6. 색인 & Graph 동기화              | 3주           | - ElasticSearch 색인 모듈 연동 (CRUD 이벤트 → 색인 반영)- Neo4j 동기화 모듈 (Incremental/Full Sync)- 동기화 오류 처리 및 서킷 브레이커 구현 | - 색인 후 검색/필터 기능 테스트 통과- Neo4j에서 관계 탐색 및 쿼리 테스트 통과- 서킷 브레이커 로직 시나리오 통과            |
| 7. 성능·부하 테스트 & 최적화        | 2주           | - UI 부하 테스트 (1,000개 노드/5,000개 속성 로드)- API 부하 테스트 (동시 100명 요청)- DB 샤딩/인덱스 최적화                                 | - 테스트 결과: UI 응답 시간 ≤ 200ms, API 응답 시간 ≤ 300ms- DB 인덱싱, 파티셔닝 성능 확인                                  |
| 8. 베타 릴리스 & 사용자 피드백 반영 | 2주           | - 베타 사용자 그룹 모집 및 테스트- 피드백 수집 및 개선 사항 반영                                                                            | - 베타 피드백 보고서- 수정된 기능 및 버그 픽스 목록                                                                        |
| 9. 정식 릴리스 & 운영 지원          | 2주           | - 정식 배포- 운영 모니터링 대시보드 구축 (Prometheus + Grafana)- 사용자 매뉴얼/온라인 도움말 완성                                           | - 모니터링 대시보드 배포- 사용자 매뉴얼 문서 공개 (Wiki 또는 Confluence)                                                   |

- **총 개발 기간: 약 18주 (4.5개월)**
- **팀 구성 기준**:
  - 프런트엔드 개발자 2명
  - 백엔드 개발자 2명
  - 데이터 엔지니어 1명 (ElasticSearch/Neo4j/ETL 관련)
  - DevOps 엔지니어 1명
  - 디자이너(UI/UX) 1명

## **8. 운영 및 유지보수 계획**

### **8.1. 모니터링 및 알림**

- **Prometheus**
  - **메트릭 수집**:
    - OMS API 응답 시간 (http_request_duration_seconds)
    - 에러율 (http_requests_total{status="5xx"} 비율)
    - PostgreSQL 연결 수 (pg_stat_activity)
    - ElasticSearch 색인 지연 시간 (Kafka→ES 지연)
    - Neo4j 동기화 지연 (incrementalSync/FullSync 소요 시간)
  - **알림 룰**:
    - API Error Rate > 1% (5분 평균) → Slack 알림
    - DB Connection Pool 사용량 > 80% → PagerDuty 긴급 알림
    - ElasticSearch 색인 지연 시간 > 1분 지속 → 엔지니어 이메일 알림
    - Neo4j Sync 실패율 > 5회 누적 → Slack 알림
- **Grafana 대시보드**
  - **시각화 항목**:
    - Canvas 렌더링 지연 시간 (Front-end Custom Metric)
    - Change Set Merge 실패율
    - 사용자 동시 접속 수 (WebSocket 연결 수)
    - 서버 CPU/메모리 사용량, 네트워크 트래픽
  - **Dashboard 구성**:
    - **API Performance Panel**: http_request_duration_seconds Histogram + 95th Percentile
    - **Error Rate Panel**: 5xx 비율 그래프
    - **DB Usage Panel**: PostgreSQL Connection Pool 사용률
    - **ELK Sync Panel**: ES 색인 지연 시간 (Kafka → ES), Sync 비율
    - **Neo4j Sync Panel**: Incremental Sync Duration, Last Sync Timestamp

### **8.2. 백업 및 복구**

1. **MetaStore DB (PostgreSQL)**
   - **일일 백업**: PM 2시 자동 백업 (Logical Dump + Compression)
     - pg*dump -h <host> -U <user> -Fc ontology_db > /backups/ontology_db*$(date +%F).dump
     - CronJob: 0 14 \* \* \* /usr/local/bin/backup_postgres.sh
   - **주간 백업**: 매주 금요일 00:00 자동 백업 (Physical Snapshot)
     - pg_basebackup -h <host> -U <user> -Ft -z -D /backups/ontology_db_weekly/$(date +%F)
   - **복구 절차**:
     - 장애 발생 → PMO 보고 후 백업본 확인
     - 백업 파일 로드 테스트 (테스트 환경에서)
     - 메인 DB 다운 → 대상 DB에 Restore (pg_restore -h <host> -U <user> -d ontology_db /backups/ontology_db_YYYY-MM-DD.dump)
     - 복구 완료 후 서비스 재시작 → Smoke Test
2. **ElasticSearch**
   - **스냅샷 저장소**: 매일 새벽 S3 버킷에 스냅샷 저장 (Elasticsearch Snapshot API)
     - Snapshot Repository 등록:

PUT \_snapshot/onto_snapshot

{

"type": "s3",

"settings": {

"bucket": "onto-elasticsearch-backups",

"region": "ap-northeast-2",

"compress": true

}

}

-
- Daily Snapshot (CronJob에서 API 호출):

curl -XPUT "http://localhost:9200/_snapshot/onto_snapshot/daily_$(date +%F)?wait_for_completion=true"

-
- **복구 확인**: 매주 스냅샷 복구 테스트 실행

1. **Neo4j**
   - **Hot Backup**: Neo4j Enterprise Edition의 Hot Backup 사용, 매일 1회 스냅샷 (Bolt URL)
     - neo4j-admin backup --backup-dir=/backups/neo4j --name=backup\_$(date +%F)
   - **Point-in-Time Recovery**: Write-Ahead Log (WAL) 기반 복구 지원
     - 정기적으로 dbms.backup.execute('online', {...}) 스크립트 실행

### **8.3. 장애 대응 프로세스**

1. **장애 감지**
   - Prometheus 알람 (Slack, PagerDuty) 수신
   - 사용자/운영자 시스템 모니터링 도구 통합
2. **1차 대응**
   - 당일 운영자(온콜 엔지니어) 알람 수신 후 5분 이내 상황 파악
     - Alert Details: 특정 메트릭, 에러 로그, 타임스탬프 확인
   - RMS(Root Cause Analysis) 초동 조사
     - DB 연결 문제인지, API 오류인지, 색인/Graph Sync 지연인지 확인
3. **복구 및 패치**
   - **심각 장애(서비스 중단)**
     - DB 롤백 또는 캐시 Clear (Redis) 등 긴급 대응 진행
     - 임시 Hotfix 릴리스 → 롤링 업데이트 (Kubernetes)
     - 사고 발생 지점 rollback (Git revert, DB restore)
   - **근본 원인 조사 (PMT: Post Mortem Talk)**
     - 장애 원인, 영향 범위, 복구 조치, 개선 방안 문서화
     - JIRA Ticket 생성 → 담당자 지정 → 재발 방지책 이행
4. **보고**
   - 장애 원인, 영향 범위, 복구 조치 및 개선 사항을 요약하여 24시간 이내 주요 의사결정권자에게 보고
   - 요약 문서: 서비스 이름, 장애 시각, 복구 시각, Root Cause, 영향받은 기능, 복구 조치, 향후 계획

## **9. 위험 요소(Risks) 및 대응 방안**

| **위험 요소**                             | **영향 범위**                     | **대응 방안**                                                                                                                                                                    |
| ----------------------------------------- | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 요구사항 변경/확장                        | 개발 일정 지연                    | - 요구사항 확정 시 “Must have vs. Nice to have” 구분- Scope Creep 방지 위한 Change Request 프로세스 마련 (JIRA Workflow 정의)                                                    |
| 동시 편집 충돌로 인한 데이터 손상         | 메타데이터 무결성 훼손            | - 낙관적 잠금(Optimistic Locking) 또는 비관적 잠금(Pessimistic Locking) 전략 적용 (Redis Lock 활용)- Change Set 기반 병합 UI 제공- Conflict Resolver 교육 자료 제공              |
| 대용량 온톨로지로 인한 성능 저하          | UI 렌더링 지연, API 응답 지연     | - 가상화(Virtualization) 기능 제공 (Canvas 내 일부 노드/속성만 로드) - 서버 사이드 페이징/무한 스크롤 적용 (검색/탐색 시)- Canvas에 노드 클러스터링(Clustering) 기능 추가        |
| 보안 취약점 (권한 우회, XSS 등)           | 민감 메타데이터 노출, 서비스 불가 | - OWASP Top10 기반 정기 보안 테스팅 수행 (정적/동적 분석 도구) - JWT 토큰 유효성 검증 강화 (만료 검사, 서명 검증) - 콘텐츠 보안 정책(CSP) 적용 (Helmet.js 사용)                  |
| 인덱스 서비스 장애                        | 검색/필터 기능 불가               | - 서킷 브레이커 패턴 적용 (ElasticSearch 장애 시 Query 캐시 사용, Graceful Degradation) - 색인 실패 시 Retry 로직 → 3회 재시도 후 지속 실패 시 개발자 알림 (Slack/Email)         |
| Graph DB 동기화 지연                      | 실시간 탐색 기능 불가             | - Incremental Sync 모드 도입 (Change Set 병합 시 즉시 동기) - Full Sync 시 장애 발생 시 자동 재시도 및 마지막 성공 시점 저장 - 동기화 실패 시 알림 및 수동 재동기화 기능 제공    |
| 데브옵스 인프라 설정 오류 (K8s, 네트워크) | CI/CD 파이프라인 중단             | - IaC(Infrastructure as Code) 툴(Terraform, Helm Charts) 사용 → 버전 관리 및 코드 리뷰 시행 - Staging 환경에서 사전 Smoke Test 후 프로덕션 롤아웃 - DRY Run 시뮬레이션 환경 구축 |

## **10. 구체적인 커밋 전략 및 테스트 시나리오**

### **10.1. Git Branch 전략**

1. **Branch 구조**
   - main: 정식 릴리스 코드만 존재 (프로덕션 배포 브랜치)
   - develop: 다음 릴리스를 위한 통합 브랜치 (MVP, Beta 기능 통합)
   - feature/\*: 새로운 기능 개발 브랜치 (ex: feature/object-crud, feature/canvas-ui, feature/version-control)
   - release/\*: 릴리스 준비 브랜치 (배포 전 최종 QA, 테스트)
   - hotfix/\*: 프로덕션 긴급 수정 브랜치
2. **커밋 규칙**
   - 메시지 형식: <type>(<scope>): <subject>
     - type: feat, fix, docs, style, refactor, perf, test, chore
     - scope: 대상 모듈 또는 컴포넌트 (예: canvas, metadata, api)
     - subject: 간단한 설명 (50자 이내)
   - 예시: feat(canvas): implement node drag-and-drop
3. **Pull Request (PR) 템플릿**

## 개요

- 변경 사항 요약

## 작업 내용

- 테스트 케이스
- 유닛 테스트
- 통합 테스트
- E2E 테스트

## 체크리스트

- 코드 리뷰 완료
- 빌드 및 테스트 통과 (CI 로깅)
- ESLint, Prettier 적용

## 관련 이슈

- 링크 또는 이슈 번호

### **10.2. 테스트 시나리오**

### **10.2.1. 단위 테스트 (Unit Test) – React + Jest + React Testing Library**

1. **CanvasArea 컴포넌트 테스트 (CanvasArea.test.tsx)**
   - **목표**:
     - 노드 추가/삭제/이동 시 Canvas 상태가 올바르게 변경되는지 검증
     - Zoom/Pan 이벤트 처리 유효화
   - **테스트 케이스**:
     - 초기 렌더링: Canvas 영역이 보이고 노드가 없음을 확인
     - 노드 추가: 임의의 노드 데이터를 주입하고, renderNodes 로직이 Canvas에 SVG <g> 원소로 렌더되는지 확인
     - 노드 삭제: deleteNode 이벤트 트리거 후 Canvas에 해당 <g> 원소가 사라졌는지 확인
     - Zoom In: onWheel 이벤트 시 zoom 상태가 1 → 1.1로 증가했는지 확인
     - Pan: onMouseDown, onMouseMove, onMouseUp 이벤트 시 pan 상태가 적절히 변경되었는지 확인
2. **MetadataService 테스트 (metadataService.test.ts)**
   - **목표**:
     - API 호출에 대한 HTTP 모킹(Mock) 후, 반환값 처리 로직이 올바른지 확인
   - **테스트 케이스**:
     - createObjectType 호출 → fetchMock 또는 msw(Mock Service Worker) 사용하여 201 응답 반환 → 성공 시 객체 리턴
     - updateObjectType 호출 → 버전 불일치 시 409 응답 → 오류 처리 로직(예외 던지기) 확인
     - deleteObjectType 호출 → 204 응답 → 함수가 Promise.resolve 반환 확인
3. **ActionService 테스트 (actionService.test.ts)**
   - **목표**:
     - Function Body 저장 로직이 올바르게 동작하는지 확인
4. **Zustand Store 테스트 (useOntologyStore.test.ts)**
   - **목표**:
     - 상태 업데이트 로직(노드 추가, 노드 선택, Change Set 업데이트 등)이 올바르게 동작하는지 확인

### **10.2.2. 통합 테스트 (Integration Test) – Node.js + Supertest + Jest**

1. **ObjectType API 테스트 (objectType.e2e.ts)**
   - **목표**:
     1. POST /api/object-type → 201 응답 + DB에 객체 삽입
     2. GET /api/object-type/:rid → 200 응답 + 올바른 객체 데이터 반환
     3. PUT /api/object-type/:rid (버전 일치) → 200 응답 + DB 업데이트 확인
     4. PUT /api/object-type/:rid (버전 불일치) → 409 응답
     5. DELETE /api/object-type/:rid → 204 응답 + DB에서 삭제 확인
   - **시나리오**:
     1. 초기 DB 상태: 비어 있음
     2. POST로 객체 2개 생성 → DB에 2개 레코드 존재 확인
     3. 첫 번째 객체 GET → 반환값 검증
     4. 첫 번째 객체 업데이트 → 새로운 Display Name 입력 → GET 시 변경 사항 반영 확인
     5. 첫 번째 객체 삭제 → DB에서 레코드 개수 1로 줄어듦 확인
2. **LinkType API 테스트 (linkType.e2e.ts)**
   - **목표**:
     1. Relation 생성, 조회, 수정, 삭제 흐름 검증
   - **시나리오**:
     1. 두 개의 Object Type 생성
     2. POST /api/link-type 호출 → Relation 생성 (ONE_TO_MANY)
     3. GET /api/link-type/:rid → 200 응답 + 정확한 관계 데이터
     4. PUT /api/link-type/:rid 호출 → Cardinality 변경 → GET 시 반영 확인
     5. DELETE /api/link-type/:rid → 204 응답 → DB에서 레코드 삭제 확인
3. **VersionController 테스트 (version.e2e.ts)**
   - **목표**:
     1. Change Set 생성, Merge, Rollback 흐름 검증
   - **시나리오**:
     1. Object Type 1개 생성
     2. POST /api/version/change-set 호출 → Change Set ID 반환
     3. Object Type 이름 변경 후 Change Set commit
     4. POST /api/version/merge/:changeSetId 호출 → Merge 성공 응답
     5. 변경 내용이 DB에 반영되었는지 확인
     6. POST /api/version/rollback/:changeSetId 호출 → 이전 상태 복원 확인

### **10.2.3. E2E 테스트 (End-to-End) – Cypress**

1. **로그인 및 메인 흐름**
   - **목표**:
     1. 사용자가 로그인 → Ontology Editor 진입 → 기본 CRUD 작업 흐름
   - **시나리오**:
     1. 브라우저 열기 → https://onto.company.com
     2. 로그인 페이지 → Keycloak 로그인 팝업 (msw나 Mock Keycloak 서버로 대체 가능)
     3. 로그인 후 온톨로지 에디터 페이지로 리다이렉트
     4. Sidebar → Object 드래그 → Canvas에 드롭 → CreateObjectModal 팝업 → 입력 값 채움 → “Create” 클릭 → Canvas에 노드 렌더 확인
     5. 노드 클릭 → InspectorPanel 열림 → “Properties” 탭 → “Add Property” 클릭 → 필드 채움 → “Save” 클릭 → Property 목록에 속성 추가 확인
     6. Sidebar → Link 탭 → Link 아이콘 클릭 → Source Node 클릭 → Target Node 클릭 → CreateLinkModal 팝업 → 필드 채움 → “Save” 클릭 → Canvas에 화살표 렌더 확인
     7. Action 생성 및 코드 편집: Sidebar → Action 드래그 → CreateActionModal 팝업 → 기본 정보 입력 → “Create” → Canvas에 Action 노드 렌더 → 노드 클릭 → CodeEditor 팝업 → 코드 입력 → “Save” → 성공 메시지 확인
     8. 버전 관리: “Create Change Set” 클릭 → VersionControl Panel에 Change Set 목록 추가 확인 → “Merge” 클릭 → Master 브랜치 머지 후 알림 확인
2. **검색 및 탐색 테스트**
   - **목표**:
     1. 검색 기능이 정상 작동하는지 확인
   - **시나리오**:
     1. Sidebar → Search 탭 클릭 → 검색어 입력 (예: “Employee”) → 자동완성 결과 리스트 표시
     2. 결과 클릭 → Canvas 중앙 포커싱 및 노드 하이라이트 확인
3. **권한 제어 테스트**
   - **목표**:
     1. Viewer 계정으로는 편집 불가, Editor 계정은 조회·편집만 가능, Admin 계정은 모든 기능 가능 확인
   - **시나리오**:
     1. Viewer 계정으로 로그인 → Ontology Editor 진입 → “Add Object” 버튼 비활성화 확인 → 노드 클릭 시 편집 버튼 비활성화 확인
     2. Editor 계정으로 로그인 → “Add Object” 버튼 활성화, 노드 클릭 후 속성 편집 가능하지만 삭제 버튼 비활성화 확인
     3. Admin 계정으로 로그인 → 모든 버튼 활성화 확인
4. **보안 시나리오 테스트**
   - **목표**:
     1. CSRF, XSS, SQL Injection 방어 확인
   - **시나리오**:
     1. CSRF: Developer Tools에서 임의 CSRF 토큰 제거 후 요청 시 403 Forbidden 응답 확인
     2. XSS: InspectionPanel Description 필드에 <script>alert("XSS")</script> 입력 후 저장 시, 화면 상 스크립트 실행되지 않고 툴팁으로 안전하게 이스케이프 처리 확인
     3. SQL Injection: Postman을 통해 POST /api/object-type 시 Body에 api_name=Employee'; DROP TABLE object_type;-- 입력 시 400 Bad Request 또는 Prepared Statement 처리되어 테이블 삭제되지 않음 확인

## **11. 운영 및 유지보수 세부 절차**

### **11.1. 배포 파이프라인 (CI/CD) – GitHub Actions 예시**

1. **Workflow 파일: .github/workflows/ci-cd.yml**

name: Ontology Editor CI/CD

on:

push:

branches:

- develop
- main
- 'feature/\*'
- 'release/\*'

pull_request:

branches:

- develop
- main

jobs:

lint-test-build:

runs-on: ubuntu-latest

services:

postgres:

image: postgres:13

env:

POSTGRES_DB: ontology_db

POSTGRES_USER: postgres

POSTGRES_PASSWORD: postgres

ports:

- 5432:5432

options: >-

- -health-cmd "pg_isready -U postgres"
- -health-interval 10s
- -health-timeout 5s
- -health-retries 5

steps:

- name: Checkout code

uses: actions/checkout@v3

- name: Set up Node.js

uses: actions/setup-node@v3

with:

node-version: '18'

- name: Install dependencies (Frontend)

working-directory: frontend

run: npm ci

- name: Lint (Frontend)

working-directory: frontend

run: npm run lint

- name: Unit Tests (Frontend)

working-directory: frontend

run: npm run test:unit

- name: Build (Frontend)

working-directory: frontend

run: npm run build

- name: Install dependencies (Backend)

working-directory: server

run: npm ci

- name: Lint (Backend)

working-directory: server

run: npm run lint

- name: Run Migrations

working-directory: server

env:

DATABASE_URL: postgres://postgres:postgres@localhost:5432/ontology_db

run: npm run migration:run

- name: Integration Tests (Backend)

working-directory: server

env:

DATABASE_URL: postgres://postgres:postgres@localhost:5432/ontology_db

run: npm run test:integration

- name: Build Docker Images

run: |

docker build -t onto-frontend:latest ./frontend

docker build -t onto-backend:latest ./server

- name: Push to DockerHub

if: github.ref == 'refs/heads/main'

env:

DOCKERHUB_USERNAME: ${{ secrets.DOCKERHUB_USERNAME }}

DOCKERHUB_TOKEN: ${{ secrets.DOCKERHUB_TOKEN }}

run: |

echo $DOCKERHUB_TOKEN | docker login -u $DOCKERHUB_USERNAME --password-stdin

docker tag onto-frontend:latest $DOCKERHUB_USERNAME/onto-frontend:latest

docker tag onto-backend:latest $DOCKERHUB_USERNAME/onto-backend:latest

docker push $DOCKERHUB_USERNAME/onto-frontend:latest

docker push $DOCKERHUB_USERNAME/onto-backend:latest

deploy-staging:

needs: lint-test-build

if: github.ref == 'refs/heads/develop'

runs-on: ubuntu-latest

steps:

- name: Checkout code

uses: actions/checkout@v3

- name: Deploy to Staging (Kubernetes)

env:

KUBE_CONFIG_DATA: ${{ secrets.STAGING_KUBE_CONFIG }}

run: |

echo "$KUBE_CONFIG_DATA" | base64 --decode > kubeconfig

kubectl --kubeconfig=kubeconfig apply -f k8s/staging/frontend-deployment.yaml

kubectl --kubeconfig=kubeconfig apply -f k8s/staging/backend-deployment.yaml

deploy-production:

needs: lint-test-build

if: github.ref == 'refs/heads/main'

runs-on: ubuntu-latest

steps:

- name: Checkout code

uses: actions/checkout@v3

- name: Deploy to Production (Kubernetes)

env:

KUBE_CONFIG_DATA: ${{ secrets.PRODUCTION_KUBE_CONFIG }}

run: |

echo "$KUBE_CONFIG_DATA" | base64 --decode > kubeconfig

kubectl --kubeconfig=kubeconfig apply -f k8s/prod/frontend-deployment.yaml

kubectl --kubeconfig=kubeconfig apply -f k8s/prod/backend-deployment.yaml

1.
2. **Kubernetes Manifest 예시 (k8s/staging/frontend-deployment.yaml)**

apiVersion: apps/v1

kind: Deployment

metadata:

name: onto-frontend

namespace: staging

labels:

app: onto-frontend

spec:

replicas: 3

selector:

matchLabels:

app: onto-frontend

template:

metadata:

labels:

app: onto-frontend

spec:

containers:

- name: onto-frontend

image: $DOCKERHUB_USERNAME/onto-frontend:latest

ports:

- containerPort: 80

livenessProbe:

httpGet:

path: /

port: 80

initialDelaySeconds: 30

periodSeconds: 10

readinessProbe:

httpGet:

path: /

port: 80

initialDelaySeconds: 10

periodSeconds: 5

resources:

requests:

memory: "256Mi"

cpu: "250m"

limits:

memory: "512Mi"

cpu: "500m"

## **12. 결론**

지금까지 제시된 기획문서는 React + BlueprintJS 기반의 온톨로지 에디터가 구현되어야 할 모든 요소를 **“왜 필요한지(근거)”**와 **“어떻게 설계할지(구체 방안)”** 두 축으로 면밀히 분석하여 작성한 것입니다.

- **Why (근거)**:
  1. 비개발자도 직관적인 GUI를 통해 데이터 모델(온톨로지)을 정의/관리함으로써 조직 내 공유 어휘 통일.
  2. 일관된 메타데이터 관리로 데이터 파이프라인·AI 모델·애플리케이션 단계에서 재사용 가능.
- **How (구체 방안)**:
  1. React + BlueprintJS 이용한 컴포넌트 기반 UI: CanvasArea, Toolbox, InspectorPanel, CodeEditor, VersionControl 등을 모듈별로 분리하여 유지보수성 및 확장성 확보.
  2. Node.js/TypeScript 백엔드: TypeORM/Prisma 기반 Entity 모델링, Kafka 기반 이벤트 처리, ElasticSearch/Neo4j 동기화 모듈 등으로 온톨로지 메타데이터 관리 품질 극대화.
  3. 철저한 테스트 전략: Unit Test, Integration Test, E2E Test, 보안 테스트, 부하 테스트, 성능 테스트 → 품질 보증
  4. CI/CD 구성: GitHub Actions + Kubernetes → 자동화된 빌드/테스트/배포 파이프라인
  5. 운영 안정성: Prometheus + Grafana 모니터링 → 알림 룰 설정 → 장애 대응 프로세스 마련
