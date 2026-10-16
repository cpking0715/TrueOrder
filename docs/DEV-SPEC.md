# TrueOrder 开发规格与执行计划（v0.2：买家库 → 找客户、联系、跟进）

> 读者：负责实现的编码智能体。每个工作包（WP）可独立领取，按「依赖」列排序。
> 先读 `AGENTS.md`（硬约束，WP0 会修订其中三条）与本文件，再动手。

## 1. 评审结论

### 1.1 需求是否合理：合理，但目标比现有产品大一个量级

目标是「为自家产品找到客户 → 拿到联系方式 → 联系 → 跟踪意愿直至成交意向」。这是一条完整的外贸获客漏斗：

```
提单数据 → 潜在/精准名单 → 联系人 → 触达 → 回复 → 样品/报价 → 谈判 → 成交意向
[已实现]    [已实现]      [WP2/5]  [WP6]  [WP7+] [WP3]
```

现有系统只覆盖前两段。后四段本质上是一个轻量 CRM 加外发邮件系统，与「买家库」是两类产品，但数据上天然相接（企业、提单证据、产品已经有了），所以放在同一个仓库里做是合理的。

### 1.2 可行性判断（按风险从高到低）

| # | 环节 | 判断 | 说明与应对 |
| --- | --- | --- | --- |
| R1 | **提单数据本身** | 最大的业务风险 | 现在只有 26 行虚构样本。整个漏斗的质量取决于能否拿到允许建索引的**授权全量提单**。代码层面无法解决，需要用户采购。WP0 的性能修复（见 4.1）是为全量数据做准备。 |
| R2 | **找官网域名** | 补全流程的真正瓶颈 | 提单只有公司名和地址，没有域名。Hunter 之类接口通常要先有域名才能查邮箱。应对：企业上增加 `website` 字段；高置信域名自动采用，中低置信只作候选，人工确认后才继续查联系人（规则见 3.7）。 |
| R3 | **官网抓取** | 可行，准确率有限 | 只能取到公开挂出的邮箱和电话，且多为 `info@` 之类通用邮箱。抓取要遵守 robots.txt、限速、不登录、不绕过反爬。通用邮箱要打标签，不与具名联系人混为一谈。 |
| R4 | **本地发信的送达率** | 需要管控预期 | 新域名或无 SPF/DKIM/DMARC 的发件域，冷启动群发大概率进垃圾箱甚至拉黑发件域。应对：默认每日上限 30、发送间隔随机化、先预热；文档写明 DNS 配置要求。这是运营问题，代码只能提供限流和日志。 |
| R5 | **退订链接** | 本地单用户模式下**无法托管公网链接** | 后端只跑在本机，收件人点不到退订页。应对：用 `List-Unsubscribe: <mailto:...>` 加正文里「回复 STOP 即不再联系」，由用户手动标记或 IMAP 轮询识别。若以后要点击退订，需要一个公网的极小退订服务，列为非目标。 |
| R6 | **合规** | 可做护栏，不能替代法律判断 | 欧盟/英国（GDPR 合法利益、需可退订、需说明来源）与美国（CAN-SPAM：真实发件人、物理地址、可退订）要求不同。系统提供抑制名单、来源可追溯、一键删除个人数据、按国家的提示文案。本文不构成法律意见。 |
| R7 | **本地后台任务** | 可行，但要持久化 | 电脑关机时进程内队列会丢任务。应对：任务存进 PostgreSQL，worker 进程轮询认领，重启后能继续（见 3.4）。 |

### 1.3 现有架构评审

**保留（做得对）：**
- 四层依赖方向正确：`domain` 纯函数、`infrastructure` 实现端口、`interface` 只做 DTO。新功能沿用。
- 得分理由带提单 id，天然可以做成开发信里的证据引用，是本产品相对普通 CRM 的差异点。
- 企业识别用「规范化名称+国家」，同名只标记不合并，联系人沿用这个原则。

**必须改（影响新功能的地基）：**
1. **没有迁移工具**：`bootstrap` 直接 `create_all`。要加 5 张以上新表，必须引入 Alembic，否则无法演进。
2. **全量重打分**：任何导入或建产品都重算所有产品，且 `SqlBuyerPoolReader.load_pool` 把某税号族**全部历史提单**载入内存。样本规模无感，全量数据（百万行级）会成为瓶颈。需要「按产品增量打分」和「SQL 侧按 24 个月窗口过滤」。
3. **打分参数写死**：`ORIGIN_ALLOWED = {"CN","VN"}`、24/12 个月、美国提单假设都在代码里。短期保留默认值，但要抽成产品级或全局配置，避免换品类时改代码。
4. **P1 缺陷**（详见 4.1）：同文件内重复行、CSV 公式注入、上传无上限、建产品并发编号冲突。

