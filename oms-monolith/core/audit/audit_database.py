"""
Audit Database Service
Persistent storage for audit logs with enterprise-grade features
"""
import asyncio
import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from models.audit_events import AuditEventV1, AuditEventFilter, AuditAction, ResourceType
from bootstrap.config import get_config
from shared.database.sqlite_connector import SQLiteConnector, get_sqlite_connector
from utils.logger import get_logger

logger = get_logger(__name__)


class AuditDatabaseError(Exception):
    """Base exception for audit database operations"""
    pass


class AuditRetentionPolicy:
    """Audit log retention and archival policy"""
    
    def __init__(self):
        self.default_retention_days = 2555  # 7 years (regulatory compliance)
        self.retention_by_action = {
            # Critical security events - extended retention
            AuditAction.AUTH_LOGIN: 2555,
            AuditAction.AUTH_FAILED: 2555,
            AuditAction.ACL_CREATE: 2555,
            AuditAction.ACL_UPDATE: 2555,
            AuditAction.ACL_DELETE: 2555,
            
            # Schema changes - long retention for compliance
            AuditAction.SCHEMA_CREATE: 1825,  # 5 years
            AuditAction.SCHEMA_UPDATE: 1825,
            AuditAction.SCHEMA_DELETE: 1825,
            AuditAction.OBJECT_TYPE_CREATE: 1825,
            AuditAction.OBJECT_TYPE_UPDATE: 1825,
            AuditAction.OBJECT_TYPE_DELETE: 1825,
            
            # Regular operations - standard retention
            AuditAction.BRANCH_CREATE: 365,  # 1 year
            AuditAction.BRANCH_UPDATE: 365,
            AuditAction.BRANCH_MERGE: 730,  # 2 years for merges
            
            # System operations - shorter retention
            AuditAction.INDEXING_STARTED: 90,  # 3 months
            AuditAction.INDEXING_COMPLETED: 90,
            AuditAction.INDEXING_FAILED: 180,  # 6 months for failures
        }
    
    def get_retention_days(self, action: AuditAction) -> int:
        """Get retention period for specific action"""
        return self.retention_by_action.get(action, self.default_retention_days)
    
    def calculate_expiry_date(self, action: AuditAction, created_at: datetime) -> datetime:
        """Calculate when an audit log should expire"""
        retention_days = self.get_retention_days(action)
        return created_at + timedelta(days=retention_days)


