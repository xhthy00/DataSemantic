import { parseRelationCondition } from "./relation-conditions.js";

export const graphMetrics = {
  width: 272,
  header: 48,
  row: 30,
  inset: 8,
  footer: 32,
  gapX: 220,
  gapY: 64,
  padding: 48,
};

export const cardinality = (joinType) =>
  ({
    ONE_TO_ONE: ["1", "1"],
    ONE_TO_MANY: ["1", "N"],
    MANY_TO_ONE: ["N", "1"],
    MANY_TO_MANY: ["N", "N"],
  })[joinType] || ["?", "?"];

export function layoutRelationGraph(
  models,
  relationships,
  expanded = new Set(),
) {
  const g = graphMetrics;
  const nodes = models.map((model, index) => ({
    model,
    index,
    neighbors: new Set(),
    relatedFields: new Set(),
    relations: new Set(),
  }));
  const byName = new Map(nodes.map((node) => [node.model.name, node]));
  const edges = [];
  const missing = [];
  relationships.forEach((relation, index) => {
    const [from, to] = (relation.models || []).map((name) => byName.get(name));
    if (!from || !to) {
      missing.push(index);
      return;
    }
    from.neighbors.add(to);
    to.neighbors.add(from);
    from.relations.add(index);
    to.relations.add(index);
    const pairs = parseRelationCondition(
      relation.condition,
      from.model.name,
      to.model.name,
    );
    (pairs?.length ? pairs : [null]).forEach((pair, pairIndex) => {
      if (pair) {
        from.relatedFields.add(pair.from);
        to.relatedFields.add(pair.to);
      }
      edges.push({
        relation,
        index,
        from,
        to,
        pair,
        fieldLevel: Boolean(
          pair &&
            from.model.columns.some((field) => field.name === pair.from) &&
            to.model.columns.some((field) => field.name === pair.to),
        ),
        pairIndex,
        pairCount: pairs?.length || 1,
      });
    });
  });
  nodes.forEach((node) => {
    const columns = node.model.columns || [];
    node.fields = columns.filter(
      (field, index) =>
        expanded.has(node.index) ||
        node.relatedFields.has(field.name) ||
        field.name === node.model.primaryKey ||
        index < 4,
    );
    node.hiddenCount = columns.length - node.fields.length;
    node.height =
      g.header +
      g.inset * 2 +
      Math.max(1, node.fields.length) * g.row +
      g.footer +
      2;
  });

  // Keep each connected group together, placing neighbors in successive columns.
  const pending = new Set(nodes.filter((node) => node.relations.size));
  let nextY = g.padding;
  let maxX = g.width + g.padding;
  while (pending.size) {
    const root = [...pending].sort(
      (a, b) => b.neighbors.size - a.neighbors.size || a.index - b.index,
    )[0];
    const levels = [[root, 0]];
    const visited = new Set([root]);
    const columns = [];
    for (let i = 0; i < levels.length; i++) {
      const [node, depth] = levels[i];
      pending.delete(node);
      let column = Math.min(depth, 3);
      // Spread large hubs across nearby columns instead of creating one very tall stack.
      if (column > 0 && (columns[column]?.length || 0) >= 4) {
        column = [1, 2, 3].sort(
          (a, b) => (columns[a]?.length || 0) - (columns[b]?.length || 0),
        )[0];
      }
      (columns[column] ||= []).push(node);
      node.column = column;
      node.railY = nextY;
      for (const neighbor of node.neighbors) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          levels.push([neighbor, depth + 1]);
        }
      }
    }
    const heights = columns.map(
      (column) =>
        column.reduce((height, node) => height + node.height, 0) +
        (column.length - 1) * g.gapY,
    );
    const height = Math.max(...heights);
    columns.forEach((column, index) => {
      let y = nextY + 64;
      column.forEach((node) => {
        node.x = g.padding + index * (g.width + g.gapX);
        node.y = y;
        y += node.height + g.gapY;
        maxX = Math.max(maxX, node.x + g.width);
      });
    });
    nextY += height + g.gapY + 64;
  }
  const isolated = nodes.filter((node) => !node.relations.size);
  const count = Math.min(3, Math.max(1, Math.ceil(Math.sqrt(isolated.length))));
  for (let offset = 0; offset < isolated.length; offset += count) {
    const row = isolated.slice(offset, offset + count);
    row.forEach((node, column) => {
      node.x = g.padding + column * (g.width + g.gapX);
      node.y = nextY;
      node.column = column;
      maxX = Math.max(maxX, node.x + g.width);
    });
    nextY += Math.max(...row.map((node) => node.height)) + g.gapY;
  }
  const rightMargin = edges.some((edge) => edge.from.column === edge.to.column)
    ? 280
    : g.padding;
  return {
    nodes,
    edges,
    missing,
    width: maxX + rightMargin,
    height: Math.max(260, nextY + g.padding - g.gapY),
  };
}

export function routeRelationEdge(edge, lane = 0) {
  const g = graphMetrics;
  const fieldY = (node, name) => {
    const index = node.fields.findIndex((field) => field.name === name);
    return (
      node.y +
      1 +
      (index < 0
        ? g.header / 2
        : g.header + g.inset + index * g.row + g.row / 2)
    );
  };
  const fromY = fieldY(edge.from, edge.pair?.from);
  const toY = fieldY(edge.to, edge.pair?.to);
  const offset = 28 + (lane % 6) * 14;
  let start, end, path, label;
  if (edge.from.column === edge.to.column) {
    start = { x: edge.from.x + g.width, y: fromY, direction: 1 };
    end = { x: edge.to.x + g.width, y: toY, direction: 1 };
    const channel = start.x + 90 + (lane % 5) * 12;
    if (edge.from === edge.to && fromY === toY) {
      path = `M ${start.x} ${start.y} C ${channel + 40} ${start.y - 65}, ${channel + 40} ${end.y + 65}, ${end.x} ${end.y}`;
      label = { x: channel, y: start.y + 35 };
    } else {
      path = `M ${start.x} ${start.y} H ${channel} V ${end.y} H ${end.x}`;
      label = { x: channel, y: (start.y + end.y) / 2 };
    }
  } else {
    const forward = edge.from.column < edge.to.column;
    start = {
      x: edge.from.x + (forward ? g.width : 0),
      y: fromY,
      direction: forward ? 1 : -1,
    };
    end = {
      x: edge.to.x + (forward ? 0 : g.width),
      y: toY,
      direction: forward ? -1 : 1,
    };
    if (Math.abs(edge.from.column - edge.to.column) === 1) {
      const channel = (start.x + end.x) / 2 + ((lane % 5) - 2) * 13;
      path = `M ${start.x} ${start.y} H ${channel} V ${end.y} H ${end.x}`;
      label = { x: channel, y: (start.y + end.y) / 2 };
    } else {
      const x1 = start.x + start.direction * offset;
      const x2 = end.x + end.direction * offset;
      const rail = edge.from.railY + 12 + (lane % 4) * 12;
      path = `M ${start.x} ${start.y} H ${x1} V ${rail} H ${x2} V ${end.y} H ${end.x}`;
      label = { x: (x1 + x2) / 2, y: rail };
    }
  }
  return { start, end, path, label };
}
