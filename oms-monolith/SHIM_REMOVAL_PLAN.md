# Compatibility Shim 제거 계획

## 목표: Shim 0개 = 깨끗한 코드베이스

### 현재 상태 (2024-01-25)
- 총 Shim 개수: 9개
- 영향받는 파일: 37개
- 해결된 import 오류: 253개

### Shim 제거 우선순위

#### Phase 1: 단순 경로 수정 (1-2일)
```python
# TODO(#OMS-SHIM-001): middleware.rbac_middleware
_alias("middleware.rbac_middleware", "shared.middleware.rbac_middleware")
# → Action: middleware/rbac_middleware.py를 shared/middleware/로 이동
```

#### Phase 2: 네임스페이스 정리 (3-5일)
```python
# TODO(#OMS-SHIM-002): services.* → core.*
_alias("core.event_publisher.models", "services.event_publisher.core.models")
# → Action: 모든 services.* import를 core.*로 일괄 변경
```

#### Phase 3: 모듈 통합 (1주일)
```python
# TODO(#OMS-SHIM-003): Auth 모듈 통합
_alias("api.gateway.auth", "shared.auth")
# → Action: 공통 Auth 인터페이스 추출하여 shared/auth/ 생성
```

### 진행 상황 추적

| Shim ID | 설명 | 상태 | 제거 예정일 |
|---------|------|------|------------|
| OMS-SHIM-001 | rbac_middleware | 🟡 진행중 | 2024-01-26 |
| OMS-SHIM-002 | services namespace | 🔴 대기 | 2024-01-28 |
| OMS-SHIM-003 | auth module | 🔴 대기 | 2024-01-30 |

### 제거 프로세스

1. **Shim 하나 선택**
   ```bash
   grep "TODO(#OMS-SHIM" shared/__init__.py
   ```

2. **영향 분석**
   ```bash
   python scripts/verify_imports.py | grep "해당_모듈"
   ```

3. **실제 모듈 이동/수정**
   ```bash
   # 예: rbac_middleware 이동
   mkdir -p shared/middleware
   mv middleware/rbac_middleware.py shared/middleware/
   ```

4. **Import 경로 수정**
   ```bash
   # 모든 파일에서 import 경로 변경
   find . -name "*.py" -exec sed -i 's/shared\.middleware\.rbac_middleware/middleware.rbac_middleware/g' {} \;
   ```

5. **Shim 제거**
   ```python
   # shared/__init__.py에서 해당 _alias() 호출 삭제
   ```

6. **테스트**
   ```bash
   python test_imports.py
   python -m pytest tests/
   ```

### 성공 지표

- [ ] `grep "_alias" shared/__init__.py | wc -l` → 0
- [ ] `python scripts/verify_imports.py` → "All imports resolved"
- [ ] 모든 테스트 통과
- [ ] CI/CD 파이프라인 정상 작동

### 주의사항

1. **작은 단위로 진행**: 한 번에 하나의 Shim만 제거
2. **백업 필수**: 각 단계마다 git commit
3. **팀 공유**: Shim 제거 전 팀에 공지
4. **점진적 배포**: 각 Shim 제거 후 staging 환경 테스트

### 완료 후 정리

Shim이 모두 제거되면:
1. `shared/__init__.py`를 원래 상태로 복원
2. `SHIM_REMOVAL_PLAN.md` 아카이브
3. 팀 회고 및 문서화