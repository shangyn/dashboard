# 单月签排发填报（新模块）— 设计规格

**日期:** 2026-09-21
**状态:** 已确认，待实施（v5）
**硬约束:** 全新模块。既有项目的代码、数据、用户一律不改动。

---

## 0. 硬约束与边界

- 本需求是一个**全新的独立模块**，不得改动既有项目的任何代码与行为。
- 实现方式：新增独立包 `backend/monthly_forecast/`、独立数据表（`mf_` 前缀）、独立前端页面与路由。
- **完全不产出、不依赖** `budget_forecast_*.json`，与现有「签单排产发货情况」看板互不相干。
- 台账解析、两年对比、年度完成比、工期看板、现有看板：**全部保持原样**。
- **账户、角色一律不动**（需求方 2026-09-21 明确追加的硬约束）：
  本模块**不写** `user`、**不写** `role`、**不写** `module`，一行都不写。
  启动时只做**只读**检查，角色或模块入口缺失只在日志里提示，绝不自动创建。
- 名单导入只写本模块自己的 `mf_user_scope` 表。
- 唯一需要「新增行」的既有代码文件见 §6，共 3 处；既有数据表 **0 结构变更**。不新增 pip / npm 依赖。

## 1. 需求确认结论

| # | 问题 | 结论 |
|---|------|------|
| 1 | 「模块」口径 | 映射表 `cc_country_mapping.module_name` 的 **65 个模块** |
| 2 | 候选池是否限定月份 | **不限定**；按日期排序，**日期近的在前** |
| 3 | 报表a（商贸配件）是否进候选 | **不出现** |
| 4 | 已作废合同 | **排除** |
| 5 | 发货金额口径 | 台账「合同额（人民币）」单行值，元 → 万元 |
| 6 | 填报月份范围 | 暂只填一个月（基本是下个月） |
| 7 | 手输梯号属于其它模块 | **报「不属于本模块」**，不允许添加 |
| 8 | 批量全选辅助 | **不加** |
| 9 | 提交与锁定 | **无截止日期**；提交后需**留存**（快照可追溯） |
| 10 | 名单形式 | **之后上传表单**导入；**一人可多模块** |
| 11 | 无匹配用户的可见范围 | 可看**全部汇总，只读**；**包含管理员** |
| 12 | 角色 | **由需求方在后台自建**；本模块不写 user / role / module 任何一行 |
| 13 | 导出格式 | **无既定格式**，自行设计 |
| 14 | 与现有看板的关系 | **完全独立**，不产出 JSON（方案 B） |
| 15 | 导出范围 | 模块人员：**只能导出自己模块的「预计签排发台数金额」**；角色外账号：可导出全部模块两张表 |
| 16 | 名单写入范围 | 只写 `mf_user_scope`，**绝不写 `user` 表** |
| 17 | 权限标识 | 仅 1 个：`monthly_forecast`（取消独立的导出标识） |
| 18 | 工期权限 | **只给查看** `dashboard_schedule`，不给上传 |

## 2. 现状核查（读 `backend/instance/system.db`，2026-09-21）

### 2.1 候选池实测（按 §3.1 最终口径）

| 项 | 数值 |
|----|------|
| 候选行数 | **1,946 行**（1,946 台 / 22,023.7 万元） |
| 覆盖模块数 | **51 个** |
| 无模块归属 / 无梯号 | 0 行 / 0 行 |
| 排产日期跨度 | 2013-04 ~ 2026-09（长尾积压，印证「不限定月份 + 近的在前」） |
| Top 模块 | 埃及-1 492、改造 178、俄罗斯（中部）111、俄罗斯（西部）105、越南-1（工厂）104、沙特-1 71、墨西哥-1 70、哥伦比亚 68、伊朗+阿曼 64、印度私营 50 |

口径说明：「组A日期」在 `handlers.py:121` 映射到 `delivery_date`（回退列名「实际发货日期」「实际发运日期」）。

### 2.2 可复用的既有资产（只读，不修改）

- 台账表 `cc_ledger_contract`（68,597 行）、映射表 `cc_country_mapping`（65 模块 / 9 大区）
- 平台通用能力：`user` / `role` / `module` / `upload_config` / `operation_log` 表与对应蓝图
- 前端：Vue 3 + Element Plus + Pinia + axios 封装（`frontend/src/api/request.js`）

## 3. 设计

### 3.1 候选池规则（最终）

