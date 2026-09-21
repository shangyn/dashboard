# 大区/模块重构影响面清单（9大区 → 2大区）

**日期:** 2026-09-21
**状态:** 待定 — 新大区划分与模块方案尚未确定，暂不改动代码

---

## 1. 背景

后续「几个大区」将合并为「两个大区」，模块划分也会调整。届时上传新版的
《国家模块业务员表》，系统需要能正确出数。本文档记录当前代码中所有与大区/模块
强耦合的位置，以及届时的改动清单。

## 2. 前提假设

- 新《国家模块业务员表》仍保持 `Sheet3` 结构：A=国家、D=2026模块、E=2026大区
- 表头文本仍含「国家」「2026…模块」「2026…大区」
- 商贸/配件体系（商贸合计、配件-1/2、改造）保留

以上任一条不成立时，第 3.1 节的解析逻辑也要改。

## 3. 影响面

### 3.1 数据入口（已动态，通常无需改）

| 位置 | 说明 |
|------|------|
| `backend/dashboards/contract_completion/handlers.py:241` `parse_country_mapping` | 全量替换 `cc_country_mapping`，大区名取 Sheet3 E 列原值，**不做合法性校验**。列位/表头变化时才需改 |
| `backend/dashboards/contract_completion/services.py:88` `_load_mapping` / `:111` `_resolve_contract` | 按 `country` 查表取大区/模块，大区名仅作字符串传递 |
| `backend/dashboards/contract_completion/models.py` `CountryMapping` | `region = String(50)`，新名称长度无压力，**无需改表结构** |

注意：`module_manager` / `salesperson` 目前固定写空字符串（B/C 列未读取）。

### 3.2 必须修改的硬编码大区名单

| 位置 | 内容 | 影响 |
|------|------|------|
| `services.py:47` | `REGION_ORDER`（9 个大区） | `_build_region_summary` (`services.py:298`) **只遍历该列表**，不在名单中的大区会被静默丢弃：大区汇总缺行、合计少算。`get_regions` (`services.py:629`) 也用它供前端下拉框 |
| `services.py:1073` | `get_two_year_comparison` 内部重复定义的 `region_order` | 两年对比数据行排序（不在名单者排到 99，顺序错乱但不丢行） |
| `backend/seed.py:107-118` | `_seed_annual_targets()` 的 9 大区年度指标 | 写入 `cc_annual_target`，供大区汇总「指标」列。**仅在表为空时种子**，改名后需清表重种或写迁移；大区名必须与映射表上传结果完全一致，否则完成比全为 0 |
| `backend/dashboards/generate_dashboard/generate_report_v3.py:26`、`generate_report_june.py:44` | 各有一份 `REGION_ORDER` | 商贸数据看板的 `generate-dashboard` 子进程脚本 |

### 3.3 模块与大区的绑定关系（工作量最大）

| 位置 | 内容 | 影响 |
|------|------|------|
| `services.py:1193` | `ANNUAL_TARGETS`，key = `(大区, 模块)` | 年度完成比、两年对比指标列；并经 `handlers.py:568` `_build_module_region_map` 决定报表a个人业绩归属哪个大区。**需整表重抄** |
| `services.py:657` | `CATEGORY_MAP`（模块 → 类别 A/B/C/D） | 导出 Excel「类别」列，新模块需重新归类 |
| `services.py:693` | `AZT_MODULE_MAP`（AZT 合同 → 模块） | 模块改名后映射 miss，回款无法归入对应模块 |
| `数据源/模块对应表.xlsx`「整梯模块对应表」 | D=姓名 / E=模块，由 `handlers.py:574` `_load_person_module_map` 读取 | 模块名变化后报表a个人业绩归属整块失效 |

### 3.4 商贸 / 改造特判

| 位置 | 内容 |
|------|------|
| `services.py:69`、`services.py:654` | `TRADE_MODULES` / `TRADE_MODULES_ORDER`（商贸1/2/3、配件-1/2、改造） |
| `services.py:92`、`services.py:115`、`services.py:133-138`、`services.py:835-844` | `商贸配件 → 商贸合计` 归一化；`product_type` 含「改造」时强制归入 `商贸合计/改造` |
| `services.py:809`、`services.py:1117`、`services.py:1133`、`services.py:1152`、`services.py:1171` | 硬编码行名 `商贸合计` / `商贸配件合计` / `国际总计` |

### 3.5 前端

| 位置 | 内容 |
|------|------|
| `frontend/src/views/ContractCompletion.vue:112` | 大区下拉框硬编码 9 个名字，建议改为调用 `getRegions()` 接口 |
| `frontend/src/components/ContractCompletion/AnnualCompletionTable.vue` | 「改造」分组表头与列合并逻辑 |
| `frontend/src/components/ContractCompletion/TableSheet1.vue:29` | 按 `row.region === '商贸合计'` 判定行样式 |
| `frontend/src/views/TwoYearComparison.vue`、`TwoYearDashboard.vue` | 从接口 `region_order` 动态取值，**自动适配** |

### 3.6 其他看板

- 工期统计 `backend/dashboards/Project_Schedule/scripts/generate_schedule_dashboard_v2.py:103` 按 `mapped_region` 动态分组，可自动适配；但 `:162` 用 `sorted()` 排序大区，需要显式顺序表才不会乱序。
- `docs/superpowers/specs/2026-07-08-exclude-gaizao-units-from-totals-design.md` 中「按 `商贸合计` 过滤 Excel 公式」的设计经核对**尚未落地**，若后续实施需跟随新大区名。

## 4. 数据侧

- 映射表为全量替换，重传后旧大区名自动消失，无需手工清理。
- `LedgerContract.mapped_region`、`ScheduleTracking.mapped_region` 是**上传时写入的快照**，映射表本身不会回填；改完必须重新上传台账 / 报表a、b / 回款 / 发货 / 工期表。
- 建议为「未知大区」增加告警：当前不在 `REGION_ORDER` 的大区会被静默丢弃，可复用 `uploads/mapping_report.txt` 的报告机制。

## 5. 实施顺序（待方案确定后执行）

1. 抽取常量模块（如 `backend/dashboards/contract_completion/constants.py`），集中 `REGION_ORDER`、`TRADE_MODULES`、`商贸合计`、`改造`，消除重复定义。
2. 重抄 `ANNUAL_TARGETS`、`seed.py` 年度指标、`CATEGORY_MAP`、`AZT_MODULE_MAP`。
3. 增加未知大区告警。
4. 前端大区下拉框改为走接口。
5. 更新 `数据源/模块对应表.xlsx`。
6. 重传全部数据，核对：大区汇总、模块明细、两年对比、年度完成比、工期看板、Excel 导出。

## 6. 待确认事项

- [ ] 新两个大区的具体名称
- [ ] 模块调整方式（改名 / 合并 / 新增 / 删除）
- [ ] 新《国家模块业务员表》的 Sheet 名、列位置、表头文本是否不变
- [ ] 商贸 / 配件 / 改造 体系是否保留
- [ ] 年度指标是否同步提供两个大区口径的新数值
