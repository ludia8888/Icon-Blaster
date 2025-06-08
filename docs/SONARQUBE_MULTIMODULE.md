# SonarQube 다중 모듈 프로젝트 설정 가이드

## 개요

Arrakis 프로젝트는 모노레포 구조로 여러 패키지를 포함하고 있습니다. SonarQube가 각 모듈을 올바르게 분석하도록 다중 모듈 구성을 사용합니다.

## 현재 구성

### 모듈 구조
```
arrakis-project/
├── packages/
│   ├── backend/     # 백엔드 API 서버
│   ├── shared/      # 공유 타입 및 유틸리티
│   ├── contracts/   # API 계약 및 스키마
│   └── frontend/    # (향후 추가 예정)
└── sonar-project.properties
```

### sonar-project.properties 설정

```properties
# 프로젝트 식별
sonar.projectKey=Arrakis-Project
sonar.projectName=Arrakis Project
sonar.projectVersion=1.0.0

# 다중 모듈 구성
sonar.modules=backend,shared,contracts

# 각 모듈별 설정
backend.sonar.projectName=Backend
backend.sonar.projectBaseDir=packages/backend
backend.sonar.sources=src
backend.sonar.tests=src
backend.sonar.test.inclusions=**/*.test.ts,**/*.spec.ts,**/__tests__/**
backend.sonar.exclusions=**/*.test.ts,**/*.spec.ts,**/__tests__/**,**/node_modules/**,**/dist/**,**/coverage/**,**/*.d.ts
backend.sonar.javascript.lcov.reportPaths=coverage/lcov.info
```

## 새 모듈 추가 방법

### 1. Frontend 모듈 추가 예시

sonar-project.properties 파일에 다음을 추가:

```properties
# sonar.modules에 frontend 추가
sonar.modules=backend,shared,contracts,frontend

# Frontend 모듈 설정
frontend.sonar.projectName=Frontend
frontend.sonar.projectBaseDir=packages/frontend
frontend.sonar.sources=src
frontend.sonar.tests=src
frontend.sonar.test.inclusions=**/*.test.ts,**/*.test.tsx,**/*.spec.ts,**/__tests__/**
frontend.sonar.exclusions=**/*.test.ts,**/*.test.tsx,**/*.spec.ts,**/__tests__/**,**/node_modules/**,**/dist/**,**/coverage/**,**/*.d.ts
frontend.sonar.javascript.lcov.reportPaths=coverage/lcov.info
```

### 2. 새 모듈 추가 체크리스트

- [ ] `sonar.modules`에 모듈 이름 추가
- [ ] `{module}.sonar.projectName` 설정
- [ ] `{module}.sonar.projectBaseDir` 설정 (packages/ 기준 상대 경로)
- [ ] `{module}.sonar.sources` 설정 (보통 src)
- [ ] `{module}.sonar.tests` 설정
- [ ] `{module}.sonar.test.inclusions` 설정
- [ ] `{module}.sonar.exclusions` 설정
- [ ] `{module}.sonar.javascript.lcov.reportPaths` 설정

## 분석 실행

```bash
# 테스트 커버리지 생성
npm run test:coverage

# SonarQube 분석 실행
npm run sonar
```

## 모듈별 결과 확인

SonarQube 대시보드에서 각 모듈별 메트릭 확인:
- http://localhost:9000/dashboard?id=Arrakis-Project

각 모듈은 별도의 서브 프로젝트로 표시되며, 개별적으로 분석됩니다:
- Backend 모듈
- Shared 모듈
- Contracts 모듈

## 장점

1. **모듈별 독립적 분석**: 각 패키지가 독립적으로 분석되어 더 정확한 메트릭 제공
2. **커버리지 정확도**: 각 모듈의 커버리지가 올바른 경로에서 읽힘
3. **확장성**: 새 패키지 추가 시 간단히 설정 추가만으로 분석 가능
4. **유지보수성**: 모듈별 설정을 독립적으로 관리 가능

## 주의사항

1. **경로 설정**: `projectBaseDir`은 프로젝트 루트 기준 상대 경로
2. **소스 경로**: `sources`와 `tests`는 모듈 디렉터리 기준 상대 경로
3. **커버리지 경로**: `lcov.reportPaths`는 모듈 디렉터리 기준 상대 경로
4. **전역 설정**: TypeScript 설정 등은 프로젝트 루트 레벨에서 설정

## 문제 해결

### 모듈을 찾을 수 없음
- `sonar.modules`에 모듈이 올바르게 나열되어 있는지 확인
- `{module}.sonar.projectBaseDir` 경로가 정확한지 확인

### 커버리지가 표시되지 않음
- 각 모듈에서 `npm run test:coverage` 실행 확인
- `{module}.sonar.javascript.lcov.reportPaths` 경로 확인

### TypeScript 파일이 분석되지 않음
- 루트 레벨의 `sonar.typescript.tsconfigPath` 확인
- 각 모듈의 tsconfig.json 파일 존재 여부 확인