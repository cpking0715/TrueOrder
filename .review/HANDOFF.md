# Handoff — TrueOrder 自家产品海外买家库（v0.1）

## 任务

按计划文件 `品类客户汇聚平台_e63b6abd.plan.md` 在 `D:\MyProjects\TrueOrder` 从零实现「自家产品的海外买家库」：PostgreSQL 表（产品/原始提单/企业/产品税号对应/得分与排除）、产品与提单 CSV 导入、按买家类型打分（潜在/精准 + 六类排除）、以产品为入口的界面（潜在/精准页签、公司抽屉、当前筛选导出）、PostgreSQL 全文检索。不改 GoodJob；不接 Apollo / People Data Labs / Hunter / Google Places 入库；不爬提单网站；不做注册计费与开发信。

## 已实现（与计划的对应关系）

| 计划 todo | 对应实现 |
| --- | --- |
| scaffold：应用与 PostgreSQL 表 | `backend/app/infrastructure/orm.py`：`products` / `product_hs_codes` / `companies` / `raw_bills` / `company_scores`。企业键 = 规范化名称 + 国家（UNIQUE），同名冲突仅置 `same_name_conflict` 标记，不合并。 |
| catalog：产品目录 CSV 导入 + 两个示例 | `POST /api/products/import` 与 `python -m app.bootstrap`；`backend/app/seed/products.csv` 预置 P-GARMENT（成衣 620462，卖给进口商）与 P-BOARD（瓦楞纸板 480810 卖给纸壳厂，note 明示「用原料税号 480810，不是纸箱成品 4819」）。 |
| ingest：提单 CSV 导入器 + 公开样本 + 页面标明非全量 | `POST /api/bills/import`（企业归并 + 去重哈希 + 自动重打分）；`backend/app/seed/sample_bills.csv`（26 票，公司名虚构、字段结构对齐美国提单公开样本，场景对照表见 `sample_bills.README.md`）；`/api/meta` 返回非全量声明，前端每页顶部展示黄色横幅。 |
| score：按买家类型打分 + 排除 | `backend/app/domain/scoring.py` 纯函数：潜在 = 该税号近 24 个月、原产 CN/VN、≥1 票；精准 = 其中近 12 个月重复进口 + 供货方与税号对应 + 业务词匹配；排除 EX_BLANK_CONSIGNEE / EX_BANK / EX_FORWARDER / EX_RELATED_PARTY / EX_PEER_OVERSEAS / EX_HS_INVALID；每条 `ScoreReason` 携带 `bill_ids`，界面点回提单。 |
| ui：产品入口 + 潜在/精准页签 + 抽屉 + 导出 | 前端（Vue3+Vite+TS）：`#/` 产品列表（含导入面板）→ `#/products/:id` 详情页（潜在/精准/已排除三页签 + 受众切换 + FTS 搜索 + 国家/票数/排序筛选 + 导出当前筛选 CSV）；公司抽屉展示票数、最近到港、供货方、得分理由（提单号 chip）与票据明细。 |
| 快速建产品（用户反馈追加）：填产品找客户 | 主交互改为「我填产品 → 系统找客户」：`POST /api/products`（`ProductCreateIn`：名称/税号/受众，买家词选填）→ `domain/parse.build_quick_product`（校验 + 未填买家词时按受众给默认词，both 拆两类受众税号）→ `repo.next_quick_code()` 生成 QUICK-000n 编码 → upsert 后立即重打分 → 返回带计数的产品；前端首页（`ProductsView.vue` + `QuickStartForm.vue`）表单提交后直接跳到该产品的客户结果页。CSV 导入保留为批量/高级入口。数据源不变：仍只匹配已导入的授权提单库，不接任何外部查询源。 |

计划中的显式要求逐条核对：

- 产品是入口而不是税号入口 ✔（路由与页面均以产品聚合）
- 工厂产品用原料税号 ✔（480810 而非 4819；4819 票不会入纸板池，样本里有专门演示行）
- 样本页标明非全量 ✔（`/api/meta` + 前端横幅 + 种子 README）
- 排除规则生效 ✔（六类各有领域测试与样本演示行）
- 得分能回到提单 ✔（reasons.bill_ids → 抽屉提单表）
- 没有把按次查询源灌进库 ✔（无任何外部查询代码路径）

## Diff 基线

- 本仓库开工时为空（无父提交可作 base）。
- base=<空仓库> head=6d07903
- 审阅范围命令：
  - 根提交（后端全部新文件）：`git show 2e4b7a2`
  - 其余（前端/文档/修正）：`git diff 2e4b7a2..6d07903`
- `git status`：干净（无未提交变更）。
- 提交历史：`2e4b7a2`（后端）→ `a66c031`（前端+修复+README）→ `6d07903`（忽略构建产物）。

## 改动文件（关键路径）

```
backend/
  app/core/config.py                 # TRUEORDER_* 环境变量（数据库 URL、样本声明）
  app/domain/                        # 纯业务：entities / normalize / scoring / parse / ports / services
  app/infrastructure/                # orm / db / repositories / queries(FTS) / importers(CSV)
  app/interface/                     # main / deps / schemas(DTO) / mapping / routers(meta|products|bills)
  app/bootstrap.py                   # 建表 + 种子导入（幂等，--drop 重建）
  app/export_openapi.py              # 导出 openapi.json 供前端生成类型
  app/seed/                          # products.csv / sample_bills.csv / sample_bills.README.md
  tests/domain|infra|interface/      # 112 个测试
frontend/
  src/api/                           # client + products（类型来自 openapi-typescript 生成的 schema.d.ts）
  src/features/products/             # views(ProductsView/ProductDetailView) + components(8个) + composables/useBuyerFilters
  src/components/NoticeBanner.vue
  tests/                             # 14 个 Vitest（composable 直测 + Testing Library 组件测试）
AGENTS.md / README.md / .gitignore
```

## 如何启动

```bash
# 0) PostgreSQL（一次性；也可用本机已有实例，改 TRUEORDER_DATABASE_URL 即可）
docker run -d --name trueorder-pg -e POSTGRES_USER=trueorder -e POSTGRES_PASSWORD=trueorder \
  -e POSTGRES_DB=trueorder -p 5433:5432 postgres:16-alpine

# 1) 后端：建表 + 种子 + 起服务
cd backend
uv sync
uv run python -m app.bootstrap
uv run uvicorn app.interface.main:app --port 8000

# 2) 打开 http://localhost:8000 （后端自动托管 frontend/dist）
#    开发模式前端：cd frontend && pnpm install && pnpm dev  （5173，/api 代理 8000）
```

样本导入步骤（界面）：首页「数据导入」面板 → 「导入产品 CSV」选 `backend/app/seed/products.csv` → 「导入提单 CSV」选 `backend/app/seed/sample_bills.csv`（可选填 as_of 固定打分基准日，缺省今天）→ 导入后自动重打分并刷新。命令行等价：`uv run python -m app.bootstrap`（幂等，重复执行重复票计 0 新增）。

授权数据接入：拿到允许建索引的提单 CSV 后走同一入口（`POST /api/bills/import` 或界面），无需改代码；同时应把 `TRUEORDER_SAMPLE_MODE=false` 关掉非全量横幅。

