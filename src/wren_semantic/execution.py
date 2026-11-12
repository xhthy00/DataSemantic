"""Server-owned database profiles and bounded physical-query workers."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .database_scan import DatabaseConnection
from .errors import ServiceError
from .planner import Planner


class SourceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    dialect: Literal["postgres", "mysql"]
    host: str
    port: int
    database: str
    user: str
    password_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    tls: Literal["disable", "require", "verify-full"] = "require"


class SourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    sources: list[SourceProfile] = Field(min_length=1, max_length=100)


class ExecutionSources:
    def __init__(self, path: Path | None):
        self.connections: dict[str, DatabaseConnection] = {}
        if path is None:
            return
        try:
            if path.stat().st_size > 1_048_576:
                raise ValueError
            profiles = SourceFile.model_validate_json(path.read_bytes())
            for profile in profiles.sources:
                password = os.environ.get(profile.password_env)
                if not password or profile.source_id in self.connections:
                    raise ValueError
                self.connections[profile.source_id] = DatabaseConnection.model_validate(
                    {
                        **profile.model_dump(exclude={"source_id", "password_env"}),
                        "password": password,
                    }
                )
        except (OSError, ValueError):
            # Startup diagnostics must not echo profiles, environment values or passwords.
            raise ValueError(
                "Invalid execution sources configuration or missing password env"
            ) from None

    def get(self, source_id: str) -> DatabaseConnection:
        if not self.connections:
            raise ServiceError(
                "EXECUTION_DISABLED", "SQL execution sources are not configured", 503
            )
        if source_id not in self.connections:
            raise ServiceError("SOURCE_NOT_FOUND", "Execution source is not registered", 404)
        return self.connections[source_id]


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    physical_sql: str = Field(min_length=1, max_length=50_000)
    max_rows: int = Field(default=1000, ge=1, le=10_000, strict=True)


class ExecuteResponse(BaseModel):
    request_id: str
    source_id: str
    dialect: str
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    duration_ms: int


# Explicitly limited to analytics functions. Qualified functions, custom functions,
# session variables and executable comments never reach the database unchanged.
SAFE_FUNCTIONS = frozenset(
    "ABS AVG COUNT SUM MIN MAX ROUND FLOOR CEIL CEILING COALESCE NULLIF IF IFNULL "
    "CASE LOWER UPPER LENGTH CHAR_LENGTH CHARACTER_LENGTH CONCAT CONCAT_WS "
    "SUBSTRING SUBSTR TRIM LTRIM RTRIM REPLACE LEFT RIGHT CAST TRY_CAST "
    "EXTRACT DATE DATE_TRUNC TIMESTAMP_TRUNC DATE_ADD DATE_SUB DATE_DIFF DATEDIFF "
    "TIMESTAMP_ADD TIMESTAMP_SUB TIMESTAMP_DIFF TIME_TO_STR STR_TO_TIME STR_TO_DATE "
    "CURRENT_DATE CURRENT_TIMESTAMP CURRENT_TIME YEAR MONTH DAY DAY_OF_MONTH "
    "DAY_OF_WEEK DAY_OF_YEAR HOUR MINUTE SECOND NOW TO_CHAR TO_DATE TO_TIMESTAMP "
    "GREATEST LEAST POWER POW SQRT MOD ROW_NUMBER RANK DENSE_RANK LAG LEAD "
    "FIRST_VALUE LAST_VALUE NTH_VALUE NTILE PERCENT_RANK CUME_DIST "
    "STDDEV STDDEV_POP STDDEV_SAMP VARIANCE VAR_POP VAR_SAMP "
    "BOOL_AND BOOL_OR ARRAY_AGG STRING_AGG GROUP_CONCAT FILTER EXISTS".split()
)


def validate_physical_sql(sql: str, dialect: str) -> str:
    import sqlglot
    from sqlglot import exp

    from .worker import ensure_read_query

    try:
        ensure_read_query(sql, dialect)
        tree = sqlglot.parse_one(sql, read=dialect)
        blocked = (exp.Parameter, exp.SessionParameter, exp.PropertyEQ, exp.Hint)
        for node in tree.walk():
            if isinstance(node, blocked):
                raise ValueError
            if isinstance(node, exp.Dot) and isinstance(node.expression, exp.Func):
                raise ValueError
            if isinstance(node, exp.Func):
                name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
                if name.upper() not in SAFE_FUNCTIONS:
                    raise ValueError
        # Re-render without comments/hints: MySQL version comments can execute SQL
        # which an AST parser treats as comments. Never execute the original input.
        normalized = tree.sql(dialect=dialect, comments=False, unsupported_level="RAISE")
        ensure_read_query(normalized, dialect)
        return normalized
    except (ValueError, sqlglot.errors.SqlglotError):
        raise ServiceError(
            "INVALID_SQL", "Expected one read-only analytics query using supported functions", 422
        ) from None


class SQLExecutor(Planner):
    async def execute(self, connection, sql, max_rows, timeout, max_bytes):
        # Parsing and validation run in the bounded worker, before connecting.
        await self._acquire("EXECUTOR_BUSY", "All execution slots are occupied")
        process = None
        started = time.monotonic()
        try:
            async with asyncio.timeout(timeout):
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "wren_semantic.execution_worker",
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
                            "connection": payload,
                            "sql": sql,
                            "max_rows": max_rows,
                            "timeout": timeout,
                            "max_bytes": max_bytes,
                        }
                    ).encode()
                )
                del payload
            if process.returncode != 0:
                raise ServiceError("EXECUTION_FAILED", "Execution worker exited unexpectedly", 502)
            try:
                result = json.loads(stdout)
                if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                    raise ValueError
            except (ValueError, UnicodeError):
                raise ServiceError(
                    "EXECUTION_FAILED", "Invalid execution worker response", 502
                ) from None
            if not result["ok"]:
                raise ServiceError(result["code"], result["message"], result["status"])
            return result["result"], round((time.monotonic() - started) * 1000)
        except TimeoutError:
            raise ServiceError(
                "EXECUTION_TIMEOUT", "SQL execution deadline exceeded", 504
            ) from None
        finally:
            if process is not None:
                await asyncio.shield(self._stop(process))
                self.processes.discard(process)
            self.slots.put_nowait(None)
