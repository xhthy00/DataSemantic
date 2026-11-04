"""Build reviewable MDL from schema-only SQL. No statement is ever executed."""

import re

import sqlglot
from sqlglot import exp
from wren.type_mapping import parse_type

from .errors import ServiceError
from .modeling import IDENTIFIER

TYPE_CHOICES = [
    "boolean",
    "tinyint",
    "smallint",
    "integer",
    "bigint",
    "float",
    "double",
    "decimal(38, 9)",
    "varchar",
    "date",
    "time",
    "timestamp",
    "timestamptz",
    "json",
    "uuid",
    "bytea",
]


def invalid(message):
    raise ServiceError("INVALID_DDL", message, 422)


def logical_name(value, used, fallback):
    value = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") or fallback
    if value[0].isdigit():
        value = "_" + value
    name, index = value, 2
    # Wren and many SQL engines resolve logical names without case sensitivity.
    while name.lower() in used:
        name = f"{value}_{index}"
        index += 1
    used.add(name.lower())
    return name


def identifier(node, dialect):
    name = node.name
    return name.lower() if dialect == "postgres" and not node.args.get("quoted") else name


def table_key(table, dialect):
    return tuple(
        identifier(table.args[k], dialect) if table.args.get(k) else ""
        for k in ("catalog", "db", "this")
    )


def normalized_type(raw, dialect):
    canonical = parse_type(raw, dialect).lower()
    if canonical.startswith("array<") and canonical.endswith(">"):
        inner, warning = normalized_type(canonical[6:-1], "duckdb")
        return (f"{inner}[]" if inner else None), warning
    base = canonical.split("(", 1)[0].strip()
    aliases = {
        "serial": "integer",
        "smallserial": "smallint",
        "bigserial": "bigint",
        "int": "integer",
        "text": "varchar",
        "char": "varchar",
        "nchar": "varchar",
        "nvarchar": "varchar",
        "datetime": "timestamp",
        "jsonb": "json",
        "binary": "bytea",
        "varbinary": "bytea",
        "blob": "bytea",
        "utinyint": "smallint",
        "usmallint": "integer",
        "uint": "bigint",
        "ubigint": "decimal(20, 0)",
        "real": "float",
        "float4": "float",
    }
    if base in aliases:
        return aliases[base], None
    if base in {"enum", "set"}:
        return "varchar", f"{raw} 按字符串建模，请复核枚举含义。"
    if base in {
        "varchar",
        "tinyint",
        "smallint",
        "integer",
        "bigint",
        "boolean",
        "float",
        "double",
        "date",
        "time",
        "timestamp",
        "timestamptz",
        "json",
        "uuid",
        "bytea",
    }:
        return base, None
    if base in {"decimal", "numeric"}:
        return canonical, None
    return None, f"无法自动映射类型 {raw}，请选择语义类型或排除此字段。"


def resolve_table(tables, key, source=None):
    exact = [t for t in tables if tuple(t["key"]) == tuple(key)]
    if exact:
        return exact[0]
    candidates = [
        t
        for t in tables
        if t["key"][2] == key[2]
        and (not key[1] or t["key"][1] == key[1])
        and (not key[0] or t["key"][0] == key[0])
    ]
    if source and not key[1]:
        local = [t for t in candidates if t["key"][:2] == source["key"][:2]]
        if len(local) == 1:
            return local[0]
    return candidates[0] if len(candidates) == 1 else None


def prepare_preview(tables, warnings):
    """Shared naming and constraint handling for parsed DDL and live metadata."""
    used_models = set()
    for table in tables:
        available = {col["name"] for col in table["columns"]}
        constraint_columns = [*table["primary_key"]]
        for key in table["unique_keys"]:
            constraint_columns.extend(key)
        for fk in table["foreign_keys"]:
            constraint_columns.extend(fk["columns"])
        if set(constraint_columns) - available:
            invalid(f"{table['label']} 的主键、唯一约束或外键引用了未定义的本表字段。")
        table["logical_name"] = logical_name(table["key"][2], used_models, "model")
        used_columns = set()
        for col in table["columns"]:
            col["logical_name"] = logical_name(col["name"], used_columns, "column")
            col["primary_key"] = col["name"] in table["primary_key"]
            col["foreign_key"] = any(col["name"] in f["columns"] for f in table["foreign_keys"])
            if col["primary_key"]:
                col["nullable"] = False
        for fk in table["foreign_keys"]:
            target = resolve_table(tables, fk["target"], table)
            fk["target_id"] = target["id"] if target else None
    return {"tables": tables, "warnings": warnings, "type_choices": TYPE_CHOICES}


