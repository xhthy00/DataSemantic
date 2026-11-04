import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .errors import ServiceError
from .execution import ExecuteRequest, ExecuteResponse, ExecutionSources, SQLExecutor
from .planner import Planner
from .registry import Registry

logger = logging.getLogger("uvicorn.error")


def error_response(code: str, message: str, status: int, request_id: str, **extra):
    headers = {}
    if status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    if status == 503:
        headers["Retry-After"] = "1"
    return JSONResponse(
        {"error": {"code": code, "message": message, **extra}, "request_id": request_id},
        status_code=status,
        headers=headers,
    )


class RequestBoundaryMiddleware:
    def __init__(self, app, max_body_bytes: int, studio_max_bytes: int = 1_048_576):
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.studio_max_bytes = studio_max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        supplied_id = headers.get(b"x-request-id", b"").decode("ascii", "ignore")
        request_id = supplied_id if re.fullmatch(r"[\w.-]{1,100}", supplied_id) else uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.monotonic()
        status = 500
        is_studio = scope["path"].startswith("/studio")
        body_limit = self.studio_max_bytes if is_studio else self.max_body_bytes
        studio_nonce = secrets.token_urlsafe(24) if is_studio else ""
        scope["state"]["studio_nonce"] = studio_nonce

        async def send_response(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
                if is_studio:
                    message["headers"].extend(
                        [
                            (b"cache-control", b"no-store"),
                            (b"x-content-type-options", b"nosniff"),
                            (b"referrer-policy", b"same-origin"),
                            (
                                b"content-security-policy",
                                (
                                    b"default-src 'self'; script-src 'self'; "
                                    + f"style-src 'self' 'nonce-{studio_nonce}'; ".encode()
                                    + b"img-src 'self' data:; connect-src 'self'; "
                                    b"frame-ancestors 'none'; "
                                    b"base-uri 'none'; form-action 'self'"
                                ),
                            ),
                        ]
                    )
            await send(message)

        try:
            # Bound chunked bodies too; Content-Length alone is not a size boundary.
            body = bytearray()
            while True:
                chunk = await receive()
                if chunk["type"] == "http.disconnect":
                    return
                body.extend(chunk.get("body", b""))
                if len(body) > body_limit:
                    response = error_response(
                        "REQUEST_TOO_LARGE", "Request body is too large", 413, request_id
                    )
                    return await response(scope, receive, send_response)
                if not chunk.get("more_body", False):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay, send_response)
        finally:
            # Never log Authorization, SQL text, request bodies, or physical object names.
            logger.info(
                "request_id=%s method=%s status=%s duration_ms=%s",
                request_id,
                scope["method"],
                status,
                round((time.monotonic() - started) * 1000),
            )


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    bundle_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    semantic_sql: str = Field(min_length=1, max_length=50_000)


