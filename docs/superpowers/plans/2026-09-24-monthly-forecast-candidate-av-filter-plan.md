# 单月签排发填报 — 候选梯号按台账「整梯发货日期」(AV 列) 过滤 Implementation Plan

> **For agentic workers:** 逐条实现，改完一项勾一项（`- [ ]` → `- [x]`）。

**Goal:** 模块人员进入填报页时，「可发货梯号」候选池在**原有筛选规则基础上再加一条**：台账 Excel **AV 列「整梯发货日期」**（第 48 列）不得晚于当前填报月份。例：填报 2026-10 时，整梯发货日期为 2026-11 及以后的梯号不再进入可供勾选的列表。

**硬约束:** 原有候选池规则一条不动（只是追加一条）；不动 `mf_*` 表结构；不改其他模块的页面与接口；不新增依赖。

**状态:** 代码已实施（2026-09-24），待重启服务 + 重传台账 + 前端构建。

---

## 0. 需求原文与理解

> 「模块人员进入填写页面时，展示的模块可发货梯号，现在需要增加一个筛选条件，即 AV 列 整体发货日期，这个日期不能超过填报的月份。十月填报举例，如果当前筛选逻辑有 AV 是十一月份的，就不进入可供选择的梯号。」

- 「AV 列」= 台账 xlsx 的第 48 列（Excel 列标 AV）
- 「整体发货日期」= 该列表头实际写作 **整梯发货日期**（与 AW「部分发货日期」相对）
- 「填报的月份」= 页面选中的填报月 `data_month`（`YYYY-MM`，默认下个月）
- 判定：`整梯发货日期 > 填报月` → 该梯号不出现

## 1. 现状核查（读 system.db + 台账 xlsx，2026-09-24）

### 1.1 台账里的日期列

来源文件：`backend/uploads/contract_completion/contract_ledger/国贸合同标的台账(50).xlsx`，共 91 列。

| 列 | 表头 | 是否入库 |
|----|------|----------|
| AT | 整梯发货通知单号 | 否 |
| AU | 部分发货通知单号 | 否 |
| **AV** | **整梯发货日期** | **否 — 本次要用，当前完全没入库** |
| AW | 部分发货日期 | 否 |
| AX | 转收入通知单 | 否 |
| AY | 实际发货日期 | 否 |
| AZ | 组A日期 | 是 → `LedgerContract.delivery_date` |

> 现在做候选池判定的 `delivery_date` 用的是 **AZ 组A日期**（`backend/dashboards/contract_completion/handlers.py:121`、`handlers.py:150`），
> 与需求要的 AV「整梯发货日期」**不是同一列**。

### 1.2 候选池现状（按现行规则实测）

`backend/monthly_forecast/services.py:121` `list_candidates()`：

```
cc_ledger_contract
where source = 'ledger'
  and (product_status is null or product_status <> '已作废')
  and delivery_date is null          -- 组A日期为空
  and schedule_date is not null
→ 1946 行
```

把这 1946 行按梯号回连台账 xlsx 的 AV 列（1946/1946 全部匹配到）：

| AV 情况 | 行数 |
|---------|------|
| 空 | 945（48.6%） |
| 非空，≤ 2026-10 | 995 |
| 非空，> 2026-10 | **6** |
| （其中 AV 早于 2025 的老日期） | 139 |

- **填报 2026-10 时新增排除 6 条**：全部来自同一合同 `DHT-260798T`（国家 俄罗斯1，6 台，整梯发货日期 2027-09-14）。
- AV 高峰月：2026-09（347）、2026-08（150）、2026-07（72）、2026-04（71）、2026-10（35）。
- AV 最大月份：2027-09。

## 2. 口径（实现时不可偏离）

```
候选(模块, 填报月) =
  cc_ledger_contract
  where source = 'ledger'
    and (product_status is null or product_status <> '已作废')   -- 原有
    and delivery_date is null                                   -- 原有（组A日期为空）
    and schedule_date is not null                               -- 原有
    and 归属模块 == 当前模块                                      -- 原有
    and (whole_ship_date is null                                -- 新增：AV 为空 → 保留
         or whole_ship_date <= 填报月末)                          -- 新增：AV 不得晚于填报月
  order by schedule_date desc, contract_no, ladder_no
```

- 比较粒度 = **年月**：填报月 `2026-10` 时，`2026-10-31` 仍在池内，`2026-11-01` 起排除。
- 不做下界：整梯发货日期早于填报月的仍保留。
- 归属模块判定、排序、关键字过滤、分页：**一律不动**。

## 3. 关键决策：AV 列怎么进系统

