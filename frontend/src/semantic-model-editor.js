export const fieldList = (value) =>
  String(value || "")
    .split(/[,，\n]/)
    .map((v) => v.trim())
    .filter(Boolean);

const esc = (value = "") =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const clone = (value) => JSON.parse(JSON.stringify(value));
const input = (id, label, value = "", extra = "", hint = "") =>
  `<div class="form-item"><label for="${id}">${label}</label><input id="${id}" value="${esc(value)}" ${extra}>${hint ? `<p class="hint">${esc(hint)}</p>` : ""}</div>`;
const area = (id, label, value = "", hint = "") =>
  `<div class="form-item"><label for="${id}">${label}</label><textarea id="${id}" rows="2">${esc(value)}</textarea>${hint ? `<p class="hint">${esc(hint)}</p>` : ""}</div>`;
const select = (id, label, values, value) =>
  `<div class="form-item"><label for="${id}">${label}</label><select id="${id}">${values.map(([key, text]) => `<option value="${esc(key)}" ${value === key ? "selected" : ""}>${esc(text)}</option>`).join("")}</select></div>`;
const list = (id, names) =>
  `<datalist id="${id}">${names.map((n) => `<option value="${esc(n)}"></option>`).join("")}</datalist>`;
const fields = (
  id,
  label,
  value,
  listId,
  hint = "多个值用逗号分隔，复合键按填写顺序对应。",
) =>
  input(
    id,
    label,
    (value || []).join(", "),
    `list="${listId}" autocomplete="off"`,
    hint,
  );
const optional = (value) => value || null;
export const measureOperations = [
  ["identity", "直接使用字段值"],
  ["sum", "求和"],
  ["avg", "平均值"],
  ["min", "最小值"],
  ["max", "最大值"],
  ["count", "计数"],
  ["count_distinct", "去重计数"],
  ["weighted_mean", "加权平均"],
];

export function newSemanticModel(object, columns) {
  return {
    schema_version: 2,
    object,
    description: "",
    columns: [...columns],
    grain: [],
    dimensions: [],
    measures: [],
    capabilities: [],
  };
}

export function semanticEditorMarkup(obj, columns) {
  return `<div class="semantic-editor semantic-model-editor"><div class="semantic-intro"><span class="badge blue">语义模型 · V2</span><p>定义 <strong>${esc(obj.name)}</strong> 的维度身份、指标口径与可用分析能力。</p><p class="hint">粒度描述每行代表什么，不会自动要求用户选择单个维度值。打开配置时会先保存当前草稿。</p></div><p class="semantic-columns"><strong>SDK 输出字段</strong><br>${(columns[obj.name] || []).map((c) => `<code>${esc(c)}</code>`).join(" ")}</p><div data-semantic-basic></div>${[
    ["dimensions", "维度", "声明业务身份及层级；例如考试、学校、科目。"],
    ["measures", "指标", "定义字段如何计算，以及适用的统计人群。"],
    [
      "capabilities",
      "分析能力",
      "可选。声明本来源支持的分析和预计算排名范围。",
    ],
  ]
    .map(
      ([key, label, hint]) =>
        `<section data-semantic-section="${key}"><div class="semantic-section-head"><div><h3>${label} <span data-semantic-count="${key}" aria-live="polite"></span></h3><p class="hint">${hint}</p></div><button type="button" data-semantic-add="${key}">添加${label}</button></div><div data-semantic-rows="${key}"></div></section>`,
    )
    .join(
      "",
    )}<details class="semantic-preview"><summary>查看 V2 JSON</summary><pre data-semantic-json></pre></details></div>`;
}

