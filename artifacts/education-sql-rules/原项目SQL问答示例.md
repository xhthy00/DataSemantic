# 原项目 SQL 问答示例（原样摘录）

用途：追溯现有提示词。以下是旧项目示例，含旧零分口径、样例考试及部分待确认写法；不是已经校验的 MDL 语义视图，也不要整页粘贴到 Studio。

## E01 南京市第一中学高一(1)班数学平均分和人数

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT sch.name AS school,
       sc.class,
       sc.subject_name,
       sc.exam_score,
       COUNT(*) AS cnt,
       ROUND(AVG(sc.score), 2) AS avg_score
FROM tb_score sc
JOIN tb_school sch ON sc.school_id = sch.id
WHERE sch.name = '南京市第一中学'
  AND sc.class = '高一(1)班'
  AND sc.subject_name = '数学'
GROUP BY sch.name, sc.class, sc.subject_name, sc.exam_score
LIMIT 1000;
-- 及格率/优秀率：查明细 score+exam_score 后用 compute_score_stats_tool，禁止在 SQL 写死 0.6/0.85
```

## E02 对比三所学校数学均分排名

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT sch.name AS school,
       ROUND(AVG(sc.score), 2) AS class_avg,
       RANK() OVER (ORDER BY AVG(sc.score) DESC) AS rank
FROM tb_score sc
JOIN tb_school sch ON sc.school_id = sch.id
WHERE sc.subject_name = '数学'
GROUP BY sch.name
ORDER BY rank
LIMIT 1000;
```

## E03 南京市第一中学数学分数段分布

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT
  CASE
    WHEN sc.score < sc.exam_score * 0.6 THEN '0-60%'
    WHEN sc.score < sc.exam_score * 0.7 THEN '60-70%'
    WHEN sc.score < sc.exam_score * 0.8 THEN '70-80%'
    WHEN sc.score < sc.exam_score * 0.9 THEN '80-90%'
    ELSE '90-100%'
  END AS segment,
  COUNT(*) AS cnt
FROM tb_score sc
JOIN tb_school sch ON sc.school_id = sch.id
WHERE sch.name = '南京市第一中学' AND sc.subject_name = '数学'
GROUP BY segment
ORDER BY segment
LIMIT 1000;
-- 上表为相对满分的分数段分布（展示用）；及格/优秀线以异常规则配置为准，勿与 0.6/0.85 混淆
```

## E04 STU20240001 本次数学成绩

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT sc.student_id, sc.subject_name, sc.score, sc.exam_score
FROM tb_score sc
WHERE sc.student_id = 'STU20240001' AND sc.subject_name = '数学'
LIMIT 1000;
```

## E05 南京市第一中学数学每一小题得分率及关联知识点

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT sd.question_no,
       COALESCE(kn.knowledge_name, '未关联知识点') AS knowledge_name,
       eq.question_score AS full_score,
       ROUND(AVG(sd.score), 2) AS avg_score,
       ROUND(AVG(sd.score)::numeric / NULLIF(eq.question_score, 0) * 100, 2) AS score_rate
FROM tb_score_detail sd
JOIN tb_exam_question eq ON sd.question_id = eq.id
LEFT JOIN (
  SELECT eqk.question_id,
         string_agg(DISTINCT k.knowledge_name, '、' ORDER BY k.knowledge_name) AS knowledge_name
  FROM tb_exam_question_knowledge eqk
  JOIN tb_knowledge k ON k.id = eqk.knowledge_id
  GROUP BY eqk.question_id
) kn ON kn.question_id = eq.id
JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id
JOIN tb_school sch ON sc.school_id = sch.id
WHERE sch.name = '南京市第一中学' AND sc.subject_name = '数学'
GROUP BY sd.question_no, kn.knowledge_name, eq.question_score
ORDER BY sd.question_no
LIMIT 1000;
```

## E06 南京市第一中学数学知识点薄弱诊断

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT COALESCE(k.knowledge_name, '未关联知识点') AS knowledge_name,
       ROUND(SUM(sd.score * COALESCE(eqk.w_norm, 1))::numeric
             / NULLIF(SUM(eq.question_score * COALESCE(eqk.w_norm, 1)), 0) * 100, 2) AS score_rate,
       COUNT(DISTINCT sd.question_no) AS question_count
FROM tb_score_detail sd
JOIN tb_exam_question eq ON sd.question_id = eq.id
LEFT JOIN (
  SELECT question_id, knowledge_id,
         weight / NULLIF(SUM(weight) OVER (PARTITION BY question_id), 0) AS w_norm
  FROM tb_exam_question_knowledge
) eqk ON eqk.question_id = eq.id
LEFT JOIN tb_knowledge k ON k.id = eqk.knowledge_id
JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id
JOIN tb_school sch ON sc.school_id = sch.id
WHERE sch.name = '南京市第一中学' AND sc.subject_name = '数学'
GROUP BY k.knowledge_name
ORDER BY score_rate ASC
LIMIT 1000;
```

