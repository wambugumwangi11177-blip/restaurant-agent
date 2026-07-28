import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import logging

logger = logging.getLogger("uvicorn")

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Log the processing time
        logger.info(f"Request: {request.method} {request.url.path} - Duration: {process_time:.4f}s")

        # Feed the Prometheus /metrics collector (best-effort; never break a
        # response over a metrics hiccup).
        try:
            import metrics
            metrics.record_request(request.method, response.status_code, process_time)
        except Exception as exc:
            from observability import degraded
            degraded("metrics.record_request", exc)

        # Add custom header
        response.headers["X-Process-Time"] = str(process_time)
        return response
