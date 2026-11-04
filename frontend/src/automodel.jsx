import { useRef, useState } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Collapse,
  Form,
  Input,
  Modal,
  Select,
  Segmented,
  Space,
  Steps,
  Table,
  Tag,
  Typography,
  Upload,
} from "antd";
import { FileTextOutlined, UploadOutlined } from "@ant-design/icons";
import { DatabaseSource } from "./database-source.jsx";

function example(dialect) {
  const ddl = `CREATE TABLE schools (
  id BIGINT PRIMARY KEY,
  name VARCHAR(100) NOT NULL
);

CREATE TABLE students (
  id BIGINT PRIMARY KEY,
  school_id BIGINT NOT NULL,
  name VARCHAR(100) NOT NULL,
  enrolled_at DATE,
  FOREIGN KEY (school_id) REFERENCES schools(id)
);

CREATE TABLE subject_scores (
  id BIGINT PRIMARY KEY,
  student_id BIGINT NOT NULL,
  subject VARCHAR(50) NOT NULL,
  score DECIMAL(5, 2),
  is_absent BOOLEAN,
  FOREIGN KEY (student_id) REFERENCES students(id)
);`;
  return dialect === "mysql"
    ? ddl.replace(
        "name VARCHAR(100) NOT NULL",
        "name VARCHAR(100) NOT NULL COMMENT '学校名称'",
      )
    : `${ddl}\n\nCOMMENT ON TABLE schools IS '学校';\nCOMMENT ON COLUMN schools.name IS '学校名称';\nCOMMENT ON COLUMN subject_scores.score IS '原始成绩，缺考口径需由业务确认';`;
}

