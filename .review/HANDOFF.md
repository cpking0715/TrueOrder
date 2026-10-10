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
