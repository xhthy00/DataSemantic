"""Bounded database metadata jobs and session-owned, credential-free snapshots."""

import asyncio
import ipaddress
import json
import re
import secrets
import sys
import time
from copy import deepcopy
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from .errors import ServiceError
from .planner import Planner


class DatabaseConnection(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    dialect: Literal["postgres", "mysql"] = "postgres"
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    user: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(max_length=1024)
    tls: Literal["disable", "require", "verify-full"] = "require"

    @field_validator("host")
    @classmethod
    def hostname_only(cls, value):
        value = value.strip()
        if ":" in value:
            try:
                return str(ipaddress.IPv6Address(value.strip("[]")))
            except ValueError:
                raise ValueError("IPv6 地址无效；主机和端口请分开填写。") from None
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError("主机请填写单个域名或 IP，不包含协议、端口、路径或连接参数。")
        return value

    @field_validator("database", "user")
    @classmethod
    def nonblank(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("数据库和用户名不能为空或包含空字符。")
        return value


class DatabaseScope(DatabaseConnection):
    physical_schema: str = Field(min_length=1, max_length=128)
    table_filter: str = Field(default="", max_length=100)


class DatabaseScan(DatabaseScope):
    tables: list[str] = Field(min_length=1, max_length=50)

    @field_validator("tables")
    @classmethod
    def unique_tables(cls, values):
        if len(set(values)) != len(values) or any(not v or len(v) > 128 for v in values):
            raise ValueError("请选择 1～50 张不同的表。")
        return values


class ScanSnapshots:
    def __init__(self, ttl=900, limit=32, per_session=4):
        self.ttl, self.limit, self.per_session = ttl, limit, per_session
        self.entries = {}
        self.lock = RLock()

    def prune(self):
        with self.lock:
            now = time.monotonic()
            self.entries = {key: value for key, value in self.entries.items() if value[0] > now}

    def put(self, owner, dialect, preview):
        with self.lock:
            self.prune()
            owned = [key for key, value in self.entries.items() if value[1] == owner]
            while len(owned) >= self.per_session:
                del self.entries[owned.pop(0)]
            while len(self.entries) >= self.limit:
                del self.entries[next(iter(self.entries))]
            key = secrets.token_urlsafe(24)
            self.entries[key] = (time.monotonic() + self.ttl, owner, dialect, deepcopy(preview))
            return key

    def get(self, key, owner, dialect):
        with self.lock:
            self.prune()
            value = self.entries.get(key)
            if not value or value[1] != owner or value[2] != dialect:
                raise ServiceError(
                    "SCAN_EXPIRED", "扫描结果已过期或不属于当前会话，请重新扫描。", 409
                )
            return deepcopy(value[3])

    def discard(self, owner):
        with self.lock:
            self.entries = {key: value for key, value in self.entries.items() if value[1] != owner}


class DatabaseScanner(Planner):
    async def inspect(self, operation, connection):
        if self.closed:
            raise ServiceError("SERVICE_STOPPING", "服务正在停止。", 503)
        try:
            self.slots.get_nowait()
        except asyncio.QueueEmpty:
            raise ServiceError("SCANNER_BUSY", "扫描任务正在运行，请稍后重试。", 503) from None
        process = None
        try:
            async with asyncio.timeout(30):
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "wren_semantic.scan_worker",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                self.processes.add(process)
                payload = connection.model_dump(mode="json")
                payload["password"] = connection.password.get_secret_value()
                stdout, _ = await process.communicate(
                    json.dumps(
                        {
                            "operation": operation,
                            "connection": payload,
                        }
                    ).encode()
                )
                del payload
            if process.returncode != 0:
                raise ServiceError(
                    "SCAN_FAILED", "扫描进程未能完成，请检查连接或减少选表数量。", 502
                )
            try:
                result = json.loads(stdout)
                if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                    raise ValueError
            except (ValueError, UnicodeError):
                raise ServiceError("SCAN_FAILED", "扫描进程返回了无效结果。", 502) from None
            if not result["ok"]:
                raise ServiceError(result["code"], result["message"], 422)
            return result["result"]
        except TimeoutError:
            raise ServiceError(
                "SCAN_TIMEOUT", "连接或扫描超过 30 秒，请检查网络或减少选表数量。", 504
            ) from None
        finally:
            if process is not None:
                await asyncio.shield(self._stop(process))
                self.processes.discard(process)
            self.slots.put_nowait(None)
