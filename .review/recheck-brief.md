# TrueOrder 复审指令（第二轮，只读，不修改任何文件）

你是独立审阅者，工作目录为仓库根 `D:\MyProjects\TrueOrder`。这是对「findings 修复轮」的复核。

## 背景

上一轮审阅（`.review/cursor-findings.txt`，7 条 F1-F7）已由实现方处理：
处理记录见 `.review/HANDOFF.md` 的「Findings 台账」一节，修复全部在 commit `aae6768`。

## 任务

1. **逐条复核** F1-F7 的修复（`git show aae6768` 看 diff，再看相关文件全貌）：
   - 修复是否正确、完整地消除了原 finding 指出的问题？
   - 新增测试是否真实锁住行为（不是形式化断言）？
   - 修复有没有引入新缺陷或回归？
   - 台账中「部分采纳/保留」的取舍（F6 保留 LOGISTICS/FREIGHT、F3 保留法律后缀折叠）是否站得住？
2. **抽查上一轮遗漏**：修复 diff 触及的文件（scoring.py / parse.py / queries.py / bootstrap.py / CompanyDrawer.vue / BillTable.vue / ReasonList.vue / ProductDetailView.vue / api/products.ts）以及它们波及的调用方，有无新暴露的问题。
3. 边界：**只读**。不修改/创建/删除文件，不执行改变状态的命令（psql 只读查询可用；数据库 `postgresql://trueorder:trueorder@localhost:5433/trueorder`）。不需要跑完整测试套件（实现方结果：后端 121 通过、前端 18 通过，已记录在台账）。

## 输出格式（严格遵守，最终回答必须就是 FINDINGS 全文，不要写入文件）

```
## FINDINGS

### F1' [P0|P1|P2] 标题
- 位置：文件:行
- 问题：<描述与证据>
- 影响：<错误行为>
- 建议：<怎么修>

## 复核结论
逐条给出 F1-F7 的复核状态：verified（修复有效）/ partial（部分有效，说明缺口）/ regressed（引入新问题）。
一段话总结：修复轮是否可交付。
```

若未发现新问题，仍需逐条给出 F1-F7 的 verified/partial/regressed 状态并显式声明「未发现新 P0/P1 问题」。