## E07 南京市各区县数学均分对比

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT sch.district,
       COUNT(*) AS cnt,
       ROUND(AVG(sc.score), 2) AS avg_score
FROM tb_score sc
JOIN tb_school sch ON sc.school_id = sch.id
WHERE sc.subject_name = '数学'
GROUP BY sch.district
ORDER BY avg_score DESC
LIMIT 1000;
```

## E08 按年级汇总数学均分（年级从班级名解析）

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT
  CASE
    WHEN sc.class LIKE '高一%' THEN '高一'
    WHEN sc.class LIKE '高二%' THEN '高二'
    WHEN sc.class LIKE '高三%' THEN '高三'
    WHEN sc.class LIKE '初一%' THEN '初一'
    WHEN sc.class LIKE '初二%' THEN '初二'
    WHEN sc.class LIKE '初三%' THEN '初三'
    ELSE '其他'
  END AS grade,
  ROUND(AVG(sc.score), 2) AS avg_score
FROM tb_score sc
WHERE sc.subject_name = '数学'
GROUP BY grade
ORDER BY grade
LIMIT 1000;
```

## E09 邗江区 2026届高三5月模拟数学均分

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT sch.district,
       ROUND(AVG(sc.score), 2) AS avg_score,
       COUNT(*) AS cnt
FROM tb_score sc
JOIN tb_school sch ON sc.school_id = sch.id
JOIN tb_exam e ON sc.exam_id = e.id
LEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id
WHERE COALESCE(eb.batch_name, e.exam_name) LIKE '%2026届高三5月模拟%'
  AND sch.district = '邗江区'
  AND sc.subject_name = '数学'
GROUP BY sch.district
LIMIT 1000;
-- 「XX考试」按 tb_exam_batch.batch_name 过滤，禁止把试卷名当成考试批次
```

## E10 2026届高三5月模拟物理类本科线是多少

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT exam_name, wl_score_bk AS threshold
FROM tb_fraction_bar
WHERE exam_name = '2026届高三5月模拟'
LIMIT 10;
-- 分数线阈值在 tb_fraction_bar；达线人数/率须查 tb_score_indicator
```

## E11 邗江区 2026届高三5月模拟全科总分均分

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT dq,
       ROUND(AVG(zf6m), 2) AS avg_zf6m,
       COUNT(*) AS cnt
FROM tb_score_overview
WHERE exam_name = '2026届高三5月模拟'
  AND dq = '邗江区'
GROUP BY dq
LIMIT 1000;
-- 全科总分用 tb_score_overview.zf6m；学生标识 anon_stu_id；禁止 xm/sfzh/ksh
```

## E12 2026届高三1月扬州中学物理类均分与全市的比较分析

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT '扬州中学' AS scope, ROUND(AVG(zf6m), 2) AS avg_zf6m, COUNT(*) AS n
FROM tb_score_overview
WHERE exam_name LIKE '%2026届高三1月%'
  AND xkkm LIKE '物%'
  AND xx LIKE '%扬州中学%'
UNION ALL
SELECT '全市' AS scope, ROUND(AVG(zf6m), 2) AS avg_zf6m, COUNT(*) AS n
FROM tb_score_overview
WHERE exam_name LIKE '%2026届高三1月%'
  AND xkkm LIKE '物%'
LIMIT 1000;
-- 两行对比：scope+avg_zf6m+n。overview.xx 是学校明文，用 xx LIKE '%扬州中学%'；全市那一支禁止 xx；禁止 GROUP BY xx 当全市；禁止 xx='GZ_…'（校码不是校名）；物理类=xkkm 不是物理单科；禁止 exam_type / 班级横向报告
```

## E13 2026届高三3月扬州中学对比引领校语文单科

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT '扬州中学' AS scope, ROUND(AVG(yw), 2) AS avg_score, COUNT(*) AS n
FROM tb_score_overview
WHERE exam_name LIKE '%2026届高三3月%'
  AND xx LIKE '%扬州中学%'
  AND xsxz = '在籍生'
  AND yw > 0
UNION ALL
SELECT '引领校' AS scope, ROUND(AVG(yw), 2) AS avg_score, COUNT(*) AS n
FROM tb_score_overview
WHERE exam_name LIKE '%2026届高三3月%'
  AND xxlb LIKE '%引领%'
  AND xsxz = '在籍生'
  AND yw > 0