| 方案 | 做法 | 代价 | 结论 |
|------|------|------|------|
| **A** | 给 `cc_ledger_contract` 加一列 `whole_ship_date`，在既有台账解析里多读一列 | 动既有模块 2 个文件 + `seed.py` 幂等 ALTER；**需重传一次台账**，否则列为空、过滤静默失效 | **采用** |
| B | 本模块自己解析台账 xlsx（仿 `monthly_forecast/mapping.py` 解析业务员表） | 8 万行 Excel 解析一次约 35 秒，须加缓存表 + 定触发时机；与 DB 有不同步风险 | 备选 |
| C | 建 `mf_` 侧缓存表，候选池首次访问按 TTL 重建 | 免不了慢 / 同步问题 | 不推荐 |

**采用 A 的理由**

- `backend/seed.py:43-48` 已有先例：给 `cc_ledger_contract` 加过 `personal_module` / `personal_region`，写法完全一致；纯新增可空列，零回归。
- 台账上传是**每日全量替换**（`handlers.py:157` 先 delete 再插入）→ 加列之后每次上传自动填充，无需额外维护。
- 候选池查 DB，无解析开销。
- **代价**：需重新上传一次台账才生效。重传之前新列全为 NULL → 全部落入「AV 为空（保留）」→ 行为与现在完全一致，**安全降级、不报错**。

> 本方案会给 `cc_ledger_contract` 增加一列，与「新模块立项时的硬约束：既有数据表 0 结构变更」不同，已确认按此实施。

## 4. 影响文件

| 文件 | 改动 |
|------|------|
| `backend/dashboards/contract_completion/models.py` | `LedgerContract` 增 `whole_ship_date = db.Column(db.Date, index=True)` |
| `backend/dashboards/contract_completion/handlers.py` | ① 新增 `col_whole_ship_date = _h('整梯发货日期')`；② 日期预检块加 `wd = _safe_date_openpyxl(...)`；③ `row_data` 加 `'whole_ship_date': wd` |
| `backend/seed.py` | 既有 `lc_cols` 块（44-48 行）追加幂等 `ALTER TABLE cc_ledger_contract ADD COLUMN whole_ship_date DATE` |
| `backend/monthly_forecast/services.py` | `list_candidates(module_name, data_month=None, keyword=None)` 增参数 + 一条过滤 |
| `backend/monthly_forecast/blueprint.py` | `/candidates`（181 行）用既有 `_resolve_month()`（49 行）取月并传入 |
| `frontend/src/api/monthly-forecast.js` | `getCandidates(module, month, q)` 带 `month` |
| `frontend/src/views/MonthlyForecast.vue` | `loadCandidates()`（346 行）带 `month.value` |

**零改动**：`cc_*` 其他表与列、`mf_*` 表结构、候选池其余规则、其他模块页面与接口。
`handlers.py:147-153` 的 `date_cols` 是死代码（声明了但从未使用），**不要顺手改它、也不要往里加**。

## 5. 需求确认（2026-09-24 定稿）

| # | 问题 | 结论 |
|---|------|------|
| 0 | 「AV 列」= 台账第 48 列「整梯发货日期」 | 是 |
| 1 | AV 为空（945 行，48.6%）怎么处理 | **保留**，不参与判断 |
| 2 | 比较粒度 | **按年月**（`2026-10-31` 保留） |
| 3 | 是否加下界 | **不加**。整梯发货日期早于填报月的仍保留 |
| 4 | 手工输入梯号是否同样受限 | **不加**限制。`validate_ladder()` 保持原样 |
| 5 | 是否放开「给 `cc_ledger_contract` 加一列」的约束 | 是，在原有筛选基础上增加这一条 |
| 6 | 已被勾选保存的梯号若被排除，是否自动清理 | 不清理，只影响可选池 |
| 7 | 候选表格是否加「整梯发货日期」显示列 | 不加（保持最小改动） |

## 6. 任务

### Task 1: 台账侧 AV 入库
- [x] `models.py`：`LedgerContract` 增 `whole_ship_date`（`db.Date`，可空，`index=True`）
- [x] `handlers.py`：`_h('整梯发货日期')` 取列；日期预检块解析；`row_data` 带出（与 `dd` 同层同写法）
- [x] `seed.py`：`lc_cols` 块内追加幂等 ALTER（`DATE`，可空）
- [ ] **重新上传一次台账**（唯一剩余动作，需在「合同完成情况」页面操作），SQL 抽查 `DHT-260798T` 6 条已填充 `2027-09-14`

### Task 2: 候选池过滤（services.py）
- [x] `list_candidates(module_name, data_month=None, keyword=None)`：`data_month` 为空时**不做该过滤**（向后兼容）
- [x] 过滤实现：`whole_ship_date is None or whole_ship_date.strftime('%Y-%m') <= data_month`
- [x] 返回体增加 `whole_ship_date` 字段（仅备用，不加显示列）

