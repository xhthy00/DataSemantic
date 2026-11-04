# SQL生成入口源码摘录

仅用于审阅与追溯，不是可执行SQL合集。包含动态拼接、维度枚举、导入写入、旧实现和SQL约束文案。函数之间可能依赖其他常量或函数；原文已用文件与行号引用。系统通用CRUD没有在这里逐函数展开。

## scripts/import_exam_scores.py :: upsert_scores_and_details

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/scripts/import_exam_scores.py:593)

```python
def upsert_scores_and_details(
    conn,
    subject_to_id: dict[str, int],
    score_rows: list[dict[str, Any]],
    detail_rows: list[dict[str, Any]],
) -> dict[str, int]:
    """UPSERT 写入 tb_score 与 tb_score_detail。"""
    cur = conn.cursor()

    # 填 exam_id：score_rows 按 subject_name、detail_rows 按 subject_name 映射
    for row in score_rows:
        row["exam_id"] = subject_to_id[row["subject_name"]]
    _fill_detail_exam_ids(detail_rows, subject_to_id)

    # ---- tb_score UPSERT ----
    score_cols = ["exam_id", "student_id", "school_id", "class", "score", "subject_name", "exam_score", "exam_time"]
    score_params = [
        tuple(
            row[c] if c != "exam_time" else (row["exam_time"] or None)
            for c in score_cols
        )
        for row in score_rows
    ]
    score_sql = (
        "INSERT INTO public.tb_score (exam_id, student_id, school_id, class, score, subject_name, exam_score, exam_time) "
        "VALUES %s "
        "ON CONFLICT (exam_id, student_id) DO UPDATE SET "
        "school_id=EXCLUDED.school_id, class=EXCLUDED.class, score=EXCLUDED.score, "
        "subject_name=EXCLUDED.subject_name, exam_score=EXCLUDED.exam_score, exam_time=EXCLUDED.exam_time"
    )
    for i in range(0, len(score_params), 500):
        chunk = score_params[i : i + 500]
        execute_values(cur, score_sql, chunk, page_size=500)

    # ---- tb_score_detail UPSERT ----
    detail_cols = ["exam_id", "student_id", "question_no", "question_id", "score", "question_score", "class"]
    detail_params = [
        tuple(row[c] for c in detail_cols)
        for row in detail_rows
    ]
    detail_sql = (
        "INSERT INTO public.tb_score_detail (exam_id, student_id, question_no, question_id, score, question_score, class) "
        "VALUES %s "
        "ON CONFLICT (exam_id, student_id, question_no) DO UPDATE SET "
        "question_id=EXCLUDED.question_id, score=EXCLUDED.score, question_score=EXCLUDED.question_score, class=EXCLUDED.class"
    )
    for i in range(0, len(detail_params), 500):
        chunk = detail_params[i : i + 500]
        execute_values(cur, detail_sql, chunk, page_size=500)

    conn.commit()
    return {"score_rows": len(score_rows), "detail_rows": len(detail_rows)}
```

## scripts/import_exam_scores.py :: upsert_exam_batch

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/scripts/import_exam_scores.py:456)

```python
def upsert_exam_batch(conn, batch_name: str) -> int:
    """查找或新建 tb_exam_batch；返回 batch_id。"""
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM tb_exam_batch WHERE batch_name = %s",
        (batch_name,),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO tb_exam_batch (batch_name) VALUES (%s) RETURNING id",
        (batch_name,),
    )
    return cur.fetchone()[0]
```

## scripts/import_exam_scores.py :: delete_existing_exam_data

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/scripts/import_exam_scores.py:473)

```python
def delete_existing_exam_data(conn, exam_ids: list[int]) -> None:
    """删除旧题目和旧小题分明细（按 exam_id 列表）。

    不在此处 commit，由调用方统一事务控制（upsert_exams 失败时可回滚）。
    """
    if not exam_ids:
        return
    cur = conn.cursor()
    cur.execute("DELETE FROM tb_score_detail WHERE exam_id = ANY(%s)", (exam_ids,))
    cur.execute("DELETE FROM tb_exam_question WHERE exam_id = ANY(%s)", (exam_ids,))
```

## scripts/import_exam_scores.py :: upsert_exams

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/scripts/import_exam_scores.py:485)

```python
def upsert_exams(
    conn,
    exams: list[dict[str, Any]],
    exam_batch_id: int,
) -> dict[str, int]:
    """写入 tb_exam；返回 {subject: exam_id}。

    匹配规则（按优先级）：
    1. 同 ``exam_batch_id`` + 同 ``subject`` → 复用已有 exam，更新 exam_time/exam_score/exam_name
    2. 否则按 ``exam_name`` 完全匹配 → 复用并绑定到 batch
    3. 都没有 → 新建 exam

    题目（tb_exam_question）按 (exam_id, question_no) UPSERT，
    ``content`` 来自 ``q["content"]``（已由 PDF 解析器填充或默认为 "暂无"）。
    """
    subject_to_id: dict[str, int] = {}
    cur = conn.cursor()
    for exam in exams:
        # 优先按 batch_id + subject 匹配
        cur.execute(
            """SELECT id, exam_name FROM tb_exam
               WHERE exam_batch_id = %s AND subject = %s""",
            (exam_batch_id, exam["subject"]),
        )
        row = cur.fetchone()
        if row:
            exam_id = row[0]
            cur.execute(
                """UPDATE tb_exam
                   SET exam_time=%s, subject=%s, exam_score=%s, exam_name=%s,
                       exam_batch_id=%s
                   WHERE id=%s""",
                (
                    exam["exam_time"],
                    exam["subject"],
                    exam["exam_score"],
                    exam["exam_name"],
                    exam_batch_id,
                    exam_id,
                ),
            )
        else:
            # 退化：按 exam_name 完全匹配
            cur.execute(
                "SELECT id FROM tb_exam WHERE exam_name = %s",
                (exam["exam_name"],),
            )
            row = cur.fetchone()
            if row:
                exam_id = row[0]
                cur.execute(
                    """UPDATE tb_exam
                       SET exam_time=%s, subject=%s, exam_score=%s, exam_batch_id=%s
                       WHERE id=%s""",
                    (
                        exam["exam_time"],
                        exam["subject"],
                        exam["exam_score"],
                        exam_batch_id,
                        exam_id,
                    ),
                )
            else:
                # 新建
                cur.execute(
                    """INSERT INTO tb_exam
                       (exam_name, exam_time, subject, exam_score, exam_type, exam_batch_id)
                       VALUES (%s, %s, %s, %s, 'city', %s) RETURNING id""",
                    (
                        exam["exam_name"],
                        exam["exam_time"],
                        exam["subject"],
                        exam["exam_score"],
                        exam_batch_id,
                    ),
                )
                exam_id = cur.fetchone()[0]
        subject_to_id[exam["subject"]] = exam_id

        # 写入题目（UPSERT by exam_id+question_no）
        for q in exam["questions"]:
            content = q.get("content") or "暂无"
            cur.execute(
                """SELECT id FROM tb_exam_question WHERE exam_id=%s AND question_no=%s""",
                (exam_id, q["question_no"]),
            )
            qrow = cur.fetchone()
            if qrow:
                cur.execute(
                    """UPDATE tb_exam_question
                       SET question_score=%s, question_type=%s, content=%s
                       WHERE id=%s""",
                    (q["score"], q["question_type"], content, qrow[0]),
                )
                qid = qrow[0]
            else:
                cur.execute(
                    """INSERT INTO tb_exam_question
                       (exam_name, question_no, content, question_score, exam_id, question_type)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (exam["exam_name"], q["question_no"], content, q["score"], exam_id, q["question_type"]),
                )
                qid = cur.fetchone()[0]
            q["question_id"] = qid
    conn.commit()
    return subject_to_id
```

## scripts/import_exam_scores.py :: main

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/scripts/import_exam_scores.py:657)

```python
def main() -> int:
    parser = argparse.ArgumentParser(
        description="导入高三模考总分+小题分到 edu 库",
    )
    parser.add_argument("--score-file", required=True, help="总分宽表 Excel 路径")
    parser.add_argument("--detail-dir", required=True, help="各科小题分文件目录")
    parser.add_argument(
        "--paper-dir",
        default="",
        help="各科试卷 PDF 目录（含 数学.pdf / 物理.pdf 等；可选）",
    )
    parser.add_argument("--exam-name", required=True, help="考试名称前缀，如 2026届高三1月期末")
    parser.add_argument("--exam-time", required=True, help="考试日期 YYYY-MM-DD")
    parser.add_argument("--jc", type=int, default=2026, help="届次，默认 2026")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="目标库连接串；默认从环境变量 DATABASE_URL 读取",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入")
    parser.add_argument(
        "--exclude-score",
        action="append",
        default=[],
        metavar="SFZH:科目",
        help="个案排除某生某科总分及小题分（如 261081010509:物理），可重复传入",
    )
    args = parser.parse_args()

    if not args.database_url:
        print("错误：未提供 --database-url，也未设置环境变量 DATABASE_URL", file=sys.stderr)
        return 1

    # 解析排除集 {(sfzh, 科目)}
    exclude_scores: set[tuple[str, str]] = set()
    for item in args.exclude_score:
        if ":" not in item:
            print(f"错误：--exclude-score 格式应为 SFZH:科目，收到: {item}", file=sys.stderr)
            return 1
        sfzh, subject = item.split(":", 1)
        exclude_scores.add((sfzh.strip(), subject.strip()))
    if exclude_scores:
        print(f"个案排除 {len(exclude_scores)} 项: {sorted(exclude_scores)}")

    # 1. 生成试卷与题目定义
    print(f"读取小题分目录: {args.detail_dir}")
    exams = build_exams_and_questions(
        args.detail_dir, args.exam_name, args.exam_time, args.paper_dir
    )
    if not exams:
        print("错误：未生成任何试卷", file=sys.stderr)
        return 1

    # 2. 生成总分与小题分行
    print(f"读取总分宽表: {args.score_file}")
    score_rows, detail_rows, _warnings = build_score_rows(
        args.score_file, args.detail_dir, exams, exclude_scores=exclude_scores
    )
    print(f"\n总分行: {len(score_rows)}  小题分行为: {len(detail_rows)}")

    # 3. 预览
    print("\n=== 预览：各科试卷 ===")
    for e in exams:
        total = round(sum(q["score"] for q in e["questions"]), 2)
        print(f"  {e['exam_name']}: {len(e['questions'])}题, 分值={total}")

    print("\n=== 预览：每科题目抽样（前5题+content前60字符） ===")
    for e in exams:
        print(f"\n  -- {e['subject']} ({len(e['questions'])}题) --")
        for q in e["questions"][:5]:
            content_preview = (q.get("content") or "暂无")[:60].replace("\n", " ")
            print(f"    {q['question_no']} ({q['question_score']}分): {content_preview}...")

    print("\n=== 预览：总分行抽样 ===")
    for r in score_rows[:5]:
        print(f"  {r['student_id']} {r['subject_name']}={r['score']} 班级={r['class']} 学校={r['xx']}")

    if args.dry_run:
        print("\n[DRY RUN] 未写入数据库")
        return 0

    # 4. 写入（统一事务：失败回滚，保证 DELETE 与 INSERT 同生共死）
    print("\n写入数据库...")
    try:
        with psycopg2.connect(args.database_url) as conn:
            # 4a. 找/建批次（tb_exam_batch）
            exam_batch_id = upsert_exam_batch(conn, args.exam_name)
            print(f"  [批次] {args.exam_name} id={exam_batch_id}")

            # 4b. 找该批次下已有 exam_ids（按 exam_batch_id 匹配）
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM tb_exam WHERE exam_batch_id = %s",
                (exam_batch_id,),
            )
            existing_exam_ids = [r[0] for r in cur.fetchall()]
            # 4c. 先删旧题目和旧小题分明细（按现有 exam_id），重做干净
            if existing_exam_ids:
                delete_existing_exam_data(conn, existing_exam_ids)
            # 4d. 再 UPSERT 试卷/题目与总分/小题分
            subject_to_id = upsert_exams(conn, exams, exam_batch_id)
            stats = upsert_scores_and_details(conn, subject_to_id, score_rows, detail_rows)
            conn.commit()
    except Exception:
        # with conn 退出时已自动 rollback，这里再提示一下
        print("\n[错误] 写入失败，已自动回滚；tb_exam_question/tb_score_detail 数据未被破坏", file=sys.stderr)
        raise
    print(f"\n导入完成: 试卷={len(exams)}, 总分={stats['score_rows']}, 小题分={stats['detail_rows']}")
    return 0
```

## scripts/import_knowledge_xlsx.py :: insert_knowledge

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/scripts/import_knowledge_xlsx.py:146)

```python
def insert_knowledge(conn, rows: list[dict[str, Any]]) -> int:
    """批量插入知识点行，返回写入数量。"""
    if not rows:
        return 0

    cur = conn.cursor()
    cols = [
        "stage", "grade", "subject", "module", "module_no",
        "chapter", "chapter_no", "secondary", "secondary_no",
        "knowledge_name", "knowledge_no",
    ]
    params = [tuple(row[c] for c in cols) for row in rows]
    sql = (
        "INSERT INTO public.tb_knowledge ("
        "stage, grade, subject, module, module_no, chapter, chapter_no, "
        "secondary, secondary_no, knowledge_name, knowledge_no"
        ") VALUES %s"
    )
    from psycopg2.extras import execute_values
    execute_values(cur, sql, params, page_size=500)
    conn.commit()
    return len(rows)
```

## scripts/import_knowledge_xlsx.py :: ensure_columns

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/scripts/import_knowledge_xlsx.py:81)

```python
def ensure_columns(conn) -> None:
    """确保 tb_knowledge 包含目标字段；不存在则新增；并校正唯一约束。"""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tb_knowledge'
    """)
    existing = {row[0] for row in cur.fetchall()}

    for col_name, (data_type, length, comment) in COLUMNS_TO_ENSURE.items():
        if col_name in existing:
            print(f"  [已存在] {col_name}")
            continue
        type_sql = f"{data_type}({length})" if length else data_type
        cur.execute(
            f"ALTER TABLE public.tb_knowledge ADD COLUMN {col_name} {type_sql}"
        )
        cur.execute(
            "COMMENT ON COLUMN public.tb_knowledge.%s IS %%s" % col_name,
            (comment,),
        )
        print(f"  [新增字段] {col_name} {type_sql} COMMENT '{comment}'")

    # 删除 tb_knowledge 除主键外的所有唯一约束/索引
    cur.execute("""
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'public.tb_knowledge'::regclass
          AND contype = 'u'
    """)
    for row in cur.fetchall():
        cur.execute(f"ALTER TABLE public.tb_knowledge DROP CONSTRAINT {row[0]}")
        print(f"  [已删除] 唯一约束 {row[0]}")

    cur.execute("""
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'tb_knowledge'
          AND indexname != 'tb_knowledge_pkey'
    """)
    for row in cur.fetchall():
        cur.execute(f"DROP INDEX IF EXISTS public.{row[0]}")
        print(f"  [已删除] 索引 {row[0]}")

    # 重建以 knowledge_no 为唯一键的约束
    cur.execute("""
        ALTER TABLE public.tb_knowledge
        ADD CONSTRAINT uk_knowledge_no UNIQUE (knowledge_no)
    """)
    print("  [已创建] 唯一约束 uk_knowledge_no (knowledge_no)")

    conn.commit()
```

## scripts/import_score_overview.py :: build_upsert_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/scripts/import_score_overview.py:382)

```python
def build_upsert_sql(columns: list[str]) -> str:
    """构造 PostgreSQL UPSERT 语句。

    使用 psycopg2.extras.execute_values 要求的 %s 占位符模板：
        INSERT INTO ... VALUES %s ON CONFLICT ... DO UPDATE SET ...
    execute_values 会自动将 %s 展开为多组值。
    """
    col_list = ", ".join(f'"{c}"' for c in columns)
    updates = ", ".join(
        f'"{c}" = EXCLUDED."{c}"' for c in columns if c not in ("ksh", "exam_name")
    )
    return (
        f'INSERT INTO public.tb_score_overview ({col_list}) VALUES %s '
        f"ON CONFLICT (ksh, exam_name) DO UPDATE SET {updates}"
    )
```

## scripts/match_question_knowledge.py :: fetch_unmatched_questions

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/scripts/match_question_knowledge.py:97)

```python
def fetch_unmatched_questions(
    session,
    subject: str | None = None,
    exam_id: int | None = None,
    limit: int | None = None,
) -> list[QuestionRow]:
    """查询尚未关联知识点的题目，科目从 tb_exam 关联获取。"""
    sql = """
        SELECT q.id, q.exam_id, q.question_no, e.subject, q.question_type, q.content
        FROM tb_exam_question q
        JOIN tb_exam e ON q.exam_id = e.id
        LEFT JOIN tb_exam_question_knowledge qk ON q.id = qk.question_id
        WHERE qk.question_id IS NULL
          AND q.content IS NOT NULL
          AND TRIM(q.content) <> ''
          AND TRIM(q.content) <> '暂无'
    """
    params: dict[str, Any] = {}
    if subject:
        sql += " AND e.subject = :subject"
        params["subject"] = subject
    if exam_id is not None:
        sql += " AND q.exam_id = :exam_id"
        params["exam_id"] = exam_id
    if limit is not None:
        sql += " LIMIT :limit"
        params["limit"] = limit

    rows = session.execute(text(sql), params).mappings().all()
    return [
        QuestionRow(
            id=r["id"],
            exam_id=r["exam_id"],
            question_no=r["question_no"] or "",
            subject=r["subject"],
            question_type=r["question_type"],
            content=str(r["content"]).strip(),
        )
        for r in rows
    ]
```

## scripts/match_question_knowledge.py :: insert_matches

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/scripts/match_question_knowledge.py:229)

```python
def insert_matches(session, matches: list[tuple[int, int]]) -> int:
    """批量插入题目-知识点关联。"""
    if not matches:
        return 0

    # 去重并按 (question_id, knowledge_id) 插入
    seen: set[tuple[int, int]] = set()
    unique_matches = []
    for qid, kid in matches:
        key = (qid, kid)
        if key in seen:
            continue
        seen.add(key)
        unique_matches.append(key)

    session.execute(
        text("""
            INSERT INTO tb_exam_question_knowledge (question_id, knowledge_id, weight)
            VALUES (:question_id, :knowledge_id, 1)
            ON CONFLICT (question_id, knowledge_id) DO NOTHING
        """),
        [
            {"question_id": qid, "knowledge_id": kid}
            for qid, kid in unique_matches
        ],
    )
    session.commit()
    return len(unique_matches)
```

## scripts/match_question_knowledge.py :: fetch_knowledge_by_subjects

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/scripts/match_question_knowledge.py:139)

```python
def fetch_knowledge_by_subjects(session, subjects: set[str]) -> dict[str, list[KnowledgeRow]]:
    """按科目批量加载知识点。"""
    if not subjects:
        return {}

    rows = (
        session.execute(
            text("""
                SELECT id, subject, module, chapter, knowledge_name
                FROM tb_knowledge
                WHERE subject = ANY(:subjects)
            """),
            {"subjects": list(subjects)},
        )
        .mappings()
        .all()
    )

    result: dict[str, list[KnowledgeRow]] = {}
    for r in rows:
        subject = r["subject"] or ""
        result.setdefault(subject, []).append(
            KnowledgeRow(
                id=r["id"],
                name=r["knowledge_name"] or "",
                module=r["module"],
                chapter=r["chapter"],
            )
        )
    return result
```

## src/agent/education/alert_service.py :: _fetch_score_rows

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/alert_service.py:353)

```python
def _fetch_score_rows(
    db_type: str,
    config: dict[str, Any],
    *,
    school_id: str,
    exam_id: str,
) -> list[dict[str, Any]]:
    from datasource.db.db import execute_sql

    sid = _escape_sql_str(school_id)
    eid = _escape_sql_str(str(exam_id))
    sql = (
        "SELECT student_id, school_id, class, subject_name, exam_id, score, exam_score "
        f"FROM tb_score WHERE school_id = '{sid}' AND CAST(exam_id AS TEXT) = '{eid}'"
    )
    ok, msg, data = execute_sql(db_type, config, sql)
    if not ok or not isinstance(data, dict):
        logger.warning("anomaly alert score fetch failed: %s", msg)
        return []
    columns = list(data.get("columns") or [])
    rows = list(data.get("rows") or [])
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
        elif isinstance(row, (list, tuple)):
            out.append({columns[i]: row[i] for i in range(min(len(columns), len(row)))})
    return out
```

## src/agent/education/alert_service.py :: _fetch_prev_scores

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/alert_service.py:383)

```python
def _fetch_prev_scores(
    db_type: str,
    config: dict[str, Any],
    *,
    school_id: str,
    exam_id: str,
    subject_name: str,
) -> dict[str, float]:
    """同校同科、更早一场考试的上次得分 student_id -> score。"""
    from datasource.db.db import execute_sql

    sid = _escape_sql_str(school_id)
    eid = _escape_sql_str(str(exam_id))
    subj = _escape_sql_str(subject_name)
    sql = f"""
    WITH cur AS (
      SELECT exam_time FROM tb_exam WHERE CAST(id AS TEXT) = '{eid}' LIMIT 1
    ),
    prev AS (
      SELECT e.id AS exam_id
      FROM tb_exam e, cur
      WHERE e.subject = '{subj}'
        AND e.exam_time IS NOT NULL
        AND cur.exam_time IS NOT NULL
        AND e.exam_time < cur.exam_time
      ORDER BY e.exam_time DESC
      LIMIT 1
    )
    SELECT sc.student_id, sc.score
    FROM tb_score sc
    JOIN prev ON CAST(sc.exam_id AS TEXT) = CAST(prev.exam_id AS TEXT)
    WHERE sc.school_id = '{sid}' AND sc.subject_name = '{subj}'
    """
    ok, msg, data = execute_sql(db_type, config, sql)
    if not ok or not isinstance(data, dict):
        logger.debug("prev score fetch skipped: %s", msg)
        return {}
    columns = list(data.get("columns") or [])
    rows = list(data.get("rows") or [])
    out: dict[str, float] = {}
    for row in rows:
        if isinstance(row, dict):
            stu = str(row.get("student_id") or "")
            try:
                out[stu] = float(row.get("score"))
            except (TypeError, ValueError):
                continue
        elif isinstance(row, (list, tuple)) and len(columns) >= 2:
            try:
                idx_s = columns.index("student_id") if "student_id" in columns else 0
                idx_v = columns.index("score") if "score" in columns else 1
                out[str(row[idx_s])] = float(row[idx_v])
            except (TypeError, ValueError, IndexError):
                continue
    return out
```

## src/agent/education/alert_service.py :: _exam_name_lookup

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/alert_service.py:440)

```python
def _exam_name_lookup(
    db_type: str, config: dict[str, Any], exam_id: str
) -> str:
    from datasource.db.db import execute_sql

    eid = _escape_sql_str(str(exam_id))
    sql = f"SELECT exam_name FROM tb_exam WHERE CAST(id AS TEXT) = '{eid}' LIMIT 1"
    ok, _, data = execute_sql(db_type, config, sql)
    if not ok or not isinstance(data, dict):
        return ""
    rows = list(data.get("rows") or [])
    if not rows:
        return ""
    row = rows[0]
    if isinstance(row, dict):
        return str(row.get("exam_name") or "")
    if isinstance(row, (list, tuple)) and row:
        return str(row[0] or "")
    return ""
```