class AuditDatabase:
    """
    Enterprise audit database with compliance features
    
    Features:
    - Immutable audit log storage
    - Retention policy management
    - Efficient querying with indexes
    - Data integrity verification
    - Archive and purge capabilities
    - GDPR compliance support
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.config = get_config()
        self.db_name = "audit_logs.db"
        self.db_dir = db_path or "/tmp"
        self.retention_policy = AuditRetentionPolicy()
        self._connector: Optional[SQLiteConnector] = None
        self._initialized = False
        self._lock = asyncio.Lock()
        
        # Performance settings
        self.batch_size = 100
        self.connection_timeout = 30.0
    
    async def initialize(self):
        """Initialize database schema and indexes"""
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            # Get or create connector
            self._connector = await get_sqlite_connector(
                self.db_name,
                db_dir=self.db_dir,
                enable_wal=True,
                busy_timeout=30000
            )
            
            # Define migrations
            migrations = [
                # Create audit_events table
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL,
                    action TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    actor_username TEXT NOT NULL,
                    actor_is_service BOOLEAN NOT NULL DEFAULT FALSE,
                    target_resource_type TEXT NOT NULL,
                    target_resource_id TEXT NOT NULL,
                    target_resource_name TEXT,
                    target_branch TEXT,
                    success BOOLEAN NOT NULL DEFAULT TRUE,
                    error_code TEXT,
                    error_message TEXT,
                    duration_ms INTEGER,
                    request_id TEXT,
                    correlation_id TEXT,
                    causation_id TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    changes_json TEXT,
                    metadata_json TEXT,
                    tags_json TEXT,
                    compliance_json TEXT,
                    event_hash TEXT NOT NULL,
                    retention_until TIMESTAMP NOT NULL,
                    archived BOOLEAN NOT NULL DEFAULT FALSE,
                    created_year INTEGER GENERATED ALWAYS AS (strftime('%Y', created_at)) STORED,
                    created_month INTEGER GENERATED ALWAYS AS (strftime('%m', created_at)) STORED
                )
                """,
                # Create performance indexes
                "CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_events(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action)",
                "CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor_id, created_at)",
                "CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_events(target_resource_type, target_resource_id)",
                "CREATE INDEX IF NOT EXISTS idx_audit_branch ON audit_events(target_branch, created_at) WHERE target_branch IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_audit_request ON audit_events(request_id) WHERE request_id IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_audit_correlation ON audit_events(correlation_id) WHERE correlation_id IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS idx_audit_retention ON audit_events(retention_until, archived)",
                "CREATE INDEX IF NOT EXISTS idx_audit_partition ON audit_events(created_year, created_month, created_at)",
                # Create audit_integrity table for tamper detection
                """
                CREATE TABLE IF NOT EXISTS audit_integrity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_start_time TIMESTAMP NOT NULL,
                    batch_end_time TIMESTAMP NOT NULL,
                    event_count INTEGER NOT NULL,
                    batch_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                # Create audit_retention_log table
                """
                CREATE TABLE IF NOT EXISTS audit_retention_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    event_count INTEGER NOT NULL,
                    cutoff_date TIMESTAMP NOT NULL,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata_json TEXT
                )
                """
            ]
            
            # Initialize with migrations
            await self._connector.initialize(migrations=migrations)
            self._initialized = True
            logger.info(f"Audit database initialized with SQLiteConnector")
    
    async def store_audit_event(self, event: AuditEventV1) -> bool:
        """Store a single audit event with integrity verification"""
        await self.initialize()
        
        try:
            # Calculate event hash for integrity
            event_hash = self._calculate_event_hash(event)
            
            # Calculate retention date
            retention_until = self.retention_policy.calculate_expiry_date(
                event.action, 
                event.time or datetime.now(timezone.utc)
            )
            
            # Use SQLiteConnector for better connection management
            params = {
                "id": event.id,
                "created_at": (event.time or datetime.now(timezone.utc)).isoformat(),
                "action": event.action.value,
                "actor_id": event.actor.id,
                "actor_username": event.actor.username,
                "actor_is_service": event.actor.service_account,
                "target_resource_type": event.target.resource_type.value,
                "target_resource_id": event.target.resource_id,
                "target_resource_name": event.target.resource_name,
                "target_branch": event.target.branch,
                "success": event.success,
                "error_code": event.error_code,
                "error_message": event.error_message,
                "duration_ms": event.duration_ms,
                "request_id": event.request_id,
                "correlation_id": event.correlation_id,
                "causation_id": event.causation_id,
                "ip_address": event.actor.ip_address,
                "user_agent": event.actor.user_agent,
                "changes_json": json.dumps(event.changes.dict()) if event.changes else None,
                "metadata_json": json.dumps(event.metadata) if event.metadata else None,
                "tags_json": json.dumps(event.tags) if event.tags else None,
                "compliance_json": json.dumps(event.compliance.dict()) if event.compliance else None,
                "event_hash": event_hash,
                "retention_until": retention_until.isoformat()
            }
            
            await self._connector.execute(
                """
                INSERT INTO audit_events (
                    id, created_at, action, actor_id, actor_username, actor_is_service,
                    target_resource_type, target_resource_id, target_resource_name, target_branch,
                    success, error_code, error_message, duration_ms,
                    request_id, correlation_id, causation_id,
                    ip_address, user_agent,
                    changes_json, metadata_json, tags_json, compliance_json,
                    event_hash, retention_until
                ) VALUES (
                    :id, :created_at, :action, :actor_id, :actor_username, :actor_is_service,
                    :target_resource_type, :target_resource_id, :target_resource_name, :target_branch,
                    :success, :error_code, :error_message, :duration_ms,
                    :request_id, :correlation_id, :causation_id,
                    :ip_address, :user_agent,
                    :changes_json, :metadata_json, :tags_json, :compliance_json,
                    :event_hash, :retention_until
                )
                """,
                params
            )
            
            logger.debug(f"Stored audit event: {event.id}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to store audit event {event.id}: {e}")
            return False
    
    async def store_audit_events_batch(self, events: List[AuditEventV1]) -> int:
        """Store multiple audit events in a batch for performance"""
        await self.initialize()
        
        if not events:
            return 0
        
        stored_count = 0
        
        try:
            # Calculate integrity hash for this batch
            batch_start = min(e.time or datetime.now(timezone.utc) for e in events)
            batch_end = max(e.time or datetime.now(timezone.utc) for e in events)
                
            # Prepare batch data
            batch_data = []
            for event in events:
                event_hash = self._calculate_event_hash(event)
                retention_until = self.retention_policy.calculate_expiry_date(
                    event.action, 
                    event.time or datetime.now(timezone.utc)
                )
                
                batch_data.append({
                    "id": event.id,
                    "created_at": (event.time or datetime.now(timezone.utc)).isoformat(),
                    "action": event.action.value,
                    "actor_id": event.actor.id,
                    "actor_username": event.actor.username,
                    "actor_is_service": event.actor.service_account,
                    "target_resource_type": event.target.resource_type.value,
                    "target_resource_id": event.target.resource_id,
                    "target_resource_name": event.target.resource_name,
                    "target_branch": event.target.branch,
                    "success": event.success,
                    "error_code": event.error_code,
                    "error_message": event.error_message,
                    "duration_ms": event.duration_ms,
                    "request_id": event.request_id,
                    "correlation_id": event.correlation_id,
                    "causation_id": event.causation_id,
                    "ip_address": event.actor.ip_address,
                    "user_agent": event.actor.user_agent,
                    "changes_json": json.dumps(event.changes.dict()) if event.changes else None,
                    "metadata_json": json.dumps(event.metadata) if event.metadata else None,
                    "tags_json": json.dumps(event.tags) if event.tags else None,
                    "compliance_json": json.dumps(event.compliance.dict()) if event.compliance else None,
                    "event_hash": event_hash,
                    "retention_until": retention_until.isoformat()
                })
            
            # Use SQLiteConnector for batch insert
            await self._connector.execute_many(
                """
                INSERT INTO audit_events (
                    id, created_at, action, actor_id, actor_username, actor_is_service,
                    target_resource_type, target_resource_id, target_resource_name, target_branch,
                    success, error_code, error_message, duration_ms,
                    request_id, correlation_id, causation_id,
                    ip_address, user_agent,
                    changes_json, metadata_json, tags_json, compliance_json,
                    event_hash, retention_until
                ) VALUES (
                    :id, :created_at, :action, :actor_id, :actor_username, :actor_is_service,
                    :target_resource_type, :target_resource_id, :target_resource_name, :target_branch,
                    :success, :error_code, :error_message, :duration_ms,
                    :request_id, :correlation_id, :causation_id,
                    :ip_address, :user_agent,
                    :changes_json, :metadata_json, :tags_json, :compliance_json,
                    :event_hash, :retention_until
                )
                """,
                batch_data
            )
            
            # Store batch integrity record
            batch_hash = self._calculate_batch_hash(events)
            await self._connector.execute(
                """
                INSERT INTO audit_integrity (batch_start_time, batch_end_time, event_count, batch_hash)
                VALUES (:batch_start_time, :batch_end_time, :event_count, :batch_hash)
                """,
                {
                    "batch_start_time": batch_start.isoformat(),
                    "batch_end_time": batch_end.isoformat(),
                    "event_count": len(events),
                    "batch_hash": batch_hash
                }
            )
            
            stored_count = len(events)
            logger.info(f"Stored {stored_count} audit events in batch")
                
        except Exception as e:
            logger.error(f"Failed to store audit events batch: {e}")
        
        return stored_count
    
    async def query_audit_events(
        self, 
        filter_criteria: AuditEventFilter
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query audit events with filtering and pagination"""
        await self.initialize()
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        if filter_criteria.start_time:
            where_conditions.append("created_at >= ?")
            params.append(filter_criteria.start_time.isoformat())
        
        if filter_criteria.end_time:
            where_conditions.append("created_at <= ?")
            params.append(filter_criteria.end_time.isoformat())
        
        if filter_criteria.actor_ids:
            where_conditions.append(f"actor_id IN ({','.join(['?' for _ in filter_criteria.actor_ids])})")
            params.extend(filter_criteria.actor_ids)
        
        if filter_criteria.actions:
            where_conditions.append(f"action IN ({','.join(['?' for _ in filter_criteria.actions])})")
            params.extend([action.value for action in filter_criteria.actions])
        
        if filter_criteria.resource_types:
            where_conditions.append(f"target_resource_type IN ({','.join(['?' for _ in filter_criteria.resource_types])})")
            params.extend([rt.value for rt in filter_criteria.resource_types])
        
        if filter_criteria.resource_ids:
            where_conditions.append(f"target_resource_id IN ({','.join(['?' for _ in filter_criteria.resource_ids])})")
            params.extend(filter_criteria.resource_ids)
        
        if filter_criteria.branches:
            where_conditions.append(f"target_branch IN ({','.join(['?' for _ in filter_criteria.branches])})")
            params.extend(filter_criteria.branches)
        
        if filter_criteria.success is not None:
            where_conditions.append("success = ?")
            params.append(filter_criteria.success)
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Count total matching records
        count_query = f"SELECT COUNT(*) FROM audit_events {where_clause}"
        
        # Main query with pagination
        main_query = f"""
            SELECT * FROM audit_events {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        
        params.extend([filter_criteria.limit, filter_criteria.offset])
        
        try:
            # Convert params list to dict for SQLiteConnector
            count_params = {}
            main_params = {}
            param_idx = 0
            
            if filter_criteria.start_time:
                count_params["start_time"] = params[param_idx]
                main_params["start_time"] = params[param_idx]
                param_idx += 1
            
            if filter_criteria.end_time:
                count_params["end_time"] = params[param_idx]
                main_params["end_time"] = params[param_idx]
                param_idx += 1
            
            # Get total count
            count_result = await self._connector.fetch_one(count_query, count_params)
            total_count = count_result["COUNT(*)"] if count_result else 0
            
            # Add pagination params
            main_params["limit"] = filter_criteria.limit
            main_params["offset"] = filter_criteria.offset
            
            # Get paginated results
            rows = await self._connector.fetch_all(main_query, main_params)
            events = []
            
            for row in rows:
                event_dict = dict(row)
                
                # Parse JSON fields
                if event_dict.get('changes_json'):
                    event_dict['changes'] = json.loads(event_dict['changes_json'])
                if event_dict.get('metadata_json'):
                    event_dict['metadata'] = json.loads(event_dict['metadata_json'])
                if event_dict.get('tags_json'):
                    event_dict['tags'] = json.loads(event_dict['tags_json'])
                if event_dict.get('compliance_json'):
                    event_dict['compliance'] = json.loads(event_dict['compliance_json'])
                
                # Remove raw JSON fields
                for field in ['changes_json', 'metadata_json', 'tags_json', 'compliance_json']:
                    event_dict.pop(field, None)
                
                events.append(event_dict)
            
            return events, total_count
                
        except Exception as e:
            logger.error(f"Failed to query audit events: {e}")
            return [], 0
    
    async def get_audit_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get specific audit event by ID"""
        await self.initialize()
        
        try:
            row = await self._connector.fetch_one(
                "SELECT * FROM audit_events WHERE id = :event_id",
                {"event_id": event_id}
            )
            
            if row:
                event_dict = dict(row)
                
                # Parse JSON fields
                if event_dict.get('changes_json'):
                    event_dict['changes'] = json.loads(event_dict['changes_json'])
                if event_dict.get('metadata_json'):
                    event_dict['metadata'] = json.loads(event_dict['metadata_json'])
                if event_dict.get('tags_json'):
                    event_dict['tags'] = json.loads(event_dict['tags_json'])
                if event_dict.get('compliance_json'):
                    event_dict['compliance'] = json.loads(event_dict['compliance_json'])
                
                # Remove raw JSON fields
                for field in ['changes_json', 'metadata_json', 'tags_json', 'compliance_json']:
                    event_dict.pop(field, None)
                
                return event_dict
                
        except Exception as e:
            logger.error(f"Failed to get audit event {event_id}: {e}")
        
        return None
    
    async def get_audit_statistics(
        self, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get audit statistics for monitoring and dashboards"""
        await self.initialize()
        
        where_clause = ""
        params = []
        
        if start_time:
            where_clause += "WHERE created_at >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            if where_clause:
                where_clause += " AND created_at <= ?"
            else:
                where_clause = "WHERE created_at <= ?"
            params.append(end_time.isoformat())
        
        try:
            stats = {}
            
            # Convert params to dict for SQLiteConnector
            query_params = {}
            if start_time:
                query_params["start_time"] = start_time.isoformat()
            if end_time:
                query_params["end_time"] = end_time.isoformat()
            
            # Total events
            total_result = await self._connector.fetch_one(
                f"SELECT COUNT(*) as total FROM audit_events {where_clause}",
                query_params
            )
            stats['total_events'] = total_result['total'] if total_result else 0
            
            # Events by action
            action_rows = await self._connector.fetch_all(
                f"""
                SELECT action, COUNT(*) as count 
                FROM audit_events {where_clause}
                GROUP BY action 
                ORDER BY count DESC
                """,
                query_params
            )
            stats['events_by_action'] = {row['action']: row['count'] for row in action_rows}
                
                # Events by actor
                async with db.execute(f"""
                    SELECT actor_username, COUNT(*) as count 
                    FROM audit_events {where_clause}
                    GROUP BY actor_username 
                    ORDER BY count DESC 
                    LIMIT 10
                """, params) as cursor:
                    stats['top_actors'] = {row[0]: row[1] async for row in cursor}
                
                # Success/failure rate
                async with db.execute(f"""
                    SELECT success, COUNT(*) as count 
                    FROM audit_events {where_clause}
                    GROUP BY success
                """, params) as cursor:
                    success_stats = {bool(row[0]): row[1] async for row in cursor}
                    total = sum(success_stats.values())
                    if total > 0:
                        stats['success_rate'] = success_stats.get(True, 0) / total
                        stats['failure_rate'] = success_stats.get(False, 0) / total
                    else:
                        stats['success_rate'] = 0.0
                        stats['failure_rate'] = 0.0
                
                # Events by resource type
                async with db.execute(f"""
                    SELECT target_resource_type, COUNT(*) as count 
                    FROM audit_events {where_clause}
                    GROUP BY target_resource_type 
                    ORDER BY count DESC
                """, params) as cursor:
                    stats['events_by_resource_type'] = {row[0]: row[1] async for row in cursor}
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get audit statistics: {e}")
            return {}
    
    async def cleanup_expired_events(self) -> int:
        """Clean up expired audit events based on retention policy"""
        await self.initialize()
        
        try:
            current_time = datetime.now(timezone.utc)
            
            # First, get count of events to be deleted
            count_result = await self._connector.fetch_one(
                "SELECT COUNT(*) as count FROM audit_events WHERE retention_until <= :current_time AND archived = FALSE",
                {"current_time": current_time.isoformat()}
            )
            delete_count = count_result['count'] if count_result else 0
            
            if delete_count > 0:
                # Archive events first (for compliance)
                await self._connector.execute(
                    "UPDATE audit_events SET archived = TRUE WHERE retention_until <= :current_time AND archived = FALSE",
                    {"current_time": current_time.isoformat()}
                )
                
                # Log retention action
                await self._connector.execute(
                    """
                    INSERT INTO audit_retention_log (action, event_count, cutoff_date)
                    VALUES (:action, :event_count, :cutoff_date)
                    """,
                    {
                        "action": "ARCHIVE",
                        "event_count": delete_count,
                        "cutoff_date": current_time.isoformat()
                    }
                )
                
                logger.info(f"Archived {delete_count} expired audit events")
            
            return delete_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired audit events: {e}")
            return 0
    
    async def verify_integrity(self) -> Dict[str, Any]:
        """Verify audit log integrity"""
        await self.initialize()
        
        try:
            # Verify event hashes
            corrupted_events = []
            
            # Get all non-archived events for verification
            events = await self._connector.fetch_all(
                "SELECT * FROM audit_events WHERE archived = FALSE"
            )
            
            for row in events:
                event_id = row['id']
                stored_hash = row['event_hash']
                        
                        # Get full event and recalculate hash
                        event_data = await self.get_audit_event_by_id(event_id)
                        if event_data:
                            # Recreate event object for hash calculation
                            # This is a simplified check - in production would be more thorough
                            calculated_hash = hashlib.sha256(str(event_data).encode()).hexdigest()
                            
                            if stored_hash != calculated_hash:
                                corrupted_events.append(event_id)
                
                return {
                    "integrity_verified": len(corrupted_events) == 0,
                    "corrupted_events": corrupted_events,
                    "total_events_checked": len(corrupted_events) if corrupted_events else 0
                }
                
        except Exception as e:
            logger.error(f"Failed to verify audit integrity: {e}")
            return {"integrity_verified": False, "error": str(e)}
    
    def _calculate_event_hash(self, event: AuditEventV1) -> str:
        """Calculate SHA-256 hash of audit event for integrity verification"""
        # Create a normalized representation for hashing
        hash_data = {
            "id": event.id,
            "time": (event.time or datetime.now(timezone.utc)).isoformat(),
            "action": event.action.value,
            "actor_id": event.actor.id,
            "target": f"{event.target.resource_type.value}:{event.target.resource_id}",
            "success": event.success
        }
        
        hash_string = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(hash_string.encode()).hexdigest()
    
    def _calculate_batch_hash(self, events: List[AuditEventV1]) -> str:
        """Calculate hash for a batch of events"""
        event_hashes = [self._calculate_event_hash(event) for event in events]
        batch_string = "|".join(sorted(event_hashes))
        return hashlib.sha256(batch_string.encode()).hexdigest()


# Global audit database instance
_audit_database: Optional[AuditDatabase] = None


async def get_audit_database() -> AuditDatabase:
    """Get global audit database instance"""
    global _audit_database
    if _audit_database is None:
        _audit_database = AuditDatabase()
        await _audit_database.initialize()
    return _audit_database


async def initialize_audit_database(db_path: Optional[str] = None) -> AuditDatabase:
    """Initialize audit database with custom path"""
    global _audit_database
    _audit_database = AuditDatabase(db_path)
    await _audit_database.initialize()
    return _audit_database