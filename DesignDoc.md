[DesignDoc.md]
### **1. 문서 개요**

이 문서는 Ontology Editor UI/UX 설계를 최고 수준의 엔터프라이즈 프로덕션 레벨로 상세 규격화합니다. 비개발자(도메인 전문가, PM)가 코딩 없이 메타데이터를 정의·관리하고, 개발자는 문서만으로도 컴포넌트를 바로 구현할 수 있도록 컴포넌트별 인터페이스, 상태 흐름, 이벤트, 스타일 토큰, 접근성, 성능 최적화, 테스트 시나리오를 포함합니다.

**대상 독자:** 프론트엔드 개발자, UX/UI 디자이너, QA 엔지니어

---

### **2. 디자인 원칙**

1. **직관성 (Intuitiveness)**
    - 1단계 클릭/드래그로 주요 기능(노드 생성, 링크 연결, 속성 편집) 완결
    - Hover, Focus, Active 시 시각적 피드백(하이라이트, 그림자, 진동 애니메이션)
2. **일관성 (Consistency)**
    - Figma Design Tokens: 컬러, 타이포그래피, 간격 등 공통 변수화
    - BlueprintJS 컴포넌트 스타일 오버라이드, Tailwind 유틸 클래스 확장
3. **확장성 (Scalability)**
    - Atomic Design: atoms, molecules, organisms 구조 채택
    - Canvas 가상화(react-window) 적용, 노드/Edge 가시화 수준 제어(LOD)
4. **접근성 (Accessibility)**
    - WCAG 2.1 AA 준수: 텍스트 대비 4.5:1, Keyboard Nav, ARIA roles/labels
    - High Contrast & Dark Mode 지원, 사용자 선택 가능
5. **퍼포먼스 (Performance)**
    - 메모이제이션(React.memo, useMemo, useCallback), 셀렉터(Re-reselect)
    - 요청 병합(Debounce, Throttle), WebSocket 이벤트 배치 처리

---

### **3. 디자인 시스템 & 토큰**

### **3.1 컬러 토큰**

| **Token** | **Value** | **Usage** |
| --- | --- | --- |
| color.primary | #0052CC | 버튼, 링크, 강조 액센트 |
| color.secondary | #F5A623 | 경고, 중요 알림 |
| color.bg | #F4F7FA | 앱 전체 배경 |
| color.canvasGrid | #E1E8F0 | Canvas 그리드 패턴 |
| color.status.active | #CCE5FF | Object Node 배경 (active) |
| color.status.experimental | #FFF1CC | Node 배경 (experimental) |
| color.status.deprecated | #E1E1E1 | Node 배경 (deprecated) |

### **3.2 타이포그래피 토큰**

| **Token** | **Value** | **Usage** |
| --- | --- | --- |
| font.family.base | ‘Pretendard’, sans-serif | 본문 텍스트 |
| font.size.h1 | 1.5rem | 주요 제목 |
| font.size.h2 | 1.25rem | 서브 제목 |
| font.size.body | 1rem | 일반 문단 |
| font.family.code | ‘Source Code Pro’, monospace | 코드, JSON 에디터 |

### **3.3 간격 토큰**

| **Token** | **Value** | **Usage** |
| --- | --- | --- |
| spacing.xs | 4px | 내부 패딩, 마진 |
| spacing.sm | 8px | 소형 컴포넌트 간격 |
| spacing.md | 16px | 일반 레이아웃 |
| spacing.lg | 24px | 섹션 분리 |

### **3.4 아이콘 & 애니메이션**

- **아이콘**: BlueprintJS Icons, Lucide Icons 셋 중립 사용, SVG Sprite로 번들
- **애니메이션**: Framer Motion 사용 (fade, slide, scale) 100ms–200ms

---

### **4. 컴포넌트 설계**

Atomic Design 기준으로 정리: Atoms → Molecules → Organisms → Templates

### **4.1 Atoms**

- **Button**
    - Props: variant: 'primary'|'secondary'|'ghost', size: 'sm'|'md'|'lg', disabled, icon?, onClick
    - States: default, hover, active, disabled, loading
    - Accessibility: aria-label, focus ring, role=“button”
- **Icon**
    - Props: name: string, size: number, aria-hidden?
- **Input**
    - Props: type, value, placeholder, onChange, disabled, error?
    - Validation state: error 메시지 표시
- **Modal**, **Drawer**
- **Tooltip**, **Popover**

### **4.2 Molecules**

- **FormGroup** (Label + Input + Error)
- **ColorPicker** (SketchPicker 래핑, controlled)
- **IconPicker** (검색/그리드, keyboard nav)
- **Table** (Virtualized, sortable, filterable)
- **Tabs** (BlueprintJS Tab 래핑, keyboard nav)