## src/agent/education/alert_service.py :: scan_alerts_after_import

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/alert_service.py:710)

```python
def scan_alerts_after_import(
    session: Session,
    *,
    db_type: str,
    config: dict[str, Any],
    workspace_oid: int,
    datasource_id: int,
    resolved_rows: list[Any],
    exam_batch_id: int | None = None,
) -> dict[str, Any]:
    """导入成功后扫描异常提醒。

    - 仅 ``resolved_rows``：按 (school_id, exam_id) 去重，并按涉及班级过滤。
    - 同时传 ``exam_batch_id``：扫描该批次全部试卷 × resolved 中的学校，不按班级过滤。
    """
    from datasource.db.db import execute_sql

    pairs: dict[tuple[str, str], str] = {}
    classes_by_pair: dict[tuple[str, str], set[str]] = {}

    if exam_batch_id is not None:
        school_ids: set[str] = set()
        for r in resolved_rows or []:
            sid = str(
                getattr(r, "school_id", None)
                or (r.get("school_id") if isinstance(r, dict) else "")
                or getattr(r, "school_token", None)
                or (r.get("school_token") if isinstance(r, dict) else "")
                or ""
            ).strip()
            if sid:
                school_ids.add(sid)
        if not school_ids:
            return {"inserted": 0, "updated": 0, "skipped": 0, "detected": 0, "exams": 0}
        batch_id = int(exam_batch_id)
        ok, _msg, data = execute_sql(
            db_type,
            config,
            f"SELECT id, exam_name FROM tb_exam WHERE exam_batch_id = {batch_id}",
        )
        exam_rows: list[dict[str, Any]] = []
        if ok and isinstance(data, dict):
            cols = list(data.get("columns") or [])
            for row in data.get("rows") or []:
                if isinstance(row, dict):
                    exam_rows.append(row)
                elif isinstance(row, (list, tuple)):
                    exam_rows.append({cols[i]: row[i] for i in range(min(len(cols), len(row)))})
        for exam in exam_rows:
            eid = str(exam.get("id") or "").strip()
            ename = str(exam.get("exam_name") or "")
            if not eid:
                continue
            for sid in school_ids:
                pairs[(sid, eid)] = ename
        classes_by_pair = {pair: set() for pair in pairs}
    else:
        for r in resolved_rows or []:
            school_id = str(
                getattr(r, "school_id", None) or (r.get("school_id") if isinstance(r, dict) else "") or ""
            ).strip()
            exam_id = str(
                getattr(r, "exam_id", None) or (r.get("exam_id") if isinstance(r, dict) else "") or ""
            ).strip()
            exam_name = str(
                getattr(r, "exam_name", None) or (r.get("exam_name") if isinstance(r, dict) else "") or ""
            ).strip()
            class_name = str(
                getattr(r, "class_name", None) or (r.get("class_name") if isinstance(r, dict) else "") or ""
            ).strip()
            if school_id and exam_id:
                pairs[(school_id, exam_id)] = exam_name or pairs.get((school_id, exam_id), "")
                classes_by_pair.setdefault((school_id, exam_id), set())
                if class_name:
                    classes_by_pair[(school_id, exam_id)].add(class_name)

    totals = {"inserted": 0, "updated": 0, "skipped": 0, "detected": 0, "exams": 0}
    for (school_id, exam_id), exam_name in pairs.items():
        try:
            st = detect_and_upsert_for_exam(
                session,
                db_type=db_type,
                config=config,
                workspace_oid=workspace_oid,
                datasource_id=datasource_id,
                school_id=school_id,
                exam_id=exam_id,
                exam_name=exam_name,
                source=SOURCE_SCORE_IMPORT,
                class_names=sorted(classes_by_pair.get((school_id, exam_id)) or []),
            )
            for k in ("inserted", "updated", "skipped", "detected"):
                totals[k] += int(st.get(k) or 0)
            totals["exams"] += 1
        except Exception:  # noqa: BLE001 — 提醒失败不阻断导入成功
            logger.exception(
                "scan_alerts_after_import failed school=%s exam=%s", school_id, exam_id
            )
    return totals
```

## src/agent/education/api.py :: _overview_agg_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/api.py:952)

```python
def _overview_agg_sql(
    ov_cols: list[str],
    bars: list[dict[str, Any]],
    *,
    exam_name: str,
    track: str,
    include_school: bool = True,
) -> str | None:
    """区县/学校/选科达线聚合 SQL；缺总分列时返回 None。

    始终按选科分组，达线 CASE 只比较总分，便于一次查出全市/物理/历史。
    """
    if not ov_cols or not bars:
        return None
    total_col = _first_col(ov_cols, ("zf6m", "zf4m", "zf3m", "zf", "total", "total_score"))
    if not total_col:
        return None
    district_col = _first_col(ov_cols, ("dq", "district", "qx"))
    school_col = _first_col(ov_cols, ("xx", "school_id", "school"))
    exam_col = _first_col(ov_cols, ("exam_name", "exam", "ksmc"))
    track_col = _first_col(ov_cols, ("xkkm", "xkqk", "track", "xkfx"))
    d_expr = (
        f"COALESCE(CAST({_ident(district_col)} AS TEXT), '未知区县')"
        if district_col
        else "'未知区县'"
    )
    s_expr = (
        f"COALESCE(CAST({_ident(school_col)} AS TEXT), '')"
        if school_col and include_school
        else "''"
    )
    t_ident = _ident(total_col)
    reached = [
        f"SUM(CASE WHEN {t_ident} >= {float(bar['threshold'])} THEN 1 ELSE 0 END) AS r{i}"
        for i, bar in enumerate(bars)
    ]
    where: list[str] = []
    if exam_name and exam_col:
        where.append(f"{_ident(exam_col)} = '{_sql_quote(exam_name)}'")
    track_pred = _track_sql_predicate(track_col, track) if track else ""
    if track_pred:
        where.append(track_pred)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    group_by = "GROUP BY 1, 2, 3" if include_school else "GROUP BY 1, 3"
    return (
        f"SELECT {d_expr} AS district, {s_expr} AS school_name, "
        f"{_track_case_sql(track_col)} AS track, "
        f"COUNT(*) AS candidates, {', '.join(reached)} "
        f"FROM tb_score_overview{where_sql} "
        f"{group_by} ORDER BY 1, 2, 3 LIMIT 5000"
    )
```

## src/agent/education/api.py :: list_raw_import_batches

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/api.py:1631)

```python
async def list_raw_import_batches(
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    workspace_oid: int = Depends(get_workspace_oid),
) -> dict:
    from datasource.db.db import execute_sql

    _ds_id, _scope, db_type, config = _prepare_raw_import(current_user, workspace_oid)
    ok, msg, data = execute_sql(
        db_type,
        config,
        "SELECT id, batch_name, exam_time FROM tb_exam_batch ORDER BY exam_time DESC NULLS LAST, id DESC LIMIT 500",
    )
    if not ok:
        raise BadRequestException(msg or "查询批次失败")
    cols = list((data or {}).get("columns") or [])
    rows = []
    for row in (data or {}).get("rows") or []:
        if isinstance(row, dict):
            rec = row
        else:
            rec = {cols[i]: row[i] for i in range(min(len(cols), len(row)))}
        rows.append(
            {
                "id": rec.get("id"),
                "batch_name": rec.get("batch_name"),
                "exam_time": rec.get("exam_time"),
            }
        )
    return success_response(data={"batches": rows})
```

## src/agent/education/api.py :: list_raw_import_papers

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/api.py:1730)

```python
async def list_raw_import_papers(
    request: Request,
    exam_batch_id: int = Query(...),
    current_user: UserResponse = Depends(get_current_user),
    workspace_oid: int = Depends(get_workspace_oid),
) -> dict:
    from datasource.db.db import execute_sql
    from src.agent.education.raw_import import (
        _REQUIRED_SUBJECTS,
        _coerce_int_id,
        _detail_import_status_by_exam,
        _empty_detail_status,
        _overview_import_status,
    )

    _ds_id, scope, db_type, config = _prepare_raw_import(current_user, workspace_oid)
    ok, msg, data = execute_sql(
        db_type,
        config,
        (
            "SELECT id, subject, exam_score FROM tb_exam "
            f"WHERE exam_batch_id = {int(exam_batch_id)}"
        ),
    )
    if not ok:
        raise BadRequestException(msg or "查询试卷失败")
    cols = list((data or {}).get("columns") or [])
    papers = []
    seen: dict[str, int] = {}
    duplicate_subjects: list[str] = []
    for row in (data or {}).get("rows") or []:
        rec = row if isinstance(row, dict) else {cols[i]: row[i] for i in range(min(len(cols), len(row)))}
        subject = str(rec.get("subject") or rec.get("subject_name") or "").strip()
        papers.append(
            {
                "exam_id": rec.get("id"),
                "subject": subject,
                "exam_score": rec.get("exam_score"),
            }
        )
        if subject:
            seen[subject] = seen.get(subject, 0) + 1
            if seen[subject] == 2:
                duplicate_subjects.append(subject)
    present = {p["subject"] for p in papers if p["subject"]}
    missing_subjects = [s for s in _REQUIRED_SUBJECTS if s not in present]
    overview = _overview_import_status(db_type, config, int(exam_batch_id), scope)
    detail_by_exam = _detail_import_status_by_exam(
        db_type, config, [p.get("exam_id") for p in papers], scope
    )
    for paper in papers:
        eid = _coerce_int_id(paper.get("exam_id"))
        paper["detail"] = dict(
            detail_by_exam.get(eid, _empty_detail_status())
            if eid is not None
            else _empty_detail_status()
        )
    return success_response(
        data={
            "papers": papers,
            "missing_subjects": missing_subjects,
            "duplicate_subjects": duplicate_subjects,
            "overview": overview,
        }
    )
```

## src/agent/education/api.py :: _load_line_reach_bar_rows

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/api.py:1011)

```python
async def _load_line_reach_bar_rows(execute) -> list[dict[str, Any]]:
    return await _fetch_dicts(execute, "SELECT * FROM tb_fraction_bar LIMIT 500")
```

## src/agent/education/api.py :: create_raw_import_batch

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/api.py:1665)

```python
async def create_raw_import_batch(
    request: Request,
    batch_name: str = Form(...),
    exam_time: str = Form(...),
    current_user: UserResponse = Depends(get_current_user),
    workspace_oid: int = Depends(get_workspace_oid),
) -> dict:
    from datasource.db.db import WriteDbSession

    name = (batch_name or "").strip()
    when = (exam_time or "").strip()
    if not name:
        raise BadRequestException("批次名称不能为空")
    _ds_id, _scope, db_type, config = _prepare_raw_import(current_user, workspace_oid)
    with WriteDbSession(db_type, config) as session:
        ok, msg, data = session.execute_query(
            "SELECT id, batch_name, exam_time FROM tb_exam_batch WHERE batch_name = %s",
            (name,),
        )
        if not ok:
            raise BadRequestException(msg or "查询批次失败")
        cols = list((data or {}).get("columns") or [])
        existing = (data or {}).get("rows") or []
        if existing:
            row = existing[0]
            rec = (
                row
                if isinstance(row, dict)
                else {cols[i]: row[i] for i in range(min(len(cols), len(row)))}
            )
            return error_response(
                code=400,
                message=f"批次『{name}』已存在",
                data={
                    "id": rec.get("id"),
                    "batch_name": rec.get("batch_name"),
                    "exam_time": rec.get("exam_time"),
                },
            )
        ok, msg, _ = session.execute_write(
            "INSERT INTO tb_exam_batch (batch_name, exam_time) VALUES (%s, %s)",
            (name, when),
        )
        if not ok:
            session.rollback()
            raise BadRequestException(msg or "创建批次失败")
        session.commit()
        ok2, _msg2, data2 = session.execute_query(
            "SELECT id, batch_name, exam_time FROM tb_exam_batch WHERE batch_name = %s",
            (name,),
        )
    if not ok2:
        raise BadRequestException("创建批次后查询失败")
    cols2 = list((data2 or {}).get("columns") or [])
    row2 = ((data2 or {}).get("rows") or [None])[0]
    if row2 is None:
        raise BadRequestException("创建批次后未找到记录")
    rec = row2 if isinstance(row2, dict) else {cols2[i]: row2[i] for i in range(min(len(cols2), len(row2)))}
    return success_response(
        data={"id": rec.get("id"), "batch_name": rec.get("batch_name"), "exam_time": rec.get("exam_time")}
    )
```

## src/agent/education/api.py :: _probe_columns

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/api.py:911)

```python
async def _probe_columns(execute, table: str) -> list[str]:
    table_sql = _ident(table)
    try:
        result = await execute(f"SELECT * FROM {table_sql} LIMIT 1")
    except Exception:
        return []
    return [str(c) for c in (result.get("columns") or [])]
```

## src/agent/education/api.py :: _load_meta_options

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/api.py:741)

```python
async def _load_meta_options(
    orch: ReportOrchestrator,
    *,
    school_name: str | None,
    exam_name: str | None,
    class_name: str | None,
    subject: str | None,
    jc: str | None = None,
    edu_scope: Any = None,
) -> dict[str, list[str]]:
    """按 edu schema 查 DISTINCT；SQL 经权限执行，并按 edu_scope 再收敛选项。"""
    from datasource.service.edu_permission import EduScope

    execute = orch._execute_sql
    mapping = await orch._resolve_schema()
    empty = {"schools": [], "exams": [], "classes": [], "subjects": [], "cohorts": []}
    if getattr(mapping, "source", None) != "config_edu":
        return empty

    scope = edu_scope if isinstance(edu_scope, EduScope) else EduScope()
    jc_label = normalize_jc_label(jc or "")

    def _filters(*, exclude: set[str]) -> list[str]:
        parts: list[str] = []
        if school_name and "school" not in exclude:
            parts.append(_school_sql_filter(school_name))
        if exam_name and "exam" not in exclude:
            parts.append(f"{EXAM_NAME_SQL} LIKE '%{_sql_quote(exam_name)}%'")
        if class_name and "class" not in exclude:
            parts.append(f"sc.class LIKE '%{_sql_quote(class_name)}%'")
        if subject and "subject" not in exclude:
            parts.append(f"sc.subject_name LIKE '%{_sql_quote(subject)}%'")
        if jc_label and "jc" not in exclude:
            parts.append(f"{EXAM_NAME_SQL} LIKE '%{_sql_quote(jc_label)}%'")
        return parts

    def _where(parts: list[str], extra: str) -> str:
        all_parts = [*parts, extra]
        return " WHERE " + " AND ".join(all_parts)

    # 必须经 tb_score，才能挂上 school_id / class 教育权限谓词
    score_from = (
        "FROM tb_score sc "
        "JOIN tb_school sch ON sc.school_id = sch.id "
        "JOIN tb_exam e ON sc.exam_id = e.id "
        "LEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id"
    )

    schools = await _distinct_col(
        execute,
        "SELECT DISTINCT COALESCE(NULLIF(TRIM(sch.s_name), ''), sch.name) AS v "
        f"{score_from}"
        + _where(
            _filters(exclude={"school"}),
            "("
            "(sch.s_name IS NOT NULL AND CAST(sch.s_name AS TEXT) <> '')"
            " OR (sch.name IS NOT NULL AND CAST(sch.name AS TEXT) <> '')"
            ")",
        )
        + " ORDER BY v LIMIT 500",
    )
    schools = _plain_school_options(schools)
    exams_all = await _distinct_col(
        execute,
        "SELECT DISTINCT " + EXAM_NAME_SQL + " AS v "
        f"{score_from}"
        + _where(
            _filters(exclude={"exam", "jc"}),
            f"{EXAM_NAME_SQL} IS NOT NULL AND CAST({EXAM_NAME_SQL} AS TEXT) <> ''",
        )
        + " ORDER BY v LIMIT 500",
    )
    cohorts = extract_jc_labels(exams_all)
    exams = [e for e in exams_all if not jc_label or jc_label in e]
    classes = await _distinct_col(
        execute,
        "SELECT DISTINCT sc.class AS v "
        f"{score_from}"
        + _where(
            _filters(exclude={"class"}),
            "sc.class IS NOT NULL AND CAST(sc.class AS TEXT) <> ''",
        )
        + " ORDER BY v LIMIT 500",
    )
    subjects = await _distinct_col(
        execute,
        "SELECT DISTINCT sc.subject_name AS v "
        f"{score_from}"
        + _where(
            _filters(exclude={"subject"}),
            "sc.subject_name IS NOT NULL AND CAST(sc.subject_name AS TEXT) <> ''",
        )
        + " ORDER BY v LIMIT 500",
    )

    # 按账号 edu_scope 再收敛（双保险：名称配置 / 班级名单）
    if scope.school_name:
        sn = scope.school_name.strip()
        schools = [s for s in schools if s == sn or sn in s or s in sn]
        if not schools and sn:
            schools = [sn]
    if scope.class_names:
        allowed = {c.strip() for c in scope.class_names if c and str(c).strip()}
        if allowed:
            classes = [c for c in classes if c in allowed]
            if not classes:
                classes = sorted(allowed)

    return {
        "schools": schools,
        "exams": exams,
        "classes": classes,
        "subjects": subjects,
        "cohorts": cohorts,
    }
```

## src/agent/education/bureau_analysis.py :: school_lookup_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/bureau_analysis.py:220)

```python
def school_lookup_sql(school_name: str) -> str:
    """按中文校名从 tb_school 取 id/name，供对齐 overview.xx。"""
    lit = _str(school_name).replace("'", "''")
    from src.agent.education.privacy_mode import is_anonymize_display_enabled

    if is_anonymize_display_enabled():
        return (
            "SELECT id, name FROM tb_school "
            f"WHERE name LIKE '%{lit}%' LIMIT 50"
        )
    return (
        "SELECT id, name, s_name FROM tb_school "
        f"WHERE s_name LIKE '%{lit}%' OR name LIKE '%{lit}%' LIMIT 50"
    )
```

## src/agent/education/bureau_analysis.py :: school_city_avg_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/bureau_analysis.py:303)

```python
def school_city_avg_sql(exam_name: str, school_name: str, track: str = "") -> str:
    """该校 vs 全市均分：聚合 UNION，不拉学生行。"""
    exam_lit = _str(exam_name).replace("'", "''")
    sch_lit = _str(school_name).replace("'", "''")
    track_pred = ""
    if track == "物理类":
        track_pred = " AND xkkm LIKE '物%'"
    elif track == "历史类":
        track_pred = " AND (xkkm LIKE '史%' OR xkkm LIKE '历%')"
    return (
        f"SELECT '{sch_lit}' AS scope, ROUND(AVG(zf6m), 2) AS avg_zf6m, COUNT(*) AS n "
        f"FROM tb_score_overview WHERE exam_name = '{exam_lit}'{track_pred} "
        f"AND xx LIKE '%{sch_lit}%' "
        "UNION ALL "
        f"SELECT '全市' AS scope, ROUND(AVG(zf6m), 2) AS avg_zf6m, COUNT(*) AS n "
        f"FROM tb_score_overview WHERE exam_name = '{exam_lit}'{track_pred}"
    )
```

## src/agent/education/bureau_analysis.py :: overview_exam_names_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/bureau_analysis.py:413)

```python
def overview_exam_names_sql() -> str:
    return (
        "SELECT DISTINCT exam_name FROM tb_score_overview "
        "WHERE exam_name IS NOT NULL AND exam_name <> '' "
        "ORDER BY exam_name LIMIT 40"
    )
```

## src/agent/education/bureau_analysis.py :: overview_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/bureau_analysis.py:421)

```python
def overview_select_sql(exam_name: str) -> str:
    lit = (exam_name or "").replace("'", "''")
    from src.agent.education.privacy_mode import is_anonymize_display_enabled

    extra = "" if is_anonymize_display_enabled() else "xm, xh, "
    return (
        f"SELECT exam_name, {extra}anon_stu_id, xx, dq, bj, xkkm, xsxz, xxlb, "
        "zf3m, zf4m, zf6m, yw, ywzw, sx, sxkg, yy, yyzw, "
        "wl, hx, sw, zz, ls, dl, hxzh, hxdj, swzh, swdj, zzzh, zzdj, dlzh, dldj "
        f"FROM tb_score_overview WHERE exam_name = '{lit}' LIMIT 50000"
    )
```

## src/agent/education/bureau_analysis.py :: elite_class_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/bureau_analysis.py:434)

```python
def elite_class_select_sql(exam_name: str) -> str:
    lit = (exam_name or "").replace("'", "''")
    return (
        "SELECT school_id, class_name, track FROM tb_elite_class "
        f"WHERE exam_name = '{lit}' LIMIT 500"
    )
```

## src/agent/education/bureau_analysis.py :: fraction_bar_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/bureau_analysis.py:442)

```python
def fraction_bar_select_sql(exam_name: str) -> str:
    lit = (exam_name or "").replace("'", "''")
    return (
        "SELECT * FROM tb_fraction_bar "
        f"WHERE exam_name = '{lit}' LIMIT 20"
    )
```

## src/agent/education/demo_report.py :: _jan_exam_names_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/demo_report.py:425)

```python
def _jan_exam_names_sql() -> str:
    return (
        "SELECT DISTINCT exam_name FROM tb_score_overview "
        "WHERE exam_name LIKE '%2026届%' AND exam_name LIKE '%高三%' "
        "AND exam_name LIKE '%1月%' "
        "ORDER BY exam_name LIMIT 20"
    )
```

## src/agent/education/demo_report.py :: school_city_level_track_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/demo_report.py:500)

```python
def school_city_level_track_sql(exam_name: str, school_name: str) -> str:
    lit = _sql_lit(exam_name)
    pred = f"xx LIKE '%{_sql_lit(school_name)}%'"
    return (
        "SELECT CASE WHEN xkkm LIKE '物%' THEN '物理类' "
        "WHEN xkkm LIKE '史%' OR xkkm LIKE '历%' THEN '历史类' ELSE '' END AS track, "
        f"COUNT(CASE WHEN {pred} AND zf6m IS NOT NULL THEN 1 END) AS school_n, "
        "COUNT(CASE WHEN zf6m IS NOT NULL THEN 1 END) AS city_n, "
        f"{_round_avg(f'CASE WHEN {pred} THEN zf6m END')} AS school_avg, "
        f"{_round_avg('zf6m')} AS city_avg "
        "FROM tb_score_overview "
        f"WHERE exam_name = '{lit}' AND {_enrolled_pred()} "
        "GROUP BY 1"
    )
```

## src/agent/education/demo_report.py :: school_city_level_class_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/demo_report.py:516)

```python
def school_city_level_class_sql(exam_name: str, school_name: str) -> str:
    lit = _sql_lit(exam_name)
    pred = f"xx LIKE '%{_sql_lit(school_name)}%'"
    return (
        "SELECT bj, "
        "ROUND(CAST(AVG(zf6m) AS numeric), 1) AS avg, "
        "COUNT(*) AS n "
        "FROM tb_score_overview "
        f"WHERE exam_name = '{lit}' AND {_enrolled_pred()} AND {pred} "
        "AND zf6m IS NOT NULL AND bj IS NOT NULL AND CAST(bj AS TEXT) <> '' "
        "GROUP BY bj ORDER BY AVG(zf6m) DESC"
    )
```

