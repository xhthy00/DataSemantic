from copy import deepcopy

import duckdb
import pytest

from wren_semantic.exam_statistics import statistics_manifest, statistics_query
from wren_semantic.modeling import authoring_bundle, structural_issues
from wren_semantic.worker import run


def source_manifest():
    tables = {
        "tb_score": ["id", "exam_id", "student_id", "school_id", "score"],
        "tb_exam": ["id", "exam_name", "subject", "exam_score", "exam_batch_id"],
        "tb_exam_batch": ["id", "batch_name", "exam_time"],
        "tb_school": ["id", "s_name", "district"],
    }
    models = []
    for name, fields in tables.items():
        cols = []
        for field in fields:
            kind = "varchar"
            if field in {"score", "exam_score"}:
                kind = "decimal(4, 1)"
            elif field in {"exam_id", "exam_batch_id"} or (field == "id" and name != "tb_school"):
                kind = "integer"
            elif field == "exam_time":
                kind = "date"
            cols.append({"name": field, "type": kind, "expression": f'"{field}"'})
        models.append(
            {
                "name": name,
                "tableReference": {"schema": "public", "table": name},
                "primaryKey": "id",
                "columns": cols,
            }
        )
    return {
        "catalog": "wren",
        "schema": "public",
        "models": models,
        "relationships": [],
        "views": [],
    }


def test_focused_model_preserves_source_and_business_mapping():
    src = source_manifest()
    before = deepcopy(src)
    mdl = statistics_manifest(src)
    assert src == before
    assert len(mdl["models"]) == 4 and len(mdl["relationships"]) == 3
    assert len(mdl["views"]) == 2
    assert not structural_issues(mdl)
    schools = next(m for m in mdl["models"] if m["name"] == "schools")
    name = next(c for c in schools["columns"] if c["name"] == "school_name")
    assert name["expression"] == '"s_name"'
    assert "0.6" in mdl["views"][0]["statement"]
    with pytest.raises(ValueError):
        statistics_manifest({**src, "models": []})


def test_real_sdk_and_numeric_boundaries_with_known_records():
    mdl = statistics_manifest(source_manifest())
    bundle = authoring_bundle(mdl, "postgres")
    job = {
        "manifest": bundle.encoded_manifest,
        "dialect": "postgres",
        "names": list(bundle.queryable_names),
        "diagnostics": True,
    }
    assert run({**job, "operation": "validate"})["ok"]
    planned = run({**job, "operation": "plan", "sql": statistics_query(2)})
    assert planned["ok"], planned
    # Execute the matching dialect: PostgreSQL's unbounded DECIMAL casts would
    # acquire DuckDB's default scale of 3 if its SQL were executed unchanged here.
    duck_bundle = authoring_bundle(mdl, "duckdb")
    executable = run(
        {
            **job,
            "manifest": duck_bundle.encoded_manifest,
            "dialect": "duckdb",
            "operation": "plan",
            "sql": statistics_query(2),
        }
    )
    assert executable["ok"], executable
    with duckdb.connect() as db:
        db.execute("CREATE SCHEMA public")
        db.execute("CREATE TABLE public.tb_school(id VARCHAR,s_name VARCHAR,district VARCHAR)")
        db.execute(
            "INSERT INTO public.tb_school VALUES ('A','同名学校','东区'),"
            "('B','同名学校','西区'),('C','精度测试学校','北区')"
        )
        db.execute("CREATE TABLE public.tb_exam_batch(id INT,batch_name VARCHAR,exam_time DATE)")
        db.execute(
            "INSERT INTO public.tb_exam_batch VALUES (2,'目标考试','2026-01-10'),"
            "(3,'另一场考试','2026-02-01')"
        )
        db.execute(
            "CREATE TABLE public.tb_exam(id INT,exam_name VARCHAR,subject VARCHAR,"
            "exam_score DECIMAL(4,1),exam_batch_id INT)"
        )
        db.execute(
            "INSERT INTO public.tb_exam VALUES (101,'数学卷','数学',150,2),"
            "(102,'物理卷','物理',100,2),(103,'缺少满分','化学',NULL,2),"
            "(104,'精度卷','地理',100,2),(201,'其他考试','数学',150,3)"
        )
        db.execute(
            "CREATE TABLE public.tb_score(id INT,exam_id INT,student_id VARCHAR,"
            "school_id VARCHAR,score DECIMAL(4,1))"
        )
        db.execute(
            "INSERT INTO public.tb_score VALUES (1,101,'s1','A',90),(2,101,'s2','A',0),"
            "(3,101,'s3','A',150),(4,101,'s4','A',NULL),(5,102,'s1','A',60),"
            "(6,102,'s2','A',59),(7,101,'s5','B',NULL),(8,103,'s1','A',80),(9,201,'s1','A',149)"
        )
        db.execute(
            "INSERT INTO public.tb_score SELECT 1000+i,104,'r'||i,'C',"
            "CASE WHEN i=372 THEN 81.0 ELSE 60.5 END FROM range(373) AS t(i)"
        )
        cursor = db.execute(executable["physical_sql"])
        names = [c[0] for c in cursor.description]
        rows = [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]
    assert len(rows) == 5
    results = {(r["school_id"], r["subject"]): r for r in rows}
    math = results["A", "数学"]
    assert math["valid_count"] == 3 and math["missing_score_count"] == 1
    assert math["average_score"] == 80 and math["pass_count"] == 2
    assert float(math["pass_rate"]) == 66.67
    assert math["min_pass_score"] == 90
    physics = results["A", "物理"]
    assert float(physics["average_score"]) == 59.5 and physics["pass_rate"] == 50
    absent = results["B", "数学"]
    assert absent["valid_count"] == 0 and absent["pass_count"] == 0
    assert absent["average_score"] is None and absent["pass_rate"] is None
    unknown = results["A", "化学"]
    assert unknown["valid_count"] == 1 and unknown["average_score"] == 80
    assert unknown["unclassified_score_count"] == 1 and unknown["pass_rate"] is None
    # Do not round the mean to four decimals and then round again to two decimals.
    assert float(results["C", "地理"]["average_score"]) == 60.55, results["C", "地理"]


@pytest.mark.parametrize("value", [True, 0, -1, "2; DROP TABLE x", None])
def test_exam_filter_is_explicit_positive_id(value):
    with pytest.raises(ValueError):
        statistics_query(value)