**不建议做（过度设计）：**
- Celery/Redis、微服务、多租户、登录鉴权（本地单用户，见 1.5）。
  - 修订（Phase 1，2026-10-14）：不做多用户登录，但提供单一 API 令牌 `TRUEORDER_API_TOKEN`；设置后全部 `/api` 必须携带，留空即关闭（仅限本机 127.0.0.1 开发/演示）。
- 实时 WebSocket、AI 自动写信（先做模板变量，效果验证后再说）。

### 1.4 范围裁剪建议（先闭环，后自动化）

用户已确认要支持：接口补全、官网抓取、模板与 SMTP 直发。建议**交付顺序**如下，因为越靠后越依赖前面的数据质量：

| 里程碑 | 内容 | 用户得到什么 |
| --- | --- | --- |
| **M0** | 地基修复、迁移、边界文档 | 稳定可扩展的底座 |
| **M1** | 联系人（手工/CSV）+ 商机管道 + 活动时间线 + 今日待跟进 | **不发任何邮件也能完整管理客户跟进**，可立即使用 |
| **M2** | 补全接口 + 官网抓取（对选中企业） | 少打字就能拿到联系方式 |
| **M3** | 模板、SMTP 发送、抑制名单、发送日志 | 能直接发开发信 |
| **M4（可选）** | IMAP 回复识别、多步序列 | 减少手动录入 |

M1 完成时就有价值，不要等到全部做完才让用户使用。

**优先级调整（用户重点是获取联系方式）**：WP0 之后，先走 WP1（联系人）→ WP3（任务队列）→ WP4（补全与抓取），即先交付 M2，再做 WP2（商机管道）和 WP5（发信）。WP2 与 WP4 之间没有依赖，如有多个智能体可并行。

### 1.4.1 第一期范围（用户决定，2026-10-10）：只做信息获取

**第一期只交付：WP0 地基 → WP1 联系人 → WP3 任务队列 → WP4 补全与抓取 → WP7 收尾（裁剪版）。**

| 包含 | 不包含（推迟到第二期，规格保留不删） |
| --- | --- |
| 联系人表、手工/CSV 录入、官网字段 | WP2 商机管道、活动时间线、今日待跟进 |
| 后台任务队列与 worker | WP5 模板、SMTP 发信、抑制名单、发送日志 |
| Hunter 补全、官网抓取、邮箱验证、自动填充规则（3.7 第 1–3、5 条） | WP6 IMAP 回复识别、多步序列 |
| **联系人导出 CSV**（见 WP1 补充，用户在系统外联系客户所需） | 3.7 第 4、6 条（带入发信收件人） |
| 数据来源可追溯、一键清除某人的数据 | 3.5 发送护栏（第二期随发信一起做） |

第一期的实现约束：
- **不建** `opportunities`、`activities`、`email_templates`、`email_messages`、`suppressions` 表，不写发信与 SMTP 代码，也不在界面上放对应入口。第二期再用新的迁移加。
- `contacts.do_not_contact` 字段保留（成本极低，且第二期发信要用），界面可手动标记；导出时默认排除已标记的联系人。
- 第一期的交付标准：用户选定一批买家，系统自动补全域名与联系人并验证邮箱，用户在界面上看到来源与置信度，并能导出带联系方式的 CSV。
- 第一期的合规重点是**来源可追溯与数据清除**，发信相关合规（退订、抑制名单、各国要求）随第二期落地；`docs/OUTREACH-COMPLIANCE.md` 在第一期只写「联系人数据的来源与保存」部分。

### 1.5 非目标

- 多用户、登录、权限（本地单用户；若以后多人共用，另立规格）。
- 公网部署与点击式退订页。
- 爬取提单网站；批量灌入按次查询源（保留原硬约束，见 WP0 修订）。
- 绕过目标站反爬、验证码、登录墙；购买或使用来路不明的邮箱列表。
- 自动群发无限量发送；系统必须有每日上限且不可在界面里一键关闭。

## 2. 约束修订（WP0 写入 AGENTS.md 与 README）

| 原约束 | 修订为 |
| --- | --- |
| 不做开发信 | 允许开发信，但**只发给已入库、有来源记录、不在抑制名单、且由用户明确触发或批准**的联系人 |
| 不把按次查询源灌入库 | 允许补全，**仅对用户选定的一批企业**调用（单个选中，或当前筛选的前 N 家且 N ≤ 当日剩余额度），结果必须带来源和时间；禁止无人触发的全库自动补全；有每日调用上限 |
| 不爬任何提单网站 | **保留**；新增：仅允许抓取企业自有官网的公开页面，须遵守 robots.txt 并限速 |

