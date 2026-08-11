# 数据表格列组显隐控制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 4 toggle buttons each hide a specific stage's "额+海外差额" columns. 台数和合计列始终固定显示。Excel 导出同步隐藏。

**Architecture:** `TwoYearTable.vue` manages local `hiddenKeys` state (Set of hidden metric IDs) with toggle buttons, exposes via `defineExpose`. `TwoYearComparison.vue` reads exposed state via template ref when exporting, passes hidden IDs as query params. Backend filters `metric_groups`.

**Tech Stack:** Vue 3, Python Flask, openpyxl

---

## Column Toggle Mapping

```
签订台数 ┊ 签订额 ┊ 海外差额 ┊ 签订额合计    ← 按钮1: 签订额/差额
  ✅      ┊   🔘   ┊   🔘    ┊   ✅

排产台数 ┊ 排产额 ┊ 排产海外差额 ┊ 排产额合计  ← 按钮2: 排产额/差额
  ✅      ┊   🔘   ┊     🔘    ┊   ✅

发货台数 ┊ 发货额 ┊ 发货海外差额 ┊ 发货额合计  ← 按钮3: 发货额/差额
  ✅      ┊   🔘   ┊     🔘    ┊   ✅

回款     ┊ 海外回款及其他 ┊ 回款额            ← 按钮4: 回款/海外回款
  🔘      ┊      🔘       ┊   ✅
```

```js
const TOGGLE_GROUPS = [
  { id: 'sign',    label: '签订额/差额',   keys: ['sign_amount', 'overseas_diff'] },
  { id: 'schedule', label: '排产额/差额',  keys: ['schedule_amount', 'schedule_overseas_diff'] },
  { id: 'ship',    label: '发货额/差额',  keys: ['ship_amount', 'ship_overseas_diff'] },
  { id: 'payment', label: '回款/海外回款', keys: ['payment', 'overseas_payment'] },
]
```

Each button toggles exactly the listed metric IDs. **台数、合计列始终固定显示，不受任何按钮影响。**

---

### Task 1: Add toggle buttons to TwoYearTable.vue

**Files:**
- Modify: `frontend/src/components/ContractCompletion/TwoYearTable.vue`

- [ ] **Step 1: Add hiddenKeys state and toggle logic**

In `<script setup>`, add after the `props` block. Check if `ref`/`computed` are already imported from Vue — if not, add them:

```js
import { ref, computed } from 'vue'
```

Then add:

```js
// ── Column toggle ──
// Each toggle group hides specific metric IDs (amount + overseas_diff).
// 台数 and 合计 columns always stay visible.

const TOGGLE_GROUPS = [
  { id: 'sign',    label: '签订额/差额',   keys: ['sign_amount', 'overseas_diff'] },
  { id: 'schedule', label: '排产额/差额',  keys: ['schedule_amount', 'schedule_overseas_diff'] },
  { id: 'ship',    label: '发货额/差额',  keys: ['ship_amount', 'ship_overseas_diff'] },
  { id: 'payment', label: '回款/海外回款', keys: ['payment', 'overseas_payment'] },
]

// Set of metric IDs currently hidden
const hiddenKeys = ref(new Set())

function toggleKeys(groupKeys) {
  const s = new Set(hiddenKeys.value)
  // If ALL keys in this group are already hidden → show them
  // Otherwise → hide them all
  const allHidden = groupKeys.every(k => s.has(k))
  if (allHidden) {
    for (const k of groupKeys) s.delete(k)
  } else {
    for (const k of groupKeys) s.add(k)
  }
  hiddenKeys.value = s
}

function isGroupHidden(groupKeys) {
  return groupKeys.every(k => hiddenKeys.value.has(k))
}

// Filtered metric groups — exclude hidden metric IDs
const visibleMetricGroups = computed(() => {
  return props.metricGroups.filter(g => !hiddenKeys.value.has(g.id))
})

// Expose hiddenKeys so parent can read it for export
defineExpose({ hiddenKeys })
```

- [ ] **Step 2: Add toggle buttons above the table**

After the opening `<div class="table-wrap" v-loading="loading">` and before `<div class="table-scroll">`, add:

```html
<!-- Column toggle buttons -->
<div class="col-toggle-bar" v-if="metricGroups.length">
  <span class="col-toggle-label">列组：</span>
  <button
    v-for="tg in TOGGLE_GROUPS"
    :key="tg.id"
    class="col-toggle-btn"
    :class="{ 'col-toggle-btn--hidden': isGroupHidden(tg.keys) }"
    @click="toggleKeys(tg.keys)"
  >
    {{ isGroupHidden(tg.keys) ? '👁‍🗨' : '👁' }} {{ tg.label }}
  </button>
</div>
```

- [ ] **Step 3: Replace all `metricGroups` with `visibleMetricGroups` in table template**

