# 单月签排发填报（新模块）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在平台上新增一个**完全独立**的「单月签排发填报」模块：各模块自行填报签单/排产台数金额，发货由台账候选池勾选 + 手工输入梯号补充得出，支持提交留存、按模块隔离可见、两张 Excel 导出。

**硬约束:** 既有项目的代码、数据、用户**零改动**。唯一允许的既有文件改动是 `backend/app.py`（+2 行）与 `frontend/src/router/index.js`（+1 路由）；既有数据表无 ALTER，仅新增 `mf_*` 表、1 行 `role`、1 行 `module`。

**Architecture:** 新增独立包 `backend/monthly_forecast/`，通过 `register(app)` 单点接入；数据落 4 张 `mf_` 前缀新表，由既有 `seed_database()` 的 `db.create_all()` 自动建表（要求模型在 create_all 之前完成 import）。前端新增独立 SPA 页面，同一页面按「有无模块归属」切换**填报模式** / **只读汇总模式**。

**Tech Stack:** Flask + SQLAlchemy + flask-jwt-extended + openpyxl；Vue 3 + Element Plus + axios。**零新增依赖。**

---

## 关键口径（实现时不可偏离）

### 候选池 SQL

```sql
SELECT * FROM cc_ledger_contract
WHERE source = 'ledger'                              -- 天然排除报表a / 报表b
  AND (product_status IS NULL OR product_status <> '已作废')
  AND delivery_date IS NULL                          -- 组A日期为空
  AND schedule_date IS NOT NULL                      -- 排产日期不为空
  AND <归属模块> = :module_name
ORDER BY schedule_date DESC, contract_no, ladder_no  -- 日期近的在前
```

### 归属模块判定（沿用既有口径，不修改既有代码）

1. `product_type` 含「改造」→ `改造`
2. 否则 `country` → `cc_country_mapping.module_name`
3. 否则 `mapped_module`

> 基线数据（2026-09-21）：候选 1,946 行 / 1,946 台 / 22,023.7 万元，覆盖 51 个模块，无模块归属 0 行、无梯号 0 行。

### 可见性与导出

| 账号 | 可见 | 可导出 |
|------|------|--------|
| 有模块归属 | 自己模块，可编辑 | 仅 ① 预计签排发台数金额，且只有本模块 |
| 无模块归属（含管理员） | 全部汇总，只读 | ① + ② 发货明细，全部模块 |

### 权限与角色

- 仅新增 1 个权限标识：`monthly_forecast`
- 角色与模块入口**由需求方在后台自建**；本模块不写 user / role / module 任何一行（参考权限：`monthly_forecast` + `dashboard_schedule`）
- 既有角色追加 `monthly_forecast` 由需求方自行在后台完成，代码不碰

---

## File Structure

| File | Role |
|------|------|
| `backend/monthly_forecast/__init__.py` | **New** — `register(app)`：注册蓝图 + 只建自己的 mf_ 表（不碰角色与模块入口） |
| `backend/monthly_forecast/models.py` | **New** — 4 张 `mf_` 表 |
| `backend/monthly_forecast/services.py` | **New** — 候选池 / 归属判定 / 梯号校验 / 汇总 / 两张导出 |
| `backend/monthly_forecast/handlers.py` | **New** — 名单上传解析 |
| `backend/monthly_forecast/mapping.py` | **New** — 复用「国家-市场-业务员」表，人名 → 正式模块名 归一化 |
| `backend/monthly_forecast/blueprint.py` | **New** — API 路由 |
| `frontend/src/views/MonthlyForecast.vue` | **New** — 填报页 + 汇总视图（按模式切换） |
| `frontend/src/api/monthly-forecast.js` | **New** — 接口封装 |
| `backend/app.py` | Modified — +2 行（import + `register(app)`） |
| `frontend/src/router/index.js` | Modified — +1 路由条目 |

数据流：

```
MonthlyForecast.vue
  ├─ GET  /api/monthly-forecast/months
  ├─ GET  /api/monthly-forecast/entry?month=          → 我的填报值 + 发货明细
  ├─ GET  /api/monthly-forecast/candidates?month=&q=  → 候选池（排产日期倒序）
  ├─ POST /api/monthly-forecast/ladder/validate       → 梯号校验
  ├─ PUT  /api/monthly-forecast/entry                 → 存草稿
  ├─ POST /api/monthly-forecast/entry/submit          → 提交 + 留存快照
  ├─ GET  /api/monthly-forecast/summary?month=        → 只读汇总
  └─ GET  /api/monthly-forecast/export/{forecast,shipping}
```

