import copy
import json
from pathlib import Path

from wren_semantic.modeling import authoring_bundle, copy_manifest
from wren_semantic.semantic_catalog import catalog_from_manifest, semantic_issues
from wren_semantic.worker import run


def manifest():
    root = Path(__file__).resolve().parents[1]
    m = json.loads((root / "models/education-demo-v1/mdl.json").read_text())
    obj = m["models"][0]
    obj.setdefault("properties", {})["semanticModel"] = {
        "schema_version": 2,
        "object": obj["name"],
        "columns": [c["name"] for c in obj["columns"] if not c.get("relationship")],
        "grain": ["record"],
        "dimensions": [
            {"id": "record", "label": "记录", "fields": ["score_id"]},
            {"id": "exam", "label": "考试", "fields": ["exam_batch_id"]},
        ],
        "measures": [
            {
                "id": "valid.score",
                "label": "有效成绩",
                "field": "valid_score",
                "description": "发布的有效成绩字段",
                "population": "recorded",
                "required_dimensions": ["exam"],
            }
        ],
    }
    return m


def test_sdk_preserves_v2_and_immutable_hash_covers_metadata():
    m = manifest()
    bundle = authoring_bundle(m, "postgres")
    assert bundle.context["semantic_catalog_schema_version"] == 2
    catalog = catalog_from_manifest(
        copy_manifest(bundle),
        {"bundle_id": bundle.entry.bundle_id, "manifest_hash": bundle.entry.manifest_hash},
    )
    assert catalog.sources[0].capabilities == []
    result = run(
        {
            "manifest": bundle.encoded_manifest,
            "dialect": "postgres",
            "operation": "validate",
            "names": bundle.queryable_names,
        }
    )
    assert result["ok"], result
    assert not semantic_issues(m, result["output_columns"], require_outputs=True)
    changed = copy.deepcopy(m)
    changed["models"][0]["properties"]["semanticModel"]["measures"][0]["description"] += "变更"
    assert authoring_bundle(changed, "postgres").entry.manifest_hash != bundle.entry.manifest_hash


def test_invalid_refs_cycles_and_sdk_output_drift_block_publication():
    m = manifest()
    m["models"][0]["properties"]["semanticModel"]["dimensions"][0]["fields"] = ["no_such_field"]
    assert semantic_issues(m)
    m = manifest()
    assert semantic_issues(m, {"student_subject_score": ["score_id"]}, require_outputs=True)
    m["models"][0]["properties"]["semanticModel"]["dimensions"][0]["parents"] = ["record"]
    assert semantic_issues(m)


def test_catalog_endpoint_is_authenticated_hash_bound_and_old_endpoint_removed(client, auth):
    bundle = client.get("/internal/v1/bundles", headers=auth).json()["bundles"][0]
    path = f"/internal/v1/bundles/{bundle['bundle_id']}/semantic-catalog"
    assert client.get(path).status_code == 401
    response = client.get(path, headers=auth)
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == 2 and data["manifest_hash"] == bundle["manifest_hash"]
    assert data["sources"] == []  # Missing capabilities do not break old bundles.
    assert client.get(path + "?objects=nonexistent", headers=auth).status_code == 422
    assert (
        client.get(
            f"/internal/v1/bundles/{bundle['bundle_id']}/analysis-contracts", headers=auth
        ).status_code
        == 404
    )
    context = client.get(f"/internal/v1/bundles/{bundle['bundle_id']}/context", headers=auth).json()
    assert "analysis_contract_refs" not in context
    assert "analysis_contract_schema_version" not in context


def test_object_details_include_referenced_identity_sources(client, auth):
    mdl = manifest()
    semantic = mdl["models"][0]["properties"]["semanticModel"]
    semantic["dimensions"][1]["candidate_source"] = {
        "object": "exam_directory",
        "fields": ["exam_batch_id"],
        "labels": ["exam_batch_id"],
    }
    mdl.setdefault("views", []).append(
        {
            "name": "exam_directory",
            "statement": "SELECT DISTINCT exam_batch_id FROM student_subject_score",
            "properties": {
                "semanticModel": {
                    "schema_version": 2,
                    "object": "exam_directory",
                    "columns": ["exam_batch_id"],
                    "grain": ["exam"],
                    "dimensions": [{"id": "exam", "label": "考试", "fields": ["exam_batch_id"]}],
                    "measures": [],
                }
            },
        }
    )
    bundle = authoring_bundle(mdl, "postgres", "catalog-closure-test")
    registry = client.app.state.registry
    previous = registry.bundles
    try:
        registry.register(bundle)
        response = client.get(
            "/internal/v1/bundles/catalog-closure-test/semantic-catalog?objects=student_subject_score",
            headers=auth,
        )
        assert response.status_code == 200
        assert {s["object"] for s in response.json()["sources"]} == {
            "student_subject_score",
            "exam_directory",
        }
    finally:
        registry.bundles = previous