## 测试（跑过的命令与输出）

| 命令 | 结果 |
| --- | --- |
| `cd backend && uv run pytest -q` | **112 passed**, 1 warning in 6.65s（领域 78 / 基础设施 19 / 接口 15；依赖 5433 上的 PostgreSQL，测试库 `trueorder_test` 自动重建） |
| `cd backend && uv run ruff check app tests` | All checks passed! |
| `cd frontend && pnpm test` | **14 passed**（composable 6 + 组件 8；jsdom，注入假 api 模块） |
| `cd frontend && pnpm lint` | 0 errors 0 warnings |
| `cd frontend && pnpm build` | vue-tsc 类型检查通过，vite 构建成功 |
| `uv run python -m app.bootstrap`（开发库） | 26 票导入，P-GARMENT 潜在2/精准1/排除6，P-BOARD 潜在2/精准2/排除0 |

主链路冒烟（Chrome 实测，动到主链路故本轮必跑）：产品列表（非全量横幅 + 两产品卡）→ 成衣详情潜在/精准页签切换 → 点击 BROOKLYN APPAREL 打开抽屉（票数 3、最近到港 2026-09-01、供货方、四条理由全部带「提单 #1/#2/#3」）→ 纸板详情（工厂受众、GREAT LAKES/PACIFIC BOX 精准、UNION PACKAGING 同名冲突标记）→ 搜索 carton 命中 PACIFIC BOX & CARTON → 排除页签六类齐全 → `export.csv` 内容核验（表头 + 理由含提单号）。冒烟中发现并修复两个前端缺陷（见下）。

修 bug 纪录（均为先红后绿）：

1. 同组件路由切换（产品1→产品2）不刷新受众与列表，纸板页残留成衣数据。复现测试：`路由在产品间切换时受众与列表跟随新产品`。修复：watch(productId) 重置受众并重载。
2. 逐字符搜索的响应竞态：过期响应覆盖新结果（搜索 carton 显示 0 家）。复现测试：`搜索的过期响应不覆盖新响应`。修复：请求序号守卫，过期响应丢弃。

追加轮（快速建产品，2026-10-10）测试输出：

| 命令 | 结果 |
| --- | --- |
| `cd backend && uv run pytest -q` | **135 passed**, 1 warning in 7.69s（新增：领域 7 条 build_quick_product/suggest_buyer_keywords、接口 7 条 POST /api/products） |
| `cd frontend && pnpm test` | **23 passed**（新增 QuickStartForm 5 条：必填校验、税号校验、提交 payload、默认词留空、API 错误态） |
| `cd frontend && pnpm lint` + `vue-tsc --noEmit` | 0 错误（QuickStartForm 超 150 行，样式挪入 main.css 后达标） |
| Playwright 冒烟（Chrome 无头，`smoke_quickstart.py`） | 首页表单可见 → 填「儿童棉质运动套装/620462/APPAREL;CLOTHING」提交 → 落到 `#/products/5`，页签 `潜在客户（2）| 精准客户（1）| 已排除（6）` ✔ |

## 已知假设与未验证项

- **样本性质**：`sample_bills.csv` 为演示构造（公司名虚构、日期以 2026-10 为基准），非真实授权数据；打分窗口滚动，距基准太久后重新导入，精准/潜在划分会漂移（预期行为，README 已注明）。
- **FTS 生成列**：PG 的 `array_to_string` 是 STABLE 不能进生成列，故企业检索源文本单独存 `search_text` 列、由导入器维护；直接 SQL 改 `name_variants` 不会刷新向量（走导入器则一致）。
- **启发式规则**：货代/银行/同行词表、集团内部判定（同名/剥地理词/包含）、城市猜测均为 v1 启发式，领域常量可调；换真实数据后可能需要扩词表。
- **供货方国家**：CSV 无 `shipper_country` 时按原产国推断，中国发货人从越南出貨会拆成两个企业实体（名称+国家键），样本 CSV 已显式填 CN 规避。
- **冒烟为浏览器手动（有记录）**，未搭 Playwright e2e；`-m smoke` marker 已注册但暂无用例。

## 未做项（明确不在 v1 / 留待后续）

- 不做注册计费、开发信（计划明示）。
- 无登录/权限/多用户；`both` 受众切换已支持但样本未含 both 产品。
- 无企业手动合并/拆分界面（同名冲突只标记，符合计划）。
- 无增量授权数据对接（购买后走同一 CSV 入口即可）。
- 前端未做 i18n/移动端深度适配；后端无分页游标（列表 limit≤500）。

## Review 焦点

建议重点独立检查：

1. `app/domain/scoring.py` 的分层与排除顺序（空抬头→银行→货代→入池→同行→集团内部→误码）是否符合「计划原文」语义，尤其 EX_PEER_OVERSEAS 的关键词逻辑。
2. `queries.py` 的买家查询：FTS 条件与 tier/country/min_shipments 组合是否有 SQL 语义漏洞（如 FTS 与 join 的行数膨胀）。
3. `importers.py` 去重哈希字段选择（arrival+双方规范化名+税号+提单号+描述前80字符）在真实数据下的误合并/误区分风险。
4. 前端 `useBuyerFilters` 的参数构造与导出 URL 是否与列表请求完全一致（导出「当前筛选」的等价性）。
5. 非全量声明链路：`/api/meta` → 前端横幅 → 样本 README，三处口径是否一致且不可被误当全量库使用。

---

# Findings 台账（Cursor 独立审阅 2026-10-09，处理记录）

审阅原文：`.review/cursor-findings.txt`（7 条：F1-F5 P1，F6-F7 P2）。逐条独立判断后处理如下；每条修复均有先红后绿的复现/回归测试。

