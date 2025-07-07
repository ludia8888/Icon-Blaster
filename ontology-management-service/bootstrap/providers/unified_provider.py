"""
Unified provider that doesn't rely on punq or dependency_injector
Temporary solution to fix DI framework conflicts
"""
import os
from typing import Optional
from database.clients.unified_database_client import UnifiedDatabaseClient, DatabaseBackend
from database.clients.postgres_client_secure import PostgresClientSecure
from database.clients.sqlite_client_secure import SQLiteClientSecure
from database.clients.terminus_db import TerminusDBClient
from bootstrap.config import get_config
from common_logging.setup import get_logger

logger = get_logger(__name__)

# Global instance cache
_db_client_instance: Optional[UnifiedDatabaseClient] = None


async def get_unified_db_client() -> UnifiedDatabaseClient:
    """
    Get or create a unified database client instance.
    Uses a simple singleton pattern to avoid DI framework conflicts.
    """
    global _db_client_instance
    
    logger.debug("get_unified_db_client called")
    
    if _db_client_instance is not None and _db_client_instance._connected:
        logger.debug("Returning existing database client instance")
        return _db_client_instance
    
    logger.info("Creating new unified database client...")
    
    config = get_config()
    logger.debug(f"Config loaded: environment={config.service.environment}")
    
    # Create TerminusDB client
    terminus_endpoint = os.environ.get("TERMINUSDB_ENDPOINT", "http://localhost:6363")
    terminus_user = os.environ.get("TERMINUSDB_USER", "admin")
    terminus_pass = os.environ.get("TERMINUSDB_PASSWORD", "changeme-admin-pass")
    
    logger.debug(f"Creating TerminusDB client: endpoint={terminus_endpoint}, user={terminus_user}")
    
    try:
        terminus_client = TerminusDBClient(
            endpoint=terminus_endpoint,
            username=terminus_user,
            password=terminus_pass
        )
        logger.info("TerminusDB client created successfully")
    except Exception as e:
        logger.error(f"Failed to create TerminusDB client: {type(e).__name__}: {str(e)}")
        raise
    
    # Create SQLite client as fallback
    sqlite_client = SQLiteClientSecure(config=config.sqlite.model_dump())
    
    # Create PostgreSQL client if configured
    postgres_client = None
    if config.postgres and config.postgres.host:
        try:
            postgres_client = PostgresClientSecure(config=config.postgres.model_dump())
        except Exception as e:
            logger.warning(f"Failed to create PostgreSQL client: {e}")
    
    # Create unified database client
    db_client = UnifiedDatabaseClient(
        terminus_client=terminus_client,
        postgres_client=postgres_client,
        sqlite_client=sqlite_client,
        default_backend=DatabaseBackend.TERMINUSDB
    )
    
    await db_client.connect()
    _db_client_instance = db_client
    
    logger.info("Unified database client created and connected")
    return db_client


async def close_unified_db_client():
    """Close the unified database client if it exists"""
    global _db_client_instance
    
    if _db_client_instance is not None:
        await _db_client_instance.close()
        _db_client_instance = None
        logger.info("Unified database client closed")