```
候选(模块) =
    cc_ledger_contract
    where source = 'ledger'                 -- 天然排除报表a / 报表b
      and (product_status is null or product_status <> '已作废')
      and delivery_date is null             -- 组A日期为空
      and schedule_date is not null         -- 排产日期不为空
      and 归属模块 == 当前模块
    order by schedule_date desc, contract_no, ladder_no
```

归属模块判定（沿用现有项目口径，只读不改）：

1. `product_type` 含「改造」→ `改造`
2. 否则 `country` → `cc_country_mapping.module_name`
3. 否则 `mapped_module`

### 3.2 数据模型（4 张新表，`mf_` 前缀）

**`mf_monthly_input` — 模块月度填报（签单 + 排产）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `data_month` | String(7) | `YYYY-MM` |
| `module_name` | String(100) | 模块名 |
| `sign_units` / `sign_amount` | Float | 签单台数 / 金额（万元），手填 |
| `prod_units` / `prod_amount` | Float | 排产台数 / 金额（万元），手填 |
| `status` | String(20) | `draft` / `submitted` |
| `submitted_at` | DateTime | 最近一次提交时间 |
| `updated_by` / `updated_by_name` / `updated_at` | | 填报留痕 |

唯一键：`(data_month, module_name)`

**`mf_ship_selection` — 发货勾选明细**

| 字段 | 类型 | 说明 |
|------|------|------|
| `data_month` / `module_name` | | 归属 |
| `contract_no` / `ladder_no` | String | 合同号 / 梯号 |
| `unit_count` / `amount_rmb` | Float | 快照值（勾选时台账值） |
| `is_manual` | Boolean | 0 = 候选勾选，1 = 手工输入梯号 |
| `created_by` / `created_by_name` / `created_at` | | 操作留痕 |

唯一键：`(data_month, module_name, ladder_no)`

发货台数/金额 = 该月该模块所有勾选记录的 `unit_count` / `amount_rmb` 合计。

**`mf_submission` — 提交留存快照**

| 字段 | 说明 |
|------|------|
| `data_month` / `module_name` / `version` | 版本号自增 |
| `payload` | JSON：签排产 4 值 + 发货明细数组 |
| `sign_units` … `ship_amount`（合计冗余列） | 便于直接查询与导出 |
| `submitted_by` / `submitted_by_name` / `submitted_at` | |

唯一键：`(data_month, module_name, version)`

**`mf_user_scope` — 用户 → 模块 名单**

| 字段 | 说明 |
|------|------|
| `user_id` | 匹配到的 `user.id`（可为空 = 未匹配到账号） |
| `match_key` | 名单原文（工号或姓名） |
| `module_name` | 模块名 |
| `created_at` | 导入时间 |

唯一键：`(user_id, module_name)`。导入时**只读** `user` 表做匹配，不写回。

### 3.3 权限、角色与可见范围

**权限标识**：仅新增 **1 个** —— `monthly_forecast`（进入模块）。

**角色由需求方在后台自行创建**「单月签排发填报」（本模块只读检查，缺了只在启动日志提示）

- `permissions = [monthly_forecast, dashboard_schedule]`
- `is_admin = false`

**可见性与导出判定**（全部由「有没有模块归属」推导，无需第二个权限标识）

| 账号 | 可见范围 | 可导出 |
|------|----------|--------|
| 有模块归属（名单命中，即持新角色的模块人员） | 自己的模块，**可编辑** | **仅**「预计签排发台数金额」，且只有本模块 |
| 无模块归属（角色外账号，含管理员、领导） | 全部模块汇总，**只读** | 「预计签排发台数金额」+「预计能发货的合同号梯号明细」，**全部模块** |

**导出控制**：前端按钮按上述规则显隐 + **后端接口二次校验**（仅隐藏按钮不安全：模块人员不能通过构造参数拿到明细表或其它模块数据）。

### 3.4 手工添加梯号

输入梯号 → 按 `ladder_no` 精确匹配 `cc_ledger_contract`：

| 结果 | 反馈 |
|------|------|
| 台账中不存在 | 「台账中无此梯号」 |
| 存在但归属其它模块 | 「不属于本模块」（**不允许添加**） |
| 属于本模块 | 追加，`is_manual=1` |
| 已存在（已勾选/已添加） | 「该梯号已在列表中」 |

### 3.5 提交与留存

