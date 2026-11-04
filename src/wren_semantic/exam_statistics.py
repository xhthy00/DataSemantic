"""Focused MDL for the school/subject statistics confirmed by the model owner."""

from copy import deepcopy

from .modeling import structural_issues

DETAIL_VIEW = """
SELECT s.score_id, s.student_id, b.exam_batch_id, b.exam_name, b.exam_date,
       p.paper_id, p.subject, s.school_id,
       COALESCE(NULLIF(c.school_name, ''), s.school_id) AS school_name,
       c.district, CAST(p.full_score AS DECIMAL(18, 4)) AS full_score,
       CAST(p.full_score AS DECIMAL(18, 4)) * 0.6 AS pass_score,
       CAST(s.score AS DECIMAL(18, 4)) AS valid_score,
       CASE WHEN s.score IS NULL OR p.full_score IS NULL
                   OR CAST(p.full_score AS DECIMAL(18, 4)) <= 0 THEN NULL
            WHEN CAST(s.score AS DECIMAL(18, 4)) >= CAST(p.full_score AS DECIMAL(18, 4)) * 0.6
            THEN 1 ELSE 0 END AS pass_flag
FROM exam_scores s
LEFT JOIN exam_papers p ON s.paper_id = p.paper_id
LEFT JOIN exam_batches b ON p.exam_batch_id = b.exam_batch_id
LEFT JOIN schools c ON s.school_id = c.school_id
""".strip()

SUMMARY_VIEW = """
SELECT exam_batch_id, exam_name, exam_date, school_id, school_name, district, subject,
       MIN(full_score) AS min_full_score, MAX(full_score) AS max_full_score,
       MIN(pass_score) AS min_pass_score, MAX(pass_score) AS max_pass_score,
       COUNT(*) AS recorded_count, COUNT(valid_score) AS valid_count,
       COUNT(*) - COUNT(valid_score) AS missing_score_count,
       SUM(valid_score) AS total_valid_score,
       ROUND(AVG(valid_score), 2) AS average_score,
       COALESCE(SUM(pass_flag), 0) AS pass_count,
       COUNT(pass_flag) AS pass_rate_denominator,
       COUNT(valid_score) - COUNT(pass_flag) AS unclassified_score_count,
       ROUND(100.0 * SUM(pass_flag) / NULLIF(COUNT(pass_flag), 0), 2) AS pass_rate
FROM exam_score_results
GROUP BY exam_batch_id, exam_name, exam_date, school_id, school_name, district, subject
""".strip().replace(
    "FROM exam_score_results",
    f"FROM (\n{DETAIL_VIEW}\n) AS exam_score_results",
)


def statistics_manifest(source):
    """Do not mutate the imported raw model. Expose only fields needed for this analysis."""
    originals = {m["name"]: m for m in source["models"]}
    specifications = [
        (
            "tb_score",
            "exam_scores",
            "学生科目成绩",
            "score_id",
            {
                "id": "score_id",
                "exam_id": "paper_id",
                "student_id": "student_id",
                "school_id": "school_id",
                "score": "score",
            },
        ),
        (
            "tb_exam",
            "exam_papers",
            "科目试卷",
            "paper_id",
            {
                "id": "paper_id",
                "exam_name": "paper_name",
                "subject": "subject",
                "exam_score": "full_score",
                "exam_batch_id": "exam_batch_id",
            },
        ),
        (
            "tb_exam_batch",
            "exam_batches",
            "考试批次",
            "exam_batch_id",
            {
                "id": "exam_batch_id",
                "batch_name": "exam_name",
                "exam_time": "exam_date",
            },
        ),
        (
            "tb_school",
            "schools",
            "学校",
            "school_id",
            {
                "id": "school_id",
                "s_name": "school_name",
                "district": "district",
            },
        ),
    ]
    manifest = {
        "catalog": source["catalog"],
        "schema": source["schema"],
        "models": [],
        "relationships": [],
        "views": [],
    }
    for original, name, display, pk, mapping in specifications:
        if original not in originals:
            raise ValueError(f"缺少必要模型：{original}")
        src = originals[original]
        columns = {c["name"]: c for c in src["columns"]}
        missing = mapping.keys() - columns.keys()
        if missing:
            raise ValueError(f"{original} 缺少必要字段：{', '.join(sorted(missing))}")
        model = {key: deepcopy(src[key]) for key in ("tableReference", "refSql") if key in src}
        model.update(
            {
                "name": name,
                "primaryKey": pk,
                "columns": [],
                "properties": {
                    "displayName": display,
                    "description": src.get("properties", {}).get("description", ""),
                },
            }
        )
        for old, new in mapping.items():
            col = deepcopy(columns[old])
            col["name"] = new
            col["expression"] = columns[old].get("expression") or f'"{old}"'
            model["columns"].append(col)
        manifest["models"].append(model)
    relations = [
        ("exam_scores", "schools", "school_id", "school_id", "school"),
        ("exam_scores", "exam_papers", "paper_id", "paper_id", "paper"),
        ("exam_papers", "exam_batches", "exam_batch_id", "exam_batch_id", "exam_batch"),
    ]
    models = {m["name"]: m for m in manifest["models"]}
    for left, right, left_key, right_key, nav in relations:
        name = f"{left}_{right}"
        manifest["relationships"].append(
            {
                "name": name,
                "models": [left, right],
                "joinType": "MANY_TO_ONE",
                "condition": f'"{left}"."{left_key}" = "{right}"."{right_key}"',
            }
        )
        models[left]["columns"].append({"name": nav, "type": right, "relationship": name})
    manifest["views"] = [
        {
            "name": "exam_score_results",
            "statement": DETAIL_VIEW,
            "properties": {
                "displayName": "考试科目成绩明细",
                "description": "一行一条学生试卷成绩。以成绩记录上的学校为准，"
                "学校名称使用明文 s_name。"
                "试卷满分取试卷表；空成绩不参与，正常零分保留，及格线为试卷满分的60%。",
            },
        },
        {
            "name": "exam_school_subject_summary",
            "statement": SUMMARY_VIEW,
            "properties": {
                "displayName": "学校科目均分与及格率",
                "description": "一行=考试批次×学校编号×科目。average_score为有效成绩平均分；"
                "pass_rate为及格人数/可判定有效成绩人数×100，单位为百分数0—100。"
                "无有效成绩时均分与及格率为空；满分缺失时不猜测及格结果，"
                "以unclassified_score_count提示。不同学校的率不能直接求平均；"
                "缺考未生成成绩记录时无法据此统计缺考人数。重复学生科目成绩须先核查。",
            },
        },
    ]
    issues = structural_issues(manifest)
    if issues:
        raise ValueError(issues)
    return manifest


def statistics_query(batch_id):
    if not isinstance(batch_id, int) or isinstance(batch_id, bool) or batch_id < 1:
        raise ValueError("考试批次编号必须为正整数。")
    return (
        "SELECT exam_batch_id, exam_name, exam_date, school_id, school_name, district, subject, "
        "min_full_score, max_full_score, min_pass_score, max_pass_score, "
        "recorded_count, valid_count, missing_score_count, total_valid_score, average_score, "
        "pass_count, pass_rate_denominator, unclassified_score_count, pass_rate "
        f"FROM exam_school_subject_summary WHERE exam_batch_id = {batch_id} "
        "ORDER BY school_name, subject"
    )
