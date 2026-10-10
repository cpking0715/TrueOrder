# TrueOrder — 自家产品海外买家库

给自家企业用的海外买家库：**以自家产品为入口**，把海运提单授权数据按税号聚成「潜在客户 / 精准客户」名单，打分可解释（每条理由点回提单），当前筛选可导出 CSV。

- 不做注册计费、不对外售卖名单；开发信与按次查询补全按受控规则执行（见 `AGENTS.md` 硬约束）。
- 不爬提单网站；仅允许抓取企业自有官网公开页（robots.txt + 限速）；
  按次查询源只对用户选定的企业调用补全，结果带来源与时间，有每日上限。
- 当前为**非全量公开样本**演示（页面有醒目声明）；正式使用需购买允许建索引的授权提单数据后走同一导入入口。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.13 + FastAPI + SQLAlchemy 2.0（psycopg3，同步） |
| 数据库 | PostgreSQL 16（Docker，端口 5433），全文检索用 `simple` 词典 + GIN 索引 |
| 前端 | Vue 3 + TypeScript + Vite（pnpm），类型由 OpenAPI 经 openapi-typescript 生成 |
| 分层 | `interface`（路由/DTO）→ `domain`（纯业务）← `infrastructure`（SQLAlchemy/CSV/FTS 实现端口） |

## 快速开始

### 1. 数据库（一次性）

```bash
docker run -d --name trueorder-pg -e POSTGRES_USER=trueorder -e POSTGRES_PASSWORD=trueorder \
  -e POSTGRES_DB=trueorder -p 5433:5432 postgres:16-alpine
```

连接串默认 `postgresql+psycopg://trueorder:trueorder@localhost:5433/trueorder`，
可用环境变量 `TRUEORDER_DATABASE_URL` 覆盖（也可指向本机已有 PostgreSQL）。

### 2. 后端

```bash
cd backend
uv sync
uv run python -m app.bootstrap     # Alembic 迁移到 head + 导入示例产品与非全量提单样本（幂等）
uv run uvicorn app.interface.main:app --port 8000
```

后端会自动托管 `frontend/dist`（若已构建），直接打开 <http://localhost:8000>。

### 2b. 后台任务 worker（联系人补全/官网抓取需要，WP3+）

```bash
uv run python -m app.worker        # 轮询执行任务队列；Ctrl-C 停止
uv run python -m app.worker --once # 只跑一轮（调试）
```

不启动 worker 时界面照常可用，只是补全任务停留在「待执行」；任务状态见界面右上「任务」页。

### 2c. 联系人补全（WP4，可选配置）

```bash
# backend/.env
TRUEORDER_HUNTER_API_KEY=...      # 不配置则用演示数据源（fake，来源标注可辨识）
TRUEORDER_ENRICH_DAILY_CAP=20     # 按次补全每日上限（合规约束，默认 20）
```

界面入口：公司抽屉「查找联系方式 / 抓取官网」按钮（单个企业），
或买家列表工具栏「补全当前筛选前 N 家」（两段式：先估计额度再确认执行）。
域名候选分置信度：高置信自动采用，中低置信需在抽屉里点「确认是官网」后才会继续查联系人。

### 3. 前端（开发模式）

```bash
cd frontend
pnpm install
pnpm gen:api    # 从 backend/openapi.json 生成 TS 类型（先在后端跑 uv run python -m app.export_openapi）
pnpm dev        # http://localhost:5173，/api 代理到 8000
pnpm build      # 产物由后端托管
```

## 核心概念

- **产品是入口**：目录里每个产品标明卖给谁（进口商 / 工厂 / 两者）和一个或多个税号。
  卖给工厂的产品税号填**原料**税号（如纸板 → 纸壳厂用 480810 瓦楞原纸，不用 4819 纸箱成品）。
