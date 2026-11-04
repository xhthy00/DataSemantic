-- V24 位次前N分数阈值及人数：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：在籍、总分非空且保留0
-- 草案口径：按第N个排序位置分数切线，所有同分均纳入
-- 草案口径：N大于池人数时取全体最低分作为切线，并返回pool_count
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
), buckets AS (SELECT '物理类' AS track,10 AS bucket_n UNION ALL SELECT '物理类' AS track,20 AS bucket_n UNION ALL SELECT '物理类' AS track,50 AS bucket_n UNION ALL SELECT '物理类' AS track,100 AS bucket_n UNION ALL SELECT '物理类' AS track,200 AS bucket_n UNION ALL SELECT '物理类' AS track,500 AS bucket_n UNION ALL SELECT '物理类' AS track,1000 AS bucket_n UNION ALL SELECT '物理类' AS track,2000 AS bucket_n UNION ALL SELECT '历史类' AS track,10 AS bucket_n UNION ALL SELECT '历史类' AS track,20 AS bucket_n UNION ALL SELECT '历史类' AS track,50 AS bucket_n UNION ALL SELECT '历史类' AS track,100 AS bucket_n UNION ALL SELECT '历史类' AS track,200 AS bucket_n UNION ALL SELECT '历史类' AS track,500 AS bucket_n), ranked AS (
SELECT *,ROW_NUMBER() OVER(PARTITION BY exam_batch_id,exam_name,track ORDER BY total6 DESC,student_id,overview_id) AS position_no,
 COUNT(*) OVER(PARTITION BY exam_batch_id,exam_name,track) AS pool_count
FROM ov WHERE student_status='在籍生' AND track IS NOT NULL AND total6 IS NOT NULL
), cuts AS (
SELECT r.exam_batch_id,r.exam_name,r.track,b.bucket_n,MAX(r.pool_count) AS pool_count,
 MIN(CASE WHEN r.position_no<=b.bucket_n THEN r.total6 ELSE NULL END) AS cutoff_score
FROM ranked r JOIN buckets b ON r.track=b.track GROUP BY r.exam_batch_id,r.exam_name,r.track,b.bucket_n
)
SELECT c.exam_batch_id,c.exam_name,c.track,c.bucket_n,c.cutoff_score,c.pool_count,
 r.school_name,COUNT(*) AS included_count
FROM cuts c JOIN ranked r ON c.exam_batch_id=r.exam_batch_id AND c.track=r.track AND r.total6>=c.cutoff_score
GROUP BY c.exam_batch_id,c.exam_name,c.track,c.bucket_n,c.cutoff_score,c.pool_count,r.school_name
