"""
TerminusDB Audit Service
Leverages TerminusDB's built-in Git-style commit history for audit trail

BENEFITS OVER SQLITE/POSTGRES APPROACH:
1. No separate audit tables needed - uses native commit history
2. Automatic time-travel queries via commit checkouts
3. Tamper-proof by design (Git-style immutable commits)
4. Unified with business data (no data fragmentation)
5. Built-in diff tracking for all changes

FEATURES:
- Query audit log by time range, author, resource
- Time-travel to any point in history
- Change diff analysis
- Compliance reporting
- No additional storage overhead
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

from terminusdb_client import WOQLClient
from models.audit_events import AuditAction, ResourceType, AuditEventFilter
from utils.logger import get_logger

logger = get_logger(__name__)


class AuditOperation(Enum):
    """Types of audit operations from TerminusDB diffs"""
    INSERT = "InsertDocument"
    UPDATE = "UpdateDocument"
    DELETE = "DeleteDocument"
    SCHEMA_CHANGE = "SchemaChange"


class TerminusAuditService:
    """
    Audit service using TerminusDB's native commit history
    
    This replaces the need for separate audit databases by using
    TerminusDB's built-in versioning and commit tracking
    """
    
    def __init__(self, client: WOQLClient):
        self.client = client
        self._commit_cache = {}  # Cache commit metadata for performance
    
    async def log_operation(
        self,
        action: AuditAction,
        resource_type: ResourceType,
        resource_id: str,
        author: str,
        changes: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log an audit operation by creating a descriptive commit
        
        The commit message contains structured data for querying
        """
        # Build structured commit message
        audit_data = {
            "action": action.value,
            "resource_type": resource_type.value,
            "resource_id": resource_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "changes": changes,
            "metadata": metadata
        }
        
        # Create human-readable message with embedded JSON
        message = f"[{action.value}] {resource_type.value}/{resource_id}"
        if changes:
            message += f" | Changes: {len(changes)} fields"
        
        # Add structured data as JSON comment
        message += f"\n\n@audit:{json.dumps(audit_data, separators=(',', ':'))}"
        
        # Commit with author info
        try:
            commit_result = self.client.commit(
                message=message,
                author=author,
                commit_info=metadata or {}
            )
            
            logger.info(f"Audit logged: {action.value} on {resource_type.value}/{resource_id}")
            return commit_result.get("commit", "unknown")
            
        except Exception as e:
            logger.error(f"Failed to log audit operation: {e}")
            raise
    
    async def query_audit_log(
        self,
        filter_criteria: AuditEventFilter
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Query audit log from commit history
        
        Returns audit entries and total count
        """
        try:
            # Get full commit history
            history = self.client.get_commit_history()
            
            # Filter commits based on criteria
            filtered_entries = []
            
            for commit in history:
                # Parse commit data
                entry = self._parse_commit_as_audit_entry(commit)
                
                if not entry:
                    continue
                
                # Apply filters
                if not self._matches_filter(entry, filter_criteria):
                    continue
                
                # Get detailed changes if needed
                if filter_criteria.include_changes:
                    entry["changes"] = await self._get_commit_changes(
                        commit["identifier"],
                        commit.get("parent")
                    )
                
                filtered_entries.append(entry)
            
            # Sort by timestamp (newest first)
            filtered_entries.sort(key=lambda x: x["timestamp"], reverse=True)
            
            # Apply pagination
            total_count = len(filtered_entries)
            start = filter_criteria.offset
            end = start + filter_criteria.limit
            paginated = filtered_entries[start:end]
            
            return paginated, total_count
            
        except Exception as e:
            logger.error(f"Failed to query audit log: {e}")
            return [], 0
    
    async def get_resource_history(
        self,
        resource_type: ResourceType,
        resource_id: str,
        include_diffs: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get complete history for a specific resource
        
        Shows all changes made to the resource over time
        """
        history = []
        
        try:
            commits = self.client.get_commit_history()
            
            for i, commit in enumerate(commits):
                # Check if this commit affected the resource
                if self._commit_affects_resource(commit, resource_type, resource_id):
                    entry = {
                        "commit_id": commit["identifier"],
                        "timestamp": commit["timestamp"],
                        "author": commit.get("author", "unknown"),
                        "message": commit.get("message", ""),
                        "parent": commit.get("parent")
                    }
                    
                    if include_diffs and commit.get("parent"):
                        # Get what changed in this commit
                        diff = await self._get_resource_diff(
                            commit["identifier"],
                            commit["parent"],
                            resource_type,
                            resource_id
                        )
                        entry["changes"] = diff
                    
                    history.append(entry)
            
            return history
            
        except Exception as e:
            logger.error(f"Failed to get resource history: {e}")
            return []
    
    async def get_resource_at_time(
        self,
        resource_type: ResourceType,
        resource_id: str,
        timestamp: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Get resource state at specific point in time
        
        Uses TerminusDB's time-travel feature
        """
        try:
            # Find the commit active at the given timestamp
            target_commit = self._find_commit_at_time(timestamp)
            
            if not target_commit:
                logger.warning(f"No commit found before {timestamp}")
                return None
            
            # Checkout to that commit
            original_branch = self.client.branch
            self.client.checkout(target_commit)
            
            try:
                # Build document ID
                doc_id = f"{resource_type.value}/{resource_id}"
                
                # Get document at that point in time
                document = self.client.get_document(doc_id)
                
                if document:
                    # Add temporal metadata
                    document["_audit_metadata"] = {
                        "retrieved_at_commit": target_commit,
                        "retrieved_for_time": timestamp.isoformat(),
                        "is_historical": True
                    }
                
                return document
                
            finally:
                # Always return to original branch
                self.client.checkout(original_branch)
                
        except Exception as e:
            logger.error(f"Failed to get resource at time: {e}")
            return None
    
    async def get_change_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        group_by: str = "day"
    ) -> Dict[str, Any]:
        """
        Get audit statistics for dashboards and monitoring
        """
        stats = {
            "total_changes": 0,
            "changes_by_action": {},
            "changes_by_resource_type": {},
            "changes_by_author": {},
            "changes_over_time": []
        }
        
        try:
            commits = self.client.get_commit_history()
            
            # Group commits by time period
            time_buckets = {}
            
            for commit in commits:
                entry = self._parse_commit_as_audit_entry(commit)
                if not entry:
                    continue
                
                # Apply time filters
                commit_time = datetime.fromisoformat(entry["timestamp"])
                if start_time and commit_time < start_time:
                    continue
                if end_time and commit_time > end_time:
                    continue
                
                # Update statistics
                stats["total_changes"] += 1
                
                # By action
                action = entry.get("action", "unknown")
                stats["changes_by_action"][action] = stats["changes_by_action"].get(action, 0) + 1
                
                # By resource type
                resource_type = entry.get("resource_type", "unknown")
                stats["changes_by_resource_type"][resource_type] = \
                    stats["changes_by_resource_type"].get(resource_type, 0) + 1
                
                # By author
                author = entry.get("author", "unknown")
                stats["changes_by_author"][author] = stats["changes_by_author"].get(author, 0) + 1
                
                # Time buckets
                bucket_key = self._get_time_bucket_key(commit_time, group_by)
                if bucket_key not in time_buckets:
                    time_buckets[bucket_key] = 0
                time_buckets[bucket_key] += 1
            
            # Convert time buckets to sorted list
            stats["changes_over_time"] = [
                {"time": k, "count": v}
                for k, v in sorted(time_buckets.items())
            ]
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get change statistics: {e}")
            return stats
    
    async def verify_audit_integrity(
        self,
        start_commit: Optional[str] = None,
        end_commit: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify audit log integrity using Git-style commit verification
        
        TerminusDB commits are immutable and chained, providing
        built-in tamper detection
        """
        result = {
            "is_valid": True,
            "commits_checked": 0,
            "issues": []
        }
        
        try:
            commits = self.client.get_commit_history()
            
            checking = False if start_commit else True
            
            for i, commit in enumerate(commits):
                if start_commit and commit["identifier"] == start_commit:
                    checking = True
                
                if not checking:
                    continue
                
                result["commits_checked"] += 1
                
                # Verify commit has required fields
                if not commit.get("identifier"):
                    result["is_valid"] = False
                    result["issues"].append(f"Commit {i} missing identifier")
                
                if not commit.get("timestamp"):
                    result["is_valid"] = False
                    result["issues"].append(f"Commit {commit['identifier']} missing timestamp")
                
                # Verify parent chain (except for initial commit)
                if i < len(commits) - 1:
                    expected_parent = commits[i + 1]["identifier"]
                    actual_parent = commit.get("parent")
                    
                    if actual_parent != expected_parent:
                        result["is_valid"] = False
                        result["issues"].append(
                            f"Commit {commit['identifier']} has incorrect parent"
                        )
                
                if end_commit and commit["identifier"] == end_commit:
                    break
            
            if result["is_valid"]:
                logger.info(f"Audit integrity verified: {result['commits_checked']} commits valid")
            else:
                logger.warning(f"Audit integrity issues found: {result['issues']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to verify audit integrity: {e}")
            result["is_valid"] = False
            result["issues"].append(str(e))
            return result
    
    def _parse_commit_as_audit_entry(self, commit: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse commit metadata into audit entry format"""
        try:
            message = commit.get("message", "")
            
            # Extract structured audit data from message
            audit_data = None
            if "@audit:" in message:
                audit_json = message.split("@audit:")[1].strip()
                try:
                    audit_data = json.loads(audit_json)
                except:
                    pass
            
            # Build audit entry
            entry = {
                "id": commit["identifier"],
                "timestamp": commit["timestamp"],
                "author": commit.get("author", "unknown"),
                "message": message.split("\n")[0],  # First line only
                "parent_commit": commit.get("parent")
            }
            
            # Merge structured data if available
            if audit_data:
                entry.update(audit_data)
            else:
                # Try to parse from commit message
                if "[" in message and "]" in message:
                    action = message[message.find("[")+1:message.find("]")]
                    entry["action"] = action
                
                if "/" in message:
                    parts = message.split("/")
                    if len(parts) >= 2:
                        entry["resource_type"] = parts[0].split()[-1]
                        entry["resource_id"] = parts[1].split()[0]
            
            return entry
            
        except Exception as e:
            logger.debug(f"Could not parse commit as audit entry: {e}")
            return None
    
    def _matches_filter(
        self,
        entry: Dict[str, Any],
        filter_criteria: AuditEventFilter
    ) -> bool:
        """Check if audit entry matches filter criteria"""
        # Time range filter
        if filter_criteria.start_time or filter_criteria.end_time:
            entry_time = datetime.fromisoformat(entry["timestamp"])
            
            if filter_criteria.start_time and entry_time < filter_criteria.start_time:
                return False
            if filter_criteria.end_time and entry_time > filter_criteria.end_time:
                return False
        
        # Actor filter
        if filter_criteria.actor_ids:
            if entry.get("author") not in filter_criteria.actor_ids:
                return False
        
        # Action filter
        if filter_criteria.actions:
            action_values = [a.value for a in filter_criteria.actions]
            if entry.get("action") not in action_values:
                return False
        
        # Resource type filter
        if filter_criteria.resource_types:
            type_values = [rt.value for rt in filter_criteria.resource_types]
            if entry.get("resource_type") not in type_values:
                return False
        
        # Resource ID filter
        if filter_criteria.resource_ids:
            if entry.get("resource_id") not in filter_criteria.resource_ids:
                return False
        
        return True
    
    def _commit_affects_resource(
        self,
        commit: Dict[str, Any],
        resource_type: ResourceType,
        resource_id: str
    ) -> bool:
        """Check if a commit affected a specific resource"""
        message = commit.get("message", "")
        
        # Check commit message
        resource_ref = f"{resource_type.value}/{resource_id}"
        if resource_ref in message:
            return True
        
        # Check structured audit data
        if "@audit:" in message:
            try:
                audit_json = message.split("@audit:")[1].strip()
                audit_data = json.loads(audit_json)
                
                return (
                    audit_data.get("resource_type") == resource_type.value and
                    audit_data.get("resource_id") == resource_id
                )
            except:
                pass
        
        return False
    
    async def _get_commit_changes(
        self,
        commit_id: str,
        parent_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Get detailed changes from a commit"""
        if not parent_id:
            # Initial commit - everything is new
            return [{"operation": "initial_commit"}]
        
        try:
            diff = self.client.diff(commit_id, parent_id)
            return self._format_diff_as_changes(diff)
        except Exception as e:
            logger.error(f"Failed to get commit changes: {e}")
            return []
    
    async def _get_resource_diff(
        self,
        commit_id: str,
        parent_id: str,
        resource_type: ResourceType,
        resource_id: str
    ) -> Dict[str, Any]:
        """Get diff for specific resource between commits"""
        try:
            diff = self.client.diff(commit_id, parent_id)
            
            # Filter diff to only include changes for this resource
            doc_id = f"{resource_type.value}/{resource_id}"
            resource_changes = {
                "added": [],
                "modified": [],
                "deleted": []
            }
            
            for operation in diff.get("operations", []):
                if operation.get("document", {}).get("@id") == doc_id:
                    if operation["@type"] == "InsertDocument":
                        resource_changes["added"].append(operation["document"])
                    elif operation["@type"] == "UpdateDocument":
                        resource_changes["modified"].append({
                            "before": operation.get("before"),
                            "after": operation.get("after")
                        })
                    elif operation["@type"] == "DeleteDocument":
                        resource_changes["deleted"].append(operation["document"])
            
            return resource_changes
            
        except Exception as e:
            logger.error(f"Failed to get resource diff: {e}")
            return {}
    
    def _format_diff_as_changes(self, diff: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format TerminusDB diff into structured changes"""
        changes = []
        
        for op in diff.get("operations", []):
            change = {
                "operation": op["@type"],
                "document_id": op.get("document", {}).get("@id"),
                "document_type": op.get("document", {}).get("@type")
            }
            
            if op["@type"] == "UpdateDocument":
                change["fields_changed"] = self._get_changed_fields(
                    op.get("before", {}),
                    op.get("after", {})
                )
            
            changes.append(change)
        
        return changes
    
    def _get_changed_fields(self, before: Dict, after: Dict) -> List[str]:
        """Get list of fields that changed between two states"""
        changed = []
        
        all_keys = set(before.keys()) | set(after.keys())
        
        for key in all_keys:
            if before.get(key) != after.get(key):
                changed.append(key)
        
        return changed
    
    def _find_commit_at_time(self, timestamp: datetime) -> Optional[str]:
        """Find the commit that was active at given timestamp"""
        commits = self.client.get_commit_history()
        
        for commit in commits:
            commit_time = datetime.fromisoformat(commit["timestamp"])
            if commit_time <= timestamp:
                return commit["identifier"]
        
        return None
    
    def _get_time_bucket_key(self, timestamp: datetime, group_by: str) -> str:
        """Get time bucket key for grouping"""
        if group_by == "hour":
            return timestamp.strftime("%Y-%m-%d %H:00")
        elif group_by == "day":
            return timestamp.strftime("%Y-%m-%d")
        elif group_by == "week":
            # Get start of week
            week_start = timestamp - timedelta(days=timestamp.weekday())
            return week_start.strftime("%Y-W%V")
        elif group_by == "month":
            return timestamp.strftime("%Y-%m")
        else:
            return timestamp.strftime("%Y-%m-%d")