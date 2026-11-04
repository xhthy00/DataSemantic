WITH weights AS (
  SELECT question_id, knowledge_id,
         CAST(weight AS DOUBLE) /
         NULLIF(SUM(CAST(weight AS DOUBLE)) OVER (PARTITION BY question_id),0) AS normalized_weight
  FROM tb_exam_question_knowledge
  WHERE weight > 0
), items AS (
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
SELECT i.exam_batch_id, i.exam_name, i.school_id, i.school_name, i.subject,
       w.knowledge_id, COALESCE(k.knowledge_name,'未关联知识点') AS knowledge_name,
       k.ability_level,
       COUNT(DISTINCT i.question_id) AS question_count,
       COUNT(*) AS observed_item_count,
       SUM(i.item_score*COALESCE(w.normalized_weight,1)) AS weighted_score,
       SUM(i.item_full_score*COALESCE(w.normalized_weight,1)) AS weighted_full_score,
       ROUND(100.0*SUM(i.item_score*COALESCE(w.normalized_weight,1)) /
             NULLIF(SUM(i.item_full_score*COALESCE(w.normalized_weight,1)),0),2) AS mastery_rate
FROM items i
LEFT JOIN weights w ON i.question_id=w.question_id
LEFT JOIN tb_knowledge k ON w.knowledge_id=k.id
WHERE i.item_score IS NOT NULL AND i.item_full_score > 0
GROUP BY i.exam_batch_id, i.exam_name, i.school_id, i.school_name, i.subject,
         w.knowledge_id, k.knowledge_name, k.ability_level
