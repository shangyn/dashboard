# 单月签排发填报 — 发货「无梯号预估」手工输入 Implementation Plan

> **For agentic workers:** 逐条实现，改完一项勾一项（`- [ ]` → `- [x]`）。

**Goal:** 在「发货预计」卡片上增加两个手工输入框（台数 / 金额万元），用于记录「还没签合同、也没排产、台账里查不到梯号」但确定要发的量。发货合计 = 梯号明细合计 + 手工输入。

**硬约束:** 只动本模块。不改任何 `cc_*` 表、不改其他蓝图/接口/页面；既有数据表结构与数据零改动（仅给 `mf_monthly_input` 增加 2 个可空列）。零新增依赖。

## 需求确认（2026-09-22）

| # | 问题 | 结论 |
|---|------|------|
| 1 | 与梯号合计的关系 | **相加**：发货合计 = 明细合计 + 手工输入 |
| 2 | 对「后续梯号出现在候选池」是否加重复提示 | **不加** |
| 3 | 手工量是否要明细行 / 备注 | **不要**，只做模块级一个数（台数 + 金额） |
| 4 | 填写规则 | 与签单/排产一致：不填即 0，前端 `:min="0"`，两位小数 |

**背景（为什么现在填不进去）**

- 候选池要求 `schedule_date` 不为空、`delivery_date` 为空（`backend/monthly_forecast/services.py:121-133`），未排产的梯号不出现
- 手工录梯号走 `validate_ladder()`，台账里查不到就返回 `NOT_FOUND`（`services.py:207`）
- 发货台数/金额现在只能由明细合计得出，且台数金额由服务端从台账快照、不信任前端传值（`services.py:273`、`services.py:310`）

**Architecture:** 在既有 `mf_monthly_input` 上加 2 列，沿用「与签单/排产同表同层」的做法；发货台数/金额的合成口径收敛到一个 helper；前端只在填报模式的发货卡片加输入框，只读汇总模式不动（它走 `get_summary`，自动包含）。

**Tech Stack:** Flask + SQLAlchemy + openpyxl；Vue 3 + Element Plus。零新增依赖。

---

## 口径（实现时不可偏离）

```
模块发货台数 = Σ mf_ship_selection.unit_count          + mf_monthly_input.ship_manual_units
模块发货金额 = Σ mf_ship_selection.amount_rmb / 10000  + mf_monthly_input.ship_manual_amount
```

- 明细侧仍由服务端从台账快照，前端不可传值（现状不变）
- 手工侧是纯手填，服务端只做 `_to_float()`（空 → 0.0，四舍五入 2 位），不做交叉校验
- 候选池规则、梯号校验规则 **不动**

## 影响文件

**改动（4 个既有文件，均为纯新增行）**

| 文件 | 改动 |
|------|------|
| `backend/monthly_forecast/models.py` | `MonthlyInput` +2 列，`to_dict()` +2 个键 |
| `backend/monthly_forecast/services.py` | 读写 / 汇总 / 快照，共 5 处 |
| `backend/seed.py` | +6 行幂等 `ALTER TABLE`（沿用既有写法） |
| `frontend/src/views/MonthlyForecast.vue` | 发货卡片 +2 输入框、合计口径、payload |

**零改动**：`cc_*` 全部表、`blueprint.py`（无新接口）、`frontend/src/api/monthly-forecast.js`（复用 `entry` 的 GET/PUT）、其他模块与页面。

## 任务

### Task 1: 数据模型与迁移

- [x] `models.py`：`MonthlyInput` 增加 `ship_manual_units`、`ship_manual_amount`（`db.Float, default=0.0`），`to_dict()` 增加同名两个键
- [x] `seed.py`：在既有 `with db.engine.connect() as conn:` 块内，用 `inspector.get_columns('mf_monthly_input')` 判断后加两列（`FLOAT DEFAULT 0`）
  - 顺序天然满足：`register_monthly_forecast(app)` 在 `backend/app.py:78`，`seed_database(app)` 在 `backend/app.py:136`，表由同一次 `db.create_all()` 建好

### Task 2: 业务逻辑（services.py）

- [x] 新增 helper `_ship_totals(data_month, module_name)`：明细合计 + 手工值，返回 `(round(units, 2), round(amount, 2))`
- [x] `save_draft()`：写入 `record.ship_manual_units / ship_manual_amount = _to_float(payload.get(...))`
- [x] `get_entry()`：返回体补 2 个字段（含无记录时的默认 0）；`ship_units / ship_amount` 改用 `_ship_totals()`
- [x] `_module_row()`：发货两列叠加该模块记录上的手工值（汇总、合计行、导出①随之正确）
- [x] `submit()`：`mf_submission.payload` 增加 2 个字段（留存快照可追溯）

### Task 3: 前端（MonthlyForecast.vue）

- [x] `form` 增加 `ship_manual_units` / `ship_manual_amount`；`applyEntry()` 回填；`buildPayload()` 带出
- [x] 发货卡片加两个 `el-input-number`（`:min="0"`、`:controls="false"`，与签单/排产同尺寸），文案「无梯号发货预估」
- [x] 合计展示改为拆分可见：`梯号 X 台 + 手工 Y 台 = Z 台`（金额同理）
- [x] 只读汇总模式、候选池表格、手工梯号输入框 **均不动**

## 验证

- [x] 两个新框都不填：保存草稿 → `get_entry` 返回 0，汇总与改动前完全一致（回归基线）
- [x] 只填台数不填金额（反之亦然）：合计正确、无报错
- [x] 勾 1 个梯号 + 手工 3 台 / 50 万：`ship_units = 台账台数 + 3`、`ship_amount = 台账万元 + 50`
- [x] 提交后 `mf_submission` 最新版本 payload 含两字段，版本号自增正常
- [x] 只读汇总模式（无 scope 账号）该模块发货列 = 明细 + 手工
- [x] 导出①「预计签排发台数金额」发货列与页面一致
- [x] 影响面回归：`cc_ledger_contract` 行数、其他模块 `mf_monthly_input` 数据、其他页面接口返回均不变

## 已知影响

- **导出②「预计发货合同梯号明细」不含手工值**（它是梯号级明细表），因此它的合计可能小于导出①的发货列。按需求确认第 3 条这是预期结果；如后续要加一行「无梯号预估」需再确认。
- 手工值不做交叉校验：即使该模块本月已有候选梯号，也允许手工填写（需求确认第 2 条）。

## 部署

1. 同步 4 个文件到服务器
2. 重启服务（`gunicorn -c gunicorn.conf.py wsgi:app` 或 systemctl / supervisor）—— 启动时 `seed_database()` 自动执行 `ALTER TABLE`
3. 前端需重新构建：`cd frontend && npm run build`
4. 回滚：新列为可空且默认 0，旧代码不受影响