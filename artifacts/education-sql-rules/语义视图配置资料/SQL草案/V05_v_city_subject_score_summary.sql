WITH base AS (
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
)
SELECT exam_batch_id, exam_name, subject,
       COUNT(*) AS recorded_count, COUNT(score_value) AS valid_count,
       COUNT(*) - COUNT(score_value) AS null_score_count,
       SUM(score_value) AS total_score,
       ROUND(AVG(score_value),2) AS average_score,
       MIN(score_value) AS min_score, MAX(score_value) AS max_score,
       MIN(full_score) AS min_full_score, MAX(full_score) AS max_full_score,
       COALESCE(SUM(pass_flag),0) AS pass_count,
       COUNT(pass_flag) AS classified_count,
       COUNT(score_value)-COUNT(pass_flag) AS unclassified_count,
       ROUND(100.0*SUM(pass_flag)/NULLIF(COUNT(pass_flag),0),2) AS pass_rate
FROM base
GROUP BY exam_batch_id, exam_name, subject
