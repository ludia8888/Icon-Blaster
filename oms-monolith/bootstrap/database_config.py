"""
Database Configuration for Unified Approach
Configures the system to use TerminusDB as primary with PostgreSQL/SQLite fallback

MIGRATION PATH:
1. Phase 1: Dual-write mode (write to both old and new)
2. Phase 2: Read from TerminusDB, write to both
3. Phase 3: TerminusDB only
4. Phase 4: Deprecate legacy audit tables
"""

import os
from enum import Enum
from typing import Dict, Any, Optional

from database.clients.unified_database_client import UnifiedDatabaseClient, DatabaseBackend
from core.audit.audit_migration_adapter import AuditMigrationAdapter
from core.audit.terminusdb_audit_service import TerminusAuditService
from utils.logger import get_logger

logger = get_logger(__name__)


class AuditMigrationPhase(Enum):
    """Phases of audit system migration"""
    LEGACY_ONLY = "legacy_only"          # Use only SQLite/PostgreSQL
    DUAL_WRITE = "dual_write"           # Write to both, read from legacy
    READ_TERMINUS = "read_terminus"      # Write to both, read from TerminusDB
    TERMINUS_ONLY = "terminus_only"      # Use only TerminusDB
    

class DatabaseConfig:
    """
    Unified database configuration
    
    Determines which backends to use based on environment and migration phase
    """
    
    def __init__(self):
        self.env = os.getenv("APP_ENV", "development")
        self.migration_phase = AuditMigrationPhase(
            os.getenv("AUDIT_MIGRATION_PHASE", "dual_write")
        )
        
        # TerminusDB configuration
        self.terminus_config = {
            "server_url": os.getenv("TERMINUSDB_URL", "http://localhost:6363"),
            "user": os.getenv("TERMINUSDB_USER", "admin"),
            "key": os.getenv("TERMINUSDB_KEY", "root"),
            "account": os.getenv("TERMINUSDB_ACCOUNT", "admin"),
            "team": os.getenv("TERMINUSDB_TEAM", "admin")
        }
        
        # PostgreSQL configuration (for specific use cases)
        self.postgres_config = None
        if os.getenv("DATABASE_URL"):
            # Parse DATABASE_URL
            from urllib.parse import urlparse
            parsed = urlparse(os.getenv("DATABASE_URL"))
            self.postgres_config = {
                "host": parsed.hostname,
                "port": parsed.port or 5432,
                "database": parsed.path[1:],  # Remove leading /
                "user": parsed.username,
                "password": parsed.password
            }
        
        # SQLite configuration (fallback)
        self.sqlite_config = {
            "db_name": "oms_unified.db",
            "db_dir": os.getenv("SQLITE_DATA_DIR", "/data/sqlite")
        }
        
        # Routing configuration
        self.routing_overrides = self._get_routing_overrides()
    
    def _get_routing_overrides(self) -> Dict[str, DatabaseBackend]:
        """
        Get routing overrides based on environment
        
        Allows specific data types to be routed to specific backends
        """
        overrides = {}
        
        if self.env == "production":
            # In production, use PostgreSQL for high-frequency data
            overrides.update({
                "metric": DatabaseBackend.POSTGRESQL,
                "session": DatabaseBackend.POSTGRESQL,
                "lock": DatabaseBackend.POSTGRESQL
            })
        
        # During migration, route audit based on phase
        if self.migration_phase == AuditMigrationPhase.LEGACY_ONLY:
            overrides["audit"] = DatabaseBackend.POSTGRESQL if self.postgres_config else DatabaseBackend.SQLITE
        else:
            overrides["audit"] = DatabaseBackend.TERMINUSDB
        
        return overrides
    
    async def get_unified_client(self) -> UnifiedDatabaseClient:
        """Get configured unified database client"""
        client = UnifiedDatabaseClient(
            terminus_config=self.terminus_config,
            postgres_config=self.postgres_config,
            sqlite_config=self.sqlite_config,
            default_backend=DatabaseBackend.TERMINUSDB
        )
        
        # Apply routing overrides
        client._routing_rules.update(self.routing_overrides)
        
        await client.connect()
        return client
    
    async def get_audit_adapter(self) -> AuditMigrationAdapter:
        """Get audit adapter based on migration phase"""
        unified_client = await self.get_unified_client()
        
        # Configure based on migration phase
        if self.migration_phase == AuditMigrationPhase.LEGACY_ONLY:
            # Use only legacy audit
            from core.audit.audit_database import AuditDatabase
            
            if self.postgres_config:
                legacy_audit = AuditDatabase(
                    use_postgres=True,
                    postgres_config=self.postgres_config
                )
            else:
                legacy_audit = AuditDatabase(
                    db_path=self.sqlite_config["db_dir"]
                )
            
            return AuditMigrationAdapter(
                legacy_audit=legacy_audit,
                migration_mode="read_legacy"
            )
        
        elif self.migration_phase == AuditMigrationPhase.TERMINUS_ONLY:
            # Use only TerminusDB
            terminus_audit = TerminusAuditService(unified_client._terminus_client)
            
            return AuditMigrationAdapter(
                terminus_audit=terminus_audit,
                unified_client=unified_client,
                migration_mode="terminus_only"
            )
        
        else:
            # Dual mode - use both
            from core.audit.audit_database import AuditDatabase
            
            # Setup legacy
            if self.postgres_config:
                legacy_audit = AuditDatabase(
                    use_postgres=True,
                    postgres_config=self.postgres_config
                )
            else:
                legacy_audit = AuditDatabase(
                    db_path=self.sqlite_config["db_dir"]
                )
            
            # Setup TerminusDB
            terminus_audit = TerminusAuditService(unified_client._terminus_client)
            
            # Determine mode
            if self.migration_phase == AuditMigrationPhase.DUAL_WRITE:
                mode = "dual_write"
            else:  # READ_TERMINUS
                mode = "read_terminus"
            
            return AuditMigrationAdapter(
                legacy_audit=legacy_audit,
                terminus_audit=terminus_audit,
                unified_client=unified_client,
                migration_mode=mode
            )
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status"""
        return {
            "environment": self.env,
            "migration_phase": self.migration_phase.value,
            "backends": {
                "terminus": self.terminus_config["server_url"],
                "postgres": bool(self.postgres_config),
                "sqlite": self.sqlite_config["db_name"]
            },
            "routing_overrides": {
                k: v.value for k, v in self.routing_overrides.items()
            }
        }


# Global configuration instance
_db_config: Optional[DatabaseConfig] = None


def get_database_config() -> DatabaseConfig:
    """Get global database configuration"""
    global _db_config
    if not _db_config:
        _db_config = DatabaseConfig()
    return _db_config


async def initialize_unified_database():
    """Initialize the unified database system"""
    config = get_database_config()
    
    logger.info(f"Initializing unified database system")
    logger.info(f"Environment: {config.env}")
    logger.info(f"Migration phase: {config.migration_phase.value}")
    
    # Get unified client
    client = await config.get_unified_client()
    
    # Get audit adapter
    audit = await config.get_audit_adapter()
    await audit.initialize()
    
    logger.info("Unified database system initialized successfully")
    
    return {
        "client": client,
        "audit": audit,
        "config": config
    }


# Migration utilities

async def run_audit_migration(
    start_date: Optional[str] = None,
    batch_size: int = 1000
) -> Dict[str, Any]:
    """
    Run one-time migration of audit data from legacy to TerminusDB
    
    Should be run during DUAL_WRITE phase
    """
    config = get_database_config()
    
    if config.migration_phase != AuditMigrationPhase.DUAL_WRITE:
        return {
            "error": "Migration should only be run during DUAL_WRITE phase",
            "current_phase": config.migration_phase.value
        }
    
    audit_adapter = await config.get_audit_adapter()
    await audit_adapter.initialize()
    
    # Parse start date
    from datetime import datetime
    start_datetime = None
    if start_date:
        start_datetime = datetime.fromisoformat(start_date)
    
    # Run migration
    result = await audit_adapter.migrate_historical_data(
        start_date=start_datetime,
        batch_size=batch_size
    )
    
    logger.info(f"Audit migration completed: {result}")
    return result


async def verify_audit_migration(sample_size: int = 100) -> Dict[str, Any]:
    """
    Verify consistency between legacy and TerminusDB audit data
    
    Useful during DUAL_WRITE or READ_TERMINUS phases
    """
    config = get_database_config()
    
    if config.migration_phase not in [AuditMigrationPhase.DUAL_WRITE, AuditMigrationPhase.READ_TERMINUS]:
        return {
            "error": "Verification only available during DUAL_WRITE or READ_TERMINUS phases",
            "current_phase": config.migration_phase.value
        }
    
    audit_adapter = await config.get_audit_adapter()
    await audit_adapter.initialize()
    
    result = await audit_adapter.verify_migration_consistency(sample_size)
    
    logger.info(f"Audit migration verification: {result}")
    return result