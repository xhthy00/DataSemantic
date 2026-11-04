const escape = (value = "") =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );

export function mountSemanticViews(
  root,
  views,
  initialIndex = 0,
  onSelect = () => {},
  testResult = null,
) {
  let selected = Math.min(initialIndex, views.length - 1);
  let query = "";
  const description = (view) => view.properties?.description || "";
  root.innerHTML = `<div class="semantic-views-layout"><aside class="semantic-view-sidebar" aria-label="语义视图列表"><div class="semantic-view-search"><label for="semantic-view-search">查找视图</label><input id="semantic-view-search" type="search" placeholder="搜索名称、说明或 SQL"><p class="hint" id="semantic-view-count" aria-live="polite"></p></div><div class="semantic-view-items"></div></aside><section class="semantic-view-detail" aria-label="视图详情"></section></div>`;
  const list = root.querySelector(".semantic-view-items");
  const detail = root.querySelector(".semantic-view-detail");
  function draw() {
    const filter = query.trim().toLocaleLowerCase();
    const matches = views
      .map((view, index) => ({ view, index }))
      .filter(({ view }) =>
        [view.name, description(view), view.statement].some((value) =>
          String(value || "")
            .toLocaleLowerCase()
            .includes(filter),
        ),
      );
    if (!matches.some((item) => item.index === selected))
      selected = matches[0]?.index ?? null;
    onSelect(selected ?? 0);
    root.querySelector("#semantic-view-count").textContent =
      `${matches.length} / ${views.length} 个视图`;
    list.innerHTML =
      matches
        .map(
          ({ view, index }) =>
            `<button type="button" class="semantic-view-item ${selected === index ? "is-selected" : ""}" data-view-index="${index}" aria-pressed="${selected === index}"><span class="semantic-view-item-title"><span class="semantic-view-glyph" aria-hidden="true">SQL</span><strong title="${escape(view.name)}">${escape(view.name)}</strong></span><span class="semantic-view-description">${escape(description(view) || "暂无业务说明")}</span><span class="semantic-view-lines">${String(view.statement || "").split("\n").length} 行 SQL</span></button>`,
        )
        .join("") ||
      '<div class="semantic-view-no-results"><p>未找到匹配的视图</p><button type="button" data-view-clear>清空搜索</button></div>';
    const view = views[selected];
    if (!view) {
      detail.innerHTML =
        '<div class="semantic-view-placeholder"><h3>没有匹配的视图</h3><p>尝试搜索其他名称、业务说明或 SQL 关键词。</p></div>';
      return;
    }
    detail.innerHTML = `<div class="semantic-view-detail-head"><div><span class="semantic-view-eyebrow">语义视图</span><h3>${escape(view.name)}</h3></div><div class="row"><button type="button" class="primary mini" data-action="test-view" data-index="${selected}">测试视图</button><button type="button" class="mini" data-action="edit-view" data-index="${selected}">编辑视图</button><button type="button" class="quiet mini danger" data-action="delete-view" data-index="${selected}">删除视图</button></div></div><div class="semantic-view-business"><span class="small muted">业务说明</span><p>${escape(description(view) || "暂无业务说明，可通过编辑视图补充。")}</p></div><div class="semantic-view-sql-head"><strong>SQL 定义</strong><span class="small muted">${String(view.statement || "").split("\n").length} 行</span><button type="button" class="mini" data-view-copy>复制 SQL</button><span class="hint semantic-view-copy-status" role="status"></span></div><p class="semantic-view-test-hint">测试会先保存当前草稿，验证 SQL 规划，不查询业务数据。</p><pre class="semantic-view-code" tabindex="0" aria-label="${escape(view.name)} 的 SQL 定义"><code>${escape(view.statement || "尚未填写 SQL")}</code></pre>${testResult?.name === view.name && testResult.statement === view.statement ? renderViewTest(testResult) : ""}`;
  }
  root.querySelector("input").addEventListener("input", (event) => {
    query = event.target.value;
    draw();
  });
  root.addEventListener("click", async (event) => {
    const item = event.target.closest("[data-view-index]");
    if (item) {
      selected = Number(item.dataset.viewIndex);
      draw();
      list
        .querySelector(`[data-view-index="${selected}"]`)
        ?.focus({ preventScroll: true });
    }
    if (event.target.closest("[data-view-clear]")) {
      query = "";
      root.querySelector("input").value = "";
      draw();
      root.querySelector("input").focus();
    }
    if (event.target.closest("[data-view-copy]")) {
      const status = detail.querySelector(".semantic-view-copy-status");
      try {
        await navigator.clipboard.writeText(
          String(views[selected]?.statement || ""),
        );
        status.textContent = "已复制";
      } catch {
        status.textContent = "复制失败，请在下方选中 SQL 手动复制。";
      }
    }
  });
  draw();
}

function renderViewTest(result) {
  const success = Boolean(result.output);
  return `<section class="semantic-view-test-result ${success ? "is-success" : "is-error"}" data-view-test-result tabindex="-1" role="${success ? "status" : "alert"}"><div class="semantic-view-test-heading"><strong>${success ? "规划测试通过" : "规划测试未通过"}</strong>${success ? `<span>${Math.round(result.output.duration_ms)} ms</span>` : ""}</div><p>${success ? "视图已成功展开为物理 SQL，可供查询网关执行。" : escape(result.error)}</p>${result.issues?.length ? `<ul>${result.issues.map((issue) => `<li>${escape(issue.path)}：${escape(issue.message)}</li>`).join("")}</ul>` : ""}<div class="semantic-view-test-query"><span>测试查询</span><code>${escape(result.query)}</code></div>${success ? `<details><summary>生成的物理 SQL</summary><pre><code>${escape(result.output.physical_sql)}</code></pre></details>` : "<p>可编辑视图修正字段或表达式后，重新测试。</p>"}</section>`;
}