export function mountSemanticEditor(root, obj, manifest, columns) {
  const base = clone(
    obj.properties?.semanticModel ??
      newSemanticModel(obj.name, columns[obj.name] || []),
  );
  const objects = [...manifest.models, ...manifest.views];
  const sources = objects
    .filter((o) => o.name === obj.name || o.properties?.semanticModel)
    .map((o) => [o.name, o.name]);
  // Keep stale imported references visible so they can be explicitly repaired.
  for (const d of base.dimensions || []) {
    const name = d.candidate_source?.object;
    if (name && !sources.some(([n]) => n === name))
      sources.push([name, `${name}（尚未配置 V2）`]);
  }
  root.querySelector("[data-semantic-basic]").innerHTML =
    `${list("semantic-fields", columns[obj.name] || [])}<div data-semantic-identities></div><h3>来源与数据粒度</h3>${area("semantic-description", "来源说明", base.description)}<div class="form-grid">${fields("semantic-columns", "声明的输出字段", base.columns, "semantic-fields", "可声明全部或部分 SDK 输出字段，维度和指标引用的字段必须包含在内。")}${fields("semantic-grain", "每行粒度（维度标识）", base.grain, "semantic-dimensions", "填写下方定义的维度标识，例如 exam, school, subject；至少一个。")}</div>`;
  const groups = {
    dimensions: new Map(),
    measures: new Map(),
    capabilities: new Map(),
  };
  let serial = 0;
  const get = (id) => root.querySelector(`#${id}`).value.trim();
  const arr = (id) => fieldList(get(id));
  const fieldInput = (id, label, value = "") =>
    input(id, label, value, 'list="semantic-fields" autocomplete="off"');
  function refresh() {
    for (const [kind, rows] of Object.entries(groups)) {
      const container = root.querySelector(`[data-semantic-rows="${kind}"]`);
      container.querySelector("[data-semantic-empty]")?.remove();
      root.querySelector(`[data-semantic-count="${kind}"]`).textContent =
        `(${rows.size})`;
      if (!rows.size)
        container.innerHTML =
          '<p class="semantic-empty" data-semantic-empty>尚未添加，点击上方按钮开始配置。</p>';
    }
    root.querySelector("[data-semantic-identities]").innerHTML =
      list(
        "semantic-dimensions",
        [...groups.dimensions.keys()]
          .map((k) => get(`${k}-id`))
          .filter(Boolean),
      ) +
      list(
        "semantic-measures",
        [...groups.measures.keys()].map((k) => get(`${k}-id`)).filter(Boolean),
      );
  }
  function add(kind, value = {}) {
    const key = `semantic-row-${serial++}`;
    const row = document.createElement("fieldset");
    row.className = "semantic-requirement";
    const label = {
      dimensions: "维度",
      measures: "指标",
      capabilities: "分析能力",
    }[kind];
    const identity = `<div class="form-grid">${input(`${key}-id`, `${label}标识`, value.id, "required")}${kind !== "capabilities" ? input(`${key}-label`, `${label}名称`, value.label, "required") : ""}</div>`;
    let content;
    if (kind === "dimensions") {
      const candidate = value.candidate_source || {};
      content = `${identity}<div class="form-grid">${fields(`${key}-fields`, "身份键字段", value.fields, "semantic-fields")}${fields(`${key}-labels`, "显示名称字段", value.labels, "semantic-fields")}</div>${area(`${key}-description`, "维度说明", value.description)}<div class="form-grid">${fields(`${key}-parents`, "父级维度标识", value.parents, "semantic-dimensions")}${select(
        `${key}-scope`,
        "身份作用域",
        [
          ["global", "全局唯一"],
          ["parent", "父级内唯一"],
          ["period", "时段内唯一"],
        ],
        value.identity_scope || "global",
      )}${fieldInput(`${key}-order`, "维度排序字段（可选）", value.order_field)}</div><details class="semantic-advanced"><summary>候选来源与历史身份映射</summary><p class="hint">候选来源需先配置 V2 语义模型，可选择当前来源。候选键与身份键数量相同、顺序对应。</p>${select(`${key}-candidate`, "候选来源", [["", "不配置候选来源"], ...sources], candidate.object || "")}<div data-candidate-fields></div><div class="form-grid">${fields(`${key}-candidate-fields`, "候选身份键", candidate.fields, `${key}-candidate-options`)}${fields(`${key}-candidate-labels`, "候选显示字段", candidate.labels, `${key}-candidate-options`)}${input(`${key}-candidate-order`, "候选排序字段", candidate.order_field, `list="${key}-candidate-options"`)}${fields(`${key}-legacy`, "已审核的历史实体标识", value.legacy_entities, "", "仅填写已人工确认等价的历史身份标识。")}</div></details>`;
    } else if (kind === "measures") {
      content = `${identity}<div class="form-grid">${fieldInput(`${key}-field`, "指标值字段", value.field)}${select(`${key}-operation`, "计算方式", measureOperations, value.operation || "identity")}</div><div data-weight>${fieldInput(`${key}-weight`, "权重字段（加权平均必填）", value.weight_field)}</div>${area(`${key}-description`, "指标业务口径", value.description, "说明指标含义、分母和适用条件；计算公式应由已审核字段或计算方式提供。")}<div class="form-grid">${input(`${key}-population`, "统计人群标识", value.population, "required", "例如 valid_students；同一指标和能力必须使用一致的人群标识。")}${fields(`${key}-required`, "指标所需维度标识", value.required_dimensions, "semantic-dimensions", "例如 exam, subject。这是指标语义所需维度，不等于必须选择一个维度值。")}</div>`;
    } else {
      content = `${identity}<div class="form-grid">${fields(`${key}-measures`, "支持的指标标识", value.measures, "semantic-measures")}${input(`${key}-population`, "能力统计人群标识", value.population, "required", "必须与所有引用指标的统计人群一致。")}</div><div class="form-item"><span id="${key}-operations-label" class="semantic-label">支持的操作</span><div class="semantic-modes" role="group" aria-labelledby="${key}-operations-label">${[
        ["project", "直接展示"],
        ["aggregate", "聚合"],
        ["rank", "排名"],
      ]
        .map(
          ([mode, name]) =>
            `<label class="check"><input type="checkbox" data-semantic-operation="${mode}" ${(value.operations || []).includes(mode) ? "checked" : ""}>${name}</label>`,
        )
        .join(
          "",
        )}</div></div><details class="semantic-advanced"><summary>预计算排名复用范围</summary><p class="hint">仅在排名指标、分区和统计人群完全匹配时复用。没有预计算排名可留空。</p><div class="form-grid">${fieldInput(`${key}-rank-field`, "预计算排名字段", value.rank_field)}${input(`${key}-rank-measure`, "排名指标标识", value.rank_measure, 'list="semantic-measures"')}${fields(`${key}-rank-partition`, "排名分区维度标识", value.rank_partition, "semantic-dimensions")}${select(
        `${key}-rank-direction`,
        "排名方向",
        [
          ["desc", "从高到低"],
          ["asc", "从低到高"],
        ],
        value.rank_direction || "desc",
      )}</div></details>`;
    }
    row.innerHTML = `<legend>${label}</legend><div class="semantic-section-head"><strong data-row-title>${esc(value.label || value.id || `新${label}`)}</strong><button type="button" class="quiet mini danger" data-semantic-remove>删除${label}</button></div>${content}`;
    groups[kind].set(key, { row, original: clone(value) });
    const container = root.querySelector(`[data-semantic-rows="${kind}"]`);
    container.querySelector("[data-semantic-empty]")?.remove();
    container.append(row);
    row
      .querySelector("[data-semantic-remove]")
      .addEventListener("click", () => {
        groups[kind].delete(key);
        row.remove();
        refresh();
        root.querySelector(`[data-semantic-add="${kind}"]`).focus();
      });
    if (kind === "dimensions") {
      const update = () => {
        const name = get(`${key}-candidate`);
        // A catalog can intentionally expose fewer fields than the SDK source.
        const available =
          name === obj.name
            ? arr("semantic-columns")
            : objects.find((o) => o.name === name)?.properties?.semanticModel
                ?.columns || [];
        row.querySelector("[data-candidate-fields]").innerHTML = list(
          `${key}-candidate-options`,
          available,
        );
      };
      row.querySelector(`#${key}-candidate`).addEventListener("change", update);
      groups.dimensions.get(key).updateCandidates = update;
      update();
    }
    if (kind === "measures") {
      const update = () => {
        const weighted = get(`${key}-operation`) === "weighted_mean";
        row.querySelector("[data-weight]").hidden = !weighted;
        row.querySelector(`#${key}-weight`).disabled = !weighted;
      };
      row.querySelector(`#${key}-operation`).addEventListener("change", update);
      update();
    }
    refresh();
    return row;
  }
  for (const kind of Object.keys(groups))
    for (const value of base[kind] || []) add(kind, value);
  refresh();
  for (const button of root.querySelectorAll("[data-semantic-add]"))
    button.addEventListener("click", () =>
      add(button.dataset.semanticAdd).querySelector("input").focus(),
    );
  function fail(id, message) {
    root.querySelector("#semantic-field-error")?.remove();
    for (const old of root.querySelectorAll(
      '[aria-describedby="semantic-field-error"]',
    )) {
      old.removeAttribute("aria-invalid");
      old.removeAttribute("aria-describedby");
    }
    const field = root.querySelector(`#${id}`);
    field.setAttribute("aria-invalid", "true");
    field.setAttribute("aria-describedby", "semantic-field-error");
    const error = document.createElement("p");
    error.id = "semantic-field-error";
    error.className = "semantic-field-error";
    error.textContent = message;
    field.parentElement.append(error);
    throw new Error(message);
  }
  function read(validate = true) {
    if (validate) {
      if (!arr("semantic-columns").length)
        fail("semantic-columns", "请至少声明一个输出字段。");
      if (!arr("semantic-grain").length)
        fail("semantic-grain", "请填写至少一个已定义的维度标识作为数据粒度。");
      for (const [key] of groups.measures) {
        if (
          get(`${key}-operation`) === "weighted_mean" &&
          !get(`${key}-weight`)
        )
          fail(
            `${key}-weight`,
            `指标“${get(`${key}-label`) || get(`${key}-id`)}”使用加权平均，请填写权重字段。`,
          );
      }
    }
    const dimensions = [...groups.dimensions].map(([k, { original }]) => {
      const candidate = get(`${k}-candidate`);
      const candidateFields = arr(`${k}-candidate-fields`),
        labels = arr(`${k}-candidate-labels`),
        order = optional(get(`${k}-candidate-order`));
      if (!candidate && (candidateFields.length || labels.length || order))
        throw new Error(
          "填写候选字段后请选择候选来源；取消来源时请同时清空候选字段。",
        );
      return {
        ...original,
        id: get(`${k}-id`),
        label: get(`${k}-label`),
        fields: arr(`${k}-fields`),
        labels: arr(`${k}-labels`),
        description: get(`${k}-description`),
        parents: arr(`${k}-parents`),
        identity_scope: get(`${k}-scope`),
        order_field: optional(get(`${k}-order`)),
        legacy_entities: arr(`${k}-legacy`),
        candidate_source: candidate
          ? {
              ...original.candidate_source,
              object: candidate,
              fields: candidateFields,
              labels,
              order_field: order,
            }
          : null,
      };
    });
    const measures = [...groups.measures].map(([k, { original }]) => ({
      ...original,
      id: get(`${k}-id`),
      label: get(`${k}-label`),
      field: get(`${k}-field`),
      description: get(`${k}-description`),
      operation: get(`${k}-operation`),
      weight_field:
        get(`${k}-operation`) === "weighted_mean"
          ? optional(get(`${k}-weight`))
          : null,
      population: get(`${k}-population`),
      required_dimensions: arr(`${k}-required`),
    }));
    const capabilities = [...groups.capabilities].map(
      ([k, { row, original }]) => ({
        ...original,
        id: get(`${k}-id`),
        measures: arr(`${k}-measures`),
        population: get(`${k}-population`),
        operations: [
          ...row.querySelectorAll("[data-semantic-operation]:checked"),
        ].map((el) => el.dataset.semanticOperation),
        rank_field: optional(get(`${k}-rank-field`)),
        rank_measure: optional(get(`${k}-rank-measure`)),
        rank_partition: arr(`${k}-rank-partition`),
        rank_direction: get(`${k}-rank-direction`),
      }),
    );
    return {
      ...base,
      schema_version: 2,
      object: obj.name,
      columns: arr("semantic-columns"),
      description: get("semantic-description"),
      grain: arr("semantic-grain"),
      dimensions,
      measures,
      capabilities,
    };
  }
  function update() {
    refresh();
    for (const { updateCandidates } of groups.dimensions.values())
      updateCandidates?.();
    for (const rows of Object.values(groups))
      for (const [key, { row }] of rows) {
        const label =
          row.querySelector(`#${key}-label`)?.value.trim() ||
          get(`${key}-id`) ||
          "未命名";
        row.querySelector("[data-row-title]").textContent = label;
        row
          .querySelector("[data-semantic-remove]")
          .setAttribute("aria-label", `删除 ${label}`);
      }
    try {
      root.querySelector("[data-semantic-json]").textContent = JSON.stringify(
        read(false),
        null,
        2,
      );
    } catch (error) {
      root.querySelector("[data-semantic-json]").textContent = error.message;
    }
  }
  root.addEventListener("input", () => {
    root.querySelector("#semantic-field-error")?.remove();
    for (const field of root.querySelectorAll(
      '[aria-describedby="semantic-field-error"]',
    )) {
      field.removeAttribute("aria-invalid");
      field.removeAttribute("aria-describedby");
    }
    update();
  });
  root.addEventListener("change", update);
  root.addEventListener("click", update);
  update();
  root.querySelector("#semantic-description").focus();
  return { read };
}

export function renderSemanticSummary(obj) {
  const model = obj.properties?.semanticModel;
  return `<section class="semantic-summary" aria-label="V2 语义配置"><div class="semantic-section-head"><div><h4>V2 语义模型 <span class="badge ${model ? "blue" : ""}">${model ? "已配置" : "未配置"}</span></h4><p class="hint">${model ? `${model.dimensions?.length || 0} 个维度 · ${model.measures?.length || 0} 个指标 · ${model.capabilities?.length || 0} 项能力` : "定义维度身份、指标计算口径和分析能力。"}</p></div><div class="row"><button type="button" class="mini primary" data-action="edit-semantic-model" data-name="${esc(obj.name)}">${model ? "编辑 V2 配置" : "配置 V2 语义"}</button>${model ? `<button type="button" class="quiet mini danger" data-action="delete-semantic-model" data-name="${esc(obj.name)}">移除 V2 配置</button>` : ""}</div></div></section>`;
}