---

### Task 1: 包骨架 + 数据模型 + 幂等初始化

**Files:**
- Create: `backend/monthly_forecast/__init__.py`, `backend/monthly_forecast/models.py`

- [x] **Step 1: 定义 4 张 `mf_` 模型**

按设计稿 §3.2 落地 `mf_monthly_input`、`mf_ship_selection`、`mf_submission`、`mf_user_scope`，逐表加唯一约束：

```python
__table_args__ = (db.UniqueConstraint('data_month', 'module_name', name='uq_mf_input'),)
__table_args__ = (db.UniqueConstraint('data_month', 'module_name', 'ladder_no', name='uq_mf_ship'),)
__table_args__ = (db.UniqueConstraint('data_month', 'module_name', 'version', name='uq_mf_sub'),)
__table_args__ = (db.UniqueConstraint('user_id', 'module_name', name='uq_mf_scope'),)
```

- [x] **Step 2: 写 `register(app)`**

```python
def register(app):
    from monthly_forecast.blueprint import mf_bp      # import 即注册模型到 db.metadata
    app.register_blueprint(mf_bp)
    with app.app_context():
        _ensure_role()      # 幂等：存在则跳过
        _ensure_module()    # 幂等：存在则跳过
```

要求：`register(app)` 必须在 `create_app()` 里、`seed_database(app)` **之前**调用，模型才会被 `db.create_all()` 建表。

- [x] **Step 3: 启动只读，不做任何写入（2026-09-21 按需求方要求收紧）**

- 需求方明确：**账户、角色一律不动**
- `_create_tables()`：只创建缺失的表（含 4 张 `mf_` 表），不改动既有表结构
- `_report_readiness()`：只读检查角色「单月签排发填报」与模块入口是否存在，缺了**只在启动日志提示**，绝不自动创建
- 实测：把该角色删掉后启动，角色**不会被重建**；`user` / `role` / `module` 三表逐行比对完全不变

### Task 2: 候选池与归属判定

**Files:**
- Create: `backend/monthly_forecast/services.py`

- [x] **Step 1: `load_module_map()`** — 读 `cc_country_mapping` 建 `{country: module_name}`（只读）
- [x] **Step 2: `resolve_module(row)`** — 按三档优先级判定归属模块（改造 → country → mapped_module）
- [x] **Step 3: `list_candidates(module_name, keyword=None)`** — 按「关键口径」的 SQL 查询，`ORDER BY schedule_date DESC, contract_no, ladder_no`；返回合同号、梯号、项目名称、台数、金额（万元）、排产日期；`keyword` 用于前端搜索
- [x] **Step 4: 自检** — 用 2026-09-21 基线核对：全量候选应为 1,946 行 / 22,023.7 万元 / 51 个模块；报表a 与已作废必须为 0 行

### Task 3: 梯号校验

- [x] **Step 1: `validate_ladder(module_name, ladder_no)`** 返回四种结果之一：

| 场景 | 返回 |
|------|------|
| 台账无此梯号 | `{ok: False, code: 'NOT_FOUND', msg: '台账中无此梯号'}` |
| 存在但归属其它模块 | `{ok: False, code: 'OTHER_MODULE', msg: '不属于本模块'}` |
| 属于本模块 | `{ok: True, row: {...}}` |
| 已在本次填报中 | `{ok: False, code: 'DUPLICATE', msg: '该梯号已在列表中'}` |

- [x] **Step 2: 自检** — 「不属于本模块」必须**拒绝写入**，不得静默接受

### Task 4: 填报读写 + 提交留存

- [x] **Step 1: `get_entry(month, module_name)`** — 返回签单/排产 4 值、状态、发货明细列表、6 项合计
- [x] **Step 2: `save_draft(month, module_name, payload, user)`** — upsert `mf_monthly_input`；按 payload 全量替换该月该模块的 `mf_ship_selection`
- [x] **Step 3: `submit(month, module_name, user)`** — 先落地当前填报，再写 `mf_submission`，`version = max+1`，`payload` 存签排产 4 值 + 发货明细数组，冗余存 6 项合计；`status='submitted'`
- [x] **Step 4: `list_submissions(month, module_name)`** — 历史版本可查
- [x] **Step 5: 自检** — 提交后仍可修改并再次提交，版本号递增，旧版本不被覆盖

### Task 5: 汇总与两张导出

