"""
Issue Tracking Service
Validates and enforces issue linking requirements for all changes
"""
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from abc import ABC, abstractmethod

from database.clients import create_basic_client
from models.issue_tracking import (
    IssueProvider, IssueReference, IssueValidationResult, IssueRequirement,
    IssueTrackingConfig, ChangeIssueLink, IssueStatus, IssueType,
    parse_issue_reference, extract_issue_references
)
from core.auth_utils import UserContext
from common_logging.setup import get_logger

logger = get_logger(__name__)


class IssueProviderClient(ABC):
    """Abstract base class for issue provider integrations"""
    
    @abstractmethod
    async def validate_issue(self, issue_id: str) -> IssueValidationResult:
        """Validate that an issue exists and get its metadata"""
        pass
    
    @abstractmethod
    async def get_issue_metadata(self, issue_id: str) -> Dict[str, Any]:
        """Get detailed issue metadata"""
        pass
    
    @abstractmethod
    async def check_user_assignment(self, issue_id: str, user_email: str) -> bool:
        """Check if user is assigned to the issue"""
        pass


class JiraClient(IssueProviderClient):
    """JIRA integration client"""
    
    def __init__(self, base_url: str, api_token: str, email: str):
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.email = email
        self.client = create_basic_client(
            base_url=self.base_url,
            timeout=10.0
        )
        # Set auth headers for all requests
        self._auth_headers = {
            "Accept": "application/json",
            "Authorization": f"Basic {self._encode_credentials()}"
        }
    
    async def validate_issue(self, issue_id: str) -> IssueValidationResult:
        """Validate JIRA issue"""
        try:
            response = await self.client.get(f"/rest/api/3/issue/{issue_id}", headers=self._auth_headers)
            
            if response.status_code == 404:
                return IssueValidationResult(
                    valid=False,
                    exists=False,
                    error_message=f"Issue {issue_id} not found in JIRA"
                )
            
            if response.status_code != 200:
                return IssueValidationResult(
                    valid=False,
                    error_message=f"JIRA API error: {response.status_code}"
                )
            
            data = response.json()
            fields = data.get("fields", {})
            
            # Extract issue details
            issue_ref = IssueReference(
                provider=IssueProvider.JIRA,
                issue_id=issue_id,
                issue_url=f"{self.base_url}/browse/{issue_id}",
                title=fields.get("summary"),
                status=self._map_jira_status(fields.get("status", {}).get("name")),
                issue_type=self._map_jira_type(fields.get("issuetype", {}).get("name")),
                assignee=fields.get("assignee", {}).get("emailAddress")
            )
            
            # Calculate age
            created = fields.get("created")
            age_valid = True
            if created:
                created_date = datetime.fromisoformat(created.replace('Z', '+00:00'))
                age_hours = (datetime.now(timezone.utc) - created_date).total_seconds() / 3600
                age_valid = age_hours >= 0  # Can be configured
            
            return IssueValidationResult(
                valid=True,
                issue_ref=issue_ref,
                exists=True,
                status_valid=issue_ref.status in [IssueStatus.IN_PROGRESS, IssueStatus.IN_REVIEW],
                type_valid=True,
                age_valid=age_valid,
                issue_metadata={
                    "key": data.get("key"),
                    "project": fields.get("project", {}).get("key"),
                    "created": created,
                    "updated": fields.get("updated"),
                    "priority": fields.get("priority", {}).get("name"),
                    "labels": fields.get("labels", [])
                }
            )
            
        except Exception as e:
            logger.error(f"Error validating JIRA issue {issue_id}: {e}")
            return IssueValidationResult(
                valid=False,
                error_message=f"Failed to validate issue: {str(e)}"
            )
    
    async def get_issue_metadata(self, issue_id: str) -> Dict[str, Any]:
        """Get JIRA issue metadata"""
        try:
            response = await self.client.get(f"/rest/api/3/issue/{issue_id}", headers=self._auth_headers)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Error getting JIRA issue metadata: {e}")
        return {}
    
    async def check_user_assignment(self, issue_id: str, user_email: str) -> bool:
        """Check if user is assigned to JIRA issue"""
        try:
            metadata = await self.get_issue_metadata(issue_id)
            assignee = metadata.get("fields", {}).get("assignee", {}).get("emailAddress")
            return assignee == user_email
        except Exception:
            return False
    
    def _map_jira_status(self, jira_status: str) -> IssueStatus:
        """Map JIRA status to internal status"""
        status_map = {
            "To Do": IssueStatus.OPEN,
            "In Progress": IssueStatus.IN_PROGRESS,
            "In Review": IssueStatus.IN_REVIEW,
            "Done": IssueStatus.CLOSED,
            "Closed": IssueStatus.CLOSED,
            "Resolved": IssueStatus.RESOLVED,
            "Cancelled": IssueStatus.CANCELLED
        }
        return status_map.get(jira_status, IssueStatus.OPEN)
    
    def _map_jira_type(self, jira_type: str) -> IssueType:
        """Map JIRA issue type to internal type"""
        type_map = {
            "Bug": IssueType.BUG,
            "Story": IssueType.FEATURE,
            "Task": IssueType.TASK,
            "Epic": IssueType.FEATURE,
            "Improvement": IssueType.ENHANCEMENT,
            "Security": IssueType.SECURITY
        }
        return type_map.get(jira_type, IssueType.TASK)
    
    def _encode_credentials(self) -> str:
        """Encode email and API token for Basic auth"""
        import base64
        credentials = f"{self.email}:{self.api_token}"
        return base64.b64encode(credentials.encode()).decode()