LIMIT 1000;
-- 语文=yw。缺考 yw=0 不计入均分分母（否则 113.05 会被拉成 112.99）。引领校用 overview.xxlb 且在籍生；禁止 JOIN tb_school 算均分；禁止 GROUP BY xx 再平均；引领校支不要排除扬州中学
```

## E14 扬州中学1月期末各科均分

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT
  COUNT(*) AS n_stu,
  ROUND(AVG(yw) FILTER (WHERE yw > 0), 1) AS 语文,
  COUNT(*) FILTER (WHERE yw > 0) AS 语文人数,
  ROUND(AVG(sx) FILTER (WHERE sx > 0), 1) AS 数学,
  COUNT(*) FILTER (WHERE sx > 0) AS 数学人数,
  ROUND(AVG(yy) FILTER (WHERE yy > 0), 1) AS 英语,
  COUNT(*) FILTER (WHERE yy > 0) AS 英语人数,
  ROUND(AVG(wl) FILTER (WHERE wl > 0), 1) AS 物理,
  COUNT(*) FILTER (WHERE wl > 0) AS 物理人数,
  ROUND(AVG(ls) FILTER (WHERE ls > 0), 1) AS 历史,
  COUNT(*) FILTER (WHERE ls > 0) AS 历史人数,
  ROUND(AVG(hx) FILTER (WHERE hx > 0), 1) AS 化学,
  COUNT(*) FILTER (WHERE hx > 0) AS 化学人数,
  ROUND(AVG(sw) FILTER (WHERE sw > 0), 1) AS 生物,
  COUNT(*) FILTER (WHERE sw > 0) AS 生物人数,
  ROUND(AVG(zz) FILTER (WHERE zz > 0), 1) AS 政治,
  COUNT(*) FILTER (WHERE zz > 0) AS 政治人数,
  ROUND(AVG(dl) FILTER (WHERE dl > 0), 1) AS 地理,
  COUNT(*) FILTER (WHERE dl > 0) AS 地理人数
FROM tb_score_overview
WHERE exam_name LIKE '%1月期末%'
  AND xx LIKE '%扬州中学%'
LIMIT 1000;
-- 未选考/缺考宽表为 0。多科均分必须 AVG(col) FILTER (WHERE col > 0)，禁止 AVG(ls) 除以全体人数（历史会变成个位数）。禁止 WHERE ls>0（会把语数英也滤成选考历史的人）。该科参考人数用 COUNT(*) FILTER
```

## E15 2026届高三1月扬州中学高三(1)班数学成绩全市排名

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
WITH eligible AS (
  SELECT xx, bj
  FROM tb_score_overview
  WHERE exam_name LIKE '%2026届高三1月%'
    AND xsxz = '在籍生'
    AND xxlb NOT LIKE '%其他%'
  GROUP BY xx, bj
  HAVING COUNT(*) >= 10
),
class_avg AS (
  SELECT o.xx, o.bj, ROUND(AVG(o.sx) FILTER (WHERE o.sx > 0), 2) AS avg_sx
  FROM tb_score_overview o
  JOIN eligible e ON e.xx = o.xx AND e.bj = o.bj
  WHERE o.exam_name LIKE '%2026届高三1月%'
    AND o.xsxz = '在籍生'
  GROUP BY o.xx, o.bj
  HAVING COUNT(*) FILTER (WHERE o.sx > 0) >= 3
),
ranked AS (
  SELECT xx, bj, avg_sx,
         RANK() OVER (ORDER BY avg_sx DESC NULLS LAST) AS city_rank,
         COUNT(*) OVER () AS n_class
  FROM class_avg
),
tgt AS (
  SELECT city_rank FROM ranked
  WHERE xx LIKE '%扬州中学%' AND bj LIKE '%高三(1)班%'
)
SELECT xx, bj, avg_sx, city_rank, n_class,
       CASE WHEN xx LIKE '%扬州中学%' AND bj LIKE '%高三(1)班%' THEN '本班' ELSE '' END AS 标记
FROM ranked
WHERE city_rank = 1
   OR city_rank BETWEEN (SELECT city_rank FROM tgt) - 3 AND (SELECT city_rank FROM tgt) + 3;
