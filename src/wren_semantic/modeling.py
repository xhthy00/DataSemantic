"""Authoring checks around MDL. Native SDK planning remains the final structural check."""

import base64
import hashlib
import json
import re

from .errors import ServiceError
from .registry import Bundle, BundleEntry, bundle_from_bytes

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def manifest_bytes(manifest: dict) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def structural_issues(manifest: dict) -> list[dict]:
    issues = []

    def issue(path, message):
        issues.append({"path": path, "message": message})

    def name(value, path):
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            issue(path, "请使用字母或下划线开头的逻辑标识符，仅包含字母、数字和下划线。")

    def properties(value, path):
        if "properties" in value and not isinstance(value["properties"], dict):
            issue(path + ".properties", "properties 必须为对象。")

    for key in ("catalog", "schema"):
        name(manifest.get(key), key)
    models = manifest.get("models")
    if not isinstance(models, list) or not 1 <= len(models) <= 50:
        issue("models", "需要 1～50 个逻辑模型。")
        return issues
    views = manifest.get("views", [])
    relationships = manifest.get("relationships", [])
    if not isinstance(views, list) or not isinstance(relationships, list):
        issue("manifest", "views 和 relationships 必须为数组。")
        return issues
    model_names = [m.get("name") for m in models if isinstance(m, dict)]
    known = {n for n in model_names if isinstance(n, str)}
    names = set()
    for index, model in enumerate(models):
        path = f"models[{index}]"
        if not isinstance(model, dict):
            issue(path, "模型必须是对象。")
            continue
        properties(model, path)
        model_name = model.get("name")
        name(model_name, path + ".name")
        if isinstance(model_name, str):
            if model_name in names:
                issue(path + ".name", "逻辑模型名称重复。")
            names.add(model_name)
        source = model.get("tableReference")
        if not isinstance(source, dict) and not model.get("refSql"):
            issue(path, "请设置物理表 tableReference 或只读 refSql。")
        elif isinstance(source, dict):
            if not isinstance(source.get("table"), str) or not source["table"].strip():
                issue(path + ".tableReference.table", "请填写物理表或视图名称。")
        columns = model.get("columns")
        if not isinstance(columns, list) or not 1 <= len(columns) <= 500:
            issue(path + ".columns", "模型需要 1～500 个字段。")
            continue
        column_names = set()
        for ci, column in enumerate(columns):
            cp = f"{path}.columns[{ci}]"
            if not isinstance(column, dict):
                issue(cp, "字段必须是对象。")
                continue
            properties(column, cp)
            cn = column.get("name")
            name(cn, cp + ".name")
            if isinstance(cn, str):
                if cn in column_names:
                    issue(cp + ".name", "字段名称重复。")
                column_names.add(cn)
            if not isinstance(column.get("type"), str) or not column["type"].strip():
                issue(cp + ".type", "请填写字段类型。")
            if column.get("isCalculated") and not str(column.get("expression") or "").strip():
                issue(cp + ".expression", "计算字段需要表达式。")
        if model.get("primaryKey") and (
            not isinstance(model["primaryKey"], str) or model["primaryKey"] not in column_names
        ):
            issue(path + ".primaryKey", "主键必须引用模型中已存在的字段。")
    relation_names = set()
    for index, relation in enumerate(relationships):
        path = f"relationships[{index}]"
        if not isinstance(relation, dict):
            issue(path, "关联必须是对象。")
            continue
        rn = relation.get("name")
        name(rn, path + ".name")
        if isinstance(rn, str):
            if rn in relation_names:
                issue(path + ".name", "关联名称重复。")
            relation_names.add(rn)
        pair = relation.get("models")
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or any(not isinstance(m, str) or m not in known for m in pair)
        ):
            issue(path + ".models", "关联必须引用两个已存在的逻辑模型。")
        if not isinstance(relation.get("joinType"), str) or relation["joinType"] not in {
            "ONE_TO_ONE",
            "ONE_TO_MANY",
            "MANY_TO_ONE",
            "MANY_TO_MANY",
        }:
            issue(path + ".joinType", "请选择合法的关联基数。")
        if not isinstance(relation.get("condition"), str) or not relation["condition"].strip():
            issue(path + ".condition", "请填写关联条件。")
    for index, model in enumerate(models):
        if not isinstance(model, dict) or not isinstance(model.get("columns"), list):
            continue
        for ci, column in enumerate(model["columns"]):
            if isinstance(column, dict) and column.get("relationship"):
                if (
                    not isinstance(column["relationship"], str)
                    or column["relationship"] not in relation_names
                ):
                    issue(
                        f"models[{index}].columns[{ci}].relationship",
                        "导航字段引用了不存在的关联。",
                    )
    for index, view in enumerate(views):
        if not isinstance(view, dict):
            issue(f"views[{index}]", "视图必须是对象。")
            continue
        properties(view, f"views[{index}]")
        vn = view.get("name")
        name(vn, f"views[{index}].name")
        if isinstance(vn, str):
            if vn in names:
                issue(f"views[{index}].name", "模型与视图名称必须唯一。")
            names.add(vn)
        if not isinstance(view.get("statement"), str) or not view["statement"].strip():
            issue(f"views[{index}].statement", "视图需要只读语义 SQL。")
    return issues[:100]


def authoring_bundle(manifest: dict, dialect: str, bundle_id: str = "draft") -> Bundle:
    issues = structural_issues(manifest)
    if issues:
        error = ServiceError("INVALID_MDL", "模型结构需要修正。", 422)
        error.issues = issues
        raise error
    raw = manifest_bytes(manifest)
    entry = BundleEntry(
        bundle_id=bundle_id,
        dialect=dialect,
        manifest_path=f"{bundle_id}/mdl.json",
        manifest_hash=hashlib.sha256(raw).hexdigest(),
    )
    return bundle_from_bytes(entry, raw)


def copy_manifest(bundle: Bundle) -> dict:
    return json.loads(base64.b64decode(bundle.encoded_manifest))


def template_manifest(base: dict) -> dict:
    manifest = json.loads(json.dumps(base))
    manifest["models"].append(
        {
            "name": "schools",
            "tableReference": {"schema": "edu_analysis", "table": "dim_school"},
            "primaryKey": "id",
            "properties": {"displayName": "学校", "description": "学校维度，一行一所学校。"},
            "columns": [
                {"name": "id", "type": "varchar", "properties": {"description": "学校 ID"}},
                {"name": "name", "type": "varchar", "properties": {"description": "学校名称"}},
            ],
        }
    )
    manifest["relationships"].append(
        {
            "name": "score_school",
            "models": ["student_subject_score", "schools"],
            "joinType": "MANY_TO_ONE",
            "condition": "student_subject_score.school_id = schools.id",
        }
    )
    manifest["models"][0]["properties"]["displayName"] = "学生科目成绩"
    manifest["models"][0]["columns"].append(
        {
            "name": "school",
            "type": "schools",
            "relationship": "score_school",
            "properties": {"description": "通过 school_id 关联学校维度"},
        }
    )
    manifest["models"][0]["columns"].append(
        {
            "name": "school_name",
            "type": "varchar",
            "isCalculated": True,
            "expression": "school.name",
            "properties": {"description": "通过学校关联取得学校名称，可直接用于查询与分组。"},
        }
    )
    return manifest
