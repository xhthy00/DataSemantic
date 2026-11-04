from pathlib import Path

import pytest

from wren_semantic.registry import Registry
from wren_semantic.worker import ensure_read_query, run

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("dialect", ["postgres", "mysql", "duckdb"])
def test_declared_dialects_use_real_sdk(dialect):
    bundle = Registry(ROOT / "models/registry.json", 4_194_304).get("education-demo-v1")
    job = {
        "operation": "validate",
        "manifest": bundle.encoded_manifest,
        "dialect": dialect,
        "names": bundle.queryable_names,
    }
    assert run(job)["ok"]
    result = run(
        {**job, "operation": "plan", "sql": "SELECT AVG(valid_score) FROM student_subject_score"}
    )
    assert result["ok"], result
    ensure_read_query(result["physical_sql"], dialect)
