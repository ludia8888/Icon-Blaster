# Arrakis-Project

> 🏛️ Enterprise-level Ontology Management System inspired by Palantir Foundry

## Overview

Arrakis-Project는 비개발자도 쉽게 메타데이터를 정의하고 관리할 수 있는 엔터프라이즈급 온톨로지 관리 시스템(OMS)입니다. Palantir Foundry의 온톨로지 에디터 수준의 기능을 오픈소스로 제공하여, 조직 내 데이터 통합과 공유 어휘 관리를 지원합니다.

## 🎯 Key Features

- **드래그앤드롭 GUI**: 코드 작성 없이 Object Type, Property, Link Type 정의
- **실시간 협업**: 버전 관리 및 동시 편집 충돌 해결
- **엔터프라이즈 보안**: RBAC, OAuth2/OIDC, 감사 로깅
- **확장 가능한 아키텍처**: Kubernetes 기반 마이크로서비스
- **외부 시스템 연동**: ElasticSearch, Neo4j, Kafka 통합

## 🛠️ Tech Stack

### Frontend

- React 18 + TypeScript
- BlueprintJS (UI Components)
- Zustand (State Management)
- Canvas API (Visual Editor)

### Backend

- Node.js + Express + TypeScript
- PostgreSQL + TypeORM
- Redis (Caching & Locking)
- Kafka (Event Streaming)

### Infrastructure

- Kubernetes + Helm
- Docker
- GitHub Actions (CI/CD)
- Prometheus + Grafana (Monitoring)

## 📦 Project Structure

```
arrakis-project/
├── packages/
│   ├── frontend/       # React 애플리케이션
│   ├── backend/        # Express API 서버
│   ├── shared/         # 공통 타입 및 유틸리티
│   └── contracts/      # API 계약 (OpenAPI)
├── infrastructure/     # Terraform, K8s 설정
├── docs/              # 프로젝트 문서
└── tools/             # 개발 도구 및 스크립트
```

## 🚀 Getting Started

### Prerequisites

- Node.js >= 18.0.0
- npm >= 9.0.0
- PostgreSQL >= 13
- Redis >= 6.0

### Installation

```bash
# Clone repository
git clone https://github.com/ludia8888/Arrakis-Project.git
cd Arrakis-Project

# Install dependencies
npm install

# Build shared package
npm run build --workspace=@arrakis/shared
```

### Development

```bash
# Run all services in development mode
npm run dev

# Run tests
npm test

# Run tests with coverage
npm run test:coverage
```

## 📊 Development Progress

### Completed ✅

- [x] 프로젝트 초기 구조 설정
- [x] TypeScript 설정 (strict mode)
- [x] ESLint/Prettier 설정
- [x] Shared 패키지 (기본 타입 정의)
- [x] 100% 테스트 커버리지 (shared)
- [x] Contracts 패키지 (API 계약)
  - [x] Zod 스키마 검증
  - [x] OpenAPI 3.0 스펙
  - [x] 97%+ 테스트 커버리지
- [x] Backend API 서버 기본 구조
  - [x] Express + TypeScript 설정
  - [x] Health check 엔드포인트
  - [x] 에러 핸들링 미들웨어
  - [x] CORS 설정
  - [x] TypeORM + PostgreSQL 설정
  - [x] 기본 엔티티 (ObjectType, Property, LinkType)
  - [x] JWT 인증 미들웨어
  - [x] 역할 기반 접근 제어 (RBAC)
  - [x] 94%+ 테스트 커버리지

### In Progress 🔄

- [ ] ObjectType Repository 계층
- [ ] ObjectType Service 계층
- [ ] ObjectType Controller 및 REST API

### Planned 📋

- [ ] Frontend 애플리케이션 구조
- [ ] 인증 시스템 (Keycloak 연동)
- [ ] Property CRUD API
- [ ] Link Type CRUD API
- [ ] Canvas UI 컴포넌트
- [ ] 버전 관리 시스템
- [ ] ElasticSearch/Neo4j 연동

## 🧪 Testing Strategy

모든 개발은 **TDD (Test-Driven Development)** 원칙을 따릅니다:

- 함수는 10-30줄로 제한
- 단일 책임 원칙 준수
- 90% 이상 테스트 커버리지 목표

## 📄 Documentation

- [PRD (Product Requirements)](./PRD.md)
- [Design Document](./DesignDoc.md)
- [Frontend Specification](./FrontendSpec.md)
- [Backend Specification](./BackendSpec.md)
- [Infrastructure Specification](./InfraSpec.md)
- [QA Specification](./QASpec.md)

## 🤝 Contributing

이 프로젝트는 엔터프라이즈급 품질을 목표로 합니다. 기여 시 [CLAUDE-RULES.md](./CLAUDE-RULES.md)의 개발 원칙을 준수해주세요.

## 📝 License

MIT License - see [LICENSE](./LICENSE) for details

## 🙏 Acknowledgments

- Inspired by [Palantir Foundry](https://www.palantir.com/platforms/foundry/)
- Built with Claude AI assistance following enterprise best practices
