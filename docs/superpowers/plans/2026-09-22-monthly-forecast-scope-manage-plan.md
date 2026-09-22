# 月预测值 — 模块名单管理（最小版）Implementation Plan

> **For agentic workers:** 逐条实现，改完一项勾一项（`- [ ]` → `- [x]`）。

**Goal:** 在「单月签排发填报」模块里增加一个**名单管理**抽屉，让管理员能**精确增删「账号 ↔ 模块」归属**，替代"只能全量导入名单"的现状。解决三件事：单人补/退模块、一人多模块、清理后台删账号留下的无效归属。

**硬约束（隔离承诺）:** 只动本模块。不改 `cc_*` 任何表与数据、不改 `users.py` / `roles.py` / `modules.py` / 路由文件、不改候选池与汇总导出逻辑。**不新增数据库表、不新增字段、无需数据迁移**（完全复用 `mf_user_scope`）。

## 需求确认（2026-09-22）

**本次做（4 项）**

| # | 功能 | 说明 |
|---|------|------|
| 1 | 名单列表 | 账号 / 姓名 / 模块 / 来源 / 创建时间 / 状态 / 操作；支持筛选搜索 |
| 2 | 新增归属 | 选人 + 选模块，加一条；重复给明确提示 |
| 3 | 移除归属 | 行内移除 + 二次确认（带后果提示） |
| 5 | 清理无效归属 | 一键清除「账号已不存在」的孤儿行，按钮上显示条数 |

**本次不做（已确认砍掉）**

- 不做「一次设定某人全部模块」
- 不做「批量给人加同一模块」
- 不做操作留痕（不写 `operation_log`）
- 不建账号、不改角色、不改密码、不停用账号（这些在后台「用户管理」）
- 不新增「导入名单」的干跑预检（现有全量导入行为保持不变）

**已定口径（实现时不可偏离）**

- 一人多模块**允许**，不校验冲突
- 允许给**已停用**账号加归属（先配好再启用的正常流程），列表用「已停用」标签提示，**不拦截**
- 名单只表达「归属」，不校验该账号的角色权限——角色是后台的事
- 移除归属**不自动**停用账号，只在确认框里提示后果
- 「账号已不存在」（`mf_user_scope.user_id` 在 `user` 表查不到）= 孤儿行，需可识别、可一键清理

## 页面设计

**入口**：`frontend/src/views/MonthlyForecast.vue` 顶部按钮区，在「导入名单」**左侧**加一个「名单管理」按钮。
显示条件 `v-if="context.can_import_scope"`，与现有「导入名单」**完全一致的权限口径**（管理员或持 `user_manage` 权限）。
点击打开右侧 `el-drawer`。

**抽屉内容（自上而下）**

1. 标题栏：`模块名单管理`，右侧「新增」按钮
2. 工具栏：模块筛选（单选可清除）+ 关键字（DT号/姓名）+「只看异常」开关 +「刷新」
3. 表格列：`账号(DT号) | 姓名 | 模块 | 来源 | 创建时间 | 状态 | 操作`
   - 状态：`正常`（绿）/ `账号已停用`（黄）/ `账号不存在`（红）
   - 操作：`移除`（带二次确认）
4. 底部：一行固定提示 + 「清理无效归属（N）」按钮，N=0 时按钮禁用

**固定文案（照抄，不要改写）**

- 移除确认框：`移除后，该账号将变成「可看全部模块汇总」的只读账号，无法再填报本模块。建议同时到「用户管理」停用账号或更换角色。确认移除？`
- 抽屉底部提示：`「导入名单」为全量替换：会覆盖这里手工增删的结果，请以完整名单导入。`
- 清理确认框：`检测到 N 条「账号已不存在」的无效归属，清理后不可恢复。确认清理？`

## 接口设计