-- 单科全市班级排名：洗净其他校/整班不足10人，该科有效人数>=3 才进池，RANK ... NULLS LAST。禁止 PARTITION BY bj。返回第1名+目标班前后各3名并标记本班，禁止外层只留目标班一行。数学=sx 且 FILTER sx>0
```

## E16 扬州中学高三(1)班在全市班级中的排名

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
WITH base AS (
  SELECT xx, bj, zf6m,
         CASE WHEN xkkm LIKE '物%' THEN '物理类'
              WHEN xkkm LIKE '史%' OR xkkm LIKE '历%' THEN '历史类'
              ELSE NULL END AS track
  FROM tb_score_overview
  WHERE exam_name LIKE '%2026届高三1月期末%'
    AND xsxz = '在籍生'
    AND zf6m > 0
    AND xxlb NOT LIKE '%其他%'
),
regular AS (
  SELECT xx, bj FROM base GROUP BY xx, bj HAVING COUNT(*) >= 10
),
tgt_n AS (
  SELECT track, COUNT(*) AS n
  FROM base
  WHERE xx LIKE '%扬州中学%' AND bj LIKE '%高三(1)班%' AND track IS NOT NULL
  GROUP BY track
  HAVING COUNT(*) >= 3
),
majority AS (
  SELECT track FROM tgt_n WHERE n = (SELECT MAX(n) FROM tgt_n)
),
track_class AS (
  SELECT b.xx, b.bj, b.track, AVG(b.zf6m) AS avg_zf6m, COUNT(*) AS n_stu
  FROM base b
  JOIN regular r ON r.xx = b.xx AND r.bj = b.bj
  WHERE b.track IN (SELECT track FROM majority)
  GROUP BY b.xx, b.bj, b.track
  HAVING COUNT(*) >= 3
),
track_rank AS (
  SELECT *,
         RANK() OVER (PARTITION BY track ORDER BY avg_zf6m DESC) AS city_rank,
         COUNT(*) OVER (PARTITION BY track) AS n_class
  FROM track_class
),
all_class AS (
  SELECT b.xx, b.bj, AVG(b.zf6m) AS avg_zf6m, COUNT(*) AS n_stu
  FROM base b
  JOIN regular r ON r.xx = b.xx AND r.bj = b.bj
  GROUP BY b.xx, b.bj
),
all_rank AS (
  SELECT *,
         RANK() OVER (ORDER BY avg_zf6m DESC) AS city_rank,
         COUNT(*) OVER () AS n_class
  FROM all_class
),
tgt_dir AS (
  SELECT city_rank FROM track_rank
  WHERE xx LIKE '%扬州中学%' AND bj LIKE '%高三(1)班%'
),
tgt_all AS (
  SELECT city_rank FROM all_rank
  WHERE xx LIKE '%扬州中学%' AND bj LIKE '%高三(1)班%'
)
SELECT '按选考方向' AS 口径, xx, bj, city_rank, n_class, ROUND(avg_zf6m, 1) AS avg_zf6m,
       CASE WHEN xx LIKE '%扬州中学%' AND bj LIKE '%高三(1)班%' THEN '本班' ELSE '' END AS 标记
FROM track_rank
WHERE city_rank = 1
   OR city_rank BETWEEN (SELECT city_rank FROM tgt_dir) - 3 AND (SELECT city_rank FROM tgt_dir) + 3
UNION ALL
SELECT '不区分选考', xx, bj, city_rank, n_class, ROUND(avg_zf6m, 1),
       CASE WHEN xx LIKE '%扬州中学%' AND bj LIKE '%高三(1)班%' THEN '本班' ELSE '' END
FROM all_rank
WHERE city_rank = 1
   OR city_rank BETWEEN (SELECT city_rank FROM tgt_all) - 3 AND (SELECT city_rank FROM tgt_all) + 3;
-- 一条 SQL、UNION ALL 两个口径。每个口径返回第1名+目标班前后各3名并标记本班。排名池排除其他校和整班不足10人。问句点名支撑/引领/发展校时再加 xxlb LIKE '%该类%'。用目标校+班定位窗口，禁止外层只留下目标班一行。
```

