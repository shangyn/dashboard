# 发货梯号明细 - 业务备注与整体明细口径（2026-11-11）

## 目标

- 业务填报页下方改为本模块“整体发货明细”，与上方候选池不重复。
- 未发货梯号支持业务填写备注，已发货梯号只读。
- 管理端全量明细可显示/隐藏备注，并导出备注列。
- 月度预计发货计划模板增加最后一列“备注”，导入时落库。

## 数据口径

### 候选池

同时满足以下条件：

- 属于当前账号可填报模块；
- 计划有效；
- 未发货；
- 未提交；
- 没有预计发货日期。

### 整体发货明细

属于当前账号可填报模块，并满足以下任一条件：

- 已有预计发货日期；
- 已提交；
- 已发货。

已移除且未发货的计划不进入业务填报页；已发货记录即使计划已移除仍保留。

排序规则：

1. 未发货在前，已发货在后；
2. 未发货按预计发货日期升序，无日期排最后；
3. 已发货按实际发货日期倒序；
4. 不在候选池中重复出现。

## 备注字段

- `st_tracking_item.business_remark`：业务当前最新备注。
- `st_plan_item.remark`：月度计划导入时的原始备注快照。
- 业务备注通过 `POST /api/ship-tracking/weekly/remark` 保存，写入审计日志。
- 仅整体发货明细中的未发货梯号可编辑；已发货梯号、候选池梯号不可编辑。
- 自由文本，最多 500 个字符；可为空，保存后即时生效。

## 计划导入

- 月度计划模板从 11 列扩展到 12 列，最后一列为“备注”。
- 表头按名称识别，“备注”为可选列；文件没有该列不影响旧文件导入。
- 新梯号：文件有备注则导入，没有则为空。
- 已有梯号且系统备注为空：导入文件备注。
- 已有业务备注：保留系统备注，不自动覆盖；预览显示冲突数量。
- 文件备注为空：不清空已有业务备注。

## 管理端

- 全量明细表格增加可隐藏“备注”列，默认显示。
- 已有本地列设置自动补入备注列一次，之后仍可手动隐藏。
- 详情抽屉增加备注。
- 导出明细最后增加“备注”列，其他列顺序不变。

## 涉及文件

- `backend/ship_tracking/models.py`
- `backend/ship_tracking/__init__.py`
- `backend/ship_tracking/services.py`
- `backend/ship_tracking/blueprint.py`
- `backend/ship_tracking/plan_headers.py`
- `backend/ship_tracking/importer.py`
- `frontend/src/api/shipTracking.js`
- `frontend/src/views/ship_tracking/WeeklyFill.vue`
- `frontend/src/views/ship_tracking/TrackingTable.vue`
- `frontend/src/views/ship_tracking/FullTracking.vue`

## 上线检查

- 备份数据库后重启，确认新增列：
  - `st_tracking_item.business_remark`
  - `st_plan_item.remark`
- 验证老计划文件仍可导入。
- 验证新模板最后一列为“备注”。
- 验证业务填报页候选与整体明细无重复。
- 验证未发货可备注、已发货只读。
- 验证全量明细备注列可隐藏，导出最后一列为备注。