### Task 3: 接口
- [x] `blueprint.py` `/candidates`：`_resolve_month()` 取月；月份缺失/非法时行为与 `entry` 接口保持一致
- [x] `monthly-forecast.js`：`getCandidates(module, month, q)`

### Task 4: 前端
- [x] `MonthlyForecast.vue` `loadCandidates()` 带 `month.value`（`onMonthChange → loadPage → loadCandidates`，切月自动重拉，无需额外改动）

### Task 5: 明确不做
- [x] `validate_ladder()` 不加该判定（手工输入不受限）
- [x] 不加下界、不加显示列、不清理已保存的勾选

## 7. 验证

- [x] 回归基线：`data_month` 不传 / 台账未重传时，候选池 = 1946 行，与改动前逐行一致
- [x] 填报 2026-10：候选池 = 1940（1946 − 6），且 `DHT-260798T` 的 6 个梯号消失
- [ ] 填报 2026-09：排除 41（2026-10 的 35 + 2027-09 的 6），候选池 = 1905
- [x] 填报 2027-09：这 6 个梯号重新出现（2027-09 ≤ 2027-09）
- [x] AV 为空的行在任何月份都在池内（AV 全 NULL 时 1946/105 与改动前一致）
- [ ] AV 早于填报月的行不被排除（无下界）
- [ ] 手工输入 `DHT-260798T/1#`（填报 2026-10）仍可添加成功（不受限）
- [ ] 「共 N 条」计数、关键字搜索、分页在过滤后仍正确（服务端过滤，客户端只做搜索与分页）
- [ ] 已勾选已保存的梯号不受影响；汇总 / 导出①② 数值不变
- [x] 影响面回归：对照模块 埃及-1 492/492 不变，`cc_ledger_contract` 行数不变

## 8. 部署

1. 同步后端文件 → 重启服务（启动时 `seed_database()` 自动执行 `ALTER TABLE`）
2. **在「合同完成情况」重新上传一次台账**（关键：否则新列为空、过滤不生效）
3. 前端重新构建：`cd frontend && npm run build`
4. 回滚：新列可空、旧代码忽略它；`list_candidates` 的 `data_month` 可选，前端回退即恢复原行为

## 9. 实施记录（2026-09-24）

**已改 7 个文件**（`git diff --stat`：28 insertions / 6 deletions）

```
backend/dashboards/contract_completion/models.py   |  1 +
backend/dashboards/contract_completion/handlers.py |  5 ++++-
backend/monthly_forecast/services.py               | 15 ++++++++++++++-
backend/monthly_forecast/blueprint.py              |  5 ++++-
backend/seed.py                                    |  2 ++
frontend/src/api/monthly-forecast.js               |  4 ++--
frontend/src/views/MonthlyForecast.vue             |  2 +-
```

**与「组A日期」的隔离（重点复核）**

| 台账列 | 表头 | 字段 | 状态 |
|--------|------|------|------|
| AZ | 组A日期 | `LedgerContract.delivery_date` | 原有，`handlers.py:121` / `models.py:37` 一行未动 |
| AV | 整梯发货日期 | `LedgerContract.whole_ship_date` | 新增，独立按列名 `_h('整梯发货日期')` 精确取，不走组A的别名链 |

**实跑验证**（`create_app()` → 事务内临时写入 AV 值 → 断言 → `rollback()`，未落库）

| 场景 | 结果 |
|------|------|
| 迁移 | `whole_ship_date` 已建列；`delivery_date` 仍在 |
| AV 全 NULL（= 台账尚未重传） | 模块 105 / 全域 1946，任何月份都一样 → 与改动前完全一致 |
| 临时置 6 行 AV=2027-09-14 后，month=2026-08/09/10/11 | 模块 99（105−6），DHT 全部消失 |
| month=2027-09 | 模块 105，DHT 6 条回归（2027-09 ≤ 2027-09） |
| month=None | 105，不触发过滤（向后兼容） |
| 全域 month=2026-10 | **1940**（1946−6），与 Excel 侧测算完全吻合 |
| 对照模块 埃及-1 | None=492 / 2026-10=492，不受影响 |
| rollback | `DHT-260798T/1#` 的 `whole_ship_date` 回到 NULL，模块回到 105 |

**尚未验证 / 剩余动作**

- 台账重传（唯一剩余数据动作）
- 前端 UI 走查：共 N 条计数、搜索、分页（本次改动是服务端过滤，客户端逻辑未动）
- 填报 2026-09 排除 41 条（2026-10 的 35 + 2027-09 的 6）：需台账重传后用真实数据复核
- `validate_ladder()` 手工输入不受限：代码未改动，逻辑上不受影响，需人工点一次确认
