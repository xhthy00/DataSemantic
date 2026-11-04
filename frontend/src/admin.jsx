import { WorkspaceList } from "./workspace.jsx";
import { AutoModelWizard } from "./automodel.jsx";
import { useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import {
  Badge,
  Button,
  ConfigProvider,
  Form,
  Input,
  Spin,
  Space,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import zhCN from "antd/es/locale/zh_CN";
import { PageContainer, ProLayout } from "@ant-design/pro-components";
import {
  ApartmentOutlined,
  ArrowLeftOutlined,
  BookOutlined,
  CheckOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  ImportOutlined,
  LockOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  LogoutOutlined,
  PlusOutlined,
  SaveOutlined,
  SettingOutlined,
  TableOutlined,
  UploadOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import "antd/dist/reset.css";
import "./admin.css";

const SIDEBAR_WIDTH = 232;
const COLLAPSED_SIDEBAR_WIDTH = 64;

const root = createRoot(document.getElementById("app"));
const nonce = document.querySelector('meta[name="csp-nonce"]').content;
const subscribe = (callback) => {
  window.addEventListener("studio:status", callback);
  return () => window.removeEventListener("studio:status", callback);
};
export function notifyAdmin() {
  window.dispatchEvent(new Event("studio:status"));
}
const theme = {
  token: {
    colorPrimary: "#1677ff",
    borderRadius: 6,
    fontFamily:
      '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif',
  },
  components: {
    Button: { defaultShadow: "none", primaryShadow: "none" },
    Layout: { bodyBg: "#f0f2f5" },
    Tabs: { horizontalItemGutter: 28 },
  },
};
function Provider({ children }) {
  return (
    <ConfigProvider locale={zhCN} csp={{ nonce }} theme={theme}>
      {children}
    </ConfigProvider>
  );
}
function useStatus(state) {
  return useSyncExternalStore(
    subscribe,
    () => `${state.dirty}:${state.draft?.revision}:${state.busy}`,
  );
}
function SaveStatus({ state }) {
  useStatus(state);
  return (
    <Tag id="save-state" color={state.dirty ? "gold" : "default"}>
      {state.dirty ? "未保存" : `草稿 · r${state.draft.revision}`}
    </Tag>
  );
}
function NativeWorkspace({ html, onReady, renderId }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    ref.current.innerHTML = html;
    onReady();
  }, [renderId]);
  return <div className="studio-editor" ref={ref} />;
}
function ModelNavigation({ state, onAction }) {
  const items = state.draft.manifest.models;
  return (
    <section className="model-navigation" aria-label="逻辑模型导航">
      <div className="model-navigation-heading">
        <span>
          逻辑模型 <Tag>{items.length}</Tag>
        </span>
        <Button
          type="text"
          icon={<PlusOutlined aria-hidden="true" />}
          aria-label="添加逻辑模型"
          onClick={() => onAction("add-model")}
        />
      </div>
      <div className="model-navigation-items">
        {items.map((m, i) => (
          <Tooltip key={i} title={m.name} placement="right">
            <button
              type="button"
              className={`model-navigation-item ${state.model === i ? "selected" : ""}`}
              onClick={() => onAction("select-model", { index: i })}
            >
              <TableOutlined aria-hidden="true" />
              <span>
                {m.properties?.displayName || m.name || "未命名模型"}
                <small>{m.name}</small>
              </span>
            </button>
          </Tooltip>
        ))}
        {!items.length && (
          <p className="model-navigation-empty">添加业务实体，开始建模。</p>
        )}
      </div>
    </section>
  );
}
function EditorFooter({ state }) {
  useStatus(state);
  const d = state.draft;
  return (
    <footer className="admin-editor-footer">
      <span>
        <Badge status={state.dirty ? "warning" : "success"} />
        {state.dirty
          ? "修改尚未保存"
          : `已保存 · ${new Date(d.updated_at).toLocaleString("zh-CN", { hour12: false })}`}
      </span>
      <span>
        {d.dialect} <span className="footer-separator">/</span>{" "}
        {d.manifest.catalog}.{d.manifest.schema}
      </span>
    </footer>
  );
}
function AdminFrame({
  state,
  html,
  onReady,
  onAction,
  renderId,
  request,
  onGenerated,
}) {
  useStatus(state);
  const [autoModelOpen, setAutoModelOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(
    () => window.matchMedia("(max-width:991px)").matches,
  );
  const d = state.draft;
  const editing = d && !["workspace", "releases", "guide"].includes(state.tab);
  const title =
    state.tab === "workspace"
      ? "模型工作空间"
      : state.tab === "releases"
        ? "已发布版本"
        : state.tab === "guide"
          ? "创建指南"
          : d?.name || "建模工作台";
  const pathname =
    state.tab === "releases"
      ? "/releases"
      : state.tab === "guide"
        ? "/guide"
        : "/modeling";
  const routes = [
    {
      path: "/modeling",
      name: "模型工作空间",
      icon: <ApartmentOutlined aria-hidden="true" />,
      action: "workspace",
    },
    {
      path: "/releases",
      name: "已发布版本",
      icon: <UploadOutlined aria-hidden="true" />,
      action: "releases",
    },
    {
      path: "/guide",
      name: "创建指南",
      icon: <BookOutlined aria-hidden="true" />,
      action: "guide",
    },
  ];
  const tabs = [
    ["models", "模型与字段"],
    ["relationships", "模型关联"],
    ["views", "语义视图"],
    ["json", "MDL JSON"],
    ["sql", "SQL 预览"],
  ];
  return (
    <ProLayout
      className="studio-admin"
      style={{
        "--studio-sidebar-width": `${collapsed ? COLLAPSED_SIDEBAR_WIDTH : SIDEBAR_WIDTH}px`,
      }}
      title="DataSemantic"
      logo={
        <span className="admin-logo">
          <ApartmentOutlined aria-hidden="true" />
        </span>
      }
      layout="mix"
      navTheme="light"
      fixedHeader
      fixSiderbar
      siderWidth={SIDEBAR_WIDTH}
      collapsed={collapsed}
      onCollapse={setCollapsed}
      headerRender={(props, dom) =>
        props.isMobile ? (
          <div className="mobile-admin-header">
            <Button
              type="text"
              icon={<MenuUnfoldOutlined aria-hidden="true" />}
              aria-label={collapsed ? "展开后台导航" : "收起后台导航"}
              aria-expanded={!collapsed}
              onClick={() => setCollapsed(!collapsed)}
            />
            <span className="admin-logo">
              <ApartmentOutlined aria-hidden="true" />
            </span>
            <strong>DataSemantic</strong>
            <span className="mobile-header-spacer" />
            <Button
              type="text"
              icon={<ImportOutlined aria-hidden="true" />}
              aria-label="导入 MDL JSON"
              onClick={() => onAction("import")}
            />
            <Button
              type="text"
              icon={<LogoutOutlined aria-hidden="true" />}
              aria-label="退出登录"
              onClick={() => onAction("logout")}
            />
          </div>
        ) : (
          dom
        )
      }
      breakpoint="lg"
      contentWidth="Fluid"
      contentStyle={{ padding: 0 }}
      bgLayoutImgList={false}
      location={{ pathname }}
      route={{ routes }}
      menu={{ locale: false, defaultOpenAll: true }}
      menuProps={{
        "aria-label": "后台导航",
        onClick: ({ key }) => {
          const item = routes
            .flatMap((r) => [r, ...(r.children || [])])
            .find((r) => r.path === key);
          if (item) {
            if (window.matchMedia("(max-width:767px)").matches)
              setCollapsed(true);
            onAction(item.action, item.payload);
          }
        },
      }}
      menuItemRender={(_, dom) => dom}
      menuHeaderRender={false}
      collapsedButtonRender={(collapsed) => (
        <Button
          type="text"
          onClick={() => setCollapsed(!collapsed)}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "展开后台导航" : "收起后台导航"}
          icon={
            collapsed ? (
              <MenuUnfoldOutlined aria-hidden="true" />
            ) : (
              <MenuFoldOutlined aria-hidden="true" />
            )
          }
        />
      )}
      menuExtraRender={({ collapsed }) =>
        collapsed ? null : (
          <div className="sider-section-label">语义模型管理</div>
        )
      }
      menuFooterRender={({ collapsed }) =>
        collapsed ? null : (
          <div className="sider-footer">
            <Badge status="processing" text="MDL 语义建模" />
            <div>DataSemantic Studio</div>
          </div>
        )
      }
      headerTitleRender={(logo) => (
        <div className="admin-header-brand">
          <div className="admin-header-brand-main">
            {logo}
            {!collapsed && <strong>DataSemantic</strong>}
          </div>
          <span className="admin-product-name">MDL Studio</span>
        </div>
      )}
      actionsRender={() => [
        <span key="status" className="admin-connection">
          {state.busy ? <Spin size="small" /> : <Badge status="success" />}
          {state.busy ? "正在处理" : "服务已连接"}
        </span>,
        <Tooltip key="import" title="导入 MDL JSON">
          <Button
            type="text"
            icon={<ImportOutlined aria-hidden="true" />}
            aria-label="导入 MDL JSON"
            onClick={() => onAction("import")}
          />
        </Tooltip>,
        <Tooltip key="logout" title="退出登录">
          <Button
            type="text"
            icon={<LogoutOutlined aria-hidden="true" />}
            aria-label="退出登录"
            onClick={() => onAction("logout")}
          />
        </Tooltip>,
      ]}
      avatarProps={{
        icon: <UserOutlined aria-hidden="true" />,
        size: "small",
        title: "模型管理员",
      }}
      token={{
        bgLayout: "#f0f2f5",
        header: { heightLayoutHeader: 56, colorBgHeader: "#fff" },
        sider: {
          colorMenuBackground: "#fff",
          colorTextMenuSelected: "#1677ff",
          colorBgMenuItemSelected: "#e6f4ff",
        },
      }}
    >
      <div id="workspace" tabIndex={-1}>
        <PageContainer
          className={`admin-page${editing ? " admin-page-editing" : ""}`}
          title={
            editing ? (
              <div className="admin-editor-title">
                <Tooltip title="返回模型工作空间">
                  <Button
                    type="text"
                    icon={<ArrowLeftOutlined aria-hidden="true" />}
                    aria-label="返回模型工作空间"
                    onClick={() => onAction("workspace")}
                  />
                </Tooltip>
                <h1 className="admin-page-title" title={title}>
                  {title}
                </h1>
              </div>
            ) : (
              <h1 className="admin-page-title">{title}</h1>
            )
          }
          tags={editing && <SaveStatus state={state} />}
          content={
            editing
              ? undefined
              : state.tab === "workspace"
                ? "集中管理 MDL 模型，维护业务口径与发布版本。"
                : state.tab === "releases"
                  ? "管理固定版本与模型发布物，为宿主服务提供稳定的语义绑定。"
                  : state.tab === "guide"
                    ? "从物理数据到业务语义，逐步完成模型创建与发布。"
                    : "创建模型草稿，开始定义业务实体与指标口径。"
          }
          breadcrumbRender={editing ? false : undefined}
          breadcrumb={{
            items:
              state.tab === "workspace"
                ? [{ title: "工作空间" }, { title: "模型管理" }]
                : editing
                  ? [
                      {
                        title: (
                          <Button
                            type="link"
                            className="breadcrumb-workspace-link"
                            onClick={() => onAction("workspace")}
                          >
                            模型工作空间
                          </Button>
                        ),
                      },
                      { title },
                    ]
                  : [{ title: "工作空间" }, { title }],
          }}
          extra={
            state.tab === "workspace" ? (
              <Space className="workspace-page-actions">
                <Button
                  icon={<ImportOutlined aria-hidden="true" />}
                  onClick={() => onAction("import")}
                >
                  导入 MDL
                </Button>
                <Button
                  icon={<PlusOutlined aria-hidden="true" />}
                  onClick={() => onAction("new-draft")}
                >
                  新建模型草稿
                </Button>
                <Button
                  type="primary"
                  icon={<ThunderboltOutlined aria-hidden="true" />}
                  onClick={() => setAutoModelOpen(true)}
                >
                  自动建模
                </Button>
              </Space>
            ) : editing ? (
              <div className="admin-page-actions">
                <Tooltip title="草稿设置">
                  <Button
                    icon={<SettingOutlined aria-hidden="true" />}
                    aria-label="草稿设置"
                    onClick={() => onAction("settings")}
                  />
                </Tooltip>
                <Button
                  icon={<DownloadOutlined aria-hidden="true" />}
                  onClick={() => onAction("export")}
                >
                  导出
                </Button>
                <Button
                  icon={<SaveOutlined aria-hidden="true" />}
                  onClick={() => onAction("save")}
                >
                  保存
                </Button>
                <Button
                  icon={<CheckOutlined aria-hidden="true" />}
                  onClick={() => onAction("validate")}
                >
                  校验
                </Button>
                <Button
                  type="primary"
                  icon={<UploadOutlined aria-hidden="true" />}
                  onClick={() => onAction("publish")}
                >
                  发布版本
                </Button>
              </div>
            ) : undefined
          }
        >
          {state.tab === "workspace" ? (
            <WorkspaceList state={state} onAction={onAction} />
          ) : editing ? (
            <Tabs
              className="admin-editor-tabs"
              activeKey={state.tab}
              onChange={(tab) => onAction("tab", { tab })}
              destroyOnHidden
              items={tabs.map(([key, label]) => ({
                key,
                label,
                children:
                  key === state.tab ? (
                    <div className="admin-modeling-layout">
                      {state.tab !== "views" && (
                        <ModelNavigation state={state} onAction={onAction} />
                      )}
                      <div className="admin-modeling-content">
                        <NativeWorkspace
                          html={html}
                          onReady={onReady}
                          renderId={renderId}
                        />
                        <EditorFooter state={state} />
                      </div>
                    </div>
                  ) : null,
              }))}
            />
          ) : (
            <div className="admin-single-layout">
              <NativeWorkspace
                html={html}
                onReady={onReady}
                renderId={renderId}
              />
            </div>
          )}
        </PageContainer>
      </div>
      {autoModelOpen && (
        <AutoModelWizard
          request={request}
          onClose={() => setAutoModelOpen(false)}
          onCreated={(result) => {
            setAutoModelOpen(false);
            onGenerated(result);
          }}
        />
      )}
    </ProLayout>
  );
}
let renderId = 0;
export function renderAdmin(props) {
  flushSync(() =>
    root.render(
      <Provider>
        <AdminFrame {...props} renderId={++renderId} />
      </Provider>,
    ),
  );
}
function LoginPage({ message, onSubmit }) {
  return (
    <div className="admin-login">
      <header className="login-brand">
        <span className="admin-logo">
          <ApartmentOutlined aria-hidden="true" />
        </span>
        <strong>DataSemantic</strong>
        <Tag>MDL Studio</Tag>
      </header>
      <main className="admin-login-card">
        <div className="login-symbol">
          <DatabaseOutlined aria-hidden="true" />
        </div>
        <Typography.Title level={2}>登录建模工作台</Typography.Title>
        <Typography.Paragraph type="secondary">
          创建语义模型，连接数据与业务。
        </Typography.Paragraph>
        {message && (
          <div id="login-error" className="admin-login-error" role="alert">
            {message}
          </div>
        )}
        <Form
          layout="vertical"
          onFinish={(values) => onSubmit(values.password)}
          requiredMark={false}
        >
          <Form.Item
            name="password"
            label="管理密码"
            rules={[{ required: true, message: "请输入管理密码" }]}
          >
            <Input.Password
              id="password"
              prefix={<LockOutlined aria-hidden="true" />}
              placeholder="输入 Studio 管理密码"
              autoComplete="current-password"
              size="large"
            />
          </Form.Item>
          <Button type="primary" size="large" htmlType="submit" block>
            进入工作台
          </Button>
        </Form>
        <p className="admin-login-note">
          使用服务端配置的独立管理密码。
          <br />
          模型草稿保存在当前服务，可随时继续编辑。
        </p>
      </main>
      <footer className="admin-login-footer">DataSemantic · MDL Studio</footer>
    </div>
  );
}
export function renderLoginPage(props) {
  flushSync(() =>
    root.render(
      <Provider>
        <LoginPage {...props} />
      </Provider>,
    ),
  );
}
