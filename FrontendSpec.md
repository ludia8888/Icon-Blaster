[FrontendSpec.md]
## **FrontendSpec.md**

### **1. 개요**

이 문서는 Ontology Editor 프론트엔드 구현 사양을 엔터프라이즈 프로덕션 수준으로 심층 규격화합니다. DesignDoc.md에서 정의된 UI/UX 설계를 바탕으로, 개발자가 문서만으로 컴포넌트를 즉시 구현할 수 있도록 상세한 폴더 구조, 코드 패턴, 상태 관리, 라우팅, 스타일 시스템, API 연동, 성능·접근성·보안 기준, 테스팅 전략을 모두 포함합니다.

**대상 독자:** 프론트엔드 개발자, DevOps, QA

---

### **2. 프로젝트 설정 및 구조**

### **2.1 Monorepo & 패키지 관리**

- Yarn Workspaces 사용: packages/frontend, packages/shared-ui, packages/utils
- Root package.json 에 공통 스크립트 정의

### **2.2 주요 디렉토리**

```
packages/frontend/
├─ public/                 # 정적 자산
│   └─ index.html          # Single SPA host
├─ src/
│   ├─ atoms/              # Atomic Design: 버튼, 입력폼, 아이콘 등
│   ├─ molecules/          # 조합 컴포넌트: FormGroup, TableRow 등
│   ├─ organisms/          # 복합 컴포넌트: Header, Sidebar, InspectorPanel
│   ├─ templates/          # 페이지 템플릿: EditorLayout
│   ├─ pages/              # Next.js-style 페이지 (optional SSR)
│   ├─ hooks/              # 커스텀 훅 (useOntologyStore, useAuth)
│   ├─ services/           # API 서비스 (axios instances, react-query)
│   ├─ routes/             # React Router 구성
│   ├─ lib/                # 로케일, 테마, 환경변수 타입 등
│   ├─ styles/             # Tailwind 설정, 글로벌 CSS
│   ├─ assets/             # SVG, 폰트 등
│   ├─ utils/              # 범용 유틸 함수, 타입
│   ├─ App.tsx
│   └─ main.tsx            # ReactDOM.render
├─ tailwind.config.js      # theme 확장
├─ tsconfig.json           # 경로 별칭 설정
├─ vite.config.ts          # alias, plugin 설정
└─ .env.*                  # 환경별 변수
```

### **2.3 환경 변수 관리**

- .env.development, .env.production 파일에 VITE_ prefix 사용
- import.meta.env.VITE_API_BASE 타입 정의(env.d.ts)

---

### **3. 기술 스택 및 도구**

- **프레임워크**: React 18 (Strict Mode), Vite 4
- **언어**: TypeScript (tsconfig: strict, noImplicitAny, paths 설정)
- **UI 라이브러리**: BlueprintJS v6, custom shared-ui 패키지
- **스타일**: Tailwind CSS + PostCSS, CSS Modules for scoped styles
- **상태 관리**: Zustand v4 + immer + middleware (persist, devtools)
- **데이터 패칭**: React Query v5 (swr 대체), queryClient with global config
- **라우팅**: React Router v6.10, nested routes, Layout Routes
- **코드 에디터**: Monaco Editor with webpack worker plugin
- **번들러**: Vite + Plugins (alias, babel, svg loader)
- **i18n**: react-i18next, lazy load locales
- **테스팅**: Jest + React Testing Library + msw, Cypress for E2E, Storybook for UI
- **CI/CD**: GitHub Actions, Netlify/Vercel 배포
- **관측성**: Sentry for error tracking, Prometheus client for metrics
- **보안**: CSP, Helmet.js, OWASP ZAP GitHub Action

---

### **4. 상태 관리 상세**

### **4.1 useOntologyStore (Zustand)**

```
interface OntologyState {
  nodes: Node[];
  links: Link[];
  selectedId: string | null;
  zoom: number;
  pan: { x: number; y: number };
  branch: string;
  changeSetId: string;
  searchResults: SearchResult[];
  isLoading: boolean;
  error: string | null;
}
```

- **Actions**: CRUD, select/deselect, pan/zoom, changeSet ops, error clear
- **Middleware**:
    - persist (localStorage: branch, changeSetId)
    - devtools (ReduxDevTools 연동)
- **Immutability**: immer 적용

### **4.2 React Query 설정**

```
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5분
      cacheTime: 1000 * 60 * 10,
      retry: 2,
      refetchOnWindowFocus: false,
      onError: (err) => Sentry.captureException(err),
    },
    mutations: {
      onError: (err) => toast.error(err.message),
      onSettled: () => queryClient.invalidateQueries('nodes'),
    }
  }
});
```

- **Query Keys**: ['nodes'], ['links', nodeId], ['search', query]
- **Optimistic Updates**: onMutate + rollbackOnError

---

### **5. 라우팅 & 코드 스플리팅**

