export const relationColumns = (model) =>
  (model?.columns || []).filter(
    (column) => column.name && !column.relationship,
  );

// Wren supports column equalities joined by AND. Preserve any other existing SQL.
export function parseRelationCondition(condition, from, to) {
  if (typeof condition !== "string") return condition == null ? [] : null;
  if (!condition?.trim()) return [];
  const tokenPattern =
    /\s*("(?:[^"]|"")*"|`(?:[^`]|``)*`|[A-Za-z_][A-Za-z0-9_]*|<>|!=|>=|<=|[=><().])/y;
  const tokens = [];
  let offset = 0;
  while (offset < condition.trimEnd().length) {
    tokenPattern.lastIndex = offset;
    const match = tokenPattern.exec(condition);
    if (!match) return null;
    tokens.push(match[1]);
    offset = tokenPattern.lastIndex;
  }
  let cursor = 0;
  const take = () => tokens[cursor++];
  const identifier = () => {
    const token = take();
    if (
      !token ||
      !/^(?:[A-Za-z_][A-Za-z0-9_]*|"(?:[^"]|"")*"|`(?:[^`]|``)*`)$/.test(token)
    )
      throw new Error("identifier");
    return /^["`]/.test(token)
      ? token.slice(1, -1).replaceAll(token[0].repeat(2), token[0])
      : token;
  };
  const field = () => {
    const model = identifier();
    if (take() !== ".") throw new Error("field");
    return [model, identifier()];
  };
  const term = () => {
    if (tokens[cursor] === "(") {
      take();
      const rows = expression();
      if (take() !== ")") throw new Error("parenthesis");
      return rows;
    }
    const left = field();
    const operator = take();
    if (operator !== "=") throw new Error("operator");
    const right = field();
    if (left[0] === from && right[0] === to)
      return [{ from: left[1], operator, to: right[1] }];
    if (left[0] === to && right[0] === from) {
      return [{ from: right[1], operator, to: left[1] }];
    }
    throw new Error("model");
  };
  const expression = () => {
    const rows = term();
    while (tokens[cursor]?.toUpperCase() === "AND") {
      take();
      rows.push(...term());
    }
    return rows;
  };
  try {
    const rows = expression();
    return cursor === tokens.length ? rows : null;
  } catch {
    return null;
  }
}

export function buildRelationCondition(rows, from, to, allModels) {
  if (!from || !to || from === to) throw new Error("请选择两个不同的模型。");
  const fields = [from, to].map((name) =>
    relationColumns(allModels.find((model) => model.name === name)).map(
      (column) => column.name,
    ),
  );
  if (!rows.length) throw new Error("请添加至少一条关联条件。");
  const seen = new Set();
  const quote = (name) => `"${name.replaceAll('"', '""')}"`;
  return rows
    .map((row, index) => {
      if (!fields[0].includes(row.from) || !fields[1].includes(row.to))
        throw new Error(`请为第 ${index + 1} 条条件选择来源字段和目标字段。`);
      if (row.operator !== "=")
        throw new Error("关联条件仅支持字段之间的等值比较。");
      const key = JSON.stringify([row.from, row.operator, row.to]);
      if (seen.has(key))
        throw new Error(`第 ${index + 1} 条关联条件重复，请删除重复条件。`);
      seen.add(key);
      return `${quote(from)}.${quote(row.from)} ${row.operator} ${quote(to)}.${quote(row.to)}`;
    })
    .join(" AND ");
}
