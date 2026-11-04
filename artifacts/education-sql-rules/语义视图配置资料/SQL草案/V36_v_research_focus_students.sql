-- V36 尖子生与压线薄弱学生：SQL草案，尚待业务确认。
-- 使用原始tb_*逻辑模型；本次未查询真实业务库。
-- 草案口径：只输出匿名学生ID，三类名单独立list_type，跨名单不能直接相加人数
-- 草案口径：尖子生仅引领校、物理前100/历史前30含并列；尖子班按实际名单
-- 草案口径：压线保留旧科目特殊比较J12，但改用选科标识保留真实0，必须逐项确认
-- 草案口径：同一学生命中多条关注线时均保留线种，不沿用旧首条break；这是一项明确草案差异
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
), line_members AS (
SELECT o.*,l.line_code,l.line_name,l.threshold,
 SUM(CASE WHEN o.total6=l.threshold THEN 1 ELSE 0 END) OVER(PARTITION BY o.exam_batch_id,o.track,l.line_code) AS exact_count,
 ROW_NUMBER() OVER(PARTITION BY o.exam_batch_id,o.track,l.line_code ORDER BY o.total6,o.student_id,o.overview_id) AS reached_position
FROM ov o JOIN cutoff_lines l ON o.exam_batch_id=l.exam_batch_id AND o.track=l.track
WHERE o.student_status='在籍生' AND o.total6>=l.threshold AND l.threshold>0
), chosen AS (
SELECT * FROM line_members WHERE (exact_count>0 AND total6=threshold) OR (exact_count=0 AND reached_position=1)
), contributions AS (
SELECT c.exam_batch_id,c.exam_name,c.track,c.line_code,c.line_name,c.threshold,s.subject,s.score_type,
 AVG(s.comparable_score) AS contribution_score,COUNT(s.comparable_score) AS sample_count,
 MAX(CASE WHEN c.exact_count>0 THEN 'exact_cutoff_students' ELSE 'one_lowest_reached_student' END) AS sample_policy
FROM chosen c JOIN subject_rows s ON c.overview_id=s.overview_id
WHERE s.selected_flag=1 AND s.comparable_score IS NOT NULL
GROUP BY c.exam_batch_id,c.exam_name,c.track,c.line_code,c.line_name,c.threshold,s.subject,s.score_type
), student_rank AS (
SELECT *,RANK() OVER(PARTITION BY exam_batch_id,track ORDER BY total6 DESC) AS total_rank
FROM ov WHERE student_status='在籍生' AND total6 IS NOT NULL AND track IS NOT NULL
), focus_rows AS (
SELECT s.*,o.total6,r.total_rank FROM subject_rows s JOIN ov o ON s.overview_id=o.overview_id
LEFT JOIN student_rank r ON s.overview_id=r.overview_id
)
SELECT s.exam_batch_id,s.exam_name,s.student_id,s.school_name,s.class_name,s.subject,s.track,
 'elite_student' AS list_type,s.total6 AS total_score,CAST(NULL AS VARCHAR) AS line_code,
 s.comparable_score AS subject_score,CAST(NULL AS DOUBLE) AS reference_score
FROM focus_rows s
WHERE s.selected_flag=1 AND s.comparable_score IS NOT NULL AND s.student_status='在籍生'
 AND s.school_type LIKE '%引领%'
 AND ((s.track='物理类' AND s.total_rank<=100 AND s.subject NOT IN ('政治','历史'))
 OR (s.track='历史类' AND s.total_rank<=30 AND s.subject NOT IN ('物理','化学','生物')))
UNION ALL
SELECT s.exam_batch_id,s.exam_name,s.student_id,s.school_name,s.class_name,s.subject,s.track,
 'cutoff_weak',s.total6,c.line_code,s.comparable_score,c.contribution_score
FROM focus_rows s JOIN contributions c ON s.exam_batch_id=c.exam_batch_id AND s.track=c.track AND s.subject=c.subject
WHERE s.student_status='在籍生' AND s.selected_flag=1 AND s.comparable_score IS NOT NULL
 AND s.total6>=c.threshold-10 AND s.total6<c.threshold
 AND ((s.school_type LIKE '%引领%' AND c.line_code IN ('211','tz'))
 OR (s.school_type LIKE '%支撑%' AND c.line_code IN ('tz','bk'))
 OR ((s.school_type IS NULL OR (s.school_type NOT LIKE '%引领%' AND s.school_type NOT LIKE '%支撑%')) AND c.line_code='bk'))
 AND NOT (s.subject IN ('物理','化学','生物') AND s.track<>'物理类')
 AND NOT (s.subject='历史' AND s.track<>'历史类')
 AND (CASE WHEN s.subject='语文' THEN s.comparable_score < FLOOR(c.contribution_score+0.5)-CASE WHEN c.contribution_score>=105 AND c.contribution_score<108 THEN 1 ELSE 0 END
 WHEN s.subject='历史' THEN s.comparable_score<c.contribution_score-1
 WHEN s.subject='化学' THEN s.comparable_score<FLOOR(c.contribution_score+0.5)
 WHEN s.subject='政治' AND s.track='物理类' THEN s.comparable_score<FLOOR(c.contribution_score)
 WHEN s.subject IN ('生物','政治','地理') THEN s.comparable_score<c.contribution_score
 ELSE s.comparable_score<=c.contribution_score END)
UNION ALL
SELECT s.exam_batch_id,s.exam_name,s.student_id,s.school_name,s.class_name,s.subject,s.track,
 'elite_class',s.total6,NULL,s.comparable_score,NULL
FROM focus_rows s WHERE s.student_status='在籍生' AND s.selected_flag=1 AND s.comparable_score IS NOT NULL
AND EXISTS(SELECT 1 FROM tb_elite_class ec WHERE ec.exam_batch_id=s.exam_batch_id AND ec.school_id=s.school_name
AND ec.class_name=s.class_name AND (ec.track='' OR ec.track=s.track))