其余硬约束不变：不改 `D:\MyProjects\GoodJob`；得分理由带提单 id；凭据只走环境变量；企业识别只用规范化名称加国家。

## 3. 目标架构

### 3.1 分层与新增模块

```
backend/app/
  domain/
    contacts.py        # 联系人规则：邮箱规范化、通用邮箱判定、去重键、核验状态
    pipeline.py        # 商机阶段机、意愿等级、跟进到期判断
    outreach.py        # 模板变量渲染、抑制名单判定、发送额度计算、退订语句
    ports.py           # 新增端口：ContactFinder / WebsiteCrawler / MailSender / JobQueue
  infrastructure/
    contact_finders/   # hunter.py（适配器）、fake.py（测试用）
    crawler.py         # 官网抓取（robots、限速、SSRF 防护）
    mail.py            # smtp.py、fake.py
    jobs.py            # 基于 PostgreSQL 的任务队列
    imap.py            # M4 可选
  interface/routers/
    contacts.py  opportunities.py  templates.py  outreach.py  suppression.py  jobs.py
  worker.py            # python -m app.worker：轮询认领任务
alembic/               # 迁移
```

依赖方向不变：`interface → domain ← infrastructure`。domain 里不 import 任何框架，也不做网络调用。

### 3.2 数据模型（新增，均由 Alembic 迁移创建）

**companies 增列**：`website TEXT NULL`、`website_confirmed BOOL DEFAULT false`。

**contacts**
| 列 | 类型 | 说明 |
| --- | --- | --- |
| id | PK | |
| company_id | FK companies | |
| name | TEXT | 可空（通用邮箱无人名） |
| title | TEXT | 职位 |
| email | TEXT NULL | 小写存储 |
| phone | TEXT NULL | |
| is_generic | BOOL | `info@/sales@/contact@` 等 |
| source | ENUM | `manual` / `csv` / `finder` / `website` |
| source_ref | TEXT | 接口名或页面 URL |
| acquired_at | TIMESTAMPTZ | |
| verify_status | ENUM | `unknown` / `valid` / `invalid` / `bounced` |
| do_not_contact | BOOL | |
| UNIQUE | `(company_id, lower(email))` WHERE email IS NOT NULL | 同邮箱不重复；冲突只提示，不合并 |

**opportunities**：`id`、`product_id`、`company_id`、`stage`、`intent`（`cold|warm|hot`）、`next_follow_up_on DATE NULL`、`owner_note TEXT`、`created_at`、`updated_at`、`closed_reason TEXT NULL`。`UNIQUE(product_id, company_id)`。

**activities**：`id`、`opportunity_id`、`contact_id NULL`、`kind`（`email_out|email_in|call|whatsapp|note|stage_change`）、`summary`、`body`、`intent_after NULL`、`occurred_at`、`email_message_id NULL`。只追加，不修改、不删除（删除联系人时见 WP2 的数据清除）。

**email_templates**：`id`、`name`、`subject`、`body`、`language`、`created_at`。

**email_messages**：`id`、`opportunity_id`、`contact_id`、`template_id NULL`、`subject`、`body`（渲染后快照）、`status`（`queued|sending|sent|failed|bounced|suppressed`）、`error TEXT`、`scheduled_at`、`sent_at`、`message_id_header`、`attempts`。

**suppressions**：`id`、`email NULL`、`domain NULL`、`reason`（`unsubscribed|bounced|manual|complaint`）、`created_at`、`CHECK(email IS NOT NULL OR domain IS NOT NULL)`。

**jobs**：`id`、`kind`（`send_email|find_contacts|crawl_website|poll_imap`）、`payload JSONB`、`status`（`pending|running|done|failed`）、`run_after`、`attempts`、`max_attempts`、`last_error`、`locked_at`、`created_at`。

**enrichment_calls**：`id`、`provider`、`company_id`、`credits_used`、`called_at`、`ok`，用于每日上限计量和审计。

### 3.3 商机阶段机（domain/pipeline.py，纯函数）

阶段：`lead → contacted → replied → sample_quote → negotiating → won_intent`，另有终态 `lost`。

规则：
- 允许向前跳级（例如 `lead → replied`，对方主动来信）。
- 允许从任意阶段进入 `lost`，必须带 `closed_reason`。
- 允许 `lost → lead` 重新打开。
- `won_intent` 之后只能进入 `lost`，不能倒退。
- 系统自动推进：成功发出第一封邮件且阶段为 `lead` 时置 `contacted`；记录 `email_in` 且阶段为 `contacted` 时置 `replied`。每次变更写一条 `stage_change` 活动。
- 到期判断：`next_follow_up_on <= today` 且阶段不在 `won_intent/lost` 即为「今日待跟进」。

