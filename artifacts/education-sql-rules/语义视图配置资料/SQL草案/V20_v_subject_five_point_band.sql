-- V20 学科五分段及累计人数：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：化生政地使用转换分，其他使用原始分
-- 草案口径：xkkm确认选科，真实0单独成段；缺分不补0
-- 草案口径：小数先FLOOR，学生性质分开统计
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
), subject_rows AS (
SELECT overview_id,exam_batch_id,exam_name,student_id,school_name,district,class_name,cohort_year,student_status,school_type,subject_combination,track,'语文' AS subject,yw AS raw_score,CAST(NULL AS DOUBLE) AS assigned_score,CAST(NULL AS VARCHAR) AS assigned_grade,'raw' AS score_type,yw AS comparable_score,1 AS selected_flag FROM ov
UNION ALL
SELECT overview_id,exam_batch_id,exam_name,student_id,school_name,district,class_name,cohort_year,student_status,school_type,subject_combination,track,'数学' AS subject,sx AS raw_score,CAST(NULL AS DOUBLE) AS assigned_score,CAST(NULL AS VARCHAR) AS assigned_grade,'raw' AS score_type,sx AS comparable_score,1 AS selected_flag FROM ov
UNION ALL
SELECT overview_id,exam_batch_id,exam_name,student_id,school_name,district,class_name,cohort_year,student_status,school_type,subject_combination,track,'英语' AS subject,yy AS raw_score,CAST(NULL AS DOUBLE) AS assigned_score,CAST(NULL AS VARCHAR) AS assigned_grade,'raw' AS score_type,yy AS comparable_score,1 AS selected_flag FROM ov
UNION ALL
SELECT overview_id,exam_batch_id,exam_name,student_id,school_name,district,class_name,cohort_year,student_status,school_type,subject_combination,track,'物理' AS subject,wl AS raw_score,CAST(NULL AS DOUBLE) AS assigned_score,CAST(NULL AS VARCHAR) AS assigned_grade,'raw' AS score_type,wl AS comparable_score,CASE WHEN subject_combination IS NULL OR subject_combination='' THEN NULL WHEN subject_combination LIKE '%物%' THEN 1 ELSE 0 END AS selected_flag FROM ov
UNION ALL
SELECT overview_id,exam_batch_id,exam_name,student_id,school_name,district,class_name,cohort_year,student_status,school_type,subject_combination,track,'历史' AS subject,ls AS raw_score,CAST(NULL AS DOUBLE) AS assigned_score,CAST(NULL AS VARCHAR) AS assigned_grade,'raw' AS score_type,ls AS comparable_score,CASE WHEN subject_combination IS NULL OR subject_combination='' THEN NULL WHEN subject_combination LIKE '%史%' OR subject_combination LIKE '%历%' THEN 1 ELSE 0 END AS selected_flag FROM ov
UNION ALL
SELECT overview_id,exam_batch_id,exam_name,student_id,school_name,district,class_name,cohort_year,student_status,school_type,subject_combination,track,'化学' AS subject,hx AS raw_score,hxzh AS assigned_score,hxdj AS assigned_grade,'assigned' AS score_type,hxzh AS comparable_score,CASE WHEN subject_combination IS NULL OR subject_combination='' THEN NULL WHEN subject_combination LIKE '%化%' THEN 1 ELSE 0 END AS selected_flag FROM ov
UNION ALL
SELECT overview_id,exam_batch_id,exam_name,student_id,school_name,district,class_name,cohort_year,student_status,school_type,subject_combination,track,'生物' AS subject,sw AS raw_score,swzh AS assigned_score,swdj AS assigned_grade,'assigned' AS score_type,swzh AS comparable_score,CASE WHEN subject_combination IS NULL OR subject_combination='' THEN NULL WHEN subject_combination LIKE '%生%' THEN 1 ELSE 0 END AS selected_flag FROM ov
UNION ALL
SELECT overview_id,exam_batch_id,exam_name,student_id,school_name,district,class_name,cohort_year,student_status,school_type,subject_combination,track,'政治' AS subject,zz AS raw_score,zzzh AS assigned_score,zzdj AS assigned_grade,'assigned' AS score_type,zzzh AS comparable_score,CASE WHEN subject_combination IS NULL OR subject_combination='' THEN NULL WHEN subject_combination LIKE '%政%' THEN 1 ELSE 0 END AS selected_flag FROM ov
UNION ALL
SELECT overview_id,exam_batch_id,exam_name,student_id,school_name,district,class_name,cohort_year,student_status,school_type,subject_combination,track,'地理' AS subject,dl AS raw_score,dlzh AS assigned_score,dldj AS assigned_grade,'assigned' AS score_type,dlzh AS comparable_score,CASE WHEN subject_combination IS NULL OR subject_combination='' THEN NULL WHEN subject_combination LIKE '%地%' THEN 1 ELSE 0 END AS selected_flag FROM ov
), labeled AS (
SELECT *,CASE WHEN comparable_score=0 THEN 0 ELSE FLOOR((FLOOR(comparable_score)-1)/5)*5+1 END AS band_lower
FROM subject_rows WHERE selected_flag=1 AND comparable_score IS NOT NULL AND comparable_score>=0
), hist AS (
SELECT exam_batch_id,exam_name,school_name,district,student_status,subject,score_type,band_lower,COUNT(*) AS band_count
FROM labeled GROUP BY exam_batch_id,exam_name,school_name,district,student_status,subject,score_type,band_lower
)
SELECT *,CASE WHEN band_lower=0 THEN 0 ELSE band_lower+4 END AS band_upper,
 SUM(band_count) OVER(PARTITION BY exam_batch_id,exam_name,school_name,district,student_status,subject,score_type) AS valid_count,
 ROUND(100.0*band_count/NULLIF(SUM(band_count) OVER(PARTITION BY exam_batch_id,exam_name,school_name,district,student_status,subject,score_type),0),2) AS band_rate,
 SUM(band_count) OVER(PARTITION BY exam_batch_id,exam_name,school_name,district,student_status,subject,score_type ORDER BY band_lower DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_count
FROM hist
