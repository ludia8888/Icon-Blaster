# OMS-SHIM-003: shared.auth → api.gateway.auth

## Overview
- **Shim ID**: OMS-SHIM-003
- **Type**: Path Migration
- **Priority**: High
- **Status**: 🔴 Pending
- **Created**: 2025-06-25
- **Target Completion**: 2025-06-25

## Current State
```python
# shared/__init__.py:68
_alias("api.gateway.auth", "shared.auth")
```

## Issue
- Code expects to import from `shared.auth`
- Actual module is at `api.gateway.auth`
- Import path doesn't match actual file location

## Historical Context
- [Why did this shim come to exist?]
- [What was the original design decision?]
- [Why was refactoring deferred?]
- [What is the target architecture?]

## Risk Assessment
- **Risk Level**: [Low|Medium|High]
- **Reasons**:
  - [ ] Simple path change only
  - [ ] Affects core business logic
  - [ ] Changes architectural semantics
  - [ ] Impacts testing strategies

## Migration Plan

### Step 1: Impact Analysis
```bash
# Find all usages
grep -r "shared.auth" . --include="*.py"
```

**Affected Files**:
- - `api/graphql/resolvers.py:11`
- `api/graphql/subscriptions.py:13`
- `api/graphql/main.py:25`
- `api/graphql/main.py:25`
- `path/to/file2.py:LINE`

### Step 2: File/Module Changes
```bash
# Commands to execute the migration
mkdir -p shared
mv api/gateway/auth.py shared/auth
```

### Step 3: Import Updates

#### Import Action
- [ ] ✅ Import already consistent with final path → No change needed
- [ ] ⚠️  Import needs update in X files
- [ ] ⛔ Do NOT refactor to legacy path during rollback

```python
# Before:
from shared.auth import Something

# After:
from shared.auth import [ClassName]
```

### Step 4: Shim Removal
```python
# Remove from shared/__init__.py:68
# _alias("api.gateway.auth", "shared.auth")
```

### Step 5: Testing
```bash
# Test commands
pytest tests/relevant_test.py
python -c "from shared.auth import [ClassName]"
python main_enterprise.py
```

## Rollback Plan
```bash
# Steps to rollback if issues arise
mv shared/authfile.py old/
# Re-add the _alias line to shared/__init__.py
```

## Success Criteria
- [ ] All imports resolve without shim
- [ ] No functionality regression
- [ ] All tests passing
- [ ] CI/CD pipeline passes

## CI/CD Enforcement Rule
```yaml
# .github/workflows/lint.yml
- name: Assert OMS-SHIM-003 removed
  run: |
    if grep -q "OMS-SHIM-003" shared/__init__.py; then
      echo "❌ Shim OMS-SHIM-003 still present!"
      exit 1
    fi
```

## Git Commit Convention
```bash
git commit -am "[OMS-SHIM-003] Brief description of what was removed"
```

## Notes
- [Any special considerations]
- [Dependencies on other shims]
- [Team coordination needed]

## Test Results

| Test Type         | Status  | Command/Notes                          | Timestamp |
|-------------------|---------|----------------------------------------|-----------|
| Unit Test         | ⏳      | `pytest tests/...`                     |           |
| Import Validation | ⏳      | `python -c "..."`                      |           |
| Integration Test  | ⏳      | `...`                                  |           |
| Full Pipeline     | ⏳      | CI on branch `shim-cleanup-XXX`        |           |
| Shim Removal Check| ⏳      | `grep "OMS-SHIM-003" shared/__init__.py` returns empty | |

### Execution Log
```bash
# Paste actual test execution results here
```

## Completion Checklist
- [ ] Historical context documented
- [ ] Impact analysis complete
- [ ] Migration executed
- [ ] All imports updated
- [ ] Shim removed from shared/__init__.py
- [ ] All tests passing
- [ ] CI enforcement rule added
- [ ] Documentation updated
- [ ] Team notified via [Slack|Email|PR]
- [ ] Moved to archive/

## Final Summary
```
✅ Shim OMS-SHIM-003 successfully removed without side effects.
[One sentence describing the improvement this brings]
```

---
**Author**: [Name]
**Reviewer**: [Name]
**PR Link**: #[NUMBER]