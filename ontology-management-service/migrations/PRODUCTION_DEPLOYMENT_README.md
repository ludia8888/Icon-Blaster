# Production Deployment Guide for IAM-TerminusDB Integration

## Overview
This guide covers the production deployment of the IAM-TerminusDB integration with secure author tracking.

## Pre-Deployment Checklist

### 1. Dependencies
Ensure all required dependencies are installed:
```bash
pip install -r requirements_updated.txt
```

Note: The httpx dependency issue has been fixed in `requirements_updated.txt`:
```
httpx[http2]>=0.25.2,<0.26
```

### 2. Environment Variables
Verify the following environment variables are set:
```bash
# TerminusDB Configuration
TERMINUS_DB_URL=https://your-terminus-instance.com
TERMINUS_DB_TEAM=your-team
TERMINUS_DB_TOKEN=your-token

# IAM Configuration
IAM_SERVICE_URL=https://your-iam-service.com
IAM_VERIFICATION_ENDPOINT=/api/v1/verify

# Monitoring
PROMETHEUS_PUSHGATEWAY_URL=http://your-prometheus:9091
DLQ_ALERT_WEBHOOK=https://your-alert-webhook.com
```

## Deployment Steps

### Step 1: Analyze Current Schema (Dry Run)
First, run the migration in dry-run mode to analyze the current schema:

```bash
cd /path/to/oms-monolith
python migrations/production_audit_fields_migration.py --env production --dry-run
```

This will:
- Connect to TerminusDB
- Analyze all document types
- Identify types that need audit fields
- Generate a migration plan
- Save a report without making changes

### Step 2: Review Migration Plan
The dry-run will create a JSON report: `migration_report_audit_fields_[timestamp].json`

Review this report to ensure:
- All expected document types are included
- No system types are being modified
- The estimated duration is acceptable

### Step 3: Execute Migration
Once satisfied with the plan, execute the actual migration:

```bash
python migrations/production_audit_fields_migration.py --env production --execute
```

The script will:
1. Ask for confirmation before proceeding
2. Add audit fields to each document type
3. Validate the changes
4. Generate a final report

### Step 4: Start Monitoring
After migration, start the audit monitoring:

```bash
# In your application startup
from core.monitoring.audit_metrics import get_metrics_collector

metrics = get_metrics_collector()
await metrics.start_monitoring()
```

### Step 5: Configure Alerts
Set up alerts based on the DLQ thresholds:

```python
from core.monitoring.audit_metrics import get_alert_manager

alert_manager = get_alert_manager()
# Configure thresholds
alert_manager.alert_threshold = 100  # Alert if DLQ > 100 events
alert_manager.age_threshold_seconds = 3600  # Alert if events > 1 hour old
```

## Validation

### 1. Check Schema Updates
Verify audit fields were added to all document types:

```python
# Use TerminusDB console or API to inspect schema
# Each type should have: _created_by, _created_at, _updated_by, etc.
```

### 2. Test Write Operations
Test that writes include secure author tracking:

```bash
# Create a test document via API
curl -X POST https://your-api/api/v1/objects \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "test", "type": "ObjectType"}'
```

Check that the created document has:
- `_created_by`: User ID from JWT
- `_created_by_username`: Username from JWT
- `_created_at`: Current timestamp

### 3. Monitor Metrics
Check Prometheus metrics:

```
# Audit events
oms_audit_events_total{action="create",resource_type="ObjectType",success="true"}

# DLQ monitoring
oms_audit_dlq_size{dlq_type="fallback"}
oms_audit_dlq_oldest_event_age_seconds{dlq_type="fallback"}

# Service account operations
oms_service_account_operations_total{service_name="deployment",operation="create"}
```

## Rollback Plan

If issues arise, rollback procedure:

1. **Stop Application** - Prevent new writes
2. **Restore Schema** - Use TerminusDB backup to restore previous schema
3. **Clear DLQ** - Remove any failed audit events
4. **Restart Application** - With previous configuration

## Post-Deployment

### 1. Update Documentation
- Update API documentation with audit field descriptions
- Document service account requirements for IAM team

### 2. Configure Service Accounts
Work with IAM team to ensure service accounts have proper claims:
```json
{
  "sub": "svc_deployment",
  "type": "service",
  "service_account": true,
  "roles": ["service", "schema:write"]
}
```

### 3. Set Up Regular Reviews
Schedule quarterly reviews of:
- Service account permissions
- DLQ error patterns
- Audit log integrity

## Troubleshooting

### Common Issues

#### 1. Migration Fails with Permission Error
- Ensure the database user has `schema:admin` permission
- Check TerminusDB connection settings

#### 2. DLQ Growing Rapidly
- Check `/tmp/audit_dlq_*.jsonl` files for error patterns
- Common causes:
  - Network timeouts to audit backend
  - Invalid JWT tokens
  - Missing user context

#### 3. Metrics Not Appearing
- Verify Prometheus scraping configuration
- Check that metrics endpoint is exposed: `/metrics`

### Debug Commands

```bash
# Check DLQ files
ls -la /tmp/audit_dlq_*.jsonl
tail -f /tmp/audit_dlq_fallback.jsonl | jq .

# Test JWT verification
curl -X GET https://your-api/api/v1/iam/verify-service-account \
  -H "Authorization: Bearer $SERVICE_JWT"

# Check audit logs
curl -X GET https://your-api/api/v1/audit/logs?limit=10
```

## Contact

For issues or questions:
- Security Team: security@company.com
- IAM Team: iam@company.com
- DevOps: devops@company.com