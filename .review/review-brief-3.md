# 审阅 Brief 3：快速建产品 + 前端改版（fa8e468 + a1981eb）

## 范围

- diff：`git diff aaf9e7b..a1981eb`（忽略 `.review/screenshots/`、`.review/redesign/` 截图与文档）
- 两个特性提交：
  1. `fa8e468` 主交互改为「填产品找客户」：POST /api/products + QuickStartForm + 首页改版
  2. `a1981eb` 前端视觉与交互改版：设计系统重写（main.css）+ Esc 关抽屉 + 空结果指引

## 背景与不变量（复核时必须守住的硬约束）

- 见仓库根 AGENTS.md：数据源只限授权 CSV/演示样本；领域层不 import 框架；分层依赖单向；每条理由带提单 id。
- 交互主线（用户定调）：「我填我的产品，系统帮我找对应客户」——表单是主入口，CSV 导入是数据准备入口。

## 改动清单（复核起点，不是终点）

后端：
- `app/domain/parse.py`：新增 `suggest_buyer_keywords`（受众默认买家词）与 `build_quick_product`（表单 → ProductConfig：校验名称/税号/受众；买家词未填用默认；both 拆两类受众税号）
- `app/infrastructure/repositories.py`：`SqlProductRepository.next_quick_code()`（QUICK-000n 递增）
- `app/interface/routers/products.py`：`POST /api/products`（建产品 → 立即 rescore → 返回带计数 ProductOut）
- `app/interface/schemas.py`：`ProductCreateIn`；`app/interface/deps.py`：`get_product_repository`

前端：
- `QuickStartForm.vue`（新组件，检索单表单）、`ProductsView.vue`（hero 改版）、`ScoreSummary.vue`（抽屉摘要拆分）
- `CompanyDrawer.vue`：Esc 关闭（窗口级 keydown，随抽屉开关挂/卸 + onBeforeUnmount 清理）、标题层级徽章
- `ProductDetailView.vue`：`hasNoBills` 空结果指引（audienceCounts 总数为 0 时提示去导入）
- `BuyerTabs/BuyerTable/ProductCard/ProductHeader/ImportPanel`：层级色轨、mono 数据面、眉题
- `main.css`：设计 token 全量重写（海关青/三色信号/等宽数据面），保留旧类名与 `--accent` 等别名
- `eslint.config.js`：browserGlobals 增加 KeyboardEvent

## 重点核查方向

1. **事务边界**：POST /api/products 里 upsert_product 只 flush 不 commit，靠 importer.rescore 内的 commit 落库——中途异常是否留下半状态？生产 get_session 关闭时未提交变更是否回滚？
2. **next_quick_code 并发/正确性**：LIKE 'QUICK-%' + isdigit 后缀取 max 的方案，code 列有无 UNIQUE 约束兜底（看 orm.py）？两次 POST 同 code 会怎样？
3. **默认买家词语义**：默认词不含行业词 → 精准层缺席是设计取舍（接口测试已锁），但 build_quick_product 对 peer_keywords 不给默认——同行排除在快速建的产品上静默失效，是否需要提示？
4. **Esc 监听生命周期**：CompanyDrawer 的 watch([companyId, productId, audience]) 每次先 remove 再按需 add——有无重复挂载/泄漏路径？组件卸载时是否干净？
5. **空结果指引判定**：hasNoBills 用 audienceCounts（both 产品按受众细分），受众切换瞬间会否误报/漏报？
6. **CSS 兼容**：旧类名/别名是否全覆盖（grep 模板里 var(--ok/--danger/--accent) 等）；BillTable/ReasonList 的 scoped 样式与全局新 token 是否冲突。
7. **前端表单校验与后端校验的一致性**（税号规则、关键词切分）以及测试是否锁住关键行为。

## 输出格式（严格遵守）

最终回答必须就是 FINDINGS 全文，不要写入任何文件。每条：

```
### F# [P0/P1/P2] 标题
- 位置：文件:行
- 问题：…
- 影响：…
- 建议：…
```

结尾给复核结论表（编号 / 状态 verified 或 rejected / 一句话说明），并明确列出「未发现新 P0/P1」或列出之。
