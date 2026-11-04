-- PostgreSQL只读检查模板：未在真实数据库执行。
-- 每段是一条独立查询，可逐条执行。返回异常组/异常数量不代表已自动修复。

-- 1. 查看真实主键、唯一约束与外键。空结果仅表示此筛选下未查到约束。
-- 唯一索引若未挂为constraint，不会出现在此查询中。
SELECT t.relname AS table_name,
       c.conname AS constraint_name,
       CASE c.contype WHEN 'p' THEN 'PRIMARY KEY'
                      WHEN 'u' THEN 'UNIQUE'
                      WHEN 'f' THEN 'FOREIGN KEY' END AS constraint_type,
       pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace ns ON ns.oid = t.relnamespace
WHERE ns.nspname = 'public'
  AND c.contype IN ('p', 'u', 'f')
  AND t.relname IN (
    'tb_school', 'tb_student', 'tb_exam_batch', 'tb_exam',
    'tb_score', 'tb_score_detail', 'tb_exam_question',
    'tb_exam_question_knowledge', 'tb_knowledge', 'tb_knowledge_version',
    'tb_score_overview', 'tb_fraction_bar', 'tb_score_indicator',
    'tb_score_contribution', 'tb_assign_band', 'tb_elite_class',
    'tb_exam_match_task', 'tb_exam_match_item'
  )
ORDER BY t.relname, c.contype, c.conname;

-- 2. 成绩(试卷,学生)是否重复。无结果表示当前非空键未发现重复。
SELECT exam_id, student_id, COUNT(*) AS duplicate_count
FROM public.tb_score
WHERE exam_id IS NOT NULL AND student_id IS NOT NULL
GROUP BY exam_id, student_id
HAVING COUNT(*) > 1;

-- 3. 小题(试卷,学生,题号)是否重复。
SELECT exam_id, student_id, question_no, COUNT(*) AS duplicate_count
FROM public.tb_score_detail
GROUP BY exam_id, student_id, question_no
HAVING COUNT(*) > 1;

-- 4. 总览(匿名学生,批次)是否重复。
SELECT anon_stu_id, exam_batch_id, COUNT(*) AS duplicate_count
FROM public.tb_score_overview
WHERE anon_stu_id IS NOT NULL AND exam_batch_id IS NOT NULL
GROUP BY anon_stu_id, exam_batch_id
HAVING COUNT(*) > 1;

-- 5. 题目(试卷,题号)是否唯一，决定能否用复合条件回退匹配题目。
SELECT exam_id, question_no, COUNT(*) AS duplicate_count
FROM public.tb_exam_question
GROUP BY exam_id, question_no
HAVING COUNT(*) > 1;

-- 6. 同批次预测线配置是否多行。
SELECT exam_batch_id, COUNT(*) AS duplicate_count
FROM public.tb_fraction_bar
WHERE exam_batch_id IS NOT NULL
GROUP BY exam_batch_id
HAVING COUNT(*) > 1;

-- 7. 学校明文名称是否重复，重复时不能直接按名称做MANY_TO_ONE。
SELECT s_name, COUNT(*) AS school_count
FROM public.tb_school
WHERE s_name IS NOT NULL AND BTRIM(s_name) <> ''
GROUP BY s_name
HAVING COUNT(*) > 1;

-- 8. 成绩空键、有子无父，以及试卷批次未匹配的数量。
SELECT
  COUNT(*) AS score_rows,
  COUNT(*) FILTER (WHERE sc.exam_id IS NULL) AS null_exam_id,
  COUNT(*) FILTER (WHERE sc.exam_id IS NOT NULL AND e.id IS NULL) AS missing_exam,
  COUNT(*) FILTER (WHERE sc.student_id IS NULL) AS null_student_id,
  COUNT(*) FILTER (WHERE sc.student_id IS NOT NULL AND st.id IS NULL) AS missing_student,
  COUNT(*) FILTER (WHERE sc.school_id IS NULL) AS null_school_id,
  COUNT(*) FILTER (WHERE sc.school_id IS NOT NULL AND sch.id IS NULL) AS missing_school,
  COUNT(*) FILTER (WHERE e.id IS NOT NULL AND e.exam_batch_id IS NULL) AS null_batch_id,
  COUNT(*) FILTER (WHERE e.exam_batch_id IS NOT NULL AND eb.id IS NULL) AS missing_batch
