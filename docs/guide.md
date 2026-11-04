# DataSemantic 使用与部署指南

[返回项目介绍](../README.md)

WrenAI Core SDK 的独立 HTTP 规划与只读查询服务。当前锁定 `wrenai==0.17.1`，底层引擎绑定为 `wren-core-py==0.8.2`，完整依赖见 `uv.lock`。

服务加载服务器预先发布的 MDL，将语义 SQL 转换为物理 SQL。规划 API 不执行业务查询，不需要业务库凭据、LLM Key 或向量库；可选的执行 API 使用服务端配置的只读账号执行物理 SQL。Studio 可使用管理员临时提供的只读连接扫描数据库元数据，辅助创建 MDL。

```text
Deep Agents → 宿主教育指标服务 → DataSemantic /plan
                                      ↓ 物理 SQL
                             宿主查询网关 → DataSemantic /execute → 数据库
                                          （或宿主自行执行）
```

宿主负责认证最终用户、工作空间及数据源授权、指标口径、实体绑定、执行授权与结果权限。服务令牌代表受信任的宿主后端，不代表最终用户的数据权限。不要把令牌或物理 SQL 接口直接开放给浏览器或模型。

## Docker 启动

在仓库根目录运行：

```bash
python3 scripts/init_env.py
docker compose up -d --build --wait
curl http://127.0.0.1:8090/health/ready
```

`init_env.py` 只在 `.env` 不存在时生成随机令牌，权限为 `0600`，不会输出令牌或覆盖已有文件。`.env` 已被 Git 与镜像构建上下文排除。部署到其他机器时重新生成令牌，调用方使用相同凭据。

默认只映射本机 `127.0.0.1:8090`。应用与本服务放在同一 Compose 网络时，应用使用 `http://wren-semantic:8090`，可以删除宿主端口映射。跨主机接入由内网入口提供 TLS 与服务身份校验。

```bash
docker compose ps
docker compose logs --tail=50 wren-semantic
docker compose down
```

镜像以非 root 身份运行，模型只读挂载，根文件系统只读；默认 2 CPU、2 GiB 内存、2 个规划槽位。单个规划在独立子进程中执行；超时或取消后杀死并回收子进程。这里没有另起一套 Wren 官方完整产品服务。

## 本地开发

需要 Python 3.11～3.13 与 uv。Docker 当前使用 Python 3.11。

```bash
python3 scripts/init_env.py
uv sync --locked --python 3.11
uv run --locked uvicorn wren_semantic.app:create_app --factory \
  --host 127.0.0.1 --port 8090 --workers 1 --env-file .env --no-access-log
```

另一个终端验证真实 HTTP 调用：

```bash
uv run --locked python scripts/smoke_http.py
```

这个冒烟脚本读取 `.env`，验证健康、鉴权、真实规划、版本冲突与非法 SQL；不会打印令牌或连接业务数据库。默认使用 `education-demo-v1`；替换模型后请同步调整脚本中的示例查询。

## MDL 前端创建工具

仓库内置 **MDL Studio**，整体后台框架采用 React + Ant Design 5 + ProLayout（Ant Design Pro），提供折叠导航、页面容器、面包屑、编辑标签页、统一操作区和中文表单。前端资源在本地打包，不依赖 CDN；仓库附带构建产物，直接启动 Python 服务即可使用。默认关闭，启用后访问 `/studio/`。

在 `.env` 中加入以下配置，并将占位内容替换为自选管理密码（至少 12 字符，不能与服务令牌相同）：

```dotenv
WREN_STUDIO_ENABLED=true
WREN_STUDIO_PASSWORD=替换为独立管理密码
WREN_STUDIO_DATA_DIR=.state/studio
```

