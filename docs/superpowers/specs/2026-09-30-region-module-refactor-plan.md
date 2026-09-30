# 大区/模块重构实施计划（9大区 → 2大区）

**日期:** 2026-09-30
**状态:** 已确认并按「方案 A」一次性实施完成（2026-09-30）
**上游文档:** `docs/superpowers/specs/2026-09-21-region-module-refactor-impact.md`

---

## 1. 本次输入

| 文件 | Sheet | 结构 | 用途 |
|------|-------|------|------|
| `数据源/国家-市场-业务员9.29.xlsx` | `Sheet3` | A=国家, B=2025九大区模块, C=2025九大区, **D=2026年对应模块, E=2026对应大区**, F=原模块, G=标记 | 系统目前唯一读取的映射源（`handlers.parse_country_mapping`）；末尾 15 行只有模块、没有国家 |
| 同上 | `模块-模主-助理` | 序号/模块/模主/助理/助理2/大区（分 陈、刘 两段） | 模块→模主/助理/大区 |
| 同上 | `国家-业务员` | 国家/模块/大区/模块经理（194 国） | 国家→模块/大区/**模块经理**（`Sheet3` 子集，无冲突） |
| `数据源/模块任务划分9.30.xlsx` | `Sheet1` | 序号/模块/**模块级别(A/B/C/D)**/签订台数/签订额/排产台数/排产额/发货台数/发货额/**回款指标** | 新版 `ANNUAL_TARGETS` + `CATEGORY_MAP`，分 陈、刘 两段 |

实测数据：

- `Sheet3`：272 个国家行（有效 247 行 → 去重 243 国）+ **15 个"无国家、只有模块"占位行**；25 行无效（`#N/A`/`0`）
- 大区取值只有 **刘 / 陈**（已定：陈=`大区1`、刘=`大区2`）
- **三个文件模块清单完全一致：80 个模块**（陈 40 + 刘 40），模块→大区无冲突
- `模块任务划分9.30` 给出 **模块级别(A/B/C/D) + 7 项指标（含回款）**，正好替代 `CATEGORY_MAP` 与 `ANNUAL_TARGETS`；仅 `商贸1-4` 无级别
- 台账 229 国中 **215 国有有效映射**；14 国（乌干达、美国、意大利、加纳、阿富汗…）D/E 为 `0`/`#N/A`，与旧表一致，仍会进未匹配
- E 列表头由 `2026九大区` 改为 **`2026对应大区`**
- **商贸/配件模块现在带大区**：`配件-1/2/3/4`、`改造` → 陈（大区1）；`商贸1/2/3/4` → 刘（大区2）

### 1.1 模块变更（旧 → 新）

**改名：**

| 旧模块 | 新模块 |
|--------|--------|
| 乌兹别克斯坦 | 乌兹别克斯坦-1 |
| 伊朗+阿曼 | 伊朗 / 阿曼（拆分） |
| 孟加拉-1 | 孟加拉 |
| 巴西 | 巴西-1 |
| 秘鲁 | 秘鲁-1 |
| 秘鲁2 | 秘鲁-2 |
| 菲律宾 | 菲律宾-1 |
| 金三角 | 泰国 |
| 香港-台湾 | 日港台 |
| 0（无效） | 伊拉克 |

**新增模块（旧 `ANNUAL_TARGETS` 没有）：**
土耳其、乌兹别克斯坦（工厂）、阿曼、伊朗、孟加拉、日港台、秘鲁-1、秘鲁-2、菲律宾-1、巴西-1、泰国3、巴西-2、阿根廷、乌克兰、格鲁吉亚、德国西班牙、**商贸4、配件3、配件4**

**`Sheet3` 末尾占位（暂无国家绑定）：**
格鲁吉亚、乌克兰、配件-1、配件-2、配件3、配件4、改造（→ 陈）；泰国3、巴西-2、阿根廷、德国西班牙、商贸1、商贸2、商贸3、商贸4（→ 刘）

---

## 2. 大区/模块在项目中的定义与使用位置（全景）

### 2.1 数据入口（动态，一般不用改）

| 位置 | 说明 |
|------|------|
| `backend/dashboards/contract_completion/handlers.py:247` `parse_country_mapping` | 全量替换 `cc_country_mapping`，D/E 列原样入库，不校验大区名；`module_manager/salesperson` 固定写空 |
| `handlers.py:237` `_is_invalid` | `#N/A / 0 / None / 空` 视为无效并跳过，输出 `uploads/mapping_report.txt` |
| `models.py:61` `CountryMapping` | `region = String(50)`，2 字大区名无压力，**不用改表结构** |
| `services.py:88` `_load_mapping` / `:111` `_resolve_contract` | 按 `country` 查大区/模块，大区名只当字符串传递 |

### 2.2 硬编码大区名单（**必须改**）

| 位置 | 内容 | 不改的后果 |
|------|------|-----------|
| `services.py:47` | `REGION_ORDER`（9 个大区） | `_build_region_summary`(`:298`) 只遍历它 → 不在名单的大区**静默丢弃**，大区汇总缺行、合计少算 |
| `services.py:339` | `_build_module_detail` 用 `REGION_ORDER.index` 排序 | 新大区排到 99，顺序错乱 |
| `services.py:511` / `:528` / `:629` | 接口返回的 `region_order` / `get_regions` 下拉框 | 前端下拉框是旧大区 |
| `services.py:1076` | 两年对比内部重复定义的 `region_order`（8 个） | 两年对比行排序错乱 |
| `services.py:1746` | `get_annual_completion` 内部 `region_order`（8 个） | 年度完成比排序错乱 |
| `backend/seed.py:128-138` | `_seed_annual_targets` 的 9 大区年度指标 | `cc_annual_target` 里是旧大区名，大区汇总"指标"列全 0（**仅在表为空时种子**） |
| `generate_report_v3.py:26` | `REGION_ORDER`（8 个） | 见 2.4 |
| `generate_report_june.py:44` | `REGION_ORDER`（8 个） | 见 2.4（**致命**） |

### 2.3 模块↔大区/类别/指标绑定（工作量最大）

| 位置 | 内容 | 影响 |
|------|------|------|
| `services.py:1197` `ANNUAL_TARGETS` | key=`(大区, 模块)`，71 项 | 年度完成比指标、两年对比、**并经 `handlers.py:574` `_build_module_region_map` 决定报表a个人业绩归属哪个大区** → 改用 `模块任务划分9.30` |
| `services.py:657` `CATEGORY_MAP` | 模块 → 类别 A/B/C/D | 导出 Excel「类别」列 → 改用任务表「模块级别」 |
| `services.py:694` `AZT_MODULE_MAP` | AZT 合同 → 模块 | 其目标模块在新表中**全部存在**，可不改 |
| `handlers.py:580` `_load_person_module_map` | 读 `数据源/模块对应表.xlsx`「整梯模块对应表」D=姓名/E=模块 → 见 §3 说明 | 该文件仍是旧模块名（秘鲁/巴西/菲律宾/孟加拉-1/伊朗+阿曼/香港-台湾/更新改造）→ 报表a个人业绩归属整体 miss |
| `handlers.py:567` `_TRADE_SKIP_MODULES` | 商贸/配件/改造跳过集合 | 需补 `商贸4/配件3/配件4` |
| `seed.py:128` | 年度指标改为 2 大区 + 新模块 | 需清表重种或写迁移 |

### 2.4 商贸数据看板（`generate_data` 报表）

| 位置 | 内容 | 影响 |
|------|------|------|
| `generate_report_v3.py:221` `build_region_modules_from_db` | 从 DB 映射表建 `{大区: [模块]}`，先按 `REGION_ORDER` 建空桶，未知大区追加末尾 | 新大区行能出来但排在最后 |
| `generate_report_june.py:74` `fill_template_dynamic`（被 v3 复用） | `:131` `for region in REGION_ORDER:` —— **只遍历硬编码 8 大区** | **新大区一个都不会写进 Excel 报表**，必须改 |
| `generate_report_june.py:374` | 日志统计 | 同上 |
| `generate_report.py:114-145` `build_mapping` | 按表头关键词 `2026九大区` 定位大区列 | 新表头 `2026对应大区` → 取不到列 → KeyError（v1 旧路径，需确认是否仍在使用） |
| `generate_report_v3.py:27` / `generate_report_june.py:47` | `TRADE_PARTS_MODULES` | 需补 `商贸4/配件3/配件4` |

### 2.5 工期看板（`schedule_dashboard`）

| 位置 | 内容 | 影响 |
|------|------|------|
| `Project_Schedule/scripts/generate_schedule_dashboard_v2.py:103` | 按 `ScheduleTracking.mapped_region` 动态分组 | 自动适配；`:163` 按字母排序，2 大区需显式顺序 |
| `handlers.py:1200` `parse_schedule_tracking` | 上传时把大区/模块快照写入 `mapped_region/mapped_module` | 映射表更新后**必须重传工期表** |
| `Project_Schedule/scripts/process_data.py:23,34-52` | v1 脚本，硬编码文件名 + 读 Sheet3 | 旧路径，已停用，可不动 |

### 2.6 单月签排发填报（`monthly_forecast`）

| 位置 | 内容 | 影响 |
|------|------|------|
| `monthly_forecast/mapping.py:58-69` `_MODULE_ALIASES` | 旧写法 → 旧正式模块名（`日港台→香港-台湾`、`孟加拉→孟加拉-1`、`秘鲁－1→秘鲁`） | 新表里 `日港台/孟加拉/秘鲁-1` 本身就是正式名，别名会指到不存在的模块 → 解析失败 |
| `monthly_forecast/mapping.py:72`、`add_accounts.py:46` | `AUTHORITATIVE_SHEET = '任命令模块-模主'` | 新文件里该 sheet 已改名为 **`模块-模主-助理`**（`业务员-市场` → `国家-业务员`），命中不到会退化 |
| `monthly_forecast/mapping.py:155` `canonical_modules()`、`services.py:92` `all_modules()` | 从 `cc_country_mapping` 取模块名 | 重传后自动变新名；但 `UserScope` 里旧模块名需重跑账号同步 |
| `monthly_forecast/services.py:77-100` | 国家→模块 归属 | 自动适配 |

### 2.7 前端

| 位置 | 内容 | 影响 |
|------|------|------|
| `frontend/src/views/ContractCompletion.vue:112` | 大区下拉框**硬编码** 9 个值 | 必须改。顺带修 bug：缺 `中亚`、多一个不存在的 `亚洲`；`getRegions()` 已 import 未使用 |
| `frontend/src/components/ContractCompletion/TableSheet1.vue:29` | `row.region === '商贸合计'` 判定行样式 | 取决于 §4.2-1 的方案 |
| `TwoYearComparison.vue` / `TwoYearDashboard.vue` / `TwoYearTable.vue` / `TableSheet2.vue` | 从接口 `region_order` 动态取值 | 自动适配 |
| `TableSheet2.vue` | 「负责人」列显示 `module_manager` | 目前为空 |

### 2.8 数据侧（快照 + 按模块名匹配的数据源）

| 数据 | 说明 |
|------|------|
| `cc_ledger_contract.mapped_region/mapped_module` | 上传时快照（目前只对 report_a/b 商贸行有值）；台账行查询时动态映射 |
| `cc_schedule_tracking.mapped_region/mapped_module` | 上传时快照，**必须重传工期表** |
| `2025发货.xlsx`（→`cc_shipment_data`） | 按模块名匹配；含 `乌兹别克斯坦/伊朗+阿曼/孟加拉-1/秘鲁` 等旧名 → 需更新重传 |
| `海外差值2026.7(2).xlsx`（→`cc_overseas_diff`） | 按模块名匹配；含 `乌兹别克斯坦` 等旧名 → 需更新重传 |
| `商贸数据-看板.xlsx` / `2025商贸数据.xlsx` | 商贸模块名（商贸1/2/3、配件-1/2、改造）；新增商贸4/配件3/4 需确认 |
| `数据源/模块对应表.xlsx` | 旧模块名，见 §3 |

---

## 3. 两个待解释的用法

### 3.1 `数据源/模块对应表.xlsx` 用在哪

- `handlers.py:580` `_load_person_module_map()` 读它的 `整梯模块对应表`，D列=姓名 → E列=模块，得到 `{姓名: 模块}`。
- 只在 `handlers.py:613 parse_report_a()` 里用：报表a 的 col56 是"订单备注（人名）"，用 `{姓名: 模块}` 反查模块，再用 `_build_module_region_map()`（模块→大区，来自 `ANNUAL_TARGETS`）定大区。
- 结果写入 `LedgerContract.personal_module / personal_region`（`handlers.py:644-655, 678-679`）。
- 这两个字段只在 **`include_personal=1`** 时被使用：`services.py:899` 把报表a的个人业绩额外归属到大区/模块，供「两年对比」和「年度完成比」的 `include_personal` 视图（前端 `ContractCompletion.vue`、`TwoYearComparison.vue`）。
- **结论**：它是报表a个人业绩归属的唯一来源。文件里若还是旧模块名，`mod2region.get()` 取不到 → 归属结果直接为 None（静默丢弃）。

### 3.2 `CountryMapping.module_manager` 用在哪

- 列定义 `models.py:69`；上传时固定写 `''`（`handlers.py:336`），所以现在永远是空。
- 读取链：`services.py:94 _load_mapping` → `:140 _resolve_contract` 返回 manager → `:179` 存进 `module_data['manager']` → `:375 _build_module_detail` 输出 `module_manager` → `get_module_detail` API → 前端 `TableSheet2.vue` 的「负责人」列。**目前整列空白。**
- 同理 `salesperson` 进 `sp_data`，是「业务员表」`TableSheet3.vue` 的唯一数据源（`services.py:214 if sp:`）。因为恒为空，**「业务员表」事实上一直没有数据**。
- 两个 1 分钟就能补上：`国家-业务员` sheet 有 国家→模块经理，`模块-模主-助理` 有 模块→模主。

---

## 4. 已确认 / 待确认

### 4.1 已确认

1. 大区命名：陈=`大区1`、刘=`大区2`。
2. 年度指标改用 `数据源/模块任务划分9.30.xlsx` Sheet1，按模块对应。
3. 类别(A/B/C/D) 同在该文件的「模块级别」列。
4. `商贸4`、`配件3`、`配件4` 启用；部分新模块暂无国家绑定（`Sheet3` 末尾占位行）。

### 4.2 已确认（方案 A，已实施）

1. **商贸/配件并入大区（方案 A）**：取消独立「商贸合计」行；`配件-1/2/3/4`、`改造` → 陈（大区1）；`商贸1/2/3/4` → 刘（大区2）。
2. 「负责人」列取 `模块-模主-助理` 的**模主**；「积压台数」**清零**。
3. `模块对应表.xlsx` → 改读新文件的 `模块-模主-助理`（模主 + 助理）。
4. `CountryMapping.module_manager` **暂不填**（用户明确「先不填了」）；「负责人」改由常量表 `PERSON_MAP` 提供。
5. 无效国家（`#N/A`/`0`）继续跳过（与旧表一致，进未匹配清单）。

---

## 5. 实施结果（2026-09-30）

新增 `backend/dashboards/contract_completion/constants.py` 作为唯一事实来源：

- `REGION_ORDER=['大区1','大区2']`、`REGION_DISPLAY={'陈':'大区1','刘':'大区2'}`
- `MODULE_REGION`（80 模块→大区）、`PERSON_MAP`（80 模块→模主）、`CATEGORY_MAP`（80，商贸1-4 为 `''`）
- `ANNUAL_TARGETS`（80×7 指标）
- `TRADE_MODULES_ORDER`、`ACCESSORY_MODULES=['配件-1','配件-2','配件3','配件4']`、`ACCESSORY_ALIASES`、`ANNUAL_TARGET_METRIC_KEYS`

改动清单：

| 文件 | 改动 |
|------|------|
| `contract_completion/services.py` | 常量改 import；删 500 行旧指标；新增 `_normalize_region`（陈/刘→展示名、`商贸合计`按模块回落）；改造统一归 `_GAIZAO_REGION`（大区1）；删除商贸合计/配件合计行；`_inject_trade_data`/`AZT_MODULE_MAP` 用 `MODULE_REGION`；`get_annual_completion` 的 `person=PERSON_MAP[module]`、`backlog_units=0`；修 `_norm_target` 重复 `/10000` 的真实 bug |
| `contract_completion/handlers.py` | `parse_country_mapping` E 列经 `REGION_DISPLAY` 转展示名；`_TRADE_SKIP_MODULES` 补商贸4/配件3/配件4；`_load_person_module_map` 改读 `模块-模主-助理`（模主+助理）；`parse_report_a/b` 配件集合改 `ACCESSORY_MODULES`，签单/排产/发货行 `mapped_region=MODULE_REGION` |
| `seed.py` | `_seed_annual_targets` 从 `constants` 重建 2026 指标（模块级 80×7 + 大区级 2×7） |
| `generate_dashboard/generate_report_june.py` | 商贸/配件/改造**并入各自大区行**；删除「商贸配件」「商贸配件合计」两块；清理残留 merged cells |
| `generate_dashboard/generate_report_v3.py` | `build_region_modules_from_db` 以 `MODULE_REGION` 为准 |
| `generate_dashboard/generate_report.py` | `build_mapping` 大区列关键词 → `2026对应大区` |
| `generate_dashboard/fill_trade_parts*.py` | 配件模块改 `ACCESSORY_MODULES`；`_refresh_totals` 动态识别合计行 |
| `monthly_forecast/mapping.py` | `AUTHORITATIVE_SHEET='模块-模主-助理'`；`SOURCE_DIR` 回退 `数据源/`；别名精简 + 缺失时退回自动匹配；`canonical_modules` 含 `MODULE_REGION` |
| `monthly_forecast/services.py` | `all_modules()` 以 `MODULE_REGION` 为全集（80 个） |
| `monthly_forecast/add_accounts.py` | 支持 sheet 别名列表 |
| `Project_Schedule/scripts/generate_schedule_dashboard_v2.py` | 运行期按映射表动态解析 大区/模块（陈/刘→展示名） |
| `frontend/.../ContractCompletion.vue` | 大区下拉框改为 `getRegions()` 动态获取 |
| `frontend/.../TableSheet1.vue` | 删除 `商贸合计` 行样式 |

本轮补充修复的 3 个真实缺陷（收尾排查时发现）：

1. `generate_report.py` `build_mapping` 返回的 `region_modules` 仍以源表原始写法（`陈`/`刘`）为 key，而 `generate_report_june.fill_template_dynamic` 按 `REGION_ORDER`（`大区1/大区2`）取模块 → **6 月看板会一行都写不出来**。现已按 `REGION_DISPLAY` 归一，并以 `MODULE_REGION` 为全量模块清单（普通模块在前、商贸/配件/改造在后）。
2. `services.py` `get_two_year_comparison(include_personal=True)` 直接使用旧上传留存的 `personal_region`，会出现 `欧洲/中亚/中东…` 幻影大区行（实测 68 行）。现改为只认 `MODULE_REGION`，旧模块名历史行直接跳过（重传报表a 后即恢复）。
3. `handlers.py` `parse_report_a` 的**签单行** `mapped_region` 仍写死 `商贸合计`（只改了排产/发货行），现统一改为 `MODULE_REGION.get(模块)`。

验证：

- `python -m compileall` 0 错误；`npm run build` 成功
- 映射入库：243 条（大区1=106、大区2=137）
- 年度指标：574 行（80×7 + 2×7）；大区1 签单额指标 155494 万、大区2 89505.55 万，完成比口径正常
- 两年对比：83 行（80 + 2 子合计 + 1 总合计）
- 商贸数据看板 `generate_report('2026-09')`：80 模块 / 2 大区 / 2 子合计，`大区1合计` 第 45 行、`大区2合计` 第 86 行、`全国贸合计` 第 87 行
- 单月填报 `all_modules()` = 80 个；`mf_user_scope` 已按新映射重算（13 条改名，4 条待业务确认）
- 工期看板：1013 条（大区1=536、大区2=475、未分类=2）

---

## 6. 必须由用户重传 / 处理（代码无法代劳）

1. **在平台重传映射表** `国家-市场-业务员9.29.xlsx`（正式流程走上传；未上传时只读代码也可直接读 `数据源/`）。
2. **重传按快照/模块名匹配的数据**：台账、报表a、报表b、`2025发货`、`海外差值`、`商贸数据`、**工期表**（`cc_schedule_tracking` 快照大区名仍是旧的；代码已做运行期动态解析兜底）。
3. **单月填报名单**：已在库内按新映射重算；仍有 **4 个账号**查不到新归属，需业务确认：
   - `安鹏霖` 原 朝鲜-韩国（新表模主 = 金刚）
   - `李军辉` 原 阿联酋-2（新表模主 = 唐毓瀚）
   - `马月` 原 吉尔吉斯斯坦（新表模主 = 马玉）
   - `李知源` 原 秘鲁（新表拆成 秘鲁-1/秘鲁-2，两行均非此人）
4. `数据源/模块任务划分9.30.xlsx` 的年度指标**已自动入库**，无需上传。

## 7. 备注（未改，行为不变）

- `services.py` 的 `RATIO_CONFIG`、`_load_targets`、`get_region_summary`/`get_module_detail`（Sheet1/Sheet2 走 `cc_annual_target`）为另一套老接口。
- `AZT_MODULE_MAP` 的目标模块在新方案中均存在。
- `Sheet3` 末尾 15 行只有模块、无国家（格鲁吉亚、乌克兰、配件-1/2/3/4、改造、泰国3、巴西-2、阿根廷、德国西班牙、商贸1/2/3/4）→「模块明细」暂无数据。
- 台账 229 国中 215 国有有效映射；14 国（乌干达、美国、意大利、加纳、阿富汗…）D/E 为 `0`/`#N/A`，进未匹配清单。
- 模主空白的模块（10 个）：东欧、乌克兰、商贸4、巴西-2、新西、智利、秘鲁-1、配件3、配件4、阿根廷。