- [x] **Step 1: `get_summary(month)`** — 全部模块 6 列 + 合计行；发货列取自 `mf_ship_selection` 合计
- [x] **Step 2: `export_forecast(month, modules)`** — Excel ①：模块 × 6 列（签单台数/金额、排产台数/金额、发货台数/金额）+ 合计行；模块人员仅传自己的模块
- [x] **Step 3: `export_shipping(month)`** — Excel ②：合同号、梯号、项目名称、台数、金额（万元）、来源（候选勾选 / 手工输入）、填报人
- [x] **Step 4: 自检** — 用 openpyxl 打开产物，核对行列与合计

### Task 6: 蓝图与路由

**Files:**
- Create: `backend/monthly_forecast/blueprint.py`
- Modify: `backend/app.py` (+2 行)

- [x] **Step 1: 实现 11 个接口**（见 File Structure 数据流；全部 `@jwt_required()`）
- [x] **Step 2: 权限与范围校验**

统一取当前用户的模块归属列表：

```python
scope = mf_user_scope.query.filter_by(user_id=user.id).all()
module_names = [s.module_name for s in scope]
```

- 有 scope → `entry` / `candidates` / `save_draft` / `submit` 只允许 scope 内的模块；`export_forecast` 只导出 scope 内模块
- 无 scope → 只允许 `summary` 与 `export/*`；**任何写接口一律 403**
- `export_shipping` 在**有 scope 时直接 403**（后端硬挡，不依赖前端）
- 请求里的 `module` 参数必须落在 scope 内，否则 403（防越权）

- [x] **Step 3: 在 `app.py` 接入**

```python
from monthly_forecast import register as register_monthly_forecast
# create_app() 内、seed_database(app) 之前：
register_monthly_forecast(app)
```

- [x] **Step 4: 自检** — 启动服务，确认 4 张 `mf_` 表已创建；`user` / `role` / `module` 逐行比对完全不变

### Task 7: 名单导入

**Files:**
- Create: `backend/monthly_forecast/handlers.py`
- 复用: `POST /api/monthly-forecast/scope`

- [x] **Step 1: 解析名单表单** — 读 Excel/CSV，识别 **DT号（=工号）** 与 **人名**；「模块」列可选（有则优先）
- [x] **Step 2: 只读匹配 `user` 表** — 先按 DT号 `username` 再按 人名 `real_name` 匹配，**绝不写回 `user`**
- [x] **Step 3: 模块自动解析** — 复用「国家-市场-业务员」表（`contract_completion/contract_mapping/` 最新一份，只读），
      人名 → 正式模块名；命中 1 个写入、命中 0 个或多个人工处理（见设计规格 §7）
- [x] **Step 4: 写入 `mf_user_scope`** — 先清空后导入（全量替换），需人工处理的明细写入 `uploads/monthly_forecast/scope_report.txt`
- [x] **Step 5: 自检** — 导入后 `user` 表行数与内容不变；有模块归属者只见自己模块

### Task 8: 前端页面与路由

**Files:**
- Create: `frontend/src/api/monthly-forecast.js`, `frontend/src/views/MonthlyForecast.vue`
- Modify: `frontend/src/router/index.js` (+1 路由，放在用户端 layout 下)

- [x] **Step 1: API 封装** — 与后端 11 个接口一一对应
- [x] **Step 2: 页面骨架** — 月份选择（默认下个月）+ 保存草稿 + 提交 + 导出按钮
- [x] **Step 3: 填报区** — 签单/排产各 2 个输入框（台数、金额）
- [x] **Step 4: 发货候选表** — 勾选框（默认不勾）、合同号、梯号、项目、台数、金额、排产日期；排产日期倒序；前端搜索
- [x] **Step 5: 手工添加梯号** — 输入框 + 即时校验反馈（四种结果对应四种提示）
- [x] **Step 6: 实时小计** — 签排发 6 个数字
- [x] **Step 7: 只读汇总模式** — 无 scope 时自动切换为全部模块汇总，隐藏所有写入控件
- [x] **Step 8: 模式与按钮显隐** — 模块人员只显示 ① 导出；无归属显示 ① + ②

### Task 9: 验收

- [x] 候选池与基线一致（1,946 行 / 22,023.7 万元 / 51 模块）
- [x] 台账中不存在的梯号、属于其它模块的梯号、重复梯号 → 三种提示均正确且**不落库**
- [x] 模块人员 A 无法通过构造参数读写模块 B 的数据（越权测试）
- [x] 模块人员调 `export/shipping` 返回 403
- [x] 无归属账号进入即为只读汇总，无任何写入控件
- [x] 提交后 `mf_submission` 生成 version=1；再次修改提交生成 version=2，version=1 内容不变
- [x] 两张 Excel 导出内容与页面一致
- [x] `user` 表 0 改动；`cc_*` 表 0 改动；既有页面（两年对比、年度完成比、工期、签单排产发货情况）功能与数据与改动前一致

