import asyncio
import sys

import pytest
from pydantic import ValidationError
from test_studio import studio as studio
from test_studio import studio_settings as studio_settings

from wren_semantic.database_scan import DatabaseConnection, DatabaseScanner, ScanSnapshots
from wren_semantic.errors import ServiceError
from wren_semantic.scan_worker import error_result, metadata_preview

CONNECTION = {
    "dialect": "postgres",
    "host": "db.example",
    "port": 5432,
    "database": "edu",
    "user": "reader",
    "password": "never-echo-this-password",
    "tls": "require",
}


def preview():
    return metadata_preview(
        {"tables": ["schools", "students"], "physical_schema": "education", "dialect": "postgres"},
        [{"name": "schools", "description": "学校"}, {"name": "students", "description": "学生"}],
        [
            {
                "table_name": "schools",
                "name": "id",
                "raw_type": "bigint",
                "nullable": False,
                "description": "",
            },
            {
                "table_name": "schools",
                "name": "name",
                "raw_type": "varchar(100)",
                "nullable": True,
                "description": "学校名",
            },
            {
                "table_name": "students",
                "name": "id",
                "raw_type": "bigint",
                "nullable": False,
                "description": "",
            },
            {
                "table_name": "students",
                "name": "school_id",
                "raw_type": "bigint",
                "nullable": False,
                "description": "",
            },
        ],
        [
            {"table_name": "schools", "kind": "p", "columns": ["id"]},
            {"table_name": "students", "kind": "p", "columns": ["id"]},
            {
                "table_name": "students",
                "kind": "f",
                "columns": ["school_id"],
                "target_schema": "education",
                "target_table": "schools",
                "target_columns": ["id"],
            },
        ],
    )


@pytest.mark.parametrize(
    "host", ["http://db", "db,other", "/var/run/postgresql", "db password=secret", "db?a=1"]
)
def test_host_cannot_inject_connection_options(host):
    with pytest.raises(ValidationError) as exc:
        DatabaseConnection(**{**CONNECTION, "host": host})
    assert CONNECTION["password"] not in str(exc.value)


def test_metadata_snapshot_is_owned_expiring_bounded_and_detached(monkeypatch):
    clock = [100]
    monkeypatch.setattr("wren_semantic.database_scan.time.monotonic", lambda: clock[0])
    cache = ScanSnapshots(ttl=10, limit=3, per_session=2)
    p = preview()
    key = cache.put("first", "postgres", p)
    p["tables"].clear()
    fetched = cache.get(key, "first", "postgres")
    assert len(fetched["tables"]) == 2
    fetched["tables"].clear()
    assert cache.get(key, "first", "postgres")["tables"]
    for owner, dialect in [("second", "postgres"), ("first", "mysql")]:
        with pytest.raises(ServiceError):
            cache.get(key, owner, dialect)
    cache.put("first", "postgres", preview())
    cache.put("first", "postgres", preview())
    assert len(cache.entries) == 2
    with pytest.raises(ServiceError):
        cache.get(key, "first", "postgres")
    other = cache.put("second", "postgres", preview())
    cache.discard("first")
    assert len(cache.entries) == 1
    clock[0] = 111
    with pytest.raises(ServiceError):
        cache.get(other, "second", "postgres")
    assert not cache.entries


def test_driver_messages_are_never_returned():
    exc = RuntimeError("password=never-echo-this-password ssl private host details")
    code, message = error_result(exc)
    assert code == "DB_CONNECTION_FAILED" and CONNECTION["password"] not in message
    assert error_result(Exception(1045, CONNECTION["password"]))[0] == "DB_AUTH_FAILED"


def test_scan_api_metadata_generation_and_session_isolation(studio, monkeypatch):
    operations = []

    async def fake(operation, body):
        operations.append(operation)
        assert body.password.get_secret_value() == CONNECTION["password"]
        return {"connected": True, "schemas": ["education"]} if operation == "test" else preview()

    monkeypatch.setattr(studio.app.state.database_scanner, "inspect", fake)
    before = studio.get("/studio/api/drafts").json()
    test = studio.post("/studio/api/automodel/database/test", json=CONNECTION)
    assert test.status_code == 200 and test.json()["connected"]
    response = studio.post(
        "/studio/api/automodel/database/scan",
        json={**CONNECTION, "physical_schema": "education", "tables": ["schools", "students"]},
    )
    assert response.status_code == 200, response.text
    assert CONNECTION["password"] not in response.text
    p = response.json()
    assert studio.get("/studio/api/drafts").json() == before
    body = {
        "scan_id": p["scan_id"],
        "name": "直连扫描模型",
        "dialect": "postgres",
        "tables": [
            {"table_id": t["id"], "columns": [c["id"] for c in t["columns"]]} for t in p["tables"]
        ],
    }
    review = studio.post("/studio/api/automodel/review", json=body)
    assert review.status_code == 200, review.text
    generated = studio.post("/studio/api/automodel/generate", json=body)
    assert generated.status_code == 201, generated.text
    assert generated.json()["validation"]["valid"]
    assert len(generated.json()["draft"]["manifest"]["relationships"]) == 1
    assert generated.json()["draft"]["manifest"] == review.json()["manifest"]
    assert operations == ["test", "scan"]  # review/generation never reconnect or reuse passwords.
    contents = studio.app.state.studio_store.path.read_bytes()
    assert CONNECTION["password"].encode() not in contents
    assert CONNECTION["password"] not in generated.text
    both = {**body, "ddl": "CREATE TABLE t(id INT)"}
    assert studio.post("/studio/api/automodel/review", json=both).status_code == 422
    studio.post("/studio/api/logout")
    login = studio.post("/studio/api/login", json={"password": "studio-test-password"})
    studio.headers["X-Studio-CSRF"] = login.json()["csrf"]
    assert studio.post("/studio/api/automodel/review", json=body).status_code == 409


def test_scan_auth_csrf_and_connection_validation(studio):
    token = studio.headers.pop("X-Studio-CSRF")
    assert studio.post("/studio/api/automodel/database/test", json=CONNECTION).status_code == 403
    studio.headers["X-Studio-CSRF"] = token
    invalid = {**CONNECTION, "host": "http://localhost", "port": 70000}
    response = studio.post("/studio/api/automodel/database/test", json=invalid)
    assert response.status_code == 422
    assert CONNECTION["password"] not in response.text
    assert (
        studio.post(
            "/studio/api/automodel/database/scan",
            json={**CONNECTION, "physical_schema": "education", "tables": ["t"] * 51},
        ).status_code
        == 422
    )
    studio.post("/studio/api/logout")
    assert studio.post("/studio/api/automodel/database/test", json=CONNECTION).status_code == 401


def test_scanner_cancellation_reaps_child_and_releases_slot(monkeypatch):
    async def scenario():
        original = asyncio.create_subprocess_exec
        started, children = asyncio.Event(), []

        async def sleeper(*args, **kwargs):
            child = await original(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
            children.append(child)
            started.set()
            return child

        monkeypatch.setattr(asyncio, "create_subprocess_exec", sleeper)
        scanner = DatabaseScanner(1)
        job = DatabaseConnection(**CONNECTION)
        running = asyncio.create_task(scanner.inspect("test", job))
        await asyncio.wait_for(started.wait(), 5)
        with pytest.raises(ServiceError) as error:
            await scanner.inspect("test", job)
        assert error.value.code == "SCANNER_BUSY"
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert children[0].returncode is not None
        assert not scanner.processes and scanner.slots.qsize() == 1
        await scanner.close()

    asyncio.run(scenario())
