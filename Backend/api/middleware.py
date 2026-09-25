import time
import uuid


class RequestObservabilityMiddleware:
    """Attach a correlation ID and server timing to every API response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.request_id = request_id
        started = time.perf_counter()
        response = self.get_response(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response["X-Request-ID"] = request_id
        response["Server-Timing"] = f"app;dur={duration_ms}"
        return response


class ApiSecurityHeadersMiddleware:
    """Add restrictive browser headers to JSON API responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            response["Content-Security-Policy"] = (
                "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
                "form-action 'none'"
            )
            response["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
            response["Cross-Origin-Resource-Policy"] = "same-site"
        return response
