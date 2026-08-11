# 商贸数据集成 — 设计文档

**日期**: 2026-07-06
**状态**: 已确认

## 背景

两年对比看板中商贸1/2/3模块无数据，需要从 `商贸数据.xlsx` 读取。

## 数据源

- 文件: `商贸数据.xlsx` Sheet1
- 列: 模块 | 签订额 | 回款额 | 排产额 | 发货额
- 单位: 万元（Excel原始值）
- 周期: 2026年1-6月累计（每日可能更新覆盖）
- 3行: 商贸1, 商贸2, 商贸3
- 无2025历史数据

## 设计

### 数据流

```
商贸数据.xlsx 上传 (万元)
  → parse_trade_data: 万元×10000→元 存模型
  → get_two_year_comparison(): 读模型, 注入agg['商贸合计', tmod]
  → _wan(): 元÷10000→整数万元 显示
```

### 模型: TradeModuleData (`cc_trade_module_data`)

| 字段 | 类型 | 说明 |
|------|------|------|
| data_year | Integer | 年份 |
| module_name | String | 商贸1/2/3 |
| sign_amount | Float | 签订额(元) |
| payment_amount | Float | 回款额(元) |
| schedule_amount | Float | 排产额(元) |
| ship_amount | Float | 发货额(元) |

### 文件改动

1. `models.py` — 新增 TradeModuleData
2. `handlers.py` — 新增 parse_trade_data
3. `upload/handlers.py` — 注册 contract_trade_data
4. `services.py` — get_two_year_comparison() 注入商贸数据
5. `seed.py` — 添加权限