## src/agent/education/demo_report.py :: school_city_level_school_avg_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/demo_report.py:447)

```python
def school_city_level_school_avg_sql(exam_name: str) -> str:
    """按校聚合总分/九科，全市约几十行，供校均排名。"""
    lit = _sql_lit(exam_name)
    bits: list[str] = []
    for _, col in _SUBJECT_COLS:
        bits.append(f"COUNT(*) FILTER (WHERE {col} > 0) AS n_{col}")
        bits.append(f"{_round_avg_sitters(col)} AS {col}")
    for _, col in _TOTAL_COLS:
        bits.append(f"COUNT({col}) AS n_{col}")
        bits.append(f"{_round_avg(col)} AS {col}")
    return (
        "SELECT xx, COUNT(*) AS n, "
        + ", ".join(bits)
        + " FROM tb_score_overview "
        f"WHERE exam_name = '{lit}' AND {_enrolled_pred()} "
        "AND xx IS NOT NULL AND CAST(xx AS TEXT) <> '' "
        "GROUP BY xx"
    )
```

## src/agent/education/demo_report.py :: school_city_level_kpi_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/demo_report.py:467)

```python
def school_city_level_kpi_sql(exam_name: str, school_name: str) -> str:
    """本校 vs 全市一行 KPI：均分、标准差、高分段、分数段人数。"""
    lit = _sql_lit(exam_name)
    pred = f"xx LIKE '%{_sql_lit(school_name)}%'"
    band_bits: list[str] = []
    for i, (_, lo, hi) in enumerate(_BANDS_SPEC):
        cond = "zf6m IS NOT NULL"
        if lo is not None:
            cond += f" AND zf6m >= {lo}"
        if hi is not None:
            cond += f" AND zf6m <= {hi}"
        band_bits.append(
            f"COUNT(CASE WHEN {pred} AND {cond} THEN 1 END) AS s_b{i}"
        )
        band_bits.append(f"COUNT(CASE WHEN {cond} THEN 1 END) AS c_b{i}")
    return (
        "SELECT "
        f"COUNT(CASE WHEN {pred} AND zf6m IS NOT NULL THEN 1 END) AS school_n, "
        "COUNT(CASE WHEN zf6m IS NOT NULL THEN 1 END) AS city_n, "
        f"{_round_avg(f'CASE WHEN {pred} THEN zf6m END')} AS zf6m_school, "
        f"{_round_avg('zf6m')} AS zf6m_city, "
        f"ROUND(CAST(STDDEV_POP(CASE WHEN {pred} THEN zf6m END) AS numeric), 1) AS std_school, "
        "ROUND(CAST(STDDEV_POP(zf6m) AS numeric), 1) AS std_city, "
        f"COUNT(CASE WHEN {pred} AND zf6m >= 600 THEN 1 END) AS n_600, "
        "COUNT(CASE WHEN zf6m >= 600 THEN 1 END) AS city_n_600, "
        f"COUNT(CASE WHEN {pred} AND zf6m >= 650 THEN 1 END) AS n_650, "
        "COUNT(CASE WHEN zf6m >= 650 THEN 1 END) AS city_n_650, "
        + ", ".join(band_bits)
        + " FROM tb_score_overview "
        f"WHERE exam_name = '{lit}' AND {_enrolled_pred()}"
    )
```

## src/agent/education/difficulty_curve.py :: item_catalog_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/difficulty_curve.py:561)

```python
def item_catalog_sql(exam_name: str, subject_name: str) -> str:
    exam = sql_lit(exam_name)
    subj = sql_lit(subject_name)
    return (
        "SELECT DISTINCT sd.question_no AS question_no "
        "FROM tb_score_detail sd "
        "JOIN tb_score sc ON sc.exam_id = sd.exam_id AND sc.student_id = sd.student_id "
        "JOIN tb_exam e ON sc.exam_id = e.id "
        "LEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id "
        f"WHERE sc.subject_name = '{subj}' "
        f"AND (eb.batch_name = '{exam}' OR e.exam_name LIKE '%{exam}%') "
        "AND sd.question_no IS NOT NULL AND sd.question_no <> '' "
        "ORDER BY sd.question_no LIMIT 200"
    )
```

## src/agent/education/difficulty_curve.py :: exam_full_score_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/difficulty_curve.py:622)

```python
def exam_full_score_sql(exam_name: str, subject_name: str) -> str:
    exam = sql_lit(exam_name)
    subj = sql_lit(subject_name)
    return (
        "SELECT MAX(e.exam_score) AS exam_score FROM tb_exam e "
        "LEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id "
        f"WHERE e.subject = '{subj}' "
        f"AND (eb.batch_name = '{exam}' OR e.exam_name LIKE '%{exam}%') "
        "LIMIT 1"
    )
```

## src/agent/education/difficulty_curve.py :: item_band_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/difficulty_curve.py:577)

```python
def item_band_sql(
    exam_name: str,
    subject_name: str,
    subject_col: str,
    question_nos: list[str] | None = None,
    *,
    school: str = "",
    class_name: str = "",
) -> str:
    exam = sql_lit(exam_name)
    subj = sql_lit(subject_name)
    col = re.sub(r"[^a-z0-9_]", "", (subject_col or "").lower()) or "sx"
    q_filter = ""
    if question_nos:
        ins = ", ".join("'" + sql_lit(q) + "'" for q in question_nos)
        q_filter = f" AND eq.question_no IN ({ins})"
    school_f = f" AND ov.xx LIKE '%{sql_lit(school)}%'" if school else ""
    class_f = f" AND ov.bj LIKE '%{sql_lit(class_name)}%'" if class_name else ""
    # 小题分导入会跳过空单元格（未写 0 分）。INNER JOIN 明细会丢掉答错的人，
    # 选择题看起来整段 100%。以应考学生为底，缺行当 0 分。
    return (
        "SELECT ((CAST(ov." + col + " AS int) - 1) / 10) * 10 + 1 AS band_lo, "
        "eq.question_no AS question_no, "
        "ROUND(AVG(COALESCE(sd.score, 0)::numeric) * 100 "
        "/ NULLIF(MAX(eq.question_score), 0), 2) AS score_rate, "
        "COUNT(*) AS n "
        "FROM tb_score_overview ov "
        "JOIN tb_score sc ON sc.student_id = ov.anon_stu_id "
        f"AND sc.subject_name = '{subj}' "
        "JOIN tb_exam e ON sc.exam_id = e.id "
        "LEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id "
        "JOIN tb_exam_question eq ON eq.exam_id = sc.exam_id "
        "LEFT JOIN tb_score_detail sd ON sd.exam_id = sc.exam_id "
        "AND sd.student_id = ov.anon_stu_id "
        "AND sd.question_no = eq.question_no "
        f"WHERE ov.exam_name = '{exam}' "
        f"AND (eb.batch_name = '{exam}' "
        f"OR (eb.batch_name IS NULL AND e.exam_name LIKE '%{exam}%')) "
        f"AND ov.{col} > 0 "
        f"{school_f}{class_f}{q_filter} "
        "GROUP BY 1, eq.question_no "
        "ORDER BY 1, eq.question_no LIMIT 2000"
    )
```

## src/agent/education/filter_peek.py :: peek_edu_filter_values

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/filter_peek.py:111)

```python
def peek_edu_filter_values(
    execute: ExecuteFn,
    *,
    exam_hint: str = "",
    table: str = "tb_score_indicator",
) -> dict[str, Any]:
    """执行 DISTINCT 探查，返回结构化维值。

    ``execute(sql) -> (ok, msg, result)``，result 形如 ``{columns, rows}``。
    """
    hint = str(exam_hint or "").strip()
    primary = (table or "tb_score_indicator").strip() or "tb_score_indicator"
    tables_try = [primary]
    if primary != "tb_score_overview":
        tables_try.append("tb_score_overview")
    if primary != "tb_score_indicator":
        tables_try.append("tb_score_indicator")

    last_error = ""
    for tbl in tables_try:
        where = ""
        if hint:
            where = f" WHERE exam_name LIKE '%{_sql_quote(hint)}%'"
        # indicator: district/line_name/track；overview: dq，无 line_name
        if tbl == "tb_score_overview":
            sql = (
                f"SELECT DISTINCT exam_name, dq AS district "
                f"FROM tb_score_overview{where} "
                f"ORDER BY 1, 2 LIMIT 200"
            )
        else:
            sql = (
                f"SELECT DISTINCT exam_name, district, line_name, track "
                f"FROM tb_score_indicator{where} "
                f"ORDER BY 1, 2, 3, 4 LIMIT 500"
            )
        ok, msg, result = execute(sql)
        if not ok:
            last_error = msg or "查询失败"
            # 无 exam_name 列时去掉 hint 再试一次
            if hint and where:
                ok2, msg2, result2 = execute(
                    sql.replace(where, "") if where in sql else sql
                )
                if ok2:
                    ok, msg, result = ok2, msg2, result2
                else:
                    last_error = msg2 or last_error
                    continue
            else:
                continue

        exam_names = _col_values(result, "exam_name")
        districts = _col_values(result, "district")
        if not districts:
            districts = _col_values(result, "dq")
        line_names = _col_values(result, "line_name")
        tracks = _col_values(result, "track")
        payload = {
            "table": tbl,
            "exam_hint": hint,
            "exam_names": exam_names,
            "districts": districts,
            "line_names": line_names,
            "tracks": tracks,
            "sql": sql,
        }
        if not exam_names and not districts and hint:
            # hint 过严：无 hint 再 peek 一次本表
            if tbl == "tb_score_overview":
                sql_all = (
                    "SELECT DISTINCT exam_name, dq AS district "
                    "FROM tb_score_overview ORDER BY 1, 2 LIMIT 200"
                )
            else:
                sql_all = (
                    "SELECT DISTINCT exam_name, district, line_name, track "
                    "FROM tb_score_indicator ORDER BY 1, 2, 3, 4 LIMIT 500"
                )
            ok_all, _, result_all = execute(sql_all)
            if ok_all and result_all:
                payload["exam_names"] = _col_values(result_all, "exam_name")
                d2 = _col_values(result_all, "district") or _col_values(result_all, "dq")
                payload["districts"] = d2
                payload["line_names"] = _col_values(result_all, "line_name")
                payload["tracks"] = _col_values(result_all, "track")
                payload["note"] = "exam_hint 未命中行，已回退为全表候选"
        return payload

    return {
        "table": primary,
        "exam_hint": hint,
        "exam_names": [],
        "districts": [],
        "line_names": [],
        "tracks": [],
        "error": last_error or "无法读取过滤维值",
    }
```

## src/agent/education/kpi_sql.py :: build_primary_exam_id_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/kpi_sql.py:31)

```python
def build_primary_exam_id_sql(where_sql: str = "") -> str:
    """参与人数最多的 exam_id（与 prepare_score_rows_for_kpi 收敛策略一致）。"""
    where = _normalize_where(where_sql)
    return (
        "SELECT sc.exam_id AS exam_id\n"
        f"{SCORE_JOIN_FROM}"
        f"{where}\n"
        "GROUP BY sc.exam_id\n"
        "ORDER BY COUNT(*) DESC\n"
        "LIMIT 1"
    )
```

## src/agent/education/kpi_sql.py :: build_score_count_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/kpi_sql.py:44)

```python
def build_score_count_sql(where_sql: str = "") -> str:
    where = _normalize_where(where_sql)
    if where:
        return (
            "SELECT COUNT(*) AS cnt\n"
            f"{SCORE_JOIN_FROM}"
            f"{where}\n"
            "AND sc.score > 0"
        )
    return (
        "SELECT COUNT(*) AS cnt\n"
        f"{SCORE_JOIN_FROM}\n"
        "WHERE sc.score > 0"
    )
```

## src/agent/education/kpi_sql.py :: build_kpi_aggregate_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/kpi_sql.py:60)

```python
def build_kpi_aggregate_sql(where_sql: str, config: EducationConfig) -> str:
    """单行 KPI 聚合；无 LIMIT。"""
    where = _normalize_where(where_sql)
    default_fs = float(config.default_full_score)
    pass_r = float(config.pass_ratio)
    exc_r = float(config.excellent_ratio)
    good_r = float(config.good_ratio)
    low_r = float(config.low_score_ratio)
    ratios = [float(r) for r in (config.score_segment_ratios or [0.6, 0.7, 0.8, 0.9])]
    # 边界比例：0, r0, r1, ..., 1.0
    bound_ratios = [0.0] + ratios + [1.0]

    seg_selects: list[str] = []
    for i in range(len(bound_ratios) - 1):
        lo_r, hi_r = bound_ratios[i], bound_ratios[i + 1]
        if i == len(bound_ratios) - 2:
            cond = f"b.score >= meta.fs * {lo_r} AND b.score <= meta.fs * {hi_r}"
        else:
            cond = f"b.score >= meta.fs * {lo_r} AND b.score < meta.fs * {hi_r}"
        seg_selects.append(f"COUNT(*) FILTER (WHERE {cond}) AS seg_{i}_count")

    return (
        "WITH base AS (\n"
        "  SELECT sc.score AS score, sc.exam_score AS exam_score\n"
        f"  {SCORE_JOIN_FROM}"
        f"{where}\n"
        "),\n"
        "meta AS (\n"
        f"  SELECT COALESCE(MAX(exam_score), {default_fs}) AS fs,\n"
        "         COUNT(*) FILTER (WHERE score > 0) AS cnt\n"
        "  FROM base\n"
        ")\n"
        "SELECT\n"
        "  meta.cnt AS count,\n"
        "  meta.fs AS full_score,\n"
        "  ROUND(AVG(b.score)::numeric, 2) AS avg,\n"
        "  ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY b.score))::numeric, 2) AS median,\n"
        "  ROUND(STDDEV_SAMP(b.score)::numeric, 2) AS stdev,\n"
        "  MIN(b.score) AS min,\n"
        "  MAX(b.score) AS max,\n"
        f"  ROUND(COUNT(*) FILTER (WHERE b.score >= meta.fs * {pass_r})::numeric "
        "/ NULLIF(meta.cnt, 0) * 100, 2) AS pass_rate,\n"
        f"  ROUND(COUNT(*) FILTER (WHERE b.score >= meta.fs * {exc_r})::numeric "
        "/ NULLIF(meta.cnt, 0) * 100, 2) AS excellent_rate,\n"
        f"  ROUND(COUNT(*) FILTER (WHERE b.score >= meta.fs * {good_r})::numeric "
        "/ NULLIF(meta.cnt, 0) * 100, 2) AS good_rate,\n"
        f"  ROUND(COUNT(*) FILTER (WHERE b.score < meta.fs * {low_r})::numeric "
        "/ NULLIF(meta.cnt, 0) * 100, 2) AS low_score_rate,\n"
        f"  ROUND(COUNT(*) FILTER (WHERE b.score < meta.fs * {pass_r})::numeric "
        "/ NULLIF(meta.cnt, 0) * 100, 2) AS fail_rate,\n"
        + ",\n".join(seg_selects)
        + "\nFROM base b\nCROSS JOIN meta\n"
        "WHERE b.score > 0\n"
        "GROUP BY meta.cnt, meta.fs"
    )
```

## src/agent/education/line_reach_report.py :: exam_batch_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/line_reach_report.py:102)

```python
def exam_batch_select_sql() -> str:
    return (
        "SELECT id, batch_name, exam_time FROM tb_exam_batch "
        "ORDER BY exam_time NULLS LAST, id"
    )
```

## src/agent/education/line_reach_report.py :: indicator_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/line_reach_report.py:109)

```python
def indicator_select_sql(exam_name: str) -> str:
    lit = (exam_name or "").replace("'", "''")
    return (
        "SELECT exam_name, track, district, school_id, school_name, "
        "line_code, line_name, threshold, candidates, reached_count, reach_rate "
        f"FROM tb_score_indicator WHERE exam_name = '{lit}' LIMIT 8000"
    )
```

## src/agent/education/metric_catalog.py :: compile_metric_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/metric_catalog.py:132)

```python
def compile_metric_sql(
    spec: MetricSpec,
    bound: Mapping[str, str],
    *,
    question: str = "",
    config: Any = None,
) -> str:
    """编译认证指标 SQL。"""
    from src.agent.education.config import EducationConfig

    cfg = config if isinstance(config, EducationConfig) else EducationConfig()
    where = build_metric_where(bound)
    if spec.id == METRIC_SCORE_KPI:
        return build_kpi_aggregate_sql(where, cfg)
    if spec.id == METRIC_OVERVIEW_TOTAL:
        col = overview_score_column(question)
        where_ov = where.replace("sc.class_name", "bj").replace("sc.bj", "bj")
        where_ov = where_ov.replace("sc.xsxz", "xsxz").replace("sc.district", "dq")
        return (
            "SELECT "
            f"ROUND(AVG({col})::numeric, 2) AS avg, "
            f"COUNT(*) FILTER (WHERE {col} > 0) AS n "
            f"FROM tb_score_overview\n{where_ov}\n"
            "AND xsxz = '在籍生'"
        )
    if spec.id == METRIC_LINE_REACH:
        exam = _sql_quote(str((bound or {}).get(SLOT_EXAM) or ""))
        school = _sql_quote(str((bound or {}).get(SLOT_SCHOOL) or ""))
        bits = [f"exam_name = '{exam}'"] if exam else []
        if school:
            bits.append(f"school_name LIKE '%{school}%'")
        district = _sql_quote(str((bound or {}).get("district") or ""))
        if district:
            bits.append(f"district LIKE '%{district}%'")
        where_lr = ("WHERE " + " AND ".join(bits)) if bits else ""
        return (
            "SELECT line_name, "
            "SUM(reached_count) AS reached, "
            "SUM(candidates) AS candidates, "
            "ROUND(SUM(reached_count)::numeric / NULLIF(SUM(candidates), 0) * 100, 2) AS rate "
            f"FROM tb_score_indicator\n{where_lr}\n"
            "GROUP BY line_name"
        )
    # 优势/薄弱：各科均分全市排名骨架，供工具执行
    return (
        "SELECT e.subject_name AS subject, "
        "ROUND(AVG(sc.score) FILTER (WHERE sc.score > 0)::numeric, 2) AS avg, "
        "COUNT(*) FILTER (WHERE sc.score > 0) AS n "
        f"{SCORE_JOIN_FROM}\n{where}\n"
        "GROUP BY e.subject_name"
    )
```

## src/agent/education/orchestrator.py :: _build_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/orchestrator.py:1791)

```python
    def _build_sql(self, spec: ReportSpec, mapping: ScoreSchemaMapping) -> str:
        """按 mapping 生成只读 SELECT。"""
        if mapping.source == "config_edu" and mapping.mode == "normalized":
            return self._build_sql_config_edu(spec, mapping)
        class_name = spec.filters.get("class_name")
        subject = spec.filters.get("subject")
        if mapping.mode == "wide":
            table = mapping.table
            subject_col = next(iter(mapping.subject_columns.values()), None)
            if not subject_col:
                return ""
            where = f" WHERE {mapping.fields.get('class_name') or 'class'} = '{_sql_escape(class_name)}'" if class_name else ""
            return f"SELECT {subject_col} AS score FROM {table}{where} LIMIT 1000"
        score_tbl = mapping.tables.get("score", "score")
        score_field = mapping.fields.get("score", "score")
        subject_field = mapping.fields.get("subject", "subject")
        where_parts: list[str] = []
        if subject:
            where_parts.append(f"{subject_field} = '{_sql_escape(subject)}'")
        where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        return f"SELECT {score_field} AS score FROM {score_tbl}{where} LIMIT 1000"
```

## src/agent/education/orchestrator.py :: _build_sql_config_edu

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/orchestrator.py:1813)

```python
    def _build_sql_config_edu(self, spec: ReportSpec, mapping: ScoreSchemaMapping) -> str:
        f = mapping.fields
        score_expr = f.get("score", "sc.score")
        full_expr = f.get("full_score", "sc.exam_score")
        subject_expr = f.get("subject", "sc.subject_name")
        class_expr = f.get("class_name", "sc.class")
        school_expr = f.get("school_name", "sch.name")
        exam_expr = f.get("exam_name", EXAM_NAME_SQL)
        # 分析工具报告用明文：校名 s_name、学生姓名 overview.xm；学号仍保留作兜底。
        school_display = "COALESCE(NULLIF(TRIM(sch.s_name), ''), sch.name)"
        student_display = (
            "COALESCE(NULLIF(TRIM(("
            "SELECT ov.xm FROM tb_score_overview ov "
            "WHERE ov.anon_stu_id = sc.student_id "
            f"AND ov.exam_name = {exam_expr} "
            "LIMIT 1"
            ")), ''), CAST(sc.student_id AS TEXT))"
        )
        sql = (
            f"SELECT {score_expr} AS score, {full_expr} AS exam_score,\n"
            f"       {class_expr} AS class, {school_display} AS school_name,\n"
            f"       sch.district AS district, {subject_expr} AS subject,\n"
            f"       sc.student_id AS student_id,\n"
            f"       {student_display} AS student_name,\n"
            f"       {exam_expr} AS exam_name\n"
            "FROM tb_score sc\n"
            "JOIN tb_school sch ON sc.school_id = sch.id\n"
            f"{EXAM_JOIN}"
        )
        # 多场考试类报告：未指定考试时不按单场过滤，便于趋势/综合/学生画像/诊断动态性；
        # 若表单已选考试（含多选 ``a;;b``），则按所选过滤。
        filters = dict(spec.filters)
        if spec.report_type in (
            ReportType.STUDENT_PROFILE,
            ReportType.TREND_TRACKING,
            ReportType.COMPREHENSIVE,
            ReportType.DIAGNOSTIC_REPORT,
        ):
            if not str(filters.get("exam_name") or "").strip():
                filters.pop("exam_name", None)
        where = _filters_to_where(filters, school_expr, class_expr, subject_expr, exam_expr)
        if where:
            sql += f"\nWHERE {where}"
        # 行级拉取仅供档案/下钻；KPI 已由无 LIMIT 聚合负责。
        # 安全上限防止超大结果集撑爆内存，截断时 DATA_INCOMPLETE=true 且不覆盖 KPI。
        limit = 50000
        return sql + f"\nLIMIT {limit}"
```

## src/agent/education/orchestrator.py :: _build_item_diagnosis_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/orchestrator.py:1861)

