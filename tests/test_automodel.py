from copy import deepcopy

import duckdb
import pytest
from test_studio import studio as studio
from test_studio import studio_settings as studio_settings

from wren_semantic.automodel import build_manifest, parse_ddl
from wren_semantic.errors import ServiceError
from wren_semantic.modeling import authoring_bundle, structural_issues
from wren_semantic.studio import AutoModelTable
from wren_semantic.worker import run

DDL = """
CREATE TABLE schools (id BIGINT PRIMARY KEY, name VARCHAR(100) NOT NULL);
CREATE TABLE students (
    id BIGINT PRIMARY KEY, school_id BIGINT NOT NULL,
    name VARCHAR(100), private_note TEXT,
    FOREIGN KEY (school_id) REFERENCES schools(id)
);
CREATE TABLE scores (
    student_id BIGINT, subject VARCHAR(50), score DECIMAL(5, 2),
    PRIMARY KEY (student_id, subject)
);
ALTER TABLE scores ADD CONSTRAINT scores_student_fk
FOREIGN KEY (student_id) REFERENCES students(id);
COMMENT ON TABLE schools IS '学校';
COMMENT ON COLUMN schools.name IS '学校名称';
"""


def all_tables(preview):
    return [
        AutoModelTable(table_id=t["id"], columns=[c["id"] for c in t["columns"]])
        for t in preview["tables"]
    ]


def generate(ddl=DDL, dialect="postgres"):
    preview = parse_ddl(ddl, dialect)
    return build_manifest(preview, all_tables(preview), "wren", "public")


def test_postgres_keys_comments_relations_and_business_rules():
    preview = parse_ddl(DDL, "postgres")
    schools, students, scores = preview["tables"]
    assert schools["description"] == "学校"
    assert schools["columns"][1]["description"] == "学校名称"
    assert not schools["columns"][0]["nullable"]
    assert students["foreign_keys"][0]["target_id"] == schools["id"]
    assert scores["foreign_keys"][0]["target_id"] == students["id"]
    manifest, warnings = generate()
    assert not structural_issues(manifest)
    assert manifest["models"][0]["primaryKey"] == "id"
    assert manifest["models"][0]["columns"][0]["notNull"]
    assert manifest["models"][0]["columns"][1]["notNull"]
    assert not manifest["models"][1]["columns"][2]["notNull"]
    assert "primaryKey" not in manifest["models"][2]
    assert any("复合主键" in w for w in warnings)
    assert len(manifest["relationships"]) == 2
    assert all(r["joinType"] == "MANY_TO_ONE" for r in manifest["relationships"])
    assert not any(c.get("isCalculated") for m in manifest["models"] for c in m["columns"])


@pytest.mark.parametrize("dialect", ["postgres", "mysql", "duckdb"])
def test_real_sdk_generated_mdl_and_query_result(dialect):
    mdl, _ = generate(DDL.split("COMMENT ON")[0], dialect)
    # A business field authored after generation must traverse the generated navigation.
    students = mdl["models"][1]
    students["columns"].append(
        {
            "name": "school_name",
            "type": "varchar",
            "isCalculated": True,
            "expression": "schools_ref.name",
        }
    )
    bundle = authoring_bundle(mdl, dialect)
    job = {
        "manifest": bundle.encoded_manifest,
        "dialect": dialect,
        "operation": "validate",
        "names": list(bundle.queryable_names),
        "diagnostics": True,
    }
    assert run(job)["ok"]
    result = run(
        {
            **job,
            "operation": "plan",
            "sql": "SELECT school_name, COUNT(*) AS n FROM students GROUP BY school_name",
        }
    )
    assert result["ok"], result
    if dialect == "duckdb":
        with duckdb.connect() as db:
            db.execute(
                "CREATE TABLE schools(id BIGINT, name VARCHAR); "
                "INSERT INTO schools VALUES (1, '学校A'), (2, '学校B')"
            )
            db.execute(
                "CREATE TABLE students(id BIGINT, school_id BIGINT, name VARCHAR, "
                "private_note VARCHAR); INSERT INTO students "
                "VALUES (1,1,'甲',''), (2,1,'乙',''), (3,2,'丙','')"
            )
            assert sorted(db.execute(result["physical_sql"]).fetchall()) == [
                ("学校A", 2),
                ("学校B", 1),
            ]


