-- V40 优秀良好低分率与互斥水平分层：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：85%优秀、70%良好、40%低分为源码默认，含等于优秀/良好、不含等于低分边界
-- 草案口径：每学校科目一行：优秀良好为累计率，ABCD互斥档通过a_count/b_count/c_count/d_count另列，不按档分组改变率分母
-- 草案口径：真实0保留，缺成绩/缺满分为unclassified，不把缺分当D
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
), classified AS (
SELECT *,CASE WHEN score_value IS NULL OR full_score IS NULL OR full_score<=0 THEN 'unclassified'
 WHEN score_value>=full_score*0.85 THEN 'A' WHEN score_value>=full_score*0.70 THEN 'B'
 WHEN score_value>=full_score*0.60 THEN 'C' ELSE 'D' END AS performance_band
FROM base
)
SELECT exam_batch_id,exam_name,school_id,school_name,subject,
 COUNT(score_value) AS valid_count,COUNT(pass_flag) AS classified_count,
 SUM(CASE WHEN performance_band='A' THEN 1 ELSE 0 END) AS excellent_count,
 SUM(CASE WHEN performance_band IN ('A','B') THEN 1 ELSE 0 END) AS good_count,
 SUM(CASE WHEN pass_flag IS NOT NULL AND score_value<full_score*0.40 THEN 1 ELSE 0 END) AS low_count,
 ROUND(100.0*SUM(CASE WHEN performance_band='A' THEN 1 ELSE 0 END)/NULLIF(COUNT(pass_flag),0),2) AS excellent_rate,
 ROUND(100.0*SUM(CASE WHEN performance_band IN ('A','B') THEN 1 ELSE 0 END)/NULLIF(COUNT(pass_flag),0),2) AS good_rate,
 ROUND(100.0*SUM(CASE WHEN pass_flag IS NOT NULL AND score_value<full_score*0.40 THEN 1 ELSE 0 END)/NULLIF(COUNT(pass_flag),0),2) AS low_rate,
 SUM(CASE WHEN performance_band='A' THEN 1 ELSE 0 END) AS a_count,
 SUM(CASE WHEN performance_band='B' THEN 1 ELSE 0 END) AS b_count,
 SUM(CASE WHEN performance_band='C' THEN 1 ELSE 0 END) AS c_count,
 SUM(CASE WHEN performance_band='D' THEN 1 ELSE 0 END) AS d_count,
 SUM(CASE WHEN performance_band='unclassified' THEN 1 ELSE 0 END) AS unclassified_record_count
FROM classified GROUP BY exam_batch_id,exam_name,school_id,school_name,subject
