# Service Account Policy

## Overview
This document defines the criteria for identifying and managing service accounts in the OMS system.

## Service Account Definition
A service account is a non-human identity used by applications, services, or automated processes to interact with the OMS API.

## Identification Criteria

### 1. JWT Claims
Service accounts are identified by the following JWT claims:

```json
{
  "sub": "svc_<service_name>",
  "type": "service",
  "service_account": true,
  "roles": ["service", ...],
  "iss": "oms-iam-service"
}
```

### 2. Naming Convention
- User ID format: `svc_<service_name>` (e.g., `svc_deployment`, `svc_etl_pipeline`)
- Username format: `<service_name>-service` (e.g., `deployment-service`, `etl-pipeline-service`)

### 3. Role Assignment
Service accounts MUST have at least one of these roles:
- `service` - Base service account role
- `service:read` - Read-only service account
- `service:write` - Write-enabled service account
- `service:admin` - Administrative service account

## Implementation

### UserContext Detection
```python
class UserContext:
    @property
    def is_service_account(self) -> bool:
        """Determine if this is a service account"""
        return any([
            self.user_id.startswith("svc_"),
            "service" in self.roles,
            self.metadata.get("service_account") is True,
            self.metadata.get("type") == "service"
        ])
```

### Secure Author Format
Service accounts are marked with `[service]` tag in commit authors:
```
deployment-service (svc_deploy) [service]|ts:2025-01-04T10:00:00Z
```

## Permissions

### Default Permissions
Service accounts have restricted permissions by default:
- No access to user management endpoints
- No access to audit configuration
- Limited to specific resource types based on service purpose

### Enhanced Permissions
Service accounts requiring elevated permissions must:
1. Be explicitly approved by security team
2. Have permissions scoped to specific resources
3. Be regularly audited for usage

## Audit Requirements

### Enhanced Logging
All service account actions are logged with:
- Service name and purpose
- Initiating system/process
- Reason for action (if provided)
- Resource scope

### Delegation Tracking
When service accounts act on behalf of users:
```
deployment-service (svc_deploy) [service] [delegated|on_behalf_of:alice.smith|reason:scheduled deployment]
```

## Security Controls

### 1. Key Rotation
- Service account credentials must be rotated every 90 days
- Automated rotation preferred via IAM integration

### 2. IP Restrictions
- Service accounts should be restricted to known IP ranges
- Exceptions require security approval

### 3. Rate Limiting
- Service accounts have higher rate limits than regular users
- Specific limits based on service requirements

### 4. Monitoring
- Anomaly detection for unusual service account behavior
- Alerts for service accounts accessing unexpected resources

## Common Service Accounts

| Service Name | User ID | Purpose | Permissions |
|-------------|---------|---------|-------------|
| Deployment | svc_deploy | CI/CD deployments | schema:write, branch:write |
| ETL Pipeline | svc_etl | Data synchronization | object:read, object:write |
| Monitoring | svc_monitor | Health checks, metrics | read-only |
| Backup | svc_backup | System backups | read-only + backup:write |
| Migration | svc_migrate | Schema migrations | schema:admin |

## Integration with IAM

### Registration Process
1. Service account request submitted with:
   - Service name and purpose
   - Required permissions
   - Owner/team contact
   - Expected usage patterns

2. Security review and approval

3. IAM creates service account with:
   - Appropriate JWT claims
   - Scoped permissions
   - Monitoring configuration

### Verification Endpoint
```
GET /api/v1/iam/verify-service-account
Authorization: Bearer <service-jwt>

Response:
{
  "is_service_account": true,
  "service_name": "deployment",
  "owner": "devops-team",
  "permissions": ["schema:write", "branch:write"],
  "last_rotated": "2024-10-04T10:00:00Z",
  "expires_at": "2025-01-04T10:00:00Z"
}
```

## Compliance

### SOX Requirements
- Service accounts must have documented business justification
- Quarterly access reviews required
- Segregation of duties enforced

### GDPR Considerations
- Service accounts processing personal data must be identified
- Data processing agreements required for external services
- Audit trail of all data access maintained