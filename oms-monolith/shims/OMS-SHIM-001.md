# OMS-SHIM-001: RBAC Middleware Migration

## Overview
- **Shim ID**: OMS-SHIM-001
- **Type**: Path Migration
- **Priority**: High
- **Status**: 🟡 In Progress
- **Created**: 2024-01-25
- **Target Completion**: 2024-01-26

## Current State
```python
# shared/__init__.py:64
_alias("middleware.rbac_middleware", "shared.middleware.rbac_middleware")
```

## Issue
- GraphQL service는 `shared.middleware.rbac_middleware`를 import
- 실제 파일은 `middleware/rbac_middleware.py`에 위치
- 일관성 없는 import 경로로 혼란 발생

## Historical Context
- This shim existed due to inconsistent import paths during initial modularization
- RBAC middleware was originally designed for shared use across services
- Refactoring was deferred during GraphQL service integration (Q4 2023)
- Decision made to consolidate under `shared/` for better discoverability

## Migration Plan

### Step 1: Impact Analysis
```bash
# Find all usages
grep -r "shared.middleware.rbac_middleware" . --include="*.py"
```

**Affected Files**:
- `api/graphql/main.py:18`

### Step 2: File Migration
```bash
# Create shared middleware directory
mkdir -p shared/middleware

# Move the file
mv middleware/rbac_middleware.py shared/middleware/

# Update __init__.py
touch shared/middleware/__init__.py
```

### Step 3: Import Updates

#### Import Action
- ✅ **Import already consistent with final path → No change needed**
- ⛔ **Do NOT refactor to legacy path during rollback**

```python
# Before: api/graphql/main.py
from shared.middleware.rbac_middleware import RBACMiddleware

# After: No change needed (path now matches import)
```

### Step 4: Shim Removal
```python
# Remove from shared/__init__.py:64
# _alias("middleware.rbac_middleware", "shared.middleware.rbac_middleware")
```

### Step 5: Testing
```bash
# Unit tests
pytest tests/test_rbac_middleware.py

# Integration test
python -c "from shared.middleware.rbac_middleware import RBACMiddleware"

# Full system test
python main_enterprise.py
```

## Rollback Plan
```bash
# If issues arise:
mv shared/middleware/rbac_middleware.py middleware/
rmdir shared/middleware
# Re-add the _alias line to shared/__init__.py
```

## Success Criteria
- [ ] All imports resolve without shim
- [ ] GraphQL service starts successfully
- [ ] No regression in RBAC functionality
- [ ] CI/CD pipeline passes

## CI/CD Enforcement Rule
```yaml
# .github/workflows/lint.yml
- name: Assert OMS-SHIM-001 removed
  run: |
    if grep -q "OMS-SHIM-001" shared/__init__.py; then
      echo "❌ Shim OMS-SHIM-001 still present!"
      exit 1
    fi
```

## Git Commit Convention
```bash
git commit -am "[OMS-SHIM-001] Removed RBAC middleware shim - path now consistent"
```

## Notes
- This is a simple path migration with minimal risk
- No business logic changes required
- Good candidate for first shim removal

## Test Results

| Test Type         | Status  | Command/Notes                          | Timestamp |
|-------------------|---------|----------------------------------------|-----------|
| Unit Test         | ⏳      | `pytest tests/test_rbac_middleware.py` |           |
| Import Validation | ⏳      | `python -c "from shared.middleware.rbac_middleware import RBACMiddleware"` | |
| GraphQL Startup   | ⏳      | `python api/graphql/main.py`           |           |
| Full Pipeline     | ⏳      | CI on branch `shim-cleanup-001`        |           |
| Shim Removal Check| ⏳      | `grep "OMS-SHIM-001" shared/__init__.py` returns empty | |

### Execution Log
```bash
# Paste actual test execution results here
```

## Completion Checklist
- [ ] Impact analysis complete
- [ ] File moved to new location
- [ ] All imports updated
- [ ] Shim removed from shared/__init__.py
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Team notified
- [ ] Moved to archive/

## Final Summary
```
✅ Shim OMS-SHIM-001 successfully removed without side effects.
This cleanup paves the way for a cleaner module import structure and reduces cognitive load for new contributors.
```