## E17 2026届高三1月新华中学的优势学科

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
WITH school_avg AS (
  SELECT xx,
         ROUND(AVG(yw) FILTER (WHERE yw > 0), 2) AS yw,
         ROUND(AVG(sx) FILTER (WHERE sx > 0), 2) AS sx,
         ROUND(AVG(yy) FILTER (WHERE yy > 0), 2) AS yy,
         ROUND(AVG(wl) FILTER (WHERE wl > 0), 2) AS wl,
         ROUND(AVG(ls) FILTER (WHERE ls > 0), 2) AS ls,
         ROUND(AVG(hxzh) FILTER (WHERE hxzh > 0), 2) AS hxzh,
         ROUND(AVG(swzh) FILTER (WHERE swzh > 0), 2) AS swzh,
         ROUND(AVG(zzzh) FILTER (WHERE zzzh > 0), 2) AS zzzh,
         ROUND(AVG(dlzh) FILTER (WHERE dlzh > 0), 2) AS dlzh
  FROM tb_score_overview
  WHERE exam_name LIKE '%2026届高三1月%'
    AND xsxz = '在籍生'
  GROUP BY xx
),
ranked AS (
  SELECT xx, '语文' AS subject, yw AS avg_score,
         RANK() OVER (ORDER BY yw DESC NULLS LAST) AS city_rank,
         COUNT(*) OVER () AS n_school
  FROM school_avg WHERE yw IS NOT NULL
  UNION ALL SELECT xx, '数学', sx, RANK() OVER (ORDER BY sx DESC NULLS LAST), COUNT(*) OVER () FROM school_avg WHERE sx IS NOT NULL
  UNION ALL SELECT xx, '英语', yy, RANK() OVER (ORDER BY yy DESC NULLS LAST), COUNT(*) OVER () FROM school_avg WHERE yy IS NOT NULL
  UNION ALL SELECT xx, '物理', wl, RANK() OVER (ORDER BY wl DESC NULLS LAST), COUNT(*) OVER () FROM school_avg WHERE wl IS NOT NULL
  UNION ALL SELECT xx, '历史', ls, RANK() OVER (ORDER BY ls DESC NULLS LAST), COUNT(*) OVER () FROM school_avg WHERE ls IS NOT NULL
  UNION ALL SELECT xx, '化学', hxzh, RANK() OVER (ORDER BY hxzh DESC NULLS LAST), COUNT(*) OVER () FROM school_avg WHERE hxzh IS NOT NULL
  UNION ALL SELECT xx, '生物', swzh, RANK() OVER (ORDER BY swzh DESC NULLS LAST), COUNT(*) OVER () FROM school_avg WHERE swzh IS NOT NULL
  UNION ALL SELECT xx, '政治', zzzh, RANK() OVER (ORDER BY zzzh DESC NULLS LAST), COUNT(*) OVER () FROM school_avg WHERE zzzh IS NOT NULL
  UNION ALL SELECT xx, '地理', dlzh, RANK() OVER (ORDER BY dlzh DESC NULLS LAST), COUNT(*) OVER () FROM school_avg WHERE dlzh IS NOT NULL
)
SELECT subject, avg_score, city_rank, n_school
FROM ranked
WHERE xx LIKE '%新华中学%'
ORDER BY city_rank, subject
LIMIT 1000;
-- 优势/薄弱学科=该校各科均分的全市学校排名相对位置：名次/参赛数≤25%为前列（优势），≥50%为靠后（薄弱）。禁止把本校各科里名次较差的直接叫薄弱。禁止用该校语文均分和数学均分互比。点名班级则 GROUP BY xx,bj 做全市班级排名：RANK() OVER (ORDER BY 均分 DESC)，禁止 PARTITION BY bj，禁止 COUNT(DISTINCT bj)。必须 xsxz='在籍生'，单科 FILTER col>0；化学/生物/政治/地理用 hxzh/swzh/zzzh/dlzh
```

## E18 2026届高三1月期末扬州中学高三(5)班优势学科

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
WITH class_avg AS (
  SELECT xx, bj,
         ROUND(AVG(yw) FILTER (WHERE yw > 0), 2) AS yw,
         ROUND(AVG(sx) FILTER (WHERE sx > 0), 2) AS sx,
         ROUND(AVG(yy) FILTER (WHERE yy > 0), 2) AS yy,
         ROUND(AVG(wl) FILTER (WHERE wl > 0), 2) AS wl,
         ROUND(AVG(ls) FILTER (WHERE ls > 0), 2) AS ls,
         ROUND(AVG(hxzh) FILTER (WHERE hxzh > 0), 2) AS hxzh,
         ROUND(AVG(swzh) FILTER (WHERE swzh > 0), 2) AS swzh,
         ROUND(AVG(zzzh) FILTER (WHERE zzzh > 0), 2) AS zzzh,
         ROUND(AVG(dlzh) FILTER (WHERE dlzh > 0), 2) AS dlzh
  FROM tb_score_overview
  WHERE exam_name LIKE '%2026届高三1月期末%'
    AND xsxz = '在籍生'
  GROUP BY xx, bj
),
ranked AS (
  SELECT xx, bj, '语文' AS subject, yw AS avg_score,
         RANK() OVER (ORDER BY yw DESC NULLS LAST) AS city_rank,
         COUNT(*) OVER () AS n_class
  FROM class_avg WHERE yw IS NOT NULL
  UNION ALL SELECT xx, bj, '数学', sx, RANK() OVER (ORDER BY sx DESC NULLS LAST), COUNT(*) OVER () FROM class_avg WHERE sx IS NOT NULL
  UNION ALL SELECT xx, bj, '英语', yy, RANK() OVER (ORDER BY yy DESC NULLS LAST), COUNT(*) OVER () FROM class_avg WHERE yy IS NOT NULL
  UNION ALL SELECT xx, bj, '物理', wl, RANK() OVER (ORDER BY wl DESC NULLS LAST), COUNT(*) OVER () FROM class_avg WHERE wl IS NOT NULL
  UNION ALL SELECT xx, bj, '历史', ls, RANK() OVER (ORDER BY ls DESC NULLS LAST), COUNT(*) OVER () FROM class_avg WHERE ls IS NOT NULL
  UNION ALL SELECT xx, bj, '化学', hxzh, RANK() OVER (ORDER BY hxzh DESC NULLS LAST), COUNT(*) OVER () FROM class_avg WHERE hxzh IS NOT NULL
  UNION ALL SELECT xx, bj, '生物', swzh, RANK() OVER (ORDER BY swzh DESC NULLS LAST), COUNT(*) OVER () FROM class_avg WHERE swzh IS NOT NULL
  UNION ALL SELECT xx, bj, '政治', zzzh, RANK() OVER (ORDER BY zzzh DESC NULLS LAST), COUNT(*) OVER () FROM class_avg WHERE zzzh IS NOT NULL
  UNION ALL SELECT xx, bj, '地理', dlzh, RANK() OVER (ORDER BY dlzh DESC NULLS LAST), COUNT(*) OVER () FROM class_avg WHERE dlzh IS NOT NULL
)
SELECT subject, avg_score, city_rank, n_class
FROM ranked
WHERE xx LIKE '%扬州中学%' AND bj LIKE '%高三(5)班%'
ORDER BY city_rank, subject
LIMIT 1000;
-- 班级优势学科=该班各科均分的全市班级排名。RANK/COUNT 必须在未过滤目标班的全集上计算。禁止 PARTITION BY bj，禁止 COUNT(DISTINCT bj)，禁止 hx/sw/zz/dl
```