class GitHubClient(IssueProviderClient):
    """GitHub integration client"""
    
    def __init__(self, token: str, owner: str, repo: str):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.client = create_basic_client(
            base_url="https://api.github.com",
            timeout=10.0
        )
        self._auth_headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    async def validate_issue(self, issue_id: str) -> IssueValidationResult:
        """Validate GitHub issue"""
        try:
            url = f"https://api.github.com/repos/{self.owner}/{self.repo}/issues/{issue_id}"
            response = await self.client.get(url)
            
            if response.status_code == 404:
                return IssueValidationResult(
                    valid=False,
                    exists=False,
                    error_message=f"Issue #{issue_id} not found in GitHub"
                )
            
            if response.status_code != 200:
                return IssueValidationResult(
                    valid=False,
                    error_message=f"GitHub API error: {response.status_code}"
                )
            
            data = response.json()
            
            # Extract issue details
            issue_ref = IssueReference(
                provider=IssueProvider.GITHUB,
                issue_id=issue_id,
                issue_url=data.get("html_url"),
                title=data.get("title"),
                status=IssueStatus.OPEN if data.get("state") == "open" else IssueStatus.CLOSED,
                assignee=data.get("assignee", {}).get("login") if data.get("assignee") else None
            )
            
            # Determine issue type from labels
            labels = [label.get("name").lower() for label in data.get("labels", [])]
            issue_type = IssueType.TASK
            if "bug" in labels:
                issue_type = IssueType.BUG
            elif "feature" in labels or "enhancement" in labels:
                issue_type = IssueType.FEATURE
            elif "security" in labels:
                issue_type = IssueType.SECURITY
            issue_ref.issue_type = issue_type
            
            # Calculate age
            created = data.get("created_at")
            age_valid = True
            if created:
                created_date = datetime.fromisoformat(created.replace('Z', '+00:00'))
                age_hours = (datetime.now(timezone.utc) - created_date).total_seconds() / 3600
                age_valid = age_hours >= 0
            
            return IssueValidationResult(
                valid=True,
                issue_ref=issue_ref,
                exists=True,
                status_valid=data.get("state") == "open",
                type_valid=True,
                age_valid=age_valid,
                issue_metadata={
                    "number": data.get("number"),
                    "state": data.get("state"),
                    "created_at": created,
                    "updated_at": data.get("updated_at"),
                    "labels": labels,
                    "milestone": data.get("milestone", {}).get("title") if data.get("milestone") else None
                }
            )
            
        except Exception as e:
            logger.error(f"Error validating GitHub issue {issue_id}: {e}")
            return IssueValidationResult(
                valid=False,
                error_message=f"Failed to validate issue: {str(e)}"
            )
    
    async def get_issue_metadata(self, issue_id: str) -> Dict[str, Any]:
        """Get GitHub issue metadata"""
        try:
            url = f"https://api.github.com/repos/{self.owner}/{self.repo}/issues/{issue_id}"
            response = await self.client.get(url)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Error getting GitHub issue metadata: {e}")
        return {}
    
    async def check_user_assignment(self, issue_id: str, user_email: str) -> bool:
        """Check if user is assigned to GitHub issue"""
        try:
            metadata = await self.get_issue_metadata(issue_id)
            assignees = metadata.get("assignees", [])
            # Note: Would need to map GitHub username to email
            return any(assignee.get("login") == user_email for assignee in assignees)
        except Exception:
            return False