| 编号 | 严重度 | 结论 | 处理 |
| --- | --- | --- | --- |
| F1 理由未真正点回提单（chip 无交互、提单表无单号列） | P1 | **成立，fixed** | `BillTable` 增加「提单号 + #id」列与 `bill-row-{id}` 锚点；`ReasonList` chip 改为可点击按钮，点击后滚动定位并高亮对应提单行 2.5s。组件测试 `点击理由里的提单号会高亮定位对应提单行`；浏览器实测点击「提单 #3」→ `bill-row-3` 高亮。 |
| F2 EX_PEER_OVERSEAS 被买家词子串击穿（PAPER ⊂ PAPER MILL，种子配置即中招） | P1 | **成立，fixed** | `scoring.py`：被同行词包含的买家命中视为伪命中（`real_buyer_hits`），同行排除与 BUSINESS_MATCH 均改用真命中。领域回归 `买家词只是同行词的子串时是伪命中仍排除`（ATLANTA PAPER MILL 场景）。词表本身保留 PAPER（对纸品加工商是合理买家词），语义漏洞由逻辑修复封死。 |
| F3 去重指纹：法律后缀折叠 + 缺字段导致真实数据误合并 | P1 | **成立，fixed** | 指纹纳入原产国/港口/数量，货物描述完整参与（不截 80 字符）。4 个领域回归（数量/港口/原产国/长描述差异）。法律后缀折叠保留——与企业识别键（规范化名+国家）一致，属有意设计。**注意**：指纹算法变更后，对已导入旧数据的库再次导入同一文件会双份入库；开发库已 `--drop` 重建，正式库换版时需重建或清空重导。 |
| F4 列表默认 limit=50 与导出 100000 不等价 | P1 | **成立，fixed** | 列表请求 `limit=500`（`BUYERS_PAGE_LIMIT`）；当 `items.length < total` 时显示「已显示前 N 家（共 T 家），导出 CSV 含全部筛选结果」提示；导出按钮文案与 title 明确「全部」。组件测试 `列表被截断时显示截断提示` + `结果未截断时不显示截断提示`。未实现真分页（v1 范围外，已在未做项注明）。 |
| F5 both 受众：抽屉得分与页签计数未按 audience 区分 | P1 | **成立，fixed** | 后端：`product_tier_counts` 按 (product, audience) 分层，`ProductOut` 新增 `counts_by_audience`（`counts` 保持总和供卡片）；`/api/companies/{id}` 新增 `audience` 参数过滤得分。前端：页签计数用 `counts_by_audience[当前受众]`，抽屉传 audience。接口测试 2 条 + 组件测试 1 条。**连带发现并修复**：`parse.py` 合并 both 产品多行时买家/同行关键词只取首行——改为跨行并集（领域回归 `多行产品的关键词合并而不是取首行`），此为审阅未直接命中的同域缺陷。 |
| F6 货代词表过宽（CARGO/LOGISTICS/FREIGHT 单词即排除） | P2 | **部分成立，部分采纳** | 移除 `CARGO`（服装品牌常用词，误伤面最大；领域回归 `名称仅含CARGO不视为货代`）。保留 `LOGISTICS`/`FREIGHT`：名称含这两个词的收货人在提单语境下绝大多数为 3PL/货代，收益大于误伤；词表是 `scoring.py` 顶部常量，接入真实数据后可校准。 |
| F7 bootstrap 未固定 as_of，样本分层随「今天」漂移 | P2 | **成立，fixed** | `bootstrap.py` 新增 `SEED_AS_OF = 2026-10-09`（与样本设计基准一致），种子导入固定用该基准日；界面/API 导入不受影响仍可指定。 |

处理后的验证（2026-10-09）：

| 命令 | 结果 |
| --- | --- |
| `cd backend && uv run pytest -q` | **121 passed**（原 112 + 新增回归 9） |
| `cd backend && uv run ruff check app tests` | All checks passed! |
| `cd frontend && pnpm test` | **18 passed**（原 14 + 新增 4） |
| `cd frontend && pnpm lint` / `pnpm build` | 0 errors / 构建成功 |
| `uv run python -m app.bootstrap`（幂等） | 重复导入 0 新增；分层与首版一致（成衣 2/1/6、纸板 2/2/0） |
| 浏览器冒烟 | 抽屉提单号列可见；点击「提单 #3」→ `bill-row-3` 高亮；页签/计数正常 |

---

# 第二轮复审记录（Cursor 2026-10-09，对修复轮 aae6768 的复核）

复审原文：`.review/cursor-recheck.txt`。结论：**F1-F7 全部 verified，未发现新 P0/P1，修复轮可交付**。3 条 P2 处理如下：

| 编号 | 问题 | 结论 | 处理 |
| --- | --- | --- | --- |
| F1' 货代词表注释与实现不符（注释称 LOGISTICS 不纳入，实际保留） | P2 | 成立 | 注释改为如实描述：已移除 CARGO；保留 LOGISTICS/FREIGHT 及理由。 |
| F2' 前端测试未锁定列表 limit=500 | P2 | 成立 | `默认展示潜在客户` 用例补 `expect.objectContaining({ tier, limit: 500 })`，参数回退会被测到。 |
| F3' 指纹变更缺升级告警/文档 | P2 | 成立 | README「数据导入」节写明升级步骤：已有库升级后须 `--drop` 重建重导，不要旧库追加导入。（导入时自动检测指纹版本属过度工程，文档化即可） |

处理后复跑：后端 `uv run pytest -q` 121 通过、ruff 0 错；前端 `pnpm test` 18 通过、ESLint 0 错。

---

# Handoff — TrueOrder WP0 地基与边界（DEV-SPEC 4.1–4.4，2026-10-10）

## 任务

按 `docs/DEV-SPEC.md`（v0.2）实施 WP0：七项 P1 缺陷修复、Alembic 迁移体系、性能评估与必要的性能修复、约束文档修订、smoke 冒烟与 CI。第一期范围（WP1/WP3/WP4/WP7）不在本轮。

## 已实现

1. **4.1 缺陷修复**（每项先写失败测试再修）：
   - 同文件重复行：`import_bills` 循环内把新插入的 `bill_hash` 加入已见集合，重复行计 `duplicate_bills` 不再炸 UNIQUE。
   - CSV 公式注入：新增 `interface/csv_safety.py::sanitize_csv_cell`（`= + - @` 及 \t\r\n 前缀加 `'`），导出全列接入。
   - 上传上限：`Settings.max_upload_mb`（默认 20），产品/提单导入端点超限 413。
   - 建产品只打分新产品：`CsvImporter.rescore_one`，`create_product` 改用它；既有产品得分行 id/computed_at 不变（接口测试锁定）。
   - 并发建产品：`SqlProductRepository.create_quick`（撞号回滚换号重试×3）+ `find_quick_duplicate`（同名同税号同受众 409 带既有 id）。并发测试在 infra 层双线程双 Session 真并发。
   - 打分窗口：`BuyerPoolReader.load_pool(families, as_of)` 端口签名变更，SQL 侧 `arrival_date >= months_before(as_of,24)`，窗外提单不进候选。
   - 杂项：`product_row_to_out` 下沉 mapping；`get_product_buyer_type` 单产品查询；抽屉 `bills_truncated`（fetch limit+1）；导出改真流式 generator。
2. **4.2 迁移**：Alembic 接入（`backend/alembic/`），基线迁移（5 表+约束+生成列）+ 表达式索引迁移；`bootstrap` 改 `upgrade head`，create_all 旧库自动 stamp；删空包 `backend/src/`，pyproject 去 scripts/build-system。
3. **4.4 性能**：`tests/perf/gen_bills.py` + `bench.py`，10万/50万/100万三档实测入 `docs/perf.md`。评估中发现并修复两个真缺陷：大 CSV 查重超 PG 65535 参数上限（分批 5 万）；导入逐行公司查询 20 万次往返（批内公司缓存，186s→36s，缓存命中仍走变体更新分支）。100 万行打分 49s 超 30s 目标，已记录优化路径不提前优化。
4. **4.3 文档与 CI**：AGENTS.md 约束修订（受控开发信/补全、官网抓取规则、TRUEORDER_ 前缀、必测点补本轮切片）；README 同步；`docs/OUTREACH-COMPLIANCE.md`（第一期部分）；`tests/smoke/` 2 例（补上 smoke 0 用例缺口）；`.github/workflows/ci.yml`（backend/frontend/schema 一致性三 job）。

## Diff 基线

base=1351d68  head=7266ca6
审阅范围命令：git diff 1351d68...7266ca6