## E19 全市均衡性最好的学科

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT * FROM (
  SELECT '语文' AS subject,
         ROUND((STDDEV_SAMP(yw) FILTER (WHERE yw > 0))::numeric, 2) AS stdev,
         ROUND((AVG(yw) FILTER (WHERE yw > 0))::numeric, 1) AS avg_score,
         COUNT(*) FILTER (WHERE yw > 0) AS n
  FROM tb_score_overview WHERE exam_name LIKE '%目标考试%'
  UNION ALL
  SELECT '数学', ROUND((STDDEV_SAMP(sx) FILTER (WHERE sx > 0))::numeric, 2),
         ROUND((AVG(sx) FILTER (WHERE sx > 0))::numeric, 1), COUNT(*) FILTER (WHERE sx > 0)
  FROM tb_score_overview WHERE exam_name LIKE '%目标考试%'
  UNION ALL
  SELECT '英语', ROUND((STDDEV_SAMP(yy) FILTER (WHERE yy > 0))::numeric, 2),
         ROUND((AVG(yy) FILTER (WHERE yy > 0))::numeric, 1), COUNT(*) FILTER (WHERE yy > 0)
  FROM tb_score_overview WHERE exam_name LIKE '%目标考试%'
  UNION ALL
  SELECT '物理', ROUND((STDDEV_SAMP(wl) FILTER (WHERE wl > 0))::numeric, 2),
         ROUND((AVG(wl) FILTER (WHERE wl > 0))::numeric, 1), COUNT(*) FILTER (WHERE wl > 0)
  FROM tb_score_overview WHERE exam_name LIKE '%目标考试%'
  UNION ALL
  SELECT '历史', ROUND((STDDEV_SAMP(ls) FILTER (WHERE ls > 0))::numeric, 2),
         ROUND((AVG(ls) FILTER (WHERE ls > 0))::numeric, 1), COUNT(*) FILTER (WHERE ls > 0)
  FROM tb_score_overview WHERE exam_name LIKE '%目标考试%'
  UNION ALL
  SELECT '化学', ROUND((STDDEV_SAMP(hxzh) FILTER (WHERE hxzh > 0))::numeric, 2),
         ROUND((AVG(hxzh) FILTER (WHERE hxzh > 0))::numeric, 1), COUNT(*) FILTER (WHERE hxzh > 0)
  FROM tb_score_overview WHERE exam_name LIKE '%目标考试%'
  UNION ALL
  SELECT '生物', ROUND((STDDEV_SAMP(swzh) FILTER (WHERE swzh > 0))::numeric, 2),
         ROUND((AVG(swzh) FILTER (WHERE swzh > 0))::numeric, 1), COUNT(*) FILTER (WHERE swzh > 0)
  FROM tb_score_overview WHERE exam_name LIKE '%目标考试%'
  UNION ALL
  SELECT '政治', ROUND((STDDEV_SAMP(zzzh) FILTER (WHERE zzzh > 0))::numeric, 2),
         ROUND((AVG(zzzh) FILTER (WHERE zzzh > 0))::numeric, 1), COUNT(*) FILTER (WHERE zzzh > 0)
  FROM tb_score_overview WHERE exam_name LIKE '%目标考试%'
  UNION ALL
  SELECT '地理', ROUND((STDDEV_SAMP(dlzh) FILTER (WHERE dlzh > 0))::numeric, 2),
         ROUND((AVG(dlzh) FILTER (WHERE dlzh > 0))::numeric, 1), COUNT(*) FILTER (WHERE dlzh > 0)
  FROM tb_score_overview WHERE exam_name LIKE '%目标考试%'
) t
ORDER BY stdev ASC
LIMIT 1000;
-- 均衡性=标准差越小越均衡。未选考/缺考为 0，STDDEV/AVG 必须 FILTER col>0，否则选考科均分被拉低、离散被夸大。化学/生物/政治/地理用转换分 hxzh/swzh/zzzh/dlzh
```

## E20 2026届高三5月模拟理科语数外三门均分的学校排名

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT xx AS school,
       COUNT(*) AS candidates,
       ROUND(AVG(zf3m), 1) AS avg_zf3m
FROM tb_score_overview
WHERE exam_name = '2026届高三5月模拟'
  AND xkkm LIKE '物%'
GROUP BY xx
ORDER BY avg_zf3m DESC
LIMIT 1000;
-- 语数外/三门均分=AVG(zf3m) 三科总分校均（约 350），禁止除以 3，禁止 tb_score 三科 AVG(score)
-- 理科=物理类 xkkm LIKE '物%'；学校用 xx（学校明文），不要用 tb_school.name 脱敏码
```