def parse_ddl(ddl, dialect):
    if len(ddl.encode()) > 500_000:
        invalid("DDL 文件不能超过 500 KB，请按业务域拆分表结构。")
    try:
        statements = [s for s in sqlglot.parse(ddl, read=dialect) if s is not None]
    except (sqlglot.errors.SqlglotError, ValueError, RecursionError):
        invalid("DDL 解析失败，请检查所选数据库类型和 SQL 语法，仅导入建表结构。")
    tables, warnings = [], []
    keys = set()

    def warn(message):
        if message not in warnings:
            warnings.append(message)

    def constraints(table, nodes):
        for node in nodes:
            if isinstance(node, exp.Constraint):
                constraints(table, node.expressions)
            elif isinstance(node, exp.PrimaryKey):
                table["primary_key"] = [identifier(c, dialect) for c in node.expressions]
            elif isinstance(node, exp.UniqueColumnConstraint):
                schema = node.this
                table["unique_keys"].append(
                    [
                        identifier(c.this if isinstance(c, exp.Column) else c, dialect)
                        for c in schema.expressions
                    ]
                )
            elif isinstance(node, exp.ForeignKey):
                add_reference(
                    table,
                    [identifier(c, dialect) for c in node.expressions],
                    node.args.get("reference"),
                )

    def add_reference(table, columns, reference):
        if not isinstance(reference, exp.Reference) or not isinstance(
            reference.this, (exp.Schema, exp.Table)
        ):
            warn(f"{table['label']}：跳过无法识别的外键，请在模型关联中复核。")
            return
        schema = reference.this
        target_table = schema.this if isinstance(schema, exp.Schema) else schema
        fk = {
            "columns": columns,
            "target": table_key(target_table, dialect),
            "target_columns": [identifier(c, dialect) for c in schema.expressions],
        }
        if fk not in table["foreign_keys"]:
            table["foreign_keys"].append(fk)

    for statement in statements:
        if isinstance(statement, exp.Create) and statement.args.get("kind") == "TABLE":
            schema = statement.this
            if (
                not isinstance(schema, exp.Schema)
                or statement.args.get("expression")
                or statement.args.get("clone")
            ):
                invalid("仅支持包含明确字段定义的 CREATE TABLE，不支持 AS SELECT、LIKE 或 CLONE。")
            key = table_key(schema.this, dialect)
            if key in keys:
                invalid(f"表 {'.'.join(k for k in key if k)} 重复定义，请仅保留最终建表结构。")
            keys.add(key)
            table = {
                "id": f"t{len(tables) + 1}",
                "key": key,
                "label": ".".join(k for k in key if k),
                "columns": [],
                "primary_key": [],
                "unique_keys": [],
                "foreign_keys": [],
                "description": "",
            }
            props = statement.args.get("properties")
            if props:
                for prop in props.expressions:
                    if isinstance(prop, exp.SchemaCommentProperty):
                        table["description"] = prop.this.name
            seen_columns = set()
            for node in schema.expressions:
                if not isinstance(node, exp.ColumnDef):
                    continue
                name = identifier(node.this, dialect)
                if name in seen_columns:
                    invalid(f"{table['label']} 的字段 {name} 重复定义。")
                seen_columns.add(name)
                if not isinstance(node.args.get("kind"), exp.DataType):
                    invalid(f"{table['label']}.{name} 缺少字段类型。")
                raw = node.args["kind"].sql(dialect=dialect)
                mapped, warning = normalized_type(raw, dialect)
                column = {
                    "id": name,
                    "name": name,
                    "raw_type": raw,
                    "type": mapped,
                    "nullable": True,
                    "description": "",
                    "warning": warning,
                }
                for constraint in node.args.get("constraints", []):
                    kind = constraint.args.get("kind")
                    if isinstance(kind, exp.PrimaryKeyColumnConstraint):
                        table["primary_key"].append(name)
                        column["nullable"] = False
                    elif isinstance(kind, exp.NotNullColumnConstraint):
                        column["nullable"] = False
                    elif isinstance(kind, exp.UniqueColumnConstraint):
                        table["unique_keys"].append([name])
                    elif isinstance(kind, exp.Reference):
                        add_reference(table, [name], kind)
                    elif isinstance(kind, exp.CommentColumnConstraint):
                        column["description"] = kind.this.name
                table["columns"].append(column)
            constraints(table, schema.expressions)
            if not 1 <= len(table["columns"]) <= 500:
                invalid(f"{table['label']} 需要 1～500 个字段。")
            tables.append(table)
            if len(tables) > 50:
                invalid("每次最多导入 50 张表，请按业务域拆分。")
        elif isinstance(statement, (exp.Comment, exp.Alter)):
            continue  # Resolve after all CREATE TABLE statements, including forward references.
        elif isinstance(statement, (exp.Set, exp.Use, exp.Drop, exp.Transaction, exp.Commit)) or (
            isinstance(statement, exp.Create)
            and statement.args.get("kind") in {"INDEX", "SEQUENCE", "SCHEMA", "TYPE", "DATABASE"}
        ):
            warn("已忽略索引、序列、数据库设置等非建模语句；导入过程不会执行 SQL。")
        else:
            invalid("请导出仅含表结构的 SQL。当前导入不支持数据 INSERT、查询、视图或其他语句。")
    if not tables:
        invalid("没有找到 CREATE TABLE，请粘贴或上传数据库导出的建表 DDL。")

    for statement in statements:
        if isinstance(statement, exp.Alter):
            table = resolve_table(tables, table_key(statement.this, dialect))
            if not table:
                warn("存在引用未导入表的 ALTER TABLE，已跳过。")
                continue
            for action in statement.args.get("actions", []):
                if isinstance(action, exp.AddConstraint):
                    constraints(table, action.expressions)
                else:
                    invalid(
                        "ALTER TABLE 仅支持 ADD 主键、唯一约束和外键，"
                        "请导出最终 CREATE TABLE 结构。"
                    )
        elif isinstance(statement, exp.Comment):
            node, kind = statement.this, statement.args.get("kind")
            parts = node.parts
            names = [identifier(p, dialect) for p in parts]
            column = names.pop() if kind == "COLUMN" else None
            if kind not in {"COLUMN", "TABLE"}:
                continue
            key = tuple(([""] * 3 + names)[-3:])
            table = resolve_table(tables, key)
            value = statement.args.get("expression")
            if table and isinstance(value, exp.Literal):
                if column is None:
                    table["description"] = value.name
                else:
                    for col in table["columns"]:
                        if col["name"] == column:
                            col["description"] = value.name
    return prepare_preview(tables, warnings)


