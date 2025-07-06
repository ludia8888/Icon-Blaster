"""
Scope-Role Mapping Tables and Documentation
Clear definition of relationship between IAM Scopes and OMS Roles
"""
from enum import Enum
from typing import Dict, List, Set, Optional
from dataclasses import dataclass

from models.permissions import Role
from shared.iam_contracts import IAMScope


@dataclass
class ScopeDefinition:
    """Definition of an IAM scope"""
    scope: str
    description: str
    resource_types: List[str]
    actions: List[str]
    examples: List[str]


@dataclass
class RoleDefinition:
    """Definition of an OMS role with scope requirements"""
    role: Role
    description: str
    required_scopes: List[str]  # Must have ALL of these
    optional_scopes: List[str]  # Can have ANY of these
    scope_patterns: List[str]   # Regex patterns for dynamic scopes


class ScopeRoleMatrix:
    """
    Comprehensive mapping between IAM Scopes and OMS Roles
    Provides clear documentation and validation logic
    """
    
    # Scope Definitions
    SCOPE_DEFINITIONS = {
        # === READ SCOPES ===
        IAMScope.ONTOLOGIES_READ: ScopeDefinition(
            scope=IAMScope.ONTOLOGIES_READ,
            description="Read access to all ontology resources",
            resource_types=["object_type", "link_type", "action_type", "function_type"],
            actions=["read", "list"],
            examples=[
                "GET /api/v1/schemas/main/object-types",
                "GET /api/v1/schemas/main/link-types/contains"
            ]
        ),
        
        IAMScope.SCHEMAS_READ: ScopeDefinition(
            scope=IAMScope.SCHEMAS_READ,
            description="Read access to schema structure and metadata",
            resource_types=["schema"],
            actions=["read", "list", "introspect"],
            examples=[
                "GET /api/v1/schemas",
                "GET /graphql (introspection queries)"
            ]
        ),
        
        IAMScope.BRANCHES_READ: ScopeDefinition(
            scope=IAMScope.BRANCHES_READ,
            description="Read access to branches and branch metadata",
            resource_types=["branch"],
            actions=["read", "list"],
            examples=[
                "GET /api/v1/branches",
                "GET /api/v1/branches/feature-x"
            ]
        ),
        
        IAMScope.PROPOSALS_READ: ScopeDefinition(
            scope=IAMScope.PROPOSALS_READ,
            description="Read access to proposals and review history",
            resource_types=["proposal"],
            actions=["read", "list"],
            examples=[
                "GET /api/v1/proposals",
                "GET /api/v1/proposals/123"
            ]
        ),
        
        IAMScope.AUDIT_READ: ScopeDefinition(
            scope=IAMScope.AUDIT_READ,
            description="Read access to audit logs and compliance data",
            resource_types=["audit"],
            actions=["read", "search"],
            examples=[
                "GET /api/v1/audit",
                "GET /api/v1/audit?user_id=alice&action=create"
            ]
        ),
        
        # === WRITE SCOPES ===
        IAMScope.ONTOLOGIES_WRITE: ScopeDefinition(
            scope=IAMScope.ONTOLOGIES_WRITE,
            description="Create and modify ontology resources",
            resource_types=["object_type", "link_type", "action_type", "function_type"],
            actions=["create", "update"],
            examples=[
                "POST /api/v1/schemas/main/object-types",
                "PUT /api/v1/schemas/main/object-types/User"
            ]
        ),
        
        IAMScope.SCHEMAS_WRITE: ScopeDefinition(
            scope=IAMScope.SCHEMAS_WRITE,
            description="Modify schema structure and configuration",
            resource_types=["schema"],
            actions=["create", "update", "revert"],
            examples=[
                "POST /api/v1/schemas",
                "POST /api/v1/schema/revert"
            ]
        ),
        
        IAMScope.BRANCHES_WRITE: ScopeDefinition(
            scope=IAMScope.BRANCHES_WRITE,
            description="Create, modify, and merge branches",
            resource_types=["branch"],
            actions=["create", "update", "delete", "merge"],
            examples=[
                "POST /api/v1/branches",
                "POST /api/v1/branches/feature-x/merge"
            ]
        ),
        
        IAMScope.PROPOSALS_WRITE: ScopeDefinition(
            scope=IAMScope.PROPOSALS_WRITE,
            description="Create and modify proposals",
            resource_types=["proposal"],
            actions=["create", "update"],
            examples=[
                "POST /api/v1/proposals",
                "PUT /api/v1/proposals/123"
            ]
        ),
        
        # === ADMIN SCOPES ===
        IAMScope.ONTOLOGIES_ADMIN: ScopeDefinition(
            scope=IAMScope.ONTOLOGIES_ADMIN,
            description="Full administrative access to ontologies including deletion",
            resource_types=["object_type", "link_type", "action_type", "function_type"],
            actions=["create", "read", "update", "delete", "admin"],
            examples=[
                "DELETE /api/v1/schemas/main/object-types/User",
                "POST /api/v1/admin/ontologies/bulk-import"
            ]
        ),
        
        IAMScope.PROPOSALS_APPROVE: ScopeDefinition(
            scope=IAMScope.PROPOSALS_APPROVE,
            description="Approve and reject proposals",
            resource_types=["proposal"],
            actions=["approve", "reject"],
            examples=[
                "POST /api/v1/proposals/123/approve",
                "POST /api/v1/proposals/123/reject"
            ]
        ),
        
        IAMScope.SYSTEM_ADMIN: ScopeDefinition(
            scope=IAMScope.SYSTEM_ADMIN,
            description="Full system administrative access",
            resource_types=["*"],
            actions=["*"],
            examples=[
                "All endpoints",
                "System configuration",
                "User management delegation"
            ]
        ),
        
        # === SERVICE SCOPES ===
        IAMScope.SERVICE_ACCOUNT: ScopeDefinition(
            scope=IAMScope.SERVICE_ACCOUNT,
            description="Service-to-service authentication",
            resource_types=["service"],
            actions=["authenticate", "read"],
            examples=[
                "mTLS authentication",
                "Service discovery"
            ]
        ),
        
        IAMScope.WEBHOOK_EXECUTE: ScopeDefinition(
            scope=IAMScope.WEBHOOK_EXECUTE,
            description="Execute webhook actions",
            resource_types=["webhook", "action_type"],
            actions=["execute"],
            examples=[
                "POST /action-types/123/execute",
                "Webhook callback execution"
            ]
        ),
    }
    
    # Role to Scope Mapping
    ROLE_SCOPE_MAPPING = {
        Role.ADMIN: RoleDefinition(
            role=Role.ADMIN,
            description="System administrators with full access",
            required_scopes=[IAMScope.SYSTEM_ADMIN],
            optional_scopes=[],
            scope_patterns=["api:*:admin", "api:system:*"]
        ),
        
        Role.DEVELOPER: RoleDefinition(
            role=Role.DEVELOPER,
            description="Developers who can create and modify ontologies",
            required_scopes=[
                IAMScope.ONTOLOGIES_READ,
                IAMScope.SCHEMAS_READ,
                IAMScope.BRANCHES_READ
            ],
            optional_scopes=[
                IAMScope.ONTOLOGIES_WRITE,
                IAMScope.SCHEMAS_WRITE,
                IAMScope.BRANCHES_WRITE,
                IAMScope.PROPOSALS_WRITE
            ],
            scope_patterns=["api:*:write", "api:*:read"]
        ),
        
        Role.REVIEWER: RoleDefinition(
            role=Role.REVIEWER,
            description="Reviewers who can approve proposals",
            required_scopes=[
                IAMScope.PROPOSALS_READ,
                IAMScope.PROPOSALS_APPROVE
            ],
            optional_scopes=[
                IAMScope.ONTOLOGIES_READ,
                IAMScope.SCHEMAS_READ,
                IAMScope.BRANCHES_READ,
                IAMScope.AUDIT_READ
            ],
            scope_patterns=["api:*:read", "api:proposals:approve"]
        ),
        
        Role.VIEWER: RoleDefinition(
            role=Role.VIEWER,
            description="Read-only access to all resources",
            required_scopes=[],
            optional_scopes=[
                IAMScope.ONTOLOGIES_READ,
                IAMScope.SCHEMAS_READ,
                IAMScope.BRANCHES_READ,
                IAMScope.PROPOSALS_READ,
                IAMScope.AUDIT_READ
            ],
            scope_patterns=["api:*:read"]
        ),
        
        Role.SERVICE_ACCOUNT: RoleDefinition(
            role=Role.SERVICE_ACCOUNT,
            description="Service accounts for system integration",
            required_scopes=[IAMScope.SERVICE_ACCOUNT],
            optional_scopes=[
                IAMScope.WEBHOOK_EXECUTE,
                IAMScope.ONTOLOGIES_READ,
                IAMScope.SCHEMAS_READ
            ],
            scope_patterns=["api:service:*", "api:webhook:*"]
        ),
    }
    
    @classmethod
    def get_role_for_scopes(cls, scopes: List[str]) -> List[Role]:
        """
        Determine which roles a user should have based on their scopes
        
        Args:
            scopes: List of IAM scopes
            
        Returns:
            List of OMS roles that match the scopes
        """
        scope_set = set(scopes)
        matching_roles = []
        
        # Check system admin first (takes precedence)
        if IAMScope.SYSTEM_ADMIN in scope_set:
            return [Role.ADMIN]
        
        # Check each role definition
        for role, definition in cls.ROLE_SCOPE_MAPPING.items():
            # Check if all required scopes are present
            required_set = set(definition.required_scopes)
            if required_set.issubset(scope_set):
                # Check if any optional scopes are present
                optional_set = set(definition.optional_scopes)
                if not definition.optional_scopes or optional_set.intersection(scope_set):
                    matching_roles.append(role)
            
            # Check pattern matching for dynamic scopes
            for pattern in definition.scope_patterns:
                import re
                regex_pattern = pattern.replace("*", ".*")
                if any(re.match(regex_pattern, scope) for scope in scopes):
                    if role not in matching_roles:
                        matching_roles.append(role)
        
        # If no specific roles match but user has read scopes, assign viewer
        read_scopes = [s for s in scopes if s.endswith(":read")]
        if read_scopes and not matching_roles:
            matching_roles.append(Role.VIEWER)
        
        return matching_roles
    
    @classmethod
    def get_scopes_for_role(cls, role: Role) -> List[str]:
        """
        Get all possible scopes for a role
        
        Args:
            role: OMS role
            
        Returns:
            List of scopes associated with the role
        """
        definition = cls.ROLE_SCOPE_MAPPING.get(role)
        if not definition:
            return []
        
        return definition.required_scopes + definition.optional_scopes
    
    @classmethod
    def validate_role_scope_assignment(cls, role: Role, scopes: List[str]) -> tuple[bool, List[str]]:
        """
        Validate if a role assignment is consistent with scopes
        
        Args:
            role: Assigned OMS role
            scopes: User's IAM scopes
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        definition = cls.ROLE_SCOPE_MAPPING.get(role)
        if not definition:
            return False, [f"Unknown role: {role}"]
        
        scope_set = set(scopes)
        issues = []
        
        # Check required scopes
        required_set = set(definition.required_scopes)
        missing_required = required_set - scope_set
        if missing_required:
            issues.append(f"Missing required scopes for {role}: {list(missing_required)}")
        
        # Check if user has any relevant scopes for optional roles
        if definition.optional_scopes:
            optional_set = set(definition.optional_scopes)
            if not optional_set.intersection(scope_set):
                issues.append(f"No optional scopes found for {role}: expected one of {definition.optional_scopes}")
        
        return len(issues) == 0, issues
    
    @classmethod
    def get_scope_hierarchy(cls) -> Dict[str, List[str]]:
        """
        Get scope hierarchy for understanding privilege escalation
        
        Returns:
            Dictionary mapping scope to list of scopes it implies
        """
        hierarchy = {
            IAMScope.SYSTEM_ADMIN: [
                IAMScope.ONTOLOGIES_ADMIN,
                IAMScope.PROPOSALS_APPROVE,
                IAMScope.AUDIT_READ
            ],
            IAMScope.ONTOLOGIES_ADMIN: [
                IAMScope.ONTOLOGIES_WRITE,
                IAMScope.ONTOLOGIES_READ
            ],
            IAMScope.ONTOLOGIES_WRITE: [
                IAMScope.ONTOLOGIES_READ
            ],
            IAMScope.SCHEMAS_WRITE: [
                IAMScope.SCHEMAS_READ
            ],
            IAMScope.BRANCHES_WRITE: [
                IAMScope.BRANCHES_READ
            ],
            IAMScope.PROPOSALS_WRITE: [
                IAMScope.PROPOSALS_READ
            ],
            IAMScope.PROPOSALS_APPROVE: [
                IAMScope.PROPOSALS_READ
            ]
        }
        return hierarchy


# Scope-Role Summary Table for Documentation
SCOPE_ROLE_SUMMARY_TABLE = """
# Scope-Role Mapping Summary

