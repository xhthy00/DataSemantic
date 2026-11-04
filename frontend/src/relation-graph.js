import {
  cardinality,
  graphMetrics,
  layoutRelationGraph,
  routeRelationEdge,
} from "./relation-graph-layout.js";

const escape = (value = "") =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const tableIcon =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10"/></svg>';

export function mountRelationGraph(root, models, relationships, onEdit) {
  const expanded = new Set();
  let layout;
  let zoom = 1;
  let selected = null;
  let initialized = false;
  let drag = null;
  const hint = relationships.length
    ? "连线连接关联字段；点击连线或标签查看详情。拖动画布空白处或滚动可移动视图。"
    : "尚未配置关联。添加关联并保存后，这里将显示对应字段之间的连线。";
  root.innerHTML = `<div class="relation-graph-toolbar"><div class="relation-graph-summary"><strong>${models.length} 个模型</strong><span>${relationships.length} 条关联</span><span class="muted">1 表示一 · N 表示多</span></div><div class="relation-graph-tools"><label class="sr-only" for="graph-relation-select">定位关联</label><select id="graph-relation-select"><option value="">全部关联</option>${relationships.map((relation, i) => `<option value="${i}">${escape(relation.name)}</option>`).join("")}</select><div class="relation-graph-zoom"><button type="button" data-graph-action="out" aria-label="缩小画布">−</button><output aria-label="画布缩放比例">100%</output><button type="button" data-graph-action="in" aria-label="放大画布">+</button></div><button type="button" data-graph-action="fit">适应宽度</button><button type="button" data-graph-action="reset">100%</button></div></div><p class="relation-graph-hint">${hint}</p><div class="relation-graph-viewport" tabindex="0" role="region" aria-label="模型关联画布"><div class="relation-graph-space"><div class="relation-graph-stage"></div></div></div><div class="relation-graph-detail" aria-live="polite"></div>`;
  const viewport = root.querySelector(".relation-graph-viewport");
  const space = root.querySelector(".relation-graph-space");
  const stage = root.querySelector(".relation-graph-stage");
  const detail = root.querySelector(".relation-graph-detail");
  const picker = root.querySelector("#graph-relation-select");

  function setZoom(value, center = true) {
    const old = zoom;
    const x = (viewport.scrollLeft + viewport.clientWidth / 2) / old;
    const y = (viewport.scrollTop + viewport.clientHeight / 2) / old;
    zoom = Math.max(0.35, Math.min(1.5, value));
    stage.style.transform = `scale(${zoom})`;
    space.style.width = `${Math.ceil(layout.width * zoom)}px`;
    space.style.height = `${Math.ceil(layout.height * zoom)}px`;
    root.querySelector("output").textContent = `${Math.round(zoom * 100)}%`;
    root.querySelector('[data-graph-action="out"]').disabled = zoom <= 0.35;
    root.querySelector('[data-graph-action="in"]').disabled = zoom >= 1.5;
    if (center) {
      viewport.scrollLeft = x * zoom - viewport.clientWidth / 2;
      viewport.scrollTop = y * zoom - viewport.clientHeight / 2;
    }
  }
  function fit() {
    setZoom(Math.min(1, viewport.clientWidth / layout.width), false);
    viewport.scrollLeft = 0;
    viewport.scrollTop = 0;
  }
  function selectRelation(index, locate = false) {
    selected = index;
    picker.value = index === null ? "" : String(index);
    const relation = relationships[index];
    root.classList.toggle("has-relation-selection", Boolean(relation));
    stage.querySelectorAll("[data-graph-relation]").forEach((element) => {
      const active = Number(element.dataset.graphRelation) === index;
      element.classList.toggle("is-selected", active);
      if (element.tagName === "BUTTON")
        element.setAttribute("aria-pressed", String(active));
    });
    stage.querySelectorAll("[data-graph-node]").forEach((element) => {
      const node = layout.nodes[Number(element.dataset.graphNode)];
      element.classList.toggle("is-selected", node.relations.has(index));
    });
    stage.querySelectorAll("[data-graph-field]").forEach((element) => {
      const node =
        layout.nodes[
          Number(element.closest("[data-graph-node]").dataset.graphNode)
        ];
      const active = layout.edges.some(
        (edge) =>
          edge.index === index &&
          edge.pair &&
          ((edge.from === node &&
            edge.pair.from === element.dataset.graphField) ||
            (edge.to === node && edge.pair.to === element.dataset.graphField)),
      );
      element.classList.toggle("is-selected", active);
    });
    if (!relation) {
      detail.innerHTML =
        '<span class="muted">选择一条关联，查看字段条件与关联基数。</span>';
      return;
    }
    const ratio = cardinality(relation.joinType).join(" : ");
    detail.innerHTML = `<div class="relation-graph-detail-heading"><strong>${escape(relation.name)}</strong><span class="badge blue">${ratio}</span><span class="small muted">${escape(relation.models?.join(" → "))}</span><div class="relation-graph-detail-actions"><button type="button" data-graph-action="edit">编辑关联</button><button type="button" class="quiet" data-graph-action="clear">取消选择</button></div></div><code>${escape(relation.condition)}</code>`;
    if (locate) {
      const related = layout.nodes.filter((node) => node.relations.has(index));
      if (related.length) {
        const left = Math.min(...related.map((node) => node.x));
        const right = Math.max(
          ...related.map((node) => node.x + graphMetrics.width),
        );
        const top = Math.min(...related.map((node) => node.y));
        viewport.scrollLeft =
          ((left + right) / 2) * zoom - viewport.clientWidth / 2;
        viewport.scrollTop = Math.max(0, top * zoom - 36);
      }
    }
  }
  function draw() {
    layout = layoutRelationGraph(models, relationships, expanded);
    stage.style.width = `${layout.width}px`;
    stage.style.height = `${layout.height}px`;
    stage.innerHTML = `<svg class="relation-graph-lines" width="${layout.width}" height="${layout.height}" aria-hidden="true">${layout.edges
      .map((edge, lane) => {
        const route = routeRelationEdge(edge, lane);
        const [from, to] = cardinality(edge.relation.joinType);
        return `<g data-graph-relation="${edge.index}" class="relation-graph-edge ${edge.fieldLevel ? "" : "is-model-level"}"><path class="relation-graph-edge-hit" d="${route.path}"/><path class="relation-graph-edge-line" d="${route.path}"/>${[
          [route.start, from],
          [route.end, to],
        ]
          .map(
            ([point, value]) =>
              `<circle cx="${point.x}" cy="${point.y}" r="4"/><text x="${point.x + point.direction * 13}" y="${point.y - 9}" text-anchor="middle">${value}</text>`,
          )
          .join("")}</g>`;
      })
      .join(
        "",
      )}</svg>${layout.nodes.map((node) => `<section class="relation-graph-node ${node.relations.size ? "is-connected" : ""}" data-graph-node="${node.index}" aria-label="模型 ${escape(node.model.name)}"><div class="relation-graph-node-title" title="${escape(node.model.name)}">${tableIcon}<strong>${escape(node.model.name)}</strong><span class="relation-graph-node-count">${node.relations.size}</span></div><div class="relation-graph-node-fields">${node.fields.map((field) => `<div class="relation-graph-field ${node.relatedFields.has(field.name) ? "is-linked" : ""}" data-graph-field="${escape(field.name)}" title="${escape([field.name, field.type, field.properties?.description].filter(Boolean).join(" · "))}"><span class="relation-graph-field-kind" aria-hidden="true">${field.relationship ? "↗" : "#"}</span><span class="relation-graph-field-name">${escape(field.name)}</span>${node.model.primaryKey === field.name ? '<span class="relation-graph-pk">主键</span>' : ""}<span class="relation-graph-field-type">${escape(field.relationship ? "导航" : field.type)}</span></div>`).join("") || '<div class="relation-graph-field muted">暂无字段</div>'}</div><div class="relation-graph-node-footer">${node.hiddenCount || expanded.has(node.index) ? `<button type="button" data-graph-expand="${node.index}" aria-expanded="${expanded.has(node.index)}">${node.hiddenCount ? `展开其余 ${node.hiddenCount} 个字段` : "收起字段"}</button>` : `<span>${node.model.columns.length} 个字段</span>`}<span>${node.relations.size ? `${node.relations.size} 条关联` : "未关联"}</span></div></section>`).join("")}${layout.edges.map((edge, lane) => `<button type="button" class="relation-graph-label ${edge.fieldLevel ? "" : "is-model-level"}" data-graph-relation="${edge.index}" data-graph-edge="${lane}" aria-pressed="false" aria-label="查看关联 ${escape(edge.relation.name)}，${cardinality(edge.relation.joinType).join(" 对 ")}${edge.fieldLevel ? `，${escape(edge.pair.from)} 等于 ${escape(edge.pair.to)}` : "，模型级连线"}" title="${escape(edge.relation.name)} · ${escape(edge.relation.condition)}"><span>${escape(edge.relation.name)}${edge.pairCount > 1 ? ` (${edge.pairIndex + 1}/${edge.pairCount})` : ""}</span><b>${cardinality(edge.relation.joinType).join(":")}</b></button>`).join("")}`;
    stage.querySelectorAll("[data-graph-node]").forEach((element) => {
      const node = layout.nodes[Number(element.dataset.graphNode)];
      Object.assign(element.style, {
        left: `${node.x}px`,
        top: `${node.y}px`,
        width: `${graphMetrics.width}px`,
        height: `${node.height}px`,
      });
    });
    stage.querySelectorAll("[data-graph-edge]").forEach((element) => {
      const lane = Number(element.dataset.graphEdge);
      const { label } = routeRelationEdge(layout.edges[lane], lane);
      element.style.left = `${label.x}px`;
      element.style.top = `${label.y}px`;
    });
    root.querySelector(".relation-graph-hint").textContent = hint;
    if (layout.missing.length) {
      root.querySelector(".relation-graph-hint").textContent =
        `${layout.missing.length} 条关联引用了不存在的模型，无法绘制；请在下方关联明细中修正。`;
    } else if (layout.edges.some((edge) => !edge.fieldLevel)) {
      root.querySelector(".relation-graph-hint").textContent +=
        " 虚线表示条件未能定位到具体字段，可点击查看原始条件。";
    }
    if (!initialized) {
      setZoom(
        Math.max(0.65, Math.min(1, viewport.clientWidth / layout.width)),
        false,
      );
      initialized = true;
    } else setZoom(zoom, false);
    selectRelation(selected);
  }
  const click = (event) => {
    if (event.target.closest("[data-graph-expand]")) {
      const index = Number(
        event.target.closest("[data-graph-expand]").dataset.graphExpand,
      );
      if (expanded.has(index)) expanded.delete(index);
      else expanded.add(index);
      draw();
      stage
        .querySelector(`[data-graph-expand="${index}"]`)
        ?.focus({ preventScroll: true });
      return;
    }
    const edge = event.target.closest("[data-graph-relation]");
    if (edge) {
      selectRelation(Number(edge.dataset.graphRelation));
      return;
    }
    const action = event.target.closest("[data-graph-action]")?.dataset
      .graphAction;
    if (action === "in") setZoom(zoom + 0.1);
    if (action === "out") setZoom(zoom - 0.1);
    if (action === "reset") setZoom(1);
    if (action === "fit") fit();
    if (action === "clear") selectRelation(null);
    if (action === "edit" && selected !== null) onEdit(selected);
  };
  root.addEventListener("click", click);
  picker.addEventListener("change", () =>
    selectRelation(picker.value === "" ? null : Number(picker.value), true),
  );
  viewport.addEventListener("pointerdown", (event) => {
    if (
      event.button !== 0 ||
      event.pointerType === "touch" ||
      event.target.closest(
        "button, .relation-graph-node, [data-graph-relation]",
      )
    )
      return;
    drag = {
      x: event.clientX,
      y: event.clientY,
      left: viewport.scrollLeft,
      top: viewport.scrollTop,
    };
    viewport.setPointerCapture(event.pointerId);
    viewport.classList.add("is-panning");
  });
  viewport.addEventListener("pointermove", (event) => {
    if (!drag) return;
    viewport.scrollLeft = drag.left - (event.clientX - drag.x);
    viewport.scrollTop = drag.top - (event.clientY - drag.y);
  });
  const stop = () => {
    drag = null;
    viewport.classList.remove("is-panning");
  };
  viewport.addEventListener("pointerup", stop);
  viewport.addEventListener("pointercancel", stop);
  viewport.addEventListener("lostpointercapture", stop);
  draw();
  return () => {
    root.removeEventListener("click", click);
  };
}