FROM public.tb_score sc
LEFT JOIN public.tb_exam e ON sc.exam_id = e.id
LEFT JOIN public.tb_exam_batch eb ON e.exam_batch_id = eb.id
LEFT JOIN public.tb_student st ON sc.student_id = st.id
LEFT JOIN public.tb_school sch ON sc.school_id = sch.id;

-- 9. 小题找不到成绩、找不到题目或题目试卷不一致。
-- 先通过第2项确认成绩复合键唯一，避免本查询被重复成绩扩行。
SELECT
  COUNT(*) AS detail_rows_after_join,
  COUNT(*) FILTER (WHERE sc.id IS NULL) AS missing_subject_score,
  COUNT(*) FILTER (WHERE sd.question_id IS NULL) AS null_question_id,
  COUNT(*) FILTER (WHERE sd.question_id IS NOT NULL AND eq.id IS NULL) AS missing_question,
  COUNT(*) FILTER (
    WHERE eq.id IS NOT NULL AND sd.exam_id IS DISTINCT FROM eq.exam_id
  ) AS question_exam_mismatch
FROM public.tb_score_detail sd
LEFT JOIN public.tb_score sc
  ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id
LEFT JOIN public.tb_exam_question eq ON sd.question_id = eq.id;

-- 10. 题目知识点桥接关系重复、非正权重、孤儿知识点须单独检查。
SELECT question_id, knowledge_id, COUNT(*) AS duplicate_count
FROM public.tb_exam_question_knowledge
GROUP BY question_id, knowledge_id
HAVING COUNT(*) > 1;

SELECT
  COUNT(*) FILTER (WHERE eqk.weight IS NULL OR eqk.weight <= 0) AS invalid_weight,
  COUNT(*) FILTER (WHERE eq.id IS NULL) AS missing_question,
  COUNT(*) FILTER (WHERE k.id IS NULL) AS missing_knowledge
FROM public.tb_exam_question_knowledge eqk
LEFT JOIN public.tb_exam_question eq ON eqk.question_id = eq.id
LEFT JOIN public.tb_knowledge k ON eqk.knowledge_id = k.id;

-- 11. 批次ID是否缺失，以及ID所指批次名是否与存储的考试名称一致。
SELECT
  COUNT(*) FILTER (WHERE ov.exam_batch_id IS NULL) AS null_batch_id,
  COUNT(*) FILTER (WHERE ov.exam_batch_id IS NOT NULL AND eb.id IS NULL) AS missing_batch,
  COUNT(*) FILTER (
    WHERE eb.id IS NOT NULL AND ov.exam_name IS DISTINCT FROM eb.batch_name
  ) AS batch_name_mismatch
FROM public.tb_score_overview ov
LEFT JOIN public.tb_exam_batch eb ON ov.exam_batch_id = eb.id;

-- 12. 总览学校文字在当前学校维度中无精确明文匹配的数量。
-- 此处不自动去前缀/模糊匹配；失配可能来自名称格式、校区或缺维度。
SELECT COUNT(*) AS rows_without_exact_school_name_match
FROM public.tb_score_overview ov
WHERE NOT EXISTS (
  SELECT 1 FROM public.tb_school sch WHERE sch.s_name = ov.xx
);

-- 13. 每条成绩按学生+批次关联总览时，匹配0行或多行的成绩记录数量。
WITH match_counts AS (
  SELECT sc.id, COUNT(ov.id) AS matched_overview_rows
  FROM public.tb_score sc
  LEFT JOIN public.tb_exam e ON sc.exam_id = e.id
  LEFT JOIN public.tb_score_overview ov
    ON ov.anon_stu_id = sc.student_id
   AND ov.exam_batch_id = e.exam_batch_id
  GROUP BY sc.id
)
SELECT
  COUNT(*) FILTER (WHERE matched_overview_rows = 0) AS no_overview_match,
  COUNT(*) FILTER (WHERE matched_overview_rows > 1) AS multiple_overview_matches
FROM match_counts;