### **4.3 Organisms**

- **Header**
    - Logo, NavTabs, ProfileMenu, Notifications
    - Props: links: { label, path }[], onLogout
- **Sidebar (Toolbox)**
    - Tabs: Node | Link | Search
    - DragSources: useDrag(Hook), preview overlay
- **CanvasArea**
    - Zoom/Pan controls, grid pattern, NodeLayer, EdgeLayer
    - Props: nodes, links, selectedId, callbacks on events
    - Performance: virtualization for off-screen nodes
- **InspectorPanel**
    - Controlled Drawer, 탭별 panel components (MetadataForm, PropertiesTable, LinksTable, HelpMarkdown)
- **VersionControlBar**

### **4.4 Templates & Pages**

- **EditorPage**: Header + Sidebar + CanvasArea + InspectorPanel + VersionControlBar
- **LoginPage**: OAuth2 Redirect 처리, error handling

---

### **5. 상태 관리 & 데이터 흐름**

Zustand + immer + React Query 활용

### **5.1 Store 구조 (**

### **useOntologyStore**

### **)**

```
interface Node { rid: string; x: number; y: number; status: string; metadata: Metadata; }
interface Link { rid: string; source: string; target: string; cardinality: string; }
interface OntologyState {
  nodes: Node[];
  links: Link[];
  selectedId: string | null;
  zoom: number;
  pan: { x: number; y: number };
  changeSetId: string;
  branch: string;
  isLoading: boolean;
  error: string | null;
}
```

- Actions: CRUD, select/deselect, pan/zoom, changeSet operations
- Persist: localStorage (branch, changeSetId)

### **5.2 React Query**

- Queries: getNodes, getLinks, getChangeSet, searchNodes
- Mutations: create/update/delete Node, Link, Property, Action
- Cache invalidation: onSuccess, optimistic updates with rollback on error

### **5.3 WebSocket/EventBus**

- Notifications: change merged, conflict alerts
- GraphSync events: update Node/Link real-time

---

### **6. 인터랙션 & 에러 처리 시나리오**

| **이벤트** | **정상 흐름** | **에러 핸들링** |
| --- | --- | --- |
| 노드 생성 | drag→modal→submit→API→optimistic update→success toast | validation error→modal inline errornetwork error→retry button + toast |
| 속성 추가 | panel→add modal→API→table row 추가 | JSON parse error→monaco lint errorAPI 400→error banner |
| 링크 생성 | click mode→select src/tgt→modal→API→edge render | invalid cardinality→modal highlight field409 conflict→conflict resolver UI |
| 코드 저장 | CodeEditor→put API→success toast | syntax error→lint error under editor500→toast retry |
| 변경 병합 | Merge click→API→success toast + changeSet clear | 409 conflict→open ConflictResolver modal |

---

### **7. 접근성(ARIA) 정의**

- **Canvas**: role=“application”, aria-label=“Ontology Canvas”
- **Nodes/Edges**: role=“group”, aria-labelledby nodes names
- **InspectorPanel**: role=“region”, aria-label=“Inspector Panel”
- **Forms/Buttons**: all labels 연결, keyboard nav, focus order

---

### **8. 성능 최적화**

- **Code Splitting**: React.lazy, Suspense for heavy components (CodeEditor)
- **Virtualization**: react-window for node list & search results
- **Memoization**: React.memo, custom hooks
- **Batching**: requestAnimationFrame for canvas redraws
- **Network**: HTTP/2, GZIP, caching headers

---

### **9. 테스트 전략**

- **Storybook**: 모든 atom/molecule/organism 스토리화, accessibility addon
- **Unit Tests**: Jest + React Testing Library for components & hooks
- **Integration Tests**: msw(Mock Service Worker) + React Query mocking
- **E2E**: Cypress (login → CRUD → merge → search 시나리오)
- **Performance**: Lighthouse CI, Canvas 렌더 타임 측정

---

### **10. 와이어프레임 & 프로토타입**

- Figma 컴포넌트 라이브러리, 디자인 토큰 링크 제공
- 주요 화면: EditorPage, Modals, ConflictResolver, Notifications Panel

---

### **11. 개발 가이드**

- **폴더 구조**: atomic 기준 src/{atoms,molecules,organisms,templates}
- **코딩 컨벤션**: ESLint, Prettier, 커밋 메시지 컨벤션
- **Design Token 관리**: tokens.json → Tailwind theme
- **릴리즈 노트**: Storybook Docs & GitHub Releases

---

### **12. 후속 문서 링크**

- FrontendSpec.md (서비스/라우터/API 상세)
- APISpec.md
- BackendSpec.md
- InfraSpec.md
- CICDSpec.md
- QASpec.md