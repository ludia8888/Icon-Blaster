# OMS-SHIM-002: Services Namespace Migration

## Overview
- **Shim ID**: OMS-SHIM-002
- **Type**: Namespace Restructuring
- **Priority**: Medium
- **Status**: 🔴 Pending
- **Created**: 2024-01-25
- **Target Completion**: 2024-01-28

## Current State
```python
# Multiple shims for services.* namespace
_alias("core.event_publisher.models", "services.event_publisher.core.models")
_alias("core.event_publisher.state_store", "services.event_publisher.core.state_store")
_alias("api.gateway.auth", "services.api_gateway.core.auth")
_alias("api.gateway.models", "services.api_gateway.core.models")
```

## Issue
- Code expects `services.*` namespace (MSA mindset)
- Actual code is in `core.*` and `api/*` (modular monolith)
- Semantic mismatch: "service boundary" vs "domain logic"

## Risk Assessment
⚠️ **High Risk**: This is not just a path change but a conceptual shift
- `services.*` implies deployment-level boundaries
- `core.*` implies domain logic layer
- May affect testing strategies and mocking patterns

## Migration Strategy

### Phase 1: Create Legacy Bridge (Low Risk)
```bash
# Create intermediate legacy path
mkdir -p core/legacy/event_publisher
mkdir -p core/legacy/api_gateway

# Copy (not move) to maintain compatibility
cp core/event_publisher/models.py core/legacy/event_publisher/
cp core/event_publisher/state_store.py core/legacy/event_publisher/
```

### Phase 2: Gradual Import Migration
```python
# Step 1: Update to use legacy path
# Before: from services.event_publisher.core.models import *
# After:  from core.legacy.event_publisher.models import *

# Step 2: Eventually move to final path
# Final:  from core.event_publisher.models import *
```

### Phase 3: Testing Each Step
```bash
# After each file update:
python scripts/verify_imports.py | grep "services."
python -m pytest tests/
```

## Affected Files Analysis
```bash
# Get full impact
grep -r "services\." . --include="*.py" | grep -v "__pycache__"
```

**High Impact Files**:
- `core/event_publisher/change_detector.py`
- `api/gateway/router.py`
- `api/graphql/main.py`

## Rollback Plan
```bash
# Keep legacy directories for 2 weeks after migration
# If issues arise, update imports to point back to legacy/
```

## Success Criteria
- [ ] All `services.*` imports eliminated
- [ ] No functionality regression
- [ ] Test coverage maintained
- [ ] Performance benchmarks unchanged

## Alternative Approach
Consider keeping `services` namespace as an explicit "public API" layer:
```python
# services/__init__.py
"""Public API exports - stable interfaces"""
from core.event_publisher import EventPublisher as EventPublisherService
from core.validation import ValidationService
```

## Notes
- This migration affects architectural semantics
- Requires team consensus on namespace meaning
- Consider documenting the new structure in ADR

## Test Results
<!-- Add test results here after execution -->

## Completion Checklist
- [ ] Team consensus on approach
- [ ] Legacy bridge created
- [ ] Import migration script written
- [ ] Staged rollout plan approved
- [ ] All imports migrated
- [ ] Legacy bridge deprecated
- [ ] Shims removed
- [ ] Architecture documentation updated
- [ ] Moved to archive/