## 改动文件

后端核心：`infrastructure/{importers,repositories,queries,orm}.py`、`domain/{ports,services}.py`、`interface/routers/{products,bills}.py`、`interface/{mapping,schemas,csv_safety}.py`、`core/config.py`、`bootstrap.py`、`alembic/`（2 迁移）。
测试：`tests/infra/{test_importer,test_queries,test_migrations}.py`、`tests/interface/{test_api,test_csv_safety}.py`、`tests/smoke/`、`tests/perf/`。
文档与 CI：`AGENTS.md`、`README.md`、`docs/{perf.md,OUTREACH-COMPLIANCE.md}`、`.github/workflows/ci.yml`、`frontend/src/api/schema.d.ts`（重新生成）+1 测试 mock 补字段。

## 测试

- `uv run pytest -q` → **151 passed**（基线 135 → +16 新用例）
- `uv run pytest -q -m smoke` → **2 passed, 151 deselected**
- `uv run ruff check .` → All checks passed
- `pnpm test` → **25 passed**；`pnpm exec eslint .` / `vue-tsc --noEmit` → 通过
- `uv run python -m app.bootstrap` 实跑：旧库 stamp → head → 种子幂等（重复 26 票）
- 性能：10万/50万/100万三档 bench 实跑，数据在 `docs/perf.md`

## 已知假设与未验证项

- **CI 未实跑**（本地无 GitHub Actions 环境）：workflow 语法经人工核对，`uv sync --locked`/`gen:api`/`git diff --exit-code` 三步已在本地实跑验证等价命令。
- 100 万行打分 49s 超 DEV-SPEC 目标 30s：按规格「不提前优化」处理，优化路径已写入 perf.md（聚合下推 SQL 或分批装载）。
- `.zcodeignore`（未跟踪）是 ZCode 工作区索引配置，有意不提交、不删除，由用户决定去留。
- 打分窗口 24 个月：窗外提单的公司完全退出候选（含 excluded 也不出现）——这是规格 4.1.6 的字面要求，行为变化已被新测试锁定；如需「窗外仅退出精准、仍显示历史」需另立需求。

## Review 焦点

1. **导入缓存的并发与语义**：`_upsert_company` 的批内缓存（`importers.py`）在 variant 新增路径上是否与无缓存版行为完全等价（同名不同写法、同名冲突重算）。
2. **打分窗口端口变更**：`load_pool(families, as_of)` 语义是否会误伤既有调用方；窗口边界（正好 24 个月）的含闭区间判断。
3. **并发重试**：`create_quick` 的 rollback 时机是否会把同事务内的其他未提交改动一并回滚（create_product 端点里 upsert 前无其他写，但请独立核查）。
4. **公式注入**：转义前缀集合是否够（`= + - @ \t \r \n`）；`sanitize_csv_cell` 对非字符串（date/int）的处理。
5. **迁移一致性测试**的强度：`test_迁移后ORM建表为空操作` 只比表集合，不比列/索引/约束级差异，是否可接受。
6. CI workflow 的 PG 服务与 conftest 建库权限（POSTGRES_USER 即 superuser）假设。

## Findings 台账（Claude Code 独立审阅 2026-10-10，对 7266ca6；修复轮 9261b99）

审阅产出 7 条（1 major / 6 minor），逐条独立核实后处理：

| 编号 | 严重度 | 结论 | 处理 |
| --- | --- | --- | --- |
| F1 `.zcodeignore` 被一并提交（HANDOFF 声称未跟踪，与事实不符） | minor | **成立，fixed** | `git rm --cached` 移出 + `.gitignore` 加规则；根因是 git_commit 工具把未跟踪文件一并 add，下轮交接前先核对 `git status` 未跟踪清单 |
| F2 旧库接管 stamp 到 head，增量迁移（表达式索引）被跳过，仅新库有索引 | **major** | **成立，fixed** | `_ensure_schema` 改 stamp 基线 `df993f8cbfd2` 后照常 `upgrade head`；复现测试 `旧库经ensure_schema补齐增量索引`（先红后绿）。注：本机开发库因曾手动 upgrade 掩盖了此路径缺陷——我的实跑验证口径太弱，只验了"不报错+种子幂等"没验索引存在 |
| F3 迁移一致性测试只比表集合，看不到列/索引/约束漂移 | minor | **成立，fixed** | 升级为 `compare_metadata` 全量比对断言空 diff（实测无噪音）；CI 增加 `alembic check` 步骤 |
| F4 导入公司缓存只在新建分支填充，库里查到的公司不缓存，二次导入仍逐行查库；`\| None` 注解无用 | minor | **成立，fixed** | existing 分支补写缓存，类型改 `dict[str, CompanyORM]`；行为锁测试 `库中既有公司在批内也被缓存`（scalar 计数 ≤ 公司数，先红后绿）。变体等价性结论与审阅一致（焦点 1 无缺陷） |
| F5 413 检查在 `await file.read()` 之后，超大文件先整读进内存 | minor | **成立，fixed** | 两导入端点加 `Content-Length` 请求头预检（读前拒绝），保留读后字节检查兜底 chunked 无头请求；功能性区分不写专项测试（内存行为难在 TestClient 断言），现有 413 用例继续锁行为 |
| F6a `create_quick` 裸 `session.rollback()` 会波及外层事务其他未提交改动 | minor | **成立，fixed** | 改 `begin_nested()`（SAVEPOINT），撞号只回滚本次插入；现有端点路径本无前置写（审阅确认），此修复保护未来调用方 |
| F6b 409 查重与插入非原子：并发同 payload 双双通过检查创建重复产品 | minor | **记录为已知限制（open）** | 单用户本地系统 + 前端提交防重，触发面极窄，后果仅为可手动删除的重复产品；根治需给 quick 产品加唯一约束（会波及 CSV 多 code 同名产品路径），留待 WP1 建联系人时统一评估数据模型 |
| F7 迁移测试库 URL 硬编码 localhost:5433，非常规配置失效 | minor | **rejected（保持现状）** | 与既有 `tests/infra/conftest.py`、`tests/interface/conftest.py` 同一口径（CI 恰好同配置）；配置化是独立于 WP0 的测试基建改进，避免本轮范围膨胀 |

修复轮验证（9261b99）：

| 命令 | 结果 |
| --- | --- |
| `uv run pytest -q` | **153 passed**（+2 新复现/行为锁） |
| `uv run pytest -q -m smoke` | **2 passed** |
| `uv run ruff check .` | All checks passed |
| `uv run python -m app.bootstrap` | 幂等（重复 26 票，索引在位） |

## 复审记录（Claude Code 2026-10-10，对修复轮 9261b99）

verdict：F1/F2/F4/F5/F6a 全部 verified；F6b/F7 处理被认可；F3 的修复引入 CI 回归（新问题 3 条）。

