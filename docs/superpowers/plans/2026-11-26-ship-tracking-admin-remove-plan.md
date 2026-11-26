# 发货梯号明细 - 管理员移除计划（2026-11-26）

## 目标

- 在“发货梯号明细 → 全量明细”增加管理员专用的“移除计划”操作，支持单选和批量。
- 管理员可移除任意已存在于梯号明细中的梯号，不限制状态：未提交、已提交、已订舱、已发货、已逾期等均可选择。
- “移除”采用软移除：不再出现在默认明细、业务整体发货明细、统计和导出中，但保留实际发货、订舱、承诺、计划快照和审计记录。
- 同步提供“恢复计划”，避免误操作后只能改库。
- 不向业务开放删除权限；原“撤回”权限语义不变。

## 权限

- 仅 `is_admin` 或拥有 `ship_tracking_admin` 权限的账号可移除、恢复。
- 复用现有管理员选择列：`TrackingTable` 的 `selectable` 已经按 `context.can_admin` 控制，不需要新增权限项。
- 业务角色即使拥有 `ship_tracking_weekly_withdraw`，也只能撤回自己的已提交周计划，不能调用管理员移除接口。

## 数据口径

### 移除后的显示

- 全量明细默认不显示管理员已移除的记录。
- 勾选“显示已移除计划”后可查看，状态显示为“管理员已移除”，并展示移除人、移除时间和原因。
- 业务填报页的候选池和“整体发货明细”都不显示管理员已移除记录，包括原本已发货的记录。
- 汇总卡片、总数、台数、状态计数、订舱计数和 Excel 导出默认排除管理员已移除记录。

### 保留的数据

- 不物理删除 `st_tracking_item`，避免破坏历史与审计。
- 保留 `actual_ship_date`、`DailyShipment`、订舱记录、承诺字段、预计日期、业务备注和计划快照。
- 移除仅设置管理员移除状态，并将当前计划标记为已移除；恢复后按移除前的计划状态恢复。

## 数据模型

在 `st_tracking_item` 增加：

- `admin_removed`：布尔值，默认 `false`，建索引。
- `admin_removed_at`：管理员移除时间。
- `admin_removed_by`：移除人用户 ID。
- `admin_removed_by_name`：移除人姓名快照。
- `admin_remove_reason`：移除原因，最多 500 字。
- `admin_removed_prev_plan_status`：移除前的计划状态，用于恢复。

启动迁移沿用 `_ensure_tracking_columns()` 的幂等补列方式：

- `ALTER TABLE st_tracking_item ADD COLUMN ...`
- `CREATE INDEX IF NOT EXISTS ix_st_tracking_item_admin_removed ON st_tracking_item(admin_removed)`
- 迁移只新增列和索引，不重建表、不回填业务数据。

## 后端接口

新增接口：

- `POST /api/ship-tracking/admin/remove-plans`
  - 入参：`ladder_keys`、`reason`
  - 返回：`removed`、`skipped`、`not_found`、按原状态统计的数量
- `POST /api/ship-tracking/admin/restore-plans`
  - 入参：`ladder_keys`、`reason`
  - 返回：`restored`、`skipped`、`not_found`

服务层新增：

- `remove_plans(user, ladder_keys, reason)`
- `restore_plans(user, ladder_keys, reason)`

处理规则：

- 校验管理员权限和必填原因。
- 梯号去重并做规范化；按 500 条分块查询，避免 SQLite 参数上限。
- 已移除记录跳过并计入 `skipped`；不存在的梯号计入 `not_found`。
- 移除时记录移除前状态，并写入 `plan_status='removed'`、`plan_removed_at` 和管理员移除字段。
- 不清理实发、订舱、承诺、预计日期、备注或计划版本。
- 恢复时清除管理员移除字段，并恢复 `admin_removed_prev_plan_status`。
- 整批单事务提交；任一数据库异常回滚。

## 状态与查询

- `_tracking_dict()` 增加管理员移除字段；管理员已移除时优先显示状态 `admin_removed`，标签为“管理员已移除”。
- `query_tracking()` 默认排除 `admin_removed`；`include_removed` 为真时同时显示自动计划移除和管理员移除记录。
- `get_weekly()` 直接排除 `admin_removed`，不再因为已有实际发货日期而显示。
- `_weekly_action_state()` 对管理员已移除记录禁用改期和撤回，并返回阻塞原因。
- 状态筛选增加“管理员已移除”；汇总中的 `removed` 计数保持兼容，可同时统计自动移除和管理员移除。

## 前端交互

### 全量明细

