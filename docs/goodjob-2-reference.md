# GoodJob 2.0 参考对照（2026-10-11，只读评估）

> 参考仓库：https://github.com/huangguojia/GoodJob.git（评估时 master=2.05，浅克隆于本机临时目录，未改动原仓库）。
> 结论先行：**代码不可直接搬**（TS/Node + MySQL，TrueOrder 是 Python/FastAPI + PG），但**设计契约与踩坑经验对第二期高度可用**——它在 TrueOrder 第二期要做的三块（发信、回复识别、域名发现）都已趟过并有测试固化的行为契约。

## 模块对照表

| GoodJob 2.0 模块 | 对 TrueOrder 的价值 | 对应物/去向 |
| --- | --- | --- |
| `inbound-mail-watcher.ts`（IMAP 回信/退信监听） | **高**：即 WP6「回复识别」。可直接借的设计原则：只读不删邮件、连接失败只写状态不影响主服务；归属识别 In-Reply-To/References 优先、发件人+最近发信兜底；**分类保守**（能确定退信/退订/拒绝才下判断，其余 auto_unknown 交人工） | WP6 规格输入 |
| `outreach-email-sequencer.ts`（阶段感知发信序列） | **高**：即 WP5。核心思想：「第几封」→「接着客户现在的阶段走」（已回复/已发5封的人不再从首触发一遍）；两条纪律值得照抄——**中文绝不进英文信**（englishOnly 守卫）；**无 AI 也要能出可直接发的兜底模板** | WP5 规格输入 |
| `development-email-skill.ts`（分阶段写信蓝图） | 中高：objective/angle/mustInclude/mustAvoid/maxWords/subjectRule 的信件蓝图结构 | WP5 模板设计 |
| `email-delivery-security` / `sender-mailbox` / `sent-folder-archive` / `email-tracking` | **高**：发送护栏与追踪的完整清单，用来**交叉验证 DEV-SPEC 3.5**（日上限/冷却/退订/Message-ID 关联）有没有漏项 | WP5 护栏核对 |
| `prospect-website-discovery.ts`（域名发现） | 中：公司后缀归一化集合（inc/llc/gmbh/sa/srl/bv/plc…）可与我们的 `normalize_company_name` 对照查漏；候选置信度流可对照 WP4 已实现的 `website_confidence` | 对照改进 WP4 |
| `prospect-contact-enrichment` / `website-contact-ai` / `website-probe` | 中：与 WP4 的 finder/crawler 同题，可对照提取规则 | 对照改进 WP4 |
| `provider-request-ledger` / `provider-response-cache` / `provider-runtime` / `prospect-fake-provider` | 中：按次源的请求台账（≈我们的 enrichment_calls）+ **响应缓存**（同企业短期不重复查，比我们只记 30 天更细）+ fake provider 模式（我们同构） | 额度/审计对照 |
| `shipment-ocr` / `trade-document-import`（贸易单据 OCR 导入） | 中：**PDF/图片提单→结构化入库**的思路。若授权数据以单据形式交付，这是补充导入通道；不改变 R1（全量授权数据需采购） | 备选导入通道 |
| `customs-export` / `market-trade-observations` / 各贸易统计 provider | 低：国家汇总数据，TrueOrder 计划已明确排除（无公司名） | 不采用 |
| `whatsapp-plugin`（Baileys/Meta，独立服务） | 低（当期）：独立 TS 服务可旁路部署不进库；若第二期后想加 WhatsApp 触达可作为独立组件并置 | 暂不采用 |
| AI agent 执行链 / 企微 / 考试 / 报表 | 范围外 | 不采用 |

## 关键提醒

1. **约束不变**：GoodJob 的 google-places/apollo 类按次 provider 正是 TrueOrder 硬约束禁止灌库的路径；借它的**治理模式**（台账/缓存/日上限），不借它的数据入库策略。
2. **R1 依旧**：GoodJob 没有解决「授权全量提单」的采购问题；它的海关相关是单据 OCR 导入，不是提单库。
3. **第二期开工时**：WP5/WP6 的规格撰写应先读对应模块的**测试文件**（行为契约固化处），把契约移植成 Python 版验收标准。
