"""Exercise the running demo service over HTTP without executing a database query."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
base = os.getenv("WREN_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
token = os.environ["WREN_SERVICE_TOKEN"]


def call(path, body=None, *, auth=True):
    headers = {"Authorization": f"Bearer {token}"} if auth else {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


status, result = call("/health/ready", auth=False)
assert status == 200 and result["status"] == "ready", (status, result)
assert call("/internal/v1/bundles", auth=False)[0] == 401
status, schema = call("/internal/v1/openapi.json")
assert status == 200 and "HTTPBearer" in schema["components"]["securitySchemes"]
status, result = call("/internal/v1/bundles")
assert status == 200, (status, result)
bundle = next(item for item in result["bundles"] if item["bundle_id"] == "education-demo-v1")
body = {
    "bundle_id": bundle["bundle_id"],
    "manifest_hash": bundle["manifest_hash"],
    "semantic_sql": (
        "SELECT AVG(valid_score) AS average_score, COUNT(valid_score) AS valid_count "
        "FROM student_subject_score WHERE exam_batch_id = 'exam_demo'"
    ),
}
status, result = call("/internal/v1/plan", body)
assert status == 200 and "physical_sql" in result, (status, result)
assert "edu_analysis" in result["physical_sql"]
assert call("/internal/v1/plan", {**body, "manifest_hash": "0" * 64})[0] == 409
assert (
    call("/internal/v1/plan", {**body, "semantic_sql": "DROP TABLE student_subject_score"})[0]
    == 422
)
assert (
    call("/internal/v1/plan", {**body, "semantic_sql": "SELECT AVG( FROM student_subject_score"})[0]
    == 422
)
print(
    json.dumps(
        {
            "status": "passed",
            "bundle_id": body["bundle_id"],
            "wrenai_version": result["wrenai_version"],
            "duration_ms": result["duration_ms"],
        }
    )
)
