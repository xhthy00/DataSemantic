import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .errors import ServiceError

Dialect = Literal["postgres", "mysql", "duckdb"]


class BundleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundle_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    dialect: Dialect
    manifest_path: str
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RegistryFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundles: list[BundleEntry] = Field(min_length=1, max_length=100)


def _description(obj: dict) -> str:
    properties = obj.get("properties") or {}
    return str(properties.get("description") or "")


@dataclass(frozen=True)
class Bundle:
    entry: BundleEntry
    encoded_manifest: str
    context: dict
    queryable_names: tuple[str, ...]

    def summary(self) -> dict:
        return {
            "bundle_id": self.entry.bundle_id,
            "manifest_hash": self.entry.manifest_hash,
            "dialect": self.entry.dialect,
        }


class Registry:
    """Immutable startup snapshot. No request-controlled paths or manifests."""

    def __init__(self, path: Path, max_manifest_bytes: int):
        root = path.resolve().parent
        config = RegistryFile.model_validate_json(path.read_bytes())
        self.bundles: dict[str, Bundle] = {}
        for entry in config.bundles:
            if entry.bundle_id in self.bundles:
                raise ValueError(f"Duplicate bundle: {entry.bundle_id}")
            source = (root / entry.manifest_path).resolve()
            if not source.is_relative_to(root):
                raise ValueError("Manifest must remain inside the registry directory")
            with source.open("rb") as stream:
                raw = stream.read(max_manifest_bytes + 1)
            if len(raw) > max_manifest_bytes:
                raise ValueError("Manifest exceeds configured size limit")
            if hashlib.sha256(raw).hexdigest() != entry.manifest_hash:
                raise ValueError(f"Manifest hash mismatch: {entry.bundle_id}")
            self.bundles[entry.bundle_id] = bundle_from_bytes(entry, raw)

    def register(self, bundle: Bundle) -> None:
        if bundle.entry.bundle_id in self.bundles:
            raise ServiceError("BUNDLE_EXISTS", "发布物 ID 已存在，请使用新的版本 ID。", 409)
        self.bundles = {**self.bundles, bundle.entry.bundle_id: bundle}

    def get(self, bundle_id: str) -> Bundle:
        try:
            return self.bundles[bundle_id]
        except KeyError:
            raise ServiceError("BUNDLE_NOT_FOUND", "Unknown published bundle", 404) from None


def bundle_from_bytes(entry: BundleEntry, raw: bytes) -> Bundle:
    if hashlib.sha256(raw).hexdigest() != entry.manifest_hash:
        raise ValueError(f"Manifest hash mismatch: {entry.bundle_id}")
    mdl = json.loads(raw)
    models, views = mdl.get("models", []), mdl.get("views", [])
    names = tuple(obj["name"] for obj in [*models, *views])
    if not models or len(set(names)) != len(names):
        raise ValueError("A bundle requires models with unique model/view names")
    context = {
        "models": [
            {
                "name": model["name"],
                "description": _description(model),
                "primary_key": model.get("primaryKey"),
                "columns": [
                    {
                        "name": col["name"],
                        "type": col.get("type"),
                        "description": _description(col),
                        "relationship": col.get("relationship"),
                        "is_calculated": col.get("isCalculated", False),
                    }
                    for col in model.get("columns", [])
                ],
            }
            for model in models
        ],
        "relationships": mdl.get("relationships", []),
        "views": [{"name": view["name"], "description": _description(view)} for view in views],
    }
    return Bundle(entry, base64.b64encode(raw).decode("ascii"), context, names)
