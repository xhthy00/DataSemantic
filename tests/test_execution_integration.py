"""Opt-in tests against isolated containers; never use business database credentials."""

import hashlib
import json
import os

import pytest
from conftest import TOKEN
from fastapi.testclient import TestClient

from wren_semantic.app import create_app
from wren_semantic.config import Settings

pytestmark = pytest.mark.skipif(
    os.getenv("EXECUTION_TEST_DATABASES") != "1",
    reason="Requires isolated execution test databases",
)


@pytest.fixture(scope="module", params=[("postgres", 15444), ("mysql", 13318)])
def execution_client(request, tmp_path_factory):
    dialect, port = request.param
    root = tmp_path_factory.mktemp("execution")
    path = root / "sources.json"
    manifest = {
        "catalog": "wren",
        "schema": "education",
        "models": [
            {
                "name": "modeled_scores",
                "tableReference": {
                    "schema": "public" if dialect == "postgres" else "execute_test",
                    "table": "scores",
                },
                "primaryKey": "id",
                "columns": [{"name": "id", "type": "int"}, {"name": "score", "type": "decimal"}],
            }
        ],
        "relationships": [],
        "views": [],
    }
    raw = json.dumps(manifest).encode()
    (root / "mdl.json").write_bytes(raw)
    (root / "registry.json").write_text(
        json.dumps(
            {
                "bundles": [
                    {
                        "bundle_id": "test",
                        "dialect": dialect,
                        "manifest_path": "mdl.json",
                        "manifest_hash": hashlib.sha256(raw).hexdigest(),
                    }
                ]
            }
        )
    )
    path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "test",
                        "dialect": dialect,
                        "host": "127.0.0.1",
                        "port": port,
                        "database": "execute_test",
                        "user": "execute_reader",
                        "password_env": "EXECUTION_TEST_READER_PASSWORD",
                        "tls": "disable" if dialect == "postgres" else "require",
                    }
                ]
            }
        )
    )
    settings = Settings(
        service_token=TOKEN,
        registry_path=root / "registry.json",
        execution_sources_path=path,
        execution_max_result_bytes=4096,
        execution_timeout_seconds=3,
    )
    with TestClient(create_app(settings)) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        yield client


def ask(client, sql, **extra):
    return client.post(
        "/internal/v1/execute",
        json={
            "source_id": "test",
            "physical_sql": sql,
            **extra,
        },
    )


def test_plan_then_execute(execution_client):
    client = execution_client
    bundle = client.get("/internal/v1/bundles").json()["bundles"][0]
    plan = client.post(
        "/internal/v1/plan",
        json={
            "bundle_id": bundle["bundle_id"],
            "manifest_hash": bundle["manifest_hash"],
            "semantic_sql": "SELECT AVG(score) AS average_score FROM modeled_scores",
        },
    )
    assert plan.status_code == 200, plan.text
    response = ask(client, plan.json()["physical_sql"])
    assert response.status_code == 200, response.text
    assert float(response.json()["rows"][0][0]) == 40


def test_real_queries_types_duplicate_columns_and_empty_results(execution_client):
    client = execution_client
    response = ask(client, "SELECT id, score, day FROM scores ORDER BY id")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["columns"] == ["id", "score", "day"]
    assert result["rows"] == [
        [1, "0.0000", "2026-11-03"],
        [2, "80.0000", "2026-11-03"],
        [3, None, None],
    ]
    assert result["row_count"] == 3 and not result["truncated"]
    assert result["request_id"] == response.headers["x-request-id"]
    aggregate = ask(client, "SELECT AVG(score) AS average_score FROM scores").json()
    assert float(aggregate["rows"][0][0]) == 40
    duplicate = ask(client, "SELECT 1 AS x, 2 AS x").json()
    assert duplicate["columns"] == ["x", "x"] and duplicate["rows"] == [[1, 2]]
    empty = ask(client, "SELECT id FROM scores WHERE id=99").json()
    assert empty["columns"] == ["id"] and empty["rows"] == []
    assert not empty["truncated"]


def test_row_byte_caps_and_connection_recovery(execution_client):
    client = execution_client
    result = ask(client, "SELECT id FROM scores ORDER BY id", max_rows=2).json()
    assert result["rows"] == [[1], [2]] and result["truncated"]
    exact = ask(client, "SELECT id FROM scores WHERE id<3", max_rows=2).json()
    assert not exact["truncated"]
    text = "x" * 1500
    bounded = ask(client, f"SELECT '{text}' AS payload FROM numbers").json()
    assert 0 < bounded["row_count"] < 100 and bounded["truncated"]
    huge = ask(client, "SELECT '" + "x" * 6000 + "' AS payload")
    assert huge.status_code == 422 and huge.json()["error"]["code"] == "RESULT_TOO_LARGE"
    assert ask(client, "SELECT 1").status_code == 200


def test_rejected_queries_missing_sources_and_redacted_errors(execution_client):
    client = execution_client
    for sql in ["DELETE FROM scores", "SELECT pg_sleep(1)", "SELECT 1; SELECT 2"]:
        response = ask(client, sql)
        assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_SQL"
    assert ask(client, "SELECT COUNT(*) FROM scores").json()["rows"] == [[3]]
    missing = client.post(
        "/internal/v1/execute",
        json={
            "source_id": "missing",
            "physical_sql": "SELECT 1",
        },
    )
    assert missing.status_code == 404
    response = ask(client, "SELECT private_column_never_echo FROM scores")
    assert response.status_code == 422
    assert "private_column_never_echo" not in response.text
    assert "execute-reader-test" not in response.text


def test_real_query_deadline_and_slot_recovery(execution_client):
    client = execution_client
    response = ask(
        client,
        "SELECT SUM(a.n * b.n + c.n * d.n + e.n) FROM numbers a CROSS JOIN numbers b "
        "CROSS JOIN numbers c CROSS JOIN numbers d CROSS JOIN numbers e",
    )
    assert response.status_code == 504, response.text
    assert response.json()["error"]["code"] == "EXECUTION_TIMEOUT"
    assert ask(client, "SELECT 1").status_code == 200
