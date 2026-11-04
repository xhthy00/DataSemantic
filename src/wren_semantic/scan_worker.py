"""Short-lived, read-only metadata connections. Credentials travel only over stdin."""

import contextlib
import json
import math
import ssl
import sys

from .automodel import normalized_type, prepare_preview
from .errors import ServiceError

PG_TABLES = """
SELECT c.relname AS name, left(coalesce(obj_description(c.oid, 'pg_class'), ''), 2000)
       AS description
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname=%s AND c.relkind IN ('r','p')
  AND has_table_privilege(c.oid, 'SELECT') AND position(%s in c.relname)>0
ORDER BY c.relname LIMIT 1001
"""
PG_COLUMNS = """
SELECT c.relname AS table_name, a.attname AS name,
       pg_catalog.format_type(a.atttypid,a.atttypmod) AS raw_type,
       NOT a.attnotnull AS nullable,
       left(coalesce(col_description(c.oid,a.attnum),''),2000) AS description
FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname=%s AND c.relname=ANY(%s) AND c.relkind IN ('r','p')
  AND has_table_privilege(c.oid, 'SELECT') AND a.attnum>0 AND NOT a.attisdropped
ORDER BY c.relname,a.attnum LIMIT 25001
"""
PG_KEYS = """
SELECT c.relname AS table_name, con.conname AS constraint_name, con.contype AS kind,
 ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY AS k(num,ord)
       JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.num
       ORDER BY k.ord) AS columns,
 rn.nspname AS target_schema, rc.relname AS target_table,
 ARRAY(SELECT a.attname FROM unnest(con.confkey) WITH ORDINALITY AS k(num,ord)
       JOIN pg_catalog.pg_attribute a ON a.attrelid=rc.oid AND a.attnum=k.num
       ORDER BY k.ord) AS target_columns
FROM pg_catalog.pg_constraint con JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
LEFT JOIN pg_catalog.pg_class rc ON rc.oid=con.confrelid
LEFT JOIN pg_catalog.pg_namespace rn ON rn.oid=rc.relnamespace
WHERE n.nspname=%s AND c.relname=ANY(%s) AND con.contype IN ('p','u','f')
ORDER BY c.relname,con.conname LIMIT 25001
"""
MYSQL_TABLES = """
SELECT TABLE_NAME AS name, left(coalesce(TABLE_COMMENT,''),2000) AS description
FROM information_schema.TABLES
WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' AND LOCATE(%s,TABLE_NAME)>0
ORDER BY TABLE_NAME LIMIT 1001
"""


def fail(message):
    raise ServiceError("SCAN_METADATA_INVALID", message, 422)


def query(db, sql, params=()):
    with db.cursor() as cursor:
        cursor.execute(sql, params or None)
        return list(cursor.fetchall())


