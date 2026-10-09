# TrueOrder — 自家产品的海外买家库

## 一句话产品

给自家企业用的海外买家库：以自家产品为入口，把授权海运提单数据按税号聚成「潜在客户 / 精准客户」名单并打分导出。不做注册计费、不做开发信、不对外售卖名单、不爬提单网站、不把 Apollo / People Data Labs / Hunter / Google Places 等按次查询源灌入库。

## 技术栈实例化

- 后端：Python 3.13 + FastAPI + SQLAlchemy 2.0（同步，psycopg3）+ PostgreSQL 16（Docker，端口 5433）。
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
uv run python -m app.bootstrap            # 建表 + 导入示例产品与非全量提单样本（幂等）
uv run uvicorn app.interface.main:app --reload --port 8000   # 起后端
uv run pytest -q                          # 日常测试（领域+基础设施+接口）
uv run pytest -q -m smoke                 # e2e 冒烟（默认命令不含）
```

前端（`frontend/` 目录下）：

```bash
pnpm install
pnpm gen:api      # 从 backend/openapi.json 生成 TS 类型（需先 uv run python -m app.export_openapi）
pnpm dev          # Vite 开发服务器，/api 代理到 8000
pnpm test         # Vitest（composable + 组件）
```

## 必测点

- 领域层（纯函数，零 mock）：公司名归一化与同名冲突判定；国家归一化；税号有效性；潜在/精准分层规则（24 个月、12 个月重复、供货方、业务词匹配）；六类排除（空抬头/银行/货代/集团内部/同行海外/税号误码）；每条得分理由必须带提单 id。
- 基础设施层（真 PostgreSQL，测试库 `trueorder_test`）：schema/UNIQUE 约束（企业名+国家、提单去重哈希）；CSV 导入幂等（二次导入 0 新增）；FTS 能按词命中并支持 OR。
- 接口层（TestClient + dependency_overrides）：产品列表/详情；买家列表 tier 与筛选参数；导出 CSV 的表头与行数；提单导入端点；meta 的非全量样本声明。
- 前端（Vitest + Testing Library）：筛选 composable 的参数构造与导出 URL；产品页潜在/精准页签切换的公司可见性；公司抽屉展示票数/最近日期/供货方/得分理由；空态。
- e2e 冒烟（`-m smoke` 或浏览器有记录的手动）：产品列表 → 点进产品 → 两个页签 → 打开公司抽屉 → 看到提单证据。

## 硬约束

- 提单数据只来自用户上传的授权 CSV 与仓库内标注「非全量样本」的演示文件；界面必须展示非全量声明（`/api/meta`）。
- 不爬任何提单网站，不接按次查询数据源入库存。
- 不改 `D:\MyProjects\GoodJob`。
- 得分/排除必须可解释：每条理由携带提单 id，界面能点回提单。
- 企业识别只用「规范化名称 + 国家」，同名冲突只标记 `same_name_conflict`，不自动合并。
- 凭据只走环境变量 / `.env`（`DATABASE_URL`），源码与样本里不写生产凭据。
