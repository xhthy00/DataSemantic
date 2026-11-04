-- V32 后十名与中位组知识点差距：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：每份试卷同校同班排序，真实0保留，后10和中位名次±2
-- 草案口径：顺序分组不扩同分；允许小班重叠并输出overlap_count
-- 草案口径：仅已有非空小题记录成对计算，不对缺行补0
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
), ranked AS (
SELECT *,ROW_NUMBER() OVER(PARTITION BY paper_id,school_id,class_name ORDER BY score_value DESC,student_id,score_id) AS position_no,
 COUNT(*) OVER(PARTITION BY paper_id,school_id,class_name) AS pool_count
FROM score_base WHERE score_value IS NOT NULL AND class_name IS NOT NULL
), cohorts AS (
SELECT *,CASE WHEN position_no>pool_count-LEAST(10,pool_count) THEN 1 ELSE 0 END AS bottom_flag,
 CASE WHEN position_no BETWEEN GREATEST(1,FLOOR((pool_count+1)/2.0)-2) AND LEAST(pool_count,FLOOR((pool_count+1)/2.0)+2) THEN 1 ELSE 0 END AS median_flag
FROM ranked
), cohort_counts AS (
SELECT paper_id,school_id,class_name,SUM(bottom_flag) AS bottom_count,SUM(median_flag) AS median_count,
 SUM(CASE WHEN bottom_flag=1 AND median_flag=1 THEN 1 ELSE 0 END) AS overlap_count
FROM cohorts GROUP BY paper_id,school_id,class_name
), weights AS (
SELECT question_id,knowledge_id,CAST(weight AS DOUBLE)/NULLIF(SUM(CAST(weight AS DOUBLE)) OVER(PARTITION BY question_id),0) AS w
FROM tb_exam_question_knowledge WHERE weight>0
), per_knowledge AS (
SELECT c.exam_batch_id,c.exam_name,c.paper_id,c.school_id,c.school_name,c.class_name,c.subject,
 w.knowledge_id,COALESCE(k.knowledge_name,'未关联知识点') AS knowledge_name,
 SUM(CASE WHEN c.bottom_flag=1 THEN CAST(d.score AS DOUBLE)*COALESCE(w.w,1) ELSE NULL END) AS bottom_score,
 SUM(CASE WHEN c.bottom_flag=1 THEN CAST(COALESCE(q.question_score,d.question_score) AS DOUBLE)*COALESCE(w.w,1) ELSE NULL END) AS bottom_full,
 SUM(CASE WHEN c.median_flag=1 THEN CAST(d.score AS DOUBLE)*COALESCE(w.w,1) ELSE NULL END) AS median_score,
 SUM(CASE WHEN c.median_flag=1 THEN CAST(COALESCE(q.question_score,d.question_score) AS DOUBLE)*COALESCE(w.w,1) ELSE NULL END) AS median_full
FROM cohorts c JOIN tb_score_detail d ON c.paper_id=d.exam_id AND c.student_id=d.student_id
LEFT JOIN tb_exam_question q ON d.question_id=q.id AND d.exam_id=q.exam_id
LEFT JOIN weights w ON d.question_id=w.question_id LEFT JOIN tb_knowledge k ON w.knowledge_id=k.id
WHERE d.score IS NOT NULL AND CAST(COALESCE(q.question_score,d.question_score) AS DOUBLE)>0
GROUP BY c.exam_batch_id,c.exam_name,c.paper_id,c.school_id,c.school_name,c.class_name,c.subject,w.knowledge_id,k.knowledge_name
)
SELECT p.*,cc.bottom_count,cc.median_count,cc.overlap_count,
 ROUND(100.0*bottom_score/NULLIF(bottom_full,0),2) AS bottom_rate,
 ROUND(100.0*median_score/NULLIF(median_full,0),2) AS median_rate,
 ROUND(100.0*median_score/NULLIF(median_full,0)-100.0*bottom_score/NULLIF(bottom_full,0),2) AS gap_pp
FROM per_knowledge p JOIN cohort_counts cc ON p.paper_id=cc.paper_id AND p.school_id=cc.school_id AND p.class_name=cc.class_name
