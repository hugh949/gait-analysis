"""
Middleware for request logging and error tracking
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger
import uuid
import time
from typing import Callable


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID and structured logging"""
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        
        # Log request start
        start_time = time.time()
        logger.info(
            f"[{request_id}] {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": str(request.url.path),
                "client": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent")
            }
        )
        
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log response
            logger.info(
                f"[{request_id}] {request.method} {request.url.path} - {response.status_code}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": str(request.url.path),
                    "status_code": response.status_code,
                    "process_time": process_time
                }
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.3f}"
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"[{request_id}] {request.method} {request.url.path} - Exception after {process_time:.3f}s",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": str(request.url.path),
                    "error_type": type(e).__name__,
                    "process_time": process_time
                },
                exc_info=True
            )
            raise
