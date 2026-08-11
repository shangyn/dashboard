# 两年对比：国际总计台数排除改造梯

**日期**: 2026-07-08
**状态**: 设计中

---

## 需求

两年对比表（数据表格 + 年度完成比）最后一行「国际总计」中：
- **签订台数合计、排产台数合计、发货台数合计** 目前包含了改造梯的台数
- 需要改为：这三项台数合计 **不包含改造梯的台数**
- 金额类字段（签订额、排产额、发货额、回款及各种合计额）**保持不变**

## 当前问题

### 数据聚合 (`get_two_year_comparison`)

- 合同按 `(大区, 模块)` 聚合，改造梯归属 `(商贸合计, 改造)`
- 国际总计（grand_total）聚合了 `agg` 中**所有**条目，包括改造梯
- 因此签订台数/排产台数/发货台数的合计中包含了改造梯台数

### Excel 导出

- 两年对比 Excel：grand_total 行台数列用 `SUM(所有含"合计"的行)`，包含备件商贸合计
- 年度完成比 Excel：grand_total 行台数列用 `SUM(所有subtotal行)`，包含商贸合计

## 改动方案

### 1. 后端聚合 — `services.py:get_two_year_comparison()`

在 grand_raw 聚合完成后，减去改造模块的台数：

```python
# 国际总计的台数不包含改造梯
gaizao_key = ('商贸合计', '改造')
if gaizao_key in agg:
    gz = agg[gaizao_key]
    for field in ['sign_units_prev', 'sign_units_curr',
                  'schedule_units_prev', 'schedule_units_curr',
                  'ship_units_prev', 'ship_units_curr']:
        grand_raw[field] = grand_raw.get(field, 0) - gz.get(field, 0)
```

> 效果：前端看板KPI卡片、数据表格、年度完成比表的 grand_total 台数自动修正。

### 2. 两年对比 Excel 导出 — `export_two_year_comparison_xlsx()`

台数列（sign_units, schedule_units, ship_units）在 grand_total 行中，将 SUM 公式改为 **排除备件商贸合计行**：

- 当前：`SUM(所有含"合计"的行)`
- 改为：遍历找所有含"合计"的行时，跳过 module 值为"备件商贸合计"的行

### 3. 年度完成比 Excel 导出 — `export_annual_completion_xlsx()`

台数列（sign_units, schedule_units, ship_units）在 grand_total 行中，将 SUM 公式改为 **排除商贸合计 subtotal 行**：

- 当前：`SUM(所有subtotal行)`
- 改为：遍历 subtotal 行时，跳过 region 为"商贸合计"的行

### 4. 不改动的部分

- 前端组件（自动读取后端修正后的数据）
- 大区小计行
- 备件商贸合计行自身
- 所有金额字段
- 增长率计算（自动基于修正后的 prev/curr 计算）

## 影响文件

| 文件 | 改动 |
|------|------|
| `backend/dashboards/contract_completion/services.py` | 1处：grand_total 聚合后减去改造梯台数；2处：Excel 导出公式过滤 |
