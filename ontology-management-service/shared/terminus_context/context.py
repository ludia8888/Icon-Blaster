"""
Context variables and helpers for TerminusDB metadata
"""
import contextvars
from contextlib import contextmanager
from typing import Optional, Dict, Any
from datetime import datetime

from .constants import DEFAULT_BRANCH, SERVICE_NAME, format_author

# Context variables
_author_ctx = contextvars.ContextVar("terminus_author", default="anonymous@unknown")
_branch_ctx = contextvars.ContextVar("terminus_branch", default=DEFAULT_BRANCH)
_trace_id_ctx = contextvars.ContextVar("terminus_trace_id", default="")
_request_path_ctx = contextvars.ContextVar("request_path", default="")
_request_method_ctx = contextvars.ContextVar("request_method", default="")


# Author context
def get_author() -> str:
    """Get current author from context."""
    return _author_ctx.get()


def set_author(author: str):
    """Set author in context."""
    _author_ctx.set(author)


# Branch context
def get_branch() -> str:
    """Get current branch from context."""
    return _branch_ctx.get()


def set_branch(branch: str):
    """Set branch in context."""
    _branch_ctx.set(branch)


# Trace ID context
def get_trace_id() -> str:
    """Get current trace ID from context."""
    return _trace_id_ctx.get()


def set_trace_id(trace_id: str):
    """Set trace ID in context."""
    _trace_id_ctx.set(trace_id)


# Request context (for commit messages)
def set_request_context(method: str, path: str):
    """Set HTTP request context for commit message building."""
    _request_method_ctx.set(method)
    _request_path_ctx.set(path)


def get_commit_message(custom_msg: Optional[str] = None) -> str:
    """
    Get commit message. 
    If custom message provided, use it.
    Otherwise build from request context.
    """
    if custom_msg:
        return custom_msg
    return build_commit_message()


def build_commit_message() -> str:
    """Build commit message from context."""
    method = _request_method_ctx.get()
    path = _request_path_ctx.get()
    trace_id = get_trace_id()
    
    # Base message
    if method and path:
        msg = f"{method} {path}"
    else:
        msg = f"Operation via {SERVICE_NAME}"
    
    # Add trace ID if available
    if trace_id:
        msg += f" | trace={trace_id[:8]}"
    
    return msg


def get_terminus_context() -> Dict[str, Any]:
    """Get all terminus context as a dictionary."""
    return {
        "author": get_author(),
        "branch": get_branch(),
        "trace_id": get_trace_id(),
        "commit_msg": build_commit_message(),
        "timestamp": datetime.utcnow().isoformat()
    }


# Context managers for temporary overrides
@contextmanager
def OverrideBranch(branch: str):
    """Temporarily override branch in context."""
    token = _branch_ctx.set(branch)
    try:
        yield
    finally:
        _branch_ctx.reset(token)


@contextmanager  
def OverrideAuthor(author: str):
    """Temporarily override author in context."""
    token = _author_ctx.set(author)
    try:
        yield
    finally:
        _author_ctx.reset(token)


@contextmanager
def OverrideContext(branch: Optional[str] = None, author: Optional[str] = None):
    """Temporarily override multiple context values."""
    tokens = []
    
    if branch is not None:
        tokens.append(("branch", _branch_ctx.set(branch)))
    if author is not None:
        tokens.append(("author", _author_ctx.set(author)))
    
    try:
        yield
    finally:
        for ctx_name, token in tokens:
            if ctx_name == "branch":
                _branch_ctx.reset(token)
            elif ctx_name == "author":
                _author_ctx.reset(token)