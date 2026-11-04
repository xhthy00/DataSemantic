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
)
SELECT exam_batch_id,exam_name,paper_id,school_id,school_name,subject,
       question_id,question_no,question_type,item_full_score,
       COUNT(item_score) AS observed_count,ROUND(AVG(item_score),2) AS average_item_score,
       ROUND(100.0*AVG(item_score)/NULLIF(item_full_score,0),2) AS score_rate,
       ROUND(1.0-AVG(item_score)/NULLIF(item_full_score,0),4) AS difficulty_index
FROM items
GROUP BY exam_batch_id,exam_name,paper_id,school_id,school_name,subject,
         question_id,question_no,question_type,item_full_score
