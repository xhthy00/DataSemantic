-- V35 教研整体、分卷和拖后腿小题：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：仅在籍，排市报学校；OV学生批次键唯一是前提
-- 草案口径：校区按学校名前字母+两数字编码合并，无编码用school_id；混合校类需先修复
-- 草案口径：row_type分overall/section/item；原始整卷均分、分卷、小题在不同粒度，禁止混合SUM
-- 草案口径：有整科成绩的学生×试卷题目作底，缺小题暂补0；卷1/2题型沿用旧前缀，拖后腿2/3名门槛
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
), research_base AS (
SELECT b.*,CASE WHEN REGEXP_LIKE(b.school_name,'^[A-Za-z][0-9]{2}') THEN SUBSTRING(b.school_name,1,3) ELSE b.school_id END AS school_unit_id
FROM raw_base b JOIN tb_score_overview o ON b.student_id=o.anon_stu_id AND b.exam_batch_id=o.exam_batch_id
WHERE o.xsxz='在籍生' AND b.score_value IS NOT NULL
 AND (b.school_type IS NULL OR b.school_type NOT LIKE '%市报%')
), overall AS (
SELECT exam_batch_id,exam_name,subject,school_unit_id,MAX(school_type) AS school_type,
 COUNT(*) AS unit_n,AVG(CAST(score_value AS DOUBLE)) AS raw_average
FROM research_base GROUP BY exam_batch_id,exam_name,subject,school_unit_id
), ranked_overall AS (
SELECT *,RANK() OVER(PARTITION BY exam_batch_id,subject ORDER BY raw_average DESC) AS city_rank
FROM overall
), tier_stats AS (
SELECT exam_batch_id,subject,school_type,AVG(CAST(score_value AS DOUBLE)) AS tier_average
FROM research_base GROUP BY exam_batch_id,subject,school_type
), research_items AS (
SELECT b.*,q.id AS question_id,q.question_no,
 CASE WHEN q.question_type IS NULL OR q.question_type='' THEN 'other'
 WHEN q.question_type LIKE '单选题%' OR q.question_type LIKE '多选题%' OR q.question_type LIKE '听力%' OR q.question_type LIKE '阅读理解%' OR q.question_type LIKE '阅读%' OR q.question_type LIKE '完形填空%' OR q.question_type LIKE '七选五%' THEN 'paper1' ELSE 'paper2' END AS paper_section,
 CAST(COALESCE(d.score,0) AS DOUBLE) AS item_score
FROM research_base b JOIN tb_exam_question q ON b.paper_id=q.exam_id
LEFT JOIN tb_score_detail d ON d.exam_id=b.paper_id AND d.student_id=b.student_id AND d.question_id=q.id
), student_sections AS (
SELECT exam_batch_id,exam_name,subject,school_unit_id,student_id,paper_id,paper_section,SUM(item_score) AS section_score
FROM research_items WHERE paper_section IN ('paper1','paper2')
GROUP BY exam_batch_id,exam_name,subject,school_unit_id,student_id,paper_id,paper_section
), sections AS (
SELECT exam_batch_id,subject,school_unit_id,paper_section,AVG(section_score) AS section_average
FROM student_sections GROUP BY exam_batch_id,subject,school_unit_id,paper_section
), section_ranks AS (
SELECT *,RANK() OVER(PARTITION BY exam_batch_id,subject,paper_section ORDER BY section_average DESC) AS section_rank
FROM sections
), item_stats AS (
SELECT exam_batch_id,subject,school_unit_id,question_id,question_no,AVG(item_score) AS item_average
FROM research_items GROUP BY exam_batch_id,subject,school_unit_id,question_id,question_no
), item_ranks AS (
SELECT *,RANK() OVER(PARTITION BY exam_batch_id,subject,question_id ORDER BY item_average DESC) AS item_rank
FROM item_stats
), batches AS (
 SELECT id AS exam_batch_id,batch_name,exam_time,CAST(jc AS VARCHAR) AS cohort_year,exam_type,school_id,
 CASE WHEN jc IS NULL OR exam_time IS NULL THEN NULL ELSE
 LAG(id) OVER(PARTITION BY jc,exam_type,school_id ORDER BY exam_time,id) END AS previous_batch_id
 FROM tb_exam_batch WHERE jc IS NOT NULL AND CAST(jc AS VARCHAR)<>'' AND exam_time IS NOT NULL
), enriched AS (
SELECT r.*,t.tier_average,b.previous_batch_id,p.raw_average AS previous_average,p.city_rank AS previous_city_rank,p.city_rank-r.city_rank AS rank_change
FROM ranked_overall r LEFT JOIN tier_stats t ON r.exam_batch_id=t.exam_batch_id AND r.subject=t.subject
 AND COALESCE(r.school_type,'')=COALESCE(t.school_type,'')
LEFT JOIN batches b ON r.exam_batch_id=b.exam_batch_id
LEFT JOIN ranked_overall p ON p.exam_batch_id=b.previous_batch_id AND p.subject=r.subject AND p.school_unit_id=r.school_unit_id
)
SELECT e.*,'overall' AS row_type,CAST(NULL AS VARCHAR) AS paper_section,
 CAST(NULL AS DOUBLE) AS section_average,CAST(NULL AS BIGINT) AS section_rank,
 CAST(NULL AS INTEGER) AS question_id,CAST(NULL AS VARCHAR) AS question_no,
 CAST(NULL AS DOUBLE) AS item_average,CAST(NULL AS BIGINT) AS item_rank,
 CAST(NULL AS BIGINT) AS rank_lag,CAST(NULL AS INTEGER) AS lagging_flag
FROM enriched e
UNION ALL
SELECT e.*,'section',s.paper_section,s.section_average,s.section_rank,NULL,NULL,NULL,NULL,NULL,NULL
FROM enriched e JOIN section_ranks s ON e.exam_batch_id=s.exam_batch_id AND e.subject=s.subject AND e.school_unit_id=s.school_unit_id
UNION ALL
SELECT e.*,'item',NULL,NULL,NULL,i.question_id,i.question_no,i.item_average,i.item_rank,i.item_rank-e.city_rank,
 CASE WHEN i.item_rank-e.city_rank>=CASE WHEN e.school_type LIKE '%引领%' THEN 2 ELSE 3 END THEN 1 ELSE 0 END
FROM enriched e JOIN item_ranks i ON e.exam_batch_id=i.exam_batch_id AND e.subject=i.subject AND e.school_unit_id=i.school_unit_id
