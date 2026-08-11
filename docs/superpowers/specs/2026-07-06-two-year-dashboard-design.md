# 两年对比看板 — 设计规格书

**日期:** 2026-07-06
**状态:** 已确认，待实施

---

## 1. 概述

将 TwoYearComparison 页面的「图表视图开发中」占位符替换为完整的增长率驱动数据看板，同时重构整体页面布局。

### 核心原则

- **增长率优先**：大字展示同比增长%，绝对值退为辅助小字
- **数据完整**：覆盖全部 7 个核心指标（签订台数/额、排产台数/额、发货台数/额、回款）
- **灵动布局**：避免死板表格，用卡片+热力图+排行条形成视觉节奏
- **可筛选**：大区下拉框切换，默认全部大区

### 受众

领导层快速概览 — 1 分钟内掌握全局增长态势

---

## 2. 数据源

### API

`GET /api/contract-completion/two-year-comparison`

**返回结构：**
```json
{
  "title": "国贸签订、排产、发货两年对比",
  "date_prev_end": "2025-06-30",
  "date_curr_end": "2026-06-30",
  "year_prev": 2025,
  "year_curr": 2026,
  "metric_groups": [
    {"id": "sign_units",      "name": "签订台数",       "has_growth": true},
    {"id": "sign_amount",     "name": "签订额\n（万元）", "has_growth": true},
    {"id": "schedule_units",  "name": "排产台数",       "has_growth": true},
    {"id": "schedule_amount", "name": "排产额",         "has_growth": true},
    {"id": "ship_units",      "name": "发货台数",       "has_growth": true},
    {"id": "ship_amount",     "name": "发货额",         "has_growth": true},
    {"id": "payment",         "name": "回款",           "has_growth": false}
  ],
  "region_order": ["俄罗斯","中亚","亚洲1","亚洲2","美洲","中东","非洲","欧洲"],
  "rows": [
    {
      "type": "data|subtotal|trade|grand_total",
      "region": "俄罗斯",
      "module": "空压机",
      "category": "空压机",
      "sign_units_prev": 100, "sign_units_curr": 125, "sign_units_growth": 25,
      "sign_amount_prev": 5000, "sign_amount_curr": 6000, "sign_amount_growth": 20,
      ...
    }
  ]
}
```

### 核心指标（7个）

用于看板展示的指标 ID：
1. `sign_units` — 签订台数
2. `sign_amount` — 签订额
3. `schedule_units` — 排产台数
4. `schedule_amount` — 排产额
5. `ship_units` — 发货台数
6. `ship_amount` — 发货额
7. `payment` — 回款

排除指标（数据为空/合计列）：`overseas_diff`, `sign_total`, `overseas_payment`, `payment_total`

---

## 3. 页面布局重构

### 现状 → 目标

```
❌ 旧布局：
┌─────────────────────────────────────┐
│ 标题                    日期 导出 大区│  ← 顶行
├────┬────────────────────────────────┤
│看板│                                │
│    │       内容区                    │
│表格│                                │
│    │                                │
└────┴────────────────────────────────┘
  90px 侧栏（呆板，占空间）

✅ 新布局：
┌─────────────────────────────────────┐
│ 标题  [看板|表格]      日期 大区 导出│  ← 一体化控制栏 52px
├─────────────────────────────────────┤
│                                     │
│         全宽内容区                   │
│                                     │
└─────────────────────────────────────┘
```

### 顶部控制栏

- **左侧**：标题（16px bold）+ Segmented Control（看板/表格切换，iOS 风格圆角滑块）
- **右侧**：日期范围说明（小字灰色）+ 大区下拉框 + 导出Excel 按钮
- 高度 52px，白色背景，底部细线分隔

### Segmented Control 规格

- 容器：`background: #f1f5f9; border-radius: 8px; padding: 3px`
- 选中态：`background: #fff; color: #1a73e8; font-weight: 700; box-shadow: 0 1px 3px rgba(0,0,0,0.1)`
- 未选中：`color: #888`
- 无边框，纯背景对比

---

## 4. 看板视图设计

### 4.1 增长率卡片行（7列）

