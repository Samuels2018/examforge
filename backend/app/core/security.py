import hashlib
import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.services.audit import AuditService
from app.services.rate_limit import SlidingWindowRateLimiter

logger = logging.getLogger(__name__)

_AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _client_key(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        digest = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()[:32]
        return f"token:{digest}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


def install_rate_limit(app: FastAPI, settings: Settings) -> None:
    if not settings.rate_limit_enabled:
        return

    limiter = SlidingWindowRateLimiter(
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    app.state.rate_limiter = limiter
    exempt = {path.rstrip("/") or "/" for path in settings.rate_limit_exempt_paths}

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        path = request.url.path
        normalized = path.rstrip("/") or "/"
        if not path.startswith("/api") or normalized in exempt:
            return await call_next(request)
        allowed, retry_after = limiter.allow(_client_key(request))
        if not allowed:
            logger.warning("rate_limit path=%s key=%s", path, _client_key(request))
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Demasiadas peticiones. Espera un momento e inténtalo de nuevo.",
                        "details": {"retry_after_seconds": retry_after},
                    }
                },
            )
        return await call_next(request)


def install_audit_middleware(app: FastAPI, settings: Settings) -> None:
    if not settings.audit_enabled:
        return

    audit = AuditService(app.state.session_factory, max_events=settings.audit_max_events)
    app.state.audit = audit

    @app.middleware("http")
    async def audit_middleware(request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api") or request.method.upper() not in _AUDITED_METHODS:
            return await call_next(request)

        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            client_ip = request.client.host if request.client else None
            await run_in_threadpool(
                audit.record,
                user_id=getattr(request.state, "user_id", None),
                method=request.method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                request_id=getattr(request.state, "request_id", None),
            )