### 3.4 后台任务

- 数据库表 `jobs` 加 `worker.py`。认领使用 `SELECT ... FOR UPDATE SKIP LOCKED`，认领即置 `running` 并写 `locked_at`。
- 超过 10 分钟仍为 `running` 的任务视为僵死，重新置 `pending` 并增加 `attempts`。
- 失败按指数退避重试，超过 `max_attempts` 置 `failed`。
- 发送任务必须幂等：先建 `email_messages` 行（`queued`），worker 发送前检查状态，发送成功后写 `sent_at` 与 `message_id_header`，避免重启后重复发信。
- 界面提供「任务状态」只读页，用于查看失败原因。

### 3.5 发送护栏（domain/outreach.py + worker，不可绕过）

1. **抑制名单先查**：邮箱或域名命中任一记录，该消息直接置 `suppressed`，不发送。
2. **联系人 `do_not_contact` 或 `verify_status in (invalid, bounced)`**：不发送。
3. **每日上限**：环境变量 `TRUEORDER_SMTP_DAILY_CAP`，默认 30，范围 1–500。界面不提供关闭开关。
4. **发送间隔**：每封之间随机 20–90 秒，可配置下限。
5. **每封邮件必带**：真实发件人名与地址、公司物理地址（配置项，缺失则拒绝启动发送功能）、退订语句（回复 STOP）、`List-Unsubscribe: <mailto:...>` 头。
6. **每个联系人冷却**：同一联系人两封邮件间隔不得小于 N 天（默认 3），防误触重复发送。
7. **预览后确认**：界面必须先渲染预览，用户点「加入发送队列」才创建任务，不存在一键群发全部名单。
8. **实现说明（Phase 1）**：`check_send_guards` 返回结构化 `SendRejection`（`SENDER_CONFIG_MISSING / DO_NOT_CONTACT / INVALID_EMAIL / NO_SOURCE / SUPPRESSED / COOLDOWN / QUOTA`）；缺 `TRUEORDER_COMPANY_ADDRESS` 或 `TRUEORDER_SMTP_REPLY_TO` 一律拒发；联系人须有来源记录（`source` 必填，非 `manual` 还须 `source_ref`）；`QUOTA` 只延期到下一个 UTC 日、邮件保持 `queued`；发送前先落 `sending`，SMTP 报错标 `failed` 并交队列重试，重入遇到 `sending` 不重发（标 `failed` 待人工核对）。「当日」统一按 UTC 自然日计算。

### 3.6 联系人补全与抓取

**ContactFinder 端口**（domain/ports.py）：`find(domain: str, company_name: str) -> list[FoundContact]`。
- 适配器 `hunter.py` 读取 `TRUEORDER_HUNTER_API_KEY`；没有 key 时使用 `fake.py` 并在界面提示未配置。
- 只对用户在界面选中的企业触发，并先检查 `enrichment_calls` 当日用量是否超过 `TRUEORDER_ENRICH_DAILY_CAP`（默认 20）。
- 没有 `website` 的企业不调用接口，提示先填写官网。

**WebsiteCrawler**：
- 输入官网域名（已确认，或 3.7 节规则允许自动采用的高置信域名）；抓取首页以及路径中含 `contact/about/team` 的链接，最多 5 页。
- 先读 robots.txt（`urllib.robotparser`），不允许则放弃并记录。
- 同一主机两次请求间隔不少于 2 秒，超时 10 秒，单页大小上限 1 MB，仅 http/https。
- **SSRF 防护**：解析 IP 后拒绝回环、私网、链路本地地址，重定向后同样校验。
- 提取 `mailto:` 与文本里的邮箱、电话，记录来源 URL，`is_generic` 按前缀判定。
- 结果写入 `contacts`（`source=website`，`verify_status=unknown`），不自动联系。

### 3.7 自动填充规则（用户要求：拿到联系方式后尽量自动填）

补全流程：**企业 → 域名 → 联系人 → 验证 → 带入发信**，每一步都自动，但保留可见的来源与置信度。

1. **域名自动填**：补全服务或抓取返回域名时，写入 `companies.website`，同时记录 `website_source` 与 `website_confidence`（`high|medium|low`）。
   - `high`：服务返回的公司名与企业规范化名称完全一致，且国家一致；自动采用并继续查联系人。
   - `medium/low`：写入为候选并在界面标黄，**不自动查联系人**，由用户点「确认」后继续。理由：域名错了，会把别家公司的人当成客户，后面的发信就发错人。
