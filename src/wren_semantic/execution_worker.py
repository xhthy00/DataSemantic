"""Execute one validated physical query, with no credentials on argv or stderr."""

import base64
import contextlib
import datetime
import decimal
import json
import math
import sys
from uuid import UUID

from .errors import ServiceError
from .execution import validate_physical_sql
from .scan_worker import connect


def abandon_mysql_result(db, cursor):
    # SSCursor.close() normally drains the entire result, even after max_rows.
    # This connection is never reused, so discard its socket and pending result.
    db.close()
    if cursor._result is not None:
        cursor._result.unbuffered_active = False


def json_value(value):
    """Preserve exact decimals, large integers and duplicate column names."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return str(value) if abs(value) > 2**53 - 1 else value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (datetime.date, datetime.time, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, (decimal.Decimal, UUID, datetime.timedelta)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    raise ServiceError("RESULT_TYPE_UNSUPPORTED", "Query returned an unsupported data type", 422)


def execute(job):
    body = job["connection"]
    sql = validate_physical_sql(job["sql"], body["dialect"])
    milliseconds = max(1, int(job["timeout"] * 1000))
    db = connect(body, statement_timeout_ms=milliseconds, application_name="DataSemantic query")
    try:
        if body["dialect"] == "postgres":
            from psycopg.rows import tuple_row

            # Builtins resolve before any user-controlled schema. Physical table
            # references may still be explicitly schema-qualified by Wren.
            with db.cursor() as setup:
                setup.execute("SET LOCAL search_path TO pg_catalog, public")
            cursor = db.cursor(name="datasemantic_result", row_factory=tuple_row)
        else:
            from pymysql.cursors import SSCursor

            cursor = db.cursor(SSCursor)
        with contextlib.ExitStack() as stack:
            stack.enter_context(cursor)
            if body["dialect"] == "mysql":
                stack.callback(abandon_mysql_result, db, cursor)
            cursor.execute(sql)
            columns = [str(col[0]) for col in cursor.description or []]
            if not columns:
                raise ServiceError("INVALID_SQL", "Query must return a result set", 422)
            # Include the envelope overhead in the response budget; never fetchall.
            size = len(json.dumps({"columns": columns, "rows": []}).encode()) + 1024
            if size > job["max_bytes"]:
                raise ServiceError(
                    "RESULT_TOO_LARGE", "Result metadata exceeds the byte limit", 422
                )
            rows, truncated = [], False
            for _ in range(job["max_rows"] + 1):
                row = cursor.fetchone()
                if row is None:
                    break
                if len(rows) == job["max_rows"]:
                    truncated = True
                    break
                encoded = [json_value(value) for value in row]
                row_bytes = (
                    len(json.dumps(encoded, ensure_ascii=True, allow_nan=False).encode()) + 2
                )
                if size + row_bytes > job["max_bytes"]:
                    if not rows:
                        raise ServiceError(
                            "RESULT_TOO_LARGE", "One result row exceeds the byte limit", 422
                        )
                    truncated = True
                    break
                rows.append(encoded)
                size += row_bytes
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "truncated": truncated,
            }
    finally:
        with contextlib.suppress(Exception):
            db.rollback()
        with contextlib.suppress(Exception):
            db.close()


def error_result(exc):
    if isinstance(exc, ServiceError):
        return exc.code, exc.message, exc.status
    code = getattr(exc, "sqlstate", None)
    number = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
    if code == "57014" or number in {3024, 1317}:
        return "EXECUTION_TIMEOUT", "SQL execution deadline exceeded", 504
    if code in {"42501", "25006"} or number in {1044, 1142, 1792}:
        return "DB_PERMISSION_DENIED", "Database read permission denied", 403
    if code in {"28P01", "28000"} or number in {1045, 1698}:
        return "DB_AUTH_FAILED", "Execution source authentication failed", 502
    if code and code.startswith(("42", "22", "0A")) or number in {1054, 1064, 1146, 1305}:
        return "QUERY_FAILED", "Query could not be executed against this source", 422
    return "DB_EXECUTION_FAILED", "Database connection or query failed", 502


def main():
    try:
        job = json.load(sys.stdin)
        with contextlib.redirect_stdout(sys.stderr):
            result = execute(job)
        output = {"ok": True, "result": result}
    except Exception as exc:
        code, message, status = error_result(exc)
        output = {"ok": False, "code": code, "message": message, "status": status}
    json.dump(output, sys.stdout, ensure_ascii=True, allow_nan=False)


if __name__ == "__main__":
    main()
