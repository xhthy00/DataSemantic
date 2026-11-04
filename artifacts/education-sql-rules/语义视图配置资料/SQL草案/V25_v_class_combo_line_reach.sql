-- V25 班级和组合达线：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：有效六门总分作分母，NULL总分只进recorded_count不进candidate_count
-- 草案口径：所有实际组合保留，包括历史组合；六种物理组合可在外层筛
-- 草案口径：学生性质单独分组；每批次预测线必须唯一
WITH ov AS (
SELECT o.id AS overview_id,o.exam_batch_id,o.exam_name,
 o.anon_stu_id AS student_id,o.xx AS school_name,o.dq AS district,
 o.bj AS class_name,o.jc AS cohort_year,o.xsxz AS student_status,
 o.xxlb AS school_type,o.xkkm AS subject_combination,
 CASE WHEN o.xkkm LIKE '物%' THEN '物理类' WHEN o.xkkm LIKE '史%' OR o.xkkm LIKE '历%' THEN '历史类' ELSE NULL END AS track,
 CAST(o.zf3m AS DOUBLE) AS total3,CAST(o.zf4m AS DOUBLE) AS total4,
 CAST(o.zf6m AS DOUBLE) AS total6,
 CAST(o.yw AS DOUBLE) AS yw,CAST(o.sx AS DOUBLE) AS sx,CAST(o.yy AS DOUBLE) AS yy,
 CAST(o.wl AS DOUBLE) AS wl,CAST(o.ls AS DOUBLE) AS ls,
 CAST(o.hx AS DOUBLE) AS hx,CAST(o.sw AS DOUBLE) AS sw,CAST(o.zz AS DOUBLE) AS zz,CAST(o.dl AS DOUBLE) AS dl,
 CAST(o.hxzh AS DOUBLE) AS hxzh,CAST(o.swzh AS DOUBLE) AS swzh,
 CAST(o.zzzh AS DOUBLE) AS zzzh,CAST(o.dlzh AS DOUBLE) AS dlzh,
 o.hxdj,o.swdj,o.zzdj,o.dldj
FROM tb_score_overview o
), cutoff_lines AS (
SELECT exam_batch_id,exam_name,'物理类' AS track,'tz' AS line_code,'特控线' AS line_name,CAST(wl_score_tz AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE wl_score_tz IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'物理类' AS track,'bk' AS line_code,'本科线' AS line_name,CAST(wl_score_bk AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE wl_score_bk IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'物理类' AS track,'ty' AS line_code,'体育线' AS line_name,CAST(wl_score_ty AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE wl_score_ty IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'物理类' AS track,'ms' AS line_code,'美术线' AS line_name,CAST(wl_socre_ms AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE wl_socre_ms IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'物理类' AS track,'yy' AS line_code,'音乐线' AS line_name,CAST(wl_score_yy AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE wl_score_yy IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'物理类' AS track,'211' AS line_code,'211线' AS line_name,CAST(wl_score_211 AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE wl_score_211 IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'物理类' AS track,'985' AS line_code,'985线' AS line_name,CAST(wl_score_985 AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE wl_score_985 IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'物理类' AS track,'qb' AS line_code,'清北线' AS line_name,CAST(wl_score_qb AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE wl_score_qb IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'物理类' AS track,'nd' AS line_code,'南大线' AS line_name,CAST(wl_score_nd AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE wl_score_nd IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'历史类' AS track,'tz' AS line_code,'特控线' AS line_name,CAST(ls_score_tz AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE ls_score_tz IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'历史类' AS track,'bk' AS line_code,'本科线' AS line_name,CAST(ls_score_bk AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE ls_score_bk IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'历史类' AS track,'ty' AS line_code,'体育线' AS line_name,CAST(ls_score_ty AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE ls_score_ty IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'历史类' AS track,'ms' AS line_code,'美术线' AS line_name,CAST(ls_score_ms AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE ls_score_ms IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'历史类' AS track,'yy' AS line_code,'音乐线' AS line_name,CAST(ls_score_yy AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE ls_score_yy IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'历史类' AS track,'211' AS line_code,'211线' AS line_name,CAST(ls_score_211 AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE ls_score_211 IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'历史类' AS track,'985' AS line_code,'985线' AS line_name,CAST(ls_score_985 AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE ls_score_985 IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'历史类' AS track,'qb' AS line_code,'清北线' AS line_name,CAST(ls_score_qb AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE ls_score_qb IS NOT NULL
UNION ALL
SELECT exam_batch_id,exam_name,'历史类' AS track,'nd' AS line_code,'南大线' AS line_name,CAST(ls_score_nd AS DECIMAL(18,4)) AS threshold FROM tb_fraction_bar WHERE ls_score_nd IS NOT NULL
), student_lines AS (
SELECT o.*,l.line_code,l.line_name,l.threshold,o.total6-l.threshold AS distance_to_line
FROM ov o JOIN cutoff_lines l ON o.exam_batch_id=l.exam_batch_id AND o.track=l.track
WHERE l.threshold>0
)
SELECT exam_batch_id,exam_name,school_name,class_name,track,subject_combination,student_status,
 line_code,line_name,threshold,COUNT(*) AS recorded_count,COUNT(total6) AS candidate_count,
 SUM(CASE WHEN total6>=threshold THEN 1 ELSE 0 END) AS reached_count,
 ROUND(100.0*SUM(CASE WHEN total6>=threshold THEN 1 ELSE 0 END)/NULLIF(COUNT(total6),0),2) AS reach_rate
FROM student_lines GROUP BY exam_batch_id,exam_name,school_name,class_name,track,subject_combination,student_status,line_code,line_name,threshold
