"""
TerminusDB Context Middleware - Automatically sets branch, author, and trace context
"""
import os
import logging
from typing import Callable

from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace

from shared.terminus_context import (
    set_author, set_branch, set_trace_id, set_request_context,
    format_author, get_default_branch
)

logger = logging.getLogger(__name__)


class TerminusContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts and sets TerminusDB context from requests.
    Must be placed AFTER AuthMiddleware in the chain.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            # 1) Set trace ID from OpenTelemetry
            trace_id = ""
            span = trace.get_current_span()
            if span and span.is_recording():
                span_ctx = span.get_span_context()
                trace_id = format(span_ctx.trace_id, '032x')
                set_trace_id(trace_id)
            else:
                set_trace_id("")
            
            # 2) Set author from authenticated user
            user = getattr(request.state, "user", None)
            if user:
                # User context from auth middleware
                author = format_author(
                    user.username or user.user_id,
                    os.getenv("SERVICE_NAME", "oms")
                )
            else:
                # Anonymous or system user
                author = format_author(
                    "anonymous",
                    os.getenv("SERVICE_NAME", "oms")
                )
            set_author(author)
            
            # 3) Set branch from header or default
            branch_header = request.headers.get("X-Branch")
            if branch_header:
                # Validate branch format. It should be in the format 'organization/database'.
                if "/" in branch_header and len(branch_header.split("/")) >= 2:
                    branch = branch_header
                else:
                    # If the header is present but invalid, reject the request.
                    # This prevents data from being accidentally written to the default branch.
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Invalid X-Branch header format: '{branch_header}'. "
                            "Expected format is 'organization/database'."
                        )
                    )
            else:
                # Use default branch for service
                branch = get_default_branch()
            set_branch(branch)
            
            # 4) Set request context for commit message building
            set_request_context(
                method=request.method,
                path=str(request.url.path)
            )
            
            # Log context for debugging
            logger.debug(
                f"TerminusDB context set: author={author}, branch={branch}, "
                f"trace_id={trace_id[:8] if trace_id else 'none'}"
            )
            
            # Process request
            response = await call_next(request)
            
            # Optionally add context to response headers for debugging
            if os.getenv("DEBUG_TERMINUS_CONTEXT", "false").lower() == "true":
                response.headers["X-Terminus-Author"] = author
                response.headers["X-Terminus-Branch"] = branch
                if trace_id:
                    response.headers["X-Terminus-Trace"] = trace_id[:8]
            
            return response

        except HTTPException:
            # Allow FastAPI to handle its own exceptions to return proper HTTP responses.
            raise
        except Exception as e:
            logger.error(f"Error in TerminusContextMiddleware: {e}", exc_info=True)
            # For other unexpected errors, the original logic was to proceed without context.
            # This is risky but we preserve it while allowing HTTPExceptions to pass.
            return await call_next(request)