## E21 2026届高三1月期末扬州中学达线情况

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT line_name,
       track,
       SUM(candidates) AS candidates,
       SUM(reached_count) AS reached_count,
       ROUND(SUM(reached_count) * 100.0 / NULLIF(SUM(candidates), 0), 2) AS reach_rate
FROM tb_score_indicator
WHERE exam_name LIKE '%2026届高三1月期末%'
  AND school_name LIKE '%扬州中学%'
GROUP BY line_name, track
ORDER BY line_name, track
LIMIT 1000;
-- 学校达线用 school_name LIKE '%校名%'；禁止 school_id='GZ_…'；禁止用 district='市直' 冒充学校
```

## E22 2026届高三1月期末全市引领校达线情况

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT ind.line_name,
       ind.track,
       SUM(ind.candidates) AS candidates,
       SUM(ind.reached_count) AS reached_count,
       ROUND(SUM(ind.reached_count) * 100.0 / NULLIF(SUM(ind.candidates), 0), 2) AS reach_rate
FROM tb_score_indicator ind
JOIN tb_school sch ON ind.school_name = COALESCE(sch.s_name, sch.name)
WHERE ind.exam_name LIKE '%2026届高三1月期末%'
  AND sch."type" LIKE '%引领%'
GROUP BY ind.line_name, ind.track
ORDER BY ind.line_name, ind.track
LIMIT 1000;
-- 引领/支撑/发展校达线：indicator JOIN tb_school，校类用 sch.type（与 overview.xxlb 同源）；禁止套用全市达线 HTML
```

## E23 邗江区物理类本科线达线人数和达线率

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT district,
       track,
       line_name,
       SUM(candidates) AS candidates,
       SUM(reached_count) AS reached_count,
       ROUND(SUM(reached_count) * 100.0 / NULLIF(SUM(candidates), 0), 2) AS reach_rate
FROM tb_score_indicator
WHERE district LIKE '%邗江%'
  AND track = '物理类'
  AND line_name = '本科线'
GROUP BY district, track, line_name
LIMIT 1000;
-- 达线查 tb_score_indicator；区县/全市必须 SUM 后重算率，禁止 AVG(reach_rate)
```

## E24 扬州市2026届高三3月广陵区本科线达线人数和达线率

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT district,
       line_name,
       SUM(candidates) AS candidates,
       SUM(reached_count) AS reached_count,
       ROUND(SUM(reached_count) * 100.0 / NULLIF(SUM(candidates), 0), 2) AS reach_rate
FROM tb_score_indicator
WHERE exam_name LIKE '%2026届高三3月%'
  AND district LIKE '%广陵%'
  AND line_name = '本科线'
GROUP BY district, line_name
LIMIT 1000;
-- 禁止把「N月」拼进 district；考试用 LIKE 对齐 batch_name
```