全部挂在现有 `mf_bp`（`backend/monthly_forecast/blueprint.py`）上，纯新增函数；统一 `@jwt_required()` + `@permission_required(PERMISSION)` + `_is_management(user)` 校验（与现有名单接口一致，非管理用户一律 403）。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/monthly-forecast/scope` | **已有**，增强：每条增加 `user_status`（`active` / `inactive` / `missing`）。只加字段，不删字段，保持向后兼容 |
| GET | `/api/monthly-forecast/scope/options` | 新增：`{modules: [...], users: [{id, username, real_name, is_active}]}`，供两个下拉使用。**特意不依赖 `/api/users`**，避免权限口径不一致 |
| POST | `/api/monthly-forecast/scope/item` | 新增一条，body `{user_id, module_name}` |
| DELETE | `/api/monthly-forecast/scope/item/<int:item_id>` | 删除一条 |
| POST | `/api/monthly-forecast/scope/cleanup` | 清理全部孤儿行，返回 `{removed: n}` |
| POST | `/api/monthly-forecast/scope` | **已有**（文件全量导入），保持不变 |

**`POST /scope/item` 校验顺序与返回**

1. `user_id` 查不到 → 400 `账号不存在`
2. `module_name` 不在 `all_modules()` → 400 `模块不存在`
3. 命中 `uq_mf_scope` 唯一约束 → 400 `该账号已在「XX」模块`
4. 成功 → 200，返回新增行（含 `username` / `real_name` / `user_status`）

## 影响文件

| 文件 | 改动 |
|------|------|
| `backend/monthly_forecast/blueprint.py` | 新增 4 个接口函数 + 1 处 `api_get_scope` 补字段（纯新增为主） |
| `frontend/src/api/monthly-forecast.js` | 新增 4 个封装函数 |
| `frontend/src/components/MonthlyForecast/ScopeManageDrawer.vue` | **新文件** |
| `frontend/src/views/MonthlyForecast.vue` | +1 按钮、+1 import、+1 组件标签（3 行） |

**零改动**：`mf_*` 表结构、`cc_*` 全表与数据、`users.py`、`roles.py`、`modules.py`、`router/index.js`、其他任何页面。

## 任务

### Task 1: 后端接口（blueprint.py）

- [x] `api_get_scope()`：每条补 `user_status`（按 `user` 表是否存在 + `is_active` 判定），其余字段不变
- [x] 新增 `api_scope_options()`：返回模块清单（`svc.all_modules()`）与人员清单（`user` 表 id/username/real_name/is_active）
- [x] 新增 `api_add_scope_item()`：按上面的校验顺序实现，捕获唯一约束冲突并转成 400 文案
- [x] 新增 `api_delete_scope_item()`：不存在返回 404，成功返回 200
- [x] 新增 `api_cleanup_scope()`：删除 `user_id` 不在 `user` 表的行，返回删除条数
- [x] 4 个新接口全部加 `_is_management` 校验，非管理用户 403

### Task 2: 前端接口封装（api/monthly-forecast.js）

- [x] 新增 `getScopeOptions()`
- [x] 新增 `addScopeItem(payload)`
- [x] 新增 `removeScopeItem(id)`
- [x] 新增 `cleanupScope()`

### Task 3: 抽屉组件（ScopeManageDrawer.vue，新文件）

- [x] `el-drawer` + `v-model` 控制显隐；打开时并行加载名单与 options
- [x] 工具栏：模块筛选、关键字、只看异常、刷新
- [x] 表格：7 列 + 状态标签（正常/已停用/账号不存在）+ 行内「移除」
- [x] 新增：标题栏按钮 + 行内表单（人员下拉可搜索 + 模块下拉），提交成功后刷新列表并提示
- [x] 移除：`ElMessageBox.confirm` 用固定文案，成功后刷新
- [x] 底部：固定提示 + 「清理无效归属（N）」，N 为 0 时禁用
- [x] 加载中/空态处理；接口报错由现有响应拦截器统一提示

### Task 4: 页面入口（MonthlyForecast.vue）

- [x] 顶部按钮区加「名单管理」按钮（`v-if="context.can_import_scope"`）
- [x] import 组件 + 放置组件标签，`v-model` 绑定本地 visible
- [x] 不动「导入名单」按钮与其余任何逻辑

## 验证

- [x] 列表：59 条正常显示，状态标签正确（正常/已停用/账号不存在）
- [x] 新增：给人加一个**新**模块 → 列表出现该行；该账号可见范围变成 2 个模块
- [x] 新增重复 → 400「该账号已在「XX」模块」
- [x] 新增不存在的人员 / 模块 → 400 明确文案
- [x] 移除：删掉某人唯一的模块 → 该账号恢复「只读汇总、可见全部模块」；数据（填报/提交）不受影响
- [x] 清理孤儿：副本上制造孤儿 → 列表标「账号不存在」→ 清理后 removed=1、再点 removed=0
- [x] 权限：非管理用户调用 5 个接口（含 GET）→ 403
- [x] 回归：context / summary / entry 正常，旧 `/scope` POST 路由仍在
- [x] 回归：`user` / `mf_*` / `cc_*` 9 张表行数全部不变，真实库 MD5 不变

## 实施记录（2026-09-22）

- 实际改动文件：`backend/monthly_forecast/blueprint.py`、`frontend/src/api/monthly-forecast.js`、
  `frontend/src/components/MonthlyForecast/ScopeManageDrawer.vue`（新增）、
  `frontend/src/views/MonthlyForecast.vue`
- 验证方式：数据库副本 + Flask test client，**45 项断言全部通过**；真实库 MD5 `f47b846e231616a52ec455d969eb43a5` 未变
- 前端 `npm run build` 通过，新组件已进 `MonthlyForecast-*.js` chunk
- 未做：`delete_user()` 清理孤儿（治本项，仍留给后续）

## 部署

1. 同步 4 个文件到服务器
2. 重启服务（无数据库迁移、无表结构变更）
3. 前端重新构建：`cd frontend && npm run build`
4. 回滚：接口与组件均为新增，删除对应代码即可；数据无副作用

## 后续可选（本次不做，记录备查）

- 「一次设定某人全部模块」「批量加人」「操作留痕」「导入前干跑预检」
- 在 `backend/users.py` 的 `delete_user()` 里顺手清理该账号的 `mf_user_scope` 行（治本，避免孤儿）
