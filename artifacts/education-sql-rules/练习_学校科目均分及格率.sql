WITH base AS (
  SELECT
    b.exam_batch_id,
    b.exam_name,
    s.school_id,
    c.school_name,
    p.subject,
    CAST(s.score AS DECIMAL(18, 4)) AS score_value,
    CAST(p.full_score AS DECIMAL(18, 4)) AS full_score
  FROM exam_scores s
  JOIN exam_papers p ON s.paper_id = p.paper_id
  JOIN exam_batches b ON p.exam_batch_id = b.exam_batch_id
  LEFT JOIN schools c ON s.school_id = c.school_id
), judged AS (
  SELECT *,
    CASE
      WHEN score_value IS NULL OR full_score IS NULL
           OR full_score <= 0 THEN NULL
      WHEN score_value >= full_score * 0.60 THEN 1
      ELSE 0
    END AS pass_flag
  FROM base
)
SELECT
  exam_batch_id,
  exam_name,
  school_id,
  school_name,
  subject,
  COUNT(score_value) AS valid_count,
  ROUND(AVG(score_value), 2) AS average_score,
  COALESCE(SUM(pass_flag), 0) AS pass_count,
  COUNT(pass_flag) AS classified_count,
  COUNT(score_value) - COUNT(pass_flag) AS unclassified_count,
  ROUND(
    100.0 * SUM(pass_flag) / NULLIF(COUNT(pass_flag), 0),
    2
  ) AS pass_rate
FROM judged
GROUP BY exam_batch_id, exam_name, school_id, school_name, subject
