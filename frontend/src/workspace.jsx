import { useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Dropdown,
  Empty,
  Input,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
} from "antd";
import {
  DatabaseOutlined,
  DownOutlined,
  EditOutlined,
  ReloadOutlined,
  SearchOutlined,
  UndoOutlined,
} from "@ant-design/icons";

const dialectNames = {
  postgres: "PostgreSQL",
  mysql: "MySQL",
  duckdb: "DuckDB",
};
const time = (value) =>
  value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
const names = (d) =>
  Array.isArray(d.manifest?.models)
    ? d.manifest.models.filter((m) => m && typeof m === "object")
    : [];
function statusOf(d, bundles) {
  const releases = bundles
    .filter((b) => b.draft_id === d.id)
    .sort((a, b) => b.revision - a.revision);
  if (!releases.length)
    return { key: "draft", label: "未发布", color: "default" };
  const latest = releases[0];
  return latest.revision === d.revision
    ? {
        key: "published",
        label: "已发布",
        color: "green",
        release: latest.bundle_id,
      }
    : {
        key: "changed",
        label: "有更新",
        color: "gold",
        release: latest.bundle_id,
      };
}
export function WorkspaceList({ state, onAction }) {
  const [section, setSection] = useState("active");
  const [query, setQuery] = useState("");
  const [dialect, setDialect] = useState("all");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const deleted = section === "trash";
  const source = deleted ? state.trash : state.drafts;
  const filter = query.trim().toLocaleLowerCase();
  const rows = source.filter(
    (d) =>
      (!filter ||
        [d.name, d.id, ...names(d).map((m) => m.name)].some((v) =>
          String(v).toLocaleLowerCase().includes(filter),
        )) &&
      (dialect === "all" || d.dialect === dialect) &&
      (deleted ||
        status === "all" ||
        statusOf(d, state.bundles).key === status),
  );
  useEffect(
    () =>
      setPage((p) =>
        Math.min(p, Math.max(1, Math.ceil(rows.length / pageSize))),
      ),
    [rows.length, pageSize],
  );
  const change = (setter) => (value) => {
    setter(value);
    setPage(1);
  };
  const columns = [
    {
      title: "模型名称",
      dataIndex: "name",
      key: "name",
      width: 300,
      render: (_, d) => (
        <div className="workspace-model-name">
          <span className="workspace-model-icon">
            <DatabaseOutlined aria-hidden="true" />
          </span>
          <div>
            {deleted ? (
              <strong>{d.name}</strong>
            ) : (
              <Button
                type="link"
                className="workspace-name-link"
                onClick={() => onAction("open-draft", { id: d.id })}
              >
                {d.name}
              </Button>
            )}
            <p
              title={names(d)
                .map((m) => m.name)
                .join(" / ")}
            >
              {names(d)
                .map((m) => m.name)
                .join(" / ") || "尚未添加逻辑模型"}
            </p>
          </div>
        </div>
      ),
    },
    {
      title: "数据库",
      dataIndex: "dialect",
      width: 120,
      filters: undefined,
      render: (v) => <Tag>{dialectNames[v] || v}</Tag>,
    },
    {
      title: "模型 / 字段",
      key: "counts",
      width: 130,
      render: (_, d) => (
        <span className="workspace-model-counts">
          {names(d).length}
          <span> / </span>
          {names(d).reduce(
            (n, m) => n + (Array.isArray(m.columns) ? m.columns.length : 0),
            0,
          )}
        </span>
      ),
    },
    {
      title: "版本状态",
      key: "status",
      width: 160,
      render: (_, d) => {
        const item = statusOf(d, state.bundles);
        return (
          <div>
            <Tag color={item.color}>{item.label}</Tag>
            <small className="workspace-revision">
              草稿 r{d.revision}
              {item.release && (
                <Tooltip title={item.release}>
                  <span> · {item.release}</span>
                </Tooltip>
              )}
            </small>
          </div>
        );
      },
    },
    {
      title: deleted ? "删除时间" : "更新时间",
      dataIndex: deleted ? "deleted_at" : "updated_at",
      width: 180,
      defaultSortOrder: "descend",
      sorter: (a, b) =>
        new Date(deleted ? a.deleted_at : a.updated_at) -
        new Date(deleted ? b.deleted_at : b.updated_at),
      render: time,
    },
    {
      title: "操作",
      key: "actions",
      width: 220,
      render: (_, d) =>
        deleted ? (
          <Button
            type="link"
            icon={<UndoOutlined aria-hidden="true" />}
            disabled={state.busy}
            onClick={() => onAction("draft-restore", { id: d.id })}
          >
            恢复
          </Button>
        ) : (
          <Space size={4} className="workspace-row-actions">
            <Button
              type="link"
              icon={<EditOutlined aria-hidden="true" />}
              disabled={state.busy}
              onClick={() => onAction("open-draft", { id: d.id })}
            >
              编辑
            </Button>
            <Button
              type="link"
              disabled={state.busy}
              onClick={() => onAction("draft-metadata", { id: d.id })}
            >
              修改信息
            </Button>
            <Dropdown
              trigger={["click"]}
              menu={{
                items: [
                  { key: "draft-update", label: "更新 MDL" },
                  { key: "draft-export", label: "导出 MDL" },
                  { type: "divider" },
                  { key: "draft-delete", label: "删除", danger: true },
                ],
                onClick: ({ key }) => onAction(key, { id: d.id }),
              }}
            >
              <Button
                type="text"
                disabled={state.busy}
                aria-label={`更多操作：${d.name}`}
              >
                更多
                <DownOutlined aria-hidden="true" />
              </Button>
            </Dropdown>
          </Space>
        ),
    },
  ];
  const published = state.drafts.filter(
    (d) => statusOf(d, state.bundles).key !== "draft",
  ).length;
  const changed = state.drafts.filter(
    (d) => statusOf(d, state.bundles).key === "changed",
  ).length;
  return (
    <div className="workspace-list-page">
      {state.error && (
        <Alert
          id="page-error"
          tabIndex={-1}
          type="error"
          showIcon
          message={state.error.message}
          action={
            <Button size="small" onClick={() => onAction("refresh-workspace")}>
              刷新列表
            </Button>
          }
        />
      )}
      <div className="workspace-summary">
        <span>
          <strong>{state.drafts.length}</strong> 个模型草稿
        </span>
        <span>
          <Badge status="success" />
          {published} 个有发布版本
        </span>
        <span>
          <Badge status="warning" />
          {changed} 个待发布更新
        </span>
      </div>
      <Card className="workspace-table-card">
        <div className="workspace-tabs-row">
          <Tabs
            activeKey={section}
            onChange={change(setSection)}
            items={[
              { key: "active", label: `全部模型（${state.drafts.length}）` },
              { key: "trash", label: `回收站（${state.trash.length}）` },
            ]}
          />
          <Button
            icon={<ReloadOutlined aria-hidden="true" />}
            loading={state.busy}
            onClick={() => onAction("refresh-workspace")}
          >
            刷新列表
          </Button>
        </div>
        {deleted && (
          <Alert
            className="workspace-trash-note"
            showIcon
            type="info"
            message="删除的模型草稿可在此恢复。已发布的版本继续保留。"
          />
        )}
        <div className="workspace-filters">
          <div className="workspace-search">
            <label htmlFor="model-search">模型名称 / 逻辑模型</label>
            <Input
              id="model-search"
              prefix={<SearchOutlined aria-hidden="true" />}
              value={query}
              allowClear
              placeholder="搜索模型名称或逻辑模型"
              onChange={(e) => change(setQuery)(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="model-dialect-filter">数据库类型</label>
            <Select
              id="model-dialect-filter"
              aria-label="数据库类型筛选"
              value={dialect}
              onChange={change(setDialect)}
              options={[
                { value: "all", label: "全部数据库" },
                ...Object.entries(dialectNames).map(([value, label]) => ({
                  value,
                  label,
                })),
              ]}
            />
          </div>
          {!deleted && (
            <div>
              <label htmlFor="model-status-filter">版本状态</label>
              <Select
                id="model-status-filter"
                aria-label="版本状态筛选"
                value={status}
                onChange={change(setStatus)}
                options={[
                  { value: "all", label: "全部状态" },
                  { value: "draft", label: "未发布" },
                  { value: "published", label: "已发布" },
                  { value: "changed", label: "有更新" },
                ]}
              />
            </div>
          )}
          <Button
            className="workspace-reset"
            onClick={() => {
              setQuery("");
              setDialect("all");
              setStatus("all");
              setPage(1);
            }}
          >
            重置
          </Button>
        </div>
        <div className="workspace-table-caption">
          <strong>{deleted ? "已删除的模型" : "模型列表"}</strong>
          <span>
            共 {rows.length} 条
            {query || dialect !== "all" || status !== "all" ? "筛选结果" : ""}
          </span>
        </div>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={rows}
          size="middle"
          scroll={{ x: 1140 }}
          pagination={{
            current: page,
            pageSize,
            total: rows.length,
            showSizeChanger: true,
            pageSizeOptions: [10, 20, 50],
            showTotal: (total) => `共 ${total} 条`,
            onChange: (p, size) => {
              setPage(p);
              setPageSize(size);
            },
          }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  deleted
                    ? "回收站为空"
                    : source.length
                      ? "未找到匹配的模型"
                      : "还没有模型草稿"
                }
              >
                {!deleted && !source.length && (
                  <Button type="primary" onClick={() => onAction("new-draft")}>
                    新建模型草稿
                  </Button>
                )}
              </Empty>
            ),
          }}
        />
      </Card>
    </div>
  );
}
