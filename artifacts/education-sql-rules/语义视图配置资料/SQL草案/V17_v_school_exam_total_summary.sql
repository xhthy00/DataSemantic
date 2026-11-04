-- V17 学校三门四门六门总均分：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：不默认合并在籍和市报，student_status作为输出分组
-- 草案口径：总分非空且包括真实0分
-- 草案口径：三门总均分不除以3，六门直接读zf6m
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
), totals AS (
 SELECT exam_batch_id,exam_name,school_name,district,track,student_status,'three' AS total_type,total3 AS total_score FROM ov
 UNION ALL SELECT exam_batch_id,exam_name,school_name,district,track,student_status,'four',total4 FROM ov
 UNION ALL SELECT exam_batch_id,exam_name,school_name,district,track,student_status,'six',total6 FROM ov
)
SELECT exam_batch_id,exam_name,school_name,district,track,student_status,total_type,
 COUNT(total_score) AS valid_count,SUM(total_score) AS total_score_sum,
 ROUND(AVG(total_score),2) AS average_total
FROM totals GROUP BY exam_batch_id,exam_name,school_name,district,track,student_status,total_type
