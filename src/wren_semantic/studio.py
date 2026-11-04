"""Same-origin admin console. Separate cookie auth; never exposes the service token."""

import asyncio
import base64
import io
import json
import secrets
import time
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from .automodel import build_manifest, parse_ddl
from .database_scan import (
    DatabaseConnection,
    DatabaseScan,
    DatabaseScanner,
    DatabaseScope,
    ScanSnapshots,
)
from .errors import ServiceError
from .modeling import (
    authoring_bundle,
    copy_manifest,
    manifest_bytes,
    structural_issues,
    template_manifest,
)
from .registry import BundleEntry, Dialect, bundle_from_bytes
from .studio_store import StudioStore

COOKIE = "wren_studio_session"
ASSETS = Path(__file__).parent / "static"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    password: SecretStr


class DraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    dialect: Dialect = "postgres"
    manifest: dict


class DraftSave(DraftCreate):
    revision: int = Field(ge=1)


class DraftAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


class DraftMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    dialect: Dialect
    revision: int = Field(ge=1)


class DraftPlan(DraftAction):
    semantic_sql: str = Field(min_length=1, max_length=50_000)


class DraftPublish(DraftAction):
    bundle_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


class AutoModelSource(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    ddl: str = Field(min_length=1, max_length=500_000)
    dialect: Dialect = "postgres"


class AutoModelTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table_id: str = Field(min_length=1, max_length=20)
    columns: list[str] = Field(min_length=1, max_length=500)
    types: dict[str, str] = Field(default_factory=dict, max_length=500)


class AutoModelGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    ddl: str | None = Field(default=None, min_length=1, max_length=500_000)
    scan_id: str | None = Field(default=None, min_length=1, max_length=100)
    dialect: Dialect = "postgres"
    name: str = Field(min_length=1, max_length=100)
    catalog: str = Field(default="wren", min_length=1, max_length=100)
    semantic_schema: str = Field(default="public", alias="schema", min_length=1, max_length=100)
    tables: list[AutoModelTable] = Field(min_length=1, max_length=50)
    relationships: bool = True

    @model_validator(mode="after")
    def one_source(self):
        if (self.ddl is None) == (self.scan_id is None):
            raise ValueError("请提供 DDL 或当前会话的扫描结果，不能同时提供。")
        return self


def restore_releases(store: StudioStore, registry):
    for release in store.releases():
        entry = BundleEntry(
            bundle_id=release["bundle_id"],
            dialect=release["dialect"],
            manifest_path=f"{release['bundle_id']}/mdl.json",
            manifest_hash=release["manifest_hash"],
        )
        registry.register(bundle_from_bytes(entry, release["manifest"].encode()))


def mount_studio(app: FastAPI, settings) -> None:
    attempts = {}
    publication_lock = asyncio.Lock()
    snapshots = ScanSnapshots()
    app.state.database_scanner = DatabaseScanner(2)

    def store() -> StudioStore:
        return app.state.studio_store

    def same_origin(request: Request):
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.url.netloc}"
        if (origin and origin != expected) or request.headers.get("sec-fetch-site") == "cross-site":
            raise ServiceError("ORIGIN_DENIED", "管理操作必须来自同源页面。", 403)

    def session(request: Request):
        value = store().session(request.cookies.get(COOKIE, ""))
        if value is None:
            raise ServiceError("STUDIO_LOGIN_REQUIRED", "请先登录 MDL Studio。", 401)
        if request.method not in {"GET", "HEAD"}:
            same_origin(request)
            if not secrets.compare_digest(request.headers.get("x-studio-csrf", ""), value["csrf"]):
                raise ServiceError("CSRF_DENIED", "管理会话已失效，请刷新页面。", 403)
        return value

    @app.get("/", include_in_schema=False)
    async def home():
        return RedirectResponse("/studio/")

    @app.get("/studio", include_in_schema=False)
    async def studio_redirect():
        return RedirectResponse("/studio/")

    @app.get("/studio/", include_in_schema=False)
    async def studio_page(request: Request):
        html = (
            (ASSETS / "index.html")
            .read_text()
            .replace("__STUDIO_NONCE__", request.state.studio_nonce)
        )
        return HTMLResponse(html)

    app.mount("/studio/assets", StaticFiles(directory=ASSETS), name="studio-assets")
    public = APIRouter(prefix="/studio/api", include_in_schema=False)

    @public.post("/login")
    async def login(body: LoginRequest, request: Request, response: Response):
        same_origin(request)
        current = time.monotonic()
        address = request.client.host if request.client else "local"
        if len(attempts) > 1024:
            attempts.clear()
        count, until = attempts.get(address, (0, current + 60))
        if until <= current:
            count, until = 0, current + 60
        if count >= 5:
            raise ServiceError("LOGIN_THROTTLED", "尝试次数过多，请一分钟后再试。", 429)
        if not secrets.compare_digest(
            body.password.get_secret_value().encode(),
            settings.studio_password.get_secret_value().encode(),
        ):
            attempts[address] = (count + 1, until)
            raise ServiceError("INVALID_PASSWORD", "管理密码不正确。", 401)
        attempts.pop(address, None)
        token, csrf = store().new_session()
        response.set_cookie(
            COOKIE,
            token,
            httponly=True,
            secure=settings.studio_cookie_secure,
            samesite="strict",
            path="/studio",
            max_age=8 * 3600,
        )
        return {"authenticated": True, "csrf": csrf}

    app.include_router(public)
    router = APIRouter(
        prefix="/studio/api", dependencies=[Depends(session)], include_in_schema=False
    )

    @router.get("/session")
    async def read_session(request: Request):
        return {"authenticated": True, "csrf": session(request)["csrf"]}

    @router.post("/logout")
    async def logout(request: Request, response: Response):
        snapshots.discard(session(request)["csrf"])
        store().logout(request.cookies.get(COOKIE, ""))
        response.delete_cookie(COOKIE, path="/studio")
        return {"ok": True}

    @router.get("/templates")
    async def templates():
        registry = app.state.registry
        demo = registry.bundles.get("education-demo-v1")
        values = [
            {
                "id": "blank",
                "name": "空白模型",
                "manifest": {
                    "catalog": "wren",
                    "schema": "public",
                    "models": [],
                    "relationships": [],
                    "views": [],
                },
            }
        ]
        if demo:
            values.insert(
                0,
                {
                    "id": "education",
                    "name": "学情分析示例",
                    "manifest": template_manifest(copy_manifest(demo)),
                },
            )
        return {"templates": values}

    @router.get("/drafts")
    async def drafts(deleted: bool = False):
        return {"drafts": store().list_drafts(deleted=deleted)}

    def check_size(manifest):
        if len(manifest_bytes(manifest)) > min(
            settings.studio_max_request_bytes, settings.max_manifest_bytes
        ):
            raise ServiceError("MANIFEST_TOO_LARGE", "模型超过当前大小上限。", 413)

    @router.post("/drafts", status_code=201)
    async def create(body: DraftCreate):
        check_size(body.manifest)
        return store().create_draft(body.name, body.dialect, body.manifest)

    @router.get("/drafts/{draft_id}")
    async def read_draft(draft_id: str):
        return store().get_draft(draft_id)

    @router.put("/drafts/{draft_id}")
    async def save(draft_id: str, body: DraftSave):
        check_size(body.manifest)
        return store().save_draft(draft_id, body.name, body.dialect, body.manifest, body.revision)

    @router.patch("/drafts/{draft_id}")
    async def metadata(draft_id: str, body: DraftMetadata):
        return store().update_metadata(draft_id, body.name, body.dialect, body.revision)

    @router.delete("/drafts/{draft_id}")
    async def delete_draft(draft_id: str, body: DraftAction):
        return store().delete_draft(draft_id, body.revision)

    @router.post("/drafts/{draft_id}/restore")
    async def restore_draft(draft_id: str, body: DraftAction):
        return store().restore_draft(draft_id, body.revision)

    def checked_draft(draft_id, revision):
        draft = store().get_draft(draft_id)
        if draft["revision"] != revision:
            raise ServiceError("DRAFT_CONFLICT", "草稿版本已变化，请重新加载。", 409)
        return draft

    async def check_with_sdk(draft):
        issues = structural_issues(draft["manifest"])
        if issues:
            return {"valid": False, "issues": issues}
        bundle = authoring_bundle(draft["manifest"], draft["dialect"])
        try:
            _, duration = await app.state.planner.run(
                bundle, None, settings.startup_timeout_seconds, diagnostics=True
            )
        except ServiceError as exc:
            if exc.status != 422:
                raise
            return {
                "valid": False,
                "issues": [{"path": "Wren SDK", "message": exc.message}],
                "sdk_code": exc.sdk_code,
            }
        return {
            "valid": True,
            "issues": [],
            "manifest_hash": bundle.entry.manifest_hash,
            "checked_models": list(bundle.queryable_names),
            "duration_ms": duration,
        }

    @router.post("/automodel/preview")
    def automodel_preview(body: AutoModelSource):
        return parse_ddl(body.ddl, body.dialect)

    @router.post("/automodel/database/test")
    async def database_test(body: DatabaseConnection):
        return await app.state.database_scanner.inspect("test", body)

    @router.post("/automodel/database/tables")
    async def database_tables(body: DatabaseScope):
        return await app.state.database_scanner.inspect("tables", body)

    @router.post("/automodel/database/scan")
    async def database_scan(body: DatabaseScan, identity: Annotated[dict, Depends(session)]):
        preview = await app.state.database_scanner.inspect("scan", body)
        check_size(preview)
        scan_id = snapshots.put(identity["csrf"], body.dialect, preview)
        return {**preview, "scan_id": scan_id, "expires_in_seconds": snapshots.ttl}

    def source_preview(body, identity):
        if body.scan_id:
            return snapshots.get(body.scan_id, identity["csrf"], body.dialect)
        return parse_ddl(body.ddl, body.dialect)

    @router.post("/automodel/review")
    def automodel_review(body: AutoModelGenerate, identity: Annotated[dict, Depends(session)]):
        preview = source_preview(body, identity)
        manifest, warnings = build_manifest(
            preview, body.tables, body.catalog, body.semantic_schema, body.relationships
        )
        check_size(manifest)
        return {"manifest": manifest, "warnings": warnings}

    @router.post("/automodel/generate", status_code=201)
    async def automodel_generate(
        body: AutoModelGenerate, identity: Annotated[dict, Depends(session)]
    ):
        preview = await asyncio.to_thread(source_preview, body, identity)
        manifest, warnings = build_manifest(
            preview, body.tables, body.catalog, body.semantic_schema, body.relationships
        )
        check_size(manifest)
        checked = await check_with_sdk({"manifest": manifest, "dialect": body.dialect})
        if not checked["valid"]:
            error = ServiceError("INVALID_MDL", "自动建模未通过 Wren 校验，请调整字段类型。", 422)
            error.issues = checked["issues"]
            raise error
        draft = store().create_draft(body.name, body.dialect, manifest)
        return {"draft": draft, "warnings": warnings, "validation": checked}

    @router.post("/drafts/{draft_id}/validate")
    async def validate(draft_id: str, body: DraftAction):
        return await check_with_sdk(checked_draft(draft_id, body.revision))

    @router.post("/drafts/{draft_id}/plan")
    async def plan_draft(draft_id: str, body: DraftPlan):
        draft = checked_draft(draft_id, body.revision)
        bundle = authoring_bundle(draft["manifest"], draft["dialect"])
        result, duration = await app.state.planner.run(
            bundle, body.semantic_sql, settings.plan_timeout_seconds, diagnostics=True
        )
        return {
            "physical_sql": result["physical_sql"],
            "duration_ms": duration,
            "manifest_hash": bundle.entry.manifest_hash,
        }

    @router.post("/drafts/{draft_id}/publish", status_code=201)
    async def publish(draft_id: str, body: DraftPublish):
        draft = checked_draft(draft_id, body.revision)
        checked = await check_with_sdk(draft)
        if not checked["valid"]:
            error = ServiceError("INVALID_MDL", "校验未通过，无法发布。", 422)
            error.issues = checked["issues"]
            raise error
        bundle = authoring_bundle(draft["manifest"], draft["dialect"], body.bundle_id)
        async with publication_lock:
            if bundle.entry.bundle_id in app.state.registry.bundles:
                raise ServiceError("BUNDLE_EXISTS", "版本 ID 已存在，请使用新的版本 ID。", 409)
            store().publish(draft, bundle)
            app.state.registry.register(bundle)
        return {**bundle.summary(), "draft_id": draft_id, "revision": draft["revision"]}

    @router.get("/bundles")
    async def bundles():
        release_info = {row["bundle_id"]: row for row in store().releases()}
        return {
            "bundles": [
                {
                    **bundle.summary(),
                    "models_count": len(bundle.queryable_names),
                    "created_at": release_info.get(bundle.entry.bundle_id, {}).get("created_at"),
                    "source": "studio" if bundle.entry.bundle_id in release_info else "registry",
                    "draft_id": release_info.get(bundle.entry.bundle_id, {}).get("draft_id"),
                    "revision": release_info.get(bundle.entry.bundle_id, {}).get("revision"),
                }
                for bundle in app.state.registry.bundles.values()
            ]
        }

    @router.get("/bundles/{bundle_id}/manifest")
    async def read_manifest(bundle_id: str):
        return copy_manifest(app.state.registry.get(bundle_id))

    @router.get("/bundles/{bundle_id}/download")
    async def download(bundle_id: str):
        bundle = app.state.registry.get(bundle_id)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{bundle_id}/mdl.json", base64.b64decode(bundle.encoded_manifest))
            archive.writestr(
                "registry.json", json.dumps({"bundles": [bundle.entry.model_dump()]}, indent=2)
            )
        return Response(
            output.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{bundle_id}.zip"'},
        )

    app.include_router(router)
