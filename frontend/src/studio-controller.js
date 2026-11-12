import { renderAdmin, renderLoginPage, notifyAdmin } from "./admin.jsx";
import { mountRelationGraph } from "./relation-graph.js";
import { mountSemanticViews } from "./semantic-views.js";
import {
  semanticEditorMarkup,
  mountSemanticEditor,
  renderSemanticSummary,
} from "./semantic-model-editor.js";
import {
  relationColumns,
  parseRelationCondition,
  buildRelationCondition,
} from "./relation-conditions.js";

const $ = (selector, root = document) => root.querySelector(selector);
const escape = (value = "") =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const clone = (value) => JSON.parse(JSON.stringify(value));
const object = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const identifier = "^[A-Za-z_][A-Za-z0-9_]*$";
const types = [
  "varchar",
  "integer",
  "bigint",
  "double",
  "boolean",
  "date",
  "timestamp",
  "decimal",
];
const state = {
  csrf: "",
  drafts: [],
  trash: [],
  bundles: [],
  templates: [],
  draft: null,
  tab: "workspace",
  model: 0,
  column: 0,
  view: 0,
  viewTest: null,
  dirty: false,
  raw: null,
  validation: null,
  sql: null,
  output: null,
  error: null,
  busy: false,
  mobile: false,
};
const paths = {
  layers: '<path d="m3 7 9-5 9 5-9 5zM3 12l9 5 9-5M3 17l9 5 9-5"/>',
  table:
    '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  save: '<path d="M5 3h12l4 4v14H3V3zM7 3v6h10V3M7 21v-8h10v8"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  link: '<path d="m10 13 4-4M8 16l-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m4 0 2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/>',
  code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18"/>',
  book: '<path d="M12 5c-3-2-7-2-10-1v15c3-1 7-1 10 1 3-2 7-2 10-1V4c-3-1-7-1-10 1v15"/>',
  box: '<path d="m3 7 9-5 9 5v10l-9 5-9-5zM3 7l9 5 9-5M12 12v10"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  play: '<path d="m8 4 12 8-12 8z"/>',
  settings:
    '<circle cx="12" cy="12" r="3"/><path d="M3 7h18M3 17h18M7 3v8m10 2v8"/>',
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
  logout: '<path d="M9 3H3v18h6M10 12h11m-4-4 4 4-4 4"/>',
};
const icon = (name) =>
  `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.table}</svg>`;
const btn = (action, label, glyph, cls = "", extra = "") =>
  `<button type="button" data-action="${action}" class="${cls}" ${extra}>${glyph ? icon(glyph) : ""}${label}</button>`;
const input = (id, label, value = "", extra = "", hint = "") =>
  `<div class="form-item"><label for="${id}">${label}</label><input id="${id}" name="${id}" value="${escape(value)}" ${extra}>${hint ? `<p class="hint">${hint}</p>` : ""}</div>`;
const area = (id, label, value = "", extra = "") =>
  `<div class="form-item"><label for="${id}">${label}</label><textarea id="${id}" name="${id}" ${/\brows=/.test(extra) ? "" : 'rows="3"'} ${extra}>${escape(value)}</textarea></div>`;
const select = (id, label, values, value) =>
  `<div class="form-item"><label for="${id}">${label}</label><select id="${id}" name="${id}">${values
    .map((v) => {
      const [key, text] = Array.isArray(v) ? v : [v, v];
      return `<option value="${escape(key)}" ${key === value ? "selected" : ""}>${escape(text)}</option>`;
    })
    .join("")}</select></div>`;
const description = (o) => o?.properties?.description || "";
const models = () => state.draft?.manifest.models || [];
const currentModel = () => models()[state.model];
const date = (value) =>
  value
    ? new Date(value).toLocaleString("zh-CN", { hour12: false })
    : "随服务预置";
