# TrueOrder 独立审阅指令（只读，不修改任何文件）

你是独立审阅者。仓库根目录即当前工作目录（`D:\MyProjects\TrueOrder`）。实现由另一位工程师（ZCode）完成，你不是实现者，请保持独立判断。

## 输入材料（按顺序读）

1. 计划原文（含「回来后我审什么」一节）：`C:\Users\15755\.cursor\plans\品类客户汇聚平台_e63b6abd.plan.md`
2. 实现交接文档：`.review/HANDOFF.md`
3. 仓库 `AGENTS.md`（分层与硬约束）、`README.md`
4. 代码：`backend/app/`（domain / infrastructure / interface 分层）、`backend/tests/`、`frontend/src/`、`frontend/tests/`
5. 种子样本：`backend/app/seed/`

## 审阅重点（按优先级）

A. **计划符合性**（计划文件「回来后我审什么」原文）：
   1. 产品是入口而不是税号入口；
   2. 工厂产品用的是原料税号（纸板 480810 而非纸箱 4819）；
   3. 样本页标明非全量；
   4. 六类排除规则真实生效（TO THE ORDER OF / 银行 / 货代 / 集团内部 / 同行海外 / 税号误码）；
   5. 得分理由能点回提单；
   6. 没有把按次查询源（Apollo / People Data Labs / Hunter / Google Places）灌进库，没有爬提单网站的代码路径。

B. **HANDOFF「Review 焦点」五条**：
   1. `backend/app/domain/scoring.py` 分层与排除顺序的语义正确性（尤其 EX_PEER_OVERSEAS 关键词逻辑）；
   2. `backend/app/infrastructure/queries.py` 买家查询的 FTS + 筛选组合是否有 SQL 语义漏洞（行数膨胀等）；
   3. `backend/app/infrastructure/importers.py` 去重哈希字段选择的误合并/误区分风险；
   4. 前端 `useBuyerFilters` 的参数构造与导出 URL 是否与列表请求完全一致（导出「当前筛选」等价性）；
   5. 非全量声明链路三处口径一致（`/api/meta` → 前端横幅 → 种子 README）。

C. **常规质量**：分层违规（domain 不得 import 框架）、注入风险（CSV/FTS 查询参数）、DTO/领域/表模型混用、测试是否真的锁住行为（不是形式化测试）、明显性能问题。

## 边界

- **只读审阅**：不要修改、创建、删除任何文件；不要执行会改变状态的命令。允许只读命令（ls、读文件、git log/diff/show、psql 只读查询若必要）。
- 数据库在 `postgresql://trueorder:trueorder@localhost:5433/trueorder`（Docker 容器 trueorder-pg），测试库 `trueorder_test`。
- 不需要跑完整测试套件（实现方已跑过并贴在 HANDOFF）；抽查即可。

## 输出格式（严格遵守，最后输出）

```
## FINDINGS

### F1 [P0|P1|P2] 标题
- 位置：文件路径:行号
- 问题：<具体描述，引用证据>
- 影响：<会导致什么错误行为>
- 建议：<怎么修>

（每条一个 F 编号；P0=正确性/合规问题必须修，P1=应修，P2=可选改进）

## 总结
一段话：计划符合性结论 + 测试可信度结论 + 是否可交付。
```

没有问题时也要显式说「未发现 P0/P1 问题」。
