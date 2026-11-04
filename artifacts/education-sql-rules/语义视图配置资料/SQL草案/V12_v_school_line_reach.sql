SELECT exam_batch_id, exam_name, school_id, school_name, district, track, line_code, line_name,
       MIN(CAST(threshold AS DECIMAL(18,4))) AS min_threshold,
       MAX(CAST(threshold AS DECIMAL(18,4))) AS max_threshold,
       SUM(candidates) AS candidate_count,
       SUM(reached_count) AS reached_count,
       ROUND(100.0*SUM(reached_count)/NULLIF(SUM(candidates),0),2) AS reach_rate
FROM tb_score_indicator
GROUP BY exam_batch_id, exam_name, school_id, school_name, district, track, line_code, line_name