class PlanResponse(BaseModel):
    request_id: str
    bundle_id: str
    manifest_hash: str
    dialect: str
    physical_sql: str
    duration_ms: int
    wrenai_version: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = False
        planner = Planner(settings.max_concurrent_plans)
        app.state.planner = planner
        executor = SQLExecutor(settings.max_concurrent_executions)
        app.state.executor = executor
        try:
            app.state.execution_sources = ExecutionSources(settings.execution_sources_path)
            registry = Registry(settings.registry_path, settings.max_manifest_bytes)
            if settings.studio_enabled:
                from .studio import restore_releases
                from .studio_store import StudioStore

                app.state.studio_store = StudioStore(settings.studio_data_dir)
                restore_releases(app.state.studio_store, registry)
            for bundle in registry.bundles.values():
                await planner.run(bundle, None, settings.startup_timeout_seconds)
            app.state.registry = registry
            app.state.ready = True
            logger.info(
                "Wren SDK ready: version=%s bundles=%s", version("wrenai"), len(registry.bundles)
            )
            yield
        finally:
            app.state.ready = False
            await planner.close()
            await executor.close()
            scanner = getattr(app.state, "database_scanner", None)
            if scanner is not None:
                await scanner.close()

    app = FastAPI(
        title="DataSemantic · Wren SDK Planning and Query API",
        version="0.1.0",
        description=(
            "Plans semantic SQL and optionally executes read-only physical SQL against "
            "server-configured sources. Studio can scan read-only database metadata."
        ),
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        RequestBoundaryMiddleware,
        max_body_bytes=settings.max_request_bytes,
        studio_max_bytes=settings.studio_max_request_bytes,
    )

    @app.exception_handler(ServiceError)
    async def handle_service_error(request: Request, exc: ServiceError):
        extra = {"sdk_code": exc.sdk_code} if exc.sdk_code else {}
        if getattr(exc, "issues", None):
            extra["issues"] = exc.issues
        return error_response(exc.code, exc.message, exc.status, request.state.request_id, **extra)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        # Pydantic's default input field can echo SQL or arbitrary submitted secrets.
        return error_response(
            "INVALID_REQUEST",
            "Request fields do not match the API contract",
            422,
            request.state.request_id,
            fields=[
                {"location": list(item["loc"]), "message": item["msg"]} for item in exc.errors()
            ],
        )

    bearer = HTTPBearer(auto_error=False)

    async def authorize(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
    ):
        supplied = credentials.credentials if credentials else ""
        expected = settings.service_token.get_secret_value()
        # Compare bytes so malformed non-ASCII headers fail closed, not with TypeError.
        if not secrets.compare_digest(supplied.encode(), expected.encode()):
            raise ServiceError("UNAUTHORIZED", "A valid service bearer token is required", 401)

    @app.get("/health/live", tags=["health"])
    async def live():
        return {"status": "ok"}

    @app.get("/health", tags=["health"])
    @app.get("/health/ready", tags=["health"])
    async def ready():
        if not getattr(app.state, "ready", False):
            raise ServiceError("NOT_READY", "Models are not ready", 503)
        return {"status": "ready", "wrenai_version": version("wrenai")}

    router = APIRouter(prefix="/internal/v1", dependencies=[Depends(authorize)])

    @router.get("/bundles", tags=["models"])
    async def list_bundles():
        return {"bundles": [bundle.summary() for bundle in app.state.registry.bundles.values()]}

    @router.get("/bundles/{bundle_id}/context", tags=["models"])
    async def context(bundle_id: str):
        bundle = app.state.registry.get(bundle_id)
        return {**bundle.summary(), **bundle.context}

    @router.post("/plan", response_model=PlanResponse, tags=["planning"])
    async def plan(body: PlanRequest, request: Request):
        bundle = app.state.registry.get(body.bundle_id)
        if body.manifest_hash != bundle.entry.manifest_hash:
            raise ServiceError("MODEL_VERSION_MISMATCH", "Published model hash does not match", 409)
        result, duration_ms = await app.state.planner.run(
            bundle, body.semantic_sql, settings.plan_timeout_seconds
        )
        return PlanResponse(
            request_id=request.state.request_id,
            **bundle.summary(),
            physical_sql=result["physical_sql"],
            duration_ms=duration_ms,
            wrenai_version=version("wrenai"),
        )

    @router.post("/execute", response_model=ExecuteResponse, tags=["execution"])
    async def execute(body: ExecuteRequest, request: Request):
        connection = app.state.execution_sources.get(body.source_id)
        result, duration_ms = await app.state.executor.execute(
            connection,
            body.physical_sql,
            body.max_rows,
            settings.execution_timeout_seconds,
            settings.execution_max_result_bytes,
        )
        return ExecuteResponse(
            request_id=request.state.request_id,
            source_id=body.source_id,
            dialect=connection.dialect,
            duration_ms=duration_ms,
            **result,
        )

    @router.get("/openapi.json", include_in_schema=False)
    async def openapi():
        return app.openapi()

    app.include_router(router)
    if settings.studio_enabled:
        from .studio import mount_studio

        mount_studio(app, settings)
    return app
