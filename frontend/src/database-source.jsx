import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Typography,
} from "antd";

export function DatabaseSource({
  form,
  busy,
  discovery,
  chosen,
  onChoose,
  schemas,
  tested,
  onTest,
  onList,
}) {
  const dialect = Form.useWatch("dialect", form) || "postgres";
  return (
    <>
      <div className="automodel-connection-grid">
        <Form.Item
          name="host"
          label="数据库主机"
          extra="Docker 访问本机数据库：host.docker.internal"
          rules={[
            { required: true, whitespace: true, message: "请输入数据库主机" },
          ]}
        >
          <Input
            maxLength={253}
            autoComplete="off"
            placeholder="host.docker.internal"
          />
        </Form.Item>
        <Form.Item
          name="port"
          label="端口"
          rules={[{ required: true, message: "请输入端口" }]}
        >
          <InputNumber
            min={1}
            max={65535}
            precision={0}
            style={{ width: "100%" }}
          />
        </Form.Item>
        <Form.Item
          name="database"
          label="数据库名称"
          rules={[
            { required: true, whitespace: true, message: "请输入数据库名称" },
          ]}
        >
          <Input maxLength={128} autoComplete="off" />
        </Form.Item>
        <Form.Item
          name="user"
          label="数据库用户名"
          rules={[
            { required: true, whitespace: true, message: "请输入数据库用户名" },
          ]}
        >
          <Input maxLength={128} autoComplete="off" />
        </Form.Item>
        <Form.Item
          name="password"
          label="数据库密码"
          extra="仅用于本次连接，扫描后清空，不保存到草稿。"
        >
          <Input.Password maxLength={1024} autoComplete="new-password" />
        </Form.Item>
        <Form.Item name="tls" label="TLS 连接模式" rules={[{ required: true }]}>
          <Select
            options={[
              { value: "require", label: "加密连接（不校验证书）" },
              { value: "verify-full", label: "加密并校验证书及主机名" },
              { value: "disable", label: "不使用 TLS（本地测试）" },
            ]}
          />
        </Form.Item>
        {dialect === "postgres" && (
          <Form.Item
            name="physical_schema"
            label="物理 Schema"
            rules={[
              {
                required: true,
                whitespace: true,
                message: "请输入物理 Schema",
              },
            ]}
          >
            {schemas.length ? (
              <Select
                showSearch
                options={schemas.map((value) => ({ value, label: value }))}
              />
            ) : (
              <Input maxLength={128} placeholder="public" />
            )}
          </Form.Item>
        )}
        <Form.Item
          name="table_filter"
          label="表名包含（可选）"
          extra="表较多时，先按业务域缩小清单。"
        >
          <Input maxLength={100} placeholder="例如：edu_" />
        </Form.Item>
      </div>
      <Space wrap className="automodel-connection-actions">
        <Button loading={busy} onClick={onTest}>
          测试连接
        </Button>
        <Button disabled={busy} onClick={onList}>
          读取表清单
        </Button>
        {tested && (
          <Typography.Text type="success" role="status">
            连接成功，可读取表结构
          </Typography.Text>
        )}
      </Space>
      {discovery && (
        <section className="automodel-discovery" aria-label="数据库表清单">
          <div className="automodel-selection-toolbar">
            <strong>数据库表清单 · 已选 {chosen.length} / 50</strong>
            <Space>
              <Button
                size="small"
                disabled={
                  busy ||
                  discovery.tables.length > 50 ||
                  !discovery.tables.length
                }
                onClick={() => onChoose(discovery.tables.map((t) => t.name))}
              >
                全选清单
              </Button>
              <Button size="small" disabled={busy} onClick={() => onChoose([])}>
                清空
              </Button>
            </Space>
          </div>
          {discovery.truncated && (
            <Alert
              type="warning"
              showIcon
              message="仅显示前 1000 张表，请填写表名筛选以缩小范围。"
            />
          )}
          {!discovery.tables.length && (
            <Alert
              type="info"
              showIcon
              message="未找到可见的基础表，请检查 Schema、表名筛选及账号的 SELECT 权限。"
            />
          )}
          <Table
            size="small"
            rowKey="name"
            dataSource={discovery.tables}
            pagination={{
              pageSize: 8,
              showSizeChanger: false,
              hideOnSinglePage: true,
            }}
            scroll={{ x: 450, y: 245 }}
            rowSelection={{
              selectedRowKeys: chosen,
              preserveSelectedRowKeys: true,
              hideSelectAll: true,
              onChange: onChoose,
              getCheckboxProps: (t) => ({
                disabled:
                  busy || (chosen.length >= 50 && !chosen.includes(t.name)),
                "aria-label": `扫描表 ${t.name}`,
              }),
            }}
            columns={[
              { title: "物理表", dataIndex: "name", width: 220 },
              {
                title: "表注释",
                dataIndex: "description",
                render: (s) => s || "—",
              },
            ]}
          />
          <Typography.Paragraph type="secondary">
            扫描仅读取选中表的字段和约束。关联需要同时扫描两端的表；当前不导入视图。
          </Typography.Paragraph>
        </section>
      )}
    </>
  );
}