let toastTimer;
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, 4200);
}
function markDirty() {
  state.dirty = true;
  state.validation = null;
  state.output = null;
  state.error = null;
  notifyAdmin();
  $("#validation")?.remove();
  $("#page-error")?.remove();
  $("#raw-json")?.removeAttribute("aria-invalid");
  $("#raw-json")?.removeAttribute("aria-describedby");
}
function errorText(error) {
  return error.message || "操作未完成，请稍后重试。";
}
async function api(path, method = "GET", body) {
  const response = await fetch(`/studio/api${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" ? { "X-Studio-CSRF": state.csrf } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && path !== "/login") {
      state.csrf = "";
      if ($("#modal").open) $("#modal").close();
      renderLogin("登录已过期。重新登录后可继续保存当前页面的修改。");
    }
    const error = new Error(
      data.error?.message || `请求失败（${response.status}）`,
    );
    Object.assign(error, {
      code: data.error?.code,
      issues: data.error?.issues,
      status: response.status,
    });
    throw error;
  }
  return data;
}
async function run(work) {
  if (state.busy) return;
  state.busy = true;
  notifyAdmin();
  const controls = [
    ...document.querySelectorAll("button,input,textarea,select"),
  ].map((el) => [el, el.disabled]);
  controls.forEach(([el]) => {
    el.disabled = true;
  });
  document.body.setAttribute("aria-busy", "true");
  try {
    return await work();
  } catch (error) {
    if ($("#modal").open)
      showDialogError(
        errorText(error) +
          (error.issues
            ? "\n" +
              error.issues.map((i) => i.path + "：" + i.message).join("\n")
            : ""),
      );
    else if (state.csrf) {
      state.error = error;
      if (error.issues)
        state.validation = { valid: false, issues: error.issues };
      render();
      $("#page-error")?.focus();
    } else if (!$("#login-error")) renderLogin(errorText(error));
  } finally {
    state.busy = false;
    notifyAdmin();
    controls.forEach(([el, disabled]) => {
      el.disabled = disabled;
    });
    document.body.removeAttribute("aria-busy");
  }
}
function assertEditable(manifest) {
  if (!object(manifest)) throw new Error("MDL 顶层必须为 JSON 对象。");
  for (const key of ["models", "relationships", "views"]) {
    if (manifest[key] === undefined) manifest[key] = [];
    if (!Array.isArray(manifest[key]) || manifest[key].some((v) => !object(v)))
      throw new Error(`${key} 必须为对象数组。`);
  }
  for (const model of manifest.models) {
    if (model.columns === undefined) model.columns = [];
    if (model.tableReference !== undefined && !object(model.tableReference))
      throw new Error("tableReference 必须为对象。");
    if (!Array.isArray(model.columns) || model.columns.some((c) => !object(c)))
      throw new Error("每个模型的 columns 必须为字段对象数组。");
  }
  for (const value of [
    ...manifest.models,
    ...manifest.models.flatMap((m) => m.columns),
    ...manifest.views,
  ]) {
    if (value.properties !== undefined && !object(value.properties))
      throw new Error("properties 必须为对象。");
  }
  for (const r of manifest.relationships)
    if (
      r.models !== undefined &&
      (!Array.isArray(r.models) || r.models.some((n) => typeof n !== "string"))
    )
      throw new Error("关联的 models 必须为模型名称数组。");
  return manifest;
}
function applyRaw() {
  if (state.raw === null) return;
  let manifest;
  try {
    manifest = JSON.parse(state.raw);
  } catch (e) {
    throw new Error(`JSON 语法错误：${e.message}`);
  }
  state.draft.manifest = assertEditable(manifest);
  state.raw = null;
  state.model = Math.min(state.model, Math.max(models().length - 1, 0));
  state.column = 0;
}
function setDraft(draft) {
  assertEditable(draft.manifest);
  state.draft = clone(draft);
  state.model = 0;
  state.column = 0;
  state.tab = "models";
  state.view = 0;
  state.viewTest = null;
  state.raw = null;
  state.dirty = false;
  state.validation = null;
  state.error = null;
  state.output = null;
  state.sql = null;
  history.replaceState(null, "", `#draft=${encodeURIComponent(draft.id)}`);
  render();
}
async function refresh() {
  const [drafts, bundles, templates, trash] = await Promise.all([
    api("/drafts"),
    api("/bundles"),
    api("/templates"),
    api("/drafts?deleted=true"),
  ]);
  state.trash = trash.drafts;
  state.drafts = drafts.drafts;
  state.bundles = bundles.bundles;
  state.templates = templates.templates;
}
async function saveDraft() {
  applyRaw();
  if (!state.dirty) return state.draft;
  const d = state.draft;
  const saved = await api(`/drafts/${d.id}`, "PUT", {
    name: d.name,
    dialect: d.dialect,
    manifest: d.manifest,
    revision: d.revision,
  });
  state.draft = saved;
  state.dirty = false;
  state.drafts = [saved, ...state.drafts.filter((x) => x.id !== saved.id)];
  return saved;
}
function openDialog(title, body, submitLabel, onSubmit) {
  const dialog = $("#modal");
  dialog.innerHTML = `<form id="dialog-form"><div class="dialog-head"><h2 id="dialog-title">${escape(title)}</h2>${btn("close-dialog", "", "close", "quiet icon-only", 'aria-label="关闭对话框"')}</div><div class="dialog-body"><div id="dialog-error" class="dialog-error" role="alert" tabindex="-1" hidden></div>${body}</div><div class="dialog-foot">${btn("close-dialog", "取消", null)}<button type="submit" class="primary">${escape(submitLabel)}</button></div></form>`;
  if (!dialog.open) dialog.showModal();
  $("#dialog-form").onsubmit = (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void run(async () => {
      await onSubmit(data);
    });
  };
}
function showDialogError(message) {
  const el = $("#dialog-error");
  if (el) {
    el.textContent = message;
    el.hidden = false;
    el.focus();
  }
}
async function mayLeave() {
  if (!state.dirty) return true;
  return new Promise((resolve) => {
    openDialog(
      "尚有未保存的修改",
      "<p>离开当前草稿前，请选择保存修改或放弃修改。</p>",
      "保存并继续",
      async () => {
        await saveDraft();
        $("#modal").close();
        render();
        resolve(true);
      },
    );
    $(".dialog-foot").insertAdjacentHTML(
      "afterbegin",
      btn("discard", "放弃修改", null, "danger"),
    );
    $('[data-action="discard"]').onclick = () => {
      void run(async () => {
        const draft = await api(`/drafts/${state.draft.id}`);
        $("#modal").close();
        setDraft(draft);
        resolve(true);
      });
    };
    $("#modal").addEventListener("close", () => resolve(false), { once: true });
  });
}
function renderLogin(message = "") {
  renderLoginPage({
    message,
    onSubmit: (password) => {
      void run(async () => {
        try {
          const session = await api("/login", "POST", { password });
          state.csrf = session.csrf;
          await refresh();
          if (state.draft) render();
          else await initialDraft();
        } catch (error) {
          renderLogin(errorText(error));
        }
      });
    },
  });
}
function validation() {
  const v = state.validation;
  if (!v) return "";
  return `<section id="validation" class="validation ${v.valid ? "good" : ""}" tabindex="-1" role="${v.valid ? "status" : "alert"}">${btn("clear-validation", "", "close", "quiet mini", 'aria-label="关闭校验结果"')}<h3>${icon(v.valid ? "check" : "code")}${v.valid ? "模型校验通过" : "请修正以下模型问题"}</h3>${v.valid ? `<p>Wren SDK 已验证 ${v.checked_models.length} 个模型 / 视图，耗时 ${v.duration_ms} ms。可继续预览 SQL 或发布。</p>` : `<ul>${v.issues.map((issue) => `<li><button class="issue-link" data-action="issue" data-path="${escape(issue.path)}"><code>${escape(issue.path)}</code></button> — ${escape(issue.message)}</li>`).join("")}</ul>`}</section>`;
}
function render() {
  if (!state.csrf) return renderLogin();
  const d = state.draft;
  const editing = d && !["workspace", "guide", "releases"].includes(state.tab);
  const error = state.error
    ? `<div id="page-error" class="dialog-error" role="alert" tabindex="-1">${escape(errorText(state.error))}${state.error.code === "DRAFT_CONFLICT" && editing ? `<p>当前修改仍在页面中。请先导出备份，再重新加载服务器草稿。</p>${btn("export", "导出当前 MDL", "download")}${btn("reload-draft", "重新加载服务器草稿", null)}` : ""}</div>`
    : "";
  const html =
    error +
    (editing
      ? `${validation()}<section id="tab-panel" aria-label="${{ models: "模型与字段", relationships: "模型关联", views: "语义视图", json: "MDL JSON", sql: "SQL 预览" }[state.tab]}">${content()}</section>`
      : content());
  renderAdmin({
    state,
    html,
    onReady: bindEditor,
    onAction: dispatchAction,
    request: api,
    onGenerated: (result) => {
      state.drafts = [result.draft, ...state.drafts];
      setDraft(result.draft);
      state.validation = result.validation;
      render();
      toast(
        `自动建模完成，已生成 ${result.draft.manifest.models.length} 个模型并通过 Wren 校验。`,
      );
    },
  });
}
function empty(title, text, action, label) {
  return `<div class="panel empty">${icon("layers")}<h2>${title}</h2><p>${text}</p>${btn(action, label, "plus", "primary")}</div>`;
}
function content() {
  if (state.tab === "workspace") return "";
  if (state.tab === "guide") return guide();
  if (state.tab === "releases") return releases();
  if (!state.draft)
    return empty(
      "创建你的第一个 MDL 模型",
      "选择学情示例了解建模方式，或从空白草稿开始映射自己的数据。",
      "new-draft",
      "新建模型草稿",
    );
  if (state.tab === "relationships") return relations();
  if (state.tab === "views") return views();
  if (state.tab === "json")
    return `<section class="panel"><div class="panel-head"><div><h2>${icon("code")}MDL JSON</h2><p class="sub">与可视化编辑同步；保留自定义属性。保存时检查 JSON 语法。</p></div>${btn("format-json", "格式化", null)}</div><label class="sr-only" for="raw-json">MDL JSON 源码</label><textarea spellcheck="false" id="raw-json" class="code-editor" ${state.error ? 'aria-invalid="true" aria-describedby="page-error"' : ""}>${escape(state.raw ?? JSON.stringify(state.draft.manifest, null, 2))}</textarea></section>`;
  if (state.tab === "sql") return sqlPanel();
  return modelEditor();
}
function modelEditor() {
  const m = currentModel();
  if (!m)
    return empty(
      "添加一个逻辑模型",
      "逻辑模型代表一个业务实体，例如学生、学校或考试成绩。",
      "add-model",
      "添加逻辑模型",
    );
  const c = m.columns[state.column];
  return `<div class="editor-layout"><section class="panel"><div class="panel-head"><div><h2>${icon("table")}${escape(m.properties?.displayName || m.name || "逻辑模型")}</h2><p class="sub">${escape(m.name)} · ${m.columns.length} 个字段</p></div><div class="row">${btn("edit-model", "编辑模型", null, "mini")}${btn("delete-model", "", "trash", "quiet mini danger", 'aria-label="删除当前模型"')}</div></div>${renderSemanticSummary(m)}<div class="model-properties"><div class="form-grid"><div><label>物理数据来源</label><div class="mono source-value">${escape(m.refSql || [m.tableReference?.catalog, m.tableReference?.schema, m.tableReference?.table].filter(Boolean).join("."))}</div></div><div><label>业务说明</label><p class="small muted">${escape(description(m) || "尚未填写，点击编辑模型补充。")}</p></div></div></div><div class="table-heading"><h3>字段 <span class="muted">${m.columns.length}</span></h3>${btn("add-column", "添加字段", "plus", "mini")}</div>${m.columns.length ? `<div class="table-wrap"><table><thead><tr><th>逻辑字段</th><th>数据类型</th><th>业务说明</th><th>属性</th></tr></thead><tbody>${m.columns.map((col, i) => `<tr class="${state.column === i ? "active" : ""}"><td><button class="field-button" data-action="select-column" data-index="${i}"><span class="field-icon">${col.relationship ? "↗" : "#"}</span>${escape(col.name || "未命名")}</button></td><td><span class="type-label">${escape(col.type)}</span></td><td class="col-description">${escape(description(col) || "—")}</td><td><div class="prop-icons">${m.primaryKey === col.name ? '<span class="prop-tag pk">主键</span>' : ""}${col.isCalculated ? '<span class="prop-tag calc">计算</span>' : ""}${col.relationship ? '<span class="prop-tag">关联</span>' : ""}${col.notNull ? '<span class="prop-tag">非空</span>' : ""}</div></td></tr>`).join("")}</tbody></table></div>` : '<div class="empty"><p>还没有字段。添加字段，建立逻辑名称与物理列的映射。</p></div>'}</section><aside class="panel inspector"><div class="panel-head"><h2>字段属性</h2><span class="badge blue">${c?.relationship ? "导航字段" : c?.isCalculated ? "计算字段" : "物理字段"}</span></div>${c ? `<div class="panel-body"><p class="inspector-title">${escape(m.name)}.${escape(c.name)}</p>${input("col-name", "逻辑字段名称", c.name, 'data-column="name"')}${input("col-type", "数据类型", c.type, 'data-column="type" list="column-types"')}<datalist id="column-types">${[...types, ...models().map((x) => x.name)].map((t) => `<option value="${escape(t)}">`).join("")}</datalist>${area("col-description", "业务说明", description(c), 'data-column="description"')}${input("col-expression", c.relationship ? "关联名称" : "物理列 / SQL 表达式", c.relationship || c.expression || "", `data-column="${c.relationship ? "relationship" : "expression"}"`, c.relationship ? "引用“模型关联”中定义的关联。" : "留空时使用同名物理列。")}<hr class="section-divider"><label class="check"><input type="checkbox" data-column="isCalculated" ${c.isCalculated ? "checked" : ""}>计算字段</label><label class="check"><input type="checkbox" data-column="primaryKey" ${m.primaryKey === c.name ? "checked" : ""}>设为主键</label><label class="check"><input type="checkbox" data-column="notNull" ${c.notNull ? "checked" : ""}>不允许为空</label><div class="info-strip">计算字段可使用表达式定义业务口径，例如有效成绩、金额或比率。关联取值可设为计算字段，例如 school_name 的表达式为 school.name。</div>${btn("delete-column", "删除字段", "trash", "quiet danger")}</div>` : '<div class="panel-body muted small">选择一个字段查看与编辑属性。</div>'}</aside></div>`;
}
function relations() {
  const rs = state.draft.manifest.relationships;
  return `<div class="stack"><section class="panel"><div class="panel-head"><div><h2>${icon("link")}模型关联</h2><p class="sub">定义实体之间的连接条件与关联基数；通过导航字段定义跨模型计算字段。</p></div>${btn("add-relation", "添加关联", "plus", "primary")}</div>${
    models().length
      ? '<div id="relation-canvas" class="relation-graph"></div>'
      : ""
  }<div class="panel-body small muted">${rs.length} 条关联 · ${models().length} 个逻辑模型</div></section><div class="relation-list">${rs.map((r, i) => `<section class="panel relation-card"><div class="row spread"><h3>${escape(r.name)}</h3><div class="row">${btn("edit-relation", "编辑", null, "mini", `data-index="${i}"`)}${btn("delete-relation", "", "trash", "quiet mini danger", `data-index="${i}" aria-label="删除关联 ${escape(r.name)}"`)}</div></div><div class="relation-route">${escape(r.models?.[0])}<span class="badge blue">${escape(r.joinType)}</span>${escape(r.models?.[1])}</div><p class="condition mono">${escape(r.condition)}</p></section>`).join("") || empty("连接你的业务实体", "先添加两个逻辑模型，再定义它们如何连接。", "add-relation", "添加关联")}</div></div>`;
}
function views() {
  const items = state.draft.manifest.views;
  return `<section class="panel semantic-views-panel"><div class="panel-head"><div><h2>${icon("code")}语义视图 <span class="badge">${items.length}</span></h2><p class="sub">将常用查询封装为可复用视图，选择左侧条目查看 SQL 定义。</p></div>${btn("add-view", "添加视图", "plus", "primary")}</div>${items.length ? '<div id="semantic-views"></div>' : empty("把常用查询封装为视图", "使用逻辑模型与字段编写 SQL，例如按学校聚合平均有效成绩。", "add-view", "添加语义视图")}</section>`;
}
function sqlPanel() {
  if (state.sql === null) {
    const m = currentModel() || models()[0];
    state.sql = m
      ? `SELECT * FROM "${String(m.name).replaceAll('"', '""')}" LIMIT 10`
      : "";
  }
  return `<div class="stack"><section class="panel"><div class="panel-head"><div><h2>${icon("code")}语义 SQL</h2><p class="sub">使用逻辑模型和字段编写查询。预览前会自动保存当前草稿。</p></div><span class="badge">${escape(state.draft.dialect)}</span></div><label for="semantic-sql" class="sr-only">语义 SQL</label><textarea id="semantic-sql" spellcheck="false" class="code-editor sql-editor">${escape(state.sql)}</textarea><div class="sql-actions row spread"><span class="small muted">仅生成物理 SQL，不执行数据库查询。</span>${btn("plan", "生成物理 SQL", "play", "primary")}</div></section><section class="panel"><div class="panel-head"><h2>物理 SQL</h2>${state.output ? `<span class="badge green">规划成功 · ${state.output.duration_ms} ms</span>` : ""}</div><pre class="code-output ${state.output ? "" : "placeholder"}">${escape(state.output?.physical_sql || "生成结果将显示在这里。")}</pre></section></div>`;
}
function guide() {
  return `<div class="guide stack"><div class="page-heading"><div><h1>从数据表到 MDL 模型</h1><p>MDL 描述业务实体、字段、计算口径与模型关系。</p></div>${btn("new-draft", "开始创建", "plus", "primary")}</div><div class="help-steps">${[
    ["01 / MAP", "映射业务实体", "为物理表或视图起一个逻辑名称，如 schools。"],
    [
      "02 / DEFINE",
      "定义字段与口径",
      "设置字段类型、业务说明、主键及计算表达式。",
    ],
    [
      "03 / VERIFY",
      "验证并发布",
      "校验模型，用标准 SQL 验证，再发布不可变版本。",
    ],
  ]
    .map(
      ([n, t, p]) =>
        `<section class="panel help-step"><div class="step-number">${n}</div><h3>${t}</h3><p>${p}</p></section>`,
    )
    .join(
      "",
    )}</div><section class="panel"><div class="panel-head"><h2>推荐创建流程</h2></div><div class="panel-body"><ol class="guide-list"><li><strong>新建草稿：</strong>选择学情分析示例或空白模型，填写名称与目标数据库方言。</li><li><strong>添加逻辑模型：</strong>指定物理表的 catalog / schema / table；也可使用只读 <code>refSql</code> 定义数据来源。</li><li><strong>添加字段：</strong>填写逻辑名、类型及说明。不同名物理列填入表达式；计算字段填写 SQL 表达式并启用计算。</li><li><strong>建立关联：</strong>选择两个模型、关联基数和连接条件，再添加导航字段，并用它定义计算字段，例如 <code>school_name = school.name</code>。关联条件示例：<code>student_subject_score.school_id = schools.id</code>。</li><li><strong>保存并校验：</strong>通过结构检查与真实 Wren SDK 规划。点击校验问题可查看对应的 JSON。</li><li><strong>SQL 预览：</strong>用逻辑字段编写标准业务查询，查看展开后的物理 SQL；实际数据对账由宿主查询网关完成。</li><li><strong>发布版本：</strong>填写唯一版本 ID，如 <code>education-v2</code>。发布后可下载包含 MDL 与 registry 的 ZIP，或直接在当前服务中使用该版本。</li></ol><p class="info-strip">示例物理表仅用于演示映射。正式使用时请替换为真实数据结构，并核对业务口径。发布不会修改或创建业务数据库中的表。</p></div></section></div>`;
}
function releases() {
  return `<div class="stack"><div class="page-heading"><div><h1>已发布版本</h1><p>每个版本固定 MDL 内容与 SHA-256，可供宿主服务绑定。</p></div>${btn("refresh-releases", "刷新", null)}</div><section class="panel"><div class="table-wrap"><table><thead><tr><th>发布物</th><th>数据库 / 模型</th><th>来源 / 时间</th><th>操作</th></tr></thead><tbody>${state.bundles.map((b) => `<tr><td><div class="release-id">${escape(b.bundle_id)}</div><div class="release-hash">${escape(b.manifest_hash)}</div></td><td>${escape(b.dialect)} · ${b.models_count}</td><td>${b.source === "studio" ? "Studio 发布" : "预置模型"}<div class="small muted">${date(b.created_at)}</div></td><td><div class="row"><a class="button mini" href="/studio/api/bundles/${encodeURIComponent(b.bundle_id)}/download">${icon("download")}下载 ZIP</a>${btn("clone-bundle", "创建草稿", null, "mini", `data-id="${escape(b.bundle_id)}"`)}</div></td></tr>`).join("")}</tbody></table></div></section></div>`;
}
let graphCleanup;
function bindEditor() {
  graphCleanup?.();
  graphCleanup = null;
  const viewList = $("#semantic-views");
  if (viewList)
    mountSemanticViews(
      viewList,
      state.draft.manifest.views,
      state.view,
      (index) => {
        state.view = index;
      },
      state.viewTest?.draftId === state.draft.id &&
        state.viewTest.manifest === JSON.stringify(state.draft.manifest)
        ? state.viewTest
        : null,
    );
  const graph = $("#relation-canvas");
  if (graph) {
    graphCleanup = mountRelationGraph(
      graph,
      models(),
      state.draft.manifest.relationships,
      (index) => void dispatchAction("edit-relation", { index }),
    );
  }
  document.querySelectorAll("[data-column]").forEach((el) =>
    el.addEventListener("input", () => {
      const m = currentModel(),
        c = m.columns[state.column],
        key = el.dataset.column;
      if (key === "description")
        c.properties = { ...c.properties, description: el.value };
      else if (key === "primaryKey") {
        if (el.checked) m.primaryKey = c.name;
        else delete m.primaryKey;
      } else if (key === "name") {
        if (m.primaryKey === c.name) m.primaryKey = el.value;
        c.name = el.value;
      } else c[key] = el.type === "checkbox" ? el.checked : el.value;
      markDirty();
      const row = $(".table-wrap tbody")?.rows[state.column];
      if (row) {
        row.cells[0].querySelector("button").innerHTML =
          `<span class="field-icon">${c.relationship ? "↗" : "#"}</span>${escape(c.name || "未命名")}`;
        row.cells[1].querySelector("span").textContent = c.type;
        row.cells[2].textContent = description(c) || "—";
      }
      document.querySelectorAll(".table-wrap tbody tr").forEach((tr, i) => {
        const col = m.columns[i];
        tr.cells[3].innerHTML = `<div class="prop-icons">${m.primaryKey === col.name ? '<span class="prop-tag pk">主键</span>' : ""}${col.isCalculated ? '<span class="prop-tag calc">计算</span>' : ""}${col.relationship ? '<span class="prop-tag">关联</span>' : ""}${col.notNull ? '<span class="prop-tag">非空</span>' : ""}</div>`;
      });
      $(".inspector-title").textContent = `${m.name}.${c.name}`;
      $(".inspector .badge").textContent = c.relationship
        ? "导航字段"
        : c.isCalculated
          ? "计算字段"
          : "物理字段";
    }),
  );
  $("#raw-json")?.addEventListener("input", (e) => {
    state.raw = e.target.value;
    markDirty();
  });
  $("#semantic-sql")?.addEventListener("input", (e) => {
    state.sql = e.target.value;
    state.output = null;
    const output = $(".code-output");
    if (output) {
      output.textContent = "查询已修改，请重新生成物理 SQL。";
      output.classList.add("placeholder");
    }
    $("#tab-panel .badge.green")?.remove();
  });
}
function editModel(index = null) {
  const m =
    index === null
      ? {
          name: "",
          columns: [],
          tableReference: { schema: "public", table: "" },
          properties: {},
        }
      : models()[index];
  openDialog(
    index === null ? "添加逻辑模型" : "编辑逻辑模型",
    `<p>将物理数据源映射为业务实体。逻辑名称用于语义 SQL。</p><div class="form-grid">${input("model-name", "逻辑模型名称", m.name, `required pattern="${identifier}" placeholder="student_subject_score"`)}${input("display-name", "显示名称", m.properties?.displayName)}${input("source-catalog", "物理 Catalog（可选）", m.tableReference?.catalog)}${input("source-schema", "物理 Schema（可选）", m.tableReference?.schema)}<div class="full">${input("source-table", "物理表 / 视图", m.tableReference?.table, 'placeholder="v_student_subject_score"')}</div><div class="full">${area("ref-sql", "或使用只读来源 SQL（refSql）", m.refSql, 'class="code-input" placeholder="SELECT id, name FROM public.students"')}<p class="hint">表映射与 refSql 二选一；填写 SQL 时优先使用 SQL。</p></div><div class="full">${area("model-description", "业务说明", description(m))}</div></div>`,
    "保存模型",
    async (f) => {
      const name = f.get("model-name").trim();
      if (
        models().some((x, i) => i !== index && x.name === name) ||
        state.draft.manifest.views.some((v) => v.name === name)
      )
        throw new Error("模型或视图名称已存在。");
      const sql = f.get("ref-sql").trim(),
        table = f.get("source-table").trim();
      if (!sql && !table) throw new Error("请填写物理表名称或来源 SQL。");
      if (
        index !== null &&
        name !== m.name &&
        state.draft.manifest.relationships.some((r) =>
          r.models?.includes(m.name),
        )
      )
        throw new Error(
          "该模型已被关联引用。请先在 MDL JSON 中同步修改模型名、关联条件与导航字段类型。",
        );
      m.name = name;
      if (m.properties?.semanticModel) m.properties.semanticModel.object = name;
      m.properties = {
        ...m.properties,
        displayName: f.get("display-name").trim(),
        description: f.get("model-description").trim(),
      };
      if (sql) {
        m.refSql = sql;
        delete m.tableReference;
      } else {
        delete m.refSql;
        m.tableReference = { table };
        for (const key of ["catalog", "schema"])
          if (f.get("source-" + key).trim())
            m.tableReference[key] = f.get("source-" + key).trim();
      }
      if (index === null) {
        models().push(m);
        state.model = models().length - 1;
        state.column = 0;
      }
      markDirty();
      $("#modal").close();
      render();
    },
  );
}
function addColumn() {
  const m = currentModel();
  openDialog(
    "添加字段",
    `<div class="form-grid">${input("field-name", "逻辑字段名称", "", 'required pattern="' + identifier + '" placeholder="student_id"')}${input("field-type", "数据类型", "varchar", 'required list="new-types"')}<datalist id="new-types">${[...types, ...models().map((x) => x.name)].map((t) => `<option value="${escape(t)}">`).join("")}</datalist><div class="full">${input("field-expression", "物理列 / SQL 表达式", "", 'placeholder="默认与逻辑字段同名"')}</div><div class="full">${select("field-relation", "导航字段关联（可选）", [["", "普通字段"], ...state.draft.manifest.relationships.filter((r) => r.models?.includes(m.name)).map((r) => r.name)], "")}</div><div class="full">${area("field-description", "业务说明")}</div><label class="check"><input type="checkbox" name="calculated">计算字段</label><label class="check"><input type="checkbox" name="primary-key">设为主键</label></div>`,
    "添加字段",
    async (f) => {
      const name = f.get("field-name").trim(),
        expression = f.get("field-expression").trim(),
        relationship = f.get("field-relation");
      if (m.columns.some((c) => c.name === name))
        throw new Error("当前模型已有同名字段。");
      if (f.has("calculated") && !expression)
        throw new Error("计算字段需要填写表达式。");
      if (relationship && f.has("calculated"))
        throw new Error("导航字段不能同时设为计算字段。");
      const c = {
        name,
        type: f.get("field-type").trim(),
        properties: { description: f.get("field-description").trim() },
      };
      if (expression) c.expression = expression;
      if (f.has("calculated")) c.isCalculated = true;
      if (relationship) {
        c.relationship = relationship;
        const r = state.draft.manifest.relationships.find(
          (r) => r.name === relationship,
        );
        c.type = r.models.find((n) => n !== m.name) || m.name;
      }
      m.columns.push(c);
      if (f.has("primary-key")) m.primaryKey = name;
      state.column = m.columns.length - 1;
      markDirty();
      $("#modal").close();
      render();
    },
  );
}
function editRelation(index = null) {
  if (models().length < 2) {
    toast("请先添加至少两个逻辑模型。");
    return;
  }
  const r =
    index === null
      ? {
          name: "",
          models: [
            (currentModel() || models()[0]).name,
            models().find((m) => m !== (currentModel() || models()[0])).name,
          ],
          joinType: "MANY_TO_ONE",
          condition: "",
        }
      : state.draft.manifest.relationships[index];
  const fromName = r.models?.[0] || models()[0].name;
  const toName = r.models?.[1] || models()[1].name;
  let rows = parseRelationCondition(r.condition, fromName, toName);
  let preserveCondition = rows === null;
  rows = rows?.length ? rows : [{ from: "", operator: "=", to: "" }];
  const navigation = models().flatMap((m) =>
    m.columns.filter((c) => c.relationship && c.relationship === r.name),
  );
  openDialog(
    index === null ? "添加模型关联" : "编辑模型关联",
    `<div class="form-grid"><div class="full">${input("relation-name", "关联名称", r.name, `required pattern="${identifier}"`)}</div>${select(
      "from-model",
      "来源模型",
      models().map((m) => m.name),
      fromName,
    )}${select(
      "to-model",
      "目标模型",
      models().map((m) => m.name),
      toName,
    )}<div class="full">${select(
      "join-type",
      "关联基数",
      [
        ["MANY_TO_ONE", "多对一 · MANY_TO_ONE"],
        ["ONE_TO_MANY", "一对多 · ONE_TO_MANY"],
        ["ONE_TO_ONE", "一对一 · ONE_TO_ONE"],
        ["MANY_TO_MANY", "多对多 · MANY_TO_MANY"],
      ],
      r.joinType,
    )}</div><div class="full" id="relation-model-hint"></div><fieldset class="full relation-conditions"><legend>关联条件</legend><p class="hint">两侧字段相等时关联，选择字段即可。多条条件需同时满足（AND）。</p><div id="condition-editor"></div><div class="condition-preview"><span class="small muted">条件预览</span><pre id="condition-preview" aria-live="polite"></pre></div></fieldset></div><p class="hint">保存关联后，在来源模型添加一个导航字段，选择此关联，再通过计算字段暴露目标字段（如 school_name 的表达式为 school.name）。</p>`,
    "保存关联",
    async (f) => {
      const name = f.get("relation-name").trim(),
        from = $("#from-model").value,
        to = $("#to-model").value;
      if (from === to) throw new Error("请选择两个不同的模型。");
      if (
        state.draft.manifest.relationships.some(
          (x, i) => i !== index && x.name === name,
        )
      )
        throw new Error("关联名称已存在。");
      if (navigation.length && (from !== r.models[0] || to !== r.models[1]))
        throw new Error("关联已被导航字段使用，请先移除导航字段再更换模型。");
      const condition = preserveCondition
        ? r.condition
        : buildRelationCondition(rows, from, to, models());
      navigation.forEach((c) => {
        c.relationship = name;
      });
      Object.assign(r, {
        name,
        models: [from, to],
        joinType: f.get("join-type"),
        condition,
      });
      if (index === null) state.draft.manifest.relationships.push(r);
      markDirty();
      $("#modal").close();
      render();
    },
  );
  const modelSelects = [$("#from-model"), $("#to-model")];
  const selectedModels = () => modelSelects.map((el) => el.value);
  const availableColumns = () =>
    selectedModels().map((name) =>
      relationColumns(models().find((m) => m.name === name)),
    );
  const updatePreview = () => {
    $("#dialog-error").hidden = true;
    const preview = $("#condition-preview");
    if (preserveCondition) preview.textContent = r.condition;
    else {
      try {
        preview.textContent = buildRelationCondition(
          rows,
          ...selectedModels(),
          models(),
        );
      } catch (error) {
        preview.textContent = error.message;
      }
    }
  };
  const renderConditions = () => {
    const [from, to] = selectedModels();
    const columns = availableColumns();
    modelSelects.forEach((el, side) => {
      el.disabled = navigation.length > 0 || preserveCondition;
      [...el.options].forEach((option) => {
        option.disabled = option.value === modelSelects[1 - side].value;
      });
    });
    $("#relation-model-hint").innerHTML = navigation.length
      ? '<p class="hint">此关联已被导航字段使用，模型已锁定；仍可调整字段条件和关联基数。</p>'
      : "";
    const editor = $("#condition-editor");
    if (preserveCondition) {
      editor.innerHTML =
        '<p class="info-strip">此关联包含复杂表达式，已保留原条件。可直接保存其他设置，或重新选择字段配置条件。</p><button type="button" class="mini" data-condition-action="replace">重新选择字段配置</button>';
    } else {
      const fieldOptions = (side, value) => {
        const options = [
          ["", columns[side].length ? "请选择字段" : "此模型暂无可关联字段"],
        ];
        if (value && !columns[side].some((c) => c.name === value))
          options.push([value, `${value}（字段已不存在，请重新选择）`]);
        return [
          ...options,
          ...columns[side].map((c) => [
            c.name,
            [c.name, c.type, description(c)].filter(Boolean).join(" · "),
          ]),
        ];
      };
      editor.innerHTML =
        rows
          .map(
            (row, i) =>
              `<div class="condition-row" data-condition-index="${i}">${i ? '<span class="condition-and">且</span>' : ""}<div class="condition-fields">${select(`condition-from-${i}`, `来源字段${rows.length > 1 ? ` ${i + 1}` : ""} · ${escape(from)}`, fieldOptions(0, row.from), row.from).replace("<select ", "<select required ")}<div class="form-item"><span class="condition-operator-label">关联方式</span><div class="condition-equals" aria-label="等于">等于 =</div></div>${select(`condition-to-${i}`, `目标字段${rows.length > 1 ? ` ${i + 1}` : ""} · ${escape(to)}`, fieldOptions(1, row.to), row.to).replace("<select ", "<select required ")}<button type="button" class="quiet icon-only danger condition-remove" data-condition-action="remove" aria-label="删除第 ${i + 1} 条条件" ${rows.length === 1 ? "disabled" : ""}>${icon("trash")}</button></div></div>`,
          )
          .join("") +
        '<button type="button" class="mini" data-condition-action="add">' +
        icon("plus") +
        "添加条件</button>";
      if (columns.some((list) => !list.length))
        editor.insertAdjacentHTML(
          "beforeend",
          '<p class="hint">请先为所选模型添加普通字段；导航字段不能作为关联条件。</p>',
        );
    }
    updatePreview();
  };
  $("#condition-editor").addEventListener("change", (event) => {
    const match = event.target.name?.match(/^condition-(from|to)-(\d+)$/);
    if (!match) return;
    rows[Number(match[2])][match[1]] = event.target.value;
    updatePreview();
  });
  $("#condition-editor").addEventListener("click", (event) => {
    const button = event.target.closest("[data-condition-action]");
    if (!button || state.busy) return;
    const action = button.dataset.conditionAction;
    let focus;
    if (action === "replace") {
      preserveCondition = false;
      rows = [{ from: "", operator: "=", to: "" }];
      focus = "#condition-from-0";
    } else if (action === "add") {
      rows.push({ from: "", operator: "=", to: "" });
      focus = `#condition-from-${rows.length - 1}`;
    } else if (action === "remove" && rows.length > 1) {
      const i = Number(
        button.closest("[data-condition-index]").dataset.conditionIndex,
      );
      rows.splice(i, 1);
      focus = `#condition-from-${Math.min(i, rows.length - 1)}`;
    }
    renderConditions();
    if (focus) $(focus)?.focus();
  });
  modelSelects.forEach((el, side) => {
    el.addEventListener("change", () => {
      // A field from the old model must never silently become a different field.
      rows.forEach((row) => {
        row[side === 0 ? "from" : "to"] = "";
      });
      renderConditions();
    });
  });
  renderConditions();
}
async function editSemanticModel(name) {
  await saveDraft();
  const manifest = state.draft.manifest;
  const obj = [...manifest.models, ...manifest.views].find(
    (item) => item.name === name,
  );
  if (!obj) throw new Error("请选择需要配置的模型或视图。");
  const viewIndex = manifest.views.indexOf(obj);
  if (viewIndex >= 0) state.view = viewIndex;
  const path = `/drafts/${state.draft.id}/semantic-preview`;
  const body = { revision: state.draft.revision, object_name: name };
  const discovered = await api(path, "POST", body);
  if (!discovered.valid) {
    const error = new Error("无法读取输出字段，请先修正模型或视图 SQL。");
    error.issues = discovered.issues;
    throw error;
  }
  let editor;
  openDialog(
    `配置 V2 语义模型 · ${name}`,
    semanticEditorMarkup(obj, discovered.output_columns),
    "校验并应用到草稿",
    async () => {
      const semantic = editor.read();
      const result = await api(path, "POST", {
        ...body,
        semantic_model: semantic,
      });
      if (!result.valid) {
        const error = new Error("V2 语义配置校验未通过，请检查下列配置。");
        error.issues = result.issues;
        throw error;
      }
      obj.properties = { ...obj.properties, semanticModel: semantic };
      markDirty();
      $("#modal").close();
      render();
      toast("V2 语义配置已应用到草稿，请保存并发布新版本。");
    },
  );
  editor = mountSemanticEditor(
    $(".semantic-model-editor"),
    obj,
    manifest,
    discovered.output_columns,
  );
}

function editView(index = null) {
  const v =
    index === null
      ? { name: "", statement: "", properties: {} }
      : state.draft.manifest.views[index];
  openDialog(
    index === null ? "添加语义视图" : "编辑语义视图",
    `${input("view-name", "视图名称", v.name, `required pattern="${identifier}"`)}${area("view-description", "业务说明", description(v))}${area("view-sql", "只读语义 SQL", v.statement, 'required class="code-input" rows="6"')}`,
    "保存视图",
    async (f) => {
      const name = f.get("view-name").trim();
      if (
        models().some((m) => m.name === name) ||
        state.draft.manifest.views.some(
          (x, i) => i !== index && x.name === name,
        )
      )
        throw new Error("模型或视图名称已存在。");
      Object.assign(v, {
        name,
        statement: f.get("view-sql").trim(),
        properties: {
          ...v.properties,
          description: f.get("view-description").trim(),
        },
      });
      if (v.properties?.semanticModel) v.properties.semanticModel.object = name;
      if (index === null) state.draft.manifest.views.push(v);
      state.view = index ?? state.draft.manifest.views.length - 1;
      markDirty();
      $("#modal").close();
      render();
    },
  );
}
function confirmDelete(title, message, work) {
  openDialog(title, `<p>${escape(message)}</p>`, "确认删除", async () => {
    work();
    markDirty();
    $("#modal").close();
    render();
  });
}
function newDraft(imported = null, defaultName = "") {
  const templates = state.templates;
  openDialog(
    imported ? "从 MDL 创建草稿" : "新建模型草稿",
    `<p>草稿可随时修改；发布后将生成独立、固定的版本。</p>${input("draft-name", "草稿名称", defaultName, 'required maxlength="100" placeholder="例如：学情分析语义模型"')}${select(
      "dialect",
      "目标数据库",
      [
        ["postgres", "PostgreSQL"],
        ["mysql", "MySQL"],
        ["duckdb", "DuckDB"],
      ],
      "postgres",
    )}${
      imported
        ? '<p class="hint">已载入 MDL 内容，创建后可继续编辑。</p>'
        : select(
            "template",
            "起始模板",
            templates.map((t) => [t.id, t.name]),
            templates[0]?.id,
          )
    }`,
    "创建草稿",
    async (f) => {
      const manifest = assertEditable(
        clone(
          imported ||
            templates.find((t) => t.id === f.get("template")).manifest,
        ),
      );
      const draft = await api("/drafts", "POST", {
        name: f.get("draft-name").trim(),
        dialect: f.get("dialect"),
        manifest,
      });
      state.drafts.unshift(draft);
      $("#modal").close();
      setDraft(draft);
      toast("草稿已创建，开始定义模型与字段。");
    },
  );
}
function importDialog() {
  openDialog(
    "导入 MDL JSON",
    `<p>导入已有的 mdl.json 为新草稿，也可直接粘贴 JSON。</p><div class="form-item"><label for="mdl-file">选择 MDL 文件</label><input id="mdl-file" type="file" accept=".json,application/json"></div>${area("import-json", "MDL JSON", "", 'class="code-input" rows="9"')}`,
    "继续创建",
    async (f) => {
      let source = f.get("import-json").trim();
      const file = $("#mdl-file").files[0];
      if (file) {
        if (file.size > 1_000_000) throw new Error("文件不能超过 1 MB。");
        source = await file.text();
      }
      let manifest;
      try {
        manifest = JSON.parse(source);
      } catch {
        throw new Error("请输入有效的 MDL JSON 或选择 JSON 文件。");
      }
      assertEditable(manifest);
      newDraft(manifest, file?.name.replace(/\.json$/i, "") || "导入的模型");
    },
  );
}
function exportDraft() {
  applyRaw();
  downloadManifest(state.draft.manifest);
}
function downloadManifest(manifest) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(manifest, null, 2) + "\n"], {
      type: "application/json",
    }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "mdl.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("已导出当前 MDL。");
}
function findDraft(id) {
  const draft = state.drafts.find((d) => d.id === id);
  if (!draft) throw new Error("草稿已变化，请刷新列表。");
  return clone(draft);
}
function metadataDialog(draft) {
  openDialog(
    "修改模型信息",
    `${input("draft-name", "模型名称", draft.name, 'required maxlength="100"')}${select(
      "dialect",
      "目标数据库",
      [
        ["postgres", "PostgreSQL"],
        ["mysql", "MySQL"],
        ["duckdb", "DuckDB"],
      ],
      draft.dialect,
    )}<p class="hint">更改数据库类型后，请重新校验模型与 SQL。</p>`,
    "保存修改",
    async (f) => {
      await api(`/drafts/${draft.id}`, "PATCH", {
        name: f.get("draft-name").trim(),
        dialect: f.get("dialect"),
        revision: draft.revision,
      });
      await refresh();
      state.error = null;
      $("#modal").close();
      render();
      toast("模型信息已更新。");
    },
  );
}
function deleteDraftDialog(draft) {
  openDialog(
    "删除模型草稿",
    `<p>将 <strong>${escape(draft.name)}</strong> 移入回收站，可随时恢复。已发布版本继续可用。</p>`,
    "移入回收站",
    async () => {
      await api(`/drafts/${draft.id}`, "DELETE", { revision: draft.revision });
      if (state.draft?.id === draft.id) {
        state.draft = null;
        state.dirty = false;
        state.raw = null;
      }
      await refresh();
      state.error = null;
      $("#modal").close();
      render();
      toast("模型已移入回收站。");
    },
  );
}
function manifestCounts(manifest) {
  const models = Array.isArray(manifest.models) ? manifest.models : [];
  return `${models.length} 个模型 · ${models.reduce((n, m) => n + (Array.isArray(m.columns) ? m.columns.length : 0), 0)} 个字段 · ${Array.isArray(manifest.relationships) ? manifest.relationships.length : 0} 条关联`;
}
function updateManifestDialog(draft) {
  openDialog(
    "更新 MDL 内容",
    `<p>为 <strong>${escape(draft.name)}</strong> 导入新版本的 MDL。更新后可进入编辑页校验并发布。</p><div class="form-item"><label for="update-file">选择 MDL JSON 文件</label><input id="update-file" type="file" accept=".json,application/json"></div>${area("update-json", "或粘贴 MDL JSON", "", 'class="code-input" rows="8"')}`,
    "预览更新",
    async (f) => {
      let source = f.get("update-json").trim();
      const file = $("#update-file").files[0];
      if (file) {
        if (file.size > 1_000_000) throw new Error("文件不能超过 1 MB。");
        source = await file.text();
      }
      let manifest;
      try {
        manifest = JSON.parse(source);
      } catch {
        throw new Error("请选择有效的 MDL JSON 文件，或粘贴 JSON 内容。");
      }
      assertEditable(manifest);
      openDialog(
        "确认更新 MDL",
        `<p>替换 <strong>${escape(draft.name)}</strong> 的草稿内容，已发布版本保留。</p><div class="update-comparison"><div><label>当前内容</label><p>${manifestCounts(draft.manifest)}</p></div><div><label>更新后</label><p>${manifestCounts(manifest)}</p></div></div><p class="hint">更新后请重新校验字段、关联及业务口径。</p>`,
        "确认更新",
        async () => {
          await api(`/drafts/${draft.id}`, "PUT", {
            name: draft.name,
            dialect: draft.dialect,
            manifest,
            revision: draft.revision,
          });
          await refresh();
          state.error = null;
          $("#modal").close();
          render();
          toast("MDL 内容已更新，请进入编辑页校验。");
        },
      );
    },
  );
}
function settingsDialog() {
  const d = state.draft;
  openDialog(
    "草稿设置",
    `${input("draft-name", "草稿名称", d.name, 'required maxlength="100"')}${select("dialect", "目标数据库", ["postgres", "mysql", "duckdb"], d.dialect)}<div class="form-grid">${input("catalog", "逻辑 Catalog", d.manifest.catalog, `required pattern="${identifier}"`)}${input("schema", "逻辑 Schema", d.manifest.schema, `required pattern="${identifier}"`)}</div>`,
    "应用设置",
    async (f) => {
      d.name = f.get("draft-name").trim();
      d.dialect = f.get("dialect");
      d.manifest.catalog = f.get("catalog").trim();
      d.manifest.schema = f.get("schema").trim();
      markDirty();
      $("#modal").close();
      render();
    },
  );
}
function publishDialog() {
  openDialog(
    "发布模型版本",
    `<p>发布前将自动保存并校验。版本 ID 必须唯一，发布后内容固定；后续修改请使用新的版本 ID。</p>${input("bundle-id", "版本 ID", "", 'required pattern="^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$" maxlength="100" placeholder="education-v2"')}<p class="hint">发布成功后，该版本可立即通过当前服务的规划 API 使用。</p>`,
    "校验并发布",
    async (f) => {
      await saveDraft();
      const b = await api(`/drafts/${state.draft.id}/publish`, "POST", {
        revision: state.draft.revision,
        bundle_id: f.get("bundle-id").trim(),
      });
      await refresh();
      state.tab = "releases";
      state.validation = null;
      state.error = null;
      $("#modal").close();
      render();
      toast(`版本 ${b.bundle_id} 已发布。`);
    },
  );
}
async function initialDraft() {
  const id = new URLSearchParams(location.hash.slice(1)).get("draft");
  if (id && state.drafts.some((d) => d.id === id))
    setDraft(await api(`/drafts/${encodeURIComponent(id)}`));
  else {
    state.tab = "workspace";
    history.replaceState(null, "", "#workspace");
    render();
  }
}
async function dispatchAction(action, data = {}) {
  if (state.busy) return;
  const el = { dataset: data };
  const index = Number(data.index);
  if (action === "close-dialog") {
    $("#modal").close();
    return;
  }
  if (action === "discard") return;
  if (
    [
      "workspace",
      "open-draft",
      "reload-draft",
      "new-draft",
      "import",
      "clone-bundle",
      "logout",
    ].includes(action)
  ) {
    if (!(await mayLeave())) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  await run(async () => {
    if (action === "mobile") {
      state.mobile = !state.mobile;
      render();
    } else if (action === "workspace") {
      await refresh();
      state.tab = "workspace";
      state.error = null;
      history.replaceState(null, "", "#workspace");
      render();
    } else if (action === "refresh-workspace") {
      await refresh();
      state.error = null;
      render();
      toast("列表已更新。");
    } else if (action === "draft-metadata") {
      metadataDialog(findDraft(data.id));
    } else if (action === "draft-update") {
      updateManifestDialog(findDraft(data.id));
    } else if (action === "draft-delete") {
      deleteDraftDialog(findDraft(data.id));
    } else if (action === "draft-restore") {
      const draft = state.trash.find((d) => d.id === data.id);
      if (!draft) throw new Error("草稿已变化，请刷新列表。");
      await api(`/drafts/${draft.id}/restore`, "POST", {
        revision: draft.revision,
      });
      await refresh();
      render();
      toast("模型已恢复，可在模型列表继续编辑。");
    } else if (action === "draft-export") {
      downloadManifest(findDraft(data.id).manifest);
    } else if (action === "new-draft") newDraft();
    else if (action === "import") importDialog();
    else if (action === "open-draft" || action === "reload-draft") {
      setDraft(
        await api(
          `/drafts/${encodeURIComponent(el.dataset.id || state.draft.id)}`,
        ),
      );
      state.mobile = false;
      render();
    } else if (action === "logout") {
      await api("/logout", "POST", {});
      Object.assign(state, { csrf: "", draft: null, dirty: false, raw: null });
      history.replaceState(null, "", location.pathname);
      renderLogin();
    } else if (action === "clone-bundle") {
      const manifest = await api(
        `/bundles/${encodeURIComponent(el.dataset.id)}/manifest`,
      );
      newDraft(manifest, el.dataset.id + " 副本");
    } else if (action === "releases" || action === "guide") {
      applyRaw();
      state.tab = action;
      state.mobile = false;
      render();
    } else if (action === "refresh-releases") {
      await refresh();
      render();
    } else if (action === "select-model") {
      applyRaw();
      state.model = index;
      state.column = 0;
      state.tab = "models";
      state.mobile = false;
      render();
    } else if (action === "select-column") {
      state.column = index;
      render();
      $("#col-name")?.focus();
    } else if (action === "tab") {
      applyRaw();
      state.error = null;
      state.tab = el.dataset.tab;
      render();
      $(`#tab-${state.tab}`)?.focus();
    } else if (action === "save") {
      await saveDraft();
      state.error = null;
      render();
      toast("草稿已保存。");
    } else if (action === "validate") {
      await saveDraft();
      state.validation = await api(
        `/drafts/${state.draft.id}/validate`,
        "POST",
        { revision: state.draft.revision },
      );
      state.error = null;
      render();
      $("#validation")?.focus();
    } else if (action === "test-view") {
      const view = state.draft.manifest.views[index];
      if (!view) throw new Error("请选择需要测试的语义视图。");
      state.view = index;
      state.viewTest = null;
      const button = document.querySelector('[data-action="test-view"]');
      if (button) button.textContent = "测试中…";
      await saveDraft();
      const query = `SELECT * FROM "${String(view.name).replaceAll('"', '""')}" LIMIT 10`;
      const result = {
        draftId: state.draft.id,
        name: view.name,
        statement: view.statement,
        manifest: JSON.stringify(state.draft.manifest),
        query,
      };
      try {
        result.output = await api(`/drafts/${state.draft.id}/plan`, "POST", {
          revision: state.draft.revision,
          semantic_sql: query,
        });
      } catch (error) {
        if (error.status === 401 || error.status === 409) throw error;
        result.error = errorText(error);
        result.issues = error.issues;
      }
      state.viewTest = result;
      render();
      document.querySelector("[data-view-test-result]")?.focus();
    } else if (action === "plan") {
      if (!state.sql?.trim()) throw new Error("请输入语义 SQL。");
      await saveDraft();
      state.output = null;
      state.error = null;
      const output = await api(`/drafts/${state.draft.id}/plan`, "POST", {
        revision: state.draft.revision,
        semantic_sql: state.sql,
      });
      state.output = output;
      render();
    } else if (action === "publish") {
      applyRaw();
      publishDialog();
    } else if (action === "export") exportDraft();
    else if (action === "settings") {
      applyRaw();
      settingsDialog();
    } else if (action === "add-model") {
      applyRaw();
      editModel();
    } else if (action === "edit-model") editModel(state.model);
    else if (action === "add-column") addColumn();
    else if (action === "add-relation") editRelation();
    else if (action === "edit-relation") editRelation(index);
    else if (action === "add-view") editView();
    else if (action === "edit-view") editView(index);
    else if (action === "edit-semantic-model")
      await editSemanticModel(data.name);
    else if (action === "delete-semantic-model") {
      const obj = [
        ...state.draft.manifest.models,
        ...state.draft.manifest.views,
      ].find((item) => item.name === data.name);
      if (!obj) throw new Error("模型或视图不存在。");
      confirmDelete(
        "移除 V2 语义配置",
        `移除 ${obj.name} 的 V2 配置？引用该来源的候选维度需要同步调整，保存并发布新版本后生效。`,
        () => {
          delete obj.properties.semanticModel;
        },
      );
    } else if (action === "delete-model") {
      const m = currentModel();
      if (
        state.draft.manifest.relationships.some((r) =>
          r.models?.includes(m.name),
        )
      )
        throw new Error("请先移除引用此模型的关联及导航字段。");
      confirmDelete(
        "删除逻辑模型",
        `将删除 ${m.name} 及其所有字段。语义视图与 SQL 表达式中的引用需自行同步调整。`,
        () => {
          models().splice(state.model, 1);
          state.model = 0;
          state.column = 0;
        },
      );
    } else if (action === "delete-column") {
      const m = currentModel(),
        c = m.columns[state.column];
      confirmDelete(
        "删除字段",
        `将删除字段 ${c.name}。关联条件、计算字段及视图中的引用需自行同步调整。`,
        () => {
          if (m.primaryKey === c.name) delete m.primaryKey;
          m.columns.splice(state.column, 1);
          state.column = Math.max(0, state.column - 1);
        },
      );
    } else if (action === "delete-relation") {
      const r = state.draft.manifest.relationships[index];
      confirmDelete(
        "删除模型关联",
        `将删除 ${r.name} 及引用它的导航字段。`,
        () => {
          models().forEach((m) => {
            m.columns = m.columns.filter((c) => c.relationship !== r.name);
          });
          state.draft.manifest.relationships.splice(index, 1);
          state.column = 0;
        },
      );
    } else if (action === "delete-view")
      confirmDelete(
        "删除语义视图",
        `将删除 ${state.draft.manifest.views[index].name}，请检查其他视图中的引用。`,
        () => state.draft.manifest.views.splice(index, 1),
      );
    else if (action === "clear-validation") {
      state.validation = null;
      render();
    } else if (action === "issue") {
      applyRaw();
      state.tab = "json";
      render();
      const raw = $("#raw-json");
      raw.focus();
      const match = el.dataset.path.match(
        /^models\[(\d+)\]\.columns\[(\d+)\](?:\.(\w+))?/,
      );
      if (match && models()[Number(match[1])]?.columns[Number(match[2])]) {
        state.model = Number(match[1]);
        state.column = Number(match[2]);
        state.tab = "models";
        render();
        const target =
          {
            name: "col-name",
            type: "col-type",
            expression: "col-expression",
            relationship: "col-expression",
          }[match[3]] || "col-name";
        const field = $("#" + target);
        field.focus();
        field.setAttribute("aria-invalid", "true");
        field.setAttribute("aria-describedby", "validation");
      } else raw.focus();
    } else if (action === "format-json") {
      applyRaw();
      render();
    }
  });
}
document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-action]");
  if (el) void dispatchAction(el.dataset.action, el.dataset);
});
document.addEventListener("keydown", (e) => {
  if (
    (e.metaKey || e.ctrlKey) &&
    e.key === "s" &&
    state.csrf &&
    state.draft &&
    !$("#modal").open
  ) {
    e.preventDefault();
    void run(async () => {
      await saveDraft();
      render();
      toast("草稿已保存。");
    });
  }
});
$("#modal").addEventListener("cancel", (e) => {
  if (state.busy) e.preventDefault();
});
window.addEventListener("beforeunload", (e) => {
  if (state.dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
void run(async () => {
  try {
    state.csrf = (await api("/session")).csrf;
    await refresh();
    await initialDraft();
  } catch (error) {
    if (error.status === 401) renderLogin();
    else renderLogin("无法连接工作台：" + errorText(error));
  }
});
