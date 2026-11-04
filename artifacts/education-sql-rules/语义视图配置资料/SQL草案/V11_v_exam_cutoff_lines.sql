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