本地启动方式与上方相同；打开 [MDL Studio](http://127.0.0.1:8090/studio/) 后使用管理密码登录。Compose 方式修改 `.env` 后运行 `docker compose up -d --build --wait`，草稿与发布版本保存在 `studio-data` 命名卷中。HTTPS 部署设置 `WREN_STUDIO_COOKIE_SECURE=true`，反向代理需正确转发请求协议与 Host，保持管理请求同源。

### 前端开发与构建

修改前端时，在 `frontend` 目录运行：

```bash
npm ci
npm run build
npm run check
```

需要 Node.js 22。`src/admin.jsx` 维护 Ant Design 后台框架，`src/studio-controller.js` 维护建模交互，`src/admin.css` 和 `src/editor.css` 维护界面样式。构建生成 `src/wren_semantic/static` 下的本地 JS/CSS 及依赖许可证；请一并更新构建产物。`editor.css` 在构建时限定于建模内容和对话框，避免覆盖 Ant Design 组件。Docker 多阶段构建会从锁定依赖自动重建前端，不将 Node.js 或开发依赖带入运行镜像。

每次 Studio HTML 响应为 Ant Design 动态样式生成独立 CSP nonce；脚本继续限制为同源静态文件。

### 工作空间列表管理

进入 Studio 默认展示模型工作空间列表。可以按模型名称或逻辑模型搜索，按数据库与发布状态筛选、排序并分页；点击“编辑”进入独立建模页，点击面包屑返回列表。

- **修改信息**：直接调整草稿名称和目标数据库类型，保留 MDL 内容。
- **更新 MDL**：从“更多”选择更新，上传 JSON 或粘贴 MDL；预览模型、字段和关联数量后确认替换，再进入编辑页校验。
- **删除与恢复**：删除草稿会移入回收站，可随时恢复；已发布版本保持可用。修改、替换、删除和恢复均检查草稿 revision，避免覆盖其他页面的新内容。

现有 SQLite 数据目录首次启动时自动增加回收站字段，保留已有草稿、发布版本和会话。

### 自动建模：数据库直连扫描

进入模型工作空间 → **自动建模 → 数据库直连**，支持 PostgreSQL 与 MySQL：

1. 填写主机、端口、数据库、只读用户名、密码与 TLS 模式；可点击“测试连接”。PostgreSQL 可选择物理 Schema，MySQL 扫描当前连接数据库。语义 Catalog / Schema 独立于物理命名空间。
2. 点击“连接并读取表清单”，按表名包含条件缩小范围，勾选 1～50 张表后点击“扫描选中表”。只读取基础表的字段类型、注释、非空约束、主键、唯一约束和外键，不读取业务行或导入视图。字段、类型和外键生成规则与 DDL 模式相同。
3. 选择字段，预览 MDL，并通过真实 Wren SDK 校验后创建新草稿。扫描完成即关闭连接并清空页面中的密码，生成过程使用扫描快照，无需重新连接。

Docker 部署时，连接本机数据库使用 **`host.docker.internal` + 数据库映射到宿主机的端口**；`127.0.0.1` 指向服务容器本身。同一 Docker 网络可使用数据库服务名和容器端口。直连扫描需要数据库允许该来源地址及账号连接。默认启用 TLS 加密，可选择系统可信 CA 的证书及主机名校验；本地未启用 TLS 的数据库可显式选择“不使用 TLS”。支持 TCP 连接，不接受连接字符串、Unix socket 或任意连接参数。

连接信息只用于当前扫描请求，通过子进程标准输入传递，不放入命令行、日志、草稿或 SQLite。数据库密码不保存在扫描快照中；快照仅含表结构，绑定当前登录会话，15 分钟后过期，退出登录或服务重启即失效。每个会话最多保留 4 份、服务最多 32 份快照。连接超时 5 秒、单次元数据查询约 8 秒、每项扫描总超时 30 秒；超时、取消或服务关闭会回收子进程与连接，同时最多运行 2 项扫描。

表清单最多显示 1000 张表，超出时请缩小表名筛选范围。每次扫描最多 50 张表、每表最多 500 个字段，注释最多保留 2000 字符，快照上限 1 MB。外键两端都需选中才生成关联；复合主键、自关联和无法识别的类型会提示复核。连接扫描不会执行导入的 DDL 或任意业务 SQL。

管理接口新增 `POST /studio/api/automodel/database/test`、`/database/tables` 和 `/database/scan`；生成接口接受当前会话的 `scan_id`，与 `ddl` 二选一，继续使用原有 Cookie 与 CSRF 校验。

### 自动建模：从 DDL 生成

在模型工作空间点击 **自动建模**，选择 PostgreSQL、MySQL 或 DuckDB，上传 UTF-8 建表 SQL 文件或粘贴 DDL。可点击“填入学情示例”体验三表建模。

1. **导入表结构**：填写草稿名称和语义 Catalog / Schema。物理表的 catalog、schema 由 DDL 解析，独立于语义命名空间。支持 `CREATE TABLE`、表与字段注释，以及 `ALTER TABLE ADD` 主键、唯一约束和外键。
2. **选择建模范围**：勾选表与字段，排除敏感或无关字段。字段类型自动映射；未识别类型必须手动选择语义类型或排除字段。可选择是否依据明确外键生成关联。
3. **确认并生成**：预览模型、主键、关联、提示和完整 MDL JSON，再点击“校验并创建草稿”。服务重新解析原始 DDL，按选择生成 MDL，并调用真实 Wren SDK 校验，通过后创建独立草稿并打开编辑器。

导入仅解析结构，不连接数据库、不执行 SQL，也不上传至外部 AI 服务。每次最多 500 KB DDL、50 张表，每表最多 500 个字段（包含关联导航字段）。请导出最终表结构，不要包含数据 `INSERT`、视图或 `CREATE TABLE AS SELECT`。索引、序列和数据库设置不参与 MDL，会提示跳过。DDL 内容只在此次向导与请求中使用，生成后持久化 MDL。

外键两端的表及字段均选中时才生成关联和导航字段；不会根据字段名猜测关联。自关联、缺失外键目标和复合主键会提示复核；当前编辑器仅支持 MDL 单字段主键，复合主键不伪装成单字段主键。业务指标、缺考处理等计算口径仍需在生成后补充。数据库类型转换、枚举和手动类型映射应在生成结果中复核。

对应管理接口为 `POST /studio/api/automodel/preview`（解析）、`/automodel/review`（按选择预览）、`/automodel/generate`（校验并创建），均使用现有 Studio 会话与 CSRF 校验。创建接口仅新增草稿，不替换已有草稿或发布版本。

### 手动创建模型

1. **新建草稿**：选择“学情分析示例”或“空白模型”，填写草稿名称和数据库方言。
2. **定义模型**：添加逻辑模型，映射物理 catalog/schema/table，或填写只读 `refSql`。例如将 `edu_analysis.dim_school` 映射为 `schools`。
3. **定义字段**：添加字段名、类型、业务说明和主键。同名物理列无需表达式；计算字段填写表达式并勾选“计算字段”。例如 `CASE WHEN score_status = 'valid' THEN score ELSE NULL END`。
4. **定义关联**：选择两个模型、基数、连接条件；在来源模型添加导航字段并选择该关联。教育模板已包含成绩到学校的多对一关系，以及表达式为 `school.name` 的计算字段 `school_name`。查询时直接使用 `school_name`，或在语义 SQL 中显式 JOIN 逻辑模型。
5. **保存与校验**：使用“保存”或 Cmd/Ctrl+S 保存草稿，再点击“校验”。校验覆盖结构与真实 Wren SDK 规划；问题附带 JSON 路径，可跳至源码查看。

“模型关联”画布按已配置的关联连接具体字段，并在两端标注 `1` / `N` 基数。点击连线或关系标签可高亮对应字段、查看条件并进入编辑；复合条件会逐一连接字段。支持缩放、适应宽度、拖动空白处平移，以及展开模型的其余字段。复杂条件使用模型级虚线展示，缺失模型会提示在下方关联明细中修正；未配置的关联不会根据字段名自动推断。

“语义视图”采用左侧列表、右侧详情布局，支持按名称、业务说明或 SQL 关键词搜索，选中后查看完整 SQL 并复制、编辑或删除。长 SQL 在详情区内滚动，编辑或保存草稿后保留当前视图选择。

视图详情中的“测试视图”会先保存当前草稿，再用 `SELECT * FROM "视图名" LIMIT 10` 调用真实 Wren SDK 规划，展示通过状态、耗时与物理 SQL，或返回错误原因。该测试不执行业务数据库查询；修改视图或模型定义后，旧测试结果失效，需要重新测试。
6. **SQL 预览**：输入语义 SQL，生成对应物理 SQL。例如 `SELECT school_name, AVG(valid_score) FROM student_subject_score GROUP BY school_name`。预览不执行查询。
7. **发布版本**：填写唯一 ID（如 `education-v2`）。系统再次校验，成功后在当前进程注册该版本；重启时从 Studio 存储恢复并进行启动验证。已发布内容不可修改。可下载包含 `mdl.json`、`registry.json` 的 ZIP，迁移到其他服务。

支持 JSON 文件/文本导入、当前 MDL 导出、语义视图、已发布版本复制为新草稿，以及保留自定义 MDL 属性的源码编辑。可视化编辑和 JSON 共享同一份草稿；JSON 有语法问题时会保留输入并阻止保存。草稿以 revision 检测并发修改，冲突时先导出当前内容，再重新加载服务器版本。

Studio 使用独立密码、HttpOnly/SameSite Cookie 和同源 CSRF 校验；浏览器不接触服务令牌。管理会话可读取物理映射，应只向模型管理员开放。管理 API 位于 `/studio/api`，服务端规划 API 继续使用 Bearer 认证。草稿和发布内容存储在 SQLite 中；请持久化并备份 Studio 数据目录，删除该目录或 Compose 卷会丢失其中的数据。

## HTTP 接口

以下 `/internal/v1` 接口均要求 `Authorization: Bearer <WREN_SERVICE_TOKEN>`。可传 `X-Request-ID`；响应也会返回关联 ID。服务日志仅记录请求 ID、方法、状态和耗时，不记录请求正文、SQL 或鉴权头。

| 方法与路径 | 用途 |
|---|---|
| `GET /health/live` | HTTP 进程存活 |
| `GET /health/ready`、`GET /health` | 模型已加载且启动时真实 SDK 规划探测通过 |
| `GET /internal/v1/bundles` | 发布物 ID、SHA-256、数据库方言 |
| `GET /internal/v1/bundles/{bundle_id}/context` | 逻辑模型、字段、描述与关联上下文 |
| `POST /internal/v1/plan` | 语义 SQL → 物理 SQL |
| `POST /internal/v1/execute` | 在服务端注册的数据源上执行只读物理 SQL |
| `GET /internal/v1/openapi.json` | 带 Bearer 安全声明的 OpenAPI 协议 |

单次规划请求：

```json
{
  "bundle_id": "education-demo-v1",
  "manifest_hash": "从 bundles 接口获取的 64 位 SHA-256",
  "semantic_sql": "SELECT AVG(valid_score) AS average_score, COUNT(valid_score) AS valid_count FROM student_subject_score WHERE exam_batch_id = 'exam_demo'"
}
```

响应字段：

```json
{
  "request_id": "关联请求 ID",
  "bundle_id": "education-demo-v1",
  "manifest_hash": "实际发布物 SHA-256",
  "dialect": "postgres",
  "physical_sql": "WITH student_subject_score AS (...) SELECT ...",
  "duration_ms": 200,
  "wrenai_version": "0.17.1"
}
```

上面的响应仅演示结构，耗时和 SQL 以实际返回值为准。`duration_ms` 包含子进程启动与 SDK 初始化。请求不能指定模型文件路径、MDL 内容、数据库凭据或随意切换方言；多余字段会被拒绝。

宿主 Python 调用示例：

```python
import os
import httpx

with httpx.Client(
    base_url=os.environ["WREN_BASE_URL"],
    headers={"Authorization": f"Bearer {os.environ['WREN_SERVICE_TOKEN']}"},
    timeout=20,
) as client:
    # 示例使用演示绑定；生产中由服务器维护工作空间/数据源/领域到发布物的授权绑定。
    response = client.get("/internal/v1/bundles")
    response.raise_for_status()
    bundle = next(b for b in response.json()["bundles"] if b["bundle_id"] == "education-demo-v1")
    response = client.post(
        "/internal/v1/plan",
        json={
            "bundle_id": bundle["bundle_id"],
            "manifest_hash": bundle["manifest_hash"],
            "semantic_sql": "SELECT AVG(valid_score) FROM student_subject_score",
        },
    )
    response.raise_for_status()
    physical_sql = response.json()["physical_sql"]
    # 将 physical_sql 交回宿主查询网关：落实最终用户权限后，调用 /execute 或自行执行。
```

宿主必须固定批准的 `bundle_id + manifest_hash`。版本不匹配时先重新审核绑定，不要自动接受新哈希并重试查询。

## 执行物理 SQL

`POST /internal/v1/execute` 支持 PostgreSQL、MySQL。默认未配置数据源时返回 `503 EXECUTION_DISABLED`。执行不需要 LLM，也不会重新调用 Wren 规划；宿主可以把 `/plan` 返回的 `physical_sql` 交给该接口。

### 配置数据源

复制 `config/execution-sources.example.json` 为 `config/execution-sources.json`，修改连接地址、端口、数据库、只读用户名与 TLS。配置结构如下：

```json
{
  "sources": [
    {
      "source_id": "education-pg",
      "dialect": "postgres",
      "host": "127.0.0.1",
      "port": 5432,
      "database": "education",
      "user": "analytics_reader",
      "password_env": "EDUCATION_DB_PASSWORD",
      "tls": "require"
    }
  ]
}
```

MySQL 将 `dialect` 改为 `mysql`，使用相应端口（通常为 3306）及数据库账号。可注册多个不同 `source_id`。`tls` 支持 `disable`、`require`（加密）和 `verify-full`（验证 CA 与主机名）。PostgreSQL 查询默认搜索路径为 `pg_catalog, public`；其他物理 Schema 请在 SQL 中显式指定。

在本地 `.env` 中设置以下变量，数据库密码使用自己的值：

```dotenv
WREN_EXECUTION_SOURCES_PATH=config/execution-sources.json
EDUCATION_DB_PASSWORD=替换为只读数据库密码
```

按原有 `uvicorn --env-file .env` 方式重启服务。密码变量由 `password_env` 指向，仅在启动时从进程环境读取；请求不能传数据库连接、密码或自选配置文件。数据源配置错误、重复 ID 或密码变量缺失会阻止服务启动。修改配置后需重启；健康检查只验证规划就绪，不探测执行数据库连接。

Docker 使用附带的 `compose.execution.example.yaml` 叠加配置，先创建上面的 JSON 并在 `.env` 中设置 `EDUCATION_DB_PASSWORD`：

```bash
docker compose -f compose.yaml -f compose.execution.example.yaml up -d --build --wait
```

该配置将 JSON 只读挂载至 `/config/execution-sources.json`，并显式注入密码环境变量。多数据源时请为每个 `password_env` 在 Compose `environment` 中补充对应变量。Docker 访问宿主机数据库请用 `host.docker.internal`。

### 请求与结果

```http
POST /internal/v1/execute
Authorization: Bearer <WREN_SERVICE_TOKEN>
Content-Type: application/json

{
  "source_id": "education-pg",
  "physical_sql": "SELECT school_id, AVG(score) AS average_score FROM edu_analysis.v_student_subject_score GROUP BY school_id",
  "max_rows": 1000
}
```

```json
{
  "request_id": "关联请求 ID",
  "source_id": "education-pg",
  "dialect": "postgres",
  "columns": ["school_id", "average_score"],
  "rows": [["school_1", "75.5000"]],
  "row_count": 1,
  "truncated": false,
  "duration_ms": 120
}
```

示例仅演示契约，表与结果取决于实际数据库。`columns` 与每行数组按位置对应，保留同名结果列；空结果保留列名。Decimal、超出 JavaScript 安全整数范围的整数转成字符串，日期时间用 ISO 字符串，二进制用 Base64，NaN/Infinity 用字符串表示。

`max_rows` 默认为 1000，范围为 1～10000。达到行数或结果字节上限时返回 `truncated: true`，`row_count` 是实际返回行数，不是总行数；单行或列元数据超过字节预算时返回 `422 RESULT_TOO_LARGE`，请缩小字段或查询范围。

执行仅接受单条只读查询，支持常见聚合、CTE、窗口函数；拒绝写入、锁定、多语句、会话变量、查询提示、带 Schema 的函数及未列入允许清单的函数。执行前移除注释并重新生成 SQL，避免 MySQL 可执行注释绕过检查。数据库使用只读事务，结果通过流式游标读取，每次执行在独立子进程中完成，超时或取消时终止并回收子进程与连接；数据库侧也设置语句期限。

执行接口是受信任后端的底层工具，不检查 MDL、发布物哈希或模型字段范围。宿主须维护用户→数据源→模型版本的授权绑定、检查物理 SQL 的行列权限，并为每个数据源配置最小权限只读账号。服务 Bearer token 可访问所有已注册执行源，不代表最终用户身份。SQL 检查不能替代数据库权限和函数执行权限。

## 模型发布

`models/registry.json` 是服务器端发布清单。每条记录包含：

```json
{
  "bundle_id": "education-demo-v1",
  "dialect": "postgres",
  "manifest_path": "education-demo-v1/mdl.json",
  "manifest_hash": "对应文件原始字节的 SHA-256"
}
```

当前接受 `postgres`、`mysql`、`duckdb` 方言；业务权限、实际执行及各数据库特有 SQL 仍需在宿主接入时分别验证。

发布流程：

1. 在模型工程维护、审核 MDL；使用锁定 SDK 的 `wren context build` 构建 `target/mdl.json`。
2. 复制到新的发布目录，例如 `models/education-v2/mdl.json`，不要覆盖在途任务引用的旧发布物。
3. 计算新文件哈希，将新记录加入 `models/registry.json` 的 `bundles` 数组。
4. 重启服务。它会验证路径、哈希、模型名称，并对每个逻辑模型/视图执行真实 `dry_plan` 启动探测。失败则不进入就绪状态。
5. 用业务标准题库验收，再切换宿主的授权绑定。模型构建/规划成功不能证明指标口径或业务数据正确。

计算 SHA-256：

```bash
python3 -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('models/education-v2/mdl.json').read_bytes()).hexdigest())"
```

服务在启动时将模型读入内存并固定为不可变快照，运行中不热加载文件修改；Studio 发布可注册新的不可变版本；模型文件路径不能逃出清单所在目录。未注册发布物返回 404，哈希不匹配返回 409。

**随附的是演示模型。** `edu_analysis.v_student_subject_score` 是拟议规范视图，当前没有创建、连接或迁移真实教育数据库。演示的 `valid_score` 把 `valid` 状态的真实零分保留，其余状态置空。正式口径及原始表映射需要结合业务确认。现有 `education_schema.json` 不能直接当作 Wren MDL 使用。

## 配置与错误

配置通过环境变量注入，本地开发由 uvicorn 的 `--env-file .env` 加载。Docker Compose 从 `.env` 读取对应变量。

| 配置 | 默认值 | 含义 |
|---|---|---|
| `WREN_SERVICE_TOKEN` | 必填 | 至少 32 字符，建议由脚本随机生成 |
| `WREN_REGISTRY_PATH` | `models/registry.json` | 模型清单，Docker 固定为 `/models/registry.json` |
| `WREN_PLAN_TIMEOUT_SECONDS` | 15 | 单次规划期限，包含进程启动 |
| `WREN_STARTUP_TIMEOUT_SECONDS` | 60 | 每个发布物启动探测的期限 |
| `WREN_MAX_CONCURRENT_PLANS` | 2 | 每个 API worker 可用的规划槽位 |
| `WREN_MAX_REQUEST_BYTES` | 65536 | 请求体上限，包含分块传输 |
| `WREN_MAX_MANIFEST_BYTES` | 4194304 | 本地 Settings 可设置的单个模型大小上限 |
| `WREN_EXECUTION_SOURCES_PATH` | 未设置 | 执行数据源 JSON 路径；未设置时关闭执行 |
| `WREN_EXECUTION_TIMEOUT_SECONDS` | 15 | 单次执行总期限，含启动、连接、读取结果 |
| `WREN_MAX_CONCURRENT_EXECUTIONS` | 2 | 每个 API worker 的执行槽位 |
| `WREN_EXECUTION_MAX_RESULT_BYTES` | 4194304 | 单次执行结果字节预算，最大 16 MiB |
| `WREN_HTTP_PORT` | 8090 | Compose 映射的本机端口 |

语义 SQL 最长 50,000 字符，必须为单条只读查询；启用严格模型范围、关闭回退，并对展开后的 SQL 再检查只读。拒绝 DDL、DML、SELECT INTO、锁定查询、多语句和未建模表。它仍不能替代宿主数据权限、函数策略或数据库只读账号。

| HTTP | 错误码示例 | 调用方处理 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 修正服务身份 |
| 404 | `BUNDLE_NOT_FOUND` | 检查发布与授权绑定 |
| 409 | `MODEL_VERSION_MISMATCH` | 检查版本，重新审核绑定 |
| 413 | `REQUEST_TOO_LARGE` | 缩小请求 |
| 422 | `INVALID_REQUEST`、`INVALID_SQL`、`PLANNING_FAILED` | 修正需求/模型/SQL；规划错误可附安全的 SDK 错误码 |
| 503 | `PLANNER_BUSY` | 无排队槽位，按 `Retry-After` 退避 |
| 504 | `PLANNING_TIMEOUT` | 工作进程已终止，检查查询复杂度或服务资源 |
| 403 | `DB_PERMISSION_DENIED` | 检查数据库只读账号权限 |
| 404 | `SOURCE_NOT_FOUND` | 检查服务端注册的数据源 ID |
| 422 | `QUERY_FAILED`、`RESULT_TOO_LARGE` | 修正 SQL 或缩小结果范围 |
| 502 | `DB_AUTH_FAILED`、`DB_EXECUTION_FAILED`、`EXECUTION_FAILED` | 检查数据库配置、连通性与工作进程 |
| 503 | `EXECUTION_DISABLED`、`EXECUTOR_BUSY` | 配置数据源或稍后重试 |
| 504 | `EXECUTION_TIMEOUT` | 缩小查询范围或检查数据库负载 |
| 500 | `WORKER_FAILED` | 定位运行环境与原生进程故障 |

错误格式为 `{"error":{"code":"...","message":"..."},"request_id":"..."}`。不返回原始 SDK 异常、文件路径、SQL 或凭据。默认一台服务一个 API worker；增加 worker 会按进程放大规划并发和资源消耗。每个请求创建工作进程，优先保证隔离和硬超时，当前没有长期引擎池或规划缓存。

## 验证

```bash
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest -q
uv run --locked python scripts/smoke_http.py
```

测试使用真实官方 SDK，覆盖 HTTP 鉴权、模型哈希与路径限制、只读/模型范围、CTE、实际展开 SQL 的演示数值对账，以及超时/取消时的真实子进程回收和并发拒绝。数值对账在独立的内存 DuckDB 中完成，不访问业务库。Starlette 当前会对测试用 httpx 兼容层发出弃用提示，不影响测试结果。

执行集成测试为显式启用项：`EXECUTION_TEST_DATABASES=1 EXECUTION_TEST_READER_PASSWORD=<隔离测试库密码> uv run --locked pytest tests/test_execution_integration.py -q`。测试要求独立 PostgreSQL（15444）与 MySQL（13318）测试库 `execute_test`、只读账号 `execute_reader`、含三行样例的 `scores` 表以及含 1～100 的 `numbers(n)` 表；覆盖真实结果类型、聚合、重复列、空结果、行数/字节截断、错误脱敏与超时后的恢复，不使用业务库。

上游依据：[WrenAI](https://github.com/Canner/WrenAI)、[SDK 引擎接口](https://github.com/Canner/WrenAI/blob/main/core/wren/src/wren/engine.py)、[MDL 说明](https://github.com/Canner/WrenAI/blob/main/docs/core/concepts/what_is_mdl.md)。此服务的 HTTP 路由与发布协议为本项目自建。
