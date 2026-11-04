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
), school_stats AS (
SELECT exam_batch_id,exam_name,school_id,school_name,subject,
       COUNT(score_value) AS school_count,AVG(score_value) AS school_avg
FROM base GROUP BY exam_batch_id,exam_name,school_id,school_name,subject
), city_stats AS (
SELECT exam_batch_id,subject,COUNT(score_value) AS city_count,AVG(score_value) AS city_avg
FROM base GROUP BY exam_batch_id,subject
)
SELECT s.*,c.city_count,ROUND(c.city_avg,2) AS city_average_score,
       ROUND(s.school_avg,2) AS school_average_score,
       ROUND(s.school_avg-c.city_avg,2) AS average_score_gap
FROM school_stats s
LEFT JOIN city_stats c ON s.exam_batch_id=c.exam_batch_id AND s.subject=c.subject