| 编号 | 严重度 | 结论 | 处理（61fd58b） |
| --- | --- | --- | --- |
| N1 CI `alembic check` 连的 trueorder 库从未被迁移，必红（本机因手动升级过而掩盖） | 高 | **成立，fixed** | check 前加 `uv run alembic upgrade head`；本机建空库完整模拟 CI 步骤实跑：`No new upgrade operations detected`，exit 0（用 PIPESTATUS 取真实退出码验证） |
| N2 ORM 已含索引之后 create_all 的库，stamp 后 upgrade 因裸 `create_index` 无 IF NOT EXISTS 报错 | 低 | **成立，fixed** | 迁移改原生 `CREATE INDEX IF NOT EXISTS`（`postgresql_if_not_exists` 参数本版 SQLAlchemy 不支持，先踩后改）；既有「create_all+stamp+upgrade」测试绿 |
| N3 `int(content-length)` 非法值理论上 500 | 极低 | **rejected** | uvicorn/h11 对非法 Content-Length 前置拒绝，审阅方自评不构成实际风险 |

教训记录（同一天第二次）：改 CI/配置未实跑、依赖本机环境差异掩盖——N1 与 F2 同根。本轮已用「本机完整模拟 CI 步骤 + 真实退出码」的实跑口径收口。

最终状态（61fd58b）：后端 153 passed + smoke 2 + ruff 干净；迁移 4 passed（含 compare_metadata 全量比对）；CI 步骤全部本机等价实跑。WP0 交付。

---

# Handoff — TrueOrder WP1 联系人与来源（DEV-SPEC WP1 + 遗留 findings，2026-10-10）

## 任务

按 `docs/DEV-SPEC.md` WP1 实施联系人全链路（第一期信息获取主线），并处理上上轮试点审阅的遗留 findings（产品详情路由、排除测试证据链断言）。

## 已实现

1. **迁移**（`244c6cd8340a`）：`contacts` 表——部分唯一索引 `uq_contacts_company_email (company_id, lower(email)) WHERE email IS NOT NULL`、`source`/`verify_status` CHECK 约束、FK 级联删；`companies` 加 `website`/`website_confirmed`（带 server_default，存量库安全）。
2. **domain/contacts.py**：`normalize_email`（空→NULL）、`is_valid_email`（最低格式）、`is_generic_email`（19 个公共前缀词表）、`contact_dedup_key`。12 个领域单测（先红后绿：模块从无到有）。
3. **API**（`routers/contacts.py` 新文件）：公司联系人 CRUD（同公司同邮箱大小写不敏感 409、坏邮箱 422、公司 404）；`POST /api/contacts/import`（company_id 或「企业名+国家」双定位、重复计 duplicates、20MB 上限 + Content-Length 预检）；`PATCH /api/companies/{id}` 官网字段；`GET /api/products/{id}/contacts/export.csv`（与买家列表同一组筛选，每联系人一行，默认排除 do_not_contact 与 invalid/bounced，`include_invalid=true` 只放开验证状态——**DNC 是联系意愿永不导出**，此语义由测试暴露的歧义修正）。
4. **前端**：抽屉新增联系人区（ContactsPanel/ContactItem/ContactForm 组件族：新增/行内编辑/标记不再联系/删除/通用邮箱与验证状态标签）、官网编辑（WebsiteField）、买家列表「导出联系人 CSV」按钮（复用买家筛选参数）。CompanyDrawer 超行数红线两次拆分（ScoreSection、CompanySummary 出去），全部组件 ≤150 行。
5. **遗留 findings**：`GET /api/products/{id}` 详情路由（先红后绿）；银行/货代/集团内部排除测试补 `reason.bill_ids` 断言（实现本已满足，断言补齐锁定）；同行海外用例已有断言无需改。

## Diff 基线

base=61fd58b  head=01babf6
审阅范围命令：git diff 61fd58b...01babf6

## 改动文件

后端：`domain/contacts.py`、`infrastructure/contact_repository.py`（新）、`interface/routers/contacts.py`（新）、`queries.py`（company_detail 加官网字段 + get_product_with_counts）、`schemas.py`（6 个 DTO）、`orm.py`（ContactORM + companies 两列）、`routers/products.py`（详情路由）、迁移 1 个。
前端：`api/contacts.ts`（新）、组件 6 个（4 新 2 拆分）、`ProductDetailView`（导出按钮）、`schema.d.ts` 重新生成。

## 测试

- `uv run pytest -q` → **184 passed**（基线 153 → +31：领域 12、schema 5、接口 12+2 详情）
- `uv run pytest -q -m smoke` → **2 passed**
- `uv run ruff check .` → All checks passed
- `pnpm test` → **30 passed**（+5 ContactsPanel）；`pnpm exec eslint .` / `vue-tsc --noEmit` → 通过
- 迁移测试含「WP0 时代旧库（剥离 WP1 对象模拟）stamp 基线后升级补齐 contacts 与官网列」

## 已知假设与未验证项

- **website_confidence 导出列为空**：规格 WP1 导出列含「官网置信度」，但 `website_source`/`website_confidence` 列属 WP4 迁移；当前导出保留列头、值为空，WP4 落地后填。
- **前端浏览器冒烟未跑**：组件级行为由 30 个 Vitest 锁定，但「抽屉联系人区 + 导出按钮」的端到端浏览器操作未实机点过（smoke 测试覆盖 API 链路）。
- products.py 216 行仍超路由文件 200 红线（WP0 遗留）：本轮未重构拆分，避免与功能改动混在一个提交；建议下轮纯重构处理。
- F6b（并发同参数绕过产品 409 查重）维持 open：联系人侧同类问题已由 DB 部分唯一索引天然兜底（插入竞态由唯一约束拒绝→409）。

## Review 焦点

1. **部分唯一索引语义**：`uq_contacts_company_email` 与领域 `contact_dedup_key` 的一致性；无邮箱多条、跨公司同邮箱的行为是否都被测到。
2. **导出 JOIN 语义**：`export_rows` 先取买家列表公司集合再查联系人——公司与联系人 join 无重复行？`include_invalid` 与 DNC 的过滤组合边界。
3. **CSV 导入定位**：`_resolve_company` 的 company_id 优先/名称+国家回退顺序、`company_not_found` 与 `invalid_rows` 的归类是否会互相吞错误。
4. **前端组件拆分**：ContactItem 的 `@update` emit 链（panel 传 contact_id）是否会把 A 联系人的编辑提交到 B。
5. **迁移**：部分唯一索引在 alembic autogenerate 产物中的 `postgresql_where` 保真度；`website_confirmed` server_default 对存量库的影响。
6. **产品详情路由**与既有列表路由的 id 冲突（`/api/products/{product_id}` vs `/api/products/import` 的路由顺序）。

## Findings 台账（Claude Code 独立审阅 2026-10-10，对 01babf6；修复轮 c2762f7）

审阅产出 5 条（1 blocker / 1 major / 3 minor）+ 2 项焦点确认无缺陷（路由顺序、部分唯一索引一致性）：

