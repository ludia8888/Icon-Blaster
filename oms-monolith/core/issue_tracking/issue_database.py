"""
Issue Tracking Database Service
Manages persistence of change-issue links
"""
import json
import os
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta

from models.issue_tracking import (
    ChangeIssueLink, IssueReference, IssueProvider
)
from shared.database.sqlite_connector import SQLiteConnector, get_sqlite_connector
from utils.logger import get_logger

logger = get_logger(__name__)


class IssueTrackingDatabase:
    """
    SQLite database for issue tracking persistence
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_name = "issue_tracking.db"
        self.db_dir = db_path or os.path.join(
            os.path.dirname(__file__), 
            "..", "..", "data"
        )
        self._connector: Optional[SQLiteConnector] = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize database and create tables"""
        if self._initialized:
            return
        
        # Get or create connector
        self._connector = await get_sqlite_connector(
            self.db_name,
            db_dir=self.db_dir,
            enable_wal=True
        )
        
        # Read migration file
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "database", "migrations", "create_issue_tracking_tables.sql"
        )
        
        migrations = []
        if os.path.exists(migration_path):
            with open(migration_path, 'r') as f:
                migrations.append(f.read())
        
        # Initialize with migrations
        await self._connector.initialize(migrations=migrations)
        self._initialized = True
        logger.info(f"Issue tracking database initialized with SQLiteConnector")
    
    async def _ensure_initialized(self):
        """Ensure database is initialized"""
        if not self._initialized:
            await self.initialize()
    
    async def store_change_issue_link(self, link: ChangeIssueLink) -> int:
        """Store a change-issue link"""
        await self._ensure_initialized()
        
        # Insert main link record
        link_id = await self._connector.execute(
            """
            INSERT INTO change_issue_links (
                change_id, change_type, branch_name,
                primary_issue_provider, primary_issue_id,
                emergency_override, override_justification, override_approver,
                linked_by, linked_at, validation_result
            ) VALUES (
                :change_id, :change_type, :branch_name,
                :primary_issue_provider, :primary_issue_id,
                :emergency_override, :override_justification, :override_approver,
                :linked_by, :linked_at, :validation_result
            )
            """,
            {
                "change_id": link.change_id,
                "change_type": link.change_type,
                "branch_name": link.branch_name,
                "primary_issue_provider": link.primary_issue.provider.value,
                "primary_issue_id": link.primary_issue.issue_id,
                "emergency_override": link.emergency_override,
                "override_justification": link.override_justification,
                "override_approver": link.override_approver,
                "linked_by": link.linked_by,
                "linked_at": link.linked_at,
                "validation_result": json.dumps(link.validation_result) if link.validation_result else None
            }
        )
        
        # Get the last inserted row id
        result = await self._connector.fetch_one("SELECT last_insert_rowid() as id")
        link_id = result['id'] if result else None
        
        # Insert related issues
        if link_id and link.related_issues:
            for related_issue in link.related_issues:
                await self._connector.execute(
                    """
                    INSERT INTO change_related_issues (
                        link_id, issue_provider, issue_id
                    ) VALUES (:link_id, :issue_provider, :issue_id)
                    """,
                    {
                        "link_id": link_id,
                        "issue_provider": related_issue.provider.value,
                        "issue_id": related_issue.issue_id
                    }
                )
        
        logger.info(
            f"Stored change-issue link: {link.change_id} -> "
            f"{link.primary_issue.get_display_name()}"
        )
        
        return link_id
    
    async def get_issues_for_change(self, change_id: str) -> Optional[ChangeIssueLink]:
        """Get issues linked to a change"""
        await self._ensure_initialized()
        
        # Get main link
        row = await self._connector.fetch_one(
            """
            SELECT * FROM change_issue_links
            WHERE change_id = :change_id
            ORDER BY linked_at DESC
            LIMIT 1
            """,
            {"change_id": change_id}
        )
        
        if not row:
            return None
        
        # Get related issues
        related_rows = await self._connector.fetch_all(
            """
            SELECT issue_provider, issue_id
            FROM change_related_issues
            WHERE link_id = :link_id
            """,
            {"link_id": row['id']}
        )
        
        # Reconstruct link
        primary_issue = IssueReference(
            provider=IssueProvider(row['primary_issue_provider']),
            issue_id=row['primary_issue_id']
        )
        
        related_issues = [
            IssueReference(
                provider=IssueProvider(rel['issue_provider']),
                issue_id=rel['issue_id']
            )
            for rel in related_rows
        ]
        
        return ChangeIssueLink(
                change_id=row['change_id'],
                change_type=row['change_type'],
                branch_name=row['branch_name'],
                primary_issue=primary_issue,
                related_issues=related_issues,
                emergency_override=bool(row['emergency_override']),
                override_justification=row['override_justification'],
                override_approver=row['override_approver'],
                linked_by=row['linked_by'],
                linked_at=datetime.fromisoformat(row['linked_at']),
                validation_result=json.loads(row['validation_result']) if row['validation_result'] else None
            )
    
    async def get_changes_for_issue(
        self, 
        issue_provider: IssueProvider, 
        issue_id: str
    ) -> List[Dict[str, Any]]:
        """Get all changes linked to an issue"""
        await self._ensure_initialized()
        
        # Check primary issues
        primary_changes = await self._connector.fetch_all(
            """
            SELECT * FROM change_issue_links
            WHERE primary_issue_provider = :provider AND primary_issue_id = :issue_id
            ORDER BY linked_at DESC
            """,
            {"provider": issue_provider.value, "issue_id": issue_id}
        )
        
        # Check related issues
        related_changes = await self._connector.fetch_all(
            """
            SELECT l.* FROM change_issue_links l
            JOIN change_related_issues r ON l.id = r.link_id
            WHERE r.issue_provider = :provider AND r.issue_id = :issue_id
            ORDER BY l.linked_at DESC
            """,
            {"provider": issue_provider.value, "issue_id": issue_id}
        )
        
        # Combine and deduplicate
        all_changes = []
        seen_ids = set()
        
        for row in primary_changes + related_changes:
            if row['change_id'] not in seen_ids:
                seen_ids.add(row['change_id'])
                all_changes.append({
                        'change_id': row['change_id'],
                        'change_type': row['change_type'],
                        'branch_name': row['branch_name'],
                        'linked_by': row['linked_by'],
                        'linked_at': row['linked_at'],
                        'is_primary': row in primary_changes,
                        'emergency_override': bool(row['emergency_override'])
                    })
            
            return all_changes
    
    async def get_compliance_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        branch_name: Optional[str] = None,
        change_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get compliance statistics"""
        await self._ensure_initialized()
        
        # Build query with named parameters
        query = """
            SELECT 
                COUNT(*) as total_changes,
                COUNT(DISTINCT primary_issue_id) as unique_issues,
                SUM(CASE WHEN emergency_override = 1 THEN 1 ELSE 0 END) as emergency_overrides,
                COUNT(DISTINCT linked_by) as unique_users,
                COUNT(DISTINCT branch_name) as unique_branches
            FROM change_issue_links
            WHERE 1=1
        """
        params = {}
        
        if start_date:
            query += " AND linked_at >= :start_date"
            params["start_date"] = start_date.isoformat()
        
        if end_date:
            query += " AND linked_at <= :end_date"
            params["end_date"] = end_date.isoformat()
        
        if branch_name:
            query += " AND branch_name = :branch_name"
            params["branch_name"] = branch_name
        
        if change_type:
            query += " AND change_type = :change_type"
            params["change_type"] = change_type
        
        row = await self._connector.fetch_one(query, params)
        
        return {
                'total_changes': row['total_changes'],
                'unique_issues': row['unique_issues'],
                'emergency_overrides': row['emergency_overrides'],
                'emergency_override_rate': (
                    row['emergency_overrides'] / row['total_changes'] * 100
                    if row['total_changes'] > 0 else 0
                ),
                'unique_users': row['unique_users'],
                'unique_branches': row['unique_branches']
            }
    
    async def get_user_compliance_stats(
        self,
        user: str,
        start_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get compliance statistics for a specific user"""
        await self._ensure_initialized()
        
        query = """
            SELECT 
                COUNT(*) as total_changes,
                COUNT(DISTINCT primary_issue_id) as unique_issues,
                    SUM(CASE WHEN emergency_override = 1 THEN 1 ELSE 0 END) as emergency_overrides,
                    MIN(linked_at) as first_change,
                    MAX(linked_at) as last_change
            FROM change_issue_links
            WHERE linked_by = :user
        """
        params = {"user": user}
        
        if start_date:
            query += " AND linked_at >= :start_date"
            params["start_date"] = start_date.isoformat()
        
        row = await self._connector.fetch_one(query, params)
        
        # Get breakdown by change type
        type_rows = await self._connector.fetch_all(
            """
            SELECT 
                change_type,
                COUNT(*) as count
            FROM change_issue_links
            WHERE linked_by = :user
            GROUP BY change_type
            """,
            {"user": user}
        )
        
        type_breakdown = {
            row['change_type']: row['count']
            for row in type_rows
        }
            
            return {
                'user': user,
                'total_changes': row['total_changes'],
                'unique_issues': row['unique_issues'],
                'emergency_overrides': row['emergency_overrides'],
                'emergency_override_rate': (
                    row['emergency_overrides'] / row['total_changes'] * 100
                    if row['total_changes'] > 0 else 0
                ),
                'first_change': row['first_change'],
                'last_change': row['last_change'],
                'change_type_breakdown': type_breakdown
            }
    
    async def cache_issue_metadata(
        self,
        provider: IssueProvider,
        issue_id: str,
        metadata: Dict[str, Any],
        ttl_seconds: int = 300
    ):
        """Cache issue metadata"""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        
        await self._ensure_initialized()
        
        await self._connector.execute(
            """
            INSERT OR REPLACE INTO issue_metadata_cache (
                issue_provider, issue_id, title, status, issue_type,
                priority, assignee, issue_url, metadata, cached_at, expires_at
            ) VALUES (:provider, :issue_id, :title, :status, :issue_type, :priority, :assignee, :issue_url, :metadata, :cached_at, :expires_at)
            """,
            {
                "provider": provider.value,
                "issue_id": issue_id,
                "title": metadata.get('title'),
                "status": metadata.get('status'),
                "issue_type": metadata.get('issue_type'),
                "priority": metadata.get('priority'),
                "assignee": metadata.get('assignee'),
                "issue_url": metadata.get('issue_url'),
                "metadata": json.dumps(metadata),
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at.isoformat()
            }
        )
    
    async def get_cached_issue_metadata(
        self,
        provider: IssueProvider,
        issue_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached issue metadata"""
        await self._ensure_initialized()
        
        row = await self._connector.fetch_one(
            """
            SELECT * FROM issue_metadata_cache
            WHERE issue_provider = :provider AND issue_id = :issue_id
            AND expires_at > :now
            """,
            {
                "provider": provider.value,
                "issue_id": issue_id,
                "now": datetime.now(timezone.utc).isoformat()
            }
        )
        
        if row:
            return json.loads(row['metadata'])
        
        return None
    
    async def cleanup_expired_cache(self):
        """Clean up expired cache entries"""
        await self._ensure_initialized()
        
        await self._connector.execute(
            """
            DELETE FROM issue_metadata_cache
            WHERE expires_at < :now
            """,
            {"now": datetime.now(timezone.utc).isoformat()}
        )


# Global instance
_issue_db: Optional[IssueTrackingDatabase] = None


async def get_issue_database() -> IssueTrackingDatabase:
    """Get global issue tracking database instance"""
    global _issue_db
    if _issue_db is None:
        _issue_db = IssueTrackingDatabase()
        await _issue_db.initialize()
    return _issue_db