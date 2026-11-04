SELECT id AS overview_id, exam_batch_id, exam_name, anon_stu_id AS student_id,
       xx AS school_name, dq AS district, bj AS class_name, jc AS cohort_year,
       xkkm AS subject_combination, xsxz AS student_status, xxlb AS school_type,
       CASE WHEN xkkm LIKE '物%' THEN '物理类' WHEN xkkm LIKE '史%' OR xkkm LIKE '历%' THEN '历史类' ELSE NULL END AS track,
       CAST(zf3m AS DECIMAL(18,4)) AS three_subject_total,
       CAST(zf4m AS DECIMAL(18,4)) AS four_subject_total,
       CAST(zf6m AS DECIMAL(18,4)) AS six_subject_total
FROM tb_score_overview