class InternalIssueClient(IssueProviderClient):
    """Internal issue tracking client (mock implementation)"""
    
    def __init__(self):
        # In a real implementation, this would connect to an internal database
        self.mock_issues = {
            "OMS-001": {
                "title": "Implement audit logging",
                "status": IssueStatus.IN_PROGRESS,
                "type": IssueType.FEATURE,
                "assignee": "developer@example.com",
                "created": datetime.now(timezone.utc) - timedelta(days=2)
            },
            "OMS-002": {
                "title": "Fix schema validation bug",
                "status": IssueStatus.OPEN,
                "type": IssueType.BUG,
                "assignee": "developer@example.com",
                "created": datetime.now(timezone.utc) - timedelta(hours=1)
            }
        }
    
    async def validate_issue(self, issue_id: str) -> IssueValidationResult:
        """Validate internal issue"""
        issue_data = self.mock_issues.get(issue_id.upper())
        
        if not issue_data:
            return IssueValidationResult(
                valid=False,
                exists=False,
                error_message=f"Issue {issue_id} not found"
            )
        
        issue_ref = IssueReference(
            provider=IssueProvider.INTERNAL,
            issue_id=issue_id.upper(),
            issue_url=f"http://internal.tracker/issues/{issue_id}",
            title=issue_data["title"],
            status=issue_data["status"],
            issue_type=issue_data["type"],
            assignee=issue_data["assignee"]
        )
        
        age_hours = (datetime.now(timezone.utc) - issue_data["created"]).total_seconds() / 3600
        
        return IssueValidationResult(
            valid=True,
            issue_ref=issue_ref,
            exists=True,
            status_valid=issue_data["status"] in [IssueStatus.IN_PROGRESS, IssueStatus.IN_REVIEW],
            type_valid=True,
            age_valid=age_hours >= 0,
            assignee_valid=True,
            issue_metadata={
                "created": issue_data["created"].isoformat(),
                "internal_id": issue_id
            }
        )
    
    async def get_issue_metadata(self, issue_id: str) -> Dict[str, Any]:
        """Get internal issue metadata"""
        issue_data = self.mock_issues.get(issue_id.upper())
        if issue_data:
            return {
                "id": issue_id,
                "title": issue_data["title"],
                "status": issue_data["status"].value,
                "type": issue_data["type"].value,
                "assignee": issue_data["assignee"],
                "created": issue_data["created"].isoformat()
            }
        return {}
    
    async def check_user_assignment(self, issue_id: str, user_email: str) -> bool:
        """Check if user is assigned to internal issue"""
        issue_data = self.mock_issues.get(issue_id.upper())
        return issue_data and issue_data.get("assignee") == user_email