```python
    def _build_item_diagnosis_sql(self, spec: ReportSpec, mapping: ScoreSchemaMapping) -> str:
        f = mapping.fields
        school_expr = f.get("school_name", "sch.name")
        class_expr = f.get("class_name", "sc.class")
        subject_expr = f.get("subject", "sc.subject_name")
        exam_expr = f.get("exam_name", EXAM_NAME_SQL)
        kn_join = knowledge_names_subquery_join("pg")
        sql = (
            "SELECT sd.question_no,\n"
            "       COALESCE(kn.knowledge_name, '未关联知识点') AS knowledge_name,\n"
            "       eq.question_type AS question_type,\n"
            "       COALESCE(eq.question_score, sd.question_score) AS full_score,\n"
            "       ROUND(AVG(sd.score), 2) AS avg_score,\n"
            "       ROUND(AVG(sd.score)::numeric / NULLIF(COALESCE(eq.question_score, sd.question_score), 0) * 100, 2) AS score_rate\n"
            "FROM tb_score_detail sd\n"
            "LEFT JOIN tb_exam_question eq ON sd.question_id = eq.id\n"
            "    AND (eq.exam_id IS NULL OR eq.exam_id = sd.exam_id)\n"
            f"{kn_join}"
            "JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id\n"
            "JOIN tb_school sch ON sc.school_id = sch.id\n"
            f"{EXAM_JOIN}"
        )
        where = _filters_to_where(spec.filters, school_expr, class_expr, subject_expr, exam_expr)
        if where:
            sql += f"\nWHERE {where}"
        return (
            sql
            + "\nGROUP BY sd.question_no, COALESCE(kn.knowledge_name, '未关联知识点'), "
            "eq.question_type, COALESCE(eq.question_score, sd.question_score)\n"
            "ORDER BY sd.question_no\nLIMIT 1000"
        )
```

## src/agent/education/orchestrator.py :: _build_knowledge_diagnosis_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/orchestrator.py:1893)

```python
    def _build_knowledge_diagnosis_sql(self, spec: ReportSpec, mapping: ScoreSchemaMapping) -> str:
        f = mapping.fields
        school_expr = f.get("school_name", "sch.name")
        class_expr = f.get("class_name", "sc.class")
        subject_expr = f.get("subject", "sc.subject_name")
        exam_expr = f.get("exam_name", EXAM_NAME_SQL)
        w_join = knowledge_weighted_join()
        full_score_expr = "COALESCE(eq.question_score, sd.question_score)"
        sql = (
            "SELECT COALESCE(k.knowledge_name, '未关联知识点') AS knowledge_name,\n"
            "       k.ability_level AS ability_level,\n"
            "       COUNT(DISTINCT sd.question_no) AS question_count,\n"
            f"       ROUND(SUM(sd.score * COALESCE(eqk.w_norm, 1))::numeric / "
            f"NULLIF(SUM({full_score_expr} * COALESCE(eqk.w_norm, 1)), 0) * 100, 2) AS score_rate\n"
            "FROM tb_score_detail sd\n"
            "LEFT JOIN tb_exam_question eq ON sd.question_id = eq.id\n"
            "    AND (eq.exam_id IS NULL OR eq.exam_id = sd.exam_id)\n"
            f"{w_join}"
            "JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id\n"
            "JOIN tb_school sch ON sc.school_id = sch.id\n"
            f"{EXAM_JOIN}"
        )
        where = _filters_to_where(spec.filters, school_expr, class_expr, subject_expr, exam_expr)
        if where:
            sql += f"\nWHERE {where}"
        return sql + "\nGROUP BY COALESCE(k.knowledge_name, '未关联知识点'), k.ability_level\nORDER BY score_rate ASC\nLIMIT 1000"
```

## src/agent/education/privacy_mode.py :: privacy_sql_instruction

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/privacy_mode.py:67)

```python
def privacy_sql_instruction() -> str:
    """注入 SQL/规划提示的隐私口径。"""
    if is_anonymize_display_enabled():
        return (
            "学校字段：展示与过滤只用 sch.name 或 sch.id / sc.school_id（脱敏码）；"
            "**禁止** SELECT/引用 tb_school.s_name（可能含中文明文）。"
            "但 tb_score_overview.xx 仍是学校明文，点名学校用 xx LIKE '%校名%'；"
            "禁止把 GZ_ 校码写进 overview.xx。"
            "学生标识只用 student_id / anon_stu_id；"
            "**禁止** SELECT xm（姓名）、xh（真实学号）、sfzh/ksh。"
        )
    return (
        "当前已关闭匿名脱敏：可 SELECT xm（姓名）、xh（学号）、tb_school.s_name（学校全称）；"
        "点名学校时 tb_score 用 sch.s_name LIKE '%校名%'；"
        "tb_score_overview.xx 是学校明文（如「扬州中学」），用 xx LIKE '%校名%'；"
        "禁止 xx='GZ_…' / xx=tb_school.id / xx=tb_school.name（那些是脱敏校码，不是校名）；"
        "禁止 WHERE sch.name = '扬州中学'（name 仍是脱敏码）；"
        "仍禁止 SELECT sfzh/ksh（身份证/考生号）。"
    )
```

## src/agent/education/prompt_context.py :: build_education_sql_hint_text

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/prompt_context.py:75)

```python
def build_education_sql_hint_text(question: str) -> str:
    """给 Team/DataAnalyst 的短提示（非整包 XML）。"""
    intent = resolve_edu_sql_intent(question or "")
    term, training = build_education_prompt_extras(question)
    q = question or ""
    # 压缩：只保留关键规则行 + 示例题干
    rules: list[str] = []
    from src.agent.education.line_offset import line_offset_hint
    from src.agent.education.query_parse import (
        extract_school_type_target,
        is_citywide_nth_class_lookup_query,
        is_class_city_rank_query,
        is_class_subject_city_rank_query,
        is_school_class_comparison_query,
        is_school_vs_school_type_avg_query,
        is_subject_strength_query,
    )

    st = extract_school_type_target(q)
    type_pool = (
        f"问句点名{st}校时对照池必须 xxlb LIKE '%{st}%'，禁止全市普通高中混排。"
        if st
        else ""
    )
    if is_class_city_rank_query(q):
        rules.append(
            "班级全市六门排名必须一条 SQL 用 UNION ALL 一次返回两个口径："
            "按选考方向（人数多的一类，该类满3人进池）+ 不区分选考；"
            "禁止只报文理混排，禁止拆两次 execute_sql。"
            "每个口径返回第1名+目标班前后各3名（标记本班），禁止只查出目标班一行。"
            "排名池排除其他校（xxlb NOT LIKE '%其他%'）和整班不足10人的小班。"
            f"{type_pool}"
            "物理类 xkkm LIKE '物%'，历史类 LIKE '史%' OR LIKE '历%'；"
            "GROUP BY xx,bj 后 RANK() OVER (ORDER BY 均分 DESC)，"
            "用学校 xx 与班级 bj 定位窗口。"
        )
    if is_citywide_nth_class_lookup_query(q):
        rules.append(
            "全市第N是哪个班：没有目标班；洗净其他校（xxlb NOT LIKE '%其他%'）和整班不足10人；"
            "该科 FILTER col>0 且 HAVING 有效人数>=3；RANK 与 COUNT(*) OVER() 在进池后同一 SELECT；"
            "外层 WHERE 全市排名=N，禁止第1名+前后3名窗口，禁止外层滤已知班；"
            "化学/生物/政治/地理用 hxzh/swzh/zzzh/dlzh，禁止把行政班总数当再选科分母。"
        )
    if is_class_subject_city_rank_query(q):
        rules.append(
            "班级单科全市排名：洗净其他校（xxlb NOT LIKE '%其他%'）和整班不足10人的小班；"
            f"{type_pool}"
            "该科 FILTER col>0 且 HAVING 有效人数>=3；RANK() OVER (ORDER BY 均分 DESC NULLS LAST)；"
            "查询结果返回第1名+目标班前后各3名并标记本班，禁止只查出目标班一行；"
            "用 xx LIKE '%校名%' 与 bj 定位窗口；禁止 UNION ALL 文理双行；"
            "名次/总数≤25% 称前列，禁止称中上段；结论禁止字段名与 A01 校码。"
        )

    if is_subject_strength_query(q):
        rules.append(
            "优势/薄弱学科：按该校（有班则该班）各科均分的全市排名相对位置判断，"
            "名次/参赛数≤25%为前列（优势），≥50%为靠后（薄弱），中间为中游；"
            "禁止把本校各科里名次较差的直接叫薄弱；禁止用本校各科均分互比；"
            "GROUP BY xx（班级再加 bj）后 RANK() OVER (ORDER BY 均分 DESC NULLS LAST) "
            "与 COUNT(*) OVER()，各科须先 WHERE 均分 IS NOT NULL（或 >0）；"
            "禁止 PARTITION BY bj，禁止 COUNT(DISTINCT bj)，禁止空均分校进参赛池，"
            "xsxz='在籍生'，AVG FILTER col>0；化学/生物/政治/地理用 hxzh/swzh/zzzh/dlzh；"
            "最终结果一科一行（学科/均分/全市排名/参赛数），禁止语文均分+语文排名并排宽表。"
        )
    if is_school_class_comparison_query(q):
        rules.append(
            "班级横向对比：班级列是 bj 不是 xx；SELECT bj AS class_name，GROUP BY xx, bj；"
            "禁止 SELECT xx AS class_name，禁止只 GROUP BY xx（会把全校塌成一行）。"
            "小题为空时仍用学生行按班聚合，禁止手写学校级 AVG。"
        )
    if is_school_vs_school_type_avg_query(q):
        rules.append(
            "学校 vs 引领/支撑/发展校均分或单科：查 tb_score_overview；"
            "校类用 xxlb LIKE '%引领%' 且 xsxz=在籍生；语文=yw 且 yw > 0（缺考 0 分不计入）；"
            "禁止 JOIN tb_school 算学生均分；禁止 GROUP BY xx 再平均。"
        )
    if not is_school_vs_school_type_avg_query(q) and (
        "AVG(reach_rate)" in term or "达线" in term
    ):
        rules.append(
            "达线：区县/全市查 tb_score_indicator，SUM(reached_count)/SUM(candidates)；"
            "点名学校用 school_name LIKE '%校名%'，禁止 school_id='GZ_…'；"
            "引领/支撑/发展校 JOIN tb_school，sch.type LIKE '%引领%'（与 overview.xxlb 同源）；"
            "禁止套用全市达线报告；禁止 AVG(reach_rate)；先 peek_edu_filter_values。"
        )
    if "zf3m" in term or "zf6m" in term:
        rules.append("三门/六门均分用 tb_score_overview.zf3m/zf6m，禁止对 tb_score 三科 AVG 当三门均分。")
    rules.append(
        "凡单科分数统计（均分/标准差/均衡性/中位/最值/分数段）必须排除未选考/缺考 0 分："
        "AVG/STDDEV_SAMP(col) FILTER (WHERE col > 0)；禁止 AVG(ls/zz/dl) 或 STDDEV(ls) 除以全体人数。"
    )
    rules.append(
        "查 tb_score_overview 默认 AND xsxz='在籍生'：市报生/往届不进均分、不进全市班级或学校排名。"
    )
    rules.append(
        "选科方向只用 xkkm：物理类 LIKE '物%'，历史类必须 (LIKE '史%' OR LIKE '历%')；"
        "禁止只写 xkkm LIKE '历%'（库内是史政地，历史会变成 0 人）；"
        "禁止 xkqk IN ('134','135','136') 分轨（xkqk 常为空，IN 会少人）；"
        "跨考试 JOIN 用 anon_stu_id，有 zf6m 即算参考，不要要求两侧 xkqk 都有值。"
    )
    offset = line_offset_hint(q)
    if offset:
        rules.append(offset)
    if "hxzh" in term or "十分段" in term or "分以上" in term:
        rules.append(
            "绝对分数段查 tb_score_overview；化学用 hxzh；十分段 ((zf6m-1)/10)*10+1。"
        )
    if "peek" not in " ".join(rules).lower():
        rules.append("写 district/exam_name 过滤前先 peek_edu_filter_values；空结果禁止断言缺数。")
    import re

    qs = re.findall(r"<question>(.*?)</question>", training, re.DOTALL)
    ex = "；".join(q.strip() for q in qs[:3] if q.strip())
    return (
        f"【教育 SQL 提示 intent={intent}】"
        + " ".join(rules)
        + (f" 参考问法：{ex}" if ex else "")
    )
```

## src/agent/education/raw_import.py :: _load_overview_dimensions

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/raw_import.py:424)

```python
def _load_overview_dimensions(
    db_type: str,
    config: dict[str, Any],
    exam_batch_id: int,
    xx_values: set[str] | list[str],
) -> dict:
    tables = _table_names()
    batch_table = tables.get("exam_batch", "tb_exam_batch")
    school_table = tables.get("school", "tb_school")
    exam_table = tables.get("exam", "tb_exam")
    batch_id = int(exam_batch_id)

    ok, msg, result = execute_sql(
        db_type,
        config,
        f"SELECT id, batch_name, exam_time FROM {batch_table} WHERE id = {batch_id}",
    )
    if not ok:
        raise ValueError(msg)
    batch_rows = _rows_to_dicts(result or {})
    if not batch_rows:
        raise ValueError(f"考试批次不存在: {batch_id}")
    batch = batch_rows[0]

    schools_by_name: dict[str, Any] = {}
    names = {str(x).strip() for x in xx_values if str(x).strip()}
    if names:
        ok, msg, result = execute_sql(
            db_type,
            config,
            f"SELECT id, s_name FROM {school_table} WHERE s_name IN ({_in_literals(names)})",
        )
        if not ok:
            raise ValueError(msg)
        for row in _rows_to_dicts(result or {}):
            s_name = str(row.get("s_name") or "").strip()
            if s_name:
                schools_by_name[s_name] = str(row.get("id") or "")

    ok, msg, result = execute_sql(
        db_type,
        config,
        f"SELECT id, exam_name, subject, exam_score, exam_time "
        f"FROM {exam_table} WHERE exam_batch_id = {batch_id}",
    )
    if not ok:
        raise ValueError(msg)
    exams_by_subject: dict[str, dict] = {}
    duplicate_subjects: list[str] = []
    for row in _rows_to_dicts(result or {}):
        row = _normalize_exam_row(row)
        subject = str(row.get("subject_name") or "").strip()
        if not subject:
            continue
        if subject in exams_by_subject:
            if subject not in duplicate_subjects:
                duplicate_subjects.append(subject)
            continue
        exams_by_subject[subject] = row

    return {
        "batch": batch,
        "schools_by_name": schools_by_name,
        "exams_by_subject": exams_by_subject,
        "duplicate_subjects": duplicate_subjects,
    }
```

## src/agent/education/raw_import.py :: _load_detail_dimensions

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/raw_import.py:1259)

```python
def _load_detail_dimensions(
    db_type: str,
    config: dict[str, Any],
    exam_batch_id: int,
    exam_id: int,
    sfzh_values: set[str],
) -> dict:
    tables = _table_names()
    batch_table = tables.get("exam_batch", "tb_exam_batch")
    exam_table = tables.get("exam", "tb_exam")
    overview_table = tables.get("score_overview") or "tb_score_overview"
    question_table = tables.get("exam_question", "tb_exam_question")
    batch_id = int(exam_batch_id)
    eid = int(exam_id)

    batch_rows = _sql_ok(
        db_type, config, f"SELECT id, batch_name FROM {batch_table} WHERE id = {batch_id}"
    )
    if not batch_rows:
        raise ValueError(f"考试批次不存在: {batch_id}")
    batch = batch_rows[0]

    exam_rows = _sql_ok(
        db_type,
        config,
        (
            f"SELECT id, exam_name, subject, exam_score, exam_time, exam_batch_id "
            f"FROM {exam_table} WHERE id = {eid}"
        ),
    )
    if not exam_rows:
        raise ValueError(f"试卷不存在: {eid}")
    exam = _normalize_exam_row(exam_rows[0])
    try:
        exam_batch = int(exam.get("exam_batch_id"))
    except (TypeError, ValueError):
        exam_batch = None
    if exam_batch != batch_id:
        raise ValueError(f"试卷 {eid} 不属于所选批次")

    overview_by_sfzh: dict[str, dict] = {}
    if sfzh_values:
        batch_name = str(batch.get("batch_name") or "").replace("'", "''")
        sfzh_sql = _in_literals({str(s) for s in sfzh_values})
        ov_rows = _sql_ok(
            db_type,
            config,
            (
                f"SELECT sfzh, anon_stu_id, xx, bj, xm, ksh FROM {overview_table} "
                f"WHERE exam_name = '{batch_name}' AND sfzh IN ({sfzh_sql})"
            ),
        )
        for row in ov_rows:
            key = _normalize_id_str(row.get("sfzh"))
            if key:
                overview_by_sfzh[key] = row

    q_rows = _sql_ok(
        db_type,
        config,
        f"SELECT id, question_no, question_score FROM {question_table} WHERE exam_id = {eid}",
    )
    questions_by_no = {str(r.get("question_no") or "").strip(): r for r in q_rows if r.get("question_no")}
    return {
        "batch": batch,
        "exam": exam,
        "overview_by_sfzh": overview_by_sfzh,
        "questions_by_no": questions_by_no,
    }
```

## src/agent/education/raw_import.py :: load_raw_detail_template_meta

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/raw_import.py:1753)

```python
def load_raw_detail_template_meta(
    db_type: str,
    config: dict[str, Any],
    exam_id: int,
) -> tuple[str, list[dict[str, Any]]]:
    """读取试卷科目与题目，供生成带真实题号的小题分模板。"""
    tables = _table_names()
    exam_table = tables.get("exam", "tb_exam")
    question_table = tables.get("exam_question", "tb_exam_question")
    eid = int(exam_id)
    exam_rows = _sql_ok(
        db_type,
        config,
        f"SELECT id, subject FROM {exam_table} WHERE id = {eid}",
    )
    if not exam_rows:
        raise ValueError(f"试卷不存在: {eid}")
    exam = _normalize_exam_row(exam_rows[0])
    subject = str(exam.get("subject_name") or exam.get("subject") or "").strip() or "未命名"
    q_rows = _sql_ok(
        db_type,
        config,
        (
            f"SELECT question_no, question_score FROM {question_table} "
            f"WHERE exam_id = {eid} ORDER BY question_no"
        ),
    )
    questions = [
        {
            "question_no": str(r.get("question_no") or "").strip(),
            "question_score": r.get("question_score"),
        }
        for r in q_rows
        if str(r.get("question_no") or "").strip()
    ]
    return subject, questions
```

## src/agent/education/raw_import.py :: _overview_import_status

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/raw_import.py:501)

```python
def _overview_import_status(
    db_type: str,
    config: dict[str, Any],
    exam_batch_id: int,
    scope: EduScope | None = None,
) -> dict[str, Any]:
    """查询该批次宽表是否已导入；校管理员只统计本校。"""
    tables = _table_names()
    batch_table = tables.get("exam_batch", "tb_exam_batch")
    school_table = tables.get("school", "tb_school")
    overview_table = tables.get("score_overview") or "tb_score_overview"
    batch_id = int(exam_batch_id)
    try:
        ok, _msg, result = execute_sql(
            db_type,
            config,
            f"SELECT id, batch_name FROM {batch_table} WHERE id = {batch_id}",
        )
        if not ok:
            return _empty_overview_status()
        batch_rows = _rows_to_dicts(result or {})
        if not batch_rows:
            return _empty_overview_status()
        batch_name = str(batch_rows[0].get("batch_name") or "").strip()
        if not batch_name:
            return _empty_overview_status()

        xx_filter = ""
        if scope is not None and scope.edu_role == "school_admin":
            school_token = str(scope.school_id or "").strip()
            if not school_token:
                return _empty_overview_status()
            token_sql = school_token.replace("'", "''")
            ok, _msg, school_result = execute_sql(
                db_type,
                config,
                (
                    f"SELECT s_name FROM {school_table} "
                    f"WHERE CAST(id AS TEXT) = '{token_sql}' LIMIT 1"
                ),
            )
            school_rows = _rows_to_dicts(school_result or {}) if ok else []
            s_name = str((school_rows[0].get("s_name") if school_rows else "") or "").strip()
            if not s_name:
                return _empty_overview_status()
            escaped_name = s_name.replace("'", "''")
            xx_filter = f" AND xx = '{escaped_name}'"

        name_sql = batch_name.replace("'", "''")
        ok, _msg, count_result = execute_sql(
            db_type,
            config,
            (
                "SELECT COUNT(*) AS row_count, COUNT(DISTINCT xx) AS school_count, "
                "MAX(update_time) AS last_write_time "
                f"FROM {overview_table} "
                f"WHERE (exam_batch_id = {batch_id} OR exam_name = '{name_sql}')"
                f"{xx_filter}"
            ),
        )
        if not ok:
            return _empty_overview_status()
        rows = _rows_to_dicts(count_result or {})
        rec = rows[0] if rows else {}
        row_count = int(rec.get("row_count") or 0)
        school_count = int(rec.get("school_count") or 0)
        last_write = rec.get("last_write_time")
        return {
            "imported": row_count > 0,
            "row_count": row_count,
            "school_count": school_count,
            "last_write_time": str(last_write) if last_write is not None else None,
        }
    except (TypeError, ValueError, KeyError):
        return _empty_overview_status()
```

## src/agent/education/raw_import.py :: _detail_import_status_by_exam

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/raw_import.py:592)

```python
def _detail_import_status_by_exam(
    db_type: str,
    config: dict[str, Any],
    exam_ids: list[Any],
    scope: EduScope | None = None,
) -> dict[int, dict[str, Any]]:
    """按试卷统计小题分是否已导入；校管理员只统计本校学生。"""
    ids = [eid for eid in (_coerce_int_id(raw) for raw in exam_ids) if eid is not None]
    if not ids:
        return {}
    tables = _table_names()
    detail_table = tables.get("score_detail") or "tb_score_detail"
    stu_filter = ""
    if scope is not None and scope.edu_role == "school_admin":
        token = str(scope.school_id or "").strip()
        if not token:
            return {}
        stu_filter = f" AND student_id LIKE '{_sql_like_prefix(token)}\\_%' ESCAPE '\\'"
    try:
        ok, _msg, result = execute_sql(
            db_type,
            config,
            (
                "SELECT exam_id, COUNT(*) AS row_count, "
                "COUNT(DISTINCT student_id) AS student_count "
                f"FROM {detail_table} "
                f"WHERE exam_id IN ({','.join(str(i) for i in ids)})"
                f"{stu_filter} "
                "GROUP BY exam_id"
            ),
        )
        if not ok:
            return {}
        out: dict[int, dict[str, Any]] = {}
        for rec in _rows_to_dicts(result or {}):
            eid = _coerce_int_id(rec.get("exam_id"))
            if eid is None:
                continue
            row_count = int(rec.get("row_count") or 0)
            student_count = int(rec.get("student_count") or 0)
            out[eid] = {
                "imported": row_count > 0,
                "row_count": row_count,
                "student_count": student_count,
            }
        return out
    except (TypeError, ValueError, KeyError):
        return {}
```

## src/agent/education/scope_guard.py :: lookup_bound_school_labels

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/scope_guard.py:121)

```python
def lookup_bound_school_labels(
    school_id: str,
    *,
    datasource_id: int | None = None,
    workspace_oid: int | None = None,
) -> list[str]:
    """用 tb_school 把权限校 ID 还原成展示名（如 A01扬州中学）。失败返回空。"""
    sid = str(school_id or "").strip()
    if not sid or not _SCHOOL_ID_RE.fullmatch(sid) or not datasource_id:
        return []
    try:
        from src.agent.resource.tool.business import _load_datasource
        from src.datasource.db.db import execute_sql

        db_type, config, _name = _load_datasource(int(datasource_id), workspace_oid)
        lit = sid.replace("'", "''")
        ok, _msg, result = execute_sql(
            db_type,
            config,
            "SELECT id, name, s_name FROM tb_school "
            f"WHERE id = '{lit}' OR name = '{lit}' LIMIT 5",
        )
        if not ok or not isinstance(result, dict):
            return []
        labels: list[str] = []
        for row in result.get("rows") or []:
            vals = _row_values(row)
            for raw in vals:
                tok = str(raw or "").strip()
                if tok and tok not in labels and not _looks_like_school_id(tok):
                    labels.append(tok)
                elif tok and _SCHOOL_CODE_RE.match(tok) and tok not in labels:
                    labels.append(tok)
        return labels
    except Exception:
        return []
```

