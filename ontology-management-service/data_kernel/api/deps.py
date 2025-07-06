from typing import Optional
from dataclasses import dataclass
from fastapi import Request, Depends, Header

from data_kernel.service.terminus_service import get_service, TerminusService


@dataclass
class CommitMeta:
    """Metadata for TerminusDB commits."""
    author: str
    trace_id: Optional[str]
    commit_msg: str


async def get_commit_meta(
    request: Request,
    x_commit_msg: Optional[str] = Header(None, alias="X-Commit-Msg"),
    traceparent: Optional[str] = Header(None)
) -> CommitMeta:
    """Extract commit metadata from request context."""
    # Get user from request state (set by auth middleware)
    user = getattr(request.state, "user", None)
    if user:
        user_id = f"{user.username}@{user.tenant_id or 'default'}"
    else:
        user_id = "anonymous"
    
    # Use custom commit message if provided, otherwise default
    commit_msg = x_commit_msg or "OMS-Gateway write"
    
    return CommitMeta(
        author=user_id,
        trace_id=traceparent,
        commit_msg=commit_msg
    )


async def get_terminus_service() -> TerminusService:
    """Dependency to get the TerminusService singleton."""
    return await get_service()