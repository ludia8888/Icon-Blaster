"""
Global Error Handler Middleware
"""
import logging
import traceback
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

logger = logging.getLogger(__name__)

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Catches all unhandled exceptions and returns a standardized 500 error response.
    This acts as a last-resort safety net for the application.
    """
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as e:
            # Log the full traceback for debugging purposes
            tb = traceback.format_exc()
            logger.critical(
                f"Unhandled exception for request {request.method} {request.url.path}: {e}\n{tb}"
            )
            
            # Return a standardized, non-revealing error response to the client
            return JSONResponse(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "An internal server error occurred."},
            ) 