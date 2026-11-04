import duckdb
import pytest


def test_health_auth_and_private_openapi(client, auth):
    assert client.get("/health/ready").json()["status"] == "ready"
    assert client.get("/health/live").status_code == 200
    assert client.get("/internal/v1/bundles").status_code == 401
    assert (
        client.get("/internal/v1/bundles", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )
    assert client.get("/internal/v1/openapi.json").status_code == 401
    assert client.get("/internal/v1/openapi.json", headers=auth).status_code == 200


def test_context_exposes_logical_fields_without_physical_mapping(client, auth):
    response = client.get("/internal/v1/bundles/education-demo-v1/context", headers=auth)
    assert response.status_code == 200
    context = response.json()
    assert any(col["name"] == "valid_score" for col in context["models"][0]["columns"])
    assert "tableReference" not in response.text
    assert "edu_analysis" not in response.text


def test_real_sdk_plan_and_effective_zero_score(client, auth, plan_body):
    response = client.post(
        "/internal/v1/plan", headers={**auth, "X-Request-ID": "test-average"}, json=plan_body
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["request_id"] == response.headers["x-request-id"] == "test-average"
    assert result["manifest_hash"] == plan_body["manifest_hash"]
    assert result["wrenai_version"] == "0.17.1"
    # Execute only the emitted demo SQL in an isolated in-memory test DB.
    # The default test configuration does not enable physical SQL execution.
    with duckdb.connect() as db:
        db.execute("CREATE SCHEMA edu_analysis")
        db.execute(
            "CREATE TABLE edu_analysis.v_student_subject_score("
            "exam_batch_id VARCHAR, score DOUBLE, score_status VARCHAR)"
        )
        db.execute(
            "INSERT INTO edu_analysis.v_student_subject_score VALUES "
            "('exam_demo',0,'valid'),('exam_demo',80,'valid'),"
            "('exam_demo',100,'absent'),('other',100,'valid')"
        )
        assert db.execute(result["physical_sql"]).fetchone() == (40.0, 2)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE student_subject_score",
        "DELETE FROM student_subject_score",
        "SELECT 1; SELECT 2",
        "SELECT * INTO stolen FROM student_subject_score",
        "WITH changed AS (DELETE FROM student_subject_score RETURNING *) SELECT * FROM changed",
        "SELECT * FROM student_subject_score FOR UPDATE",
        "SELECT * FROM secret_physical_table",
        "SELECT pg_sleep(1) FROM student_subject_score",
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT AVG( FROM student_subject_score",
    ],
)
def test_rejects_unsafe_or_unmodeled_sql(client, auth, plan_body, sql):
    response = client.post(
        "/internal/v1/plan", headers=auth, json={**plan_body, "semantic_sql": sql}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] in {"INVALID_SQL", "PLANNING_FAILED"}


def test_model_binding_and_body_limits(client, auth, plan_body):
    response = client.post(
        "/internal/v1/plan", headers=auth, json={**plan_body, "manifest_hash": "0" * 64}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MODEL_VERSION_MISMATCH"
    assert (
        client.post(
            "/internal/v1/plan", headers=auth, json={**plan_body, "bundle_id": "missing"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/internal/v1/plan", headers=auth, json={**plan_body, "manifest_path": "/etc/passwd"}
        ).status_code
        == 422
    )
    assert client.post("/internal/v1/plan", headers=auth, content=b"x" * 70_000).status_code == 413


def test_validation_errors_do_not_echo_sql(client, auth, plan_body):
    secret = "sensitive-content-should-not-be-echoed"
    response = client.post(
        "/internal/v1/plan", headers=auth, json={**plan_body, "arbitrary": secret}
    )
    assert response.status_code == 422
    assert secret not in response.text


def test_cte_plan_stays_within_model(client, auth, plan_body):
    sql = (
        "WITH scores AS (SELECT class_id, valid_score FROM student_subject_score) "
        "SELECT class_id, AVG(valid_score) FROM scores GROUP BY class_id"
    )
    response = client.post(
        "/internal/v1/plan", headers=auth, json={**plan_body, "semantic_sql": sql}
    )
    assert response.status_code == 200, response.text
