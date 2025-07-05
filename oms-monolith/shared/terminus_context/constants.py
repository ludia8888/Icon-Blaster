"""
TerminusDB Branch and Author naming conventions
"""
import os
from typing import Tuple, Optional

# Environment detection
ENV = os.getenv("DEPLOY_ENV", "dev")
SERVICE_NAME = os.getenv("SERVICE_NAME", "oms")

# Default branch pattern: <env>/<service>/<purpose>
DEFAULT_BRANCH = f"{ENV}/{SERVICE_NAME}/main"

# Branch purposes
BRANCH_PURPOSES = {
    "main": "Main branch for service",
    "snapshot": "Read-only snapshot",
    "migration": "Schema migration branch",
    "scratch": "Temporary development branch",
    "test": "Testing branch"
}

# Read-only branch patterns
READONLY_PATTERNS = [
    "*/snapshot-*",
    "*/archive-*",
    "prod/*/snapshot-*"
]


def get_default_branch(service: Optional[str] = None) -> str:
    """Get default branch for a service."""
    service = service or SERVICE_NAME
    return f"{ENV}/{service}/main"


def format_branch(env: str, service: str, purpose: str) -> str:
    """Format a branch name according to convention."""
    return f"{env}/{service}/{purpose}"


def parse_branch(branch: str) -> Tuple[str, str, str]:
    """
    Parse branch name into (env, service, purpose).
    Returns ('unknown', 'unknown', branch) if not parseable.
    """
    parts = branch.split("/", 2)
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        return parts[0], parts[1], "main"
    else:
        return "unknown", "unknown", branch


def is_readonly_branch(branch: str) -> bool:
    """Check if branch is read-only based on patterns."""
    for pattern in READONLY_PATTERNS:
        # Simple glob matching
        if pattern.startswith("*/"):
            if branch.endswith(pattern[2:]):
                return True
        elif pattern.endswith("/*"):
            if branch.startswith(pattern[:-2]):
                return True
        elif "*" in pattern:
            # More complex pattern - split and match parts
            prefix, suffix = pattern.split("*", 1)
            if branch.startswith(prefix) and branch.endswith(suffix):
                return True
        elif branch == pattern:
            return True
    return False


def format_author(user_id: str, service: Optional[str] = None) -> str:
    """Format author string as user@service."""
    service = service or SERVICE_NAME
    return f"{user_id}@{service}"


def parse_author(author: str) -> Tuple[str, str]:
    """
    Parse author into (user_id, service).
    Returns (author, 'unknown') if not parseable.
    """
    if "@" in author:
        parts = author.split("@", 1)
        return parts[0], parts[1]
    return author, "unknown"