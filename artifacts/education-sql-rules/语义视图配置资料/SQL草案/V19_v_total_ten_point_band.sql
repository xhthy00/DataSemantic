-- V19 总分十分段及累计人数：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：小数先FLOOR再按1–10、11–20分箱
-- 草案口径：真实0分单独0–0段，负分不参与
-- 草案口径：区县×校类×学生性质保留为独立切片；不把各切片累计率相加
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
), labeled AS (
SELECT *,CASE WHEN total6=0 THEN 0 ELSE FLOOR((FLOOR(total6)-1)/10)*10+1 END AS band_lower
FROM ov WHERE total6 IS NOT NULL AND total6>=0
), hist AS (
SELECT exam_batch_id,exam_name,track,district,school_type,student_status,band_lower,
 COUNT(*) AS band_count
FROM labeled GROUP BY exam_batch_id,exam_name,track,district,school_type,student_status,band_lower
)
SELECT *,CASE WHEN band_lower=0 THEN 0 ELSE band_lower+9 END AS band_upper,
 SUM(band_count) OVER(PARTITION BY exam_batch_id,exam_name,track,district,school_type,student_status) AS denominator_count,
 ROUND(100.0*band_count/NULLIF(SUM(band_count) OVER(PARTITION BY exam_batch_id,exam_name,track,district,school_type,student_status),0),2) AS band_rate,
 SUM(band_count) OVER(PARTITION BY exam_batch_id,exam_name,track,district,school_type,student_status ORDER BY band_lower DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_count,
 ROUND(100.0*SUM(band_count) OVER(PARTITION BY exam_batch_id,exam_name,track,district,school_type,student_status ORDER BY band_lower DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)/NULLIF(SUM(band_count) OVER(PARTITION BY exam_batch_id,exam_name,track,district,school_type,student_status),0),2) AS cumulative_rate
FROM hist