| 编号 | 严重度 | 结论 | 处理 |
| --- | --- | --- | --- |
| F1 单条写路径（add/update/delete/官网 PATCH）只 flush 无 commit，生产每请求独立会话全部回滚；测试因 conftest 共享 session 掩盖 | **blocker** | **成立，fixed** | `deps.get_session` 改为「请求成功自动 commit、异常回滚」的统一出口（既有 importer 显式 commit 兼容无害）；复现测试用生产式 session 工厂（monkeypatch `_session_factory`，不 override get_session）跨请求断言持久化，先红后绿 |
| F2 `add()` 的裸 `rollback()` 在导入循环中吞掉同批前面未提交行，added 计数虚报 | major | **成立，fixed** | add/update 改**预查重**（`_duplicate_exists`，同事务已 flush 行对 select 可见），常规路径零异常；DB 唯一约束只在并发窗口兜底（此时 rollback 吞行为已知限制，单用户系统窗口≈0） |
| F3 `update()` 先改字段后验邮箱，422 时其他字段留脏改动 | minor | **成立，fixed** | 校验前置（invalid_email/duplicate 均在改动前返回）；复现测试断言 422 后 title 未变 |
| F4 CSV 按名称定位缺国家时静默默认 US，可能错挂同名美国公司 | minor | **成立，fixed** | 名称定位必须带国家，缺失归入 `invalid_rows`（带行号提示） |
| F5 联系人导出 `limit=100000` 静默截断无信号 | minor | **记录为已知限制** | 与买家导出同口径同上限；当前数据规模（万级）不可触发，真实全量接入时随分页统一处理 |
| 焦点 6 路由顺序（GET /{id} vs POST /import） | — | 无缺陷 | 方法不同不冲突；GET /import 返回 422 属美观问题 |
| 焦点 1 部分唯一索引与 normalize_email 一致性 | — | 无缺陷 | 双方 lower 语义一致 |

修复轮验证（c2762f7）：

| 命令 | 结果 |
| --- | --- |
| `uv run pytest -q` | **188 passed**（+4 复现/行为锁） |
| `uv run pytest -q -m smoke` | **2 passed** |
| `uv run ruff check .` | All checks passed |
| `pnpm test` | **30 passed** |

排查过程记录（供复审参考）：F2 修复先后尝试 savepoint context/显式两版均表现异常，最终定位为**测试自身 CSV 列数错误**（6 列被当 7 列解析，email 落到 title 列、插入 email=NULL 行绕过一切去重），期间两次按行号改测试误删语句；换 csv.writer 生成测试数据并恢复被删语句后，预查重方案一次通过。产品代码的 savepoint 方案本身是否可行未继续验证（预查重方案更简单可预测，已采用）。

## 复审记录（Claude Code 2026-10-10，对修复轮 c2762f7）

verdict：**F1-F4 全部 verified**（复审通过读 fastapi 0.143 源码确认异常路径不提交、预查重可见性依赖 autoflush=False 下的显式 flush、测试数据列数逐行核对）。3 条新问题处理（2919cd2）：

| 编号 | 严重度 | 结论 | 处理 |
| --- | --- | --- | --- |
| N1 deps 自动 commit 在响应发出之后执行：客户端拿到 2xx 时事务可能未提交（前端新增后立即刷新的读写竞态）；提交失败无法转为错误响应 | minor 偏上 | **成立，fixed** | 撤销 deps 自动 commit，写方法（add/update/delete/update_website）改为**响应前显式 commit**——与 importers 既有惯例一致；生产式跨请求持久化测试保持绿 |
| N2 缺「4xx 路径不提交」回归锁（依赖 fastapi 源码行为，无测试防退化） | minor | **成立，fixed** | 新增 409 路径不落库测试（生产式会话工厂，race@ex.com 唯一一条） |
| N3 跨请求持久化测试库 URL 硬编码、engine 参数未用 | nit | **成立，fixed** | 改用 `engine.url.render_as_string(hide_password=False)`——注意 `str(url)` 会把密码打码导致认证失败（已踩坑修正） |

最终状态（2919cd2）：189 passed + smoke 2 + ruff 干净 + 前端 30。WP1 交付。

## 终审与收敛（2026-10-10，WP1 关闭）

终审 verdict：**核心全部 verified**——四个写方法 commit 均在响应前、失败路径全部绕过 commit、只读路径无意外提交、`POST /api/products` 链路（create_quick→rescore_one commit）未被撤销 deps 自动 commit 牵连。3 条非阻塞观察处理（47b14d8）：

| 观察 | 处理 |
| --- | --- |
| 409 回归测试只锁「预查重生效」，未锁「失败不提交」语义（deps 自动 commit 若被加回该测试照样过） | 补并发兜底测试：monkeypatch `_duplicate_exists` 盲化，逼出 IntegrityError 分支，断言唯一一条 + 会话可用——该分支含 rollback，若有人恢复 deps 自动 commit 且路径留脏即被抓 |
| 生产式测试用裸 sessionmaker，与生产 `expire_on_commit=False/autoflush=False` 配置不一致 | 统一复用 `db.make_session_factory` |
| import_csv 逐行 commit 后失去原子性，尾部 commit 多余 | 移除多余 commit；**行级提交（非原子）为已知行为**：中途失败留已提交前半批；导入常规路径无异常抛出（校验/查重前置），实际风险≈0，若未来需要原子导入再给 add 加 commit 开关 |

**WP1 关闭状态（47b14d8）**：190 passed + smoke 2 + ruff 干净 + 前端 30。审阅四轮（初审 5 条→修复→复审 3 条→修复→终审 verified），收敛。

## 独立审阅轮（ZCode 主会话 2026-10-10，对 fa8e468 + a1981eb）

背景：主会话对「快速建产品 + 前端改版」两提交调度了独立只读审阅（cursor-agent，brief 见 `.review/review-brief-3.md`，原文 `.review/cursor-review-3.txt`）。审阅执行期间与本仓库另一并行会话（WP0/WP1，Claude Code）的提交交错：其 `2919cd2`/`47b14d8` 已覆盖部分同源问题，F5 由其修复。本轮处理剩余 findings（全部前端）：

| 编号 | 严重度 | 结论 | 处理 |
| --- | --- | --- | --- |
| F1 both 受众缺键时 audienceCounts 回退总计数：空受众页签串成另一受众数字、no-bills 漏报 | **P1** | **成立，fixed** | both 产品缺键视为 `{}`，禁止回退总和；复现测试 `both 产品某受众无得分时缺键不回退总计数`（先红后绿） |
| F2 前端税号全零校验 `/^0+$/` 与后端 is_valid_hs「前 6 位全零即误码」不一致（0000001 落到 API 422） | P2 | **成立，fixed** | 对齐为 `hs.slice(0,6)==="000000"` 拒绝；用例 `前 6 位全零的税号本地即拒`（先红后绿） |
| F3 ReasonList scoped 样式盖过改版后的全局 chip token（12px 非 mono、hover 无青底） | P2 | **成立，fixed** | 删 scoped 块，统一走全局 `.bill-chip-link` |
| F4 Esc 关抽屉无测试；关闭后在途 fetchCompany 仍写 detail（重开竞态下串公司数据） | P2 | **成立，fixed** | 新增 `CompanyDrawer.test.ts`（Esc 开/关两用例 + `A 慢关开 B 快，A 迟到不覆盖 B` 先红后绿）；组件加 requestSeq 守卫，与买家列表同口径 |
| F5 POST /api/products commit 后读计数失败 500 而库已有产品 | P2 | **已被并行会话修复** | `2919cd2`（提交时序前移到响应前 + 失败路径回归锁），无需重复处理 |