- 工具栏增加“移除选中计划”按钮，仅 `context.can_admin` 且有选中行时显示。
- 弹窗明确展示：
  - 选中总数；
  - 已发货、已订舱、已提交数量；
  - 提示“将从明细中移除，但不会删除实际发货、订舱和审计记录”；
  - 必填移除原因。
- 操作成功后刷新列表、汇总和上下文。
- 勾选“显示已移除计划”后，选中管理员已移除记录时显示“恢复选中计划”按钮。

### 行状态与详情

- 表格状态标签支持“管理员已移除”。
- 详情抽屉展示移除人、移除时间、移除原因和移除前状态。
- 操作历史增加“管理员移除计划”“管理员恢复计划”。

## 导入与恢复保护

管理员移除必须是稳定状态，后续导入不能自动恢复：

- Excel 计划导入：已有行若 `admin_removed=true`，跳过字段更新和计划恢复，并计入 `skipped_admin_removed`。
- 从单月填报生成计划：预览和提交都跳过管理员已移除梯号，并返回跳过数量。
- 上月结转：跳过管理员已移除记录。
- 业务手工添加：不能恢复管理员已移除梯号，提示联系管理员；管理员通过“恢复计划”处理。
- 台账同步、每日实发、订舱导入不改变管理员移除状态；恢复后仍能看到原事实数据。

## 审计

- 移除写入 `category='plan'`、`action='admin_remove_plan'`。
- 恢复写入 `category='plan'`、`action='admin_restore_plan'`。
- 审计内容包含原因、移除前状态、实发日期、订舱状态、提交状态、预计日期和操作人。
- 前端操作历史映射以上两个动作名称。

## 测试清单

- 管理员分别移除未提交、已提交、已订舱、已发货、已逾期记录。
- 移除后默认全量明细、业务整体发货明细、汇总和导出均不再出现；勾选“显示已移除计划”后可出现。
- 已发货和已订舱事实数据仍保留，恢复后完整显示。
- 普通业务账号直接调用接口返回 403。
- 业务周填报撤回逻辑保持原样，不受本次改动影响。
- Excel 重新导入、单月填报重新生成、上月结转均不会恢复管理员已移除记录。
- 已移除梯号不能改期、撤回、填写业务备注或手工恢复。
- 恢复后计划状态、预计日期、标记和业务操作能力正常。
- 批量 500 条以上梯号可正常处理；重复梯号、未知梯号返回正确计数。
- 审计日志和详情抽屉信息完整。

## 上线顺序

1. 备份 `backend/instance/system.db`。
2. 发布后端，确认新增列和索引已创建。
3. 执行前端构建并发布 `dist`。
4. 重启 Flask/Gunicorn，强制刷新浏览器缓存。
5. 由管理员用一个测试梯号验证移除、默认隐藏、显示已移除、恢复和审计。

## 涉及文件

- `backend/ship_tracking/models.py`
- `backend/ship_tracking/__init__.py`
- `backend/ship_tracking/services.py`
- `backend/ship_tracking/blueprint.py`
- `backend/ship_tracking/importer.py`
- `frontend/src/api/shipTracking.js`
- `frontend/src/views/ship_tracking/FullTracking.vue`
- `frontend/src/views/ship_tracking/TrackingTable.vue`

## 本方案默认决策

- “移除计划”是软移除，不做物理删除；实际发货、订舱和审计事实继续保留。
- 管理员移除优先于已发货状态：即使原记录已发货，默认明细也不显示，只有勾选“显示已移除计划”后可见。
- 业务不获得删除能力；如后续需要业务申请删除，建议做“业务申请、管理员审核”而不是直接放开。

## 实施记录（2026-11-26）

- 已完成后端字段、幂等迁移、移除/恢复接口、查询隐藏、周填报隐藏、导入/结转保护。
- 已完成前端工具栏按钮、确认弹窗、原因必填、管理状态展示、详情字段和操作历史名称。
- 订舱导入额外跳过 `admin_removed` 记录，避免后续订舱文件把隐藏行的订舱事实重置；台账同步和每日实发只更新业务事实，不会清除管理员移除状态。
- 回款计算仍使用历史梯号事实数据，不因管理员移除而删除回款金额或比例；这属于财务历史口径，不在“整体发货明细”显示范围内。
- 后端 5 个改动文件通过 Python `compile()` 语法检查。
- 临时 SQLite 回归共 27 项全部通过：覆盖五种状态移除、默认隐藏、显示已移除、业务视图隐藏、业务手工添加拒绝、恢复原状态、自动移除恢复、HTTP 接口、业务 403、审计记录，以及计划导入、单月填报导入、上月结转均不复活。
- 前端 `npm.cmd run build` 构建成功，仅保留项目原有的 chunk 体积和第三方 PURE 注释警告。