## src/agent/education/score_import.py :: _build_upsert_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/score_import.py:756)

```python
def _build_upsert_sql(
    db_type: str,
    table: str,
    cols: list[str],
    conflict_cols: tuple[str, ...] | list[str],
) -> str:
    q = _quote_ident
    col_list = ", ".join(q(c, db_type) for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    conflict_set = set(conflict_cols)
    updates = ", ".join(
        f"{q(c, db_type)} = EXCLUDED.{q(c, db_type)}" if db_type == "pg"
        else f"{q(c, db_type)} = VALUES({q(c, db_type)})"
        for c in cols if c not in conflict_set
    )
    if db_type == "pg":
        conflict = ", ".join(conflict_cols)
        return (
            f"INSERT INTO {q(table, db_type)} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
        )
    return (
        f"INSERT INTO {q(table, db_type)} ({col_list}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
```

## src/agent/education/score_import.py :: _load_dimensions

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/score_import.py:361)

```python
def _load_dimensions(
    db_type: str,
    config: dict[str, Any],
    exam_names: set[str],
    exam_ids: set[str],
    student_ids: set[str],
    school_ids: set[str],
    exam_ids_for_questions: set[str],
    question_nos: set[int],
    question_ids: set[str],
) -> tuple[
    dict[str, list[dict]],
    dict[str, dict],
    dict[str, dict],
    dict[str, dict],
    dict[tuple[str, int], dict],
    dict[str, dict],
    bool,
]:
    """批量加载 exam / student / school / question 维度（只读，不写库）。"""
    tables = _table_names()
    exam_table = tables.get("exam", "tb_exam")
    student_table = tables.get("student", "tb_student")
    school_table = tables.get("school", "tb_school")
    question_table = tables.get("exam_question", "tb_exam_question")

    schema = execute_sql(db_type, config, "SELECT 1")
    if not schema[0]:
        raise ValueError(schema[1])

    exam_cols = _schema_columns(db_type, config, exam_table)
    student_cols = _schema_columns(db_type, config, student_table)
    student_has_school_id = "school_id" in student_cols

    exams_by_name: dict[str, list[dict]] = {}
    exams_by_id: dict[str, dict] = {}
    if exam_names or exam_ids:
        select_cols = _exam_select_cols(exam_cols)
        clauses: list[str] = []
        if exam_names and ("exam_name" in select_cols or not exam_cols or "exam_name" in exam_cols):
            if "exam_name" not in select_cols:
                select_cols.append("exam_name")
            clauses.append(f"exam_name IN ({_in_literals(exam_names)})")
        if exam_ids:
            clauses.append(f"id IN ({_in_literals(exam_ids)})")
        if not clauses:
            raise ValueError(f"表 {exam_table} 无法按试卷编号/名称查询")

        sql = f"SELECT {', '.join(select_cols)} FROM {exam_table} WHERE {' OR '.join(clauses)}"
        ok, msg, result = _execute_select_in(db_type, config, sql)
        if not ok and any(c in select_cols for c in _EXAM_SUBJECT_CANDIDATES):
            # 科目列不存在时回退，避免整批失败
            select_cols = [c for c in select_cols if c not in _EXAM_SUBJECT_CANDIDATES]
            sql = f"SELECT {', '.join(select_cols)} FROM {exam_table} WHERE {' OR '.join(clauses)}"
            ok, msg, result = _execute_select_in(db_type, config, sql)
        if not ok:
            raise ValueError(msg)
        for row in _rows_to_dicts(result):
            row = _normalize_exam_row(row)
            name = str(row.get("exam_name") or "")
            exams_by_name.setdefault(name, []).append(row)
            exams_by_id[str(row.get("id") or "")] = row

        # 若仍缺科目，按 exam_id 再查一次 subject_name
        missing_subject_ids = {
            eid for eid, ex in exams_by_id.items() if eid and not str(ex.get("subject_name") or "").strip()
        }
        if missing_subject_ids:
            for subject_col in _EXAM_SUBJECT_CANDIDATES:
                ok2, _msg2, result2 = _execute_select_in(
                    db_type,
                    config,
                    f"SELECT id, {subject_col} AS subject_name FROM {exam_table} "
                    f"WHERE id IN ({_in_literals(missing_subject_ids)})",
                )
                if not ok2:
                    continue
                for row in _rows_to_dicts(result2):
                    eid = str(row.get("id") or "")
                    subj = str(row.get("subject_name") or "").strip()
                    if eid and subj and eid in exams_by_id:
                        exams_by_id[eid]["subject_name"] = subj
                        for ex in exams_by_name.get(str(exams_by_id[eid].get("exam_name") or ""), []):
                            if str(ex.get("id") or "") == eid:
                                ex["subject_name"] = subj
                missing_subject_ids = {
                    eid
                    for eid, ex in exams_by_id.items()
                    if eid and not str(ex.get("subject_name") or "").strip()
                }
                if not missing_subject_ids:
                    break

    schools_by_id: dict[str, dict] = {}
    if school_ids:
        ok, msg, result = _execute_select_in(
            db_type, config,
            f"SELECT id FROM {school_table} WHERE id IN ({_in_literals(school_ids)})",
        )
        if not ok:
            raise ValueError(msg)
        for row in _rows_to_dicts(result):
            schools_by_id[str(row.get("id") or "")] = row

    students_by_id: dict[str, dict] = {}
    if student_ids:
        ok, msg, result = _execute_select_in(
            db_type, config,
            f"SELECT id{', school_id' if student_has_school_id else ''} "
            f"FROM {student_table} WHERE id IN ({_in_literals(student_ids)})",
        )
        if not ok:
            raise ValueError(msg)
        for row in _rows_to_dicts(result):
            students_by_id[str(row.get("id") or "")] = row

    questions_by_key: dict[tuple[str, int], dict] = {}
    questions_by_id: dict[str, dict] = {}
    question_cols = _schema_columns(db_type, config, question_table)
    q_select = _pick_existing_cols(
        ("id", "exam_id", "question_no", "question_score"),
        question_cols or {"id", "exam_id", "question_no", "question_score"},
    )
    if question_ids and q_select:
        ok, msg, result = _execute_select_in(
            db_type, config,
            f"SELECT {', '.join(q_select)} FROM {question_table} "
            f"WHERE id IN ({_in_literals(question_ids)})",
        )
        if not ok:
            raise ValueError(msg)
        for row in _rows_to_dicts(result):
            qid = str(row.get("id") or "")
            questions_by_id[qid] = row
            key = (str(row.get("exam_id") or ""), int(row.get("question_no") or 0))
            questions_by_key[key] = row
    elif exam_ids_for_questions and question_nos and q_select:
        ok, msg, result = _execute_select_in(
            db_type, config,
            f"SELECT {', '.join(q_select)} FROM {question_table} "
            f"WHERE exam_id IN ({_in_literals(exam_ids_for_questions)}) "
            f"AND question_no IN ({_in_literals(question_nos)})",
        )
        if not ok:
            raise ValueError(msg)
        for row in _rows_to_dicts(result):
            qid = str(row.get("id") or "")
            questions_by_id[qid] = row
            key = (str(row.get("exam_id") or ""), int(row.get("question_no") or 0))
            questions_by_key[key] = row

    return (
        exams_by_name,
        exams_by_id,
        students_by_id,
        schools_by_id,
        questions_by_key,
        questions_by_id,
        student_has_school_id,
    )
```

## src/agent/education/score_import.py :: _check_unique_constraint

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/score_import.py:708)

```python
def _check_unique_constraint(
    db_type: str,
    config: dict[str, Any],
    table: str,
    columns: list[str],
) -> tuple[bool, str]:
    """检查表是否存在覆盖指定列的唯一约束/索引。"""
    if db_type == "pg":
        col_list = ", ".join(columns)
        sql = f"""
            SELECT 1 FROM pg_indexes
            WHERE tablename = '{table.replace("'", "''")}'
              AND indexdef ILIKE '%UNIQUE%'
              AND indexdef ILIKE '%({col_list})%'
            LIMIT 1
        """
        ok, msg, result = execute_sql(db_type, config, sql)
        if ok and result.get("row_count", 0) > 0:
            return True, ""
        return False, (
            f"表 {table} 缺少 ({', '.join(columns)}) 唯一约束，无法安全 UPSERT。"
            f"请执行：CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_{'_'.join(columns)} "
            f"ON {table} ({', '.join(columns)});"
        )
    # MySQL: check via SHOW INDEX
    ok, msg, result = execute_sql(db_type, config, f"SHOW INDEX FROM `{table}`")
    if not ok:
        return False, msg
    cols_by_key: dict[str, set[str]] = {}
    col_name_idx = (result.get("columns") or []).index("Column_name") if "Column_name" in (result.get("columns") or []) else -1
    key_name_idx = (result.get("columns") or []).index("Key_name") if "Key_name" in (result.get("columns") or []) else -1
    non_unique_idx = (result.get("columns") or []).index("Non_unique") if "Non_unique" in (result.get("columns") or []) else -1
    if col_name_idx < 0 or key_name_idx < 0:
        return True, ""  # cannot verify, allow attempt
    for row in result.get("rows") or []:
        if non_unique_idx >= 0 and row[non_unique_idx] != 0:
            continue
        key = str(row[key_name_idx])
        cols_by_key.setdefault(key, set()).add(str(row[col_name_idx]))
    wanted = set(columns)
    for cols in cols_by_key.values():
        if wanted.issubset(cols):
            return True, ""
    return False, (
        f"表 {table} 缺少 ({', '.join(columns)}) 唯一约束，无法安全 UPSERT。"
    )
```

## src/agent/education/score_indicator.py :: _lookup_exam_batch_id

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/score_indicator.py:252)

```python
def _lookup_exam_batch_id(session, exam_name: str) -> int | None:
    exam = _str(exam_name)
    if not exam:
        return None
    ok, rows, _ = _query_dicts(
        session,
        "SELECT id FROM tb_exam_batch WHERE batch_name = %s ORDER BY id LIMIT 1",
        (exam,),
    )
    if not ok or not rows:
        return None
    return _int_id(pick_col(rows[0], "id"))
```

## src/agent/education/score_indicator.py :: _probe_columns

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/score_indicator.py:320)

```python
def _probe_columns(session, table: str) -> list[str]:
    ok, _rows, cols = _query_dicts(session, f"SELECT * FROM {_ident(table)} LIMIT 0")
    return cols if ok else []
```

## src/agent/education/score_indicator.py :: _resolve_exam_batch

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/score_indicator.py:337)

```python
def _resolve_exam_batch(session, exam_batch_id: int) -> str:
    ok, rows, _ = _query_dicts(
        session,
        "SELECT batch_name FROM tb_exam_batch WHERE id = %s LIMIT 1",
        (int(exam_batch_id),),
    )
    if not ok:
        raise RuntimeError("查询 tb_exam_batch 失败")
    if not rows:
        raise ValueError("考试批次不存在")
    name = _str(pick_col(rows[0], "batch_name", "exam_name", "name"))
    if not name:
        raise ValueError("考试批次名称为空")
    return name
```

## src/agent/education/score_indicator.py :: _load_exam_batches

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/score_indicator.py:353)

```python
def _load_exam_batches(session) -> list[dict[str, Any]]:
    ok, rows, _ = _query_dicts(
        session,
        "SELECT id, batch_name FROM tb_exam_batch ORDER BY id DESC LIMIT 500",
    )
    if not ok:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        bid = _int_id(pick_col(row, "id"))
        name = _str(pick_col(row, "batch_name", "exam_name", "name"))
        if bid is None or not name:
            continue
        out.append({"id": bid, "batch_name": name})
    return out
```

## src/agent/education/score_indicator.py :: _upsert_wide_fraction_bar

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/score_indicator.py:370)

```python
def _upsert_wide_fraction_bar(session, db_type: str, exam_name: str, wide: dict[str, Any], columns: list[str]) -> str:
    exam_col = _exam_col(columns)
    if not exam_col:
        raise ValueError("tb_fraction_bar 缺少考试列")
    exam = _str(exam_name)
    batch_col = _batch_id_col(columns)
    batch_id = _int_id(wide.get(batch_col)) if batch_col else None
    where_col, where_val = exam_col, exam
    if batch_col and batch_id is not None:
        where_col, where_val = batch_col, batch_id
    ok, existing, _ = _query_dicts(
        session,
        f"SELECT {_quote(exam_col, db_type)} FROM tb_fraction_bar "
        f"WHERE {_quote(where_col, db_type)} = %s LIMIT 1",
        (where_val,),
    )
    if not ok:
        raise RuntimeError("查询 tb_fraction_bar 失败")
    if not existing and where_col != exam_col:
        ok, existing, _ = _query_dicts(
            session,
            f"SELECT {_quote(exam_col, db_type)} FROM tb_fraction_bar "
            f"WHERE {_quote(exam_col, db_type)} = %s LIMIT 1",
            (exam,),
        )
        if not ok:
            raise RuntimeError("查询 tb_fraction_bar 失败")
        if existing:
            where_col, where_val = exam_col, exam
    set_cols = [c for c in wide if c != where_col]
    if existing:
        if not set_cols:
            return "updated"
        sets = ", ".join(f"{_quote(c, db_type)} = %s" for c in set_cols)
        params = tuple(wide[c] for c in set_cols) + (where_val,)
        ok, msg, _ = session.execute_write(
            f"UPDATE tb_fraction_bar SET {sets} WHERE {_quote(where_col, db_type)} = %s",
            params,
        )
        if not ok:
            raise RuntimeError(msg or "更新 tb_fraction_bar 失败")
        return "updated"
    insert_cols = list(wide.keys())
    placeholders = ", ".join(["%s"] * len(insert_cols))
    col_sql = ", ".join(_quote(c, db_type) for c in insert_cols)
    params = tuple(wide[c] for c in insert_cols)
    ok, msg, _ = session.execute_write(
        f"INSERT INTO tb_fraction_bar ({col_sql}) VALUES ({placeholders})",
        params,
    )
    if not ok:
        raise RuntimeError(msg or "写入 tb_fraction_bar 失败")
    return "inserted"
```

## src/agent/education/score_indicator.py :: _load_bar_rows

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/score_indicator.py:425)

```python
def _load_bar_rows(session) -> list[dict[str, Any]]:
    ok, rows, _ = _query_dicts(session, "SELECT * FROM tb_fraction_bar LIMIT 500")
    return rows if ok else []
```

## src/agent/education/score_indicator.py :: _recompute_one

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/score_indicator.py:435)

```python
def _recompute_one(
    session,
    db_type: str,
    exam_name: str,
    bar_rows: list[dict[str, Any]] | None = None,
    exam_batch_id: int | None = None,
) -> dict[str, Any]:
    from src.agent.education.api import _overview_agg_sql

    exam = _str(exam_name)
    ensure_table(session, db_type)
    raw_bars = bar_rows if bar_rows is not None else _load_bar_rows(session)
    batch_id = _int_id(exam_batch_id) or exam_batch_id_from_bars(exam, raw_bars)
    if batch_id is None:
        batch_id = _lookup_exam_batch_id(session, exam)
    bars = filter_fraction_bars(normalize_fraction_bars(raw_bars), exam_name=exam, track="")
    ov_cols = list(_OV_COL_HINTS)
    agg_sql = _overview_agg_sql(ov_cols, bars, exam_name=exam, track="")
    agg_rows: list[dict[str, Any]] = []
    if agg_sql:
        ok, agg_rows, _ = _query_dicts(session, agg_sql)
        if not ok:
            probed = _probe_columns(session, "tb_score_overview")
            if probed:
                agg_sql = _overview_agg_sql(probed, bars, exam_name=exam, track="")
                if agg_sql:
                    ok, agg_rows, _ = _query_dicts(session, agg_sql)
                    if not ok:
                        agg_rows = []
    indicator_rows = agg_rows_to_indicator_rows(
        agg_rows, bars, exam_name=exam, exam_batch_id=batch_id
    )
    ok, msg, _ = session.execute_write(
        "DELETE FROM tb_score_indicator WHERE exam_name = %s",
        (exam,),
    )
    if not ok:
        raise RuntimeError(msg or "清理 tb_score_indicator 失败")
    write_cols = _indicator_write_cols(session)
    if indicator_rows and write_cols:
        param_rows = [
            tuple(row.get(c) for c in write_cols) for row in indicator_rows
        ]
        ok, msg, _ = session.execute_upsert_batch(
            "tb_score_indicator",
            write_cols,
            _INDICATOR_CONFLICT,
            param_rows,
        )
        if not ok:
            raise RuntimeError(msg or "写入 tb_score_indicator 失败")
    return {
        "exam_name": exam,
        "exam_batch_id": batch_id,
        "bar_count": len(bars),
        "indicator_rows": len(indicator_rows),
        "empty_scores": not indicator_rows,
    }
```

## src/agent/education/sql_lint.py :: lint_edu_sql_blocks

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/sql_lint.py:687)

```python
def lint_edu_sql_blocks(
    sql: str,
    bound_literals: Sequence[str] | None = None,
    question: str | None = None,
) -> list[str]:
    """致命项：不得执行。"""
    s = sql or ""
    blocks: list[str] = []
    if _AVG_REACH.search(s):
        blocks.append(
            "检测到 AVG(reach_rate)：区县/全市达线率须 "
            "SUM(reached_count)/SUM(candidates) 重算，禁止对 reach_rate 求平均。"
        )
    if _MONTH_DISTRICT.search(s):
        blocks.append(
            "检测到疑似把「N月」拼进区县的字面量（如 '月广陵区'）："
            "请改为真实区县名或 district LIKE '%广陵%'，并先 peek_edu_filter_values。"
        )
    missing: list[str] = []
    for m in list(_SUBJECT_STAT.finditer(s)) + list(_PERCENTILE_SUBJECT.finditer(s)):
        col = (m.group("col") or "").lower()
        if col and col not in missing and not _subject_stat_excludes_zero(s, col, m.end()):
            missing.append(col)
    if missing:
        cols = "、".join(missing)
        blocks.append(
            f"检测到对 {cols} 的分数统计未排除 0 分：未选考/缺考在宽表为 0，"
            "计入会把选考科均分拉低、标准差/均衡性失真。"
            "凡均分/标准差/方差/中位/最值/分数段，须 AGG(col) FILTER (WHERE col > 0)，"
            "并同时给出 COUNT(*) FILTER (WHERE col > 0) 作为该科参考人数。"
        )
    if _overview_rank_missing_enrolled(s):
        blocks.append(
            "检测到全市班级/学校排名未排除市报生：tb_score_overview 须 "
            "AND xsxz='在籍生'，否则往届/市报虚拟班会挤占名次。"
        )
    if _class_rank_partitioned_by_name(s):
        blocks.append(
            "检测到 RANK() OVER (PARTITION BY bj)：这是各校同名班互比，不是全市班级排名。"
            "必须 GROUP BY xx,bj 后 RANK() OVER (ORDER BY 均分 DESC)，禁止 PARTITION BY bj；"
            "目标校/班只允许在排名完成后再 WHERE 过滤。"
        )
    if _rank_pool_shrunk_by_target_filter(s):
        blocks.append(_RANK_POOL_SHRINK_MSG)
    if _subject_rank_keeps_null_avgs(s):
        blocks.append(_SUBJECT_RANK_NULL_POOL_MSG)
    if _citywide_subject_avg_union_then_rank(s):
        blocks.append(_SUBJECT_MUTUAL_RANK_MSG)
    if _rank_on_unpivoted_subjects_without_partition(s):
        blocks.append(_CROSS_SUBJECT_MIXED_POOL_MSG)
    if _RANK_FN.search(s) and _COUNT_STAR_OVER_ORDER.search(s):
        blocks.append(_RUNNING_COUNT_AS_POOL_MSG)
    if _count_distinct_class_name_as_city_n(s):
        blocks.append(
            "检测到 COUNT(DISTINCT bj)：班名（高三(1)班…）全市重复，这是班名种类不是全市班级数。"
            "全市班级数用 COUNT(*) OVER ()（对 xx,bj 分组结果），禁止 COUNT(DISTINCT bj)。"
        )
    raw_electives = _raw_elective_cols(s)
    if raw_electives:
        cols = "、".join(raw_electives)
        blocks.append(
            f"检测到对 {cols} 做分数统计：化学/生物/政治/地理必须用转换分 "
            "hxzh/swzh/zzzh/dlzh，禁止 hx/sw/zz/dl。"
        )
    if _school_column_aliased_as_class(s):
        blocks.append(
            "检测到把 xx（学校）别名为 class_name/班级：班级横向对比必须用 bj。"
            "SELECT bj AS class_name，GROUP BY xx, bj；禁止 SELECT xx AS class_name，禁止只 GROUP BY xx。"
        )
    if _class_alias_grouped_by_school_only(s):
        blocks.append(
            "检测到 SELECT 班级别名却只 GROUP BY xx：会把全校塌成一行学校均分。"
            "各班对比必须 SELECT bj AS class_name，GROUP BY xx, bj。"
        )
    if _dual_class_rank_missing_union(s, question):
        blocks.append(
            "班级全市六门排名须一条 SQL 用 UNION ALL 一次返回两个口径"
            "（按选考方向 + 不区分选考），禁止只查文理混排；"
            "禁止拆两次 execute_sql（查询结果只保留最后一次）。"
        )
    if _class_rank_outer_target_without_neighborhood(s, question):
        blocks.append(
            "班级全市排名查询结果须含对照班：第1名 + 目标班名次前后各3名（标记本班）。"
            "用目标校+班定位窗口（BETWEEN），禁止外层 WHERE 只留下目标班一行。"
        )
    if _nth_class_lookup_missing_asked_rank(s, question):
        blocks.append(
            "全市第N是哪个班须外层 WHERE 排名=N（并列则多行）；"
            "倒数第K须 RANK DESC（第1=最好）后 WHERE 排名=参赛班数-K+1。"
            "禁止 BETWEEN 对照窗口，禁止 ORDER BY 均分 ASC（会把正数第K当成倒数），"
            "禁止输出全市榜，禁止外层 WHERE 已知校+班。"
        )
    if _class_rank_outer_bj_without_school(s):
        blocks.append(
            "班级全市排名外层必须同时过滤学校（xx/学校）与班级（bj/班级），"
            "禁止只滤班级（同名班会串校）。"
        )
    if _class_rank_pool_unwashed(s, question):
        blocks.append(
            "班级全市排名池须洗掉小班与其他校：xxlb NOT LIKE '%其他%'（中专/职校），"
            "整班参考人数 HAVING COUNT(*) >= 10。"
        )
    if _class_rank_missing_school_type_filter(s, question):
        blocks.append(
            "问句已点名引领/支撑/发展校：班级排名池必须 xxlb LIKE '%该类%'，"
            "禁止用全市普通高中（只排除其他校）当对照池。"
        )
    if _subject_class_rank_keeps_empty_avg(s, question):
        blocks.append(
            "班级单科全市排名须把该科有效人数为 0 的班排除出池："
            "HAVING COUNT(*) FILTER (WHERE col > 0) >= 3，或 RANK() OVER (ORDER BY 均分 DESC NULLS LAST)；"
            "禁止缺考/无分班排到第1。"
        )
    unbound = _unbound_literals(s, bound_literals)
    if unbound:
        blocks.append(
            "WHERE 字面量不在本轮已绑定集合："
            + "、".join(unbound)
            + "。必须使用已确认的考试/学校/班级/区县。"
        )
    return blocks
```

