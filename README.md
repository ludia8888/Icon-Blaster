# 🚀 Arrakis Project - Enterprise Ontology Management System

> **차세대 온톨로지 관리 플랫폼 with TerminusDB**

## 📋 프로젝트 개요

Arrakis Project는 TerminusDB를 기반으로 한 엔터프라이즈급 온톨로지 관리 시스템(OMS)입니다. 복잡한 데이터 모델과 관계를 체계적으로 관리하고, 현대적인 API와 고급 기능을 통해 대규모 조직의 데이터 거버넌스를 지원합니다.

## ✨ 핵심 기능

### 🎯 온톨로지 관리
- 객체 타입(ObjectType) 정의 및 관리
- 속성(Property) 시스템
- 링크 타입(LinkType) 관계 모델링
- 인터페이스 및 상속 지원

### 🚀 고급 기능 (2024.12 업데이트)
- **🧠 Vector Embeddings**: 7개 AI 프로바이더 지원
- **🔗 GraphQL Deep Linking**: 효율적인 그래프 탐색
- **💾 Redis SmartCache**: 3-tier 지능형 캐싱
- **🔍 Jaeger Tracing**: 분산 시스템 추적
- **⏰ Time Travel Queries**: 시간 기반 데이터 조회
- **📦 Delta Encoding**: 효율적인 버전 저장
- **📄 @unfoldable Documents**: 선택적 콘텐츠 로딩
- **📝 @metadata Frames**: 구조화된 문서 메타데이터

## 🏗️ 시스템 아키텍처

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Clients   │────▶│ API Gateway │────▶│   Services  │
└─────────────┘     └─────────────┘     └─────────────┘
                            │                    │
                            ▼                    ▼
                    ┌─────────────┐     ┌─────────────┐
                    │    Redis    │     │ TerminusDB  │
                    │   (Cache)   │     │  (GraphDB)  │
                    └─────────────┘     └─────────────┘
```

## 🚀 빠른 시작

### 1. 저장소 클론
```bash
git clone https://github.com/ludia8888/Arrakis-Project.git
cd Arrakis-Project
```

### 2. Docker로 실행
```bash
cd oms-monolith
docker-compose up -d
```

### 3. 서비스 접속
- **REST API**: http://localhost:8000
- **API 문서**: http://localhost:8000/docs
- **GraphQL**: http://localhost:8006/graphql
- **Grafana**: http://localhost:3000
- **Jaeger**: http://localhost:16686

## 📚 프로젝트 구조

```
Arrakis-Project/
├── oms-monolith/           # 메인 애플리케이션
│   ├── api/                # API 엔드포인트
│   ├── core/               # 핵심 비즈니스 로직
│   ├── models/             # 데이터 모델
│   ├── services/           # 서비스 레이어
│   └── tests/              # 테스트 코드
├── ARCHITECTURE_EXTENDED.md # 상세 아키텍처 문서
├── FEATURES.md             # 기능 가이드
└── README.md               # 이 문서
```

## 📖 문서

- **[메인 README](oms-monolith/README.md)**: 상세 구현 가이드
- **[확장 아키텍처](ARCHITECTURE_EXTENDED.md)**: 시스템 설계 상세
- **[기능 가이드](FEATURES.md)**: 9가지 확장 기능 사용법
- **[통합 테스트](INTEGRATION_TEST_README.md)**: 테스트 가이드

## 🛠️ 기술 스택

### Backend
- **Python 3.11+**: 메인 언어
- **FastAPI**: REST API 프레임워크
- **Strawberry GraphQL**: GraphQL 서버
- **TerminusDB**: 그래프 데이터베이스
- **PostgreSQL**: 관계형 데이터베이스
- **Redis**: 캐시 및 세션 스토어

### 모니터링
- **Prometheus**: 메트릭 수집
- **Grafana**: 시각화 대시보드
- **Jaeger**: 분산 추적

### 보안
- **JWT**: 토큰 기반 인증
- **RBAC**: 역할 기반 접근 제어
- **mTLS**: 상호 TLS 인증

## 🔧 개발 환경 설정

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate

# 의존성 설치
cd oms-monolith
pip install -r requirements.txt

# 개발 서버 실행
python main.py
```

## 🧪 테스트

```bash
# 단위 테스트
pytest tests/unit/

# 통합 테스트
pytest tests/integration/

# 전체 테스트
pytest --cov=. tests/
```

## 🤝 기여 방법

1. Fork 저장소
2. Feature 브랜치 생성 (`git checkout -b feature/amazing-feature`)
3. 변경사항 커밋 (`git commit -m 'Add amazing feature'`)
4. 브랜치 푸시 (`git push origin feature/amazing-feature`)
5. Pull Request 생성

## 📄 라이선스

MIT License - 자세한 내용은 [LICENSE](LICENSE) 파일 참조

## 👥 팀

- **아키텍처 설계**: Claude AI Assistant
- **시스템 구현**: 이시현 (isihyeon)
- **TerminusDB 확장**: Claude & 이시현

## 🔗 관련 링크

- **GitHub**: https://github.com/ludia8888/Arrakis-Project
- **이슈 트래커**: https://github.com/ludia8888/Arrakis-Project/issues
- **위키**: https://github.com/ludia8888/Arrakis-Project/wiki

---

**Arrakis Project** - *"복잡한 데이터의 사막을 항해하는 나침반"* 🧭

> 이 프로젝트는 Frank Herbert의 Dune 시리즈에서 영감을 받아, 데이터의 광대한 사막(Arrakis)을 효과적으로 관리하고 탐색할 수 있는 도구를 제공합니다.