class IssueTrackingService:
    """
    Central service for issue tracking validation and enforcement
    """
    
    def __init__(self, config: Optional[IssueTrackingConfig] = None):
        self.config = config or IssueTrackingConfig()
        self.providers: Dict[IssueProvider, IssueProviderClient] = {}
        self._cache: Dict[str, Tuple[IssueValidationResult, datetime]] = {}
        self._initialized = False
    
    async def initialize(self):
        """Initialize issue tracking providers"""
        if self._initialized:
            return
        
        # Initialize configured providers
        for provider, provider_config in self.config.providers.items():
            try:
                if provider == IssueProvider.JIRA:
                    self.providers[provider] = JiraClient(
                        base_url=provider_config["base_url"],
                        api_token=provider_config["api_token"],
                        email=provider_config["email"]
                    )
                elif provider == IssueProvider.GITHUB:
                    self.providers[provider] = GitHubClient(
                        token=provider_config["token"],
                        owner=provider_config["owner"],
                        repo=provider_config["repo"]
                    )
                elif provider == IssueProvider.INTERNAL:
                    self.providers[provider] = InternalIssueClient()
                    
                logger.info(f"Initialized issue provider: {provider.value}")
                
            except Exception as e:
                logger.error(f"Failed to initialize provider {provider.value}: {e}")
        
        # Always have internal provider as fallback
        if IssueProvider.INTERNAL not in self.providers:
            self.providers[IssueProvider.INTERNAL] = InternalIssueClient()
        
        self._initialized = True
        logger.info("Issue tracking service initialized")
    
    async def validate_issue_requirement(
        self,
        user: UserContext,
        change_type: str,
        branch_name: str,
        issue_refs: List[IssueReference],
        emergency_override: bool = False,
        override_justification: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Validate that issue requirements are met for a change
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        requirements = self.config.requirements
        
        # Check if issue linking is enabled
        if not requirements.enabled:
            return True, ""
        
        # Check if branch is exempt
        if branch_name in requirements.exempt_branches:
            return True, ""
        
        # Check for pattern-based exemptions (e.g., personal/*)
        for exempt_pattern in requirements.exempt_branches:
            if branch_name.startswith(exempt_pattern):
                return True, ""
        
        # Check if operation requires issue
        operation_requires_issue = False
        if change_type == "schema" and requirements.require_for_schema_changes:
            operation_requires_issue = True
        elif change_type == "deletion" and requirements.require_for_deletions:
            operation_requires_issue = True
        elif change_type == "acl" and requirements.require_for_acl_changes:
            operation_requires_issue = True
        elif change_type == "merge" and requirements.require_for_merges:
            operation_requires_issue = True
        
        if not operation_requires_issue:
            return True, ""
        
        # Check emergency override
        if emergency_override and requirements.allow_emergency_override:
            if not override_justification:
                return False, "Emergency override requires justification"
            if len(override_justification) < 20:
                return False, "Emergency override justification must be at least 20 characters"
            # Log emergency override for audit
            logger.warning(
                f"Emergency override used by {user.username} for {change_type} "
                f"on {branch_name}: {override_justification}"
            )
            return True, ""
        
        # Validate that at least one issue is provided
        if not issue_refs:
            return False, f"Issue reference required for {change_type} operations"
        
        # Validate all provided issues
        validation_errors = []
        valid_issues = []
        
        for issue_ref in issue_refs:
            result = await self.validate_issue(issue_ref)
            
            if not result.valid:
                validation_errors.append(
                    f"{issue_ref.get_display_name()}: {result.error_message}"
                )
                continue
            
            # Additional validation based on requirements
            if requirements.validate_issue_status:
                if not result.status_valid:
                    allowed_statuses = [s.value for s in requirements.allowed_statuses]
                    validation_errors.append(
                        f"{issue_ref.get_display_name()}: Invalid status. "
                        f"Must be one of: {', '.join(allowed_statuses)}"
                    )
                    continue
            
            if requirements.validate_assignee and user.email:
                if not result.assignee_valid:
                    provider = self.providers.get(issue_ref.provider)
                    if provider:
                        is_assigned = await provider.check_user_assignment(
                            issue_ref.issue_id, user.email
                        )
                        if not is_assigned:
                            validation_errors.append(
                                f"{issue_ref.get_display_name()}: "
                                f"User {user.username} is not assigned to this issue"
                            )
                            continue
            
            valid_issues.append(result)
        
        # Check if we have at least one valid issue
        if not valid_issues:
            error_msg = "No valid issues found. Errors: " + "; ".join(validation_errors)
            return False, error_msg
        
        # Additional checks for production branches
        if requirements.enforce_for_production and branch_name in ["main", "master", "production"]:
            # Stricter validation for production
            hotfix_types = requirements.allowed_issue_types_for_hotfix
            
            has_appropriate_type = any(
                result.issue_ref.issue_type in hotfix_types
                for result in valid_issues
                if result.issue_ref.issue_type
            )
            
            if not has_appropriate_type:
                allowed_types = [t.value for t in hotfix_types]
                return False, (
                    f"Production changes require issue type to be one of: "
                    f"{', '.join(allowed_types)}"
                )
        
        return True, ""
    
    async def validate_issue(self, issue_ref: IssueReference) -> IssueValidationResult:
        """Validate a single issue reference"""
        # Check cache first
        cache_key = f"{issue_ref.provider.value}:{issue_ref.issue_id}"
        if cache_key in self._cache:
            result, cached_at = self._cache[cache_key]
            if (datetime.now(timezone.utc) - cached_at).total_seconds() < self.config.cache_ttl_seconds:
                return result
        
        # Get appropriate provider
        provider = self.providers.get(issue_ref.provider)
        if not provider:
            return IssueValidationResult(
                valid=False,
                error_message=f"Issue provider {issue_ref.provider.value} not configured"
            )
        
        # Validate with provider
        try:
            result = await asyncio.wait_for(
                provider.validate_issue(issue_ref.issue_id),
                timeout=self.config.validation_timeout_seconds
            )
            
            # Cache result
            self._cache[cache_key] = (result, datetime.now(timezone.utc))
            
            return result
            
        except asyncio.TimeoutError:
            return IssueValidationResult(
                valid=False,
                error_message=f"Timeout validating issue with {issue_ref.provider.value}"
            )
        except Exception as e:
            logger.error(f"Error validating issue {issue_ref.issue_id}: {e}")
            return IssueValidationResult(
                valid=False,
                error_message=f"Failed to validate issue: {str(e)}"
            )
    
    async def link_change_to_issues(
        self,
        change_id: str,
        change_type: str,
        branch_name: str,
        user: UserContext,
        primary_issue: IssueReference,
        related_issues: Optional[List[IssueReference]] = None,
        emergency_override: bool = False,
        override_justification: Optional[str] = None
    ) -> ChangeIssueLink:
        """Create a link between a change and issues"""
        # Validate all issues
        all_issues = [primary_issue] + (related_issues or [])
        validation_results = []
        
        for issue_ref in all_issues:
            result = await self.validate_issue(issue_ref)
            validation_results.append((issue_ref, result))
        
        # Create link record
        link = ChangeIssueLink(
            change_id=change_id,
            change_type=change_type,
            branch_name=branch_name,
            primary_issue=primary_issue,
            related_issues=related_issues or [],
            emergency_override=emergency_override,
            override_justification=override_justification,
            override_approver=user.username if emergency_override else None,
            linked_by=user.username,
            validation_result={
                issue.issue_id: {
                    "valid": result.valid,
                    "error": result.error_message
                }
                for issue, result in validation_results
            }
        )
        
        # Store link in database
        try:
            from core.issue_tracking.issue_database import get_issue_database
            issue_db = await get_issue_database()
            await issue_db.store_change_issue_link(link)
        except Exception as e:
            logger.error(f"Failed to store change-issue link: {e}")
        
        return link
    
    def extract_issues_from_text(self, text: str) -> List[IssueReference]:
        """Extract issue references from text (commit message, PR description, etc)"""
        return extract_issue_references(text)
    
    async def suggest_related_issues(
        self,
        branch_name: str,
        change_type: str,
        resource_name: Optional[str] = None
    ) -> List[IssueReference]:
        """Suggest related issues based on context"""
        # This would integrate with issue tracking systems to suggest relevant issues
        # For now, return empty list
        return []


# Global instance
_issue_service: Optional[IssueTrackingService] = None


async def get_issue_service() -> IssueTrackingService:
    """Get global issue tracking service instance"""
    global _issue_service
    if _issue_service is None:
        _issue_service = IssueTrackingService()
        await _issue_service.initialize()
    return _issue_service