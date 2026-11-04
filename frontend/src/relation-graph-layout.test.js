import assert from "node:assert/strict";
import test from "node:test";
import {
  cardinality,
  graphMetrics,
  layoutRelationGraph,
  routeRelationEdge,
} from "./relation-graph-layout.js";

const model = (name, count = 8) => ({
  name,
  primaryKey: "id",
  columns: [
    { name: "id", type: "integer" },
    ...Array.from({ length: count }, (_, i) => ({
      name: `field_${i}`,
      type: "integer",
    })),
  ],
});
const relation = (from, to, condition = `${from}.field_7 = ${to}.id`) => ({
  name: `${from}_${to}`,
  models: [from, to],
  joinType: "MANY_TO_ONE",
  condition,
});

test("draws only configured relationships and reports missing models", () => {
  const models = [model("a"), model("b")];
  const empty = layoutRelationGraph(models, []);
  assert.equal(empty.edges.length, 0);
  const layout = layoutRelationGraph(models, [
    relation("a", "b"),
    relation("b", "missing"),
  ]);
  assert.equal(layout.edges.length, 1);
  assert.deepEqual(layout.missing, [1]);
  assert.deepEqual(cardinality("MANY_TO_ONE"), ["N", "1"]);
  assert.deepEqual(cardinality("ONE_TO_MANY"), ["1", "N"]);
  assert.deepEqual(cardinality("ONE_TO_ONE"), ["1", "1"]);
  assert.deepEqual(cardinality("MANY_TO_MANY"), ["N", "N"]);
});

test("composite keys connect each field and stay visible when cards are collapsed", () => {
  const layout = layoutRelationGraph(
    [model("a"), model("b")],
    [relation("a", "b", '"a"."field_7" = "b"."id" AND b.field_6 = a.field_5')],
  );
  assert.equal(layout.edges.length, 2);
  assert.deepEqual(
    layout.edges.map((edge) => edge.pair),
    [
      { from: "field_7", operator: "=", to: "id" },
      { from: "field_5", operator: "=", to: "field_6" },
    ],
  );
  for (const edge of layout.edges) {
    assert.ok(edge.fieldLevel);
    const route = routeRelationEdge(edge);
    const fromRow = edge.from.fields.findIndex(
      (field) => field.name === edge.pair.from,
    );
    assert.equal(
      route.start.y,
      edge.from.y +
        1 +
        graphMetrics.header +
        graphMetrics.inset +
        fromRow * graphMetrics.row +
        graphMetrics.row / 2,
    );
    assert.ok(
      route.start.x === edge.from.x ||
        route.start.x === edge.from.x + graphMetrics.width,
    );
  }
});

test("complex conditions and stale field names use a model-level fallback", () => {
  const layout = layoutRelationGraph(
    [model("a"), model("b")],
    [
      relation("a", "b", "CAST(a.field_7 AS integer) = b.id"),
      relation("a", "b", "a.removed = b.id"),
    ],
  );
  assert.equal(layout.edges.length, 2);
  assert.ok(layout.edges.every((edge) => !edge.fieldLevel));
  assert.equal(layout.edges[0].pair, null);
  assert.equal(
    routeRelationEdge(layout.edges[0]).start.y,
    layout.edges[0].from.y + 1 + graphMetrics.header / 2,
  );
});

test("18 models with branches, cycles, reverse edges and isolated nodes stay within the canvas", () => {
  const models = Array.from({ length: 18 }, (_, i) =>
    model(`model_${i}`, i % 3 ? 8 : 15),
  );
  const relationships = Array.from({ length: 13 }, (_, i) =>
    relation(`model_${i}`, `model_${i + 1}`),
  );
  relationships.push(
    relation("model_0", "model_8"),
    relation("model_7", "model_3"),
    relation("model_8", "model_1"),
  );
  const before = JSON.stringify({ models, relationships });
  const layout = layoutRelationGraph(models, relationships);
  for (const node of layout.nodes) {
    assert.ok(node.x >= 0 && node.y >= 0);
    assert.ok(node.x + graphMetrics.width <= layout.width);
    assert.ok(node.y + node.height <= layout.height);
    for (const other of layout.nodes.filter(
      (value) => value.index > node.index,
    )) {
      assert.ok(
        node.x + graphMetrics.width <= other.x ||
          other.x + graphMetrics.width <= node.x ||
          node.y + node.height <= other.y ||
          other.y + other.height <= node.y,
      );
    }
  }
  for (const [lane, edge] of layout.edges.entries()) {
    const route = routeRelationEdge(edge, lane);
    for (const point of [route.start, route.end, route.label])
      assert.ok(
        Number.isFinite(point.x) &&
          Number.isFinite(point.y) &&
          point.x >= 0 &&
          point.x <= layout.width &&
          point.y >= 0 &&
          point.y <= layout.height,
      );
    assert.ok(!route.path.includes("NaN"));
  }
  assert.equal(JSON.stringify({ models, relationships }), before);
});

test("expanding fields updates the anchors without losing linked fields", () => {
  const models = [model("a", 25), model("b")];
  const rs = [relation("a", "b")];
  const collapsed = layoutRelationGraph(models, rs);
  const expanded = layoutRelationGraph(models, rs, new Set([0]));
  assert.equal(expanded.nodes[0].fields.length, 26);
  assert.ok(expanded.nodes[0].height > collapsed.nodes[0].height);
  assert.ok(
    collapsed.nodes[0].fields.some((field) => field.name === "field_7"),
  );
  assert.ok(
    routeRelationEdge(expanded.edges[0]).start.y !==
      routeRelationEdge(collapsed.edges[0]).start.y,
  );
});

test("a dense hub stays near the top and distributes its neighbors", () => {
  const models = Array.from({ length: 18 }, (_, i) => model(`model_${i}`));
  const rs = models
    .slice(1)
    .map((value) => relation(value.name, models[0].name));
  const layout = layoutRelationGraph(models, rs);
  assert.equal(layout.nodes[0].y, graphMetrics.padding + 64);
  assert.equal(
    new Set(layout.nodes.slice(1).map((node) => node.column)).size,
    3,
  );
  assert.ok(layout.height < 2200);
});

test("self references route outside the card instead of disappearing", () => {
  const layout = layoutRelationGraph(
    [model("a")],
    [relation("a", "a", "a.id = a.id")],
  );
  const route = routeRelationEdge(layout.edges[0]);
  assert.ok(route.path.includes(" C "));
  assert.ok(route.label.x > layout.nodes[0].x + graphMetrics.width);
  assert.ok(route.label.x < layout.width);
});
