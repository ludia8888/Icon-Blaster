# 📚 OMS 문서 인덱스

## 🏗️ 아키텍처 및 설계
- [시스템 아키텍처](/ARCHITECTURE.md) - 전체 시스템 구조 및 설계
- [README](/README.md) - 프로젝트 개요 및 빠른 시작 가이드

## 🔐 보안 및 인증
- [인증 마이그레이션 가이드](AUTHENTICATION_MIGRATION.md) - 통합 인증으로 마이그레이션
- [서비스 계정 정책](SERVICE_ACCOUNT_POLICY.md) - 서비스 계정 관리 정책

## 🚀 배포 및 운영
- [프로덕션 배포 가이드](/migrations/PRODUCTION_DEPLOYMENT_README.md) - 프로덕션 환경 배포 절차
- [미들웨어 마이그레이션 가이드](/middleware/MIGRATION_GUIDE.md) - 미들웨어 업그레이드 가이드

## 📖 API 문서
- [Time Travel Queries API](api/time_travel_queries.md) - 시간 여행 쿼리 API 레퍼런스

## 🧩 모듈별 문서
- [감사 서비스](/core/audit/README.md) - 감사 추적 모듈
- [Rust 통합](/core/rust_integration/README.md) - Rust 바인딩 및 통합

## 📦 아카이브
완료되었거나 더 이상 사용되지 않는 문서들은 [archive/legacy/](archive/legacy/) 디렉토리에 보관되어 있습니다.

---

## 문서 관리 정책

### 활성 문서
- 현재 시스템과 일치하는 최신 정보 유지
- 주요 변경사항 발생 시 즉시 업데이트
- 명확한 버전 표시 (해당되는 경우)

### 아카이브 정책
- 완료된 마이그레이션 가이드
- 구현 완료된 계획 문서
- 더 이상 사용되지 않는 API 문서
- 6개월 이상 업데이트되지 않은 임시 문서

### 문서 작성 가이드라인
1. **명확한 제목**: 문서의 목적을 명확히 표현
2. **날짜 표시**: 작성일 및 최종 수정일 명시
3. **대상 독자**: 문서를 읽을 대상 명시
4. **실행 가능한 예제**: 코드 예제는 실제로 동작해야 함
5. **링크 검증**: 내부/외부 링크가 유효한지 확인