- `draft`：保存即覆盖自身，可反复修改。
- `submitted`：写入 `mf_submission` 快照，版本号自增。
- 无截止日期 → 提交后**允许修改并重新提交**，每次生成新版本，历史可查、可导出。

### 3.6 页面（Vue SPA，独立路由）

1. 顶部：月份选择（默认下个月）+ 保存草稿 + 提交 + 导出（按权限显隐）
2. 签单 / 排产：4 个输入框
3. 发货候选表：勾选框（默认不勾）、合同号、梯号、项目名称、台数、金额、排产日期；按排产日期倒序；支持搜索
4. 手工添加梯号：输入框 + 即时校验提示
5. 实时小计：签排发 6 个数字
6. 只读汇总视图：无模块归属用户 / 管理员可见全部模块

### 3.7 导出（两张 Excel，自行设计格式）

| # | 名称 | 内容 | 模块人员 | 角色外账号 |
|---|------|------|----------|------------|
| ① | 预计签排发台数金额 | 模块 × 6 列（签单台数/金额、排产台数/金额、发货台数/金额） | 仅本模块一行 | 全部模块 + 合计行 |
| ② | 预计能发货的合同号梯号明细 | 合同号、梯号、项目名称、台数、金额（万元）、来源（候选勾选 / 手工输入）、填报人 | **不可导出** | 全部模块 |

### 3.8 与现有看板的关系（已定）

**完全独立**。本模块不产出、不读取 `budget_forecast_*.json`，现有看板链路（`import_budget.py` / `generate_report_v3.py` / `generate_dashboard.py`）一行不动。

## 4. 确认结论（已闭环）

| # | 事项 | 结论 |
|---|------|------|
| 1 | `monthly_forecast_export` | **取消**，只保留 `monthly_forecast`；导出范围按「有无模块归属」推导 |
| 2 | 现有角色追加 `monthly_forecast` | **由需求方自行在后台完成**，本模块不触碰任何既有角色行 |
| 3 | 谁需要看全部汇总 | **由需求方自行决定并授权** |

**默认约定（已采纳）**

- 候选排序按**排产日期倒序**（「日期近的在前」）。
- 名单按**工号或姓名**匹配到 `user` 表（只读匹配，不写回）。

## 5. 实施计划

> 分任务实施步骤（含 checkbox 跟踪与验收清单）见 `docs/superpowers/plans/2026-09-21-monthly-sign-schedule-ship-fill-plan.md`。

| 阶段 | 内容 | 交付 |
|------|------|------|
| P1 | 新包骨架 + 4 张 mf_ 表（只建自己的表，不碰角色与模块入口） | 表就绪 |
| P2 | 后端 API（见下） | 接口可用 |
| P3 | 前端填报页 | 可填报 |
| P4 | 名单导入 + 可见性隔离 + 导出权限校验 | 数据隔离 |
| P5 | 导出 ×2 + 提交留存 | 功能完整 |
| P6 | 验收（口径核对、权限穿透、导出核对） | 上线 |

