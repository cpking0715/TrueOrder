# TrueOrder — 自家产品的海外买家库

## 一句话产品

给自家企业用的海外买家库与获客工具：以自家产品为入口，把授权海运提单数据按税号聚成「潜在客户 / 精准客户」名单并打分导出；对用户选定的企业补全官网与联系人联系方式（第一期）。不做注册计费、不对外售卖名单、不爬提单网站。开发信与按次查询补全服务按硬约束的受控规则执行。

## 技术栈实例化

- 后端：Python 3.13 + FastAPI + SQLAlchemy 2.0（同步，psycopg3）+ PostgreSQL 16（Docker，端口 5433）。
- 迁移：Alembic（`backend/alembic/`），schema 变更一律走迁移，`bootstrap` 只做 `upgrade head` + 种子。
- 前端：Vue 3 + TypeScript + Vite，pnpm 管理；类型由后端 OpenAPI 经 openapi-typescript 生成。
- 搜索：PostgreSQL 全文检索（`simple` 词典 + GIN 索引），不是外部搜索引擎。
- 分层：`backend/app/interface`（路由/DTO）→ `backend/app/domain`（纯业务，不 import 框架）← `backend/app/infrastructure`（SQLAlchemy/CSV 导入/FTS 实现 domain 定义的端口）。

## 常用命令

数据库（一次性）：

```bash
docker run -d --name trueorder-pg -e POSTGRES_USER=trueorder -e POSTGRES_PASSWORD=trueorder \
  -e POSTGRES_DB=trueorder -p 5433:5432 postgres:16-alpine
```

后端（`backend/` 目录下）：

```bash
uv sync                                   # 装依赖
uv run python -m app.bootstrap            # Alembic 升级到 head + 导入示例产品与非全量提单样本（幂等）
uv run uvicorn app.interface.main:app --reload --port 8000   # 起后端
uv run pytest -q                          # 日常测试（领域+基础设施+接口）
uv run pytest -q -m smoke                 # e2e 冒烟（默认命令不含）
uv run alembic -x url=<空基准库> revision --autogenerate -m "..."   # schema 变更生成迁移
```

前端（`frontend/` 目录下）：

```bash
pnpm install
pnpm gen:api      # 从 backend/openapi.json 生成 TS 类型（需先 uv run python -m app.export_openapi）
pnpm dev          # Vite 开发服务器，/api 代理到 8000
pnpm test         # Vitest（composable + 组件）
```

## 必测点

- 领域层（纯函数，零 mock）：公司名归一化与同名冲突判定；国家归一化；税号有效性；潜在/精准分层规则（24 个月、12 个月重复、供货方、业务词匹配）；六类排除（空抬头/银行/货代/集团内部/同行海外/税号误码）；每条得分理由必须带提单 id；快速建产品的表单校验与买家词默认兜底（build_quick_product/suggest_buyer_keywords）。
- 基础设施层（真 PostgreSQL，测试库 `trueorder_test`）：schema/UNIQUE 约束（企业名+国家、提单去重哈希）；CSV 导入幂等（二次导入 0 新增）与同文件重复行计 `duplicate_bills`；大 CSV 导入分批查重（PG 65535 参数上限）与批内公司缓存不改变归并/变体行为；打分候选池 24 个月窗口过滤；Alembic 迁移一致性（空库 upgrade ≡ ORM create_all）；FTS 能按词命中并支持 OR；并发建产品编号不重复（repo 层双会话）。
- 接口层（TestClient + dependency_overrides）：产品列表/详情；买家列表 tier 与筛选参数；导出 CSV 的表头、行数与公式注入转义（`= + - @` 及控制字符前缀加 `'`）；上传超限 413；提单导入端点；建产品只打分新产品（既有得分行不变）；同名同税号同受众 409；meta 的非全量样本声明；快速建产品端点（POST /api/products：建后立即有计数、校验 422、编码不冲突、默认词兜底可被覆盖）。
- 前端（Vitest + Testing Library）：筛选 composable 的参数构造与导出 URL；产品页潜在/精准页签切换的公司可见性；公司抽屉展示票数/最近日期/供货方/得分理由；空态；快速建产品表单（必填/税号校验、提交 payload、错误态）；批量补全两段式（估计→确认，0 家禁用、错误态）；抽屉查找/抓取按钮入队提示。
- 后台任务与补全（真 PostgreSQL）：任务队列认领互斥（两 worker 交错不重复）、退避/上限/僵死回收、永久失败不退避（robots/超日上限/公司不存在）；补全处理器（fake 注入）：域名发现高置信自动采用并写联系人、中低置信只写候选、额度超额拒绝、重复邮箱不重入；官网爬虫本地 HTTP 夹具（robots 拒、私网重定向拒、超大页弃、同站重定向跟随、SSRF 地址判定）；enrichment_calls 日上限与 30 天不重查；批量补全估计/确认/跳过规则。
- e2e 冒烟（`-m smoke` 或浏览器有记录的手动）：首页填产品提交 → 直接落到该产品客户结果页（计数非空）；产品列表 → 点进产品 → 两个页签 → 打开公司抽屉 → 看到提单证据 → 导出 CSV 内容校验；第一期获客闭环（选企业补全（fake）→ 联系人带来源写入 → 额度审计 → 联系人导出校验；批量补全估计与执行、跳过规则）。

## 硬约束

- 提单数据只来自用户上传的授权 CSV 与仓库内标注「非全量样本」的演示文件；界面必须展示非全量声明（`/api/meta`）。
- **不爬任何提单网站**；仅允许抓取企业自有官网的公开页面，须遵守 robots.txt 并限速。
- 按次查询源（Apollo / People Data Labs / Hunter / Google Places 等）**仅对用户选定的一批企业**调用补全（单个选中，或当前筛选的前 N 家且 N ≤ 当日剩余额度），结果必须带来源和时间；禁止无人触发的全库自动补全；有每日调用上限。
- 开发信只发给**已入库、有来源记录、不在抑制名单、且由用户明确触发或批准**的联系人；系统必须有每日上限且不可在界面一键关闭（第二期落地，护栏规格见 `docs/DEV-SPEC.md` 3.5）。
- 不改 `D:\MyProjects\GoodJob`。
- 得分/排除必须可解释：每条理由携带提单 id，界面能点回提单。
- 企业识别只用「规范化名称 + 国家」，同名冲突只标记 `same_name_conflict`，不自动合并。
- 凭据只走环境变量 / `.env`（`TRUEORDER_DATABASE_URL`、`TRUEORDER_HUNTER_API_KEY` 等 `TRUEORDER_` 前缀），源码与样本里不写生产凭据。
