# 商贸数据集成 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 `商贸数据.xlsx` 读取商贸1/2/3的签订额/回款额/排产额/发货额，注入两年对比表。

**Architecture:** 新建 `TradeModuleData` 模型存储汇总数据（万元→元转换），新建 `parse_trade_data` handler 解析Excel并全量替换，在 `get_two_year_comparison()` 中读取模型数据注入商贸行。

**Tech Stack:** Flask + SQLAlchemy + openpyxl

---

### Task 1: 新建 TradeModuleData 模型

**Files:**
- Modify: `backend/dashboards/contract_completion/models.py`

- [ ] **Step 1: 在 AnnualTarget 前插入 TradeModuleData 模型**

打开 `backend/dashboards/contract_completion/models.py`，在 `class AnnualTarget(db.Model):` 前面插入：

```python
class TradeModuleData(db.Model):
    """商贸模块汇总数据 — 从商贸数据.xlsx上传（全量替换当前年份）"""
    __tablename__ = 'cc_trade_module_data'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    data_year = db.Column(db.Integer, index=True, default=2026)           # 数据年份
    module_name = db.Column(db.String(50))                                 # 模块名（商贸1/商贸2/商贸3）
    sign_amount = db.Column(db.Float, default=0.0)                        # 签订额（元）
    payment_amount = db.Column(db.Float, default=0.0)                     # 回款额（元）
    schedule_amount = db.Column(db.Float, default=0.0)                    # 排产额（元）
    ship_amount = db.Column(db.Float, default=0.0)                        # 发货额（元）
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {c.name: getattr(self, c.name)
                for c in self.__table__.columns
                if c.name not in ('id',)}
```

---

### Task 2: 新建 parse_trade_data Handler

**Files:**
- Modify: `backend/dashboards/contract_completion/handlers.py`

- [ ] **Step 1: 在 handler 文件末尾添加 parse_trade_data 函数**

在 `handlers.py` 末尾（最后一个 `parse_report_b` 函数之后）添加：

```python
# ── Handler 6: 商贸模块汇总数据 ─────────────────────────

def parse_trade_data(file_path: str) -> dict:
    """解析商贸数据.xlsx → cc_trade_module_data（全量替换当前年份）
    
    Excel结构（Sheet1）:
      A=模块, B=签订额(万元), C=回款额(万元), D=排产额(万元), E=发货额(万元)
    """
    from dashboards.contract_completion.models import TradeModuleData

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active  # Sheet1

        # 读取表头（行1）
        headers = {}
        for c in range(1, ws.max_column + 1):
            v = _safe_str(ws.cell(row=1, column=c).value)
            if v:
                headers[c] = v

        # 按表头名定位列
        col_map = {}
        for c, name in headers.items():
            # 匹配: 模块, 签订额, 回款额, 排产额, 发货额
            if '模块' in name:
                col_map['module'] = c
            elif '签订' in name:
                col_map['sign'] = c
            elif '回款' in name:
                col_map['payment'] = c
            elif '排产' in name:
                col_map['schedule'] = c
            elif '发货' in name:
                col_map['ship'] = c

        data_year = 2026  # 商贸数据为2026年

        # 清空当前年份旧数据
        TradeModuleData.query.filter_by(data_year=data_year).delete()
        db.session.commit()

        total = 0
        for r in range(2, ws.max_row + 1):
            module_name = _safe_str(ws.cell(row=r, column=col_map.get('module', 1)).value)
            if not module_name:
                continue
            # 只处理商贸模块
            if '商贸' not in module_name:
                continue

            def _get(col_key):
                c = col_map.get(col_key)
                return _safe_float(ws.cell(row=r, column=c).value) if c else 0.0

            # Excel值(万元) × 10000 → 元（与台账数据单位一致）
            td = TradeModuleData(
                data_year=data_year,
                module_name=module_name,
                sign_amount=_get('sign') * 10000,
                payment_amount=_get('payment') * 10000,
                schedule_amount=_get('schedule') * 10000,
                ship_amount=_get('ship') * 10000,
            )
            db.session.add(td)
            total += 1

        db.session.commit()
        wb.close()
        return {"success": True, "message": f"商贸数据导入 {total} 条", "rows": total}

    except Exception as e:
        db.session.rollback()
        return {"success": False, "message": f"商贸数据解析失败: {str(e)}", "rows": 0}
```