---

## 验收结果（2026-09-21 实测）

**测试方式**：把 `backend/instance/system.db` 复制到临时库后运行，**真实库全程零改动**
（复测真实库：仍为 14 张表、0 张 `mf_` 表、17 个用户、3 个角色、`cc_ledger_contract` 68,597 行）。

**自动化端到端**：71 项断言全部通过（进程退出码 0）。

| 分组 | 覆盖内容 | 结果 |
|------|----------|------|
| 隔离性 | 仅新增 4 张 `mf_` 表；无表被删；既有 14 张表 schema 逐字一致（**0 ALTER**） | 通过 |
| 启动写入面 | 只建自己的 4 张 `mf_` 表；`user` / `role` / `module` 逐行比对完全不变（删掉角色也不会被重建） | 通过 |
| 候选池口径 | 1,946 行 / 51 个模块 / 22,023.65 万元；埃及-1 以 492 行居首；按排产日期倒序 | 通过 |
| 越权 | 模块人员写其它模块 → 403；`export/shipping` → 403；名单查看/导入 → 403 | 通过 |
| 梯号校验 | `EMPTY` / `NOT_FOUND` / `OTHER_MODULE` / `DUPLICATE` / `OK` 五种返回全部正确 | 通过 |
| 非法梯号不落库 | 保存时混入「其它模块」与「台账不存在」梯号 → 二者进 `rejected`，不写入 | 通过 |
| 数值可信 | 发货台数/金额一律由服务端按台账重新快照，前端传的数值不被采信 | 通过 |
| 提交留存 | 连续提交两次 → version 1、2；v1 内容保持不变 | 通过 |
| 导出 | 模块人员仅 ①「预计签排发台数金额」且只有本模块；角色外可导 ① + ②（全量） | 通过 |
| 名单导入 | 支持一人多模块；先按工号再按姓名匹配；未匹配与未知模块写入报告；**`user` 表零改动** | 通过 |
| 权限门 | 无 `monthly_forecast` 权限 → 相关接口全 403；未登录 → 401 | 通过 |
| 回归 | `user` +4（仅测试账号）；`role` +1、`module` +1（本模块自建）；其余既有表行数与 schema 全等 | 通过 |

**前端**：`npm run build` 成功（退出码 0），产出 `dist/assets/MonthlyForecast-*.js`。

**仍需人工完成（代码刻意不碰）**

1. 在后台给「管理员」等既有角色的权限列表**追加** `monthly_forecast`，否则看不到本模块入口（现有「管理员」角色权限中没有该项，已实测确认）。
2. 通过「导入名单」上传「工号/姓名 + 模块」表单，把各模块业务员与本模块绑定；名单为空时所有账号都是只读汇总。

> 注意：后端每次请求都从库里读角色权限，**接口层面追加权限即时生效**；
> 但前端侧边栏菜单读的是登录时缓存的 `userInfo.role.permissions`（`frontend/src/stores/auth.js`），
> 所以**要让菜单出现需重新登录一次**。

---

## 名单导入（DT号 + 人名）实测 — 2026-09-21

用一份构造名单实测，`user` 表 17 行不变，`mf_user_scope` 写入 5 条：

| 名单内容 | 结果 |
|---|---|
| DT190190 齐文童 | 写入 俄罗斯（东部） 通过 |
| DT190427 高新尧 | 写入 印度私营 通过 |
| DT106067 吴迪 | 写入 墨西哥-1 通过 |
| DT161015 陈远一 | 写入 沙特工厂 通过 |
| DT205231 刘思含 + 模块=埃及-1 | 写入 埃及-1（名单自带模块优先）通过 |
| DT201017 严晨（源表对应多模块） | 整条略过，进报告 通过 |
| DT106663 刘瑞升 | 源表查不到模块，进报告 通过 |
| DT190195 周晟航 | 源表写作「周聖航」字形不同，进报告 通过 |
| DT999999 不存在的人 | 平台无此账号，略过 通过 |
| DT205182 潘闯 + 模块=不存在的模块 | 模块名无法识别，进报告 通过 |
| 只给人名、不填 DT号 | 按 `real_name` 兜底匹配 通过 |
| 同一人重复出现多行 | 去重，不重复写入 通过 |

覆盖度（源表 `国家-市场-业务员9.1.xlsx`）：可解析人名 163 个，其中 130 人唯一模块可自动写入，
33 人对应多模块按约定略过待人工添加。
