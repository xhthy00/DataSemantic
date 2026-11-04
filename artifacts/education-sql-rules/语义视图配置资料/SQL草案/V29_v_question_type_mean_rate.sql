-- V29 题型平均得分率：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：同时输出每题等权平均与分值/观测人数加权的两种得分率
-- 草案口径：仅已记录非空题成绩，缺行不补零；满分非正排除
-- 草案口径：不同班级独立输出，合并时回到底表重算
WITH items AS (
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
), per_question AS (
SELECT exam_batch_id,exam_name,paper_id,school_id,school_name,class_name,subject,question_id,question_no,
 question_type,item_full_score,COUNT(item_score) AS observed_count,
 SUM(item_score) AS score_sum,COUNT(item_score)*item_full_score AS full_sum,
 AVG(item_score)/NULLIF(item_full_score,0)*100.0 AS question_rate
FROM items WHERE item_score IS NOT NULL AND item_full_score>0
GROUP BY exam_batch_id,exam_name,paper_id,school_id,school_name,class_name,subject,question_id,question_no,question_type,item_full_score
)
SELECT exam_batch_id,exam_name,paper_id,school_id,school_name,class_name,subject,question_type,
 COUNT(*) AS question_count,SUM(observed_count) AS observed_count,
 ROUND(AVG(question_rate),2) AS mean_item_rate,
 ROUND(100.0*SUM(score_sum)/NULLIF(SUM(full_sum),0),2) AS weighted_type_rate
FROM per_question GROUP BY exam_batch_id,exam_name,paper_id,school_id,school_name,class_name,subject,question_type
