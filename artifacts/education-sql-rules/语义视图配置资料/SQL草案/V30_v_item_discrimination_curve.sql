-- V30 题目区分度与难度曲线：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：以有非空科目成绩的学生×本卷全部题目为底，缺小题行/NULL暂按0，须业务确认
-- 草案口径：高低27%按整科成绩顺序切组，同分按学生ID稳定；至少4人算区分度
-- 草案口径：discrimination以题满分为分母，legacy_discrimination同时保留旧个人总分分母；不可混称
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
), ranked_students AS (
SELECT *,ROW_NUMBER() OVER(PARTITION BY paper_id,school_id ORDER BY score_value DESC,student_id,score_id) AS student_position,
 COUNT(*) OVER(PARTITION BY paper_id,school_id) AS student_pool_count
FROM score_base WHERE score_value IS NOT NULL AND score_value>=0
), spine AS (
SELECT s.*,q.id AS question_id,q.question_no,q.question_type,
 CAST(q.question_score AS DOUBLE) AS item_full_score,
 CAST(COALESCE(d.score,0) AS DOUBLE) AS item_score,
 CASE WHEN s.score_value=0 THEN 0 ELSE FLOOR((FLOOR(s.score_value)-1)/10)*10+1 END AS score_band
FROM ranked_students s JOIN tb_exam_question q ON s.paper_id=q.exam_id
LEFT JOIN tb_score_detail d ON d.exam_id=s.paper_id AND d.student_id=s.student_id AND d.question_id=q.id
WHERE CAST(q.question_score AS DOUBLE)>0
), bands AS (
SELECT exam_batch_id,exam_name,paper_id,school_id,school_name,subject,question_id,question_no,score_band,
 COUNT(*) AS student_count,AVG(item_score/item_full_score)*100.0 AS item_score_rate
FROM spine GROUP BY exam_batch_id,exam_name,paper_id,school_id,school_name,subject,question_id,question_no,score_band
), band_order AS (
SELECT *,ROW_NUMBER() OVER(PARTITION BY paper_id,school_id,question_id ORDER BY score_band) AS ascending_band,
 ROW_NUMBER() OVER(PARTITION BY paper_id,school_id,question_id ORDER BY score_band DESC) AS descending_band
FROM bands
), extrema AS (
SELECT paper_id,school_id,question_id,COUNT(*) AS band_count,
 MAX(CASE WHEN ascending_band=1 THEN item_score_rate ELSE NULL END) AS low_band_rate,
 MAX(CASE WHEN descending_band=1 THEN item_score_rate ELSE NULL END) AS high_band_rate
FROM band_order GROUP BY paper_id,school_id,question_id
), discrimination AS (
SELECT paper_id,school_id,question_id,MAX(student_pool_count) AS pool_count,
 AVG(CASE WHEN student_position<=GREATEST(1,FLOOR(student_pool_count*0.27)) THEN item_score/item_full_score ELSE NULL END) AS high_item_ratio,
 AVG(CASE WHEN student_position>student_pool_count-GREATEST(1,FLOOR(student_pool_count*0.27)) THEN item_score/item_full_score ELSE NULL END) AS low_item_ratio,
 AVG(CASE WHEN student_position<=GREATEST(1,FLOOR(student_pool_count*0.27)) THEN item_score/NULLIF(CAST(score_value AS DOUBLE),0) ELSE NULL END) AS high_legacy_ratio,
 AVG(CASE WHEN student_position>student_pool_count-GREATEST(1,FLOOR(student_pool_count*0.27)) THEN item_score/NULLIF(CAST(score_value AS DOUBLE),0) ELSE NULL END) AS low_legacy_ratio
FROM spine GROUP BY paper_id,school_id,question_id
)
SELECT b.*,ROUND(b.item_score_rate,2) AS score_rate,
 CASE WHEN e.band_count>=2 THEN ROUND(e.high_band_rate-e.low_band_rate,2) ELSE NULL END AS high_low_delta_pp,
 CASE WHEN d.pool_count>=4 THEN ROUND(100.0*(d.high_item_ratio-d.low_item_ratio),2) ELSE NULL END AS discrimination,
 CASE WHEN d.pool_count>=4 THEN ROUND(100.0*(d.high_legacy_ratio-d.low_legacy_ratio),2) ELSE NULL END AS legacy_discrimination,
 'missing_item_as_zero' AS missing_policy
FROM bands b JOIN extrema e ON b.paper_id=e.paper_id AND b.school_id=e.school_id AND b.question_id=e.question_id
JOIN discrimination d ON b.paper_id=d.paper_id AND b.school_id=d.school_id AND b.question_id=d.question_id