## src/agent/education/subject_diagnosis.py :: knowledge_names_subquery_join

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/subject_diagnosis.py:177)

```python
def knowledge_names_subquery_join(db_type: str = "pg") -> str:
    """小题查询：按 question_id 聚合知识点名串，避免一题多知识点裂行。"""
    if db_type == "mysql":
        agg = (
            "GROUP_CONCAT(DISTINCT k.knowledge_name "
            "ORDER BY k.knowledge_name SEPARATOR '、')"
        )
    else:
        agg = "string_agg(DISTINCT k.knowledge_name, '、' ORDER BY k.knowledge_name)"
    return (
        "LEFT JOIN (\n"
        "  SELECT eqk.question_id,\n"
        f"         {agg} AS knowledge_name\n"
        "  FROM tb_exam_question_knowledge eqk\n"
        "  JOIN tb_knowledge k ON k.id = eqk.knowledge_id\n"
        "  GROUP BY eqk.question_id\n"
        ") kn ON kn.question_id = eq.id\n"
    )
```

## src/agent/education/subject_diagnosis.py :: knowledge_weighted_join

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/subject_diagnosis.py:197)

```python
def knowledge_weighted_join() -> str:
    """知识点掌握查询：关联表 + 题内 weight 归一化为 w_norm。"""
    return (
        "LEFT JOIN (\n"
        "  SELECT question_id, knowledge_id,\n"
        "         weight / NULLIF(SUM(weight) OVER (PARTITION BY question_id), 0) AS w_norm\n"
        "  FROM tb_exam_question_knowledge\n"
        ") eqk ON eqk.question_id = eq.id\n"
        "LEFT JOIN tb_knowledge k ON k.id = eqk.knowledge_id\n"
    )
```

## src/agent/education/subject_research.py :: school_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/subject_research.py:434)

```python
def school_select_sql() -> str:
    return "SELECT id, s_name, type FROM tb_school LIMIT 500"
```

## src/agent/education/subject_research.py :: score_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/subject_research.py:438)

```python
def score_select_sql(exam_name: str, subject: str = "") -> str:
    lit = _esc(exam_name)
    subj = f" AND sc.subject_name = '{_esc(subject)}'" if _str(subject) else ""
    return (
        "SELECT sc.school_id, sc.student_id, sc.score, sc.subject_name, "
        "ov.xsxz, "
        f"{EXAM_NAME_SQL} AS exam_name\n"
        "FROM tb_score sc\n"
        f"{EXAM_JOIN}\n"
        "LEFT JOIN tb_score_overview ov ON ov.anon_stu_id = sc.student_id "
        f"AND ov.exam_name = {EXAM_NAME_SQL}\n"
        f"WHERE {EXAM_NAME_SQL} = '{lit}'{subj}\n"
        "LIMIT 200000"
    )
```

## src/agent/education/subject_research.py :: score_school_avg_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/subject_research.py:454)

```python
def score_school_avg_select_sql(exam_name: str, subject: str = "") -> str:
    """按校×科均分。全市九科约几百行，避免把全市学生行拉进内存。"""
    lit = _esc(exam_name)
    subj = f" AND sc.subject_name = '{_esc(subject)}'" if _str(subject) else ""
    return (
        "SELECT sc.school_id, sc.subject_name,\n"
        "       AVG(sc.score) AS score,\n"
        "       COUNT(*) AS n,\n"
        "       '在籍生' AS xsxz\n"
        "FROM tb_score sc\n"
        f"{EXAM_JOIN}\n"
        "LEFT JOIN tb_score_overview ov ON ov.anon_stu_id = sc.student_id "
        f"AND ov.exam_name = {EXAM_NAME_SQL}\n"
        f"WHERE {EXAM_NAME_SQL} = '{lit}' AND ov.xsxz = '在籍生'{subj}\n"
        "GROUP BY sc.school_id, sc.subject_name\n"
        "LIMIT 20000"
    )
```

## src/agent/education/subject_research.py :: paper_school_avg_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/subject_research.py:519)

```python
def paper_school_avg_select_sql(exam_name: str, subject: str = "") -> str:
    """先按生汇总卷1/卷2，再按校求均。全市九科只扫一遍明细。"""
    p1 = _sql_paper1_pred()
    p2 = _sql_paper2_pred()
    inner = (
        "SELECT sc.school_id, sc.student_id, sc.subject_name,\n"
        f"       COALESCE(SUM(CASE WHEN {p1} THEN sd.score ELSE 0 END), 0) AS paper1,\n"
        f"       COALESCE(SUM(CASE WHEN {p2} THEN sd.score ELSE 0 END), 0) AS paper2\n"
        + _detail_join_sql(exam_name, subject)
        + "\nGROUP BY sc.school_id, sc.student_id, sc.subject_name"
    )
    return (
        "SELECT school_id, subject_name,\n"
        "       AVG(paper1) AS paper1,\n"
        "       AVG(paper2) AS paper2,\n"
        "       COUNT(*) AS n\n"
        f"FROM ({inner}) t\n"
        "GROUP BY school_id, subject_name\n"
        "LIMIT 20000"
    )
```

## src/agent/education/subject_research.py :: overview_plain_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/subject_research.py:572)

```python
def overview_plain_select_sql(
    exam_name: str,
    school_xx: list[str] | None = None,
    thresholds: list[float] | None = None,
) -> str:
    """第一期始终取 xm。有本校名时不拉全市花名册（尖子生/切线生在库内筛）。"""
    lit = _esc(exam_name)
    cols = (
        "SELECT exam_name, xm, xh, anon_stu_id, xx, dq, bj, xkkm, xsxz, "
        "zf6m, yw, sx, yy, wl, hx, sw, zz, ls, dl, "
        "hxzh, hxdj, swzh, swdj, zzzh, zzdj, dlzh, dldj "
        f"FROM tb_score_overview WHERE exam_name = '{lit}' "
        "AND COALESCE(xsxz, '') <> '市报生'"
    )
    names = [_esc(x) for x in (school_xx or []) if _str(x)]
    if not names:
        return cols + " LIMIT 50000"
    xx_sql = ", ".join(f"'{n}'" for n in names)
    phy = "(xkkm LIKE '物%')"
    his = "(xkkm LIKE '史%' OR xkkm LIKE '历%')"
    parts = [
        f"xx IN ({xx_sql})",
        (
            "anon_stu_id IN (SELECT anon_stu_id FROM ("
            "SELECT anon_stu_id, RANK() OVER (ORDER BY zf6m DESC NULLS LAST) AS rk "
            f"FROM tb_score_overview WHERE exam_name = '{lit}' "
            f"AND COALESCE(xsxz, '') <> '市报生' AND {phy}"
            ") t WHERE rk <= 100)"
        ),
        (
            "anon_stu_id IN (SELECT anon_stu_id FROM ("
            "SELECT anon_stu_id, RANK() OVER (ORDER BY zf6m DESC NULLS LAST) AS rk "
            f"FROM tb_score_overview WHERE exam_name = '{lit}' "
            f"AND COALESCE(xsxz, '') <> '市报生' AND {his}"
            ") t WHERE rk <= 30)"
        ),
    ]
    nums: list[float] = []
    for raw in thresholds or []:
        n = _num(raw)
        if n is not None:
            nums.append(n)
    if nums:
        in_list = ", ".join(str(n) for n in nums)
        parts.append(f"zf6m IN ({in_list})")
        thr_union = " UNION ALL ".join(f"SELECT {n} AS thr" for n in nums)
        for track_pred in (phy, his):
            parts.append(
                "anon_stu_id IN ("
                f"SELECT s.anon_stu_id FROM ({thr_union}) b JOIN LATERAL ("
                "SELECT ov.anon_stu_id FROM tb_score_overview ov "
                f"WHERE ov.exam_name = '{lit}' AND COALESCE(ov.xsxz, '') <> '市报生' "
                f"AND ov.zf6m >= b.thr AND {track_pred.replace('xkkm', 'ov.xkkm')} "
                "ORDER BY ov.zf6m ASC NULLS LAST LIMIT 1"
                ") s ON TRUE)"
            )
    return cols + " AND (" + " OR ".join(parts) + ") LIMIT 5000"
```

## src/agent/education/subject_research.py :: paper_sum_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/subject_research.py:503)

```python
def paper_sum_select_sql(exam_name: str, subject: str = "") -> str:
    """库内按生汇总卷1/卷2，避免拉全市小题再被 LIMIT 截断。"""
    p1 = _sql_paper1_pred()
    p2 = _sql_paper2_pred()
    return (
        "SELECT sc.school_id, sc.student_id, sc.subject_name,\n"
        f"       COALESCE(SUM(CASE WHEN {p1} THEN sd.score ELSE 0 END), 0)"
        " AS paper1,\n"
        f"       COALESCE(SUM(CASE WHEN {p2} THEN sd.score ELSE 0 END), 0)"
        " AS paper2\n"
        + _detail_join_sql(exam_name, subject)
        + "\nGROUP BY sc.school_id, sc.student_id, sc.subject_name\n"
        "LIMIT 200000"
    )
```

## src/agent/education/subject_research.py :: item_school_select_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/subject_research.py:549)

```python
def item_school_select_sql(exam_name: str, subject: str = "") -> str:
    """库内按校×题号聚合，供拖后腿小题排序。"""
    qno = _item_qno_sql()
    return (
        "SELECT sc.school_id, sc.subject_name,\n"
        f"       {qno} AS question_no,\n"
        "       MAX(eq.question_type) AS question_type,\n"
        "       AVG(sd.score) AS avg_score,\n"
        "       MAX(sd.score) AS max_score,\n"
        "       MIN(sd.score) AS min_score,\n"
        "       COUNT(*) AS n\n"
        + _detail_join_sql(exam_name, subject)
        + "\nGROUP BY sc.school_id, sc.subject_name,\n"
        f"         {qno}\n"
        "LIMIT 50000"
    )
```

## src/agent/education/tools.py :: _overview_class_score_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:1910)

```python
def _overview_class_score_sql(
    *,
    school_name: str,
    subject_col: str,
    exam_name: str = "",
    full_score: float = 150.0,
) -> str:
    """学生级 overview：每行一个学生，班级列是 bj，供各班横向对比聚合。"""
    col = (subject_col or "").strip().lower()
    if col not in _OVERVIEW_SCORE_COLS:
        raise ValueError(f"illegal overview subject column: {subject_col}")
    school = _esc((school_name or "").strip())
    exam = _esc((exam_name or "").strip())
    fs = float(full_score) if full_score and full_score > 0 else 150.0
    exam_pred = f" AND exam_name LIKE '%{exam}%'" if exam else ""
    return (
        f"SELECT bj AS class, bj AS class_name, xx AS school_name, exam_name,\n"
        f"       anon_stu_id AS student_id, dq AS district, xkkm,\n"
        f"       {col} AS score, {fs:g} AS exam_score\n"
        f"FROM tb_score_overview\n"
        f"WHERE xx LIKE '%{school}%'\n"
        f"  AND xsxz = '在籍生'\n"
        f"  AND {col} IS NOT NULL AND {col} > 0\n"
        f"  AND bj IS NOT NULL AND CAST(bj AS TEXT) <> ''\n"
        f"{exam_pred}"
        f"ORDER BY exam_name DESC, bj\n"
        f"LIMIT 50000"
    )
```

## src/agent/education/tools.py :: _fetch_overview_class_tracks

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:2014)

```python
def _fetch_overview_class_tracks(
    *,
    datasource_id: int,
    workspace_oid: int | None,
    user_id: int | None,
    school_name: str,
    exam_name: str = "",
) -> dict[str, str]:
    """tb_score 无 xkkm 时，用 overview 给班级贴选科方向。"""
    from src.agent.education.class_track import class_track_map

    school = _esc((school_name or "").strip())
    if not school:
        return {}
    exam = _esc((exam_name or "").strip())
    exam_pred = f" AND exam_name LIKE '%{exam}%'" if exam else ""
    sql = (
        "SELECT bj AS class_name, xkkm\n"
        "FROM tb_score_overview\n"
        f"WHERE xx LIKE '%{school}%'\n"
        "  AND xsxz = '在籍生'\n"
        "  AND bj IS NOT NULL AND CAST(bj AS TEXT) <> ''\n"
        "  AND (xkkm LIKE '物%' OR xkkm LIKE '史%' OR xkkm LIKE '历%')\n"
        f"{exam_pred}\n"
        "LIMIT 50000"
    )
    success, _msg, result, _sql_run = _run_edu_sql(
        sql,
        datasource_id=datasource_id,
        workspace_oid=workspace_oid,
        user_id=user_id,
    )
    if not success or not isinstance(result, dict):
        return {}
    return class_track_map(_rows_to_dicts(result))
```

## src/agent/education/tools.py :: _lookup_display_name_for_school_id

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:6343)

```python
def _lookup_display_name_for_school_id(
    school_id: str,
    *,
    datasource_id: int,
    workspace_oid: int | None,
    user_id: int | None,
) -> tuple[str, list[dict[str, Any]]]:
    """把 ``tb_school.id`` 还原成 ``s_name`` 明文，仅供薄弱学科报告标题。"""
    raw = (school_id or "").strip()
    logs: list[dict[str, Any]] = []
    if not raw or not _looks_like_school_id(raw):
        return "", logs
    sql = (
        "SELECT s_name, name FROM tb_school "
        f"WHERE id = '{_esc(raw)}' LIMIT 1"
    )
    ok, msg, result, sql_run = _run_edu_sql(
        sql,
        datasource_id=int(datasource_id),
        workspace_oid=workspace_oid,
        user_id=user_id,
    )
    rows = _rows_to_dicts(result) if ok else []
    logs.append(
        {
            "label": "school_display_by_id",
            "success": ok,
            "row_count": len(rows),
            "message": msg if not ok else "",
            "sql_preview": (sql_run or sql)[:400],
        }
    )
    if not rows:
        return "", logs
    row = rows[0]
    return _plain_school_label(str(row.get("s_name") or ""), str(row.get("name") or "")), logs
```

## src/agent/education/tools.py :: fetch_subject_diagnosis_data_tool

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:729)

```python
def fetch_subject_diagnosis_data_tool(
    datasource_id: int,
    school_name: str = "",
    subject_name: str = "",
    exam_name: str = "",
    class_name: str = "",
    workspace_oid: int | None = None,
    user_id: int | None = None,
    report_data: dict[str, Any] | None = None,
    sub_task: str = "",
) -> ToolResult:
    """直接从数据库查询科目诊断所需的小题明细与知识点汇总（确定性 SQL，无需 LLM 写 JOIN）。

    **适用时机**：科目诊断报告中需要「每一小题 + 知识点」和「知识点得分率」时，
    **优先调用本工具**，而不是自己写 SQL——本工具内部已固定经
    ``tb_exam_question_knowledge`` JOIN ``tb_knowledge``（掌握度按 weight 归一化拆分），
    确保知识点名称来自数据库而非臆造。

    **Team 分工**：仅 **fetch 子任务** 调用本工具；**组装子任务**（含
    ``build_diagnostic_report_data_tool``）**禁止**再调本工具——fetch 结果已由
    运行时 ``report_data`` 自动注入组装工具。

    返回的 ``data`` 含：
    - ``item_rows``：每题一行，含 question_no / knowledge_name / full_score / avg_score / score_rate
    - ``knowledge_rows``：每个知识点一行，含 knowledge_name / question_count / score_rate
    - ``score_rows``：每个学生一行的原始成绩（含 exam_score），可直接传给 compute_score_stats_tool

    Args:
        datasource_id: 数据源 ID（必填）。
        school_name: 学校名（如「南京市第一中学」），用于 WHERE 过滤。
        subject_name: 科目名（如「数学」）。
        exam_name: 考试名关键字（如「期末质量检测」），可选。
        class_name: 班级名，可选。
    """
    from src.agent.resource.tool.business import _load_datasource
    from src.agent.education.query_parse import (
        find_upstream_fetch_data,
        sub_task_primary_tool,
    )

    task_text = (sub_task or "").strip()
    primary_tool = sub_task_primary_tool(task_text)
    if primary_tool == "build_diagnostic_report_data_tool" or (
        not primary_tool and find_upstream_fetch_data(report_data)
    ):
        return ToolResult(
            content=(
                "本子任务应组装诊断报告，**禁止重复 fetch**。"
                "请直接调 build_diagnostic_report_data_tool("
                "scope_label=全市, exam_name=..., subject_name=..., render=true)；"
                "score_rows 与 fetch_data 将由工具自动从 report_data 读取。"
            ),
            data={"error": "fetch_not_allowed_in_build_subtask"},
        )

    try:
        db_type, _config, ds_name = _load_datasource(datasource_id, workspace_oid)
    except Exception as e:
        return ToolResult(
            content=f"fetch_subject_diagnosis_data_tool 失败：{e}",
            data={"error": str(e)},
        )

    bundle = _fetch_subject_diagnosis_rows(
        datasource_id=datasource_id,
        workspace_oid=workspace_oid,
        user_id=user_id,
        school_name=school_name,
        subject_name=subject_name,
        exam_name=exam_name,
        class_name=class_name,
        db_type=db_type,
    )
    item_rows = bundle["item_rows"]
    knowledge_rows = bundle["knowledge_rows"]
    item_class_rows = bundle.get("item_class_rows") or []
    knowledge_class_rows = bundle.get("knowledge_class_rows") or []
    score_values = bundle["score_values"]
    score_rows = bundle.get("score_rows") or []
    warnings = bundle.get("warnings") or []
    errors = bundle.get("errors") or []
    sql_logs = bundle.get("sql_logs") or []
    score_result = {
        "columns": ["score", "exam_score"],
        "rows": [[v, bundle.get("full_score")] for v in score_values],
    }

    if not item_rows and not knowledge_rows and not score_values:
        err_detail = "\n".join(errors[:5]) if errors else "无额外错误信息"
        return ToolResult(
            content=(
                f"fetch_subject_diagnosis_data_tool 未查到数据（ds={ds_name}，"
                f"school={school_name}，subject={subject_name}，exam={exam_name}，class={class_name}）。\n"
                f"SQL 执行记录：\n{_format_diagnosis_sql_logs(sql_logs)}\n"
                f"错误：{err_detail}"
            ),
            data={"error": "no data", "item_rows": [], "knowledge_rows": [], "sql_logs": sql_logs},
        )

    content = (
        f"【小题明细查询】fetch_subject_diagnosis_data_tool（ds={ds_name}，db={db_type}）\n"
        f"- 小题明细（tb_score_detail）：{len(item_rows)} 题\n"
        f"- 知识点汇总：{len(knowledge_rows)} 个\n"
        f"- 学生成绩（tb_score）：{len(score_values)} 条\n"
    )
    if item_class_rows or knowledge_class_rows:
        content += (
            f"- 班级横向对比小题：{len(item_class_rows)} 行\n"
            f"- 班级横向对比知识点：{len(knowledge_class_rows)} 行\n"
        )
    if not item_rows and score_values:
        content += (
            "无小题明细不影响班级横向对比：已有带班级(bj)字段的成绩行。"
            "**禁止**手写 execute_sql；禁止 SELECT xx AS class_name；禁止只 GROUP BY xx。\n"
        )
    content += (
        f"SQL 执行记录：\n{_format_diagnosis_sql_logs(sql_logs)}\n"
        "下一步：**本步请 terminate**（禁止同子任务渲染报告，禁止手写 overview 聚合 SQL）。"
        "组装留给后续子任务："
        "科目诊断/班级横向对比调 `build_subject_diagnosis_sections_tool(render=true)`；"
        "全市诊断调 `build_diagnostic_report_data_tool(render=true)`——"
        "工具会自动读取本步 fetch 结果。"
    )
    if errors:
        content += "\n部分 SQL 失败：\n" + "\n".join(errors[:5])
    if warnings:
        content += "\n" + "\n".join(warnings)
    return ToolResult(
        content=content,
        data={
            "item_rows": item_rows,
            "knowledge_rows": knowledge_rows,
            "item_class_rows": item_class_rows,
            "knowledge_class_rows": knowledge_class_rows,
            "score_rows": score_rows,
            "score_result": score_result,
            "warnings": warnings,
            "errors": errors,
            "sql_logs": sql_logs,
        },
    )
```

## src/agent/education/tools.py :: _lookup_school_id_for_display_name

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:6381)

```python
def _lookup_school_id_for_display_name(
    school_name: str,
    *,
    datasource_id: int,
    workspace_oid: int | None,
    user_id: int | None,
) -> tuple[str, list[dict[str, Any]]]:
    """把口语校名解析成 ``tb_school.id``（脱敏码），供 ``sc.school_id`` 过滤。

    仅薄弱学科工具使用，不改共享 ``_school_scope_predicate``。
    """
    from src.agent.education.class_weak_subject import school_query_candidates

    raw = (school_name or "").strip()
    logs: list[dict[str, Any]] = []
    if not raw:
        return "", logs
    if _looks_like_school_id(raw):
        return raw, logs

    def _ids_from(sql: str, phase: str) -> list[str]:
        ok, msg, result, sql_run = _run_edu_sql(
            sql,
            datasource_id=int(datasource_id),
            workspace_oid=workspace_oid,
            user_id=user_id,
        )
        rows = _rows_to_dicts(result) if ok else []
        logs.append(
            {
                "label": phase,
                "success": ok,
                "row_count": len(rows),
                "message": msg if not ok else "",
                "sql_preview": (sql_run or sql)[:400],
            }
        )
        out: list[str] = []
        seen: set[str] = set()
        for r in rows:
            sid = str(r.get("id") or "").strip()
            if sid and sid not in seen:
                seen.add(sid)
                out.append(sid)
        return out

    for cand in school_query_candidates(raw):
        lit = _esc(cand)
        sql = (
            "SELECT id FROM tb_school "
            f"WHERE s_name = '{lit}' OR name = '{lit}' OR id = '{lit}' "
            "LIMIT 5"
        )
        ids = _ids_from(sql, f"school_id_exact/{cand}")
        if len(ids) == 1:
            return ids[0], logs

    for cand in school_query_candidates(raw):
        lit = _esc(cand)
        sql = (
            "SELECT id FROM tb_school "
            f"WHERE s_name LIKE '%{lit}' OR name LIKE '%{lit}' "
            "LIMIT 5"
        )
        ids = _ids_from(sql, f"school_id_like/{cand}")
        if len(ids) == 1:
            return ids[0], logs
    return raw, logs
```

## src/agent/education/tools.py :: compute_score_stats_tool

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:589)

