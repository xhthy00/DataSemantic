"""One bounded subprocess per plan: SDK/native work can be killed on timeout."""

import contextlib
import json
import sys


def ensure_read_query(sql: str, dialect: str) -> None:
    import sqlglot
    from sqlglot import exp

    try:
        statements = [
            statement for statement in sqlglot.parse(sql, read=dialect) if statement is not None
        ]
    except sqlglot.errors.ParseError as exc:
        raise ValueError("Query could not be parsed") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise ValueError("Exactly one read-only query is required")
    blocked = (exp.DML, exp.DDL, exp.Command, exp.Into, exp.Lock)
    if any(isinstance(node, blocked) for node in statements[0].walk()):
        raise ValueError("Mutating or locking queries are not permitted")


def run(job: dict) -> dict:
    from wren import DataSource, WrenEngine, WrenError
    from wren.config import WrenConfig

    try:
        with WrenEngine(
            manifest_str=job["manifest"],
            data_source=DataSource(job["dialect"]),
            connection_info={},
            fallback=False,
            config=WrenConfig(
                strict_mode=True,
                denied_functions=frozenset(
                    {"pg_read_file", "pg_read_binary_file", "dblink", "lo_import", "pg_sleep"}
                ),
            ),
        ) as engine:
            if job["operation"] == "validate":
                for name in job["names"]:
                    escaped = name.replace('"', '""')
                    # Startup probes actually exercise native MDL planning, without a DB.
                    sql = f'SELECT * FROM "{escaped}" LIMIT 0'
                    ensure_read_query(engine.dry_plan(sql), job["dialect"])
                return {"ok": True}
            sql = job["sql"]
            ensure_read_query(sql, job["dialect"])
            physical_sql = engine.dry_plan(sql)
            ensure_read_query(physical_sql, job["dialect"])
            return {"ok": True, "physical_sql": physical_sql}
    except WrenError as exc:
        return {
            "ok": False,
            "code": "PLANNING_FAILED",
            "message": (
                exc.message[:1500]
                if job.get("diagnostics")
                else "Query could not be planned against the published model"
            ),
            "sdk_code": exc.error_code.name,
        }
    except ValueError:
        return {
            "ok": False,
            "code": "INVALID_SQL",
            "message": "Expected one parseable, read-only query",
        }


def main() -> None:
    try:
        job = json.load(sys.stdin)
        # Keep SDK diagnostics off the JSON protocol channel.
        with contextlib.redirect_stdout(sys.stderr):
            result = run(job)
    except Exception:
        result = {"ok": False, "code": "WORKER_FAILED", "message": "Planning worker failed"}
    json.dump(result, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
