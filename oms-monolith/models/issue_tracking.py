"""
Issue Tracking Models
Links all changes to issue IDs for complete traceability
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, validator
import re

from models.domain import BaseModel as DomainBaseModel


class IssueProvider(str, Enum):
    """Supported issue tracking providers"""
    JIRA = "jira"
    GITHUB = "github"
    GITLAB = "gitlab"
    AZURE_DEVOPS = "azure_devops"
    LINEAR = "linear"
    INTERNAL = "internal"  # Internal issue tracking


class IssueType(str, Enum):
    """Types of issues"""
    BUG = "bug"
    FEATURE = "feature"
    ENHANCEMENT = "enhancement"
    TASK = "task"
    HOTFIX = "hotfix"
    SECURITY = "security"
    REFACTOR = "refactor"
    DOCUMENTATION = "documentation"


class IssuePriority(str, Enum):
    """Issue priority levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueStatus(str, Enum):
    """Issue status"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    CLOSED = "closed"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class IssueReference(BaseModel):
    """Reference to an issue in external or internal tracking system"""
    
    provider: IssueProvider = Field(..., description="Issue tracking provider")
    issue_id: str = Field(..., description="Issue ID in the provider's system")
    issue_url: Optional[str] = Field(None, description="Full URL to the issue")
    issue_type: Optional[IssueType] = Field(None, description="Type of issue")
    priority: Optional[IssuePriority] = Field(None, description="Issue priority")
    status: Optional[IssueStatus] = Field(None, description="Current issue status")
    title: Optional[str] = Field(None, description="Issue title")
    assignee: Optional[str] = Field(None, description="Issue assignee")
    
    @validator('issue_id')
    def validate_issue_id(cls, v, values):
        """Validate issue ID format based on provider"""
        if 'provider' not in values:
            return v
            
        provider = values['provider']
        
        # Provider-specific validation patterns
        patterns = {
            IssueProvider.JIRA: r'^[A-Z]+-\d+$',  # e.g., PROJ-123
            IssueProvider.GITHUB: r'^\d+$',  # e.g., 123
            IssueProvider.GITLAB: r'^\d+$',  # e.g., 123
            IssueProvider.AZURE_DEVOPS: r'^\d+$',  # e.g., 123
            IssueProvider.LINEAR: r'^[A-Z]+-\d+$',  # e.g., ENG-123
            IssueProvider.INTERNAL: r'^[A-Z]+-\d+$',  # e.g., OMS-123
        }
        
        pattern = patterns.get(provider)
        if pattern and not re.match(pattern, v):
            raise ValueError(f"Invalid issue ID format for {provider.value}: {v}")
        
        return v
    
    def get_display_name(self) -> str:
        """Get displayable issue reference"""
        if self.provider == IssueProvider.JIRA:
            return f"JIRA-{self.issue_id}"
        elif self.provider == IssueProvider.GITHUB:
            return f"GH-{self.issue_id}"
        elif self.provider == IssueProvider.GITLAB:
            return f"GL-{self.issue_id}"
        elif self.provider == IssueProvider.AZURE_DEVOPS:
            return f"AZ-{self.issue_id}"
        elif self.provider == IssueProvider.LINEAR:
            return f"LINEAR-{self.issue_id}"
        else:
            return self.issue_id


class IssueRequirement(BaseModel):
    """Configuration for issue requirement policies"""
    
    # Global settings
    enabled: bool = Field(True, description="Whether issue linking is required")
    enforce_for_production: bool = Field(True, description="Strictly enforce for production branches")
    allow_emergency_override: bool = Field(True, description="Allow emergency overrides with justification")
    
    # Branch-specific rules
    exempt_branches: List[str] = Field(
        default_factory=lambda: ["sandbox", "experiment", "personal"],
        description="Branches exempt from issue requirements"
    )
    
    # Operation-specific rules
    require_for_schema_changes: bool = Field(True, description="Require for schema modifications")
    require_for_deletions: bool = Field(True, description="Require for deletion operations")
    require_for_acl_changes: bool = Field(True, description="Require for ACL modifications")
    require_for_merges: bool = Field(True, description="Require for branch merges")
    
    # Issue type requirements
    allowed_issue_types_for_hotfix: List[IssueType] = Field(
        default_factory=lambda: [IssueType.HOTFIX, IssueType.BUG, IssueType.SECURITY],
        description="Issue types allowed for hotfix changes"
    )
    
    # Validation settings
    validate_issue_status: bool = Field(True, description="Validate that issue is in appropriate status")
    allowed_statuses: List[IssueStatus] = Field(
        default_factory=lambda: [IssueStatus.IN_PROGRESS, IssueStatus.IN_REVIEW],
        description="Allowed issue statuses for changes"
    )
    
    # Additional validation
    validate_assignee: bool = Field(False, description="Validate that user is assigned to the issue")
    require_issue_description: bool = Field(True, description="Require issue to have description")
    minimum_issue_age_hours: int = Field(0, description="Minimum age of issue before changes allowed")


class ChangeIssueLink(BaseModel):
    """Links a change to one or more issues"""
    
    change_id: str = Field(..., description="ID of the change (commit hash, operation ID, etc.)")
    change_type: str = Field(..., description="Type of change (schema, acl, branch, etc.)")
    branch_name: str = Field(..., description="Branch where change occurred")
    
    # Primary issue (required)
    primary_issue: IssueReference = Field(..., description="Primary issue this change addresses")
    
    # Related issues (optional)
    related_issues: List[IssueReference] = Field(
        default_factory=list,
        description="Other related issues"
    )
    
    # Override information (if emergency)
    emergency_override: bool = Field(False, description="Whether this was an emergency override")
    override_justification: Optional[str] = Field(None, description="Justification for override")
    override_approver: Optional[str] = Field(None, description="Who approved the override")
    
    # Metadata
    linked_by: str = Field(..., description="User who linked the issue")
    linked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Validation context
    validation_result: Optional[Dict[str, Any]] = Field(None, description="Issue validation results")
    
    def get_all_issues(self) -> List[IssueReference]:
        """Get all linked issues"""
        return [self.primary_issue] + self.related_issues


class IssueValidationResult(BaseModel):
    """Result of issue validation"""
    
    valid: bool = Field(..., description="Whether the issue reference is valid")
    issue_ref: Optional[IssueReference] = Field(None, description="Validated issue reference")
    
    # Validation details
    exists: bool = Field(False, description="Whether issue exists in tracking system")
    status_valid: bool = Field(False, description="Whether issue status is appropriate")
    type_valid: bool = Field(False, description="Whether issue type is appropriate")
    assignee_valid: bool = Field(False, description="Whether assignee is valid")
    age_valid: bool = Field(False, description="Whether issue age meets requirements")
    
    # Error information
    error_message: Optional[str] = Field(None, description="Validation error message")
    validation_warnings: List[str] = Field(default_factory=list, description="Non-blocking warnings")
    
    # Additional metadata from issue tracker
    issue_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional issue metadata")


class BulkIssueValidationRequest(BaseModel):
    """Request to validate multiple issue references"""
    
    issue_refs: List[IssueReference] = Field(..., description="Issue references to validate")
    context: Dict[str, Any] = Field(default_factory=dict, description="Validation context")
    
    # Validation options
    check_status: bool = Field(True, description="Check issue status")
    check_assignee: bool = Field(False, description="Check assignee")
    fetch_metadata: bool = Field(True, description="Fetch additional metadata")


class IssueTrackingConfig(BaseModel):
    """Configuration for issue tracking integration"""
    
    # Provider configurations
    providers: Dict[IssueProvider, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Provider-specific configurations"
    )
    
    # Default provider
    default_provider: IssueProvider = Field(
        IssueProvider.INTERNAL,
        description="Default issue provider"
    )
    
    # Requirement policies
    requirements: IssueRequirement = Field(
        default_factory=IssueRequirement,
        description="Issue requirement policies"
    )
    
    # Integration settings
    cache_ttl_seconds: int = Field(300, description="Cache TTL for issue metadata")
    validation_timeout_seconds: int = Field(10, description="Timeout for issue validation")
    batch_validation_size: int = Field(10, description="Batch size for bulk validation")
    
    # UI/UX settings
    show_issue_links_in_ui: bool = Field(True, description="Show issue links in UI")
    allow_manual_linking: bool = Field(True, description="Allow manual issue linking")
    suggest_related_issues: bool = Field(True, description="Suggest related issues based on context")


# Helper functions

def parse_issue_reference(text: str) -> Optional[IssueReference]:
    """
    Parse issue reference from text
    Supports formats like:
    - JIRA: PROJ-123
    - GitHub: #123 or GH-123
    - GitLab: !123 or GL-123
    - Linear: ENG-123
    """
    # Linear pattern (check first as it's more specific)
    linear_match = re.match(r'^(ENG|PM|BUG|TASK)-(\d+)$', text, re.IGNORECASE)
    if linear_match:
        return IssueReference(
            provider=IssueProvider.LINEAR,
            issue_id=text.upper()
        )
    
    # JIRA pattern (generic A-Z prefix)
    jira_match = re.match(r'^([A-Z]+)-(\d+)$', text)
    if jira_match and jira_match.group(1) not in ['ENG', 'PM', 'BUG', 'TASK', 'OMS', 'GH', 'GL']:
        return IssueReference(
            provider=IssueProvider.JIRA,
            issue_id=text
        )
    
    # GitHub pattern
    github_match = re.match(r'^#(\d+)$', text)
    if github_match:
        return IssueReference(
            provider=IssueProvider.GITHUB,
            issue_id=github_match.group(1)
        )
    
    github_explicit_match = re.match(r'^GH-(\d+)$', text, re.IGNORECASE)
    if github_explicit_match:
        return IssueReference(
            provider=IssueProvider.GITHUB,
            issue_id=github_explicit_match.group(1)
        )
    
    # GitLab pattern
    gitlab_match = re.match(r'^!(\d+)$', text)
    if gitlab_match:
        return IssueReference(
            provider=IssueProvider.GITLAB,
            issue_id=gitlab_match.group(1)
        )
    
    gitlab_explicit_match = re.match(r'^GL-(\d+)$', text, re.IGNORECASE)
    if gitlab_explicit_match:
        return IssueReference(
            provider=IssueProvider.GITLAB,
            issue_id=gitlab_explicit_match.group(1)
        )
    
    # Internal pattern
    internal_match = re.match(r'^OMS-(\d+)$', text, re.IGNORECASE)
    if internal_match:
        return IssueReference(
            provider=IssueProvider.INTERNAL,
            issue_id=text.upper()
        )
    
    return None


def extract_issue_references(text: str) -> List[IssueReference]:
    """Extract all issue references from text (e.g., commit message, PR description)"""
    references = []
    
    # Patterns to search for
    patterns = [
        # JIRA style: PROJ-123
        (r'\b([A-Z]+-\d+)\b', lambda m: parse_issue_reference(m.group(1))),
        # GitHub style: #123
        (r'(?:^|\s)#(\d+)\b', lambda m: IssueReference(provider=IssueProvider.GITHUB, issue_id=m.group(1))),
        # GitLab style: !123
        (r'(?:^|\s)!(\d+)\b', lambda m: IssueReference(provider=IssueProvider.GITLAB, issue_id=m.group(1))),
        # Explicit formats: GH-123, GL-123
        (r'\b(GH-\d+)\b', lambda m: parse_issue_reference(m.group(1))),
        (r'\b(GL-\d+)\b', lambda m: parse_issue_reference(m.group(1))),
    ]
    
    for pattern, parser in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            ref = parser(match)
            if ref and ref not in references:
                references.append(ref)
    
    return references