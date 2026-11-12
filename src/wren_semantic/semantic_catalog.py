"""Publication-bound v2 semantics. This file is wire-identical on the producer.

Dimensions describe identities; measures describe computations; capabilities are
optional implementations. None of these infer required inputs from result grain.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidateSource(StrictModel):
    object: str
    fields: list[str] = Field(min_length=1)
    labels: list[str] = Field(default_factory=list)
    order_field: str | None = None


class Dimension(StrictModel):
    id: str
    label: str
    fields: list[str] = Field(min_length=1)
    labels: list[str] = Field(default_factory=list)
    description: str = ""
    parents: list[str] = Field(default_factory=list)
    identity_scope: Literal["global", "parent", "period"] = "global"
    order_field: str | None = None
    # Only reviewed equivalence mappings can migrate old confirmed identities.
    candidate_source: CandidateSource | None = None
    legacy_entities: list[str] = Field(default_factory=list)


class Measure(StrictModel):
    id: str
    label: str
    field: str
    description: str
    operation: Literal[
        "identity", "sum", "avg", "min", "max", "count", "count_distinct", "weighted_mean"
    ] = "identity"
    weight_field: str | None = None
    required_dimensions: list[str] = Field(default_factory=list)
    population: str = Field(min_length=1)

    @model_validator(mode="after")
    def weighted(self):
        if (self.operation == "weighted_mean") != (self.weight_field is not None):
            raise ValueError("Only weighted_mean requires weight_field")
        return self


class Capability(StrictModel):
    id: str
    measures: list[str] = Field(min_length=1)
    operations: list[Literal["project", "aggregate", "rank"]] = Field(default_factory=list)
    population: str
    # A precomputed rank can only be reused for this exact partition and pool.
    rank_field: str | None = None
    rank_measure: str | None = None
    rank_partition: list[str] = Field(default_factory=list)
    rank_direction: Literal["asc", "desc"] = "desc"


class Source(StrictModel):
    schema_version: Literal[2] = 2
    object: str
    description: str = ""
    columns: list[str] = Field(min_length=1)
    grain: list[str] = Field(min_length=1)
    dimensions: list[Dimension]
    measures: list[Measure]
    capabilities: list[Capability] = Field(default_factory=list)

    @model_validator(mode="after")
    def references(self):
        dimensions = {d.id: d for d in self.dimensions}
        measures = {m.id: m for m in self.measures}
        if len(dimensions) != len(self.dimensions) or len(measures) != len(self.measures):
            raise ValueError("Duplicate semantic identity within source")
        if len(set(self.columns)) != len(self.columns) or len(set(self.grain)) != len(self.grain):
            raise ValueError("Duplicate output field or grain")
        refs = set()
        for d in self.dimensions:
            if d.candidate_source and len(d.candidate_source.fields) != len(d.fields):
                raise ValueError("Candidate identity arity mismatch")
            refs.update([*d.fields, *d.labels, *([d.order_field] if d.order_field else [])])
            if set(d.parents) - dimensions.keys():
                raise ValueError(f"Unknown dimension parent: {d.id}")
        visiting, visited = set(), set()

        def visit(key):
            if key in visiting:
                raise ValueError("Dimension parent cycle")
            if key not in visited:
                visiting.add(key)
                for parent in dimensions[key].parents:
                    visit(parent)
                visiting.remove(key)
                visited.add(key)

        for key in dimensions:
            visit(key)
        if set(self.grain) - dimensions.keys():
            raise ValueError("Grain must reference declared dimensions")
        for m in self.measures:
            refs.add(m.field)
            if m.weight_field:
                refs.add(m.weight_field)
            if set(m.required_dimensions) - dimensions.keys():
                raise ValueError(f"Unknown required dimension: {m.id}")
        for c in self.capabilities:
            if set(c.measures) - measures.keys() or set(c.rank_partition) - dimensions.keys():
                raise ValueError(f"Unknown capability reference: {c.id}")
            if any(measures[key].population != c.population for key in c.measures):
                raise ValueError("Capability population mismatch")
            if c.rank_field:
                refs.add(c.rank_field)
                if c.rank_measure not in c.measures:
                    raise ValueError("Precomputed rank requires a declared measure")
        if refs - set(self.columns):
            raise ValueError(f"Unknown output fields: {sorted(refs - set(self.columns))}")
        return self


class SemanticCatalog(StrictModel):
    schema_version: Literal[2] = 2
    bundle_id: str
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    sources: list[Source] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_sources(self):
        if len({s.object for s in self.sources}) != len(self.sources):
            raise ValueError("Duplicate logical source")
        objects = {s.object: s for s in self.sources}
        for source in self.sources:
            for dimension in source.dimensions:
                lookup = dimension.candidate_source
                if lookup:
                    if lookup.object not in objects:
                        raise ValueError("Candidate source is not declared in this publication")
                    fields = [
                        *lookup.fields,
                        *lookup.labels,
                        *([lookup.order_field] if lookup.order_field else []),
                    ]
                    if set(fields) - set(objects[lookup.object].columns):
                        raise ValueError("Unknown candidate source output fields")
        definitions = {}
        for source in self.sources:
            for d in source.dimensions:
                meaning = (d.label, d.description, tuple(d.parents), d.identity_scope)
                if d.id in definitions and definitions[d.id] != meaning:
                    raise ValueError(f"Conflicting dimension definition: {d.id}")
                definitions[d.id] = meaning
            for m in source.measures:
                # Operation/field can differ in a reviewed materialization;
                # semantics and population may not.
                meaning = (m.label, m.description, m.population, tuple(m.required_dimensions))
                key = ("measure", m.id)
                if key in definitions and definitions[key] != meaning:
                    raise ValueError(f"Conflicting measure definition: {m.id}")
                definitions[key] = meaning
        return self

    def binding(self):
        return self.model_dump(include={"bundle_id", "manifest_hash"})


def catalog_from_manifest(manifest: dict, binding: dict, output_columns: dict | None = None):
    """No field-name heuristics or inferred formulas."""
    sources = []
    for obj in [*manifest.get("models", []), *manifest.get("views", [])]:
        raw = (obj.get("properties") or {}).get("semanticModel")
        if raw is None:
            continue
        if raw.get("object") != obj["name"]:
            raise ValueError("Semantic source identity mismatch")
        source = Source.model_validate(raw)
        actual = (output_columns or {}).get(obj["name"])
        if actual is None and "columns" in obj:
            actual = [c["name"] for c in obj["columns"]]
        if actual is not None and set(source.columns) - set(actual):
            raise ValueError(f"Semantic fields not in SDK output: {obj['name']}")
        sources.append(source)
    return SemanticCatalog(**binding, sources=sources)


def semantic_issues(manifest, output_columns=None, *, require_outputs=False):
    try:
        if require_outputs:
            for obj in manifest.get("views", []):
                if (obj.get("properties") or {}).get("semanticModel") and obj["name"] not in (
                    output_columns or {}
                ):
                    raise ValueError(f"Missing SDK output schema: {obj['name']}")
        catalog_from_manifest(
            manifest, {"bundle_id": "validation", "manifest_hash": "0" * 64}, output_columns
        )
        return []
    except (ValueError, TypeError, KeyError) as exc:
        return [{"path": "properties.semanticModel", "message": str(exc)}]
