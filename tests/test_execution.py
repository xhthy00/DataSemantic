import asyncio
import datetime
import decimal
import json
import sys

import pytest

from wren_semantic.errors import ServiceError
from wren_semantic.execution import ExecutionSources, SQLExecutor, validate_physical_sql
from wren_semantic.execution_worker import error_result, json_value

PROFILE = {
    "source_id": "test",
    "dialect": "postgres",
    "host": "127.0.0.1",
    "port": 5432,
    "database": "test",
    "user": "reader",
    "password_env": "EXECUTE_UNIT_PASSWORD",
    "tls": "disable",
}


def test_sources_are_server_owned_and_errors_redacted(tmp_path, monkeypatch):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"sources": [PROFILE]}))
    monkeypatch.setenv("EXECUTE_UNIT_PASSWORD", "private-password")
    sources = ExecutionSources(path)
    assert sources.get("test").password.get_secret_value() == "private-password"
    with pytest.raises(ServiceError) as error:
        sources.get("missing")
    assert error.value.code == "SOURCE_NOT_FOUND"
    for profiles in [[PROFILE, PROFILE], [{**PROFILE, "password": "private-password"}]]:
        path.write_text(json.dumps({"sources": profiles}))
        with pytest.raises(ValueError) as error:
            ExecutionSources(path)
        assert "private-password" not in str(error.value)
    monkeypatch.delenv("EXECUTE_UNIT_PASSWORD")
    path.write_text(json.dumps({"sources": [PROFILE]}))
    with pytest.raises(ValueError):
        ExecutionSources(path)


@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM scores",
        "SELECT 1; SELECT 2",
        "SELECT * FROM scores FOR UPDATE",
        "WITH d AS (DELETE FROM scores RETURNING *) SELECT * FROM d",
        "SELECT pg_sleep(1)",
        "SELECT load_file('/etc/passwd')",
        "SELECT set_config('x','y',false)",
        "SELECT public.lower('x')",
        "SELECT @x := 1",
        "SELECT @@version",
        "SELECT * INTO stolen FROM scores",
    ],
)
def test_unsafe_sql_rejected(sql, dialect):
    with pytest.raises(ServiceError) as error:
        validate_physical_sql(sql, dialect)
    assert error.value.code == "INVALID_SQL"


@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
def test_analytics_ctes_and_comments(dialect):
    sql = """WITH s AS (SELECT school_id, COALESCE(score, 0) AS score FROM scores)
    SELECT school_id, ROUND(AVG(score), 2), COUNT(*) FROM s GROUP BY school_id"""
    assert "AVG" in validate_physical_sql(sql, dialect)
    assert "SLEEP" not in validate_physical_sql("SELECT 1 /*!50000 , SLEEP(100) */", dialect)
    assert "/*" not in validate_physical_sql("SELECT 1 /* private comment */", dialect)
    if dialect == "mysql":
        with pytest.raises(ServiceError):
            validate_physical_sql("SELECT /*+ MAX_EXECUTION_TIME(0) */ 1", dialect)
    assert "--" in validate_physical_sql("SELECT '--literal'", dialect)


def test_execution_api_auth_disabled_and_request_contract(client, auth):
    body = {"source_id": "test", "physical_sql": "SELECT 1"}
    assert client.post("/internal/v1/execute", json=body).status_code == 401
    response = client.post("/internal/v1/execute", headers=auth, json=body)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EXECUTION_DISABLED"
    for extra in [{"password": "private-input"}, {"max_rows": 10001}, {"max_rows": True}]:
        response = client.post("/internal/v1/execute", headers=auth, json={**body, **extra})
        assert response.status_code == 422 and "private-input" not in response.text
    schema = client.get("/internal/v1/openapi.json", headers=auth).json()
    assert "/internal/v1/execute" in schema["paths"]


def test_json_results_preserve_precision_and_types():
    assert json_value(decimal.Decimal("123.4500")) == "123.4500"
    assert json_value(2**63 - 1) == str(2**63 - 1)
    assert json_value(datetime.date(2026, 11, 3)) == "2026-11-03"
    assert json_value(b"hello") == "aGVsbG8="
    assert json_value(float("nan")) == "nan"
    assert json_value({"a": [decimal.Decimal("0.1"), None, False]}) == {"a": ["0.1", None, False]}
    assert "private-password" not in str(error_result(RuntimeError("private-password")))


def test_execution_timeout_busy_and_cancellation_reap_workers(tmp_path, monkeypatch):
    from wren_semantic.database_scan import DatabaseConnection

    connection = DatabaseConnection(
        **{k: v for k, v in PROFILE.items() if k not in {"source_id", "password_env"}},
        password="private-password",
    )

    async def scenario():
        original = asyncio.create_subprocess_exec
        started, children = asyncio.Event(), []

        async def sleeper(*args, **kwargs):
            child = await original(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
            children.append(child)
            started.set()
            return child

        monkeypatch.setattr(asyncio, "create_subprocess_exec", sleeper)
        executor = SQLExecutor(1)
        with pytest.raises(ServiceError) as error:
            await executor.execute(connection, "SELECT 1", 1, 0.2, 4096)
        assert error.value.code == "EXECUTION_TIMEOUT"
        assert children[0].returncode is not None and executor.slots.qsize() == 1
        started.clear()
        running = asyncio.create_task(executor.execute(connection, "SELECT 1", 1, 30, 4096))
        await asyncio.wait_for(started.wait(), 5)
        with pytest.raises(ServiceError) as error:
            await executor.execute(connection, "SELECT 1", 1, 30, 4096)
        assert error.value.code == "EXECUTOR_BUSY"
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert children[-1].returncode is not None
        assert not executor.processes and executor.slots.qsize() == 1
        await executor.close()
        with pytest.raises(ServiceError) as error:
            await executor.execute(connection, "SELECT 1", 1, 30, 4096)
        assert error.value.code == "SERVICE_STOPPING"

    asyncio.run(scenario())