---

### Task 3: 注册 contract_trade_data 上传映射

**Files:**
- Modify: `backend/upload/handlers.py`

- [ ] **Step 1: 添加 import**

在文件顶部的 import 块中添加 `parse_trade_data`：

```python
from dashboards.contract_completion.handlers import (
    parse_ledger_contracts,
    parse_country_mapping,
    parse_payment_collections,
    parse_report_a,
    parse_report_b,
    parse_trade_data,          # 新增
)
```

- [ ] **Step 2: 注册 handler 映射**

在 `HANDLERS` 字典中添加：

```python
HANDLERS = {
    # 合同完成情况表
    "contract_ledger":      parse_ledger_contracts,
    "contract_mapping":     parse_country_mapping,
    "contract_payment":     parse_payment_collections,
    "contract_report_a":    parse_report_a,
    "contract_report_b":    parse_report_b,
    "contract_trade_data":  parse_trade_data,        # 新增：商贸模块汇总
}
```

---

### Task 4: 注入商贸数据到两年对比表

**Files:**
- Modify: `backend/dashboards/contract_completion/services.py`

- [ ] **Step 1: 在 get_two_year_comparison() 的商贸行构建前注入数据**

找到 services.py 中这段代码（约L934-943，`# ── 商贸行 ──` 注释处）：

```python
    # ── 商贸行 ──
    trade_total = {}
    for tmod in TRADE_MODULES_ORDER:
        d = agg.get(('商贸合计', tmod))
```

在其前面插入：

```python
    # ── 注入商贸模块汇总数据（从商贸数据.xlsx上传） ──
    from dashboards.contract_completion.models import TradeModuleData
    trade_data_list = TradeModuleData.query.filter_by(data_year=year_curr).all()
    for td in trade_data_list:
        tmod = td.module_name
        if tmod in TRADE_MODULES_ORDER:
            d = _ensure('商贸合计', tmod)
            # 模型值已是元，直接注入 curr（prev 保持 0，无历史数据）
            d['sign_amount_curr'] = td.sign_amount
            d['schedule_amount_curr'] = td.schedule_amount
            d['ship_amount_curr'] = td.ship_amount
            d['payment_curr'] = td.payment_amount

    # ── 商贸行 ──
```

---

### Task 5: 添加权限到种子数据

**Files:**
- Modify: `backend/seed.py`

- [ ] **Step 1: 在 admin_permissions 列表中添加权限**

找到 `admin_permissions` 列表，在 `'upload_contract_report_b'` 后添加：

```python
'upload_contract_report_b',
'upload_contract_trade_data',   # 新增：商贸模块汇总数据上传
```

---

### Task 6: 验证数据库表自动创建

**Files:**
- Verify: `backend/seed.py` 中的 `db.create_all()` 会自-动创建新表

- [ ] **Step 1: 确认 seed_database 已有 db.create_all()**

查看 `seed.py` L14 已有 `db.create_all()`，新模型会自动建表，无需额外操作。

---

### Task 7: 上传配置（手动操作）

**Files:**
- 无代码改动，需在管理后台手动创建

- [ ] **Step 1: 登录管理后台**

访问 上传配置管理页面，在"合同完成情况表"父级下新建子配置：

- 名称: 商贸模块汇总
- code: `contract_trade_data`
- 权限: `upload_contract_trade_data`
- 文件类型: `.xlsx,.xls`

---

### Task 8: 端到端验证

- [ ] **Step 1: 重启后端服务**

```bash
cd backend && python app.py
```

- [ ] **Step 2: 上传商贸数据.xlsx**

通过上传控制台上传 `商贸数据.xlsx`，确认返回 "商贸数据导入 3 条"

- [ ] **Step 3: 验证两年对比表**

打开 两年对比页面，确认商贸1/2/3行显示正确的2026年数据（整数万元），2025年列显示 "-"

- [ ] **Step 4: 验证Excel导出**

点击导出Excel，确认商贸行数据正确
