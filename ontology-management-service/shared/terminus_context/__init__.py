"""
TerminusDB Context Management - Branch, Author, and Trace ID handling
"""
from .constants import (
    ENV,
    DEFAULT_BRANCH,
    get_default_branch,
    format_branch,
    parse_branch,
    is_readonly_branch
)
from .context import (
    get_author,
    set_author,
    get_branch,
    set_branch,
    get_trace_id,
    set_trace_id,
    get_commit_message,
    build_commit_message,
    OverrideBranch,
    OverrideAuthor,
    get_terminus_context
)

__all__ = [
    # Constants
    "ENV",
    "DEFAULT_BRANCH",
    "get_default_branch",
    "format_branch",
    "parse_branch",
    "is_readonly_branch",
    # Context functions
    "get_author",
    "set_author", 
    "get_branch",
    "set_branch",
    "get_trace_id",
    "set_trace_id",
    "get_commit_message",
    "build_commit_message",
    "OverrideBranch",
    "OverrideAuthor",
    "get_terminus_context"
]