```python
def compute_score_stats_tool(
    scores: list[float] | None = None,
    rows: list[list[Any]] | None = None,
    columns: list[str] | None = None,
    score_field: str = "",
    full_score_field: str = "exam_score",
    pass_threshold: float | None = None,
    excellent_threshold: float | None = None,
    full_score: float | None = None,
    exec_result: dict[str, Any] | None = None,
    report_data: dict[str, Any] | None = None,
    tool_runtime_ctx: dict[str, Any] | None = None,
) -> ToolResult:
    """对一组分数计算报告级统计（均分/中位数/标准差/及格率/优秀率/分数段）。

    **三种入参**（任选其一）：

    - ``scores``：直接传数值列表，例如 ``[85, 92, 78, 60, 55]``；
    - ``exec_result``：传 ``execute_sql`` 返回的 ``data`` 整包（含 columns/rows）；
    - ``rows`` + ``columns`` + ``score_field``：分列传入；``score_field`` 可省略，
      工具会按列名自动猜测（优先 ``score`` / ``avg_score``）。

    **推荐写法**（接 execute_sql 之后）::

        compute_score_stats_tool(
            exec_result={"columns": ["score", "exam_score"], "rows": [[84, 150], ...]},
            score_field="score",
            full_score_field="exam_score",
        )

    **满分与阈值**：优先使用 ``full_score`` 参数；否则从 ``rows`` 的
    ``full_score_field``（默认 ``exam_score``，对应 tb_exam/tb_score 卷面满分）
    读取。有 ``full_score`` 时及格/优秀线 = 满分 × pass_ratio(0.6) / excellent_ratio(0.85)，
    禁止写死 60/85/150。无满分列时回退 ``default_full_score``(100) 并在 observation 中 warning。

    Returns:
        ``data`` 含 ``count`` / ``avg`` / ``median`` / ``stdev`` / ``min`` /
        ``max`` / ``pass_rate`` / ``excellent_rate`` / ``fail_rate`` /
        ``full_score`` / ``segments``（每段 ``{label, count, ratio}``）。
        空数据返回 ``count=0`` 占位结构，不抛。
    """
    cfg = _get_effective_config()
    # 分数段可取 schema；及格/优秀比例以异常规则库表为准，不覆盖。
    bundle = load_schema_from_config()
    if bundle is not None and bundle.meta.score_segment_ratios:
        cfg.score_segment_ratios = list(bundle.meta.score_segment_ratios)
    if pass_threshold is not None:
        cfg.pass_threshold = float(pass_threshold)
    if excellent_threshold is not None:
        cfg.excellent_threshold = float(excellent_threshold)

    from src.agent.education.query_parse import resolve_stats_input

    ctx = tool_runtime_ctx if isinstance(tool_runtime_ctx, dict) else {}
    scores, exec_result = resolve_stats_input(
        scores=scores,
        exec_result=exec_result,
        last_exec_result=ctx.get("last_exec_result"),
        report_data=report_data or ctx.get("report_data"),
    )

    rows, columns = _coerce_exec_result(exec_result, rows, columns)
    if not score_field and columns:
        score_field = _guess_field(columns, _SCORE_FIELD_HINTS)
    if full_score_field == "exam_score" and columns:
        guessed_full = _guess_field(columns, _FULL_SCORE_FIELD_HINTS)
        if guessed_full:
            full_score_field = guessed_full

    warnings: list[str] = []
    values: list[float] = []
    if scores is not None:
        values = [float(s) for s in scores if s is not None]
    elif rows is not None and columns is not None and score_field:
        try:
            idx = columns.index(score_field)
        except ValueError:
            return ToolResult(
                content=f"compute_score_stats_tool 失败：score_field `{score_field}` 不在 columns {columns} 中。",
                data={"error": "score_field not found", "columns": columns},
            )
        for row in rows:
            try:
                v = row[idx] if isinstance(row, (list, tuple)) else row.get(score_field)
            except (IndexError, TypeError, AttributeError):
                continue
            if v is None or v == "":
                continue
            try:
                values.append(float(v))
            except (TypeError, ValueError):
                continue
        if full_score is None:
            resolved, warn = _extract_full_score_from_rows(rows, columns, full_score_field)
            if resolved is not None:
                full_score = resolved
            if warn:
                warnings.append(warn)
    else:
        hint = (
            "compute_score_stats_tool 失败：需提供 scores、exec_result，"
            "或 (rows + columns [+ score_field])。"
        )
        if rows is not None and not columns:
            hint += " 提示：可传 exec_result=execute_sql 的 data，或 rows 为 dict 列表时省略 columns。"
        elif rows is not None and columns and not score_field:
            hint += f" 未能从 columns {columns} 猜测 score_field，请显式传入 score_field。"
        return ToolResult(
            content=hint,
            data={"error": "missing input", "columns": columns or []},
        )

    if full_score is None and values:
        warnings.append(
            f"未提供满分（请 SQL SELECT 带出 `{full_score_field}`），"
            f"使用 default_full_score={cfg.default_full_score} 计算 KPI"
        )

    stats = _compute_stats(values, cfg, full_score)
    if warnings:
        stats["warnings"] = warnings
    pass_line = stats.get("pass_line")
    excellent_line = stats.get("excellent_line")
    pr = stats.get("pass_ratio")
    er = stats.get("excellent_ratio")
    content = (
        f"成绩统计完成：共 {stats['count']} 人，均分 {stats['avg']}，"
        f"满分 {stats['full_score']}，"
        f"及格线 {pass_line}（按异常规则 {stats['full_score']}×{round(float(pr or 0) * 100, 2)}%），"
        f"优秀线 {excellent_line}（按异常规则 {stats['full_score']}×{round(float(er or 0) * 100, 2)}%），"
        f"及格率 {stats['pass_rate']}%，优秀率 {stats['excellent_rate']}%，"
        f"标准差 {stats['stdev']}。"
        "撰写结论时必须使用上述及格线/优秀线，禁止改用惯例 60%/85%。"
    )
    if warnings:
        content += "\n" + "\n".join(warnings)
    return ToolResult(content=content, data=stats)
```

## src/agent/education/tools.py :: _diagnosis_sql_bundle

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:1705)

```python
def _diagnosis_sql_bundle(
    where_clause_detail: str,
    where_clause_score: str,
    db_type: str = "pg",
    *,
    student_id: str = "",
) -> tuple[str, str, str, str]:
    """返回 (item_sql, knowledge_sql, score_sql, exam_id_sql)。"""
    full_score_expr = "COALESCE(eq.question_score, sd.question_score)"
    kn_join = knowledge_names_subquery_join(db_type)
    w_join = knowledge_weighted_join()
    w_score = f"sd.score * COALESCE(eqk.w_norm, 1)"
    w_full = f"{full_score_expr} * COALESCE(eqk.w_norm, 1)"
    if student_id:
        item_rate = _score_rate_sql("sd.score", full_score_expr, db_type)
        item_sql = (
            "SELECT sd.question_no,\n"
            "       COALESCE(kn.knowledge_name, '未关联知识点') AS knowledge_name,\n"
            "       eq.question_type AS question_type,\n"
            f"       {full_score_expr} AS full_score,\n"
            "       sd.score AS avg_score,\n"
            f"       {item_rate} AS score_rate\n"
            "FROM tb_score_detail sd\n"
            "LEFT JOIN tb_exam_question eq ON sd.question_id = eq.id\n"
            "    AND (eq.exam_id IS NULL OR eq.exam_id = sd.exam_id)\n"
            f"{kn_join}"
            "JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id\n"
            "JOIN tb_school sch ON sc.school_id = sch.id\n"
            "JOIN tb_exam e ON sc.exam_id = e.id\nLEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id"
            + where_clause_detail
            + "\nORDER BY sd.question_no\nLIMIT 1000"
        )
    else:
        item_rate = _score_rate_sql("AVG(sd.score)", full_score_expr, db_type)
        item_sql = (
            "SELECT sd.question_no,\n"
            "       COALESCE(kn.knowledge_name, '未关联知识点') AS knowledge_name,\n"
            "       eq.question_type AS question_type,\n"
            f"       {full_score_expr} AS full_score,\n"
            "       ROUND(AVG(sd.score), 2) AS avg_score,\n"
            f"       {item_rate} AS score_rate\n"
            "FROM tb_score_detail sd\n"
            "LEFT JOIN tb_exam_question eq ON sd.question_id = eq.id\n"
            "    AND (eq.exam_id IS NULL OR eq.exam_id = sd.exam_id)\n"
            f"{kn_join}"
            "JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id\n"
            "JOIN tb_school sch ON sc.school_id = sch.id\n"
            "JOIN tb_exam e ON sc.exam_id = e.id\nLEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id"
            + where_clause_detail
            + f"\nGROUP BY sd.question_no, COALESCE(kn.knowledge_name, '未关联知识点'), "
            f"eq.question_type, {full_score_expr}\n"
            "ORDER BY sd.question_no\nLIMIT 1000"
        )
    know_rate = _score_rate_sql(f"SUM({w_score})", f"SUM({w_full})", db_type)
    knowledge_sql = (
        "SELECT COALESCE(k.knowledge_name, '未关联知识点') AS knowledge_name,\n"
        "       k.ability_level AS ability_level,\n"
        "       COUNT(DISTINCT sd.question_no) AS question_count,\n"
        f"       {know_rate} AS score_rate\n"
        "FROM tb_score_detail sd\n"
        "LEFT JOIN tb_exam_question eq ON sd.question_id = eq.id\n"
        "    AND (eq.exam_id IS NULL OR eq.exam_id = sd.exam_id)\n"
        f"{w_join}"
        "JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id\n"
        "JOIN tb_school sch ON sc.school_id = sch.id\n"
        "JOIN tb_exam e ON sc.exam_id = e.id\nLEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id"
        + where_clause_detail
        + "\nGROUP BY COALESCE(k.knowledge_name, '未关联知识点'), k.ability_level\n"
        "ORDER BY score_rate ASC\nLIMIT 1000"
    )
    score_sql = (
        "SELECT sc.score AS score, sc.exam_score AS exam_score, sc.exam_id AS exam_id,\n"
        "       " + EXAM_NAME_SQL + " AS exam_name, e.exam_time AS exam_time,\n"
        "       sc.class AS class, sc.class AS class_name, sc.student_id AS student_id,\n"
        "       sc.subject_name AS subject, sch.name AS school_name,\n"
        "       sch.district AS district\n"
        "FROM tb_score sc\n"
        "JOIN tb_school sch ON sc.school_id = sch.id\n"
        "JOIN tb_exam e ON sc.exam_id = e.id\nLEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id"
        + where_clause_score
        # 勿按 score DESC：LIMIT 截断时会偏向高分，导致参考人数偏少、及格/优秀率虚高。
        + "\nORDER BY e.exam_time DESC\n"
        "LIMIT 50000"
    )
    exam_id_sql = (
        "SELECT DISTINCT sc.exam_id AS exam_id\n"
        "FROM tb_score sc\n"
        "JOIN tb_school sch ON sc.school_id = sch.id\n"
        "JOIN tb_exam e ON sc.exam_id = e.id\nLEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id"
        + where_clause_score
        + "\nLIMIT 50"
    )
    return item_sql, knowledge_sql, score_sql, exam_id_sql
```

## src/agent/education/tools.py :: _diagnosis_class_compare_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:1800)

```python
def _diagnosis_class_compare_sql(
    where_clause_detail: str,
    db_type: str = "pg",
) -> tuple[str, str]:
    """各班小题均分 / 知识点得分率 SQL（用于班级横向对比）。"""
    full_score_expr = "COALESCE(eq.question_score, sd.question_score)"
    kn_join = knowledge_names_subquery_join(db_type)
    w_join = knowledge_weighted_join()
    w_score = f"sd.score * COALESCE(eqk.w_norm, 1)"
    w_full = f"{full_score_expr} * COALESCE(eqk.w_norm, 1)"
    item_rate = _score_rate_sql("AVG(sd.score)", full_score_expr, db_type)
    item_sql = (
        "SELECT sc.class AS class_name,\n"
        "       sd.question_no,\n"
        "       COALESCE(kn.knowledge_name, '未关联知识点') AS knowledge_name,\n"
        "       eq.question_type AS question_type,\n"
        f"       {full_score_expr} AS full_score,\n"
        "       ROUND(AVG(sd.score), 2) AS avg_score,\n"
        f"       {item_rate} AS score_rate\n"
        "FROM tb_score_detail sd\n"
        "LEFT JOIN tb_exam_question eq ON sd.question_id = eq.id\n"
        "    AND (eq.exam_id IS NULL OR eq.exam_id = sd.exam_id)\n"
        f"{kn_join}"
        "JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id\n"
        "JOIN tb_school sch ON sc.school_id = sch.id\n"
        "JOIN tb_exam e ON sc.exam_id = e.id\nLEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id"
        + where_clause_detail
        + f"\nGROUP BY sc.class, sd.question_no, COALESCE(kn.knowledge_name, '未关联知识点'), "
        f"eq.question_type, {full_score_expr}\n"
        "ORDER BY sd.question_no, sc.class\nLIMIT 10000"
    )
    know_rate = _score_rate_sql(f"SUM({w_score})", f"SUM({w_full})", db_type)
    knowledge_sql = (
        "SELECT sc.class AS class_name,\n"
        "       COALESCE(k.knowledge_name, '未关联知识点') AS knowledge_name,\n"
        "       COUNT(DISTINCT sd.question_no) AS question_count,\n"
        f"       {know_rate} AS score_rate\n"
        "FROM tb_score_detail sd\n"
        "LEFT JOIN tb_exam_question eq ON sd.question_id = eq.id\n"
        "    AND (eq.exam_id IS NULL OR eq.exam_id = sd.exam_id)\n"
        f"{w_join}"
        "JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id\n"
        "JOIN tb_school sch ON sc.school_id = sch.id\n"
        "JOIN tb_exam e ON sc.exam_id = e.id\nLEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id"
        + where_clause_detail
        + "\nGROUP BY sc.class, COALESCE(k.knowledge_name, '未关联知识点')\n"
        "ORDER BY knowledge_name, sc.class\nLIMIT 10000"
    )
    return item_sql, knowledge_sql
```

## src/agent/education/tools.py :: _resolve_class_name_for_student

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:4585)

```python
def _resolve_class_name_for_student(
    *,
    datasource_id: int,
    student_name: str,
    school_name: str = "",
    workspace_oid: int | None = None,
) -> str:
    """用学号/姓名反查班级，供学生报告在缺 class_name 时自查全班。"""
    from src.agent.resource.tool.business import _load_datasource
    from src.datasource.service.sql_auto_fix import run_sql_with_auto_fix

    sid = (student_name or "").strip()
    if not sid:
        return ""
    db_type, config, _ = _load_datasource(datasource_id, workspace_oid)
    parts = [f"(sc.student_id = '{_esc(sid)}' OR sc.student_id LIKE '%{_esc(sid)}%')"]
    school_pred = _school_scope_predicate(_keep_school_filter_arg(school_name))
    if school_pred:
        parts.append(school_pred)
    sql = (
        "SELECT sc.class AS class_name\n"
        "FROM tb_score sc\n"
        "JOIN tb_school sch ON sc.school_id = sch.id\n"
        "WHERE " + " AND ".join(parts) + "\n"
        "LIMIT 1"
    )
    outcome = run_sql_with_auto_fix(sql, db_type=db_type, config=config)
    if not outcome.success or not isinstance(outcome.result, dict):
        return ""
    rows = outcome.result.get("rows") or []
    if not rows:
        return ""
    cell = rows[0][0] if not isinstance(rows[0], dict) else rows[0].get("class_name")
    return str(cell or "").strip()
```

## src/agent/education/tools.py :: _fetch_subject_diagnosis_rows

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:2051)

```python
def _fetch_subject_diagnosis_rows(
    *,
    datasource_id: int,
    workspace_oid: int | None,
    user_id: int | None,
    school_name: str = "",
    subject_name: str = "",
    exam_name: str = "",
    class_name: str = "",
    student_id: str = "",
    exam_ids: list[str] | None = None,
    db_type: str = "pg",
) -> dict[str, Any]:
    """查小题/知识点/成绩，带考试名放宽与 exam_id 回退。

    全校无班级（横向对比）时额外返回 ``item_class_rows`` / ``knowledge_class_rows``。
    """
    base_kw = {
        "school_name": school_name,
        "class_name": class_name,
        "subject_name": subject_name,
        "exam_name": exam_name,
        "student_id": student_id,
    }
    pinned_exam_ids = [str(x).strip() for x in (exam_ids or []) if str(x).strip()]
    if pinned_exam_ids:
        base_kw["exam_ids"] = pinned_exam_ids
    item_rows: list[dict[str, Any]] = []
    knowledge_rows: list[dict[str, Any]] = []
    score_values: list[float] = []
    score_rows: list[dict[str, Any]] = []
    full_score: float | None = None
    warnings: list[str] = []
    errors: list[str] = []
    sql_logs: list[dict[str, Any]] = []
    last_detail_wc = ""
    last_score_wc = ""
    want_class_compare = bool(school_name and not class_name and not student_id)

    def run_bundle(
        where_clause_detail: str,
        where_clause_score: str,
        phase: str,
    ) -> tuple[list[dict], list[dict], list[float], float | None, list[str], list[dict[str, Any]]]:
        nonlocal last_detail_wc, last_score_wc
        last_detail_wc = where_clause_detail
        last_score_wc = where_clause_score
        item_sql, knowledge_sql, score_sql, exam_id_sql = _diagnosis_sql_bundle(
            where_clause_detail,
            where_clause_score,
            db_type,
            student_id=student_id,
        )
        ir: list[dict[str, Any]] = []
        kr: list[dict[str, Any]] = []
        sv: list[float] = []
        fs: float | None = None
        eids: list[str] = []
        srows: list[dict[str, Any]] = []
        for label, sql in (
            ("item_detail", item_sql),
            ("knowledge", knowledge_sql),
            ("score", score_sql),
        ):
            success, msg, result, sql_run = _run_edu_sql(
                sql,
                datasource_id=datasource_id,
                workspace_oid=workspace_oid,
                user_id=user_id,
            )
            row_count = len(result.get("rows") or []) if isinstance(result, dict) else 0
            sql_logs.append(
                {
                    "phase": phase,
                    "label": label,
                    "success": success,
                    "row_count": row_count,
                    "message": msg if not success else "",
                    "sql_preview": (sql_run or sql)[:600],
                }
            )
            if not success:
                errors.append(f"[{phase}/{label}] {msg}")
                continue
            if not isinstance(result, dict):
                continue
            if label == "item_detail":
                ir = _rows_to_dicts(result)
            elif label == "knowledge":
                kr = _rows_to_dicts(result)
            else:
                sv, fs, eids, srows = _parse_score_result(result)
        if not eids:
            success, msg, result, sql_run = _run_edu_sql(
                exam_id_sql,
                datasource_id=datasource_id,
                workspace_oid=workspace_oid,
                user_id=user_id,
            )
            sql_logs.append(
                {
                    "phase": phase,
                    "label": "exam_ids",
                    "success": success,
                    "row_count": len(result.get("rows") or []) if isinstance(result, dict) else 0,
                    "message": msg if not success else "",
                    "sql_preview": (sql_run or exam_id_sql)[:600],
                }
            )
            if not success:
                errors.append(f"[{phase}/exam_ids] {msg}")
            elif isinstance(result, dict):
                for row in result.get("rows") or []:
                    if row and str(row[0]).strip():
                        eids.append(str(row[0]).strip())
        return ir, kr, sv, fs, eids, srows

    detail_wc, score_wc = _diagnosis_where_clause_pair(**base_kw)
    item_rows, knowledge_rows, score_values, full_score, exam_ids, score_rows = run_bundle(
        detail_wc, score_wc, "primary"
    )

    # 学号查询 + 中文校名简称：sch.name 精确匹配失败时，去掉学校过滤重试
    # （school_id 形态已在 WHERE 中按 sc.school_id 过滤，无需此放宽）
    if (
        student_id
        and not item_rows
        and not score_values
        and _is_unsafe_school_name_filter(school_name)
        and not _looks_like_school_id(school_name)
    ):
        relaxed_kw = {**base_kw, "school_name": ""}
        detail_wc_s, score_wc_s = _diagnosis_where_clause_pair(**relaxed_kw)
        item_rows, knowledge_rows, score_values, full_score, exam_ids, score_rows = run_bundle(
            detail_wc_s, score_wc_s, "fallback_student_no_school"
        )
        if item_rows or score_values:
            warnings.append(
                f"学校名 `{school_name}` 与库中 sch.name 不完全一致，已按学号 {student_id} 重试（"
                f"命中小题 {len(item_rows)}、成绩 {len(score_values)} 条）"
            )

    if not item_rows and score_values and exam_ids:
        detail_wc2, score_wc2 = _diagnosis_where_clause_pair(
            **base_kw, exam_ids=exam_ids, skip_exam_name=True
        )
        item_rows, knowledge_rows, _sv2, _fs2, _, score_rows = run_bundle(
            detail_wc2, score_wc2, "fallback_exam_id"
        )
        if item_rows:
            warnings.append("小题明细已按成绩记录的 exam_id 回退查询（考试名与库中不完全一致）")

    if not item_rows and exam_name:
        detail_wc3, score_wc3 = _diagnosis_where_clause_pair(**base_kw, skip_exam_name=True)
        item_rows, knowledge_rows, score_values, full_score, exam_ids, score_rows = run_bundle(
            detail_wc3, score_wc3, "fallback_no_exam_name"
        )
        if not item_rows and score_values and exam_ids:
            detail_wc4, score_wc4 = _diagnosis_where_clause_pair(
                **base_kw, exam_ids=exam_ids, skip_exam_name=True
            )
            item_rows, knowledge_rows, _, _, _, score_rows = run_bundle(
                detail_wc4, score_wc4, "fallback_exam_id_only"
            )
            if item_rows:
                warnings.append("小题明细已按班级/科目范围回退查询")

    if score_values and not item_rows:
        warnings.append(
            "已查到总分但无小题明细：请确认 tb_score_detail 是否已导入，"
            "且 question_id 能关联 tb_exam_question（或存在 question_score 列）"
        )

    # 有小题但成绩为空：放宽 class 过滤重试一次（tb_score.class 可能与传入值不一致）
    if not score_values and item_rows:
        relaxed_kw = {**base_kw, "class_name": ""}
        detail_wc_r, score_wc_r = _diagnosis_where_clause_pair(**relaxed_kw, skip_exam_name=True)
        _, _, sv_r, fs_r, _, score_rows = run_bundle(detail_wc_r, score_wc_r, "relaxed_score_no_class")
        if sv_r:
            score_values = sv_r
            full_score = fs_r if fs_r is not None else full_score
            warnings.append(
                f"成绩记录按班级 `{class_name}` 未查到，已放宽班级过滤重试"
                f"（命中 {len(sv_r)} 条）。建议核查 tb_score.class 实际值。"
            )

    # 考试名 LIKE 可能命中多场：班级横向对比/单场诊断收敛至参与人数最多的一场
    if (
        (exam_name or want_class_compare)
        and not student_id
        and score_rows
        and not pinned_exam_ids
    ):
        from src.agent.education.aggregation import pick_primary_exam_id

        exam_keys = {
            str(r.get("exam_id") or "").strip()
            for r in score_rows
            if isinstance(r, dict) and str(r.get("exam_id") or "").strip()
        }
        if len(exam_keys) > 1:
            primary = pick_primary_exam_id(score_rows)
            if primary:
                detail_wc_n, score_wc_n = _diagnosis_where_clause_pair(
                    **base_kw, exam_ids=[primary], skip_exam_name=True
                )
                item_rows, knowledge_rows, score_values, full_score, exam_ids, score_rows = (
                    run_bundle(detail_wc_n, score_wc_n, "narrow_primary_exam")
                )
                warnings.append(
                    f"考试名匹配到多场（{len(exam_keys)}），"
                    f"已收敛至参与人数最多的 exam_id={primary}"
                )

    item_class_rows: list[dict[str, Any]] = []
    knowledge_class_rows: list[dict[str, Any]] = []
    if want_class_compare and last_detail_wc and (item_rows or knowledge_rows):
        item_c_sql, know_c_sql = _diagnosis_class_compare_sql(last_detail_wc, db_type)
        for label, sql in (
            ("item_by_class", item_c_sql),
            ("knowledge_by_class", know_c_sql),
        ):
            success, msg, result, sql_run = _run_edu_sql(
                sql,
                datasource_id=datasource_id,
                workspace_oid=workspace_oid,
                user_id=user_id,
            )
            row_count = len(result.get("rows") or []) if isinstance(result, dict) else 0
            sql_logs.append(
                {
                    "phase": "class_compare",
                    "label": label,
                    "success": success,
                    "row_count": row_count,
                    "message": msg if not success else "",
                    "sql_preview": (sql_run or sql)[:600],
                }
            )
            if not success:
                errors.append(f"[class_compare/{label}] {msg}")
                continue
            if not isinstance(result, dict):
                continue
            if label == "item_by_class":
                item_class_rows = _rows_to_dicts(result)
            else:
                knowledge_class_rows = _rows_to_dicts(result)
        if item_class_rows or knowledge_class_rows:
            warnings.append(
                f"已加载班级横向对比明细：小题 {len(item_class_rows)} 行、"
                f"知识点 {len(knowledge_class_rows)} 行"
            )

    used_overview_scores = False
    if want_class_compare and not score_values:
        ov = _fetch_overview_class_scores(
            datasource_id=datasource_id,
            workspace_oid=workspace_oid,
            user_id=user_id,
            school_name=school_name,
            subject_name=subject_name,
            exam_name=exam_name,
        )
        sql_logs.extend(ov.get("sql_logs") or [])
        if ov.get("score_rows"):
            score_rows = list(ov["score_rows"])
            score_values = list(ov["score_values"] or [])
            full_score = ov.get("full_score") if ov.get("full_score") else full_score
            used_overview_scores = True
            warnings.append(
                "tb_score/小题明细为空，已从 tb_score_overview 按班级(bj)回落各班成绩；"
                "下一步调 build_subject_diagnosis_sections_tool(render=true)。"
                "禁止手写 execute_sql，禁止 SELECT xx AS class_name / GROUP BY xx。"
            )

    # 权威 KPI：对最终成绩 WHERE 做无 LIMIT 聚合（行级 score_sql 仍可能被 LIMIT 截断）
    kpi_stats: dict[str, Any] | None = None
    score_rows_incomplete = False
    from src.agent.education.config import load_config
    from src.agent.education.kpi_sql import (
        build_kpi_aggregate_sql,
        build_score_count_sql,
        kpi_row_to_stats,
    )

    cfg = load_config()
    if used_overview_scores:
        from src.agent.education.stats import compute_score_stats

        kpi_stats = compute_score_stats(score_values, cfg, full_score)
        sql_logs.append(
            {
                "phase": "kpi_aggregate",
                "label": "overview_class_scores",
                "success": True,
                "row_count": len(score_rows),
                "message": "",
                "sql_preview": "tb_score_overview class fallback",
            }
        )
    else:
        wc = last_score_wc if last_score_wc else score_wc
        kpi_sql = build_kpi_aggregate_sql(wc, cfg)
        success, msg, result, sql_run = _run_edu_sql(
            kpi_sql,
            datasource_id=datasource_id,
            workspace_oid=workspace_oid,
            user_id=user_id,
        )
        row_count = len(result.get("rows") or []) if isinstance(result, dict) else 0
        sql_logs.append(
            {
                "phase": "kpi_aggregate",
                "label": "score_kpi",
                "success": success,
                "row_count": row_count,
                "message": msg if not success else "",
                "sql_preview": (sql_run or kpi_sql)[:600],
            }
        )
        if success and isinstance(result, dict) and result.get("rows"):
            cols = result.get("columns") or []
            kpi_stats = kpi_row_to_stats(dict(zip(cols, result["rows"][0])), cfg)
        count_sql = build_score_count_sql(wc)
        ok_c, _, cres, _ = _run_edu_sql(
            count_sql,
            datasource_id=datasource_id,
            workspace_oid=workspace_oid,
            user_id=user_id,
        )
        if ok_c and isinstance(cres, dict) and cres.get("rows"):
            try:
                total = int(cres["rows"][0][0])
                if len(score_rows) < total:
                    score_rows_incomplete = True
                    warnings.append(
                        f"成绩明细行被截断（{len(score_rows)}/{total}），"
                        "KPI 以库内聚合为准"
                    )
            except (TypeError, ValueError, IndexError):
                pass

    class_tracks: dict[str, str] = {}
    if want_class_compare and score_rows:
        from src.agent.education.class_track import class_track_map

        class_tracks = class_track_map(score_rows)
        if not class_tracks:
            class_tracks = _fetch_overview_class_tracks(
                datasource_id=datasource_id,
                workspace_oid=workspace_oid,
                user_id=user_id,
                school_name=school_name,
                exam_name=exam_name,
            )
        if class_tracks:
            for r in score_rows:
                if isinstance(r, dict) and not r.get("track"):
                    cls = str(r.get("class_name") or r.get("class") or "").strip()
                    if cls and class_tracks.get(cls):
                        r["track"] = class_tracks[cls]

    return {
        "item_rows": item_rows,
        "knowledge_rows": knowledge_rows,
        "item_class_rows": item_class_rows,
        "knowledge_class_rows": knowledge_class_rows,
        "score_values": score_values,
        "score_rows": score_rows,
        "class_tracks": class_tracks,
        "full_score": full_score,
        "kpi_stats": kpi_stats,
        "score_rows_incomplete": score_rows_incomplete,
        "warnings": warnings,
        "errors": errors,
        "sql_logs": sql_logs,
    }
```

