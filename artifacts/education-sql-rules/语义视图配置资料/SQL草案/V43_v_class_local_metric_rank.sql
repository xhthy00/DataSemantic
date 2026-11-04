-- V43 班级总览同校年级指标排名：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：均分/及格率/优秀率独立顺序编号，同分用班名稳定排序，不冒充RANK并列
-- 草案口径：对照为各班指标等权且含本班，至少2班才给名次；年级不识别不混排
-- 草案口径：优秀85%是待确认草案默认，及格60%、真实0保留
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
), metrics AS (
SELECT exam_batch_id,exam_name,school_id,school_name,grade,class_name,subject,n,'average_score' AS metric_name,CAST(class_avg AS DOUBLE) AS metric_value FROM class_stats WHERE n>0
UNION ALL
SELECT exam_batch_id,exam_name,school_id,school_name,grade,class_name,subject,n,'pass_rate',pass_rate FROM class_stats WHERE n>0
UNION ALL
SELECT exam_batch_id,exam_name,school_id,school_name,grade,class_name,subject,n,'excellent_rate',excellent_rate FROM class_stats WHERE n>0
), ranked AS (
SELECT *,COUNT(*) OVER(PARTITION BY exam_batch_id,school_id,grade,subject,metric_name) AS class_count,
 ROW_NUMBER() OVER(PARTITION BY exam_batch_id,school_id,grade,subject,metric_name ORDER BY metric_value DESC NULLS LAST,class_name) AS provisional_rank,
 AVG(metric_value) OVER(PARTITION BY exam_batch_id,school_id,grade,subject,metric_name) AS peer_equal_weight_value
FROM metrics WHERE metric_value IS NOT NULL
)
SELECT *,CASE WHEN class_count>=2 THEN provisional_rank ELSE NULL END AS row_number_rank
FROM ranked
