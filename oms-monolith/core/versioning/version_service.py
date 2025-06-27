"""
Version Tracking Service
Manages resource versions and generates ETags for efficient caching
"""
import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
import aiosqlite
import os

from models.etag import (
    VersionInfo, ResourceVersion, DeltaRequest, DeltaResponse,
    ResourceDelta, VersionConflict, CacheValidation,
    calculate_content_hash, generate_commit_hash, create_json_patch
)
from core.auth import UserContext
from utils.logger import get_logger

logger = get_logger(__name__)


class VersionTrackingService:
    """
    Service for tracking resource versions and generating deltas
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__),
            "..", "..", "data", "versions.db"
        )
        self._initialized = False
    
    async def initialize(self):
        """Initialize version tracking database"""
        if self._initialized:
            return
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Create tables
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS resource_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    commit_hash TEXT NOT NULL,
                    parent_commit TEXT,
                    content_hash TEXT NOT NULL,
                    content_size INTEGER NOT NULL,
                    etag TEXT NOT NULL,
                    change_type TEXT NOT NULL,
                    change_summary TEXT,
                    fields_changed TEXT,  -- JSON array
                    modified_by TEXT NOT NULL,
                    modified_at TIMESTAMP NOT NULL,
                    content TEXT,  -- JSON content
                    
                    UNIQUE(resource_type, resource_id, branch, version)
                );
                
                CREATE INDEX IF NOT EXISTS idx_resource ON resource_versions (resource_type, resource_id, branch);
                CREATE INDEX IF NOT EXISTS idx_commit ON resource_versions (commit_hash);
                CREATE INDEX IF NOT EXISTS idx_modified ON resource_versions (modified_at);
                
                CREATE TABLE IF NOT EXISTS version_deltas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    from_version INTEGER NOT NULL,
                    to_version INTEGER NOT NULL,
                    delta_type TEXT NOT NULL,  -- patch or full
                    delta_content TEXT NOT NULL,  -- JSON
                    delta_size INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_delta ON version_deltas (resource_type, resource_id, branch, from_version, to_version);
                
                CREATE TABLE IF NOT EXISTS branch_heads (
                    branch TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    latest_commit TEXT NOT NULL,
                    latest_version INTEGER NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    
                    PRIMARY KEY (branch, resource_type)
                );
            """)
            await db.commit()
        
        self._initialized = True
        logger.info(f"Version tracking initialized at {self.db_path}")
    
    async def track_change(
        self,
        resource_type: str,
        resource_id: str,
        branch: str,
        content: Dict[str, Any],
        change_type: str,
        user: UserContext,
        change_summary: Optional[str] = None,
        fields_changed: Optional[List[str]] = None
    ) -> ResourceVersion:
        """Track a change to a resource"""
        # Calculate content hash
        content_hash = calculate_content_hash(content)
        content_size = len(json.dumps(content))
        
        async with aiosqlite.connect(self.db_path) as db:
            # Get previous version
            cursor = await db.execute("""
                SELECT version, commit_hash, content_hash
                FROM resource_versions
                WHERE resource_type = ? AND resource_id = ? AND branch = ?
                ORDER BY version DESC
                LIMIT 1
            """, (resource_type, resource_id, branch))
            
            row = await cursor.fetchone()
            
            if row:
                prev_version = row[0]
                prev_commit = row[1]
                prev_content_hash = row[2]
                
                # Skip if content hasn't changed
                if prev_content_hash == content_hash:
                    logger.debug(f"No content change for {resource_type}/{resource_id}")
                    return await self.get_resource_version(resource_type, resource_id, branch)
                
                new_version = prev_version + 1
            else:
                prev_commit = None
                new_version = 1
            
            # Generate commit hash
            timestamp = datetime.now(timezone.utc)
            commit_hash = generate_commit_hash(
                prev_commit, content_hash, user.username, timestamp
            )
            
            # Generate ETag
            etag = f'W/"{commit_hash[:12]}-{new_version}"'
            
            # Create version info
            version_info = VersionInfo(
                version=new_version,
                commit_hash=commit_hash,
                etag=etag,
                last_modified=timestamp,
                modified_by=user.username,
                parent_version=prev_version if row else None,
                parent_commit=prev_commit,
                change_type=change_type,
                change_summary=change_summary,
                fields_changed=fields_changed or []
            )
            
            # Store version
            await db.execute("""
                INSERT INTO resource_versions (
                    resource_type, resource_id, branch, version,
                    commit_hash, parent_commit, content_hash, content_size,
                    etag, change_type, change_summary, fields_changed,
                    modified_by, modified_at, content
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                resource_type, resource_id, branch, new_version,
                commit_hash, prev_commit, content_hash, content_size,
                etag, change_type, change_summary,
                json.dumps(fields_changed or []),
                user.username, timestamp.isoformat(),
                json.dumps(content)
            ))
            
            # Update branch head
            await db.execute("""
                INSERT OR REPLACE INTO branch_heads (
                    branch, resource_type, latest_commit, latest_version, updated_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (branch, resource_type, commit_hash, new_version, timestamp.isoformat()))
            
            # Generate and store delta if applicable
            if row and prev_version:
                await self._generate_and_store_delta(
                    db, resource_type, resource_id, branch,
                    prev_version, new_version, content
                )
            
            await db.commit()
            
            # Create resource version object
            resource_version = ResourceVersion(
                resource_type=resource_type,
                resource_id=resource_id,
                branch=branch,
                current_version=version_info,
                content_hash=content_hash,
                content_size=content_size
            )
            
            logger.info(
                f"Tracked version {new_version} for {resource_type}/{resource_id} "
                f"on branch {branch} (commit: {commit_hash[:12]})"
            )
            
            return resource_version
    
    async def get_resource_version(
        self,
        resource_type: str,
        resource_id: str,
        branch: str,
        version: Optional[int] = None
    ) -> Optional[ResourceVersion]:
        """Get version info for a resource"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            if version is None:
                # Get latest version
                cursor = await db.execute("""
                    SELECT * FROM resource_versions
                    WHERE resource_type = ? AND resource_id = ? AND branch = ?
                    ORDER BY version DESC
                    LIMIT 1
                """, (resource_type, resource_id, branch))
            else:
                # Get specific version
                cursor = await db.execute("""
                    SELECT * FROM resource_versions
                    WHERE resource_type = ? AND resource_id = ? AND branch = ? AND version = ?
                """, (resource_type, resource_id, branch, version))
            
            row = await cursor.fetchone()
            if not row:
                return None
            
            version_info = VersionInfo(
                version=row['version'],
                commit_hash=row['commit_hash'],
                etag=row['etag'],
                last_modified=datetime.fromisoformat(row['modified_at']),
                modified_by=row['modified_by'],
                parent_version=row['version'] - 1 if row['version'] > 1 else None,
                parent_commit=row['parent_commit'],
                change_type=row['change_type'],
                change_summary=row['change_summary'],
                fields_changed=json.loads(row['fields_changed'])
            )
            
            return ResourceVersion(
                resource_type=resource_type,
                resource_id=resource_id,
                branch=branch,
                current_version=version_info,
                content_hash=row['content_hash'],
                content_size=row['content_size']
            )
    
    async def validate_etag(
        self,
        resource_type: str,
        resource_id: str,
        branch: str,
        client_etag: str
    ) -> Tuple[bool, Optional[ResourceVersion]]:
        """Validate client ETag and return current version"""
        current_version = await self.get_resource_version(
            resource_type, resource_id, branch
        )
        
        if not current_version:
            return False, None
        
        is_valid = current_version.current_version.etag == client_etag
        return is_valid, current_version
    
    async def get_delta(
        self,
        resource_type: str,
        resource_id: str,
        branch: str,
        delta_request: DeltaRequest
    ) -> DeltaResponse:
        """Get delta changes for a resource"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Get current version
            current = await self.get_resource_version(resource_type, resource_id, branch)
            if not current:
                return DeltaResponse(
                    to_version=VersionInfo(
                        version=0,
                        commit_hash="",
                        etag="",
                        last_modified=datetime.now(timezone.utc),
                        modified_by="system",
                        change_type="not_found"
                    ),
                    response_type="no_change",
                    total_changes=0,
                    delta_size=0,
                    etag=""
                )
            
            # Check if client is up to date
            if delta_request.client_etag == current.current_version.etag:
                return DeltaResponse(
                    to_version=current.current_version,
                    response_type="no_change",
                    total_changes=0,
                    delta_size=0,
                    etag=current.current_version.etag
                )
            
            # Get client version info
            client_version = None
            if delta_request.client_version:
                cursor = await db.execute("""
                    SELECT * FROM resource_versions
                    WHERE resource_type = ? AND resource_id = ? AND branch = ? AND version = ?
                """, (resource_type, resource_id, branch, delta_request.client_version))
                
                client_row = await cursor.fetchone()
                if client_row:
                    client_version = VersionInfo(
                        version=client_row['version'],
                        commit_hash=client_row['commit_hash'],
                        etag=client_row['etag'],
                        last_modified=datetime.fromisoformat(client_row['modified_at']),
                        modified_by=client_row['modified_by'],
                        change_type=client_row['change_type']
                    )
            
            # Check for cached delta
            if client_version:
                cursor = await db.execute("""
                    SELECT * FROM version_deltas
                    WHERE resource_type = ? AND resource_id = ? AND branch = ?
                    AND from_version = ? AND to_version = ?
                """, (
                    resource_type, resource_id, branch,
                    client_version.version, current.current_version.version
                ))
                
                delta_row = await cursor.fetchone()
                if delta_row:
                    # Use cached delta
                    delta = ResourceDelta(
                        resource_type=resource_type,
                        resource_id=resource_id,
                        operation="update",
                        from_version=client_version.version,
                        to_version=current.current_version.version,
                        delta_type=delta_row['delta_type'],
                        patches=json.loads(delta_row['delta_content'])
                            if delta_row['delta_type'] == 'patch' else None,
                        full_content=json.loads(delta_row['delta_content'])
                            if delta_row['delta_type'] == 'full' else None
                    )
                    
                    return DeltaResponse(
                        from_version=client_version,
                        to_version=current.current_version,
                        response_type="delta",
                        changes=[delta],
                        total_changes=1,
                        delta_size=delta_row['delta_size'],
                        etag=current.current_version.etag
                    )
            
            # Return full content if no delta available or requested
            cursor = await db.execute("""
                SELECT content FROM resource_versions
                WHERE resource_type = ? AND resource_id = ? AND branch = ?
                AND version = ?
            """, (resource_type, resource_id, branch, current.current_version.version))
            
            content_row = await cursor.fetchone()
            if content_row:
                content = json.loads(content_row['content'])
                delta = ResourceDelta(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    operation="update",
                    from_version=client_version.version if client_version else None,
                    to_version=current.current_version.version,
                    delta_type="full",
                    full_content=content
                )
                
                return DeltaResponse(
                    from_version=client_version,
                    to_version=current.current_version,
                    response_type="full",
                    changes=[delta],
                    total_changes=1,
                    delta_size=len(json.dumps(content)),
                    etag=current.current_version.etag
                )
            
            return DeltaResponse(
                to_version=current.current_version,
                response_type="no_change",
                total_changes=0,
                delta_size=0,
                etag=current.current_version.etag
            )
    
    async def validate_cache(
        self,
        branch: str,
        validation: CacheValidation
    ) -> CacheValidation:
        """Validate multiple resource ETags"""
        async with aiosqlite.connect(self.db_path) as db:
            for resource_key, client_etag in validation.resource_etags.items():
                # Parse resource key (format: "type:id")
                parts = resource_key.split(":", 1)
                if len(parts) != 2:
                    validation.stale_resources.append(resource_key)
                    continue
                
                resource_type, resource_id = parts
                
                # Check current version
                cursor = await db.execute("""
                    SELECT etag FROM resource_versions
                    WHERE resource_type = ? AND resource_id = ? AND branch = ?
                    ORDER BY version DESC
                    LIMIT 1
                """, (resource_type, resource_id, branch))
                
                row = await cursor.fetchone()
                
                if not row:
                    validation.deleted_resources.append(resource_key)
                elif row[0] == client_etag:
                    validation.valid_resources.append(resource_key)
                else:
                    validation.stale_resources.append(resource_key)
        
        return validation
    
    async def _generate_and_store_delta(
        self,
        db: aiosqlite.Connection,
        resource_type: str,
        resource_id: str,
        branch: str,
        from_version: int,
        to_version: int,
        new_content: Dict[str, Any]
    ):
        """Generate and store delta between versions"""
        # Get old content
        cursor = await db.execute("""
            SELECT content FROM resource_versions
            WHERE resource_type = ? AND resource_id = ? AND branch = ? AND version = ?
        """, (resource_type, resource_id, branch, from_version))
        
        row = await cursor.fetchone()
        if not row:
            return
        
        old_content = json.loads(row[0])
        
        # Generate patch
        patches = create_json_patch(old_content, new_content)
        
        # Decide whether to store patch or full content
        patch_size = len(json.dumps(patches))
        full_size = len(json.dumps(new_content))
        
        if patch_size < full_size * 0.7:  # Use patch if it's < 70% of full size
            delta_type = "patch"
            delta_content = patches
            delta_size = patch_size
        else:
            delta_type = "full"
            delta_content = new_content
            delta_size = full_size
        
        # Store delta
        await db.execute("""
            INSERT INTO version_deltas (
                resource_type, resource_id, branch,
                from_version, to_version, delta_type,
                delta_content, delta_size
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            resource_type, resource_id, branch,
            from_version, to_version, delta_type,
            json.dumps(delta_content), delta_size
        ))
    
    async def get_branch_version_summary(
        self,
        branch: str,
        resource_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get version summary for a branch"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Build query
            query = """
                SELECT 
                    resource_type,
                    COUNT(DISTINCT resource_id) as resource_count,
                    MAX(version) as max_version,
                    MAX(modified_at) as last_modified
                FROM resource_versions
                WHERE branch = ?
            """
            params = [branch]
            
            if resource_types:
                placeholders = ','.join('?' * len(resource_types))
                query += f" AND resource_type IN ({placeholders})"
                params.extend(resource_types)
            
            query += " GROUP BY resource_type"
            
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            
            summary = {
                "branch": branch,
                "resource_types": {},
                "total_resources": 0,
                "last_modified": None
            }
            
            for row in rows:
                summary["resource_types"][row['resource_type']] = {
                    "count": row['resource_count'],
                    "max_version": row['max_version'],
                    "last_modified": row['last_modified']
                }
                summary["total_resources"] += row['resource_count']
                
                if summary["last_modified"] is None or row['last_modified'] > summary["last_modified"]:
                    summary["last_modified"] = row['last_modified']
            
            return summary


# Global instance
_version_service: Optional[VersionTrackingService] = None


async def get_version_service() -> VersionTrackingService:
    """Get global version tracking service instance"""
    global _version_service
    if _version_service is None:
        _version_service = VersionTrackingService()
        await _version_service.initialize()
    return _version_service