function Warnings({ items }) {
  if (!items?.length) return null;
  return (
    <Alert
      type="warning"
      showIcon
      message={`${items.length} 项需要复核`}
      description={
        <ul className="automodel-warnings">
          {items.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      }
    />
  );
}

export function AutoModelWizard({ request, onClose, onCreated }) {
  const [form] = Form.useForm();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [error, setError] = useState("");
  const [source, setSource] = useState(null);
  const [preview, setPreview] = useState(null);
  const [selection, setSelection] = useState({});
  const [active, setActive] = useState("");
  const [relationships, setRelationships] = useState(true);
  const [review, setReview] = useState(null);
  const [fileName, setFileName] = useState("");
  const [sourceMode, setSourceMode] = useState("ddl");
  const [discovery, setDiscovery] = useState(null);
  const [databaseTables, setDatabaseTables] = useState([]);
  const [schemas, setSchemas] = useState([]);
  const [tested, setTested] = useState(false);
  const errorRef = useRef(null);

  async function perform(work) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      if (!e.errorFields) {
        const details = e.issues
          ?.map((x) => `${x.path}：${x.message}`)
          .join("；");
        setError(
          (e.message || "操作失败，请重试。") + (details ? ` ${details}` : ""),
        );
        requestAnimationFrame(() => errorRef.current?.focus());
      }
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  function connection(values) {
    return Object.fromEntries(
      ["dialect", "host", "port", "database", "user", "password", "tls"].map(
        (key) => [key, values[key] ?? ""],
      ),
    );
  }
  function scope(values) {
    return {
      ...connection(values),
      physical_schema:
        values.dialect === "mysql" ? values.database : values.physical_schema,
      table_filter: values.table_filter || "",
    };
  }
  async function testConnection() {
    const values = await form.validateFields([
      "dialect",
      "host",
      "port",
      "database",
      "user",
      "password",
      "tls",
    ]);
    const result = await request(
      "/automodel/database/test",
      "POST",
      connection(values),
    );
    setSchemas(result.schemas);
    setTested(true);
  }
  async function listTables() {
    const values = await form.validateFields();
    const result = await request(
      "/automodel/database/tables",
      "POST",
      scope(values),
    );
    setDiscovery(result);
    setDatabaseTables(
      result.tables.length <= 50 ? result.tables.map((t) => t.name) : [],
    );
    setTested(true);
  }
  async function parse() {
    if (sourceMode === "database" && !discovery) return listTables();
    const values = await form.validateFields();
    const common = Object.fromEntries(
      ["name", "dialect", "catalog", "schema"].map((key) => [key, values[key]]),
    );
    let result;
    if (sourceMode === "database") {
      if (!databaseTables.length) throw new Error("请至少选择一张表。");
      result = await request("/automodel/database/scan", "POST", {
        ...scope(values),
        tables: databaseTables,
      });
      setSource({ ...common, scan_id: result.scan_id });
      form.setFieldValue("password", "");
      setDiscovery(null);
      setDatabaseTables([]);
      setTested(false);
    } else {
      result = await request("/automodel/preview", "POST", {
        ddl: values.ddl,
        dialect: values.dialect,
      });
      setSource({ ...common, ddl: values.ddl });
    }
    setPreview(result);
    setSelection(
      Object.fromEntries(
        result.tables.map((t) => [
          t.id,
          { enabled: true, columns: t.columns.map((c) => c.id), types: {} },
        ]),
      ),
    );
    setActive(result.tables[0].id);
    setReview(null);
    setStep(1);
  }
  function change(tid, patch) {
    setSelection((old) => ({ ...old, [tid]: { ...old[tid], ...patch } }));
  }
  function payload() {
    return {
      ...source,
      relationships,
      tables: preview.tables
        .filter((t) => selection[t.id].enabled)
        .map((t) => ({
          table_id: t.id,
          columns: selection[t.id].columns,
          types: Object.fromEntries(
            Object.entries(selection[t.id].types).filter(([id]) =>
              selection[t.id].columns.includes(id),
            ),
          ),
        })),
    };
  }
  async function next() {
    if (step === 0) return parse();
    if (step === 1) {
      const selected = preview.tables.filter((t) => selection[t.id].enabled);
      if (!selected.length) throw new Error("请至少选择一张表。");
      for (const t of selected) {
        if (!selection[t.id].columns.length)
          throw new Error(`${t.label} 请至少选择一个字段。`);
        const unknown = t.columns.find(
          (c) =>
            selection[t.id].columns.includes(c.id) &&
            !(selection[t.id].types[c.id] || c.type),
        );
        if (unknown) {
          setActive(t.id);
          throw new Error(
            `${t.label}.${unknown.name} 的类型无法识别，请选择语义类型或排除此字段。`,
          );
        }
      }
      setReview(await request("/automodel/review", "POST", payload()));
      setStep(2);
      return;
    }
    const result = await request("/automodel/generate", "POST", payload());
    await onCreated(result);
  }
  const table = preview?.tables.find((t) => t.id === active);
  const chosenTables =
    preview?.tables.filter((t) => selection[t.id]?.enabled) || [];
  const count = chosenTables.reduce(
    (n, t) => n + selection[t.id].columns.length,
    0,
  );
  const issues = chosenTables.flatMap((t) =>
    t.columns
      .filter((c) => selection[t.id].columns.includes(c.id) && c.warning)
      .map((c) => `${t.label}.${c.name}：${c.warning}`),
  );

  return (
    <Modal
      open
      title="自动建模"
      width={1080}
      className="automodel-modal"
      onCancel={() => !busy && onClose()}
      closable={!busy}
      maskClosable={false}
      keyboard={!busy}
      footer={
        <div className="automodel-footer">
          <Typography.Text type="secondary">
            {step
              ? `已选 ${chosenTables.length} 张表 · ${count} 个物理字段`
              : sourceMode === "database"
                ? "只读取表结构，连接密码不保存"
                : "只解析表结构，不读取业务数据"}
          </Typography.Text>
          <Space>
            <Button
              disabled={busy}
              onClick={
                step
                  ? () => {
                      setStep(step - 1);
                      setError("");
                    }
                  : onClose
              }
            >
              {step ? "上一步" : "取消"}
            </Button>
            <Button
              type="primary"
              loading={busy}
              disabled={
                step === 0 &&
                sourceMode === "database" &&
                discovery &&
                !databaseTables.length
              }
              onClick={() => perform(next)}
            >
              {step === 0
                ? sourceMode === "database"
                  ? discovery
                    ? "扫描选中表"
                    : "连接并读取表清单"
                  : "解析表结构"
                : step === 1
                  ? "预览生成结果"
                  : busy
                    ? "正在校验并创建"
                    : "校验并创建草稿"}
            </Button>
          </Space>
        </div>
      }
    >
      <Steps
        size="small"
        current={step}
        items={[
          { title: "导入表结构" },
          { title: "选择建模范围" },
          { title: "确认并生成" },
        ]}
      />
      <div className="automodel-body" aria-busy={busy}>
        {error && (
          <div ref={errorRef} tabIndex={-1} role="alert">
            <Alert
              type="error"
              showIcon
              message="未能完成操作"
              description={error}
            />
          </div>
        )}
        <div hidden={step !== 0}>
          <Segmented
            className="automodel-source-switch"
            aria-label="建模来源"
            value={sourceMode}
            disabled={busy}
            options={[
              { value: "ddl", label: "导入 DDL" },
              { value: "database", label: "数据库直连" },
            ]}
            onChange={(mode) => {
              setSourceMode(mode);
              setDiscovery(null);
              setDatabaseTables([]);
              setSchemas([]);
              setTested(false);
              setError("");
              if (
                mode === "database" &&
                form.getFieldValue("dialect") === "duckdb"
              )
                form.setFieldsValue({ dialect: "postgres", port: 5432 });
              if (mode === "ddl") form.setFieldValue("password", "");
            }}
          />
          <Alert
            type="info"
            showIcon
            message={
              sourceMode === "database"
                ? "连接数据库，扫描表结构并生成 MDL"
                : "从数据库导出的建表 SQL 自动生成 MDL"
            }
            description={
              sourceMode === "database"
                ? "使用只读账号读取表清单、字段、注释及主外键，不查询业务数据。连接由当前 Docker 服务发起；扫描结果在当前会话保留 15 分钟。"
                : "识别字段类型、注释、主键和外键。支持 CREATE TABLE、COMMENT 和 ALTER TABLE ADD 约束，请上传仅含结构的 SQL 文件。"
            }
          />
          <Form
            form={form}
            layout="vertical"
            initialValues={{
              name: "数据库自动建模",
              dialect: "postgres",
              catalog: "wren",
              schema: "public",
              ddl: "",
              host: "host.docker.internal",
              port: 5432,
              database: "",
              user: "",
              password: "",
              tls: "require",
              physical_schema: "public",
              table_filter: "",
            }}
            onValuesChange={(changed) => {
              if (
                [
                  "dialect",
                  "host",
                  "port",
                  "database",
                  "user",
                  "password",
                  "tls",
                  "physical_schema",
                  "table_filter",
                ].some((key) => key in changed)
              ) {
                setDiscovery(null);
                setDatabaseTables([]);
                setTested(false);
              }
              if (
                [
                  "dialect",
                  "host",
                  "port",
                  "database",
                  "user",
                  "password",
                  "tls",
                ].some((key) => key in changed)
              )
                setSchemas([]);
              if (changed.dialect) {
                const port = form.getFieldValue("port");
                if (port === 5432 || port === 3306)
                  form.setFieldValue(
                    "port",
                    changed.dialect === "mysql" ? 3306 : 5432,
                  );
              }
            }}
            disabled={busy}
            requiredMark={false}
          >
            <div className="automodel-source-grid">
              <Form.Item
                name="name"
                label="草稿名称"
                rules={[
                  {
                    required: true,
                    whitespace: true,
                    message: "请输入草稿名称",
                  },
                  { max: 100 },
                ]}
              >
                <Input maxLength={100} />
              </Form.Item>
              <Form.Item
                name="dialect"
                label="源数据库"
                rules={[{ required: true }]}
              >
                <Select
                  options={[
                    { value: "postgres", label: "PostgreSQL" },
                    { value: "mysql", label: "MySQL" },
                    ...(sourceMode === "ddl"
                      ? [{ value: "duckdb", label: "DuckDB" }]
                      : []),
                  ]}
                />
              </Form.Item>
              <Form.Item
                name="catalog"
                label="语义 Catalog"
                rules={[
                  { required: true },
                  {
                    pattern: /^[A-Za-z_][A-Za-z0-9_]*$/,
                    message: "请使用字母、数字和下划线，不能以数字开头",
                  },
                ]}
              >
                <Input maxLength={100} />
              </Form.Item>
              <Form.Item
                name="schema"
                label="语义 Schema"
                rules={[
                  { required: true },
                  {
                    pattern: /^[A-Za-z_][A-Za-z0-9_]*$/,
                    message: "请使用字母、数字和下划线，不能以数字开头",
                  },
                ]}
              >
                <Input maxLength={100} />
              </Form.Item>
            </div>
            {sourceMode === "database" ? (
              <DatabaseSource
                form={form}
                busy={busy}
                discovery={discovery}
                chosen={databaseTables}
                onChoose={setDatabaseTables}
                schemas={schemas}
                tested={tested}
                onTest={() => perform(testConnection)}
                onList={() => perform(listTables)}
              />
            ) : (
              <>
                <div className="automodel-source-tools">
                  <Space wrap>
                    <Upload
                      accept=".sql,.ddl,.txt"
                      showUploadList={false}
                      disabled={busy}
                      beforeUpload={(file) => {
                        void perform(async () => {
                          if (file.size > 500000)
                            throw new Error(
                              "文件不能超过 500 KB，请按业务域拆分。",
                            );
                          form.setFieldValue("ddl", await file.text());
                          setFileName(file.name);
                        });
                        return false;
                      }}
                    >
                      <Button
                        disabled={busy}
                        icon={<UploadOutlined aria-hidden="true" />}
                      >
                        上传 DDL 文件
                      </Button>
                    </Upload>
                    <Button
                      disabled={busy}
                      icon={<FileTextOutlined aria-hidden="true" />}
                      onClick={() => {
                        form.setFieldValue(
                          "ddl",
                          example(form.getFieldValue("dialect")),
                        );
                        setFileName("");
                      }}
                    >
                      填入学情示例
                    </Button>
                  </Space>
                  <Typography.Text type="secondary">
                    {fileName || "UTF-8 · .sql / .ddl / .txt · 最大 500 KB"}
                  </Typography.Text>
                </div>
                <Form.Item
                  name="ddl"
                  label="建表 DDL"
                  rules={[
                    {
                      required: true,
                      whitespace: true,
                      message: "请上传文件或粘贴 CREATE TABLE 语句",
                    },
                  ]}
                >
                  <Input.TextArea
                    rows={12}
                    className="automodel-code"
                    spellCheck={false}
                    placeholder="CREATE TABLE schools (id BIGINT PRIMARY KEY, name VARCHAR(100));"
                  />
                </Form.Item>
              </>
            )}
          </Form>
        </div>
        {step === 1 && table && (
          <>
            {source?.scan_id && (
              <Alert
                type="info"
                showIcon
                message="表结构扫描完成，数据库连接已关闭"
                description="密码已清空。当前会话的扫描结果保留 15 分钟，请在有效期内确认并创建草稿。"
              />
            )}
            <div className="automodel-selection-toolbar">
              <Typography.Text>
                选择表与字段，可排除敏感或无关字段。
              </Typography.Text>
              <Space>
                <Button
                  size="small"
                  disabled={busy}
                  onClick={() =>
                    setSelection((old) =>
                      Object.fromEntries(
                        Object.entries(old).map(([k, v]) => [
                          k,
                          { ...v, enabled: true },
                        ]),
                      ),
                    )
                  }
                >
                  全选表
                </Button>
                <Button
                  size="small"
                  disabled={busy}
                  onClick={() =>
                    setSelection((old) =>
                      Object.fromEntries(
                        Object.entries(old).map(([k, v]) => [
                          k,
                          { ...v, enabled: false },
                        ]),
                      ),
                    )
                  }
                >
                  清空表选择
                </Button>
              </Space>
            </div>
            <div className="automodel-selection">
              <nav className="automodel-tables" aria-label="选择要建模的表">
                {preview.tables.map((t) => (
                  <div
                    key={t.id}
                    className={`automodel-table-option ${active === t.id ? "active" : ""}`}
                  >
                    <Checkbox
                      disabled={busy}
                      checked={selection[t.id].enabled}
                      aria-label={`建模 ${t.label}`}
                      onChange={(e) =>
                        change(t.id, { enabled: e.target.checked })
                      }
                    />
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => setActive(t.id)}
                    >
                      <strong>{t.label}</strong>
                      <small>
                        {t.logical_name} · {t.columns.length} 个字段
                      </small>
                    </button>
                  </div>
                ))}
              </nav>
              <section
                className="automodel-fields"
                aria-label={`${table.label} 字段选择`}
              >
                <div className="automodel-fields-heading">
                  <strong>{table.label}</strong>
                  <Typography.Text type="secondary">
                    {table.description || "未提供表注释"}
                  </Typography.Text>
                  <Tag>
                    {selection[table.id].enabled ? "参与建模" : "已排除"}
                  </Tag>
                </div>
                <Table
                  size="small"
                  rowKey="id"
                  dataSource={table.columns}
                  pagination={false}
                  scroll={{ x: 590, y: 320 }}
                  rowSelection={{
                    selectedRowKeys: selection[table.id].columns,
                    onChange: (keys) => change(table.id, { columns: keys }),
                    getCheckboxProps: (column) => ({
                      "aria-label": `选择字段 ${table.label}.${column.name}`,
                      disabled: busy || !selection[table.id].enabled,
                    }),
                  }}
                  columns={[
                    {
                      title: "字段 / 注释",
                      dataIndex: "name",
                      width: 220,
                      render: (_, c) => (
                        <div>
                          <strong>{c.name}</strong>{" "}
                          {c.primary_key && <Tag color="gold">PK</Tag>}
                          {c.foreign_key && <Tag color="blue">FK</Tag>}
                          <small className="automodel-field-note">
                            {c.description || c.logical_name}
                          </small>
                          {c.warning && (
                            <small className="automodel-type-warning">
                              {c.warning}
                            </small>
                          )}
                        </div>
                      ),
                    },
                    { title: "物理类型", dataIndex: "raw_type", width: 130 },
                    {
                      title: "语义类型",
                      width: 175,
                      render: (_, c) => (
                        <Select
                          aria-label={`${table.label}.${c.name} 语义类型`}
                          disabled={
                            busy ||
                            !selection[table.id].enabled ||
                            !selection[table.id].columns.includes(c.id)
                          }
                          status={
                            !(selection[table.id].types[c.id] || c.type)
                              ? "error"
                              : undefined
                          }
                          value={
                            selection[table.id].types[c.id] ||
                            c.type ||
                            undefined
                          }
                          placeholder="请选择类型"
                          showSearch
                          options={[
                            ...new Set([
                              ...preview.type_choices,
                              ...(c.type ? [c.type] : []),
                            ]),
                          ].map((value) => ({ value, label: value }))}
                          onChange={(value) =>
                            change(table.id, {
                              types: {
                                ...selection[table.id].types,
                                [c.id]: value,
                              },
                            })
                          }
                        />
                      ),
                    },
                  ]}
                />
              </section>
            </div>
            <Checkbox
              checked={relationships}
              disabled={busy}
              onChange={(e) => setRelationships(e.target.checked)}
            >
              {source?.scan_id
                ? "根据数据库中明确声明的外键生成模型关联"
                : "根据 DDL 中明确声明的外键生成模型关联"}
            </Checkbox>
            <Typography.Paragraph type="secondary">
              关联两端的表和字段都需选中。未声明的关联及指标计算口径，可在生成后继续补充。
            </Typography.Paragraph>
            <Warnings items={[...preview.warnings, ...issues]} />
          </>
        )}
        {step === 2 && review && (
          <>
            <Alert
              type="success"
              showIcon
              message="MDL 已准备就绪"
              description="确认后由当前服务的 Wren SDK 校验，校验通过才会保存为新草稿。"
            />
            <div className="automodel-review-summary">
              <div>
                <strong>{review.manifest.models.length}</strong>
                <span>逻辑模型</span>
              </div>
              <div>
                <strong>{count}</strong>
                <span>物理字段</span>
              </div>
              <div>
                <strong>{review.manifest.relationships.length}</strong>
                <span>模型关联</span>
              </div>
              <div>
                <strong>{source.dialect}</strong>
                <span>目标 SQL 方言</span>
              </div>
            </div>
            <Typography.Paragraph>
              <strong>{source.name}</strong> · {source.catalog}.{source.schema}
            </Typography.Paragraph>
            <Table
              size="small"
              rowKey="name"
              dataSource={review.manifest.models}
              pagination={false}
              scroll={{ x: 650, y: 220 }}
              columns={[
                { title: "逻辑模型", dataIndex: "name" },
                {
                  title: "物理表",
                  render: (_, m) => Object.values(m.tableReference).join("."),
                },
                {
                  title: "字段",
                  render: (_, m) =>
                    m.columns.filter((c) => !c.relationship).length,
                },
                {
                  title: "主键",
                  dataIndex: "primaryKey",
                  render: (v) => v || "未设置",
                },
              ]}
            />
            <Warnings items={review.warnings} />
            <Collapse
              items={[
                {
                  key: "mdl",
                  label: "查看生成的 MDL JSON",
                  children: (
                    <pre className="automodel-manifest">
                      {JSON.stringify(review.manifest, null, 2)}
                    </pre>
                  ),
                },
              ]}
            />
          </>
        )}
      </div>
    </Modal>
  );
}