审阅者自述的「begin_nested 重试」verified 项经核实为并行会话 WP0 引入（非本会话代码），其结论与仓库实际一致。

最终状态：前端 35 passed（+5 防线）、lint 0 错、vue-tsc 通过、构建成功；后端 190 passed 未动。

**合规快检（对并行会话 WP1 联系人功能）**：当前代码无任何外部按次查询实现（无 httpx/Hunter/Apollo/PDL；`finder` 仅为预留枚举），联系人来源仅 manual/csv/website 手工录入——不违反 AGENTS.md 硬约束。但 `docs/OUTREACH-COMPLIANCE.md` 规划的「按次查询补全（Hunter 等）」与硬约束「不接按次查询数据源入库存」**冲突**，实现前需用户明确裁决（改约束或改方案）。

## WP3 任务队列与 worker（ZCode 主会话 2026-10-10，34b5eea 之后）

按 DEV-SPEC v0.2 第一期顺序（WP0✅→WP1✅→**WP3**→WP4→WP7）交付：

| 层 | 交付 | 测试 |
| --- | --- | --- |
| 领域 | `domain/jobs.py`：指数退避（60s×2^n 封顶 1h）、僵死阈值 10min、重试边界纯函数 + Job 实体 | 9 条（tests/domain/test_jobs.py） |
| 基础设施 | `orm.JobORM`（JSONB payload、CHECK、认领部分索引）+ `infrastructure/jobs.py`（SqlJobQueue：FOR UPDATE SKIP LOCKED 认领/退避失败/僵死回收/永久失败；Worker.run_once 分发） | 18 条（认领互斥、交错不重复、退避时刻、上限置 failed、回收、未知类型永久失败） |
| 迁移 | `d5bbf21b2e42_wp3_jobs_table` 链在 244c6cd8340a，autogenerate 生成过 compare_metadata 一致性 | 旧库模拟测试同步剥 jobs 表（create_all 时代库不含它） |
| 接口 | `GET /api/jobs?status=` 只读（JobOut/JobsListOut） | 4 条 |
| 进程 | `python -m app.worker`（--once/--interval，空注册表安全：未知类型永久失败并在状态页可见） | 实跑 rc 0 |
| 前端 | `#/jobs` 任务状态页（10s 自动刷新、状态过滤、类型中文化、失败红轨）+ 顶栏「任务」导航 | 3 条组件测试 |

门禁：后端 **221 passed** + ruff 干净；前端 **38 passed** + eslint 0 错 + vue-tsc 通过 + 构建成功。冒烟（Playwright + 真实 worker 进程）：入队→worker --once 消费→状态页渲染类型/失败原因→过滤交互，截图 `screenshots/08-jobs-page.png`。

设计取舍：worker 处理器注册表本期为空（WP4 挂 find_contacts/crawl_website），空表下队列语义已全部锁定；队列每方法自带 commit，处理器异常走 rollback+退避，与既有「响应前显式 commit」惯例一致。

## WP4 补全与抓取（ZCode 主会话 2026-10-10，add2a70 之后）

按 DEV-SPEC 第一期顺序（WP0✅→WP1✅→WP3✅→**WP4**）交付。规格 3.6/3.7 全约束落地：

| 层 | 交付 | 测试 |
| --- | --- | --- |
| 领域 | `contacts.py` 增：website_confidence（名称+国家→high/medium/low）、pick_best_recipient（具名valid>具名unknown>通用；职位词优先）、extract_emails/phones、select_crawl_pages（首页+contact/about/team 同站≤5页） | 14 条（test_contacts_rules.py） |
| 基础设施 | `contact_finders/`（hunter 域名搜索+邮箱验证 / fake 无Key演示源，make_finder 切换）；`crawler.py`（robots.txt、同主机≥2s、1MB 上限、SSRF 解析 IP 拒回环/私网/链路本地+重定向复检、allow_loopback 仅测试）；`enrichment.py`（SqlEnrichmentLog 日上限/30天不重查；find_contacts 处理器：**域名发现**（无官网也按公司名查，高置信自动采用+查联系人，中低只写候选等确认）；crawl_website 处理器；verify_email 处理器（无Key跳过）；robots/超限/无公司→永久失败不退避） | 处理器 11 条 + 抓取器 8 条（本地 HTTP 夹具：robots拒、私网重定向拒、超大页弃、同站重定向跟随、SSRF 判定） |
| ORM/迁移 | `enrichment_calls` 表 + `companies.website_source/website_confidence`（迁移 209d5470bed4，server_default=''），旧库模拟测试同步剥 WP4 对象 | compare_metadata 一致性绿 |
| 接口 | POST /companies/{id}/find-contacts?method=finder\|website（202 入队）；POST /products/{id}/buyers/enrich（不带 confirm 只估计：可补全/跳过已有联系人/近期查过/额度截断；confirm=true 入队且受剩余额度截断）；POST /companies/{id}/website/confirm；GET /api/enrichment/usage | 9 条（test_enrich_api.py） |
| worker | build_registry 注册三类处理器；PermanentJobError 永久失败语义进 Worker（与退避重试区分） | WP3 测试语义保持 |
| 前端 | 抽屉：查找联系方式/抓取官网按钮+入队提示；官网置信度徽章（中低置信黄标）+「确认是官网」按钮（确认后重载）；买家工具栏 EnrichBar 两段式（估计→确认执行，额度提示含 fake/hunter 状态） | 5 条组件测试（EnrichBar 两段式/0家禁用/错误态 + 面板两种方法入队） |

门禁：后端 **265 passed**（+44）+ ruff 干净；前端 **43 passed** + eslint/vue-tsc/build 全绿。
冒烟（两段，真实链路）：API 入队 → 真实 worker 进程（三处理器注册）→ fake finder 联系人入库（source=finder，source_ref 标注演示数据）→ 浏览器抽屉呈现联系人+已确认官网徽章，截图 `screenshots/09-wp4-enrich.png`。

设计取舍与规格偏离（1 处，已在代码注释与本表记录）：
- 3.6 写「没有 website 不调用接口」，但 1.4.1 交付标准与 3.7 第 1 条要求「系统自动补全域名」——两者矛盾。实现取后者：无官网时仍按公司名调 finder 做**域名发现**（Hunter domain-search 支持传公司名；fake 同样支持），高置信自动采用后继续查联系人，中低置信只写候选等人工确认。额度与审计（enrichment_calls）两条路径都生效。
- `docs/finder-eval.md` 已建占位：真实 Hunter 命中率评估需要用户提供 API Key 后手工执行（10 家样本），当前无 Key 走 fake 演示源、来源可辨识不污染真实数据。

## WP7 第一期收尾（ZCode 主会话 2026-10-10，c19fe49）

