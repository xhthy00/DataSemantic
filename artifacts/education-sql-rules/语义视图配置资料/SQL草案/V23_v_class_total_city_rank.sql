-- V23 班级六门双口径排名：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：整班>=10，在籍、排除其他及未知校类，方向内有效总分>=3
-- 草案口径：同时输出全部方向和所有合格方向，is_majority_track标多数；并列多数均保留
-- 草案口径：默认展示all或is_majority_track=1；排名先在完整方向池完成
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
), eligible AS (
SELECT exam_batch_id,exam_name,school_name,class_name,COUNT(*) AS class_total_count
FROM ov WHERE student_status='在籍生' AND school_type IS NOT NULL AND school_type NOT LIKE '%其他%'
GROUP BY exam_batch_id,exam_name,school_name,class_name HAVING COUNT(*)>=10
), class_pools AS (
SELECT o.exam_batch_id,o.exam_name,o.school_name,o.class_name,'all' AS ranking_scope,'全部方向' AS track,
 COUNT(o.total6) AS student_count,AVG(o.total6) AS mean_total
FROM ov o JOIN eligible e ON o.exam_batch_id=e.exam_batch_id AND o.school_name=e.school_name AND o.class_name=e.class_name
WHERE o.student_status='在籍生' AND o.total6 IS NOT NULL
GROUP BY o.exam_batch_id,o.exam_name,o.school_name,o.class_name
UNION ALL
SELECT o.exam_batch_id,o.exam_name,o.school_name,o.class_name,'track',o.track,
 COUNT(o.total6),AVG(o.total6)
FROM ov o JOIN eligible e ON o.exam_batch_id=e.exam_batch_id AND o.school_name=e.school_name AND o.class_name=e.class_name
WHERE o.student_status='在籍生' AND o.total6 IS NOT NULL AND o.track IS NOT NULL
GROUP BY o.exam_batch_id,o.exam_name,o.school_name,o.class_name,o.track HAVING COUNT(o.total6)>=3
), ranked AS (
SELECT *,RANK() OVER(PARTITION BY exam_batch_id,exam_name,ranking_scope,track ORDER BY mean_total DESC) AS city_rank,
 COUNT(*) OVER(PARTITION BY exam_batch_id,exam_name,ranking_scope,track) AS pool_class_count,
 MAX(CASE WHEN ranking_scope='track' THEN student_count ELSE NULL END) OVER(PARTITION BY exam_batch_id,exam_name,school_name,class_name) AS majority_count
FROM class_pools
)
SELECT *,ROUND(mean_total,2) AS average_total,
 CASE WHEN ranking_scope='all' THEN 0 WHEN student_count=majority_count THEN 1 ELSE 0 END AS is_majority_track
FROM ranked