## src/agent/education/tools.py :: _knowledge_cohort_detail_sql

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:5980)

```python
def _knowledge_cohort_detail_sql(
    where_clause_detail: str,
    student_ids: list[str],
    db_type: str = "pg",
) -> str:
    """后十/中位组学生 × 知识点加权得分 SQL。"""
    full_score_expr = "COALESCE(eq.question_score, sd.question_score)"
    w_join = knowledge_weighted_join()
    w_score = "sd.score * COALESCE(eqk.w_norm, 1)"
    w_full = f"{full_score_expr} * COALESCE(eqk.w_norm, 1)"
    lits = ", ".join(f"'{_esc(str(x))}'" for x in student_ids if str(x).strip())
    id_pred = f"sc.student_id IN ({lits})" if lits else "1=0"
    extra = f" AND {id_pred}" if where_clause_detail else f" WHERE {id_pred}"
    return (
        "SELECT sc.student_id AS student_id,\n"
        "       COALESCE(k.knowledge_name, '未关联知识点') AS knowledge_name,\n"
        f"       SUM({w_score}) AS score,\n"
        f"       SUM({w_full}) AS full_score\n"
        "FROM tb_score_detail sd\n"
        "LEFT JOIN tb_exam_question eq ON sd.question_id = eq.id\n"
        "    AND (eq.exam_id IS NULL OR eq.exam_id = sd.exam_id)\n"
        f"{w_join}"
        "JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id\n"
        "JOIN tb_school sch ON sc.school_id = sch.id\n"
        "JOIN tb_exam e ON sc.exam_id = e.id\nLEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id"
        + where_clause_detail
        + extra
        + "\nGROUP BY sc.student_id, COALESCE(k.knowledge_name, '未关联知识点')\n"
        "LIMIT 20000"
    )
```

## src/agent/education/tools.py :: _fetch_class_student_item_rows

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:4454)

```python
def _fetch_class_student_item_rows(
    *,
    datasource_id: int,
    class_name: str = "",
    exam_names: list[str] | None = None,
    exam_name: str = "",
    subject_name: str = "",
    school_name: str = "",
    student_id: str = "",
    workspace_oid: int | None = None,
) -> list[dict[str, Any]]:
    """一次查出班级（或指定学生）在指定考试中每位学生的小题得分率。"""
    from src.agent.resource.tool.business import _load_datasource
    from src.datasource.service.sql_auto_fix import run_sql_with_auto_fix

    names = [str(n).strip() for n in (exam_names or []) if str(n).strip()]
    if not names and exam_name:
        names = [exam_name.strip()]

    db_type, config, _ds_name = _load_datasource(datasource_id, workspace_oid)
    parts = _diagnosis_where_parts(
        school_name=_keep_school_filter_arg(school_name),
        class_name=class_name,
        subject_name=subject_name,
        student_id=student_id.strip() if student_id else "",
        exam_name="",  # 多场考试用下方 OR 条件
        exam_id_expr="sd.exam_id",
        skip_exam_name=True,
    )
    if names:
        exam_ors: list[str] = []
        for n in names:
            for c in exam_name_like_candidates(n):
                exam_ors.append(f"{EXAM_NAME_SQL} LIKE '%{_esc(c)}%'")
        # 去重保持顺序
        seen_or: set[str] = set()
        uniq_ors: list[str] = []
        for o in exam_ors:
            if o not in seen_or:
                seen_or.add(o)
                uniq_ors.append(o)
        if uniq_ors:
            parts.append("(" + " OR ".join(uniq_ors) + ")")
    where = (" WHERE " + " AND ".join(parts)) if parts else ""

    full_score_expr = "COALESCE(eq.question_score, sd.question_score)"
    rate = _score_rate_sql("sd.score", full_score_expr, db_type)
    kn_join = knowledge_names_subquery_join(db_type)
    sql = (
        "SELECT sd.student_id AS student_id,\n"
        "       " + EXAM_NAME_SQL + " AS exam_name,\n"
        "       sd.question_no AS question_no,\n"
        "       COALESCE(kn.knowledge_name, '未关联知识点') AS knowledge_name,\n"
        f"       {full_score_expr} AS full_score,\n"
        "       sd.score AS score,\n"
        f"       {rate} AS score_rate\n"
        "FROM tb_score_detail sd\n"
        "LEFT JOIN tb_exam_question eq ON sd.question_id = eq.id\n"
        "    AND (eq.exam_id IS NULL OR eq.exam_id = sd.exam_id)\n"
        f"{kn_join}"
        "JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id\n"
        "JOIN tb_school sch ON sc.school_id = sch.id\n"
        "JOIN tb_exam e ON sc.exam_id = e.id\nLEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id"
        + where
        + f"\nORDER BY sd.student_id, {EXAM_NAME_SQL}, sd.question_no\nLIMIT 50000"
    )
    outcome = run_sql_with_auto_fix(sql, db_type=db_type, config=config)
    if not outcome.success:
        return []
    return _rows_to_dicts(outcome.result if isinstance(outcome.result, dict) else None)
```

## src/agent/education/tools.py :: _fetch_student_item_rows_direct

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:4526)

```python
def _fetch_student_item_rows_direct(
    *,
    datasource_id: int,
    student_id: str,
    subject_name: str = "",
    workspace_oid: int | None = None,
) -> list[dict[str, Any]]:
    """按学号直接查小题明细：不强制班级/考试名，避免过滤过严导致空结果。

    以 ``sd.student_id`` 为主条件，``tb_score`` 改为 LEFT JOIN（无总分行仍能出小题）。
    """
    from src.agent.resource.tool.business import _load_datasource
    from src.datasource.service.sql_auto_fix import run_sql_with_auto_fix

    sid = (student_id or "").strip()
    if not sid:
        return []
    db_type, config, _ = _load_datasource(datasource_id, workspace_oid)
    parts = [
        f"(sd.student_id = '{_esc(sid)}' OR sd.student_id LIKE '%{_esc(sid)}%')"
    ]
    if subject_name:
        parts.append(
            f"(sc.subject_name = '{_esc(subject_name)}' OR sc.subject_name IS NULL)"
        )
    where = " WHERE " + " AND ".join(parts)
    full_score_expr = "COALESCE(eq.question_score, sd.question_score)"
    rate = _score_rate_sql("sd.score", full_score_expr, db_type)
    kn_join = knowledge_names_subquery_join(db_type)
    sql = (
        "SELECT sd.student_id AS student_id,\n"
        "       COALESCE(" + EXAM_NAME_SQL + ", '未知考试') AS exam_name,\n"
        "       COALESCE(sc.subject_name, '') AS subject_name,\n"
        "       sd.question_no AS question_no,\n"
        "       COALESCE(kn.knowledge_name, '未关联知识点') AS knowledge_name,\n"
        f"       {full_score_expr} AS full_score,\n"
        "       sd.score AS score,\n"
        f"       {rate} AS score_rate\n"
        "FROM tb_score_detail sd\n"
        "LEFT JOIN tb_exam_question eq ON sd.question_id = eq.id\n"
        "    AND (eq.exam_id IS NULL OR eq.exam_id = sd.exam_id)\n"
        f"{kn_join}"
        "LEFT JOIN tb_exam e ON sd.exam_id = e.id\n"
        "LEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id\n"
        "LEFT JOIN tb_score sc ON sd.exam_id = sc.exam_id AND sd.student_id = sc.student_id"
        + where
        + "\nORDER BY subject_name, exam_name, sd.question_no\nLIMIT 20000"
    )
    outcome = run_sql_with_auto_fix(sql, db_type=db_type, config=config)
    if not outcome.success:
        logger.warning(
            "direct student item fetch failed student=%s msg=%s",
            sid,
            getattr(outcome, "message", ""),
        )
        return []
    return _rows_to_dicts(outcome.result if isinstance(outcome.result, dict) else None)
```

## src/agent/education/tools.py :: _fetch_class_score_long_table

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/education/tools.py:4621)

```python
def _fetch_class_score_long_table(
    *,
    datasource_id: int,
    class_name: str = "",
    student_name: str = "",
    school_name: str = "",
    subject_name: str = "",
    workspace_oid: int | None = None,
) -> dict[str, Any] | None:
    """上游明细缺失时，直接查 tb_score 拉全班×历次考试长表（供综合/学生报告）。"""
    from src.agent.resource.tool.business import _load_datasource
    from src.datasource.service.sql_auto_fix import run_sql_with_auto_fix

    cls = (class_name or "").strip()
    if not cls and student_name:
        cls = _resolve_class_name_for_student(
            datasource_id=datasource_id,
            student_name=student_name,
            school_name=school_name,
            workspace_oid=workspace_oid,
        )
    if not cls:
        return None

    db_type, config, _ = _load_datasource(datasource_id, workspace_oid)
    parts = _diagnosis_where_parts(
        school_name=_keep_school_filter_arg(school_name),
        class_name=cls,
        subject_name=subject_name,
        exam_name="",
        skip_exam_name=True,
    )
    where = (" WHERE " + " AND ".join(parts)) if parts else ""
    sql = (
        "SELECT " + EXAM_NAME_SQL + " AS exam_name,\n"
        "       sc.student_id AS student_id,\n"
        "       sc.subject_name AS subject_name,\n"
        "       sc.score AS score,\n"
        "       sc.class AS class,\n"
        "       e.exam_time AS exam_time\n"
        "FROM tb_score sc\n"
        "JOIN tb_school sch ON sc.school_id = sch.id\n"
        "JOIN tb_exam e ON sc.exam_id = e.id\nLEFT JOIN tb_exam_batch eb ON e.exam_batch_id = eb.id"
        + where
        + "\nORDER BY e.exam_time, sc.student_id, sc.subject_name\nLIMIT 20000"
    )
    outcome = run_sql_with_auto_fix(sql, db_type=db_type, config=config)
    if not outcome.success or not isinstance(outcome.result, dict):
        return None
    cols = list(outcome.result.get("columns") or [])
    rows = list(outcome.result.get("rows") or [])
    if not cols or not rows:
        return None
    return {
        "columns": cols,
        "rows": rows,
        "row_count": len(rows),
        "class_name": cls,
    }
```

## src/agent/resource/tool/business.py :: sample_rows

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/resource/tool/business.py:1890)

```python
def sample_rows(
    datasource_id: int,
    table_name: str,
    limit: int = SAMPLE_ROWS_DEFAULT,
    where_clause: str = "",
    user_id: int | None = None,
    workspace_oid: int | None = None,
) -> ToolResult:
    """采样表的若干行（可带 WHERE 过滤），用于理解真实数据样貌、枚举值、业务含义。

    典型用法：``describe_table`` 之后仍不确定字段取值语义时，调本工具做条件采样，
    例如只看 ``status='active'`` 的行、只看最近日期的行。

    Args:
        table_name: 表名（限制 ``[A-Za-z0-9_.]``，防 SQL 注入）。
        limit: 采样行数，默认 3，建议 1~10；超过 10 会被截断。
        where_clause: 可选 WHERE 条件**不含 WHERE 关键字本身**，例如
            ``status = 'active' AND created_at > '2024-01-01'``。留空表示不过滤。
            仅允许只读表达式；含 INSERT/UPDATE/DELETE/UNION-子 DML 等写操作一律拒绝；
            多条语句（分号）也会拒绝。
    """
    limit = max(1, min(int(limit or SAMPLE_ROWS_DEFAULT), SAMPLE_ROWS_LLM_MAX))
    db_type, config, _ = _load_datasource(datasource_id, workspace_oid)
    quoted = _safe_identifier(table_name, db_type)

    clause = (where_clause or "").strip().rstrip(";").strip()
    where_sql = f" WHERE {clause}" if clause else ""
    sql = f"SELECT * FROM {quoted}{where_sql} LIMIT {limit}"

    if clause:
        try:
            from src.agent.education.privacy_mode import apply_sql_privacy

            clause, _ = apply_sql_privacy(clause)
            where_sql = f" WHERE {clause}" if clause else ""
            sql = f"SELECT * FROM {quoted}{where_sql} LIMIT {limit}"
            _validate_read_only_select(sql, db_type)
        except ValueError as e:
            # 业务错误：返回 ToolResult 让 LLM 在 observation 里自修正；不抛。
            return ToolResult(
                content=f"采样失败：where_clause 不合法（{e}）。请只用 AND/OR 组合的过滤条件。",
                data=None,
            )

    if user_id is not None:
        from src.datasource.service.execute_with_permission import execute_sql_with_permission_by_user_id
        from src.datasource.service.sql_auto_fix import format_auto_fix_note

        success, message, result, sql_run = execute_sql_with_permission_by_user_id(
            user_id,
            datasource_id,
            workspace_oid,
            sql,
            tables_hint=[table_name.split(".")[-1]],
        )
        if not success:
            note = ""
            if isinstance(result, dict) and result.get("fixes_applied"):
                note = " " + format_auto_fix_note(result["fixes_applied"], success=False)
            return ToolResult(content=f"采样失败：{message}{note}", data=None)
    else:
        from src.datasource.service.sql_auto_fix import format_auto_fix_note, run_sql_with_auto_fix

        outcome = run_sql_with_auto_fix(sql, db_type=db_type, config=config)
        if not outcome.success:
            note = format_auto_fix_note(outcome.fixes_applied, success=False)
            msg = f"采样失败：{outcome.message}"
            if note:
                msg += f" {note}"
            return ToolResult(content=msg, data=None)
        result = outcome.result
        sql_run = outcome.sql_run

    if not isinstance(result, dict):
        return ToolResult(content="采样失败：无结果", data=None)

    from src.agent.education.privacy_mode import apply_result_privacy

    result = apply_result_privacy(result) or result
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    header = f"`{table_name}` 采样 {len(rows)} 行" + (f"（WHERE {clause}）" if clause else "") + "："
    content = header + "\n\n" + _format_rows_as_markdown(columns, rows, SAMPLE_ROWS_HARD_CAP)
    return ToolResult(content=content, data=result)
```

## src/agent/resource/tool/business.py :: _validate_read_only_select

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/agent/resource/tool/business.py:35)

```python
def _validate_read_only_select(sql: str, db_type: str) -> None:
    """确保 ``sql`` 是**单条** SELECT，AST 内不含任何写操作/DDL/UNION 绕过。

    相比 :func:`check_sql_read` 更严格：
    - 必须恰好 1 条语句（防 ``;`` 注入）；
    - 顶层必须是 ``exp.Select``（防 ``WITH`` / CTE 隐藏 INSERT 等）；
    - 全部子 AST 节点中不得出现 INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/MERGE/COPY；
    - parse 失败时**拒绝**而不是 fallback allow——工具侧是可控入口，宁可错杀。

    仅供 :func:`sample_rows` 在拼 WHERE 时用；不影响 :func:`execute_sql` 既有流程。
    """
    from sqlglot import expressions as exp
    from sqlglot import parse

    dialect = "mysql" if db_type == "mysql" else None
    try:
        statements = parse(sql, dialect=dialect)
    except Exception as e:
        raise ValueError(f"SQL 解析失败：{e}") from e
    if not statements or len(statements) != 1:
        raise ValueError("必须是恰好一条 SQL 语句")
    stmt = statements[0]
    if not isinstance(stmt, exp.Select):
        raise ValueError(f"必须是 SELECT 语句，实际是 {type(stmt).__name__}")

    write_types = (
        exp.Insert, exp.Update, exp.Delete,
        exp.Create, exp.Drop, exp.Alter,
        exp.Merge, exp.Copy,
    )
    for wt in write_types:
        if stmt.find(wt) is not None:
            raise ValueError(f"禁止使用写操作 {wt.__name__}")
```

## src/datasource/service/query_permission.py :: _exists_score_guard

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/datasource/service/query_permission.py:960)

```python
def _exists_score_guard(sd_alias: str, qualified_inner: str, db_type: str) -> str:
    """仅 FROM tb_score_detail 时，经 EXISTS 关联 tb_score 施加 school_id/class 谓词。"""
    q = "`" if db_type == "mysql" else '"'
    sc = "sc"
    return (
        f"EXISTS (SELECT 1 FROM tb_score {sc} "
        f"WHERE {sc}.{q}exam_id{q} = {sd_alias}.{q}exam_id{q} "
        f"AND {sc}.{q}student_id{q} = {sd_alias}.{q}student_id{q} "
        f"AND {qualified_inner})"
    )
```

## src/datasource/service/query_permission.py :: _sname_subq

[查看源文件](/Users/tanghaoyu/develop/git-repo/owner/awesome-project/src/datasource/service/query_permission.py:563)

```python
    def _sname_subq(body: str) -> str:
        return (
            f"SELECT COALESCE({q}s_name{q}, {q}name{q}) FROM tb_school "
            f"WHERE {q}id{q} IN ({body}) OR {q}name{q} IN ({body})"
        )
```
