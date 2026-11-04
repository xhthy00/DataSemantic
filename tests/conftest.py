from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wren_semantic.app import create_app
from wren_semantic.config import Settings

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "test-only-token-" + "a" * 40


@pytest.fixture(scope="session")
def client():
    settings = Settings(service_token=TOKEN, registry_path=ROOT / "models/registry.json")
    with TestClient(create_app(settings)) as instance:
        yield instance


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def plan_body(client, auth):
    bundle = client.get("/internal/v1/bundles", headers=auth).json()["bundles"][0]
    return {
        "bundle_id": bundle["bundle_id"],
        "manifest_hash": bundle["manifest_hash"],
        "semantic_sql": (
            "SELECT AVG(valid_score) AS average_score, COUNT(valid_score) AS valid_count "
            "FROM student_subject_score WHERE exam_batch_id = 'exam_demo'"
        ),
    }
