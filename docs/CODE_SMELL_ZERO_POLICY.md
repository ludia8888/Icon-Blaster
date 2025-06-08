# Code Smell Zero Policy

## 개요

Arrakis 프로젝트는 **Code Smell Zero** 정책을 통해 최고 수준의 코드 품질을 유지합니다. 이 정책은 SonarQube, ESLint, Prettier를 통합하여 자동화된 코드 품질 관리 체계를 구축합니다.

## 핵심 원칙

### 1. Zero Tolerance
- 모든 코드 스멜은 즉시 수정
- 새로운 코드는 스멜 없이 커밋
- 기존 코드도 점진적으로 개선

### 2. 자동화
- Pre-commit hooks로 사전 차단
- CI/CD 파이프라인에서 강제 검증
- SonarQube Quality Gate 필수 통과

### 3. 일관성
- ESLint와 SonarQube 규칙 동기화
- Prettier로 코드 포맷 통일
- 모든 개발자가 동일한 규칙 적용

## TypeScript 보안 규칙

### 엄격한 타입 체크
```typescript
// ❌ Bad
function process(data: any) {
  return data.value;
}

// ✅ Good
interface Data {
  value: string;
}
function process(data: Data): string {
  return data.value;
}
```

### Null 안전성
```typescript
// ❌ Bad
function getName(user) {
  return user.name;
}

// ✅ Good
function getName(user: User | null): string | null {
  return user?.name ?? null;
}
```

### Promise 처리
```typescript
// ❌ Bad
async function fetchData() {
  fetch('/api/data');
}

// ✅ Good
async function fetchData(): Promise<void> {
  await fetch('/api/data');
}
```

## ESLint 규칙 (SonarQube 연동)

### TypeScript 엄격 모드
- `@typescript-eslint/no-explicit-any`: 'any' 타입 금지
- `@typescript-eslint/no-unsafe-*`: 안전하지 않은 연산 금지
- `@typescript-eslint/explicit-function-return-type`: 명시적 반환 타입
- `@typescript-eslint/strict-boolean-expressions`: 엄격한 불린 표현식

### 코드 복잡도
- `max-lines-per-function`: 함수당 최대 30줄
- `complexity`: 순환 복잡도 최대 10
- `sonarjs/cognitive-complexity`: 인지 복잡도 최대 10

### 보안 규칙
- `security/detect-object-injection`: 객체 인젝션 탐지
- `security/detect-unsafe-regex`: 안전하지 않은 정규식 금지
- `security/detect-eval-with-expression`: eval 사용 금지

## Prettier 설정

```json
{
  "semi": true,
  "trailingComma": "es5",
  "singleQuote": true,
  "printWidth": 100,
  "tabWidth": 2,
  "useTabs": false,
  "arrowParens": "always",
  "endOfLine": "lf"
}
```

## 품질 게이트 설정

### SonarQube Quality Gate
- 새 코드 커버리지: 80% 이상
- 중복 코드: 3% 이하
- 코드 스멜: 0개
- 버그: 0개
- 취약점: 0개
- 보안 핫스팟: 0개

### 실패 시 조치
1. **CI/CD 중단**: Quality Gate 실패 시 배포 차단
2. **PR 차단**: 코드 스멜 있을 시 머지 불가
3. **즉시 수정**: 발견된 문제는 24시간 내 해결

## 실행 방법

### 1. 로컬 검증
```bash
# ESLint 실행
npm run lint

# Prettier 체크
npm run format:check

# TypeScript 타입 체크
npm run type-check

# 전체 코드 품질 검증
npm run code-quality
```

### 2. 자동 수정
```bash
# ESLint 자동 수정
npm run lint:fix

# Prettier 자동 포맷
npm run format
```

### 3. SonarQube 분석
```bash
# 테스트 커버리지 생성
npm run test:coverage

# SonarQube 분석 실행
npm run sonar
```

### 4. Pre-commit Hook
```bash
# Husky + lint-staged 자동 실행
git commit -m "feat: new feature"
# 자동으로 ESLint + Prettier 실행
```

## 예외 처리

### 필수 예외
특정 상황에서 규칙 비활성화가 필요한 경우:

```typescript
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const legacyApi: any = window.legacySystem;
```

### 예외 승인 절차
1. 코드 리뷰에서 정당성 설명
2. 기술 리드 승인 필요
3. TODO 주석으로 개선 계획 명시

## 모니터링

### 대시보드
- SonarQube: http://localhost:9000
- 프로젝트별 품질 메트릭 실시간 확인
- 기술 부채 추적

### 리포트
- 주간 코드 품질 리포트
- 월간 기술 부채 현황
- 분기별 개선 목표 설정

## 개발자 가이드

### 1. IDE 설정
```bash
# VS Code 확장 설치
- ESLint
- Prettier
- SonarLint
```

### 2. 설정 파일 동기화
- `.eslintrc.js`: ESLint 규칙
- `.prettierrc`: Prettier 설정
- `sonar-project.properties`: SonarQube 설정

### 3. 워크플로우
1. 코드 작성
2. 로컬에서 `npm run code-quality` 실행
3. 문제 해결
4. 커밋 (pre-commit hook 자동 실행)
5. PR 생성
6. SonarQube 분석 통과 확인
7. 코드 리뷰
8. 머지

## 지속적 개선

### 월간 리뷰
- 새로운 코드 스멜 패턴 분석
- 규칙 효과성 평가
- 개발자 피드백 수집

### 규칙 업데이트
- 분기별 규칙 검토
- 새로운 보안 취약점 대응
- TypeScript 버전 업그레이드 대응

## 성과 측정

### KPI
- 코드 스멜 발생률: 0%
- 첫 커밋 통과율: 95% 이상
- 평균 수정 시간: 1시간 이내
- 개발자 만족도: 4.5/5.0 이상

### 보고
- 주간 품질 대시보드
- 월간 트렌드 분석
- 분기별 개선 보고서

## 결론

Code Smell Zero는 단순한 정책이 아닌 문화입니다. 모든 팀원이 코드 품질에 대한 책임감을 가지고, 지속적으로 개선하는 것이 목표입니다.

**"깨끗한 코드는 팀의 자산이며, 제품의 경쟁력입니다."**