def build_manifest(preview, selections, catalog, schema, relationships=True):
    for value in (catalog, schema):
        if not IDENTIFIER.fullmatch(value):
            invalid("语义 catalog 和 schema 必须使用字母、数字和下划线，且不能以数字开头。")
    sources = {t["id"]: t for t in preview["tables"]}
    models, included = [], {}
    warnings = list(preview["warnings"])
    if not selections:
        invalid("请至少选择一张表和一个字段。")
    for selection in selections:
        tid = selection.table_id
        if tid not in sources or tid in included:
            invalid("表选择无效或重复，请重新解析 DDL。")
        source = sources[tid]
        columns = {c["id"]: c for c in source["columns"]}
        if not selection.columns or len(set(selection.columns)) != len(selection.columns):
            invalid(f"{source['label']} 请至少选择一个字段，且不能重复。")
        if set(selection.columns) - columns.keys() or set(selection.types) - set(selection.columns):
            invalid("字段选择或类型设置无效，请重新解析 DDL。")
        model = {
            "name": source["logical_name"],
            "tableReference": {
                key: value
                for key, value in zip(("catalog", "schema", "table"), source["key"], strict=True)
                if value
            },
            "columns": [],
            "properties": {"displayName": source["key"][2], "description": source["description"]},
        }
        for cid in selection.columns:
            col = columns[cid]
            chosen = selection.types.get(cid, col["type"])
            if not chosen or chosen not in TYPE_CHOICES + [col["type"]]:
                invalid(f"{source['label']}.{cid} 需要选择支持的语义类型。")
            field = {
                "name": col["logical_name"],
                "type": chosen,
                "notNull": not col["nullable"],
                "expression": '"' + col["name"].replace('"', '""') + '"',
                "properties": {"displayName": col["name"], "description": col["description"]},
            }
            model["columns"].append(field)
            if col["warning"]:
                note = (
                    col["warning"]
                    if col["type"]
                    else f"源类型 {col['raw_type']} 已手动映射为 {chosen}。"
                )
                warnings.append(f"{source['label']}.{cid}：{note}")
        pk = source["primary_key"]
        if len(pk) == 1 and pk[0] in selection.columns:
            model["primaryKey"] = columns[pk[0]]["logical_name"]
        elif pk:
            warnings.append(
                f"{source['label']}：复合主键或主键字段未全部选中，未设置 MDL 单字段主键。"
            )
        included[tid] = (source, model, set(selection.columns))
        models.append(model)
    relations = []
    used_relations = set()
    if relationships:
        for source, model, chosen in included.values():
            for fk in source["foreign_keys"]:
                target = included.get(fk["target_id"])
                label = f"{source['label']}({', '.join(fk['columns'])})"
                if not target or not set(fk["columns"]).issubset(chosen):
                    warnings.append(f"{label}：外键目标表或关联字段未选中，已跳过关联。")
                    continue
                target_source, target_model, target_chosen = target
                target_cols = fk["target_columns"] or target_source["primary_key"]
                if (
                    not target_cols
                    or len(fk["columns"]) != len(target_cols)
                    or not set(target_cols).issubset(target_chosen)
                    or source["id"] == target_source["id"]
                ):
                    warnings.append(f"{label}：自关联或目标字段不完整，请在模型关联中手动配置。")
                    continue
                source_cols = {c["id"]: c["logical_name"] for c in source["columns"]}
                target_names = {c["id"]: c["logical_name"] for c in target_source["columns"]}
                relation_name = logical_name(
                    f"{model['name']}_{'_'.join(fk['columns'])}_{target_model['name']}",
                    used_relations,
                    "relation",
                )
                condition = " AND ".join(
                    f'"{model["name"]}"."{source_cols[a]}" = '
                    f'"{target_model["name"]}"."{target_names[b]}"'
                    for a, b in zip(fk["columns"], target_cols, strict=True)
                )
                unique = any(
                    set(fk["columns"]) == set(key)
                    for key in [source["primary_key"], *source["unique_keys"]]
                )
                relations.append(
                    {
                        "name": relation_name,
                        "models": [model["name"], target_model["name"]],
                        "joinType": "ONE_TO_ONE" if unique else "MANY_TO_ONE",
                        "condition": condition,
                    }
                )
                used = {c["name"].lower() for c in model["columns"]}
                nav_name = logical_name(f"{target_model['name']}_ref", used, "related_model")
                model["columns"].append(
                    {"name": nav_name, "type": target_model["name"], "relationship": relation_name}
                )
    if any(len(m["columns"]) > 500 for m in models):
        invalid("加入关联导航字段后超过每表 500 个字段上限，请减少字段或关闭自动关联。")
    return {
        "catalog": catalog,
        "schema": schema,
        "models": models,
        "relationships": relations,
        "views": [],
    }, list(dict.fromkeys(warnings))
