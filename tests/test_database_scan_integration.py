"""Opt-in integration against this task's isolated, seeded database containers."""

import os

import pytest
from test_studio import studio as studio
from test_studio import studio_settings as studio_settings

pytestmark = pytest.mark.skipif(
    os.getenv("SCAN_TEST_DATABASES") != "1", reason="Requires isolated scan test databases"
)


@pytest.mark.parametrize(
    "dialect,port,schema,tls",
    [
        ("postgres", 15443, "education", "disable"),
        ("mysql", 13317, "mdl_scan_test", "require"),
    ],
)
def test_real_readonly_metadata_to_validated_mdl(studio, dialect, port, schema, tls):
    body = {
        "dialect": dialect,
        "host": "127.0.0.1",
        "port": port,
        "database": "mdl_scan_test",
        "user": "mdl_scanner",
        "password": "scan-integration-only",
        "tls": tls,
    }
    tested = studio.post("/studio/api/automodel/database/test", json=body)
    assert tested.status_code == 200, tested.text
    assert schema in tested.json()["schemas"]
    scope = {**body, "physical_schema": schema}
    listing = studio.post("/studio/api/automodel/database/tables", json=scope)
    assert listing.status_code == 200, listing.text
    assert {t["name"] for t in listing.json()["tables"]} == {"schools", "students", "scores"}
    filtered = studio.post(
        "/studio/api/automodel/database/tables", json={**scope, "table_filter": "school"}
    )
    assert [t["name"] for t in filtered.json()["tables"]] == ["schools"]
    scan = studio.post(
        "/studio/api/automodel/database/scan",
        json={**scope, "tables": ["schools", "students", "scores"]},
    )
    assert scan.status_code == 200, scan.text
    preview = scan.json()
    tables = {t["key"][2]: t for t in preview["tables"]}
    assert tables["schools"]["description"] == "学校表"
    assert tables["schools"]["columns"][1]["description"] == "学校名称"
    assert not tables["students"]["columns"][1]["nullable"]
    assert tables["scores"]["primary_key"] == ["student_id", "subject"]
    assert tables["students"]["foreign_keys"][0]["target_id"] == tables["schools"]["id"]
    payload = {
        "scan_id": preview["scan_id"],
        "dialect": dialect,
        "name": f"{dialect} 直连集成测试",
        "tables": [
            {
                "table_id": t["id"],
                "columns": [c["id"] for c in t["columns"] if c["id"] != "private_note"],
            }
            for t in preview["tables"]
        ],
    }
    reviewed = studio.post("/studio/api/automodel/review", json=payload)
    assert reviewed.status_code == 200, reviewed.text
    created = studio.post("/studio/api/automodel/generate", json=payload)
    assert created.status_code == 201, created.text
    result = created.json()
    assert result["validation"]["valid"] and result["warnings"]
    manifest = result["draft"]["manifest"]
    assert manifest == reviewed.json()["manifest"]
    assert "private_note" not in str(manifest)
    assert body["password"] not in created.text
    assert len(manifest["relationships"]) == 2
    d = result["draft"]
    planned = studio.post(
        f"/studio/api/drafts/{d['id']}/plan",
        json={
            "revision": d["revision"],
            "semantic_sql": "SELECT subject, AVG(score) FROM scores GROUP BY subject",
        },
    )
    assert planned.status_code == 200, planned.text
    assert schema in planned.json()["physical_sql"]
    wrong = studio.post(
        "/studio/api/automodel/database/test", json={**body, "password": "incorrect-never-echo"}
    )
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "DB_AUTH_FAILED"
    assert "incorrect-never-echo" not in wrong.text
