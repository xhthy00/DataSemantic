-- V41 学校类别达线比较：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：精确按COALESCE(s_name,name)匹配，名称不唯一不任取一所学校
-- 草案口径：匹配失败/歧义保留独立mapping_status，不丢候选人数、不扩行
-- 草案口径：使用当前学校类别，历史类别需后续快照维度；各线种独立汇总
WITH school_mapping AS (
SELECT COALESCE(s_name,name) AS school_label,COUNT(*) AS mapping_count,
 CASE WHEN COUNT(*)=1 THEN MAX(type) ELSE NULL END AS school_type
FROM tb_school GROUP BY COALESCE(s_name,name)
), mapped AS (
SELECT i.*,m.school_type,
 CASE WHEN m.mapping_count IS NULL THEN 'unmatched' WHEN m.mapping_count>1 THEN 'ambiguous' ELSE 'matched' END AS mapping_status
FROM tb_score_indicator i LEFT JOIN school_mapping m ON i.school_name=m.school_label
)
SELECT exam_batch_id,exam_name,school_type,mapping_status,track,line_code,line_name,
 SUM(candidates) AS candidate_count,SUM(reached_count) AS reached_count,
 ROUND(100.0*SUM(reached_count)/NULLIF(SUM(candidates),0),2) AS reach_rate,
 SUM(CASE WHEN mapping_status<>'matched' THEN candidates ELSE 0 END) AS unmapped_candidate_count
FROM mapped GROUP BY exam_batch_id,exam_name,school_type,mapping_status,track,line_code,line_name