```
┌─────────┬─────────┬─────────┬─────────┬─────────┬─────────┬─────────┐
│ 📝签订台数│ 📝签订额 │ 🏭排产台数│ 🏭排产额 │ 🚚发货台数│ 🚚发货额 │ 💰回款  │
│  +18%   │  +18%   │  +14%   │  +13%   │   -4%   │   -3%   │  +23%   │
│2850→3360│10660→..│1920→2190│8280→..  │1560→1498│7380→..  │5560→..  │
└─────────┴─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘
```

- 卡片：`border-radius: 10px; box-shadow: 0 1px 4px; padding: 12px 10px`
- 增长率：`font-size: 24px; font-weight: 800`，正数绿色 #059669，负数红色 #dc2626
- 绝对值：`font-size: 9px; color: #bbb`，辅助信息

### 4.2 增长率热力图（大区 × 7指标）

- 标题：「📊 同比增长率总览」
- 图例：🟢 增长 / 🔴 下降（右上角小字）
- 表格形式，每格背景色标示：
  - 增长：`background: #d4edda; color: #155724`（浅绿底深绿字）
  - 下降：`background: #f8d7da; color: #721c24`（浅红底深红字）
  - 无数据：`background: #f5f5f5; color: #999`（灰色）
- 行：大区（按 region_order 排序）
- 列：7 个核心指标
- 大区名称前加国家旗帜 emoji

### 4.3 排行双栏（底部）

```
┌──────────────────────┬──────────────────────┐
│ 🏆 签订额增长最快     │ ⚠️ 签订额下降        │
│ 俄罗斯  ████████ +22%│ 中东    ██████   -8% │
│ 亚洲1   ██████   +15%│ 中亚    ████     -5% │
│ 非洲    ████     +12%│ 欧洲    ██       -2% │
└──────────────────────┴──────────────────────┘
```

- 水平条形图，纯 CSS 实现（不需要 ECharts）
- 按签订额增长率排序，取 Top 3 / Bottom 3
- 排除「国际总计」等汇总行

### 4.4 单大区下钻

选择具体大区时：
- 热力图替换为模块级增长率明细表（行=模块，列=7指标）
- 顶部显示所选大区标签 + 摘要
- 模块行同样用绿/红色块标示增长率

---

## 5. 表格视图

- 保留现有 `TwoYearTable.vue` 组件
- 现在获得全宽空间（不再被左侧栏挤压）
- 大区筛选同样生效

---

## 6. 交互行为

| 操作 | 行为 |
|------|------|
| 切换 Segmented Control | 看板 ↔ 表格，不重新请求数据 |
| 选择大区 | 两个视图同步筛选，看板热力图切为模块明细 |
| 选择「全部大区」 | 显示大区级热力图 |
| 点击导出 Excel | 保持原有下载逻辑 |

---

## 7. 文件变更清单

### 修改

| 文件 | 变更 |
|------|------|
| `frontend/src/views/TwoYearComparison.vue` | 重构页面布局：去侧栏 → 顶部控制栏；实现看板视图 |
| `frontend/src/components/ContractCompletion/TwoYearTable.vue` | 无需改动（仅父级布局变化） |

### 新增

| 文件 | 说明 |
|------|------|
| `frontend/src/components/ContractCompletion/TwoYearDashboard.vue` | 新组件：增长率看板（卡片+热力图+排行） |

---

## 8. 技术要点

- **不新增依赖**：纯 Vue 3 + CSS Grid/Flexbox + 条件样式
- **可选 ECharts**：排行条形图可先用纯 CSS 实现，后续可选升级为 ECharts 动画
- **响应式**：7 列卡片用 `grid-template-columns: repeat(7, 1fr)`，窄屏可折行
- **数据计算**：在组件内用 computed 从 `allRows` 聚合大区级数据
  - 过滤 `type === 'data'` 的行
  - 按 region 分组求和各指标的 prev/curr
  - 计算增长率：`((curr - prev) / prev * 100)` 取整
- **颜色映射**：正值→绿，负值→红，null/undefined→灰

---

## 9. 自检

- [x] 无 TBD/TODO
- [x] 7 个核心指标与 metric_groups 映射一致
- [x] 布局改动不影响表格视图功能
- [x] 大区筛选在看板和表格间保持一致
- [x] 无新依赖引入
- [x] 与 ContractCompletion 页面风格协调