- **潜在客户**：该税号近 24 个月、原产中国或越南、≥1 票的收货人。
- **精准客户**：潜在池中近 12 个月重复进口、供货方与税号对应、业务类型匹配的子集。
- **排除**：空抬头（TO THE ORDER OF）、银行抬头、货代、集团内部供货、同行海外公司、税号误码。
- **企业识别**：规范化名称 + 国家；同名冲突只标记（`同名冲突` 徽章），不自动合并。

## 第一期获客流程（填产品 → 找客户 → 拿联系方式）

1. **填产品**：首页表单填产品名 + HS 税号 + 卖给谁，提交即建产品并直接跳到客户结果页
   （潜在 / 精准 / 已排除三页签，点公司开抽屉看票数、供货方、得分理由与提单证据）。
2. **拿联系方式**：公司抽屉里「查找联系方式」（按官网/公司名调用补全服务）或「抓取官网」
   （只抓企业自有官网公开页）。没有官网的公司会先做**域名发现**：高置信自动采用，
   中低置信标黄等你在抽屉里点「确认是官网」。
   也可以在买家列表工具栏「补全当前筛选前 N 家」批量执行——先估计额度、确认后才入队，
   已有联系人的与 30 天内查过的自动跳过。
3. **worker 执行**：另开终端 `uv run python -m app.worker`；任务进度在界面右上「任务」页。
4. **导出**：买家列表可导出「当前筛选 CSV（全部买家）」与「当前筛选的联系人 CSV」
   （含姓名/职位/邮箱/电话/来源/官网，默认排除不再联系与无效邮箱）。

界面截图见 `.review/screenshots/`（01 首页 → 03 抽屉理由定位 → 08 任务页 → 09 联系人补全）。

补全服务的合规约束与数据来源说明见 `docs/OUTREACH-COMPLIANCE.md`；
Hunter 命中率手工评估（配 Key 后做一次）见 `docs/finder-eval.md`。

## 数据导入

界面「数据导入」面板或 API：

- 产品目录：`POST /api/products/import`（CSV 列 `code,name,description,buyer_type,hs_code,audience,note,buyer_keywords,peer_keywords`，一个产品可拆多行税号）
- 提单：`POST /api/bills/import`（CSV 列见 `backend/app/seed/sample_bills.README.md`，导入后自动重打分）

样本文件：`backend/app/seed/products.csv`、`backend/app/seed/sample_bills.csv`（非全量、公司名虚构，场景说明见同目录 README）。

> **升级注意（去重指纹变更）**：提单去重指纹的字段集在 2026-10-09 的提交 `aae6768` 中扩展过（纳入原产国/港口/数量、描述全量）。指纹算法变更后，**对旧库再次导入同一 CSV 会因哈希不同而双份入库**。已有数据的库升级代码版本后，请重建库（`uv run python -m app.bootstrap --drop` 后重导授权数据），不要在旧库上直接追加导入。

## 数据库迁移

schema 由 Alembic 管理（`backend/alembic/`）。`app.bootstrap` 会自动 `upgrade head`；
`create_all` 时代的旧库首次运行 bootstrap 会被无损标记（stamp）到当前 head。
schema 变更流程：改 ORM → 对空基准库 `alembic revision --autogenerate` → 跑迁移测试。

## 测试

```bash
cd backend && uv run pytest -q          # 领域 + 基础设施 + 接口（需 5433 测试库，自动创建）
cd backend && uv run pytest -q -m smoke # e2e 冒烟（默认命令不含）
cd frontend && pnpm test                # Vitest：composable + 组件（Testing Library）
```

冒烟（`-m smoke`）走：产品列表 → 产品详情（潜在/精准页签）→ 公司抽屉（票数/最近到港/供货方/理由带提单号）→ 导出 CSV 内容校验；
以及第一期获客闭环：选企业补全（fake 补全器）→ 域名与联系人自动写入 → 额度审计 → 联系人导出校验、批量补全估计与执行。

性能基准（合成数据 10 万–100 万行）见 `docs/perf.md`，工具在 `backend/tests/perf/`。