2. **联系人自动写入**：查到的人直接进 `contacts`，带 `source`、`source_ref`、`acquired_at`。
3. **自动验证**：写入后自动排一个验证任务（Hunter Email Verifier），结果写 `verify_status`；`invalid` 的不进入发信候选。
4. **收件人自动带入**：在商机里点「写信」时，默认选中该企业**排序最优的一位**联系人：具名且 `valid` > 具名且 `unknown` > 通用邮箱；职位含 purchas/procure/buyer/sourcing/import/采购 的优先。用户可改选。
5. **批量补全**：买家列表支持「补全当前筛选的前 N 家」。
   - N 不得超过当日剩余额度；提交前显示将消耗的额度估计，由用户确认。
   - 已有联系人的企业跳过，已查过但无结果的企业 30 天内不重复查。
6. **不自动发信**：自动填充止于「带入收件人和渲染好的预览」，发送仍必须用户确认（3.5 第 7 条）。

## 4. 工作包

> 每个 WP 完成的标准：新增行为先有失败测试，后端 `uv run pytest -q`、前端 `pnpm test`、`pnpm exec eslint .`、`pnpm exec vue-tsc --noEmit` 全绿，单独一次提交，提交信息中文、说明动机。

### WP0 地基与边界（依赖：无；里程碑 M0）

**4.1 缺陷修复（先写失败测试）**
1. **同文件重复行**：`importers.import_bills` 在循环中把已处理的 `bill_hash` 加入已见集合；重复行计入 `duplicate_bills`，不得抛 500。验收：同一 CSV 内两行完全相同，导入成功，`inserted_bills == 1`，`duplicate_bills == 1`。
2. **CSV 公式注入**：导出时，单元格以 `= + - @` 或制表符、回车开头，则加前缀 `'`。验收：公司名 `=HYPERLINK(...)` 导出后以 `'=` 开头。
3. **上传上限**：产品、提单导入端点限制 20 MB（可配置），超出返回 413。验收：超限文件被拒且库内无新增。
4. **建产品只打分新产品**：`RescoreService` 增加 `rescore_product(product_id, as_of)`；`create_product` 调用它而不是 `rescore_all`。验收：已有产品的 `computed_at` 不变。
5. **并发建产品**：快速编号改用数据库序列或在 `code` 唯一约束冲突时重试；同名同税号同受众的产品返回 409，并带上已存在产品的 id。验收：两个并发请求不产生重复编号。
6. **打分内存与窗口**：`load_pool` 在 SQL 中加 `arrival_date >= as_of - 24 个月` 条件，避免载入全部历史。验收：新增测试，窗口外提单不进入候选，行为与旧版一致（现有领域测试不变）。
7. 抽出 `ProductOut` 映射到 `interface/mapping.py`；`_default_audience` 改为单产品查询；公司抽屉提单上限改为分页或返回 `truncated: true`；导出改为真正的流式输出。

**4.2 迁移与配置**
- 引入 Alembic，生成基线迁移（对应现有 5 张表），`bootstrap` 改为先 `alembic upgrade head` 再导入种子。
- 环境变量统一为 `TRUEORDER_` 前缀；AGENTS.md 里的 `DATABASE_URL` 改写成 `TRUEORDER_DATABASE_URL`。
- 删除空包 `backend/src/trueorder_backend/`，同步 `pyproject.toml` 的 scripts 与 build 配置。

**4.4 性能评估（用户：主要是获取信息，先评估，不预先过度优化）**

已读代码得到的确定事实：
- `raw_bills.hs_code` 只有普通 B-tree 索引，而 `load_pool` 用 `left(hs_code, 4) IN (...)` 过滤，这个条件**用不上该索引**，会全表扫描；`arrival_date` 没有索引。
- `load_pool` 把命中税号族的全部提单作为 ORM 对象载入内存，再在 Python 里分组。
- 每次导入或建产品都重算全部产品。

不确定、需要实测的部分：真实规模下的耗时和内存。请按下面步骤产出结论，写入 `docs/perf.md`：
1. 写 `backend/tests/perf/gen_bills.py`，生成合成提单（可配置 10 万 / 50 万 / 100 万行，企业数约行数的 1/20，税号集中在 3–5 个税号族）。
2. 在本机 PostgreSQL 上测：①导入耗时；②对单个产品 `rescore_product` 的耗时与峰值内存；③`list_buyers` 在 `q`、`country`、`tier` 组合下的 p95。
3. 目标值（达不到才需要优化）：10 万行导入 < 2 分钟；单产品打分 < 30 秒且内存 < 1 GB；买家列表 p95 < 300 ms。
4. 若不达标，按收益从高到低处理：先加索引 `(left(hs_code,4), arrival_date)`（表达式索引）；再把 `load_pool` 的过滤加上日期窗口；最后才考虑把打分聚合下推到 SQL 或分批处理。
5. 达标就不动，只把结论和规模上限（例如「验证到 100 万行」）写进文档。

