from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException

from backend.api.audits import router as audit_router
from backend.api.auth import router
from backend.api.users import router as user_router
from backend.core.config import runtime_database_url
from backend.core.database import make_engine
from backend.core.errors import ServiceError
from backend.core.throttle import LoginLimiter


def error(status, code, message):
    headers = {"Cache-Control": "no-store"}
    if status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    if status == 429:
        headers["Retry-After"] = "60"
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}}, headers=headers)


def create_app(*, engine=None):
    """Injected engines are for trusted tests; deployment always uses runtime config."""
    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = engine if engine is not None else make_engine(runtime_database_url())
        try:
            yield
        finally:
            if engine is None:
                app.state.engine.dispose()

    app = FastAPI(title="DAMS API", version="0.2.0", lifespan=lifespan)
    app.state.login_limiter = LoginLimiter()

    @app.middleware("http")
    async def safe_errors(request: Request, call_next):
        # Catch unexpected errors before the ASGI server can log exception inputs.
        try:
            response = await call_next(request)
        except Exception:
            response = error(500, "internal_error", "Internal service error")
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return error(exc.status, exc.code, exc.message)

    @app.exception_handler(StaleDataError)
    async def stale_error(request, exc):
        return error(409, "conflict", "Audit changed concurrently")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return error(503, "service_unavailable", "Service temporarily unavailable")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI's default detail can echo password/body input.
        return error(422, "invalid_request", "Request validation failed")

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(exc.status_code, "http_error", "Request could not be completed")

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(audit_router)
    app.include_router(user_router)
    return app
