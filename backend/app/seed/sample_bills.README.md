# sample_bills.csv —— 非全量公开样本（演示用）

> **这不是全量库。** 本文件是演示样本，用于在拿到授权提单数据之前，把产品页、
> 打分规则、排除规则和 CSV 导出整条链路跑通。页面上的「非全量样本」声明即指此文件。

## 性质与来源口径

- **非全量**：只有 26 票，覆盖两个示例产品的打分与排除场景；真实美国海运提单
  授权数据需另行购买并允许建索引后，通过同一个导入入口（`POST /api/bills/import`
  或 `uv run python -m app.bootstrap`）灌入。
- **结构对齐公开样本**：字段结构（到港日期、提单号、收货人、发货人、原产国、
  税号、货物描述、卸货港、数量）与美国海关提单公开样本的字段一致，可直接替换。
- **公司名为虚构**：样本中的公司名、地址、提单号均为演示构造，不指向真实企业；
  税号 620462（女士棉质裤）与 480810（瓦楞纸板原纸）为真实 HS 编码。
- **日期基准**：样本日期以 2026-10 为「今天」设计。打分窗口是滚动的
  （近 24 个月 / 近 12 个月），距离该基准太久之后重新导入，精准/潜在的划分会漂移，
  属预期行为。

## 样本覆盖的规则场景

| 场景 | 样本中的公司 | 预期结果 |
| --- | --- | --- |
| 精准客户（进口商） | BROOKLYN APPAREL LLC：12 个月内 3 票、同一供货方、业务词命中 | 精准 |
| 潜在客户（单票） | LONE STAR CLOTHING CO：近 24 个月仅 1 票 | 潜在 |
| 供货方轮换 | PACIFIC FASHION WHOLESALE INC：12 个月 2 票但两家供货方 | 潜在 |
| 精准客户（工厂） | GREAT LAKES PACKAGING CORP / PACIFIC BOX & CARTON CO | 精准 |
| 工厂业务词不匹配 | ACME TRADING LLC：重复进口但名称无行业词 | 潜在 |
| 同名冲突标记 | UNION PACKAGING（长滩 / 迈阿密两个城市线索） | 潜在 + 同名冲突 |
| 空抬头 | TO THE ORDER OF WELLS FARGER | 排除 |
| 银行抬头 | FIRST NATIONAL BANK OF OMAHA | 排除 |
| 货代 | GLOBAL FREIGHT FORWARDING INC | 排除 |
| 集团内部供货 | VN GARMENT JOINT STOCK CO 自发自收 | 排除 |
| 同行海外公司 | SHENZHEN GARMENT FACTORY USA INC | 排除 |
| 税号误码 | MYSTERY BUYERS LLC（6204X2） | 排除 |
| 超 24 个月 | ANCIENT TRADING CO（2024-05） | 不入池 |
| 非中国/越南原产 | TIJUANA TEXTILES（原产 MX） | 不入池 |
| 税号不符 | OTHER STYLE APPAREL（620442） | 不入池 |
| 成品税号误配 | SNACKFOOD BRANDS（4819 纸箱成品，非 480810 原纸） | 不入池（对纸板产品） |

## 字段说明

| 列 | 说明 |
| --- | --- |
| arrival_date | 到港日期（YYYY-MM-DD） |
| bill_number | 提单号（去重指纹的一部分） |
| consignee_name / consignee_address / consignee_country | 收货人（企业按规范化名称+国家归并） |
| shipper_name / shipper_address / shipper_country | 发货人（shipper_country 缺省时按原产国） |
| origin_country | 原产国（潜在池要求 CN / VN） |
| hs_code | HS 税号（6~10 位数字；非法格式按税号误码处理） |
| product_description | 货物描述 |
| port | 卸货港 |
| quantity | 数量（原样保存） |
