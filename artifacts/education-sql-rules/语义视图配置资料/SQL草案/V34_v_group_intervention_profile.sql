-- V34 群体特征与干预优先级：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：同校同年级科目，基准为学生加权；班级>=3
-- 草案口径：分数差只和分数标准差比，率差用百分点阈值，修正旧单位混比
-- 草案口径：±3分、1.15倍、落后5分/5pp、60%和优先级加权为待确认默认；小题仅已有非空记录
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
), school_stats AS (
SELECT exam_batch_id,school_id,grade,subject,AVG(score_value) AS school_avg,
 STDDEV_SAMP(CAST(score_value AS DOUBLE)) AS school_stdev,
 100.0*SUM(pass_flag)/NULLIF(COUNT(pass_flag),0) AS school_pass_rate
FROM graded WHERE grade IS NOT NULL GROUP BY exam_batch_id,school_id,grade,subject
), compared AS (
SELECT c.*,s.school_avg,s.school_stdev,s.school_pass_rate,
 c.class_avg-s.school_avg AS average_score_gap,c.pass_rate-s.school_pass_rate AS pass_rate_gap_pp,
 c.class_stdev/NULLIF(s.school_stdev,0) AS dispersion_ratio,
 CASE WHEN s.school_stdev>0 THEN CASE WHEN c.class_stdev>=s.school_stdev*1.15 THEN 1 ELSE 0 END
      WHEN c.score_range>=GREATEST(30,ABS(s.school_avg)*0.35) THEN 1 ELSE 0 END AS high_dispersion
FROM class_stats c JOIN school_stats s ON c.exam_batch_id=s.exam_batch_id AND c.school_id=s.school_id AND c.grade=s.grade AND c.subject=s.subject
WHERE c.n>=3
), item_base AS (
SELECT sd.id AS detail_id, sd.exam_id AS paper_id, sd.student_id,
       e.exam_batch_id, eb.batch_name AS exam_name,
       sc.school_id, sch.s_name AS school_name, sc."class" AS class_name,
       e.subject, sd.question_id, sd.question_no, eq.question_type,
       CAST(sd.score AS DECIMAL(18,4)) AS item_score,
       CAST(COALESCE(eq.question_score,sd.question_score) AS DECIMAL(18,4)) AS item_full_score
FROM tb_score_detail sd
JOIN tb_score sc ON sd.exam_id=sc.exam_id AND sd.student_id=sc.student_id
LEFT JOIN tb_exam e ON sd.exam_id=e.id
LEFT JOIN tb_exam_batch eb ON e.exam_batch_id=eb.id
LEFT JOIN tb_school sch ON sc.school_id=sch.id
LEFT JOIN tb_exam_question eq ON sd.question_id=eq.id AND sd.exam_id=eq.exam_id
), item_rates AS (
SELECT exam_batch_id,paper_id,school_id,class_name,subject,question_id,
 CASE WHEN class_name LIKE '高一%' THEN '高一' WHEN class_name LIKE '高二%' THEN '高二' WHEN class_name LIKE '高三%' THEN '高三' WHEN class_name LIKE '初一%' THEN '初一' WHEN class_name LIKE '初二%' THEN '初二' WHEN class_name LIKE '初三%' THEN '初三' ELSE NULL END AS grade,
 100.0*AVG(item_score)/NULLIF(MAX(item_full_score),0) AS item_rate
FROM item_base WHERE item_score IS NOT NULL AND item_full_score>0
GROUP BY exam_batch_id,paper_id,school_id,class_name,subject,question_id
), item_peers AS (
SELECT *,COUNT(*) OVER(PARTITION BY exam_batch_id,paper_id,school_id,grade,question_id) AS peer_classes,
 (SUM(item_rate) OVER(PARTITION BY exam_batch_id,paper_id,school_id,grade,question_id)-item_rate)/
 NULLIF(COUNT(*) OVER(PARTITION BY exam_batch_id,paper_id,school_id,grade,question_id)-1,0) AS peer_item_rate
FROM item_rates
), item_flags AS (
SELECT exam_batch_id,school_id,class_name,subject,
 SUM(CASE WHEN item_rate-peer_item_rate<=-8 THEN 1 ELSE 0 END) AS lagging_item_count,
 SUM(CASE WHEN item_rate-peer_item_rate>-8 AND item_rate<60 AND peer_item_rate<60 THEN 1 ELSE 0 END) AS common_hard_item_count
FROM item_peers GROUP BY exam_batch_id,school_id,class_name,subject
)
SELECT c.*,
 CASE WHEN average_score_gap>=3 AND high_dispersion=0 THEN '优势均衡'
 WHEN average_score_gap>=3 THEN '优势两极' WHEN average_score_gap<=-3 AND high_dispersion=1 THEN '薄弱两极'
 WHEN average_score_gap<=-3 THEN '整体偏弱' WHEN high_dispersion=1 THEN '中间分化' ELSE '中间稳健' END AS feature_label,
 CASE WHEN average_score_gap < -5 OR (average_score_gap<0 AND ABS(average_score_gap)>school_stdev)
 OR pass_rate_gap_pp < -5 OR pass_rate<60 THEN 1 ELSE 0 END AS intervention_flag,
 2*ABS(average_score_gap)+CASE WHEN pass_rate_gap_pp<0 THEN ABS(pass_rate_gap_pp) ELSE 0 END+
 CASE WHEN pass_rate<60 THEN 10 ELSE 0 END AS priority_score,
 COALESCE(i.lagging_item_count,0) AS lagging_item_count,COALESCE(i.common_hard_item_count,0) AS common_hard_item_count
FROM compared c LEFT JOIN item_flags i ON c.exam_batch_id=i.exam_batch_id AND c.school_id=i.school_id AND c.class_name=i.class_name AND c.subject=i.subject
