import json
from pathlib import Path

import pytest

from wren_semantic.registry import Registry

ROOT = Path(__file__).resolve().parents[1]


def test_rejects_modified_manifest_and_path_escape(tmp_path):
    entry = json.loads((ROOT / "models/registry.json").read_text())["bundles"][0]
    (tmp_path / "mdl.json").write_text('{"models": []}')
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"bundles": [{**entry, "manifest_path": "mdl.json"}]}))
    with pytest.raises(ValueError, match="hash mismatch"):
        Registry(path, 4096)
    path.write_text(json.dumps({"bundles": [{**entry, "manifest_path": "../outside.json"}]}))
    with pytest.raises(ValueError, match="inside"):
        Registry(path, 4096)


def test_rejects_oversized_manifest(tmp_path):
    entry = json.loads((ROOT / "models/registry.json").read_text())["bundles"][0]
    (tmp_path / "mdl.json").write_bytes(b" " * 2048)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"bundles": [{**entry, "manifest_path": "mdl.json"}]}))
    with pytest.raises(ValueError, match="size limit"):
        Registry(path, 1024)