| Role | Scope Prefix | Example Scopes | Access Level |
|------|-------------|----------------|--------------|
| **admin** | `api:*:admin`, `api:system:*` | `api:ontologies:admin`, `api:system:admin` | Full system access |
| **developer** | `api:*:write` | `api:schemas:write`, `api:ontologies:write`, `api:branches:write` | Create/modify resources |
| **reviewer** | `api:*:read`, `api:proposals:approve` | `api:proposals:approve`, `api:audit:read` | Review and approve |
| **viewer** | `api:*:read` | `api:ontologies:read`, `api:schemas:read` | Read-only access |
| **service_account** | `api:service:*`, `api:webhook:*` | `api:service:account`, `api:webhook:execute` | Service integration |

## Scope Hierarchy

```
api:system:admin
├── api:ontologies:admin
│   ├── api:ontologies:write
│   │   └── api:ontologies:read
│   └── api:schemas:write
│       └── api:schemas:read
├── api:proposals:approve
│   └── api:proposals:read
└── api:audit:read

api:branches:write
└── api:branches:read

api:webhook:execute
api:service:account
```

## Usage Examples

### Admin User
```json
{
  "sub": "admin-001",
  "scope": "api:system:admin",
  "roles": ["admin"]
}
```

### Developer User
```json
{
  "sub": "dev-001", 
  "scope": "api:ontologies:write api:schemas:read api:branches:write api:proposals:write",
  "roles": ["developer"]
}
```

### Reviewer User
```json
{
  "sub": "reviewer-001",
  "scope": "api:ontologies:read api:proposals:approve api:audit:read", 
  "roles": ["reviewer"]
}
```
"""