In the `<thead>`, replace:
- `v-for="g in metricGroups"` → `v-for="g in visibleMetricGroups"` (both rows)

In the `<tbody>`, replace:
- `v-for="g in metricGroups"` → `v-for="g in visibleMetricGroups"`

- [ ] **Step 4: Add CSS**

```css
.col-toggle-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.col-toggle-label {
  font-size: 11px;
  color: #888;
  margin-right: 2px;
}
.col-toggle-btn {
  padding: 4px 10px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #fafbfc;
  font-size: 11px;
  cursor: pointer;
  transition: all .2s;
  color: #555;
}
.col-toggle-btn:hover {
  border-color: #3b82f6;
  color: #3b82f6;
}
.col-toggle-btn--hidden {
  background: #fef2f2;
  border-color: #fecaca;
  color: #dc2626;
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ContractCompletion/TwoYearTable.vue
git commit -m "feat: add toggle buttons to hide 额/差额 columns per stage in TwoYearTable"
```

---

### Task 2: Sync hidden columns to Excel export

**Files:**
- Modify: `frontend/src/views/TwoYearComparison.vue`
- Modify: `backend/dashboards/contract_completion/services.py`
- Modify: `backend/dashboards/contract_completion/blueprint.py`

- [ ] **Step 1: Update TwoYearComparison.vue — read hiddenKeys, pass to export URL**

Add `ref` on TwoYearTable:

```html
<TwoYearTable
  ref="tableRef"
  :rows="filteredRows"
  :metricGroups="metricGroups"
  :yearPrev="yearPrev"
  :yearCurr="yearCurr"
  :loading="loading"
/>
```

Add `tableRef` in script and update `exportExcel`:

```js
const tableRef = ref(null)

function exportExcel() {
  const token = localStorage.getItem('token')
  let url = '/api/contract-completion/two-year-comparison/export'

  // Pass hidden metric IDs to backend
  if (tableRef.value && tableRef.value.hiddenKeys) {
    const hidden = [...tableRef.value.hiddenKeys]
    if (hidden.length) {
      url += '?' + hidden.map(k => 'hidden=' + encodeURIComponent(k)).join('&')
    }
  }

  fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    .then(res => res.blob())
    .then(blob => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = '两年对比表.xlsx'
      a.click()
      URL.revokeObjectURL(a.href)
    })
    .catch(() => ElMessage.error('导出失败'))
}
```

- [ ] **Step 2: Update backend export to accept hidden metric IDs**

Modify `export_two_year_comparison_xlsx()` signature and add filter logic at the top:

```python
def export_two_year_comparison_xlsx(hidden_metric_ids=None):
    """..."""
    # ... existing imports ...
    
    data = get_two_year_comparison()
    rows = data['rows']
    groups = data['metric_groups']
    year_prev = data['year_prev']
    year_curr = data['year_curr']
    
    # Filter out hidden metric columns
    if hidden_metric_ids:
        hidden_set = set(hidden_metric_ids)
        groups = [g for g in groups if g['id'] not in hidden_set]
    
    # ... rest unchanged ...
```

- [ ] **Step 3: Update backend blueprint to accept query param**

```python
@cc_bp.route('/api/contract-completion/two-year-comparison/export', methods=['GET'])
@jwt_required()
def api_export_two_year():
    """导出两年对比表Excel，支持 ?hidden=sign_amount&hidden=overseas_diff"""
    try:
        hidden = request.args.getlist('hidden') or None
        filepath = export_two_year_comparison_xlsx(hidden_metric_ids=hidden)
        return send_file(filepath, as_attachment=True,
                         download_name='两年对比表.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        return jsonify(code=500, msg=str(e), data=None), 500
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/TwoYearComparison.vue backend/dashboards/contract_completion/services.py backend/dashboards/contract_completion/blueprint.py
git commit -m "feat: sync hidden columns to Excel export via query params"
```

---

### Task 3: Build and verify

- [ ] **Step 1: Build frontend**

```bash
cd frontend && npx vite build 2>&1 | tail -5
```
Expected: Build succeeds.

- [ ] **Step 2: Verify Python syntax**

```bash
python -c "import ast; ast.parse(open('backend/dashboards/contract_completion/services.py', encoding='utf-8').read()); print('OK')"
python -c "import ast; ast.parse(open('backend/dashboards/contract_completion/blueprint.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 3: Visual check**

- [ ] 4 toggle buttons above table: 签订额/差额、排产额/差额、发货额/差额、回款/海外回款
- [ ] 台数列始终可见
- [ ] 合计列始终可见
- [ ] 点击按钮 → 对应额+差额列隐藏，按钮变红
- [ ] 导出 Excel → 隐藏列不出现

- [ ] **Step 4: Commit fixes if needed**
