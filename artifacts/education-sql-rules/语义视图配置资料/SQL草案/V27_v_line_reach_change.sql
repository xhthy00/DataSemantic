-- V27 达线较上场变化：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：前场按同届+考试类型+归属学校内时间排序，相同日期按ID稳定排序
-- 草案口径：某校没参加该前场时留NULL，不自动跳到更早一次
-- 草案口径：缺届次/日期不比较；阈值变化返回提示
WITH batches AS (
 SELECT id AS exam_batch_id,batch_name,exam_time,CAST(jc AS VARCHAR) AS cohort_year,exam_type,school_id,
 CASE WHEN jc IS NULL OR exam_time IS NULL THEN NULL ELSE
 LAG(id) OVER(PARTITION BY jc,exam_type,school_id ORDER BY exam_time,id) END AS previous_batch_id
 FROM tb_exam_batch WHERE jc IS NOT NULL AND CAST(jc AS VARCHAR)<>'' AND exam_time IS NOT NULL
), aggregated AS (
SELECT exam_batch_id,school_id,school_name,district,track,line_code,line_name,
 SUM(candidates) AS candidate_count,SUM(reached_count) AS reached_count,
 MIN(CAST(threshold AS DOUBLE)) AS min_threshold,MAX(CAST(threshold AS DOUBLE)) AS max_threshold
FROM tb_score_indicator GROUP BY exam_batch_id,school_id,school_name,district,track,line_code,line_name
), compared AS (
SELECT a.*,b.previous_batch_id,b.cohort_year,p.candidate_count AS previous_candidates,
 p.reached_count AS previous_count,p.min_threshold AS previous_min_threshold,p.max_threshold AS previous_max_threshold,
 ROUND(100.0*a.reached_count/NULLIF(a.candidate_count,0),2) AS current_rate,
 ROUND(100.0*p.reached_count/NULLIF(p.candidate_count,0),2) AS previous_rate
FROM aggregated a LEFT JOIN batches b ON a.exam_batch_id=b.exam_batch_id
LEFT JOIN aggregated p ON p.exam_batch_id=b.previous_batch_id AND p.school_id=a.school_id AND p.track=a.track AND p.line_code=a.line_code
)
SELECT *,reached_count AS current_count,reached_count-previous_count AS count_delta,
 ROUND(current_rate-previous_rate,2) AS rate_delta_pp,
 CASE WHEN min_threshold=max_threshold AND previous_min_threshold=previous_max_threshold AND min_threshold=previous_min_threshold THEN 0 ELSE 1 END AS threshold_change_or_unknown
FROM compared
