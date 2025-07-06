"""
Database Optimizations for Time Travel Queries
Index creation and query optimization strategies
"""
from typing import List, Dict, Any
from shared.database.sqlite_connector import SQLiteConnector
from common_logging.setup import get_logger

logger = get_logger(__name__)


class TimeTravelDBOptimizer:
    """
    Database optimizer for temporal queries
    """
    
    def __init__(self, connector: SQLiteConnector):
        self.connector = connector
    
    async def create_optimized_indexes(self):
        """
        Create optimized indexes for temporal queries
        """
        # Composite indexes for common query patterns
        indexes = [
            # AS OF queries - most common pattern
            """
            CREATE INDEX IF NOT EXISTS idx_temporal_as_of 
            ON resource_versions (
                resource_type, 
                branch, 
                modified_at DESC,
                resource_id,
                version DESC
            )
            """,
            
            # BETWEEN queries - time range scans
            """
            CREATE INDEX IF NOT EXISTS idx_temporal_between 
            ON resource_versions (
                resource_type,
                branch,
                modified_at,
                resource_id
            )
            """,
            
            # Version history queries
            """
            CREATE INDEX IF NOT EXISTS idx_version_history 
            ON resource_versions (
                resource_type,
                resource_id,
                branch,
                version
            )
            """,
            
            # Commit hash lookups
            """
            CREATE INDEX IF NOT EXISTS idx_commit_lookup 
            ON resource_versions (
                commit_hash,
                branch
            )
            """,
            
            # Delta queries optimization
            """
            CREATE INDEX IF NOT EXISTS idx_delta_lookup 
            ON version_deltas (
                resource_type,
                resource_id,
                branch,
                from_version,
                to_version
            )
            """,
            
            # Branch head tracking
            """
            CREATE INDEX IF NOT EXISTS idx_branch_heads_lookup 
            ON branch_heads (
                branch,
                resource_type,
                updated_at DESC
            )
            """,
            
            # Covering index for AS OF without content
            """
            CREATE INDEX IF NOT EXISTS idx_temporal_metadata 
            ON resource_versions (
                resource_type,
                resource_id,
                branch,
                modified_at DESC
            ) WHERE change_type != 'delete'
            """,
            
            # Partial index for active resources only
            """
            CREATE INDEX IF NOT EXISTS idx_active_resources 
            ON resource_versions (
                resource_type,
                branch,
                modified_at DESC
            ) WHERE change_type != 'delete'
            """
        ]
        
        # Create indexes
        for index_sql in indexes:
            try:
                await self.connector.execute(index_sql)
                logger.info(f"Created index: {index_sql.split('idx_')[1].split()[0]}")
            except Exception as e:
                logger.error(f"Failed to create index: {e}")
    
    async def analyze_and_optimize(self):
        """
        Analyze tables and update statistics for query optimizer
        """
        tables = ["resource_versions", "version_deltas", "branch_heads"]
        
        for table in tables:
            try:
                # Update SQLite statistics
                await self.connector.execute(f"ANALYZE {table}")
                logger.info(f"Updated statistics for table: {table}")
                
                # Get table stats
                stats = await self.connector.fetch_one(
                    "SELECT COUNT(*) as count FROM " + table
                )
                logger.info(f"Table {table} has {stats['count']} rows")
                
            except Exception as e:
                logger.error(f"Failed to analyze table {table}: {e}")
    
    async def create_materialized_views(self):
        """
        Create materialized views for common query patterns
        """
        views = [
            # Latest version per resource (for AS OF current time)
            """
            CREATE VIEW IF NOT EXISTS v_latest_resources AS
            WITH latest_versions AS (
                SELECT 
                    resource_type,
                    resource_id,
                    branch,
                    MAX(version) as max_version
                FROM resource_versions
                WHERE change_type != 'delete'
                GROUP BY resource_type, resource_id, branch
            )
            SELECT rv.*
            FROM resource_versions rv
            INNER JOIN latest_versions lv
                ON rv.resource_type = lv.resource_type
                AND rv.resource_id = lv.resource_id
                AND rv.branch = lv.branch
                AND rv.version = lv.max_version
            """,
            
            # Resource change frequency (for hot data identification)
            """
            CREATE VIEW IF NOT EXISTS v_resource_change_frequency AS
            SELECT 
                resource_type,
                resource_id,
                branch,
                COUNT(*) as change_count,
                MIN(modified_at) as first_modified,
                MAX(modified_at) as last_modified,
                julianday(MAX(modified_at)) - julianday(MIN(modified_at)) as lifespan_days,
                CASE 
                    WHEN julianday(MAX(modified_at)) - julianday(MIN(modified_at)) > 0
                    THEN COUNT(*) / (julianday(MAX(modified_at)) - julianday(MIN(modified_at)))
                    ELSE 0
                END as changes_per_day
            FROM resource_versions
            GROUP BY resource_type, resource_id, branch
            """
        ]
        
        for view_sql in views:
            try:
                await self.connector.execute(view_sql)
                view_name = view_sql.split('CREATE VIEW IF NOT EXISTS ')[1].split(' AS')[0]
                logger.info(f"Created view: {view_name}")
            except Exception as e:
                logger.error(f"Failed to create view: {e}")
    
    async def get_query_plan(self, query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get query execution plan for optimization
        """
        explain_query = f"EXPLAIN QUERY PLAN {query}"
        try:
            plan = await self.connector.fetch_all(explain_query, params)
            return plan
        except Exception as e:
            logger.error(f"Failed to get query plan: {e}")
            return []
    
    async def suggest_optimizations(self) -> List[str]:
        """
        Analyze current state and suggest optimizations
        """
        suggestions = []
        
        # Check index usage
        index_stats = await self.connector.fetch_all(
            """
            SELECT name, tbl_name 
            FROM sqlite_master 
            WHERE type = 'index' AND name LIKE 'idx_temporal%'
            """
        )
        
        if len(index_stats) < 5:
            suggestions.append(
                "Missing temporal indexes - run create_optimized_indexes()"
            )
        
        # Check table sizes
        for table in ["resource_versions", "version_deltas"]:
            size = await self.connector.fetch_one(
                f"SELECT COUNT(*) as count FROM {table}"
            )
            if size['count'] > 1000000:
                suggestions.append(
                    f"Table {table} has {size['count']} rows - "
                    f"consider partitioning or archiving old data"
                )
        
        # Check for missing statistics
        stat_check = await self.connector.fetch_one(
            "SELECT COUNT(*) as count FROM sqlite_stat1"
        )
        if stat_check['count'] == 0:
            suggestions.append(
                "No table statistics found - run analyze_and_optimize()"
            )
        
        return suggestions
    
    async def vacuum_database(self):
        """
        Vacuum database to reclaim space and optimize storage
        """
        try:
            await self.connector.execute("VACUUM")
            logger.info("Database vacuum completed")
        except Exception as e:
            logger.error(f"Failed to vacuum database: {e}")


# Cursor-based pagination helper
class TemporalCursorPagination:
    """
    Cursor-based pagination for temporal queries
    """
    
    @staticmethod
    def encode_cursor(
        last_timestamp: str,
        last_version: int,
        last_resource_id: str
    ) -> str:
        """Encode pagination cursor"""
        import base64
        import json
        
        cursor_data = {
            "ts": last_timestamp,
            "v": last_version,
            "id": last_resource_id
        }
        cursor_json = json.dumps(cursor_data)
        return base64.b64encode(cursor_json.encode()).decode()
    
    @staticmethod
    def decode_cursor(cursor: str) -> Dict[str, Any]:
        """Decode pagination cursor"""
        import base64
        import json
        
        try:
            cursor_json = base64.b64decode(cursor.encode()).decode()
            return json.loads(cursor_json)
        except Exception:
            return {}
    
    @staticmethod
    def build_cursor_query(
        base_query: str,
        cursor_data: Dict[str, Any],
        order_by: str = "modified_at DESC, version DESC, resource_id"
    ) -> str:
        """Build query with cursor-based pagination"""
        if not cursor_data:
            return f"{base_query} ORDER BY {order_by} LIMIT :limit"
        
        # Add cursor conditions
        cursor_condition = """
            AND (
                modified_at < :cursor_ts
                OR (modified_at = :cursor_ts AND version < :cursor_v)
                OR (modified_at = :cursor_ts AND version = :cursor_v AND resource_id > :cursor_id)
            )
        """
        
        return f"{base_query} {cursor_condition} ORDER BY {order_by} LIMIT :limit"