## E25 2026届高三3月扬州中学高三(1)班南大达线情况

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT CASE
         WHEN ov.xkkm LIKE '物%' THEN '物理类'
         WHEN ov.xkkm LIKE '史%' OR ov.xkkm LIKE '历%' THEN '历史类'
         ELSE '其他'
       END AS 选科方向,
       COUNT(*) AS 参考人数,
       SUM(CASE
             WHEN ov.xkkm LIKE '物%' AND ov.zf6m >= fb.wl_score_nd THEN 1
             WHEN (ov.xkkm LIKE '史%' OR ov.xkkm LIKE '历%') AND ov.zf6m >= fb.ls_score_nd THEN 1
             ELSE 0
           END) AS 达线人数,
       ROUND(100.0 * SUM(CASE
             WHEN ov.xkkm LIKE '物%' AND ov.zf6m >= fb.wl_score_nd THEN 1
             WHEN (ov.xkkm LIKE '史%' OR ov.xkkm LIKE '历%') AND ov.zf6m >= fb.ls_score_nd THEN 1
             ELSE 0
           END) / NULLIF(COUNT(*), 0), 2) AS "达线率%",
       MAX(CASE
             WHEN ov.xkkm LIKE '物%' THEN fb.wl_score_nd
             WHEN ov.xkkm LIKE '史%' OR ov.xkkm LIKE '历%' THEN fb.ls_score_nd
           END) AS 分数线
FROM tb_score_overview ov
JOIN tb_fraction_bar fb ON fb.exam_name = ov.exam_name
WHERE ov.exam_name LIKE '%2026届高三3月%'
  AND ov.bj LIKE '%高三(1)%'
  AND (ov.xkkm LIKE '物%' OR ov.xkkm LIKE '史%' OR ov.xkkm LIKE '历%')
GROUP BY 1
LIMIT 1000;
-- 班级达线：必须用 zf6m（禁止 zf4m/zf3m）；物理对照 wl_score_*、历史对照 ls_score_*；
-- 按 xkkm 分轨 GROUP BY；班内只有物理类则结果只有一行，禁止文理混报；WHERE 必含 bj
```

## E26 2026届高三1月期末各区特控线达线率对比

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT district,
       line_name,
       SUM(candidates) AS candidates,
       SUM(reached_count) AS reached_count,
       ROUND(SUM(reached_count) * 100.0 / NULLIF(SUM(candidates), 0), 2) AS reach_rate
FROM tb_score_indicator
WHERE exam_name = '2026届高三1月期末'
  AND line_name = '特控线'
GROUP BY district, line_name
ORDER BY reach_rate DESC
LIMIT 1000;
```

## E27 邗江物理类600分以上多少人

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT COUNT(*) FILTER (WHERE zf6m >= 600) AS n_ge,
       COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) FILTER (WHERE zf6m >= 600) / NULLIF(COUNT(*), 0), 2) AS pct
FROM tb_score_overview
WHERE exam_name = '2026届高三1月期末'
  AND dq LIKE '%邗江%'
  AND xkkm LIKE '物%'
LIMIT 1000;
-- 绝对分数段查 tb_score_overview.zf6m；禁止 tb_score / tb_score_indicator；物理类 xkkm LIKE '物%'
```

## E28 全市化学86到90分多少人

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT COUNT(*) AS n
FROM tb_score_overview
WHERE exam_name = '2026届高三1月期末'
  AND hxzh >= 86 AND hxzh < 91
LIMIT 1000;
-- 化学分段用 hxzh（转换分），禁止 hx；未选该科（0/空）不要计入
```

## E29 引领校语文110分以上人数

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT COUNT(*) FILTER (WHERE yw >= 110) AS n_ge,
       COUNT(*) AS n
FROM tb_score_overview
WHERE exam_name = '2026届高三1月期末'
  AND xxlb LIKE '%引领%'
  AND xsxz = '在籍生'
LIMIT 1000;
-- 引领/支撑/发展走 xxlb 且排除市报生；市报生用 xsxz LIKE '%市报%'
```

## E30 2026届高三1月扬州中学总分10分段分布情况

来源：[src/templates/sql_gen_prompt.py](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/templates/sql_gen_prompt.py:25)（该行是多行字符串起点）

```sql
SELECT ((CAST(zf6m AS int) - 1) / 10) * 10 + 1 AS band_lo,
       COUNT(*) AS n
FROM tb_score_overview
WHERE exam_name LIKE '%2026届高三1月%'
  AND xx LIKE '%扬州中学%'
GROUP BY 1
ORDER BY 1 DESC
LIMIT 1000;
-- 点名学校的十分段是事实查询：zf6m 六门总分，按该校过滤；禁止套用各区县分段 HTML 报告
```
