-- V38 水平分层、偏科与相关性：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：performance_band按单科实际满分判ABCD，不猜六门总满分
-- 草案口径：偏科度按同班各科顺序名次总体标准差，至少两科；不同选科参与集合影响解释
-- 草案口径：原始分差>=20且有不及格科只作legacy证据；不同满分不宣称已标准化
-- 草案口径：Pearson使用同学生成对非空记录；样本不足/零方差为NULL，不将相关性当因果
WITH raw_base AS (
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
), selected AS (
SELECT * FROM raw_base WHERE score_value IS NOT NULL AND full_score>0 AND class_name IS NOT NULL
), subject_ranks AS (
SELECT *,ROW_NUMBER() OVER(PARTITION BY exam_batch_id,school_id,class_name,subject ORDER BY score_value DESC,student_id,score_id) AS subject_rank,
 CASE WHEN score_value>=full_score*0.85 THEN 'A' WHEN score_value>=full_score*0.70 THEN 'B'
 WHEN score_value>=full_score*0.60 THEN 'C' ELSE 'D' END AS performance_band
FROM selected
), imbalance AS (
SELECT exam_batch_id,school_id,class_name,student_id,COUNT(*) AS subject_count,
 STDDEV_POP(CAST(subject_rank AS DOUBLE)) AS imbalance_degree,
 MAX(score_value)-MIN(score_value) AS raw_score_gap,
 MAX(CASE WHEN score_value<full_score*0.60 THEN 1 ELSE 0 END) AS has_failed_subject
FROM subject_ranks GROUP BY exam_batch_id,school_id,class_name,student_id
), pairs AS (
SELECT r.exam_batch_id,r.school_id,r.class_name,r.subject,
 COUNT(*) AS pair_count,STDDEV_POP(CAST(r.score_value AS DOUBLE)) AS subject_sd,STDDEV_POP(CAST(o.zf6m AS DOUBLE)) AS total_sd,CORR(CAST(r.score_value AS DOUBLE),CAST(o.zf6m AS DOUBLE)) AS pearson_r
FROM subject_ranks r JOIN tb_score_overview o ON r.exam_batch_id=o.exam_batch_id AND r.student_id=o.anon_stu_id
WHERE o.zf6m IS NOT NULL
GROUP BY r.exam_batch_id,r.school_id,r.class_name,r.subject
)
SELECT r.*,i.subject_count,CASE WHEN i.subject_count>=2 THEN ROUND(i.imbalance_degree,2) ELSE NULL END AS imbalance_degree,
 i.raw_score_gap,CASE WHEN i.subject_count>=2 AND i.raw_score_gap>=20 AND i.has_failed_subject=1 THEN 1 ELSE 0 END AS raw_gap_flag,
 p.pair_count,CASE WHEN p.pair_count>=2 AND p.subject_sd>0 AND p.total_sd>0 THEN ROUND(p.pearson_r,3) ELSE NULL END AS pearson_r
FROM subject_ranks r JOIN imbalance i ON r.exam_batch_id=i.exam_batch_id AND r.school_id=i.school_id AND r.class_name=i.class_name AND r.student_id=i.student_id
LEFT JOIN pairs p ON r.exam_batch_id=p.exam_batch_id AND r.school_id=p.school_id AND r.class_name=p.class_name AND r.subject=p.subject