- **Route Structure**:
    - /login
    - /editor/* (Layout route: Header + Sidebar)
- **Lazy Loading**: React.lazy + Suspense for heavy components (CodeEditor, InspectorPanels)
- **Fallback UIs**: skeleton 컴포넌트, spinner 위치 지정

---

### **6. API 연동 & 에러 핸들링**

### **6.1 Axios 인스턴스**

```
const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE });
api.interceptors.request.use((cfg) => {
  cfg.headers.Authorization = `Bearer ${authStore.token}`;
  return cfg;
});
api.interceptors.response.use(
  (res) => res,
  async (err) => handleAuthError(err)
);
```

- **토큰 리프레시**: 401 발생 시 refreshToken() 후 retry original request
- **글로벌 에러 처리**: Sentry, toast alerts, error boundary 연동

### **6.2 Service 패턴**

- 각 서비스 파일 내 CRUD 함수에 useMutation 래핑 예:

```
export function useCreateNode() {
  return useMutation(createNodeApi, {
    onSuccess: () => queryClient.invalidateQueries('nodes')
  });
}
```

---

### **7. 스타일 가이드 & 토큰**

### **7.1 Tailwind Config (tailwind.config.js)**

```
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}', '../shared-ui/**/*.{js,ts,tsx}'],
  theme: {
    extend: {
      colors: { primary: '#0052CC', secondary: '#F5A623' },
      spacing: { '72': '18rem', '84': '21rem' },
      fontFamily: { sans: ['Pretendard', 'sans-serif'], mono: ['Source Code Pro'] }
    }
  },
  plugins: [require('@tailwindcss/forms'), require('@tailwindcss/typography')]
};
```

### **7.2 Global Styles (index.css)**

```
@tailwind base; @tailwind components; @tailwind utilities;
:root { --focus-ring: 2px solid var(--tw-color-primary); }
```

---

### **8. 컴포넌트 인터페이스 & 예시**

### **8.1 CanvasArea.tsx**

```
export interface CanvasAreaProps {
  nodes: Node[];
  links: Link[];
  selectedId: string | null;
  zoom: number;
  pan: { x: number; y: number };
  onNodeDrag: (rid: string, x: number, y: number) => void;
  onZoomChange: (z: number) => void;
  onPanChange: (dxDy: { x: number; y: number }) => void;
  onSelect: (rid: string | null) => void;
}
```

- **Performance**: useMemo for layers, requestAnimationFrame 드로잉
- **Accessibility**: role=“application”, keyboard navigation (Arrow keys로 pan)

### **8.2 InspectorPanel.tsx**

```
export interface InspectorPanelProps {
  isOpen: boolean;
  selected: Node | Link | null;
  onClose: () => void;
  onUpdateMeta: (dto: MetadataDTO) => Promise<void>;
  onAddProp: (dto: PropertyDTO) => Promise<void>;
  /* ... */
}
```

- **Forms**: React Hook Form 사용, schema validation (zod)
- **Tabs**: ARIA 탭 키보드 제어

---

### **9. 접근성 & 국제화**

- **ARIA Roles**: region, tablist, tab, treegrid for canvas
- **Keyboard**: Tab, Shift+Tab, Enter/Escape, Arrow keys
- **i18n**: react-i18next with namespaces, fallbackLng

---

### **10. 성능 & 번들 최적화**

- **Bundle Analysis**: vite-plugin-visualizer 사용, 200KB 예산
- **Lazy Loading**: CodeEditor chunk 분리, Monaco worker 외부 로딩
- **Resource Hints**: <link rel="preload"> for large assets

---

### **11. 테스팅 전략**

### **11.1 Storybook**

- 모든 Atom/Molecule/Organism 스토리 작성
- @storybook/addon-a11y, addon-interactions 통합

### **11.2 Unit Test**

- 폴더: src/__tests__ 또는 __tests__
- 컴포넌트, 훅, util 함수 80% 커버리지 목표

### **11.3 Integration Test**

- msw로 API mocking → React Query + 컴포넌트 렌더 검증

### **11.4 E2E (Cypress)**

- 시나리오: 로그인, 노드 CRUD, link CRUD, merge flow, search
- cypress-axe로 accessibility 검사

### **11.5 Performance Test**

- Lighthouse CI, custom script로 Canvas 렌더 성능 측정

---

### **12. 관측성 & 에러 로깅**

- **Sentry**: ErrorBoundary, captureMessage/captureException
- **Metrics**: prom-client 통한 custom metrics → /metrics endpoint
- **Console**: custom logger util (levels: debug, info, warn, error)

---

### **13. 배포 & CI/CD**

- **Lint & Test**: npm run lint, npm run test:ci
- **Build & Deploy**: npm run build → vite build + Docker multi-stage
- **Preview Deploy**: PR마다 Netlify/Vercel 미리보기 URL 제공

---

### **14. 후속 참조**

- DesignDoc.md
- BackendSpec.md
- APISpec.md
- InfraSpec.md
- CICDSpec.md
- QASpec.md

