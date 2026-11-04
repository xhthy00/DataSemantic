-- V33 同校班际薄弱学科：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：同校同年级同科、每班>=3个非空成绩；未识别年级不混排
-- 草案口径：对照各班均分等权且含本班；DENSE_RANK
-- 草案口径：逐卷满分60%及格、85%优秀，真实0保留；5分/后30%/后3名为待确认默认
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
), graded AS (
SELECT *,CASE WHEN class_name LIKE '高一%' THEN '高一' WHEN class_name LIKE '高二%' THEN '高二' WHEN class_name LIKE '高三%' THEN '高三' WHEN class_name LIKE '初一%' THEN '初一' WHEN class_name LIKE '初二%' THEN '初二' WHEN class_name LIKE '初三%' THEN '初三' ELSE NULL END AS grade,
 CASE WHEN score_value IS NULL OR full_score IS NULL OR full_score<=0 THEN NULL WHEN score_value>=full_score*0.85 THEN 1 ELSE 0 END AS excellent_flag
FROM base
), class_stats AS (
SELECT exam_batch_id,exam_name,school_id,school_name,grade,class_name,subject,
 COUNT(score_value) AS n,AVG(score_value) AS class_avg,
 STDDEV_SAMP(CAST(score_value AS DOUBLE)) AS class_stdev,MAX(score_value)-MIN(score_value) AS score_range,
 100.0*SUM(pass_flag)/NULLIF(COUNT(pass_flag),0) AS pass_rate,
 100.0*SUM(excellent_flag)/NULLIF(COUNT(excellent_flag),0) AS excellent_rate
FROM graded WHERE grade IS NOT NULL AND class_name IS NOT NULL
GROUP BY exam_batch_id,exam_name,school_id,school_name,grade,class_name,subject
), ranked AS (
SELECT *,DENSE_RANK() OVER(PARTITION BY exam_batch_id,school_id,grade,subject ORDER BY class_avg DESC) AS dense_rank,
 COUNT(*) OVER(PARTITION BY exam_batch_id,school_id,grade,subject) AS class_count,
 AVG(class_avg) OVER(PARTITION BY exam_batch_id,school_id,grade,subject) AS peer_avg
FROM class_stats WHERE n>=3
)
SELECT *,ROUND(peer_avg-class_avg,2) AS avg_gap,
 CASE WHEN dense_rank>CEIL(class_count*0.70) OR peer_avg-class_avg>=5
 OR (class_count>=10 AND dense_rank>class_count-3) THEN 1 ELSE 0 END AS weak_flag
FROM ranked