**4.3 文档与 CI**
- 按第 2 节修订 `AGENTS.md`、`README.md`，新增 `docs/OUTREACH-COMPLIANCE.md`（DNS 的 SPF/DKIM/DMARC、预热建议、退订处理方式、各地区注意事项、「非法律意见」声明）。
- 把 `.review/` 下的冒烟脚本迁成 `backend/tests/smoke/`，使用已有的 `smoke` 标记。
- 增加 GitHub Actions：PostgreSQL 16 服务、后端 pytest、前端 lint/typecheck/test/build；校验 `schema.d.ts` 与后端 OpenAPI 一致（导出后 `git diff --exit-code`）。
- 先收口当前工作区未提交的前端重设计：跑通全部检查，补 `ScoreSummary.vue` 测试，再提交。

### WP1 联系人与来源（依赖：WP0；M1）

- 迁移：`contacts` 表、`companies.website` 两列。
- domain：`contacts.py`（邮箱规范化、通用邮箱判定、去重键）+ 单元测试。
- API：
  - `GET/POST /api/companies/{id}/contacts`
  - `PATCH/DELETE /api/contacts/{id}`
  - `POST /api/contacts/import`（CSV：company_id 或「企业名+国家」、name、title、email、phone）
  - `PATCH /api/companies/{id}`（改 `website`、`website_confirmed`）
- 一键清除某联系人的全部数据：硬删除联系人，并把相关活动里的 `contact_id` 置空、正文中的邮箱与姓名替换为 `[已删除]`。
- 前端：公司抽屉增加「联系人」区，可新增、编辑、标记不再联系；可填写官网。
- **第一期补充：联系人导出**
  - `GET /api/products/{id}/contacts/export.csv`：按买家列表同一组筛选（tier、国家、票数、搜索词）导出，每个联系人一行。
  - 列：公司名、国家、城市、等级、票数、最近到港、联系人姓名、职位、邮箱、电话、是否通用邮箱、验证状态、来源、来源链接、获取时间、官网、官网置信度。
  - 默认排除 `do_not_contact` 与 `verify_status in (invalid, bounced)`；可用参数 `include_invalid=true` 放开。
  - 沿用 WP0 的公式注入转义和流式输出。
  - 前端：买家列表工具栏增加「导出联系人」。
- 第一期没有活动表，故「清除联系人」只需硬删除联系人行；第二期加活动表时再补脱敏逻辑。
- 验收：同公司同邮箱重复新增返回 409；通用邮箱显示标签；清除后查不到该联系人；导出的 CSV 行数、列和排除规则符合上述约定。

### WP2 商机管道与跟进（依赖：WP1；M1）【第二期，第一期不实施】

- 迁移：`opportunities`、`activities`。
- domain：`pipeline.py` + 单元测试（所有合法与非法转换、自动推进、到期判断）。
- API：
  - `POST /api/opportunities`（从买家列表「加入跟进」，已存在则返回既有）
  - `GET /api/opportunities?stage=&product_id=&due=today`
  - `PATCH /api/opportunities/{id}`（阶段、意愿、下次跟进日、备注）
  - `POST /api/opportunities/{id}/activities`
  - `GET /api/opportunities/{id}/timeline`
- 前端：
  - 买家表每行增加「加入跟进」，已加入则显示当前阶段。
  - 新增 `#/pipeline` 看板，按阶段分列，可拖拽或下拉改阶段。
  - 新增「今日待跟进」列表，按意愿和到期日排序。
  - 公司抽屉增加时间线，并展示得分理由，便于写信时引用。
- 验收：非法转换返回 422；阶段变更自动产生 `stage_change` 活动；`lost` 必须填原因。

### WP3 任务队列与 worker（依赖：WP0；可与 WP1/WP2 并行；M2 前置）

- 迁移：`jobs`；`infrastructure/jobs.py`；`worker.py`。
- 测试（真 PostgreSQL）：两个 worker 并发不重复认领同一任务；僵死任务回收；失败退避；超过最大次数置 `failed`。
- `GET /api/jobs?status=` 只读接口加前端任务状态页。
- 启动方式写入 README：`uv run python -m app.worker`。

### WP4 补全与抓取（依赖：WP1、WP3；M2）

- 迁移：`enrichment_calls`。
- `ContactFinder` 端口、`fake.py`、`hunter.py`；`crawler.py`（3.6 节全部约束）。
- 迁移补充：`companies` 增列 `website_source`、`website_confidence`；`contacts` 增列 `rank_hint`（可选，缓存收件人排序）。
- domain：`contacts.py` 增加 `pick_best_recipient(contacts)` 与 `website_confidence(found_name, company, country)`，纯函数加测试，规则见 3.7。
- API：
  - `POST /api/companies/{id}/find-contacts?method=finder|website`，创建任务并立即返回任务 id；结果落入 `contacts`。
  - `POST /api/products/{id}/buyers/enrich`（参数：当前筛选条件加 `limit`）：返回额度估计，需带 `confirm=true` 才执行。
  - `POST /api/companies/{id}/website/confirm`。