- e2e 冒烟（`-m smoke`，4 条）：新增两条获客闭环——①选企业补全（fake）→ 域名/联系人写入（source=finder、fake 标注、verify unknown）→ 额度审计 → 联系人导出列与内容校验；②批量补全估计（不入队）→ 确认执行 → worker 消费 → 二次估计两类跳过全部生效（candidates=0）。
- README 增「第一期获客流程」四步 + 截图索引；OUTREACH-COMPLIANCE 增「实现现状核对」表（8 项逐条对照实现位置）；AGENTS.md 必测点补后台任务/补全/爬虫与前端两段式。
- 门禁：后端 265 + smoke 4 + ruff 干净；前端 43 + eslint/vue-tsc 通过。

**第一期（WP0-WP4、WP7）交付完成。** 遗留：真实 Hunter 命中率评估（docs/finder-eval.md，待用户提供 API Key）；WP3/WP4/WP7 独立审阅进行中（brief-4）。

## 独立审阅轮 4 处理（ZCode 主会话 2026-10-10，对 add2a70..c19fe49，brief-4）

审阅返回 1 P0 + 5 P1 + 3 P2，逐条核实全部成立并修复：

| 编号 | 严重度 | 结论 | 处理 |
| --- | --- | --- | --- |
| F1 verify_email 不在 jobs.kind CHECK，配 Hunter Key 后验证任务入队即 IntegrityError | **P0** | **成立，fixed** | 迁移 a7c3e91d5f02 放宽 CHECK + ORM/JobKind/前端文案同步；先红后绿测试「有 key 时排 verify_email 且可被 worker 消费→verify_status=valid」 |
| F2 FakeContactFinder 回显 domain_country=None → 域名发现永远 medium、演示路径丢联系人 | P1 | **成立，fixed** | ContactFinder.find 增加 company_country 参数（端口+两适配器），fake 回显公司国家使名称对齐时达 high；「真实 make_finder() 域名发现」集成测试先红后绿 |
| F3 额度检查与记账非原子，多 worker 并发超扣 | P1 | **成立，fixed** | reserve()：pg_advisory_xact_lock + 独立短事务计数并预插审计行（ok=False），mark_ok 成功后翻转；两公司 cap=1 并发测试：一家 done、一家延期、仅一条记账 |
| F4 额度用尽走永久失败（明日不重跑）且批量不预留 | P1 | **成立，fixed** | QuotaDeferred（携带 run_after）→ queue.defer()：回 pending、attempts 不增、延期到明日；测试改锁延期语义 |
| F5 重试/僵死回收会再次外呼扣费 | P1 | **成立，fixed** | 处理器入口按 ok_only 成功记录 30 天短路；mark_ok 在联系人落库后翻转（此前崩溃重试会再查）；「两次执行只调一次 finder」测试 |
| F6 爬虫 SSRF DNS TOCTOU（校验后连接重新解析，可被 rebinding） | P1 | **成立，fixed** | _PinnedBackend：连接强制走已校验 IP（挂 httpx 内部连接池），TLS/SNI 仍按原主机；钉扎单元测试（不存在的主机名钉到夹具 IP 能连通） |
| F7 EnrichBar 用 candidates 禁用，额度耗尽时仍可点确认 | P2 | **成立，fixed** | 禁用条件改 credits_needed===0；文案区分「今日可执行 N 家（额度不足明日自动排）」；Vitest 补截断场景 |
| F8 冒烟未锁域名发现闭环/批量不断言联系人 | P2 | **成立，fixed** | 冒烟新增「无官网→域名发现→高置信自动确认→联系人自动写入」全链路；批量用例补联系人断言（该用例原有） |
| F9 域名回写无 scheme（抽屉链接非法）+ worker 注释过时 | P2 | **成立，fixed** | 入库规范化 https:// 前缀；WebsiteField href 兜底；worker 文档字符串更新 |

复核结论表全部 verified/按处理关闭。门禁：后端 **270 passed + smoke 5** + ruff 干净；前端 **44 passed** + eslint/vue-tsc/build 全绿。

## 前端设计走查轮（Cursor，design-brief，2026-10-10）

用户质疑前端优化质量后：先拍 7 张全量基准截图（`.review/frontend-audit/`，含 WP1/WP3/WP4 新组件首次整体截图），调 Cursor 只读走查（5 P1 + 8 P2 + 3 P3），逐条裁决处理：

| 编号 | 结论 | 处理 |
| --- | --- | --- |
| D1[P1] 新组件引用 9 个从未定义的样式类（ghost/error/contact-form/list/panel、website-field、enrichbar、tags、badge.warn/muted）——WP1 会话写的组件对着不存在的样式表写，一直裸渲染 | **成立（复核属实，全部为 0 定义）** | main.css 补齐全部类；程序化审计锁定（ghost 透明底） |
| D2[P1] 确认官网失败无反馈 | 成立 | 非编辑态加 error 节点 + 确认 busy 文案 |
| D3[P1] 得分理由/提单证据被补全区挤到抽屉底部 | 成立 | 抽屉重排：摘要→得分理由→提单→官网→联系人（证据优先）；审计锁定顺序 |
| D4[P1] 买家表行不可键盘操作 | 成立 | tabindex/role/Enter/Space + focus-visible 描边；新增键盘测试 |
| D5[P1] 无 disabled 态、补全按钮可连点 | 成立 | 全局 :disabled（含 not-allowed）；补全/抓取 busy 防连点；EnrichBar busy 文案 |
| D6[P2] 行内 style 绕过 token | 成立 | .input-narrow/.input-country/.stack-top/.panel>h1/.drawer h2 全部类化，清 8 处行内样式 |
| D7[P2] 联系方式/提单码未走 mono | 成立 | email/phone/URL/提单号/HS/到港加 .code；ScoreSummary 日期改 code |
| D8[P2] 两段式切换视觉弱 | 成立 | .enrichbar 琥珀左边轨容器 + 「第 2 步 · 确认消耗额度」步骤标 |
| D9[P2] 联系人操作条主次不分 | 成立 | 拆 ContactsActions 子组件：补全=primary、抓取/新增=ghost |
| D10[P2] 390px 表格溢出 | 成立 | .table-scroll 包三处表格；filterbar/enrichbar/contact-form 移动端纵排；审计 0 溢出 |
| D11[P2] 同名冲突徽章装长句 | 成立 | 改 .alert 提示条 + 内嵌徽章 |
| D12[P2] 任务页筛选实心主按钮、running/pending 同色 | 成立 | 改 tabs 模式（aria-selected）；running 用海关青徽章 |
| D13[P2] 抽屉无焦点管理 | 成立（部分） | 打开即聚焦关闭按钮（审计锁定）；完整焦点陷阱留待后续 |
| D14[P3] 动词不一致 | 成立 | 统一「补全联系人/抓取官网/导出买家 CSV」 |
| D15[P3] 眉题英文不统一 | 成立 | Job Queue→Task Queue |
| D16[P3] 琥珀对比度存疑 | **实测通过** | #8a5a00 on #faf0d7 = 5.22 ≥ 4.5（AA），不改 |

门禁：前端 **45 passed**（+1 键盘测试）+ eslint/vue-tsc/build 全绿；Playwright 程序化复审 5 项全过（D1/D3/D4/D10/D13）。教训：这轮暴露 WP1 会话组件从未做过视觉集成验证——「组件测试绿」≠「长对了」，基准截图+走查应成为每个 WP 前端交付的门禁。
