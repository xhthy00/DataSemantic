import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .errors import ServiceError
from .modeling import manifest_bytes


def now() -> str:
    return datetime.now(UTC).isoformat()


class StudioStore:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "studio.db"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, dialect TEXT NOT NULL,
                    manifest TEXT NOT NULL, revision INTEGER NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS releases (
                    bundle_id TEXT PRIMARY KEY, dialect TEXT NOT NULL, manifest TEXT NOT NULL,
                    manifest_hash TEXT NOT NULL, draft_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL
                );
            """)
            db.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in db.execute("PRAGMA table_info(drafts)")}
            if "deleted_at" not in columns:
                db.execute("ALTER TABLE drafts ADD COLUMN deleted_at TEXT")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def draft(row):
        if row is None:
            raise ServiceError("DRAFT_NOT_FOUND", "草稿不存在。", 404)
        item = dict(row)
        item["manifest"] = json.loads(item["manifest"])
        return item

    def list_drafts(self, deleted=False):
        clause = "IS NOT NULL" if deleted else "IS NULL"
        with self.connect() as db:
            return [
                self.draft(row)
                for row in db.execute(
                    f"SELECT * FROM drafts WHERE deleted_at {clause} ORDER BY updated_at DESC"
                )
            ]

    def get_draft(self, draft_id):
        with self.connect() as db:
            return self.draft(
                db.execute(
                    "SELECT * FROM drafts WHERE id=? AND deleted_at IS NULL", (draft_id,)
                ).fetchone()
            )

    def create_draft(self, name, dialect, manifest):
        draft_id = uuid4().hex
        with self.connect() as db:
            db.execute(
                "INSERT INTO drafts(id,name,dialect,manifest,revision,updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (draft_id, name, dialect, json.dumps(manifest, ensure_ascii=False), 1, now()),
            )
        return self.get_draft(draft_id)

    def save_draft(self, draft_id, name, dialect, manifest, revision):
        with self.connect() as db:
            result = db.execute(
                "UPDATE drafts SET name=?,dialect=?,manifest=?,revision=revision+1,updated_at=? "
                "WHERE id=? AND revision=? AND deleted_at IS NULL",
                (
                    name,
                    dialect,
                    json.dumps(manifest, ensure_ascii=False),
                    now(),
                    draft_id,
                    revision,
                ),
            )
            if result.rowcount != 1:
                self.mutation_conflict(db, draft_id)
        return self.get_draft(draft_id)

    @staticmethod
    def mutation_conflict(db, draft_id, deleted=False):
        row = db.execute("SELECT deleted_at FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if row is None or (row["deleted_at"] is not None) != deleted:
            raise ServiceError("DRAFT_NOT_FOUND", "草稿不存在或已移入回收站。", 404)
        raise ServiceError("DRAFT_CONFLICT", "草稿已在其他页面更新，请刷新后重试。", 409)

    def update_metadata(self, draft_id, name, dialect, revision):
        with self.connect() as db:
            result = db.execute(
                "UPDATE drafts SET name=?,dialect=?,revision=revision+1,updated_at=? "
                "WHERE id=? AND revision=? AND deleted_at IS NULL",
                (name, dialect, now(), draft_id, revision),
            )
            if result.rowcount != 1:
                self.mutation_conflict(db, draft_id)
        return self.get_draft(draft_id)

    def delete_draft(self, draft_id, revision):
        timestamp = now()
        with self.connect() as db:
            result = db.execute(
                "UPDATE drafts SET deleted_at=?,updated_at=?,revision=revision+1 "
                "WHERE id=? AND revision=? AND deleted_at IS NULL",
                (timestamp, timestamp, draft_id, revision),
            )
            if result.rowcount != 1:
                self.mutation_conflict(db, draft_id)
        return {"id": draft_id, "revision": revision + 1, "deleted_at": timestamp}

    def restore_draft(self, draft_id, revision):
        with self.connect() as db:
            result = db.execute(
                "UPDATE drafts SET deleted_at=NULL,updated_at=?,revision=revision+1 "
                "WHERE id=? AND revision=? AND deleted_at IS NOT NULL",
                (now(), draft_id, revision),
            )
            if result.rowcount != 1:
                self.mutation_conflict(db, draft_id, deleted=True)
        return self.get_draft(draft_id)

    def releases(self):
        with self.connect() as db:
            return [
                dict(row) for row in db.execute("SELECT * FROM releases ORDER BY created_at DESC")
            ]

    def publish(self, draft, bundle):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT * FROM drafts WHERE id=?", (draft["id"],)).fetchone()
            if (
                current is None
                or current["deleted_at"] is not None
                or current["revision"] != draft["revision"]
            ):
                raise ServiceError("DRAFT_CONFLICT", "校验期间草稿已更新，请重新校验发布。", 409)
            try:
                db.execute(
                    "INSERT INTO releases VALUES (?,?,?,?,?,?,?)",
                    (
                        bundle.entry.bundle_id,
                        bundle.entry.dialect,
                        manifest_bytes(draft["manifest"]).decode(),
                        bundle.entry.manifest_hash,
                        draft["id"],
                        draft["revision"],
                        now(),
                    ),
                )
            except sqlite3.IntegrityError:
                raise ServiceError("BUNDLE_EXISTS", "版本 ID 已存在，请使用新版本。", 409) from None

    def new_session(self):
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    csrf,
                    time.time() + 8 * 3600,
                ),
            )
        return token, csrf

    def session(self, token):
        with self.connect() as db:
            row = db.execute(
                "SELECT csrf,expires FROM sessions WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
        return dict(row) if row and row["expires"] > time.time() else None

    def logout(self, token):
        with self.connect() as db:
            db.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            )
