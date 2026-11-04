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
), labeled AS (
SELECT *, CASE WHEN score_value IS NULL OR full_score IS NULL OR full_score<=0
                       OR score_value<0 OR score_value>full_score THEN NULL
  WHEN score_value<full_score*0.60 THEN '00_低于60%'
  WHEN score_value<full_score*0.70 THEN '01_60%-70%'
  WHEN score_value<full_score*0.80 THEN '02_70%-80%'
  WHEN score_value<full_score*0.90 THEN '03_80%-90%'
  ELSE '04_90%-100%' END AS score_band
FROM base)
SELECT exam_batch_id,exam_name,school_id,school_name,subject,score_band,
       COUNT(*) AS band_count
FROM labeled
GROUP BY exam_batch_id,exam_name,school_id,school_name,subject,score_band
