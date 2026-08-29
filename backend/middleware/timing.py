import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import logging

logger = logging.getLogger("uvicorn")

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = None
        try:
            response = await call_next(request)
        finally:
            process_time = time.time() - start_time

            # Log the processing time
            status_code = response.status_code if response is not None else 500
            logger.info(
                f"Request: {request.method} {request.url.path} "
                f"- Status: {status_code} - Duration: {process_time:.4f}s"
            )

            # Feed the Prometheus /metrics collector (best-effort; never break a
            # response over a metrics hiccup).
            try:
                import metrics
                metrics.record_request(request.method, status_code, process_time)
            except Exception:
                pass

        # Add custom header
        response.headers["X-Process-Time"] = str(process_time)
        return response