def test_mysql_unsigned_enum_inline_comments_and_unique_fk():
    ddl = """
    CREATE TABLE schools (id BIGINT UNSIGNED PRIMARY KEY,
        name VARCHAR(80) COMMENT '学校名称') COMMENT='学校表';
    CREATE TABLE details (id BIGINT UNSIGNED UNIQUE REFERENCES schools(id),
        status ENUM('active','off'), enabled TINYINT(1));
    """
    preview = parse_ddl(ddl, "mysql")
    assert preview["tables"][0]["description"] == "学校表"
    assert preview["tables"][0]["columns"][1]["description"] == "学校名称"
    mdl, warnings = build_manifest(preview, all_tables(preview), "wren", "public")
    assert mdl["models"][0]["columns"][0]["type"] == "decimal(20, 0)"
    assert mdl["models"][1]["columns"][1]["type"] == "varchar"
    assert mdl["models"][1]["columns"][2]["type"] == "tinyint"
    assert mdl["relationships"][0]["joinType"] == "ONE_TO_ONE"
    assert any("枚举" in w for w in warnings)


def test_selection_never_leaves_dangling_relationship_or_private_fields():
    preview = parse_ddl(DDL, "postgres")
    selection = all_tables(preview)
    selection[1].columns.remove("private_note")
    mdl, _ = build_manifest(preview, selection, "wren", "public")
    assert "private_note" not in str(mdl)
    selection[0].columns.remove("id")
    mdl, warnings = build_manifest(preview, selection, "wren", "public")
    assert len(mdl["relationships"]) == 1
    assert "primaryKey" not in mdl["models"][0]
    assert any("目标字段" in w for w in warnings)
    assert not structural_issues(mdl)
    mdl, _ = build_manifest(preview, selection[1:], "wren", "public", False)
    assert not mdl["relationships"]
    assert all(not c.get("relationship") for m in mdl["models"] for c in m["columns"])


def test_quoted_identifiers_namespaces_and_unknown_types():
    ddl = """CREATE TABLE a."School Info" ("学生 ID" BIGINT PRIMARY KEY, addr INET);
             CREATE TABLE b."School Info" (id BIGINT,
                parent BIGINT REFERENCES a."School Info"("学生 ID"));"""
    preview = parse_ddl(ddl, "postgres")
    assert preview["tables"][0]["logical_name"] != preview["tables"][1]["logical_name"]
    assert preview["tables"][1]["foreign_keys"][0]["target_id"] == "t1"
    selection = all_tables(preview)
    with pytest.raises(ServiceError, match="语义类型"):
        build_manifest(preview, selection, "wren", "public")
    selection[0].types["addr"] = "varchar"
    mdl, warnings = build_manifest(preview, selection, "wren", "public")
    assert mdl["models"][0]["tableReference"] == {"schema": "a", "table": "School Info"}
    assert mdl["models"][0]["columns"][0]["expression"] == '"学生 ID"'
    assert not structural_issues(mdl)
    assert warnings


@pytest.mark.parametrize(
    "ddl",
    [
        "",
        "SELECT 1",
        "INSERT INTO x VALUES(1)",
        "CREATE TABLE x AS SELECT 1",
        "CREATE TABLE x(id int); CREATE TABLE x(id int)",
        "CREATE TABLE x(id int, id int)",
        "CREATE TABLE x(id)",
        "CREATE TABLE x(id int); ALTER TABLE x ADD COLUMN name text",
        "CREATE TABLE x (id int",
        "CREATE TABLE x();",
        "CREATE VIEW x AS SELECT 1",
    ],
)
def test_rejects_non_schema_incomplete_or_ambiguous_ddl(ddl):
    with pytest.raises(ServiceError):
        parse_ddl(ddl, "postgres")


