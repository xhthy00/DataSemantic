-- V37 学生历次成绩及进退步：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：按同届+考试类型+归属学校的全局相邻批次，不按学生缺考后任意回溯
-- 草案口径：同一学生同科且满分相同才算原始分差；缺分、缺满分或跨满分留NULL并输出状态
-- 草案口径：只实现原始科目趋势，不冒充六门总分趋势；另给得分率差作为不同量纲
-- 草案口径：±5为本草案稳定带，学生±3/班均±0.5须作为其他指标另行定义
WITH score_base AS (
SELECT sc.id AS score_id, sc.student_id, sc.exam_id AS paper_id,
       e.exam_batch_id, eb.batch_name AS exam_name, eb.exam_time AS exam_date,
       sc.school_id, sch.s_name AS school_name, sch.district,
       sch.type AS school_type, sc."class" AS class_name, e.subject,
       CAST(sc.score AS DECIMAL(18,4)) AS score_value,
       CAST(e.exam_score AS DECIMAL(18,4)) AS full_score,
       CASE WHEN sc.score IS NULL OR e.exam_score IS NULL
                      OR CAST(e.exam_score AS DECIMAL(18,4)) <= 0 THEN NULL
            WHEN CAST(sc.score AS DECIMAL(18,4)) >= CAST(e.exam_score AS DECIMAL(18,4)) * 0.60
            THEN 1 ELSE 0 END AS pass_flag
FROM tb_score sc
LEFT JOIN tb_exam e ON sc.exam_id = e.id
LEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id
LEFT JOIN tb_school sch ON sc.school_id = sch.id
), batches AS (
 SELECT id AS exam_batch_id,batch_name,exam_time,CAST(jc AS VARCHAR) AS cohort_year,exam_type,school_id,
 CASE WHEN jc IS NULL OR exam_time IS NULL THEN NULL ELSE
 LAG(id) OVER(PARTITION BY jc,exam_type,school_id ORDER BY exam_time,id) END AS previous_batch_id
 FROM tb_exam_batch WHERE jc IS NOT NULL AND CAST(jc AS VARCHAR)<>'' AND exam_time IS NOT NULL
), paired AS (
SELECT c.*,b.cohort_year,b.previous_batch_id,p.score_value AS previous_score,p.full_score AS previous_full_score,
 CASE WHEN c.score_value IS NULL OR p.score_value IS NULL THEN 'missing_score'
 WHEN c.full_score IS NULL OR p.full_score IS NULL OR c.full_score<=0 OR p.full_score<=0 THEN 'missing_full_score'
 WHEN c.full_score<>p.full_score THEN 'different_full_score' ELSE 'comparable' END AS comparison_status
FROM score_base c LEFT JOIN batches b ON c.exam_batch_id=b.exam_batch_id
LEFT JOIN score_base p ON p.exam_batch_id=b.previous_batch_id AND p.student_id=c.student_id AND p.subject=c.subject
), trend AS (
SELECT *,CASE WHEN comparison_status='comparable' THEN score_value-previous_score ELSE NULL END AS delta_score,
 CASE WHEN score_value IS NOT NULL AND previous_score IS NOT NULL AND full_score>0 AND previous_full_score>0
 THEN ROUND(100.0*score_value/full_score-100.0*previous_score/previous_full_score,2) ELSE NULL END AS score_rate_delta_pp
FROM paired
)
SELECT *, 'raw_subject' AS score_type,score_value AS current_score,
 CASE WHEN delta_score IS NULL THEN 'unknown' WHEN delta_score>5 THEN 'progress' WHEN delta_score < -5 THEN 'regress' ELSE 'stable' END AS progress_band
FROM trend
