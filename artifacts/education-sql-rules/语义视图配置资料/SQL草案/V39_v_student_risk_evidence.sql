-- V39 临界生与退步预警证据：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：临界[及格线−5,及格线+5)，退步<=−10，分差型偏科>=20为草案默认
-- 草案口径：仅同满分可比前后成绩触发退步，不补缺考
-- 草案口径：偏科事件按科目逐行输出，统计偏科学生须DISTINCT student_id
-- 草案口径：版本字段显式为draft，不读取原系统运行配置；通知/确认/连续次数仍由应用实现
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
), batches AS (
 SELECT id AS exam_batch_id,batch_name,exam_time,CAST(jc AS VARCHAR) AS cohort_year,exam_type,school_id,
 CASE WHEN jc IS NULL OR exam_time IS NULL THEN NULL ELSE
 LAG(id) OVER(PARTITION BY jc,exam_type,school_id ORDER BY exam_time,id) END AS previous_batch_id
 FROM tb_exam_batch WHERE jc IS NOT NULL AND CAST(jc AS VARCHAR)<>'' AND exam_time IS NOT NULL
), paired AS (
SELECT c.*,b.cohort_year,b.previous_batch_id,p.score_value AS previous_score,p.full_score AS previous_full_score,
 CASE WHEN c.score_value IS NULL OR p.score_value IS NULL THEN 'missing_score'
 WHEN c.full_score IS NULL OR p.full_score IS NULL OR c.full_score<=0 OR p.full_score<=0 THEN 'missing_full_score'
 WHEN c.full_score<>p.full_score THEN 'different_full_score' ELSE 'comparable' END AS comparison_status
FROM score_base c LEFT JOIN batches b ON c.exam_batch_id=b.exam_batch_id
LEFT JOIN score_base p ON p.exam_batch_id=b.previous_batch_id AND p.student_id=c.student_id AND p.subject=c.subject
), trend AS (
SELECT *,CASE WHEN comparison_status='comparable' THEN score_value-previous_score ELSE NULL END AS delta_score,
 CASE WHEN score_value IS NOT NULL AND previous_score IS NOT NULL AND full_score>0 AND previous_full_score>0
 THEN ROUND(100.0*score_value/full_score-100.0*previous_score/previous_full_score,2) ELSE NULL END AS score_rate_delta_pp
FROM paired
), gaps AS (
SELECT exam_batch_id,school_id,student_id,COUNT(score_value) AS subject_count,
 MAX(score_value)-MIN(score_value) AS raw_score_gap,
 MAX(CASE WHEN score_value IS NOT NULL AND full_score>0 AND score_value<full_score*0.60 THEN 1 ELSE 0 END) AS has_failed_subject
FROM trend GROUP BY exam_batch_id,school_id,student_id
), evidence AS (
SELECT t.*,g.subject_count,g.raw_score_gap,g.has_failed_subject,
 full_score*0.60 AS pass_score
FROM trend t JOIN gaps g ON t.exam_batch_id=g.exam_batch_id AND t.school_id=g.school_id AND t.student_id=g.student_id
)
SELECT exam_batch_id,exam_name,school_id,school_name,class_name,student_id,subject,score_value,full_score,pass_score,
 previous_batch_id,previous_score,delta_score,'critical' AS risk_type,'draft_pass60_margin5_regress10_gap20' AS threshold_version,
 raw_score_gap,comparison_status
FROM evidence WHERE full_score>0 AND score_value>=pass_score-5 AND score_value<pass_score+5
UNION ALL
SELECT exam_batch_id,exam_name,school_id,school_name,class_name,student_id,subject,score_value,full_score,pass_score,
 previous_batch_id,previous_score,delta_score,'regression','draft_pass60_margin5_regress10_gap20',raw_score_gap,comparison_status
FROM evidence WHERE comparison_status='comparable' AND delta_score<=-10
UNION ALL
SELECT exam_batch_id,exam_name,school_id,school_name,class_name,student_id,subject,score_value,full_score,pass_score,
 previous_batch_id,previous_score,delta_score,'raw_gap_imbalance','draft_pass60_margin5_regress10_gap20',raw_score_gap,comparison_status
FROM evidence WHERE subject_count>=2 AND raw_score_gap>=20 AND has_failed_subject=1 AND score_value IS NOT NULL