def test_limits_namespace_resolution_and_selection_integrity():
    with pytest.raises(ServiceError):
        parse_ddl(" " * 500001, "postgres")
    with pytest.raises(ServiceError):
        parse_ddl(";".join(f"CREATE TABLE t{i}(id int)" for i in range(51)), "postgres")
    p = parse_ddl(
        "CREATE TABLE a.t(id int); CREATE TABLE b.t(id int); "
        "CREATE TABLE b.s(id int REFERENCES t(id));",
        "postgres",
    )
    assert p["tables"][2]["foreign_keys"][0]["target_id"] == "t2"
    selected = all_tables(p)
    for bad in [
        [],
        [selected[0], selected[0]],
        [AutoModelTable(table_id="t8", columns=["id"])],
        [AutoModelTable(table_id="t1", columns=["nope"])],
    ]:
        with pytest.raises(ServiceError):
            build_manifest(p, bad, "wren", "public")
    with pytest.raises(ServiceError):
        build_manifest(p, selected, "bad.catalog", "public")


def test_self_and_omitted_fk_are_explained_not_guessed():
    mdl, warnings = generate(
        "CREATE TABLE staff(id int primary key, parent int REFERENCES staff(id), "
        "school_id int REFERENCES not_imported(id));"
    )
    assert not mdl["relationships"]
    assert len(warnings) == 2


def test_implicit_target_pk_and_alter_pk():
    mdl, warnings = generate(
        "CREATE TABLE schools(id int); ALTER TABLE schools ADD PRIMARY KEY(id); "
        "CREATE TABLE students(id int REFERENCES schools);"
    )
    assert not warnings
    assert mdl["models"][0]["primaryKey"] == "id"
    assert mdl["relationships"][0]["condition"] == '"students"."id" = "schools"."id"'
    with pytest.raises(ServiceError):
        generate("CREATE TABLE schools(id int, PRIMARY KEY(missing));")


def test_native_validation_failure_does_not_persist_draft(studio, monkeypatch):
    before = studio.get("/studio/api/drafts").json()
    preview = parse_ddl(DDL, "postgres")
    payload = {
        "ddl": DDL,
        "name": "不会保存的无效模型",
        "tables": [s.model_dump() for s in all_tables(preview)],
    }

    async def rejected(*args, **kwargs):
        raise ServiceError("PLANNING_FAILED", "SDK rejected this manifest", 422)

    monkeypatch.setattr(studio.app.state.planner, "run", rejected)
    response = studio.post("/studio/api/automodel/generate", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["issues"][0]["path"] == "Wren SDK"
    assert studio.get("/studio/api/drafts").json() == before


def test_automodel_api_preview_review_and_validated_creation(studio):
    before = studio.get("/studio/api/drafts").json()
    response = studio.post(
        "/studio/api/automodel/preview", json={"ddl": DDL, "dialect": "postgres"}
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    payload = {
        "ddl": DDL,
        "dialect": "postgres",
        "name": "自动学情模型",
        "tables": [s.model_dump() for s in all_tables(preview)],
    }
    payload["tables"][1]["columns"].remove("private_note")
    review = studio.post("/studio/api/automodel/review", json=payload)
    assert review.status_code == 200, review.text
    assert studio.get("/studio/api/drafts").json() == before
    created = studio.post("/studio/api/automodel/generate", json=payload)
    assert created.status_code == 201, created.text
    result = created.json()
    assert result["validation"]["valid"]
    assert result["draft"]["manifest"] == review.json()["manifest"]
    assert result["draft"]["revision"] == 1
    assert result["warnings"]
    d = result["draft"]
    assert studio.get(f"/studio/api/drafts/{d['id']}").json() == d
    assert len(studio.get("/studio/api/drafts").json()["drafts"]) == len(before["drafts"]) + 1
    bad = deepcopy(payload)
    bad["tables"][0]["types"] = {"id": "not_a_type"}
    assert studio.post("/studio/api/automodel/generate", json=bad).status_code == 422
    assert len(studio.get("/studio/api/drafts").json()["drafts"]) == len(before["drafts"]) + 1


def test_automodel_auth_and_csrf(studio):
    csrf = studio.headers.pop("X-Studio-CSRF")
    assert studio.post("/studio/api/automodel/preview", json={"ddl": DDL}).status_code == 403
    studio.headers["X-Studio-CSRF"] = csrf
    assert (
        studio.post(
            "/studio/api/automodel/preview",
            json={"ddl": DDL},
            headers={"Origin": "https://other.invalid"},
        ).status_code
        == 403
    )
    studio.post("/studio/api/logout")
    assert studio.post("/studio/api/automodel/preview", json={"ddl": DDL}).status_code == 401
