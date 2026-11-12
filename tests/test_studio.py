import io
import json
import re
import zipfile
from copy import deepcopy
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from wren_semantic.app import create_app
from wren_semantic.config import Settings
from wren_semantic.modeling import structural_issues

PASSWORD = "studio-test-password"
TOKEN = "studio-service-test-token-000000000000"


@pytest.fixture
def studio_settings(tmp_path):
    return Settings(
        service_token=TOKEN,
        studio_enabled=True,
        studio_password=PASSWORD,
        studio_data_dir=tmp_path / "studio",
    )


@pytest.fixture
def studio(studio_settings):
    with TestClient(create_app(studio_settings)) as client:
        response = client.post("/studio/api/login", json={"password": PASSWORD})
        assert response.status_code == 200
        client.headers["X-Studio-CSRF"] = response.json()["csrf"]
        yield client


def template(client):
    return client.get("/studio/api/templates").json()["templates"][0]["manifest"]


def draft(client, manifest=None):
    response = client.post(
        "/studio/api/drafts",
        json={"name": "学情模型", "dialect": "postgres", "manifest": manifest or template(client)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_studio_assets_auth_and_csrf(studio_settings):
    with TestClient(create_app(studio_settings)) as client:
        assert client.get("/").url.path == "/studio/"
        for asset in [
            "/studio/",
            "/studio/assets/studio.js",
            "/studio/assets/studio.css",
            "/studio/assets/editor.css",
        ]:
            response = client.get(asset)
            assert response.status_code == 200
            assert TOKEN not in response.text and PASSWORD not in response.text
            assert "script-src 'self'" in response.headers["content-security-policy"]
        first, second = client.get("/studio/"), client.get("/studio/")
        nonce = re.search(r'name="csp-nonce" content="([^"\s]+)"', first.text).group(1)
        assert f"'nonce-{nonce}'" in first.headers["content-security-policy"]
        assert "unsafe-inline" not in first.headers["content-security-policy"]
        assert nonce not in second.text
        assert "__STUDIO_NONCE__" not in first.text
        assert client.get("/studio/api/drafts").status_code == 401
        assert client.post("/studio/api/login", json={"password": "wrong"}).status_code == 401
        response = client.post("/studio/api/login", json={"password": PASSWORD})
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert client.get("/studio/api/session").json()["authenticated"]
        body = {"name": "test", "dialect": "postgres", "manifest": {}}
        assert client.post("/studio/api/drafts", json=body).status_code == 403
        headers = {"X-Studio-CSRF": response.json()["csrf"], "Origin": "https://other.example"}
        assert client.post("/studio/api/drafts", json=body, headers=headers).status_code == 403
        client.headers["X-Studio-CSRF"] = response.json()["csrf"]
        assert client.get("/internal/v1/bundles").status_code == 401
        assert client.post("/studio/api/logout").status_code == 200
        assert client.get("/studio/api/session").status_code == 401


def test_draft_revision_invalid_model_and_real_sdk_plan(studio):
    d = draft(studio)
    path = f"/studio/api/drafts/{d['id']}"
    updated = {k: d[k] for k in ["name", "dialect", "manifest", "revision"]}
    updated["name"] = "修改后的模型"
    response = studio.put(path, json=updated)
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert studio.put(path, json=updated).status_code == 409
    assert studio.post(path + "/validate", json={"revision": 1}).status_code == 409
    checked = studio.post(path + "/validate", json={"revision": 2})
    assert checked.status_code == 200, checked.text
    assert checked.json()["valid"], checked.text
    response = studio.post(
        path + "/plan",
        json={"revision": 2, "semantic_sql": "SELECT AVG(valid_score) FROM student_subject_score"},
    )
    assert response.status_code == 200, response.text
    assert "edu_analysis" in response.json()["physical_sql"]
    response = studio.post(
        path + "/plan", json={"revision": 2, "semantic_sql": "DROP TABLE schools"}
    )
    assert response.status_code == 422
    invalid = deepcopy(updated)
    invalid["revision"] = 2
    invalid["manifest"]["models"][0]["columns"][0]["type"] = ""
    assert studio.put(path, json=invalid).status_code == 200
    checked = studio.post(path + "/validate", json={"revision": 3}).json()
    assert not checked["valid"]
    assert any(".type" in issue["path"] for issue in checked["issues"])
    assert (
        studio.post(path + "/publish", json={"revision": 3, "bundle_id": "invalid-v1"}).status_code
        == 422
    )


@pytest.mark.parametrize("composite", [False, True])
def test_selected_relation_fields_plan_with_real_sdk(studio, composite):
    manifest = template(studio)
    condition = '"student_subject_score"."school_id" = "schools"."id"'
    if composite:
        condition += ' AND "student_subject_score"."student_id" = "schools"."name"'
    manifest["relationships"][0]["condition"] = condition
    d = draft(studio, manifest)
    path = f"/studio/api/drafts/{d['id']}"
    checked = studio.post(path + "/validate", json={"revision": 1})
    assert checked.status_code == 200, checked.text
    assert checked.json()["valid"], checked.text
    planned = studio.post(
        path + "/plan",
        json={"revision": 1, "semantic_sql": "SELECT school_name FROM student_subject_score"},
    )
    assert planned.status_code == 200, planned.text
    assert "JOIN" in planned.json()["physical_sql"].upper()


def test_semantic_view_trial_query_expands_with_real_sdk(studio):
    manifest = template(studio)
    manifest["views"] = [
        {
            "name": "school_summary",
            "statement": (
                "SELECT school_id, COUNT(*) AS score_count "
                "FROM student_subject_score GROUP BY school_id"
            ),
        }
    ]
    d = draft(studio, manifest)
    result = studio.post(
        f"/studio/api/drafts/{d['id']}/plan",
        json={"revision": 1, "semantic_sql": 'SELECT * FROM "school_summary" LIMIT 10'},
    )
    assert result.status_code == 200, result.text
    assert "edu_analysis" in result.json()["physical_sql"]
    assert "10" in result.json()["physical_sql"]
    assert result.json()["duration_ms"] >= 0


def test_semantic_view_trial_query_reports_invalid_column(studio):
    manifest = template(studio)
    manifest["views"] = [
        {"name": "broken_view", "statement": "SELECT missing_column FROM student_subject_score"}
    ]
    d = draft(studio, manifest)
    result = studio.post(
        f"/studio/api/drafts/{d['id']}/plan",
        json={"revision": 1, "semantic_sql": 'SELECT * FROM "broken_view" LIMIT 10'},
    )
    assert result.status_code == 422, result.text
    assert result.json()["error"]["message"]


def test_publish_download_restore_and_immutable_release(studio, studio_settings):
    d = draft(studio)
    path = f"/studio/api/drafts/{d['id']}"
    body = {"revision": 1, "bundle_id": "studio-v1"}
    released = studio.post(path + "/publish", json=body)
    assert released.status_code == 201, released.text
    released = released.json()
    assert studio.post(path + "/publish", json=body).status_code == 409
    download = studio.get("/studio/api/bundles/studio-v1/download")
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        mdl = json.loads(archive.read("studio-v1/mdl.json"))
        assert mdl == d["manifest"]
        registry = json.loads(archive.read("registry.json"))
        assert registry["bundles"][0]["manifest_hash"] == released["manifest_hash"]
    saved = {k: d[k] for k in ["name", "dialect", "manifest", "revision"]}
    saved["manifest"]["models"][0]["properties"]["description"] = "new draft content"
    assert studio.put(path, json=saved).status_code == 200
    assert studio.get("/studio/api/bundles/studio-v1/manifest").json() == mdl
    with TestClient(create_app(studio_settings)) as restarted:
        response = restarted.get(
            "/internal/v1/bundles", headers={"Authorization": f"Bearer {TOKEN}"}
        )
        assert any(b["bundle_id"] == "studio-v1" for b in response.json()["bundles"])
        assert restarted.get("/health/ready").status_code == 200
        response = restarted.post(
            "/internal/v1/plan",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={
                "bundle_id": "studio-v1",
                "manifest_hash": released["manifest_hash"],
                "semantic_sql": "SELECT school_name, AVG(valid_score) "
                "FROM student_subject_score GROUP BY school_name",
            },
        )
        assert response.status_code == 200, response.text
        sql = response.json()["physical_sql"]
        assert "dim_school" in sql
        with duckdb.connect() as db:
            db.execute("CREATE SCHEMA edu_analysis")
            db.execute("CREATE TABLE edu_analysis.dim_school(id VARCHAR, name VARCHAR)")
            db.execute("INSERT INTO edu_analysis.dim_school VALUES ('a', 'School A')")
            db.execute(
                "CREATE TABLE edu_analysis.v_student_subject_score("
                "school_id VARCHAR, score DOUBLE, score_status VARCHAR)"
            )
            db.execute(
                "INSERT INTO edu_analysis.v_student_subject_score VALUES "
                "('a',0,'valid'),('a',80,'valid'),('a',100,'absent')"
            )
            assert db.execute(sql).fetchall() == [("School A", 40.0)]


@pytest.mark.parametrize(
    "change",
    [
        lambda m: m["relationships"][0].update(models=[{}, []]),
        lambda m: m["relationships"][0].update(joinType={}),
        lambda m: m["models"][0].update(primaryKey={"invalid": True}),
        lambda m: m["models"][0].update(properties=[]),
        lambda m: m["models"][0]["columns"][-1].update(relationship={"invalid": True}),
    ],
)
def test_malformed_import_reports_issues_instead_of_crashing(studio, change):
    manifest = template(studio)
    change(manifest)
    assert structural_issues(manifest)
    d = draft(studio, manifest)
    response = studio.post(f"/studio/api/drafts/{d['id']}/validate", json={"revision": 1})
    assert response.status_code == 200, response.text
    assert not response.json()["valid"]


def test_studio_disabled_by_default(client):
    assert client.get("/studio/").status_code == 404


def test_workspace_metadata_and_delete_restore_with_revision_checks(studio):
    d = draft(studio)
    path = f"/studio/api/drafts/{d['id']}"
    metadata = {"name": "改名的工作空间模型", "dialect": "mysql", "revision": 1}
    saved = studio.patch(path, json=metadata)
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    assert saved["name"] == metadata["name"] and saved["dialect"] == "mysql"
    assert saved["manifest"] == d["manifest"] and saved["revision"] == 2
    assert studio.patch(path, json=metadata).status_code == 409
    assert studio.patch(path, json={**metadata, "name": "   ", "revision": 2}).status_code == 422
    assert studio.request("DELETE", path, json={"revision": 1}).status_code == 409
    deleted = studio.request("DELETE", path, json={"revision": 2})
    assert deleted.status_code == 200 and deleted.json()["revision"] == 3
    assert d["id"] not in {x["id"] for x in studio.get("/studio/api/drafts").json()["drafts"]}
    trash = studio.get("/studio/api/drafts?deleted=true").json()["drafts"]
    assert len(trash) == 1 and trash[0]["id"] == d["id"] and trash[0]["deleted_at"]
    assert studio.get(path).status_code == 404
    assert studio.patch(path, json={**metadata, "revision": 3}).status_code == 404
    assert studio.put(path, json={**metadata, "revision": 3, "manifest": {}}).status_code == 404
    assert studio.post(path + "/validate", json={"revision": 3}).status_code == 404
    assert studio.post(path + "/restore", json={"revision": 2}).status_code == 409
    restored = studio.post(path + "/restore", json={"revision": 3})
    assert restored.status_code == 200, restored.text
    restored = restored.json()
    assert restored["revision"] == 4 and restored["deleted_at"] is None
    assert restored["manifest"] == d["manifest"] and restored["name"] == metadata["name"]
    assert studio.get("/studio/api/drafts?deleted=true").json()["drafts"] == []
    assert studio.post(path + "/restore", json={"revision": 4}).status_code == 404


def test_delete_keeps_published_version_and_disallows_stale_publication(studio):
    from wren_semantic.errors import ServiceError
    from wren_semantic.modeling import authoring_bundle

    d = draft(studio)
    path = f"/studio/api/drafts/{d['id']}"
    response = studio.post(path + "/publish", json={"revision": 1, "bundle_id": "keep-v1"})
    assert response.status_code == 201, response.text
    bundle = next(
        b
        for b in studio.get("/studio/api/bundles").json()["bundles"]
        if b["bundle_id"] == "keep-v1"
    )
    assert bundle["draft_id"] == d["id"] and bundle["revision"] == 1
    assert studio.request("DELETE", path, json={"revision": 1}).status_code == 200
    assert studio.get("/studio/api/bundles/keep-v1/manifest").json() == d["manifest"]
    assert studio.get("/studio/api/bundles/keep-v1/download").status_code == 200
    with pytest.raises(ServiceError, match="校验期间草稿已更新"):
        studio.app.state.studio_store.publish(
            d, authoring_bundle(d["manifest"], "postgres", "stale-v2")
        )


def test_legacy_studio_schema_migrates_without_changing_data(tmp_path):
    import sqlite3

    from wren_semantic.studio_store import StudioStore

    directory = tmp_path / "legacy"
    directory.mkdir()
    with sqlite3.connect(directory / "studio.db") as db:
        db.execute(
            "CREATE TABLE drafts(id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "dialect TEXT NOT NULL, manifest TEXT NOT NULL, revision INTEGER NOT NULL, "
            "updated_at TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO drafts VALUES (?,?,?,?,?,?)",
            ("legacy-model", "已有模型", "postgres", '{"models":[]}', 7, "2026-11-01"),
        )
    store = StudioStore(directory)
    d = store.get_draft("legacy-model")
    assert d["revision"] == 7 and d["manifest"] == {"models": []} and d["deleted_at"] is None
    assert len(StudioStore(directory).list_drafts()) == 1
    store.delete_draft("legacy-model", 7)
    assert StudioStore(directory).list_drafts() == []
    assert len(store.list_drafts(deleted=True)) == 1
    assert store.restore_draft("legacy-model", 8)["revision"] == 9


def test_workspace_mutations_require_csrf(studio):
    d = draft(studio)
    path = f"/studio/api/drafts/{d['id']}"
    studio.headers.pop("X-Studio-CSRF")
    assert (
        studio.patch(path, json={"name": "blocked", "dialect": "mysql", "revision": 1}).status_code
        == 403
    )
    assert studio.request("DELETE", path, json={"revision": 1}).status_code == 403
    assert studio.post(path + "/restore", json={"revision": 1}).status_code == 403


def test_v2_semantic_preview_publication_discards_retired_metadata(studio):
    manifest = template(studio)
    legacy = {"schemaVersion": 1, "id": "legacy.scores", "requirements": []}
    manifest["views"] = [
        {
            "name": "scores_v2",
            "statement": (
                "SELECT exam_batch_id AS exam_id, valid_score, 1 AS student_count, "
                "1 AS score_rank FROM student_subject_score"
            ),
            "properties": {"analysisContract": legacy, "description": "保留说明"},
        }
    ]
    d = draft(studio, manifest)
    path = f"/studio/api/drafts/{d['id']}"
    body = {"revision": d["revision"], "object_name": "scores_v2"}
    fields = ["exam_id", "valid_score", "student_count", "score_rank"]
    discovered = studio.post(path + "/semantic-preview", json=body)
    assert discovered.status_code == 200 and discovered.json()["valid"], discovered.text
    assert discovered.json()["output_columns"]["scores_v2"] == fields
    semantic = {
        "schema_version": 2,
        "object": "scores_v2",
        "columns": fields,
        "grain": ["exam"],
        "dimensions": [
            {
                "id": "exam",
                "label": "考试",
                "fields": ["exam_id"],
                "candidate_source": {"object": "scores_v2", "fields": ["exam_id"]},
            }
        ],
        "measures": [
            {
                "id": "average",
                "label": "均分",
                "field": "valid_score",
                "description": "有效学生均分",
                "operation": "weighted_mean",
                "weight_field": "student_count",
                "population": "valid_students",
                "required_dimensions": ["exam"],
            }
        ],
        "capabilities": [
            {
                "id": "ranking",
                "measures": ["average"],
                "population": "valid_students",
                "operations": ["rank"],
                "rank_field": "score_rank",
                "rank_measure": "average",
                "rank_partition": ["exam"],
            }
        ],
    }

    def preview(value):
        result = studio.post(path + "/semantic-preview", json={**body, "semantic_model": value})
        assert result.status_code == 200, result.text
        return result.json()

    assert preview(semantic)["valid"]
    for edit in [
        lambda s: s.update(grain=["exam_id"]),
        lambda s: s["dimensions"][0].update(parents=["exam"]),
        lambda s: s["measures"][0].update(weight_field=None),
        lambda s: s["capabilities"][0].update(population="all_students"),
        lambda s: s["capabilities"][0].update(rank_measure="absent"),
        lambda s: s.update(columns=fields + ["ghost"]),
        lambda s: s["dimensions"][0]["candidate_source"].update(object="schools"),
    ]:
        invalid = deepcopy(semantic)
        edit(invalid)
        assert not preview(invalid)["valid"]
    assert studio.get(path).json() == d
    assert studio.post(path + "/semantic-preview", json={**body, "revision": 99}).status_code == 409
    assert (
        studio.post(path + "/semantic-preview", json={**body, "object_name": "absent"}).status_code
        == 422
    )
    manifest["views"][0]["properties"]["semanticModel"] = semantic
    updated = studio.put(
        path,
        json={
            "name": d["name"],
            "dialect": d["dialect"],
            "revision": d["revision"],
            "manifest": manifest,
        },
    ).json()
    result = studio.post(
        path + "/publish", json={"revision": updated["revision"], "bundle_id": "studio-v2"}
    )
    assert result.status_code == 201, result.text
    headers = {"Authorization": f"Bearer {TOKEN}"}
    catalog = studio.get("/internal/v1/bundles/studio-v2/semantic-catalog", headers=headers).json()
    assert catalog["sources"][0]["measures"][0]["operation"] == "weighted_mean"
    assert catalog["sources"][0]["capabilities"][0]["rank_partition"] == ["exam"]
    assert catalog["manifest_hash"] == result.json()["manifest_hash"]
    assert "analysisContract" not in studio.get(path).json()["manifest"]["views"][0]["properties"]
    assert "analysisContract" in manifest["views"][0]["properties"]  # Input remains untouched.


def test_v2_field_discovery_repairs_metadata_and_supports_models(studio):
    manifest = template(studio)
    obj = manifest["models"][0]
    obj["properties"]["semanticModel"] = {"schema_version": 99}
    obj["properties"]["analysisContract"] = {"schemaVersion": 99}
    d = draft(studio, manifest)
    path = f"/studio/api/drafts/{d['id']}"
    body = {"revision": d["revision"], "object_name": obj["name"]}
    result = studio.post(path + "/semantic-preview", json=body)
    assert result.status_code == 200 and result.json()["valid"], result.text
    assert "exam_batch_id" in result.json()["output_columns"][obj["name"]]
    assert studio.get(path).json() == d
    studio.headers.pop("X-Studio-CSRF")
    assert studio.post(path + "/semantic-preview", json=body).status_code == 403


def test_retired_metadata_is_cleaned_on_import_save_and_old_routes_are_removed(studio):
    manifest = template(studio)
    properties = manifest["models"][0]["properties"]
    properties["analysisContract"] = {"schemaVersion": 99}
    properties["custom"] = {"keep": True}
    d = draft(studio, manifest)
    path = f"/studio/api/drafts/{d['id']}"
    assert "analysisContract" not in d["manifest"]["models"][0]["properties"]
    assert "analysisContract" in properties
    result = studio.put(
        path,
        json={
            "name": d["name"],
            "dialect": d["dialect"],
            "manifest": manifest,
            "revision": d["revision"],
        },
    )
    assert result.status_code == 200, result.text
    saved = result.json()
    assert "analysisContract" not in saved["manifest"]["models"][0]["properties"]
    assert saved["manifest"]["models"][0]["properties"]["custom"] == {"keep": True}
    assert studio.post(path + "/validate", json={"revision": saved["revision"]}).json()["valid"]
    assert (
        studio.post(
            path + "/contract-preview", json={"revision": saved["revision"], "view_name": "unused"}
        ).status_code
        == 404
    )


def test_retired_draft_migration_is_idempotent_and_preserves_publications(tmp_path):
    from wren_semantic.errors import ServiceError
    from wren_semantic.modeling import authoring_bundle
    from wren_semantic.studio_store import StudioStore

    directory = tmp_path / "migration"
    store = StudioStore(directory)
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "models/education-demo-v1/mdl.json").read_text()
    )
    manifest["models"][0]["properties"]["analysisContract"] = {"schemaVersion": 99}
    manifest["models"][0]["properties"]["custom"] = "keep"
    # Simulate rows written by the previous release, bypassing import normalization.
    active = store.create_draft("active", "postgres", manifest)
    trashed = store.create_draft("trash", "postgres", manifest)
    store.delete_draft(trashed["id"], trashed["revision"])
    with store.connect() as db:
        db.execute("UPDATE drafts SET manifest=?", (json.dumps(manifest),))
    before = store.get_draft(active["id"])
    old_bundle = authoring_bundle(manifest, "postgres", "historic-release")
    store.publish(before, old_bundle)
    released = store.releases()
    store = StudioStore(directory)
    current = store.get_draft(active["id"])
    assert current["revision"] == before["revision"] + 1
    assert "analysisContract" not in current["manifest"]["models"][0]["properties"]
    assert current["manifest"]["models"][0]["properties"]["custom"] == "keep"
    trash = store.list_drafts(deleted=True)[0]
    assert trash["revision"] == 3 and trash["deleted_at"]
    assert "analysisContract" not in trash["manifest"]["models"][0]["properties"]
    assert store.releases() == released
    assert "analysis_contract_schema_version" not in old_bundle.context
    assert "analysis_contract_refs" not in old_bundle.context
    assert StudioStore(directory).get_draft(active["id"]) == current
    with pytest.raises(ServiceError) as conflict:
        store.save_draft(active["id"], "stale", "postgres", manifest, before["revision"])
    assert conflict.value.code == "DRAFT_CONFLICT"
