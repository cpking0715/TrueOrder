# 审阅 Brief 4：WP3 任务队列 + WP4 补全与抓取 + WP7 第一期收尾

## 范围

- diff：`git diff add2a70^..c19fe49`（三个提交：add2a70 任务队列 / 4769d94 补全与抓取 / c19fe49 收尾文档与冒烟）
- 对应 DEV-SPEC（docs/DEV-SPEC.md）工作包：WP3（3.4 后台任务）、WP4（3.6 补全与抓取、3.7 自动填充）、WP7（第一期冒烟收尾）

## 硬约束（复核时必须守住，见仓库根 AGENTS.md）

- 按次补全仅对用户选定企业、有日上限、来源可追溯；禁止无人触发全库补全
- 只抓企业自有官网公开页（robots/限速/SSRF）；不爬提单网站
- 外部系统只经端口访问，测试不访问外网与真实 SMTP
- 分层依赖单向；领域层零框架依赖；每条得分理由带提单 id（既有约束，勿回归）

## 已知取舍（HANDOFF 已记录，审阅时验证而非重复提出）

- 3.6「无官网不调接口」与 1.4.1「自动补全域名」矛盾 → 按后者实现（域名发现受同样额度/审计约束）
- 无 Hunter Key 走 fake 演示源，source_ref 带 fake 标注；不排验证任务
- add2a70 曾漏提交 frontend/src/features/jobs/，4769d94 已补（如 diff 中该目录出现在 4769d94 属预期）

## 重点核查方向

1. **额度约束可绕过吗**：find_contacts 处理器在认领时查 calls_today——并发多个任务同时 running 时会否同时通过检查（额度超扣）？batch enrich 的 remaining 截断与单任务执行时点之间的一致性？
2. **爬虫 SSRF 完整性**：_host_is_fetchable 的 DNS 解析时机（TOCTOU：解析通过后连接时再解析可能不同）、重定向链每跳复检、robots 失败按允许处理的取舍。
3. **永久失败 vs 退避的边界**：哪些异常路径会错误地永久失败（该重试的）或错误地退避（确定性的）？RuntimeError(首页失败) 的选择。
4. **事务边界**：处理器内 repo.add（行级 commit）与 queue.enqueue 的 commit 交错；任务 complete 前崩溃会否重复写联系人（幂等性靠邮箱唯一索引？）。
5. **worker 进程**：`python -m app.worker` 的会话生命周期（每轮新建）、Ctrl-C 安全、handlers 注册表为空字典时的行为。
6. **接口层**：enrich 两段式的竞态（估计后别人消耗额度）、confirm 截断语义与 spec「N ≤ 当日剩余额度」的一致性；422/404/202 状态码语义。
7. **前端**：EnrichBar 两段式状态机、WebsiteField 确认后重载链、ContactsPanel 入队提示；测试是否锁住关键行为。
8. **冒烟质量**：新增两条 smoke 是否真的覆盖「域名与联系人自动写入 → 验证状态 → 导出校验」，还是只覆盖 happy path。

## 输出格式（严格遵守）

最终回答必须就是 FINDINGS 全文，不要写入任何文件。每条：

```
### F# [P0/P1/P2] 标题
- 位置：文件:行
- 问题：…
- 影响：…
- 建议：…
```

结尾给复核结论表（编号 / 状态 verified 或 rejected / 一句话），并明确「未发现新 P0/P1」或列出之。