**API 清单**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/monthly-forecast/months` | 可选月份 |
| GET | `/api/monthly-forecast/entry` | 填报值 + 发货明细 |
| PUT | `/api/monthly-forecast/entry` | 保存草稿 |
| POST | `/api/monthly-forecast/entry/submit` | 提交并留存快照 |
| GET | `/api/monthly-forecast/candidates` | 候选池（按模块 + 搜索） |
| POST | `/api/monthly-forecast/ladder/validate` | 梯号校验 |
| GET | `/api/monthly-forecast/summary` | 汇总（只读；范围按归属决定） |
| GET | `/api/monthly-forecast/export/forecast` | Excel ①（模块人员限本模块；角色外全量） |
| GET | `/api/monthly-forecast/export/shipping` | Excel ②（**仅角色外**，模块人员 403） |
| GET / POST | `/api/monthly-forecast/scope` | 名单查看 / 导入 |
| GET | `/api/monthly-forecast/submissions` | 历史提交版本 |

## 6. 影响文件与数据

**全新文件（不碰既有代码）**

```
backend/monthly_forecast/__init__.py     注册入口 register(app) + 只建自己的 mf_ 表
backend/monthly_forecast/models.py       4 张 mf_ 表
backend/monthly_forecast/handlers.py     名单导入解析
backend/monthly_forecast/services.py     候选池 / 校验 / 汇总 / 导出
backend/monthly_forecast/blueprint.py    API 路由
frontend/src/views/MonthlyForecast.vue   填报页 + 汇总视图
frontend/src/api/monthly-forecast.js     接口封装
docs/superpowers/specs/2026-09-21-*.md   本文档
```

**既有代码文件（仅 2 处，纯新增行）**

| 文件 | 改动 | 原因 |
|------|------|------|
| `backend/app.py` | +2 行（import + 调用 `register(app)`） | 注册蓝图；须在 `seed_database()` 的 `db.create_all()` 之前完成模型 import，新表才会被创建 |
| `frontend/src/router/index.js` | +1 个路由条目 | 否则新页面无法访问 |

**既有数据表**

| 表 | 改动 |
|----|------|
| 新增 `mf_*` × 4 | 由既有 `db.create_all()` 自动创建 |
| `role` | **0 改动**（角色由需求方在后台自建，本模块只读检查） |
| `module` | **0 改动**（模块入口由需求方在后台自行添加） |
| `user` | **0 改动** |
| `cc_*` 全部 | **0 改动**（只读查询） |

> 除上述外，既有项目文件与数据 **零改动**；既有数据表 **无 ALTER 变更**。

---

## 7. 名单导入（2026-09-21 修订：DT号 + 人名）

**背景**：原方案要求名单自带「模块」列。实际名单只给 **DT号 + 人名**，模块需自动推导。

**DT号 = 平台工号**：平台账号除 `admin` 外均为 `DT######` 格式（`DT190190`、`DT106663`…），
即 `user.username`。因此账号匹配优先用 DT号，比人名可靠。

### 7.1 模块从哪来（复用，只读）

来源：`backend/uploads/contract_completion/contract_mapping/国家-市场-业务员*.xlsx`（取最新一份），
由既有「合同完成情况」模块上传维护。**本模块不写该文件，也不改既有代码。**

> 为什么不直接用 `cc_country_mapping`：该表的 `salesperson`、`module_manager` 两列
> **当前 238 行全为空**（现有上传只落了 国家/模块/大区），人名被丢掉了。
> 所以人名→模块必须由本模块自己解析该 xlsx。

解析范围：`指标`、`业务员-市场`、`任命令模块-模主`、`模主+助理对应模块` 四张表里
所有带人名的列（模块经理 / 业务助理 / 模主 / 姓名，以及若干无表头的助理列）。
`Sheet3` 无人员信息，跳过。

### 7.2 模块名归一化（必做）

源表里同一个模块有多种写法，必须折算到系统正式名，否则归属判定对不上（台账口径用正式名）：

| 源表写法 | 系统正式名 | 差异 |
|---|---|---|
| 越南－1（工厂） | 越南-1（工厂） | 全角破折号 |
| 朝鲜／韩国 | 朝鲜-韩国 | 全角斜杠 |
| 商贸-1 | 商贸1 | 多余破折号 |
| 埃及一1 | 埃及-1 | 「一」被误写成破折号 |
| 英国／意大利 | 英国意大利 | 斜杠有无 |
| 伊朗／阿曼 | 伊朗+阿曼 | 分隔符不同 |

算法：一个原始名生成若干等价写法，**只有当所有能对上的写法都指向同一个正式模块时**才算解析成功。
**宁可漏，不可错** —— 对不上或指向多个一律视为未解析。

### 7.3 匹配规则

1. **账号**：DT号/工号 → `user.username`；失败再用人名 → `user.real_name`
2. **模块**：名单自带「模块」列优先；否则用人名去业务员表解析
3. 命中 **1 个** → 写入 `mf_user_scope`
4. 命中 **0 个** → 不写入，进报告等人工补
5. 命中 **多个** → **整条略过**，进报告等人工加（需求方已确认）
6. 平台查不到账号（离职 / 未入职）→ **整条略过，不做处理**

### 7.4 实测覆盖（2026-09-21）

| 项 | 数值 |
|---|---|
| 源表出现的模块写法 | 117 个（其中 102 个可归一化到系统正式名） |
| 可解析出的人名 | **163 个** |
| 其中唯一模块（可自动写入） | **130 人** |
| 其中对应多个模块（按约定略过） | **33 人** |

### 7.5 报告

`backend/uploads/monthly_forecast/scope_report.txt`，分节列出：
平台无此账号 / 查不到模块 / 对应多个模块已略过 / 模块名无法识别，
并附「源表里对不上系统模块的写法」清单（当前 15 个），便于从源头修表。