- 任务链：域名发现 → 联系人查找 → 邮箱验证，三步各一个任务，失败可单独重试。
- 前端：公司抽屉的「查找联系方式」按钮、域名候选的确认入口、来源/置信度标签、额度用量；买家列表的批量补全入口（带额度估计确认框）。
- 联调：先用 Hunter 免费额度对 10 家企业手工评估，结果写入 `docs/finder-eval.md`，再进入自动化。
- 测试：
  - 抓取：用本地 HTTP 夹具覆盖 robots 拒绝、限速、超大页面、私网重定向被拒、邮箱提取、通用邮箱标记。
  - 补全：超出每日上限被拒绝；无 key 时走 fake 并提示。
  - 所有测试不访问外网。
- 验收：对一个有官网的企业，点击后任务完成，联系人带 `source` 与来源 URL。

### WP5 模板与发信（依赖：WP2、WP3；M3）【第二期，第一期不实施】

- 迁移：`email_templates`、`email_messages`、`suppressions`。
- domain：`outreach.py`
  - 模板变量渲染：`{company}`、`{contact_name}`、`{product}`、`{last_arrival}`、`{shipments}`、`{supplier}`、`{sender_name}`。缺变量时渲染失败并指出变量名，不输出空串。
  - 抑制判定、日额度计算、冷却判定。
  - 全部纯函数，带测试。
- `MailSender` 端口、`smtp.py`、`fake.py`。SMTP 完全可配置，不绑定任何服务商：`TRUEORDER_SMTP_HOST`、`_PORT`、`_USER`、`_PASSWORD`、`_SECURITY`（`starttls|ssl|none`）、`_FROM_NAME`、`_FROM_ADDRESS`、`_REPLY_TO`。自己的企业邮箱、SendGrid/Resend 的 SMTP 中继都按这组变量配置。
- 设置页提供「发送测试邮件到我自己」按钮，用于验证配置，不计入每日额度，也不写入商机活动。
- API：
  - 模板增删改查。
  - `POST /api/outreach/preview`（返回渲染结果与护栏检查结果）。
  - `POST /api/outreach/queue`（创建 `email_messages` 加任务，带 `scheduled_at`）。
  - `GET /api/outreach/messages`。
  - `GET/POST/DELETE /api/suppressions`。
- 前端：模板管理页；在商机详情里选择联系人加模板，先预览，再加入队列；发送日志页；抑制名单页；手动标记「已回复」并选意愿等级（写入 `email_in` 活动并推进阶段）。
- 验收（用 fake 发送器）：
  - 命中抑制名单的联系人不发送，状态为 `suppressed`。
  - 超过日上限的消息留在 `queued` 到次日。
  - worker 在发送中途被杀后重启，不重复发出同一封。
  - 缺少物理地址配置时，队列接口返回 422 并说明原因。
  - 发出邮件正文包含退订语句，头部包含 `List-Unsubscribe`。

### WP6 回复识别与序列（依赖：WP5；M4，可选）【第二期之后，第一期不实施】

- IMAP 轮询任务：按 `In-Reply-To` 或 `References` 头匹配 `message_id_header`；命中则写 `email_in` 活动并推进阶段；内容含 `STOP/unsubscribe/退订` 自动写入抑制名单；退信（DSN）自动把邮箱标 `bounced` 并写入抑制名单。
- 多步序列：模板可设「N 天无回复后发送下一封」，收到回复、退订、退信即终止；每步仍需遵守 3.5 的所有护栏，且序列启动前需用户确认整张名单。
- 这一包只在 M3 稳定运行后再启动。

### WP7 收尾（依赖：以上；贯穿）

- **第一期冒烟**：买家列表 → 选企业补全（fake 补全器）→ 域名与联系人自动写入 → 验证状态更新 → 导出联系人 CSV 并校验内容。
- 第二期冒烟（推迟）：买家列表 → 加入跟进 → 填联系人 → 预览发送（fake）→ 标记回复 → 推进到「样品/报价」。
- 更新 README 的使用说明与截图；`docs/OUTREACH-COMPLIANCE.md` 复核。

## 5. 依赖与并行

**第一期实际顺序：WP0 → WP1 与 WP3（可并行）→ WP4 → WP7（裁剪版）。** 下图为完整依赖，WP2/WP5/WP6 属第二期。

