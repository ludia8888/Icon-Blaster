"""
Issue Tracking Database Service
Manages persistence of change-issue links
"""
import sqlite3
import json
import os
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
import aiosqlite

from models.issue_tracking import (
    ChangeIssueLink, IssueReference, IssueProvider
)
from utils.logger import get_logger

logger = get_logger(__name__)


class IssueTrackingDatabase:
    """
    SQLite database for issue tracking persistence
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__), 
            "..", "..", "data", "issue_tracking.db"
        )
        self._initialized = False
    
    async def initialize(self):
        """Initialize database and create tables"""
        if self._initialized:
            return
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Read and execute migration
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "database", "migrations", "create_issue_tracking_tables.sql"
        )
        
        if os.path.exists(migration_path):
            with open(migration_path, 'r') as f:
                migration_sql = f.read()
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.executescript(migration_sql)
                await db.commit()
        
        self._initialized = True
        logger.info(f"Issue tracking database initialized at {self.db_path}")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db
    
    async def store_change_issue_link(self, link: ChangeIssueLink) -> int:
        """Store a change-issue link"""
        async with self.get_connection() as db:
            # Insert main link record
            cursor = await db.execute("""
                INSERT INTO change_issue_links (
                    change_id, change_type, branch_name,
                    primary_issue_provider, primary_issue_id,
                    emergency_override, override_justification, override_approver,
                    linked_by, linked_at, validation_result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                link.change_id,
                link.change_type,
                link.branch_name,
                link.primary_issue.provider.value,
                link.primary_issue.issue_id,
                link.emergency_override,
                link.override_justification,
                link.override_approver,
                link.linked_by,
                link.linked_at,
                json.dumps(link.validation_result) if link.validation_result else None
            ))
            
            link_id = cursor.lastrowid
            
            # Insert related issues
            for related_issue in link.related_issues:
                await db.execute("""
                    INSERT INTO change_related_issues (
                        link_id, issue_provider, issue_id
                    ) VALUES (?, ?, ?)
                """, (
                    link_id,
                    related_issue.provider.value,
                    related_issue.issue_id
                ))
            
            await db.commit()
            
            logger.info(
                f"Stored change-issue link: {link.change_id} -> "
                f"{link.primary_issue.get_display_name()}"
            )
            
            return link_id
    
    async def get_issues_for_change(self, change_id: str) -> Optional[ChangeIssueLink]:
        """Get issues linked to a change"""
        async with self.get_connection() as db:
            # Get main link
            cursor = await db.execute("""
                SELECT * FROM change_issue_links
                WHERE change_id = ?
                ORDER BY linked_at DESC
                LIMIT 1
            """, (change_id,))
            
            row = await cursor.fetchone()
            if not row:
                return None
            
            # Get related issues
            related_cursor = await db.execute("""
                SELECT issue_provider, issue_id
                FROM change_related_issues
                WHERE link_id = ?
            """, (row['id'],))
            
            related_rows = await related_cursor.fetchall()
            
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
        async with self.get_connection() as db:
            # Check primary issues
            cursor = await db.execute("""
                SELECT * FROM change_issue_links
                WHERE primary_issue_provider = ? AND primary_issue_id = ?
                ORDER BY linked_at DESC
            """, (issue_provider.value, issue_id))
            
            primary_changes = await cursor.fetchall()
            
            # Check related issues
            related_cursor = await db.execute("""
                SELECT l.* FROM change_issue_links l
                JOIN change_related_issues r ON l.id = r.link_id
                WHERE r.issue_provider = ? AND r.issue_id = ?
                ORDER BY l.linked_at DESC
            """, (issue_provider.value, issue_id))
            
            related_changes = await related_cursor.fetchall()
            
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
        async with self.get_connection() as db:
            # Build query
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
            params = []
            
            if start_date:
                query += " AND linked_at >= ?"
                params.append(start_date.isoformat())
            
            if end_date:
                query += " AND linked_at <= ?"
                params.append(end_date.isoformat())
            
            if branch_name:
                query += " AND branch_name = ?"
                params.append(branch_name)
            
            if change_type:
                query += " AND change_type = ?"
                params.append(change_type)
            
            cursor = await db.execute(query, params)
            row = await cursor.fetchone()
            
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
        async with self.get_connection() as db:
            query = """
                SELECT 
                    COUNT(*) as total_changes,
                    COUNT(DISTINCT primary_issue_id) as unique_issues,
                    SUM(CASE WHEN emergency_override = 1 THEN 1 ELSE 0 END) as emergency_overrides,
                    MIN(linked_at) as first_change,
                    MAX(linked_at) as last_change
                FROM change_issue_links
                WHERE linked_by = ?
            """
            params = [user]
            
            if start_date:
                query += " AND linked_at >= ?"
                params.append(start_date.isoformat())
            
            cursor = await db.execute(query, params)
            row = await cursor.fetchone()
            
            # Get breakdown by change type
            type_cursor = await db.execute("""
                SELECT 
                    change_type,
                    COUNT(*) as count
                FROM change_issue_links
                WHERE linked_by = ?
                GROUP BY change_type
            """, (user,))
            
            type_breakdown = {
                row['change_type']: row['count']
                for row in await type_cursor.fetchall()
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
        
        async with self.get_connection() as db:
            await db.execute("""
                INSERT OR REPLACE INTO issue_metadata_cache (
                    issue_provider, issue_id, title, status, issue_type,
                    priority, assignee, issue_url, metadata, cached_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                provider.value,
                issue_id,
                metadata.get('title'),
                metadata.get('status'),
                metadata.get('issue_type'),
                metadata.get('priority'),
                metadata.get('assignee'),
                metadata.get('issue_url'),
                json.dumps(metadata),
                datetime.now(timezone.utc).isoformat(),
                expires_at.isoformat()
            ))
            
            await db.commit()
    
    async def get_cached_issue_metadata(
        self,
        provider: IssueProvider,
        issue_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached issue metadata"""
        async with self.get_connection() as db:
            cursor = await db.execute("""
                SELECT * FROM issue_metadata_cache
                WHERE issue_provider = ? AND issue_id = ?
                AND expires_at > ?
            """, (
                provider.value,
                issue_id,
                datetime.now(timezone.utc).isoformat()
            ))
            
            row = await cursor.fetchone()
            if row:
                return json.loads(row['metadata'])
            
            return None
    
    async def cleanup_expired_cache(self):
        """Clean up expired cache entries"""
        async with self.get_connection() as db:
            await db.execute("""
                DELETE FROM issue_metadata_cache
                WHERE expires_at < ?
            """, (datetime.now(timezone.utc).isoformat(),))
            
            await db.commit()


# Global instance
_issue_db: Optional[IssueTrackingDatabase] = None


async def get_issue_database() -> IssueTrackingDatabase:
    """Get global issue tracking database instance"""
    global _issue_db
    if _issue_db is None:
        _issue_db = IssueTrackingDatabase()
        await _issue_db.initialize()
    return _issue_db