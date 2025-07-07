# Audit Service

Enterprise-grade audit logging service with compliance features and multi-database support.

## Features

### Core Capabilities
- **Immutable Audit Logs**: Tamper-resistant event storage with cryptographic hashing
- **Multi-Database Support**: SQLite (default) and PostgreSQL backends
- **Retention Management**: Configurable retention policies by event type (7 years default)
- **Data Integrity**: Event and batch hashing for tamper detection
- **Compliance Ready**: GDPR, SOX, and regulatory compliance support
- **High Performance**: Batch processing and connection pooling

### Database Backends

#### SQLite (Default)
- Zero configuration
- Local file storage
- WAL mode for concurrent access
- Suitable for single-instance deployments

#### PostgreSQL (Enterprise)
- Centralized audit repository
- High concurrency support
- Horizontal scalability
- Suitable for multi-instance deployments

## Architecture

```
┌─────────────────────┐
│   Application       │
│   Middleware        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐     ┌─────────────────────┐
│  Audit Service      │────▶│  Event Publisher    │
│  (audit_service.py) │     │  (NATS/Outbox)     │
└──────────┬──────────┘     └─────────────────────┘
           │
           ▼
┌─────────────────────┐
│  Database Interface │
│  (Abstraction Layer)│
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    ▼             ▼
┌─────────┐  ┌─────────┐
│ SQLite  │  │PostgreSQL│
│Connector│  │Connector │
└─────────┘  └─────────┘
```

## Usage

### Default SQLite Backend

```python
from core.audit.audit_database import get_audit_database
from models.audit_events import AuditEventV1

# Get default SQLite instance
audit_db = await get_audit_database()

# Store audit event
event = AuditEventV1(...)
success = await audit_db.store_audit_event(event)

# Query events
from models.audit_events import AuditEventFilter

filter_criteria = AuditEventFilter(
    start_time=start_date,
    end_time=end_date,
    actions=[AuditAction.SCHEMA_CREATE],
    limit=100
)
events, total = await audit_db.query_audit_events(filter_criteria)
```

### PostgreSQL Backend

```python
from core.audit.audit_database import initialize_audit_database

# Initialize with PostgreSQL
postgres_config = {
    "host": "localhost",
    "port": 5432,
    "database": "audit_db",
    "user": "audit_user",
    "password": "secure_password"
}

audit_db = await initialize_audit_database(
    use_postgres=True,
    postgres_config=postgres_config
)

# Use same API as SQLite
success = await audit_db.store_audit_event(event)
```

### Switching Backends at Runtime

```python
import os
from core.audit.audit_database import initialize_audit_database

# Use environment variable to control backend
use_postgres = os.getenv("AUDIT_USE_POSTGRES", "false").lower() == "true"

if use_postgres:
    audit_db = await initialize_audit_database(
        use_postgres=True,
        postgres_config={
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "audit_db"),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", "")
        }
    )
else:
    audit_db = await initialize_audit_database(
        db_path=os.getenv("AUDIT_DB_PATH", "/var/lib/audit")
    )
```

## Cross-Validation with TerminusDB

The Side-Car Validator provides cross-validation between audit logs and TerminusDB:

```python
from core.audit.sidecar_validator import create_sidecar_validator

# Create validator
validator = await create_sidecar_validator({
    "server": "http://localhost:6363",
    "database": "audit_validation",
    "organization": "myorg"
})

# Start automatic validation
await validator.start()

# Generate compliance report
report = await validator.generate_compliance_report(period_days=30)
```

### Validation Features
- **Automatic Sync Checking**: Detects missing events between systems
- **Retention Policy Validation**: Ensures compliance with configured policies
- **Data Integrity Verification**: Detects discrepancies in event data
- **Compliance Reporting**: Generates reports for auditors

## Retention Policies

Default retention periods by event type:

| Event Category | Retention Period | Examples |
|----------------|------------------|----------|
| Security Events | 7 years | Login, ACL changes |
| Schema Changes | 5 years | Schema/Object type CRUD |
| Branch Operations | 1-2 years | Create, merge branches |
| System Operations | 3-6 months | Indexing, maintenance |

## Database Schema

### SQLite Schema
```sql
CREATE TABLE audit_events (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    action TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    -- ... other fields ...
    event_hash TEXT NOT NULL,
    retention_until TIMESTAMP NOT NULL,
    archived BOOLEAN DEFAULT FALSE
);
```

### PostgreSQL Schema
```sql
CREATE TABLE audit_events (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    -- Same fields as SQLite
    created_year INTEGER GENERATED ALWAYS AS 
        (EXTRACT(YEAR FROM created_at)::INTEGER) STORED,
    created_month INTEGER GENERATED ALWAYS AS 
        (EXTRACT(MONTH FROM created_at)::INTEGER) STORED
);
```

## Monitoring

### Health Checks
```python
# Check database statistics
stats = await audit_db.get_audit_statistics()

# Verify integrity
integrity = await audit_db.verify_integrity()

# Check pool stats (PostgreSQL)
if audit_db.use_postgres:
    pool_stats = await audit_db._connector.connector.get_pool_stats()
```

### Metrics
- Total events stored
- Events by action type
- Success/failure rates
- Top actors
- Storage usage

## Migration Guide

### From SQLite to PostgreSQL

1. Export existing data:
```python
# Export from SQLite
sqlite_db = await get_audit_database()
filter = AuditEventFilter(limit=10000)
all_events, _ = await sqlite_db.query_audit_events(filter)
```

2. Import to PostgreSQL:
```python
# Import to PostgreSQL
pg_db = await get_postgres_audit_database(postgres_config)
for event_batch in chunks(all_events, 1000):
    await pg_db.store_audit_events_batch(event_batch)
```

## Best Practices

1. **Use Batch Operations**: For high-volume events, use `store_audit_events_batch()`
2. **Regular Cleanup**: Run `cleanup_expired_events()` periodically
3. **Monitor Integrity**: Schedule regular `verify_integrity()` checks
4. **Backup Strategy**: Implement regular backups, especially for SQLite files
5. **Connection Pooling**: Configure appropriate pool sizes for PostgreSQL

## Configuration

Environment variables:
- `AUDIT_USE_POSTGRES`: Enable PostgreSQL backend
- `AUDIT_DB_PATH`: SQLite database directory
- `POSTGRES_HOST`: PostgreSQL host
- `POSTGRES_PORT`: PostgreSQL port
- `POSTGRES_DB`: PostgreSQL database name
- `POSTGRES_USER`: PostgreSQL username
- `POSTGRES_PASSWORD`: PostgreSQL password

## Security

- All events are hashed for integrity verification
- Immutable design prevents tampering
- Archived events are retained for compliance
- Connection encryption supported for PostgreSQL
- Role-based access control recommended