```
WP0 ──┬── WP1 ── WP2 ──┬── WP5 ── WP6(可选)
      │                │
      └── WP3 ─────────┼── WP4
                       └──（WP5 也依赖 WP3）
```

可并行的车道：
- 车道 A：WP1 → WP2（数据与管道）
- 车道 B：WP3（任务队列）
- WP0 完成后两条车道同时开工；WP4 需要 A 的 WP1 与 B 的 WP3；WP5 需要 WP2 与 WP3。

多个智能体同时开发时：每个 WP 一条分支；迁移文件按顺序编号，**合并前必须 rebase 并确认迁移头唯一**；`schema.d.ts` 由 `pnpm gen:api` 生成，不手改。

## 6. 通用工程规则（所有智能体）

- 新增业务规则放 `domain/`，写成纯函数，测试零 mock。
- 外部系统（Hunter、抓取、SMTP、IMAP）只经端口访问，测试用 fake，**测试不得访问外网或真实 SMTP**。
- 凭据只走 `TRUEORDER_*` 环境变量或 `.env`；不得写进源码、测试夹具、截图或日志。日志中邮箱只记录域名部分以外的字符的掩码形式。
- 不得绕过 3.5 的发送护栏，也不得为测试方便在生产路径里加开关；测试用 fake 发送器与测试配置。
- 不得修改 `D:\MyProjects\GoodJob`。
- 提交粒度：每个 WP 内按「失败测试 → 实现」小步提交，信息中文。
- 遇到本文没有覆盖、且会改变数据模型或外发行为的决定，停下来向用户确认，不要自行扩大范围。

## 7. 已确认的决定（用户答复，2026-10-10）

1. **补全服务由我选**：见第 8 节，主选 Hunter，备选 Snov.io，经 `ContactFinder` 端口可切换。
2. **发信**：走用户自己的邮箱 SMTP，同时支持配置任意 SMTP 服务（含 SendGrid/Resend 的 SMTP 中继）。重点是拿到客户联系方式，发信是次要能力。
3. **联系方式自动填充**：补全拿到的联系人自动写入，并自动带入发信收件人（规则见 3.7）。
4. **性能**：主要用途是获取信息，性能先评估再决定投入，见 WP0 的 4.4。

仍需用户在 WP5 开工前提供：发件人名、发信物理地址（合规必填）、SMTP 账号（走环境变量）。

5. **出海包 v0.1（2026-10-16 决定）**：先作为**内部工具**在本仓库实现，定位不变（自家企业用、单用户、不计费、不售卖名单）。范围只到「发出第一批开发信草稿 + 处理询盘」：今日任务台（14 天清单）、产品档案（products 的 1:1 扩展，主推 ≤5）、买家线索库（CSV 导入，复用 companies/contacts）、开发信工作台（`DraftWriter` 端口，无 AI Key 走模板，**只生成不发送**，沿用勿联系/抑制名单护栏）、询盘与报价（状态流 新询盘/已报价/等样品/赢单/丢单，PI 用纯标准库极简 PDF 导出）。不做：自动发信/WhatsApp、建站、广告、物流报关、支付、多用户、计费。若将来对外售卖，需先改本节与 AGENTS.md 定位再拆。

## 8. 补全服务选型

> 价格与额度来自厂商博客与评测文章，各来源数字互相矛盾，**不可作为依据**；实现前以官网为准。以下只确定架构选择。

| 服务 | 定位 | 取舍 |
| --- | --- | --- |
| **Hunter（主选）** | Domain Search（按域名列出邮箱）、Email Finder（姓名+域名）、Email Verifier（验证邮箱） | 有 REST API，有每月免费额度可用于开发联调；搜不到结果一般不扣额度；验证接口可自动跑，用于填 `verify_status`。其 Domain Search 据称也可传公司名，实现时核对官方文档，能用就免去「先找域名」这一步 |
| **Snov.io（备选）** | 域名搜索、邮箱查找、验证，有免费档 | 作为第二个适配器，主选查不到时可由用户在界面选择改用它 |
| Apollo | 数据库大，含职位信息 | 额度按邮箱和手机分别计价，且数据偏北美；先不接，端口留好即可 |

决策理由：
- 本产品的目标客户是进口商和工厂，多为中小企业，通用邮箱占比高，所以「按域名列邮箱」加「验证」这条路最直接。
- 提单数据没有域名，所以域名发现（第 3.7 节）和邮箱发现同样重要，两者要一起设计。
- 适配器只依赖端口，换服务不改业务代码。WP4 必须实现 Hunter 和 fake，Snov.io 适配器标为可选。
- 实现前先用免费额度手工跑 10 家样本企业，记录命中率，写进 `docs/finder-eval.md`，再决定是否需要备选服务。