def connect(body, *, statement_timeout_ms=8000, application_name="DataSemantic schema scanner"):
    if body["dialect"] == "postgres":
        import psycopg
        from psycopg.rows import dict_row

        options = dict(
            host=body["host"],
            port=body["port"],
            dbname=body["database"],
            user=body["user"],
            password=body["password"],
            connect_timeout=5,
            sslmode=body["tls"],
            row_factory=dict_row,
            application_name=application_name,
            options="-c default_transaction_read_only=on "
            f"-c statement_timeout={statement_timeout_ms} "
            "-c lock_timeout=2000 -c idle_in_transaction_session_timeout=15000",
        )
        if body["tls"] == "verify-full":
            options["sslrootcert"] = "system"
        return psycopg.connect(**options)
    import pymysql

    tls_context = None
    if body["tls"] != "disable":
        tls_context = ssl.create_default_context()
        if body["tls"] == "require":
            tls_context.check_hostname = False
            tls_context.verify_mode = ssl.CERT_NONE
    db = pymysql.connect(
        host=body["host"],
        port=body["port"],
        database=body["database"],
        user=body["user"],
        password=body["password"].encode("utf-8"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        read_timeout=max(1, math.ceil(statement_timeout_ms / 1000)),
        write_timeout=5,
        local_infile=False,
        autocommit=False,
        ssl=tls_context,
        ssl_disabled=body["tls"] == "disable",
    )
    try:
        with db.cursor() as cursor:
            cursor.execute(f"SET SESSION MAX_EXECUTION_TIME={int(statement_timeout_ms)}")
            cursor.execute("START TRANSACTION READ ONLY")
    except Exception:
        db.close()
        raise
    return db


def list_tables(db, body):
    schema = body["physical_schema"]
    if body["dialect"] == "mysql" and schema != body["database"]:
        fail("MySQL 的物理 Schema 应与连接数据库相同。")
    return query(
        db,
        PG_TABLES if body["dialect"] == "postgres" else MYSQL_TABLES,
        (schema, body.get("table_filter", "")),
    )


def mysql_metadata(db, schema, names):
    placeholders = ",".join(["%s"] * len(names))
    columns = query(
        db,
        """
        SELECT TABLE_NAME AS table_name, COLUMN_NAME AS name, COLUMN_TYPE AS raw_type,
               IS_NULLABLE='YES' AS nullable,
               left(coalesce(COLUMN_COMMENT,''),2000) AS description
        FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s
        """
        + f" AND TABLE_NAME IN ({placeholders}) "
        "ORDER BY TABLE_NAME,ORDINAL_POSITION LIMIT 25001",
        (schema, *names),
    )
    keys = query(
        db,
        """
        SELECT k.TABLE_NAME AS table_name, k.CONSTRAINT_NAME AS constraint_name,
               t.CONSTRAINT_TYPE AS kind, k.COLUMN_NAME AS column_name,
               k.REFERENCED_TABLE_SCHEMA AS target_schema,
               k.REFERENCED_TABLE_NAME AS target_table,
               k.REFERENCED_COLUMN_NAME AS target_column
        FROM information_schema.KEY_COLUMN_USAGE k
        JOIN information_schema.TABLE_CONSTRAINTS t ON
             t.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND t.TABLE_NAME=k.TABLE_NAME
             AND t.CONSTRAINT_NAME=k.CONSTRAINT_NAME
        WHERE k.TABLE_SCHEMA=%s
        """
        + f" AND k.TABLE_NAME IN ({placeholders}) "
        "ORDER BY k.TABLE_NAME,k.CONSTRAINT_NAME,k.ORDINAL_POSITION LIMIT 25001",
        (schema, *names),
    )
    grouped = {}
    kinds = {"PRIMARY KEY": "p", "UNIQUE": "u", "FOREIGN KEY": "f"}
    for row in keys:
        key = row["table_name"], row["constraint_name"]
        if row["kind"] not in kinds:
            continue
        group = grouped.setdefault(
            key, {**row, "kind": kinds[row["kind"]], "columns": [], "target_columns": []}
        )
        group["columns"].append(row["column_name"])
        if row["target_column"]:
            group["target_columns"].append(row["target_column"])
    if len(keys) > 25000:
        fail("约束数量超过扫描上限，请减少选表数量。")
    return columns, list(grouped.values())


def metadata_preview(body, tables, columns, keys):
    """Normalize catalog records without interpolating physical identifiers into SQL."""
    names, schema = body["tables"], body["physical_schema"]
    if len(columns) > 25000 or len(keys) > 25000:
        fail("字段或约束数量超过扫描上限，请减少选表数量。")
    known = {t["name"]: t for t in tables}
    if set(names) - known.keys():
        fail("选中的表已变化、不可见或不在当前范围内，请重新读取表清单。")
    result = {}
    for index, name in enumerate(sorted(names)):
        result[name] = {
            "id": f"t{index + 1}",
            "key": ["", schema, name],
            "label": f"{schema}.{name}",
            "description": known[name]["description"],
            "columns": [],
            "primary_key": [],
            "unique_keys": [],
            "foreign_keys": [],
        }
    for col in columns:
        if col["table_name"] not in result:
            continue
        mapped, warning = normalized_type(col["raw_type"], body["dialect"])
        result[col["table_name"]]["columns"].append(
            {
                "id": col["name"],
                "name": col["name"],
                "raw_type": col["raw_type"],
                "type": mapped,
                "warning": warning,
                "nullable": bool(col["nullable"]),
                "description": col["description"] or "",
            }
        )
    for key in keys:
        table = result.get(key["table_name"])
        if table is None:
            continue
        if key["kind"] == "p":
            table["primary_key"] = key["columns"]
        elif key["kind"] == "u":
            table["unique_keys"].append(key["columns"])
        elif key["kind"] == "f":
            table["foreign_keys"].append(
                {
                    "columns": key["columns"],
                    "target": ["", key["target_schema"], key["target_table"]],
                    "target_columns": key["target_columns"],
                }
            )
    for table in result.values():
        if not 1 <= len(table["columns"]) <= 500:
            fail(f"{table['label']} 字段不可见或超过每表 500 个字段上限。")
    return prepare_preview(list(result.values()), [])


def inspect(job):
    body, operation = job["connection"], job["operation"]
    db = connect(body)
    try:
        if operation == "test":
            if body["dialect"] == "postgres":
                rows = query(
                    db,
                    """SELECT nspname AS name FROM pg_catalog.pg_namespace
                    WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'
                    AND has_schema_privilege(oid,'USAGE') ORDER BY nspname LIMIT 500""",
                )
                schemas = [r["name"] for r in rows]
            else:
                # MySQL scope deliberately stays inside the explicitly selected database.
                query(db, "SELECT 1 AS connected")
                schemas = [body["database"]]
            return {"connected": True, "schemas": schemas}
        tables = list_tables(db, body)
        if operation == "tables":
            return {"tables": tables[:1000], "truncated": len(tables) > 1000}
        if operation != "scan":
            fail("未知扫描操作。")
        names, schema = body["tables"], body["physical_schema"]
        # Fetch chosen table descriptions independently of listing pagination or its filter.
        if body["dialect"] == "postgres":
            tables = query(
                db,
                """SELECT c.relname AS name,
                left(coalesce(obj_description(c.oid,'pg_class'),''),2000) AS description
                FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=%s AND c.relname=ANY(%s) AND c.relkind IN ('r','p')
                AND has_table_privilege(c.oid,'SELECT')""",
                (schema, names),
            )
            columns = query(db, PG_COLUMNS, (schema, names))
            keys = query(db, PG_KEYS, (schema, names))
        else:
            placeholders = ",".join(["%s"] * len(names))
            tables = query(
                db,
                """SELECT TABLE_NAME AS name,
                left(coalesce(TABLE_COMMENT,''),2000) AS description
                FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'
                """
                + f" AND TABLE_NAME IN ({placeholders})",
                (schema, *names),
            )
            columns, keys = mysql_metadata(db, schema, names)
        return metadata_preview(body, tables, columns, keys)
    finally:
        with contextlib.suppress(Exception):
            db.rollback()
        db.close()


def error_result(exc):
    code = getattr(exc, "sqlstate", None)
    number = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
    # libpq startup failures may omit SQLSTATE. Classify locally; never echo driver text.
    message = str(exc).lower()
    if (
        code in {"28P01", "28000"}
        or number in {1045, 1698}
        or any(
            s in message
            for s in (
                "password authentication failed",
                "no password supplied",
                "no pg_hba.conf entry",
            )
        )
    ):
        return "DB_AUTH_FAILED", "数据库认证失败，请检查用户名、密码及账号允许连接的来源地址。"
    if code == "3D000" or number == 1049:
        return "DB_NOT_FOUND", "数据库不存在，请检查数据库名称。"
    if code == "42501" or number in {1044, 1142}:
        return "DB_PERMISSION_DENIED", "账号无法读取所选数据库的表结构，请检查只读访问权限。"
    if code == "57014" or number == 3024:
        return "SCAN_TIMEOUT", "元数据查询超时，请减少选表数量。"
    if isinstance(exc, ServiceError):
        return exc.code, exc.message
    return "DB_CONNECTION_FAILED", (
        "无法完成数据库连接或扫描。请检查主机、端口、TLS 与账号权限；"
        "Docker 访问宿主机数据库时请使用 host.docker.internal。"
    )


def main():
    try:
        job = json.load(sys.stdin)
        with contextlib.redirect_stdout(sys.stderr):
            result = inspect(job)
        output = {"ok": True, "result": result}
        if len(json.dumps(output).encode()) > 1_048_576:
            fail("扫描结果超过 1 MB，请减少选表数量。")
    except Exception as exc:
        code, message = error_result(exc)
        output = {"ok": False, "code": code, "message": message}
    json.dump(output, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
