"""
合同完成情况表 — 业务逻辑服务层

指标计算、数据聚合、未匹配检测
"""
import os
from datetime import date, datetime
from flask import current_app
from sqlalchemy import or_
from models import db
from dashboards.contract_completion.models import (
    LedgerContract, CountryMapping, PaymentCollection, AnnualTarget
)

# ── 缓存 ──────────────────────────────────────────────────

_two_year_cache = None          # 两年对比表缓存结果
_two_year_fingerprint = None    # 缓存时的数据指纹


def _get_data_fingerprint():
    """快速生成数据指纹（轻量 COUNT 查询），用于判断缓存是否失效"""
    from sqlalchemy import or_
    ledger_count = LedgerContract.query.filter(
        LedgerContract.source.in_(['ledger', 'report_a', 'report_b']),
        or_(LedgerContract.product_status == None, LedgerContract.product_status != '已作废')
    ).count()
    mapping_count = CountryMapping.query.count()
    payment_count = PaymentCollection.query.count()
    today_str = date.today().isoformat()
    return f"{ledger_count}|{mapping_count}|{payment_count}|{today_str}"


def invalidate_two_year_cache():
    """手动清除两年对比缓存（数据上传后可由外部调用）"""
    global _two_year_cache, _two_year_fingerprint
    _two_year_cache = None
    _two_year_fingerprint = None


# ── 常量 ──────────────────────────────────────────────────

REGION_ORDER = ['俄罗斯', '中亚', '亚洲1', '亚洲2', '美洲', '中东', '非洲', '欧洲', '商贸合计']

METRIC_CONFIG = [
    {"id": "sign_units",      "name": "年签单台",   "unit": "台",   "type": "count"},
    {"id": "sign_amount",     "name": "年签单额",   "unit": "万元", "type": "amount"},
    {"id": "payment_amount",  "name": "回款",       "unit": "万元", "type": "amount"},
    {"id": "ship_units",      "name": "发货台",     "unit": "台",   "type": "count"},
    {"id": "ship_amount",     "name": "发货额",     "unit": "万元", "type": "amount"},
    {"id": "schedule_units",  "name": "排产台",     "unit": "台",   "type": "count"},
    {"id": "schedule_amount", "name": "排产额",     "unit": "万元", "type": "amount"},
]

RATIO_CONFIG = {
    "sign_units":      "sign_units",
    "sign_amount":     "sign_amount",
    "payment_amount":  "payment_amount",
    "ship_units":      "ship_units",
    "ship_amount":     "ship_amount",
    "schedule_units":  "schedule_units",
    "schedule_amount": "schedule_amount",
}

TRADE_MODULES = ['商贸1', '商贸2', '商贸3', '配件-1', '配件-2', '改造']


# ── 工具函数 ──────────────────────────────────────────────

def _to_wan(val):
    """元 → 万元（保留2位小数）"""
    if val is None:
        return 0.0
    return round(float(val) / 10000, 2)


def _safe_ratio(numerator, denominator):
    """安全除法"""
    if not denominator or abs(denominator) < 0.001:
        return 0.0 if (not numerator or abs(numerator) < 0.001) else 1.0
    return round(float(numerator) / float(denominator), 4)


def _load_mapping():
    """加载国家映射表 → {country: {region, module, manager, salesperson}}"""
    mappings = CountryMapping.query.all()
    return {m.country: {
        'region': m.region, 'module': m.module_name,
        'manager': m.module_manager, 'salesperson': m.salesperson,
    } for m in mappings}


def _load_targets(year, region_only=True):
    """加载年度指标 → {(region, module, metric): value}"""
    query = AnnualTarget.query.filter_by(target_year=year)
    if region_only:
        query = query.filter(AnnualTarget.module_name == '')
    targets = query.all()
    result = {}
    for t in targets:
        key = (t.region, t.module_name, t.metric_key)
        result[key] = t.target_value
    return result


def _resolve_contract(c, mapping, unmatched_list):
    """解析合同 → (region, module, manager, salesperson) 或加入unmatched"""
    # 商贸来源的行已经有 mapped_region 和 mapped_module
    if c.source in ('report_a', 'report_b'):
        return (c.mapped_region or '商贸合计', c.mapped_module or '',
                '', '')

    country = c.country
    if not country:
        unmatched_list.append({'contract_no': c.contract_no, 'country': '(空)',
                               'project_name': c.project_name or ''})
        return None

    cm = mapping.get(country)
    if cm is None:
        unmatched_list.append({'contract_no': c.contract_no, 'country': country,
                               'project_name': c.project_name or ''})
        return None

    region = cm['region']
    module = cm['module']
    # 产品型号含"改造" → 强制模块="改造"
    if c.product_type and '改造' in str(c.product_type):
        module = '改造'
        region = '商贸合计'

    return (region, module, cm['manager'], cm['salesperson'])


# ── 核心计算 ──────────────────────────────────────────────

def _compute_aggregations(year, mapping, unmatched_list):
    """
    遍历台账合同，按大区和模块聚合指标。
    返回: (region_data, module_data, salesperson_data)
    """
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    # region_data: {region: {metric_key: value}}
    region_data = {}
    # module_data: {(region, module_name): {metrics...}}
    module_data = {}
    # sp_data: {salesperson: {metrics...}}
    sp_data = {}

    def _init_metrics():
        return {m['id']: 0.0 for m in METRIC_CONFIG}

    contracts = LedgerContract.query.filter(
        or_(LedgerContract.product_status == None, LedgerContract.product_status != '已作废')
    ).all()

    for c in contracts:
        resolved = _resolve_contract(c, mapping, unmatched_list)
        if resolved is None:
            continue
        region, module, manager, sp = resolved

        # 初始化
        if region not in region_data:
            region_data[region] = _init_metrics()
        mod_key = (region, module)
        if mod_key not in module_data:
            module_data[mod_key] = {
                'region': region, 'module': module, 'manager': manager,
                'prev_schedule_not_shipped': 0, **_init_metrics(),
            }

        # 大区级累加
        rd = region_data[region]
        md = module_data[mod_key]

        # 签单：按签订日期
        if c.sign_date and year_start <= c.sign_date <= year_end:
            rd['sign_units'] += c.unit_count or 0
            rd['sign_amount'] += c.contract_amount_rmb or 0
            md['sign_units'] += c.unit_count or 0
            md['sign_amount'] += c.contract_amount_rmb or 0

        # 排产：按排产日期
        if c.schedule_date and year_start <= c.schedule_date <= year_end:
            rd['schedule_units'] += c.unit_count or 0
            rd['schedule_amount'] += c.contract_amount_rmb or 0
            md['schedule_units'] += c.unit_count or 0
            md['schedule_amount'] += c.contract_amount_rmb or 0

        # 发货：按发货日期
        if c.delivery_date and year_start <= c.delivery_date <= year_end:
            rd['ship_units'] += c.unit_count or 0
            rd['ship_amount'] += c.contract_amount_rmb or 0
            md['ship_units'] += c.unit_count or 0
            md['ship_amount'] += c.contract_amount_rmb or 0

        # 2021年前排产未发货（排产<2022 且 未发货）
        if c.schedule_date and c.schedule_date < date(2022, 1, 1):
            if not c.delivery_date or c.delivery_date > date.today():
                md['prev_schedule_not_shipped'] += c.unit_count or 0

        # 业务员维度
        if sp:
            if sp not in sp_data:
                sp_data[sp] = {
                    'salesperson': sp, 'region': region, 'module': module,
                    **_init_metrics(),
                    'prev_sign_units': 0, 'prev_sign_amount': 0,
                    'prev_ship_units': 0, 'prev_ship_amount': 0,
                    'prev_schedule_units': 0, 'prev_schedule_amount': 0,
                    'prev_payment_amount': 0,
                }
            sd = sp_data[sp]
            if c.sign_date and year_start <= c.sign_date <= year_end:
                sd['sign_units'] += c.unit_count or 0
                sd['sign_amount'] += c.contract_amount_rmb or 0
            if c.schedule_date and year_start <= c.schedule_date <= year_end:
                sd['schedule_units'] += c.unit_count or 0
                sd['schedule_amount'] += c.contract_amount_rmb or 0
            if c.delivery_date and year_start <= c.delivery_date <= year_end:
                sd['ship_units'] += c.unit_count or 0
                sd['ship_amount'] += c.contract_amount_rmb or 0
            # 去年同期：上年数据
            prev_year_start = date(year - 1, 1, 1)
            prev_year_end = date(year - 1, 12, 31)
            if c.sign_date and prev_year_start <= c.sign_date <= prev_year_end:
                sd['prev_sign_units'] += c.unit_count or 0
                sd['prev_sign_amount'] += c.contract_amount_rmb or 0
            if c.schedule_date and prev_year_start <= c.schedule_date <= prev_year_end:
                sd['prev_schedule_units'] += c.unit_count or 0
                sd['prev_schedule_amount'] += c.contract_amount_rmb or 0
            if c.delivery_date and prev_year_start <= c.delivery_date <= prev_year_end:
                sd['prev_ship_units'] += c.unit_count or 0
                sd['prev_ship_amount'] += c.contract_amount_rmb or 0

    # 回款聚合：回款通过合同号匹配台账 → 映射 → 大区/模块
    payments = PaymentCollection.query.filter(
        PaymentCollection.payment_date >= year_start,
        PaymentCollection.payment_date <= year_end,
    ).all()

    # 建立合同号→(region,module,sp)的快速查找
    contract_lookup = {}
    for c in contracts:
        if c.contract_no and c.contract_no not in contract_lookup:
            cm = mapping.get(c.country) if c.country else None
            if cm:
                contract_lookup[c.contract_no] = (cm['region'], cm['module'], cm['salesperson'])
            elif c.mapped_region:
                contract_lookup[c.contract_no] = (c.mapped_region, c.mapped_module or '', '')

    for p in payments:
        info = contract_lookup.get(p.contract_no)
        if not info:
            continue
        pregion, pmodule, psp = info
        amt = p.payment_amount_rmb or 0

        if pregion not in region_data:
            region_data[pregion] = _init_metrics()
        region_data[pregion]['payment_amount'] += amt

        mod_key = (pregion, pmodule)
        if mod_key in module_data:
            module_data[mod_key]['payment_amount'] += amt

        if psp and psp in sp_data:
            sp_data[psp]['payment_amount'] += amt
            # 去年同期回款
            if p.payment_date and date(year-1,1,1) <= p.payment_date <= date(year-1,12,31):
                sp_data[psp]['prev_payment_amount'] += amt

    return region_data, module_data, sp_data


# ── 输出构建函数 ───────────────────────────────────────────

def _build_region_summary(region_data, targets, year):
    """构建大区汇总数据"""
    result = []
    grand = {m['id']: {'target': 0.0, 'actual': 0.0} for m in METRIC_CONFIG}

    for region in REGION_ORDER:
        rd = region_data.get(region, {})
        entry = {'region': region, 'metrics': {}}
        for m in METRIC_CONFIG:
            mk = m['id']
            t_val = targets.get((region, '', mk), 0)
            a_val = rd.get(mk, 0)
            if m['type'] == 'amount':
                t_val = _to_wan(t_val)
                a_val = _to_wan(a_val)
            else:
                t_val = round(t_val, 0)
                a_val = round(a_val, 0)
            ratio = _safe_ratio(a_val, t_val)
            entry['metrics'][mk] = {'target': t_val, 'actual': a_val, 'ratio': ratio}
            grand[mk]['target'] += t_val
            grand[mk]['actual'] += a_val
        result.append(entry)

    grand_row = {'region': '合计', 'metrics': {}, 'is_total': True}
    for m in METRIC_CONFIG:
        mk = m['id']
        g = grand[mk]
        grand_row['metrics'][mk] = {
            'target': round(g['target'], 2),
            'actual': round(g['actual'], 2),
            'ratio': _safe_ratio(g['actual'], g['target']),
        }

    return result, grand_row


def _build_module_detail(module_data, targets, region_filter):
    """构建模块明细数据（按大区分组，含小计行）"""
    result = []
    current_region = None
    subtotal = {m['id']: {'target': 0.0, 'actual': 0.0} for m in METRIC_CONFIG}
    prev_shipped_total = 0

    # 按大区顺序 + 模块名排序
    sorted_modules = sorted(module_data.values(), key=lambda x: (
        REGION_ORDER.index(x['region']) if x['region'] in REGION_ORDER else 99,
        x['module']
    ))

    for md in sorted_modules:
        if region_filter and md['region'] != region_filter:
            continue

        if md['region'] != current_region:
            # 输出上一大区小计
            if current_region:
                st_entry = {
                    'type': 'subtotal', 'row_type': 'subtotal',
                    'region': current_region, 'module_name': f'{current_region}合计',
                    'metrics': {}, 'prev_schedule_not_shipped': prev_shipped_total,
                }
                for m in METRIC_CONFIG:
                    mk = m['id']
                    st = subtotal[mk]
                    st_entry['metrics'][mk] = {
                        'target': round(st['target'], 2),
                        'actual': round(st['actual'], 2),
                        'ratio': _safe_ratio(st['actual'], st['target']),
                    }
                result.append(st_entry)

            current_region = md['region']
            subtotal = {m['id']: {'target': 0.0, 'actual': 0.0} for m in METRIC_CONFIG}
            prev_shipped_total = 0

        tk = {(md['region'], md['module'], mk): targets.get((md['region'], md['module'], mk), 0)
              for mk in [m['id'] for m in METRIC_CONFIG]}

        entry = {
            'type': 'module', 'row_type': 'data',
            'region': md['region'], 'module_name': md['module'],
            'module_manager': md.get('manager', ''),
            'prev_schedule_not_shipped': md.get('prev_schedule_not_shipped', 0),
            'metrics': {},
        }
        for m in METRIC_CONFIG:
            mk = m['id']
            t_val = targets.get((md['region'], md['module'], mk), 0)
            a_val = md.get(mk, 0)
            if m['type'] == 'amount':
                t_val = _to_wan(t_val)
                a_val = _to_wan(a_val)
            else:
                t_val = round(t_val, 0)
                a_val = round(a_val, 0)
            ratio = _safe_ratio(a_val, t_val)
            entry['metrics'][mk] = {'target': t_val, 'actual': a_val, 'ratio': ratio}
            subtotal[mk]['target'] += t_val
            subtotal[mk]['actual'] += a_val
        prev_shipped_total += md.get('prev_schedule_not_shipped', 0)
        result.append(entry)

    # 最后一个大区的小计
    if current_region:
        st_entry = {
            'type': 'subtotal', 'row_type': 'subtotal',
            'region': current_region, 'module_name': f'{current_region}合计',
            'metrics': {}, 'prev_schedule_not_shipped': prev_shipped_total,
        }
        for m in METRIC_CONFIG:
            mk = m['id']
            st = subtotal[mk]
            st_entry['metrics'][mk] = {
                'target': round(st['target'], 2),
                'actual': round(st['actual'], 2),
                'ratio': _safe_ratio(st['actual'], st['target']),
            }
        result.append(st_entry)

    return result


def _build_salesperson_data(sp_data, region_filter):
    """构建业务员表数据"""
    result = []
    for name, sd in sorted(sp_data.items()):
        if region_filter and sd.get('region') != region_filter:
            continue

        entry = {
            'salesperson': name,
            'module': sd.get('module', ''),
            'region': sd.get('region', ''),
            'metrics_prev': {},   # 去年同期
            'metrics_curr': {},   # 今年
            'yoy_change': {},     # 同比增减%
        }

        metric_pairs = [
            ('sign_units', 'sign_units', 'count'),
            ('sign_amount', 'sign_amount', 'amount'),
            ('schedule_units', 'schedule_units', 'count'),
            ('schedule_amount', 'schedule_amount', 'amount'),
            ('ship_units', 'ship_units', 'count'),
            ('ship_amount', 'ship_amount', 'amount'),
            ('payment_amount', 'prev_payment_amount', 'amount'),
        ]

        for mk, prev_key, mtype in metric_pairs:
            v_prev = sd.get(f'prev_{mk}', 0)
            v_curr = sd.get(mk, 0)
            if mtype == 'amount':
                v_prev = _to_wan(v_prev)
                v_curr = _to_wan(v_curr)
            else:
                v_prev = round(v_prev, 0)
                v_curr = round(v_curr, 0)
            change = round((v_curr - v_prev) / v_prev * 100, 1) if v_prev != 0 else (0 if v_curr == 0 else 100)

            entry['metrics_prev'][mk] = v_prev
            entry['metrics_curr'][mk] = v_curr
            entry['yoy_change'][mk] = change

        result.append(entry)
    return result


def _write_unmatched_file(unmatched_list):
    """输出未匹配合同TXT"""
    uploads_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'uploads'
    )
    os.makedirs(uploads_dir, exist_ok=True)
    filepath = os.path.join(uploads_dir, 'unmatched_contracts.txt')

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [f"未匹配合同清单 - 生成时间: {timestamp}"]
    lines.append(f"{'合同号':<25} {'国家':<20} {'项目名称'}")
    lines.append("-" * 80)

    # 去重
    seen = set()
    for item in unmatched_list:
        key = item['contract_no']
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{item['contract_no']:<25} {item['country']:<20} {item['project_name']}")

    lines.append("-" * 80)
    lines.append(f"共 {len(seen)} 条未匹配记录")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return filepath, len(seen)


# ── 公开API ───────────────────────────────────────────────

def get_region_summary(year=2026, region_filter=None):
    """大区汇总 (Sheet 1)"""
    mapping = _load_mapping()
    targets = _load_targets(year, region_only=True)
    unmatched = []
    region_data, _, _ = _compute_aggregations(year, mapping, unmatched)
    regions, grand = _build_region_summary(region_data, targets, year)

    if region_filter:
        regions = [r for r in regions if r['region'] == region_filter]

    return {
        'year': year,
        'regions': regions,
        'grand_total': grand,
        'metric_config': METRIC_CONFIG,
        'region_order': REGION_ORDER,
        'unmatched_count': len(unmatched),
    }


def get_module_detail(year=2026, region_filter=None):
    """模块明细 (Sheet 2)"""
    mapping = _load_mapping()
    targets = _load_targets(year, region_only=False)
    unmatched = []
    _, module_data, _ = _compute_aggregations(year, mapping, unmatched)
    modules = _build_module_detail(module_data, targets, region_filter)

    return {
        'year': year,
        'modules': modules,
        'metric_config': METRIC_CONFIG,
        'region_order': REGION_ORDER,
        'unmatched_count': len(unmatched),
    }


def get_salesperson_comparison(year=2026, region_filter=None):
    """业务员表 (Sheet 3)"""
    mapping = _load_mapping()
    unmatched = []
    _, _, sp_data = _compute_aggregations(year, mapping, unmatched)
    salespersons = _build_salesperson_data(sp_data, region_filter)

    return {
        'year': year,
        'salespersons': salespersons,
        'unmatched_count': len(unmatched),
    }


def get_data_status():
    """数据状态"""
    from models import FileUpload, UploadConfig

    counts = {
        'ledger_count': LedgerContract.query.filter(or_(LedgerContract.product_status == None, LedgerContract.product_status != '已作废')).count(),
        'mapping_count': CountryMapping.query.count(),
        'payment_count': PaymentCollection.query.count(),
    }

    def _last_upload(code):
        cfg = UploadConfig.query.filter_by(code=code).first()
        if not cfg:
            return None
        fu = FileUpload.query.filter_by(upload_config_id=cfg.id)\
            .order_by(FileUpload.uploaded_at.desc()).first()
        return fu.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if fu else None

    # 触发未匹配检测（排除已作废）
    mapping = _load_mapping()
    contracts = LedgerContract.query.filter(
        LedgerContract.source == 'ledger',
        or_(LedgerContract.product_status == None, LedgerContract.product_status != '已作废')
    ).all()
    unmatched = []
    seen = set()
    for c in contracts:
        if not c.country:
            unmatched.append({'contract_no': c.contract_no, 'country': '(空)',
                              'project_name': c.project_name or ''})
        elif c.country not in mapping:
            key = c.contract_no
            if key not in seen:
                seen.add(key)
                unmatched.append({'contract_no': c.contract_no, 'country': c.country,
                                  'project_name': c.project_name or ''})

    # 写文件
    filepath, ucount = _write_unmatched_file(unmatched) if unmatched else (None, 0)

    return {
        **counts,
        'last_ledger_upload': _last_upload('contract_ledger'),
        'last_mapping_upload': _last_upload('contract_mapping'),
        'last_payment_upload': _last_upload('contract_payment'),
        'last_report_a_upload': _last_upload('contract_report_a'),
        'last_report_b_upload': _last_upload('contract_report_b'),
        'unmatched_count': ucount,
        'unmatched_file': '/uploads/unmatched_contracts.txt' if filepath else None,
    }


def get_unmatched_contracts():
    """返回未匹配合同列表（排除已作废）"""
    mapping = _load_mapping()
    contracts = LedgerContract.query.filter(
        LedgerContract.source == 'ledger',
        or_(LedgerContract.product_status == None, LedgerContract.product_status != '已作废')
    ).all()
    unmatched = []
    seen = set()
    for c in contracts:
        if not c.country:
            unmatched.append({'contract_no': c.contract_no, 'country': '(空)',
                              'project_name': c.project_name or ''})
        elif c.country not in mapping:
            key = c.contract_no
            if key not in seen:
                seen.add(key)
                unmatched.append({'contract_no': c.contract_no, 'country': c.country,
                                  'project_name': c.project_name or ''})

    filepath, ucount = _write_unmatched_file(unmatched) if unmatched else (None, 0)
    return {
        'count': ucount,
        'file_url': '/uploads/unmatched_contracts.txt' if filepath else None,
        'items': unmatched[:100],  # 最多返回前100条
    }


def get_regions():
    """可用大区列表"""
    return {'regions': REGION_ORDER}


# ── 两年对比表 (核心新功能) ──────────────────────────────

# 指标组定义（严格按照模板列顺序）
TWO_YEAR_GROUPS = [
    {"id": "sign_units",      "name": "签订台数",       "has_growth": True},
    {"id": "sign_amount",     "name": "签订额\n（万元）","has_growth": True},
    {"id": "overseas_diff",   "name": "海外差额",       "has_growth": False},
    {"id": "sign_total",      "name": "签订额合计",     "has_growth": True},
    {"id": "schedule_units",  "name": "排产台数",       "has_growth": True},
    {"id": "schedule_amount",       "name": "排产额",         "has_growth": True},
    {"id": "schedule_overseas_diff","name": "排产海外差额",   "has_growth": False},
    {"id": "schedule_total",        "name": "排产额合计",     "has_growth": True},
    {"id": "ship_units",            "name": "发货台数",       "has_growth": True},
    {"id": "ship_amount",           "name": "发货额",         "has_growth": True},
    {"id": "ship_overseas_diff",    "name": "发货海外差额",   "has_growth": False},
    {"id": "ship_total",            "name": "发货额合计",     "has_growth": True},
    {"id": "payment",               "name": "回款",           "has_growth": False},
    {"id": "overseas_payment","name": "海外回款及其他", "has_growth": False},
    {"id": "payment_total",   "name": "回款额",         "has_growth": True},
]

# 贸易模块顺序
TRADE_MODULES_ORDER = ['商贸1', '商贸2', '商贸3', '配件-1', '配件-2', '改造']

# 模块→市场类别 映射（匹配映射表实际模块名 → 模板类别）
CATEGORY_MAP = {
    # 俄罗斯（映射表用全角括号）
    '俄罗斯（中部）': 'A', '俄罗斯（西部）': 'A', '俄罗斯（东部）': 'A', '罗斯托夫': 'A', '哈巴': 'A',
    '俄罗斯（中南）': 'B', '俄罗斯（西南）': 'B',
    '莫斯科': 'C', '叶卡': 'C', '新西': 'C',
    # 兼容旧名
    '俄罗斯中央部门': 'A', '俄罗斯新阿尔巴特': 'A', '俄罗斯东部': 'A',
    # 中亚
    '哈萨克斯坦-1': 'A', '塔吉克/哈萨克斯坦-2': 'B', '哈萨克斯坦-3': 'C',
    '乌兹别克斯坦': 'D', '吉尔吉斯斯坦': 'D', '阿塞拜疆': 'C', '格鲁吉亚': 'D', '蒙古': 'C',
    # 亚洲1
    '朝鲜-韩国': 'D', '新加坡市政会': 'A', '新加坡HDB': 'A',
    '泰国': 'D', '泰国2': 'D', '金三角': 'D',
    '马来西亚': 'B', '马尔代夫': 'D', '香港-台湾': 'D',
    # 亚洲2
    '越南-2': 'C', '印度公建': 'B', '巴基斯坦': 'D',
    '孟加拉-1': 'B', '澳大利亚': 'C', '菲律宾': 'C', '菲律宾-2': 'C',
    '印尼-1': 'C', '印尼-2': 'C', '越南-1（工厂）': 'B', '印度私营': 'A',
    # 美洲
    '墨西哥-1': 'A', '墨西哥-2': 'A', '秘鲁': 'C', '智利': 'C',
    '加勒比海': 'A', '多米尼加': 'C', '哥伦比亚': 'A',
    '秘鲁2': 'D', '巴西': 'D',
    # 中东
    '阿联酋-2': 'B', '沙特工厂': 'A', '沙特-1': 'A',
    '科威特': 'C', '阿联酋-1': 'A', '卡塔尔': 'C',
    '伊拉克': 'D', '巴勒斯坦': 'C', '伊朗+阿曼': 'D', '阿联酋3': 'C',
    # 非洲
    '埃及-1': 'A', '埃及-2': 'D', '肯尼亚/坦桑尼亚': 'C',
    '尼日利亚/埃塞俄比亚': 'C', '非洲法语区': 'D', '南非/安格拉': 'D',
    # 欧洲
    '德国西班牙': 'D', '东欧': 'D', '英国意大利': 'D',
    # 商贸
    '商贸1': '', '商贸2': '', '商贸3': '', '配件-1': '', '配件-2': '', '改造': '',
}


def _get_category(module_name):
    """获取模块的市场类别，优先精确匹配，其次模板映射"""
    return CATEGORY_MAP.get(module_name, '')


def get_two_year_comparison():
    """
    两年对比表 — 严格按照模板 Sheet 3 格式
    日期动态计算：当年1月1日~今日，去年1月1日~去年同日
    行结构：以国家映射表为准，按大区→模块分组，含小计行、商贸行、国际总计

    缓存策略：基于数据指纹（表行数+日期），数据未变时直接返回缓存。
    """
    global _two_year_cache, _two_year_fingerprint

    # 检查缓存
    fp = _get_data_fingerprint()
    if _two_year_fingerprint == fp and _two_year_cache is not None:
        return _two_year_cache

    today = date.today()
    year_curr = today.year
    year_prev = today.year - 1

    # 今年范围：1月1日 ~ 6月30日（上半年）
    curr_start = date(year_curr, 1, 1)
    curr_end = date(year_curr, 6, 30)
    # 去年范围：1月1日 ~ 6月30日（上半年）
    prev_start = date(year_prev, 1, 1)
    prev_end = date(year_prev, 6, 30)

    # 加载国家映射表
    mapping = _load_mapping()
    contract_map = {}  # contract_no → (region, module)
    for c in LedgerContract.query.filter(
        LedgerContract.source == 'ledger',
        or_(LedgerContract.product_status == None, LedgerContract.product_status != '已作废')
    ).all():
        if c.contract_no and c.country:
            cm = mapping.get(c.country)
            if cm:
                contract_map[c.contract_no] = (cm['region'], cm['module'])

    # ── 聚合：按 (region, module) 分组 ──
    agg = {}

    def _new_entry(region, module):
        return {
            'region': region, 'module': module,
            'sign_units_prev': 0, 'sign_units_curr': 0,
            'sign_amount_prev': 0.0, 'sign_amount_curr': 0.0,
            'schedule_units_prev': 0, 'schedule_units_curr': 0,
            'schedule_amount_prev': 0.0, 'schedule_amount_curr': 0.0,
            'schedule_overseas_diff_prev': 0.0, 'schedule_overseas_diff_curr': 0.0,
            'ship_units_prev': 0, 'ship_units_curr': 0,
            'ship_amount_prev': 0.0, 'ship_amount_curr': 0.0,
            'ship_overseas_diff_prev': 0.0, 'ship_overseas_diff_curr': 0.0,
            'payment_prev': 0.0, 'payment_curr': 0.0,
        }

    # 预填充：映射表中的所有模块（即使无数据也展示）
    seen_modules = set()
    for cm in mapping.values():
        r, m = cm['region'], cm['module']
        if not r or not m:
            continue
        key = (r, m)
        if key not in seen_modules:
            seen_modules.add(key)
            agg[key] = _new_entry(r, m)
    # 商贸模块也预填充
    for tm in TRADE_MODULES_ORDER:
        key = ('商贸合计', tm)
        if key not in seen_modules:
            seen_modules.add(key)
            agg[key] = _new_entry('商贸合计', tm)

    def _ensure(region, module):
        key = (region, module)
        if key not in agg:
            agg[key] = _new_entry(region, module)
        return agg[key]

    # 遍历台账（排除已作废）
    for c in LedgerContract.query.filter(
        LedgerContract.source.in_(['ledger', 'report_a', 'report_b']),
        or_(LedgerContract.product_status == None, LedgerContract.product_status != '已作废')
    ).all():
        # 确定 region / module
        if c.source in ('report_a', 'report_b'):
            region = c.mapped_region or '商贸合计'
            module = c.mapped_module or ''
        elif c.country and c.country in mapping:
            cm = mapping[c.country]
            region = cm['region']
            module = cm['module']
            # 改造强制归入商贸合计
            if c.product_type and '改造' in str(c.product_type):
                region = '商贸合计'
                module = '改造'
        else:
            continue  # 未匹配的跳过

        if not region or not module:
            continue

        d = _ensure(region, module)

        # 签订
        if c.sign_date:
            if prev_start <= c.sign_date <= prev_end:
                d['sign_units_prev'] += c.unit_count or 0
                d['sign_amount_prev'] += c.contract_amount_rmb or 0
            if curr_start <= c.sign_date <= curr_end:
                d['sign_units_curr'] += c.unit_count or 0
                d['sign_amount_curr'] += c.contract_amount_rmb or 0

        # 排产
        if c.schedule_date:
            if prev_start <= c.schedule_date <= prev_end:
                d['schedule_units_prev'] += c.unit_count or 0
                d['schedule_amount_prev'] += c.contract_amount_rmb or 0
            if curr_start <= c.schedule_date <= curr_end:
                d['schedule_units_curr'] += c.unit_count or 0
                d['schedule_amount_curr'] += c.contract_amount_rmb or 0

        # 发货
        if c.delivery_date:
            if prev_start <= c.delivery_date <= prev_end:
                d['ship_units_prev'] += c.unit_count or 0
                d['ship_amount_prev'] += c.contract_amount_rmb or 0
            if curr_start <= c.delivery_date <= curr_end:
                d['ship_units_curr'] += c.unit_count or 0
                d['ship_amount_curr'] += c.contract_amount_rmb or 0

    # 回款聚合
    payments = PaymentCollection.query.all()
    for p in payments:
        info = contract_map.get(p.contract_no)
        if not info:
            continue
        pregion, pmodule = info
        amt = p.payment_amount_rmb or 0
        d = _ensure(pregion, pmodule)
        if p.payment_date:
            if prev_start <= p.payment_date <= prev_end:
                d['payment_prev'] += amt
            if curr_start <= p.payment_date <= curr_end:
                d['payment_curr'] += amt

    # ── 构建行列表 ──
    rows = []

    # 金额转万元（取整）
    def _wan(v):
        return round(v / 10000)

    def _growth(prev, curr):
        if prev == 0:
            return None  # 显示 '-'
        return round((curr - prev) / prev * 100)  # 整数百分比

    def _make_row(typ, region, module, d):
        cat = _get_category(module) if typ == 'data' else ''
        # sign_total = sign_amount + overseas_diff (海外差额暂为0)
        st_p = _wan(d['sign_amount_prev']) + (0)
        st_c = _wan(d['sign_amount_curr']) + (0)
        # payment_total = payment + overseas_payment (海外回款暂为0)
        pt_p = _wan(d['payment_prev']) + (0)
        pt_c = _wan(d['payment_curr']) + (0)
        return {
            'type': typ,
            'region': region,
            'module': module,
            'category': cat,
            'sign_units_prev': d['sign_units_prev'],
            'sign_units_curr': d['sign_units_curr'],
            'sign_units_growth': _growth(d['sign_units_prev'], d['sign_units_curr']),
            'sign_amount_prev': _wan(d['sign_amount_prev']),
            'sign_amount_curr': _wan(d['sign_amount_curr']),
            'sign_amount_growth': _growth(d['sign_amount_prev'], d['sign_amount_curr']),
            'overseas_diff_prev': None, 'overseas_diff_curr': None,
            'sign_total_prev': st_p,
            'sign_total_curr': st_c,
            'sign_total_growth': _growth(d['sign_amount_prev'], d['sign_amount_curr']),
            'schedule_units_prev': d['schedule_units_prev'],
            'schedule_units_curr': d['schedule_units_curr'],
            'schedule_units_growth': _growth(d['schedule_units_prev'], d['schedule_units_curr']),
            'schedule_amount_prev': _wan(d['schedule_amount_prev']),
            'schedule_amount_curr': _wan(d['schedule_amount_curr']),
            'schedule_amount_growth': _growth(d['schedule_amount_prev'], d['schedule_amount_curr']),
            # 排产海外差额（暂为0）
            'schedule_overseas_diff_prev': None, 'schedule_overseas_diff_curr': None,
            'schedule_total_prev': _wan(d['schedule_amount_prev']) + (0),
            'schedule_total_curr': _wan(d['schedule_amount_curr']) + (0),
            'schedule_total_growth': _growth(d['schedule_amount_prev'], d['schedule_amount_curr']),
            'ship_units_prev': d['ship_units_prev'],
            'ship_units_curr': d['ship_units_curr'],
            'ship_units_growth': _growth(d['ship_units_prev'], d['ship_units_curr']),
            'ship_amount_prev': _wan(d['ship_amount_prev']),
            'ship_amount_curr': _wan(d['ship_amount_curr']),
            'ship_amount_growth': _growth(d['ship_amount_prev'], d['ship_amount_curr']),
            # 发货海外差额（暂为0）
            'ship_overseas_diff_prev': None, 'ship_overseas_diff_curr': None,
            'ship_total_prev': _wan(d['ship_amount_prev']) + (0),
            'ship_total_curr': _wan(d['ship_amount_curr']) + (0),
            'ship_total_growth': _growth(d['ship_amount_prev'], d['ship_amount_curr']),
            'payment_prev': _wan(d['payment_prev']),
            'payment_curr': _wan(d['payment_curr']),
            'overseas_payment_prev': None, 'overseas_payment_curr': None,
            'payment_total_prev': pt_p,
            'payment_total_curr': pt_c,
            'payment_total_growth': _growth(d['payment_prev'], d['payment_curr']),
        }

    # 大区排序
    region_order = ['俄罗斯', '中亚', '亚洲1', '亚洲2', '美洲', '中东', '非洲', '欧洲']

    # 收集非商贸模块并按大区排序
    normal_entries = [(k, v) for k, v in agg.items() if v['region'] not in ('商贸合计',)]
    normal_entries.sort(key=lambda x: (
        region_order.index(x[1]['region']) if x[1]['region'] in region_order else 99,
        x[1]['module']
    ))

    # 按大区分组构建行
    current_region = None
    subtotals = {}

    for key, d in normal_entries:
        region, module = key

        if region != current_region:
            # 输出上一大区小计
            if current_region and current_region in subtotals:
                rows.append(_make_row('subtotal', current_region,
                                      f'{current_region}合计', subtotals[current_region]))
            current_region = region
            subtotals[region] = {k: 0 for k in d}

        # 累加到小计
        for k in d:
            if isinstance(d[k], (int, float)):
                subtotals[region][k] += d[k]

        rows.append(_make_row('data', region, module, d))

    # 最后一个大区小计
    if current_region and current_region in subtotals:
        rows.append(_make_row('subtotal', current_region,
                              f'{current_region}合计', subtotals[current_region]))

    # ── 商贸行 ──
    trade_total = {}
    for tmod in TRADE_MODULES_ORDER:
        d = agg.get(('商贸合计', tmod))
        if d:
            if not trade_total:
                trade_total = {k: 0 for k in d}
            for k in d:
                if isinstance(d[k], (int, float)):
                    trade_total[k] += d[k]
            rows.append(_make_row('trade', '商贸合计', tmod, d))

    # 备件商贸合计
    if trade_total:
        rows.append(_make_row('subtotal', '商贸合计', '备件商贸合计', trade_total))

    # ── 国际总计（聚合原始数据，避免万元重复转换） ──
    grand_raw = {}
    for key, d in agg.items():
        if not grand_raw:
            grand_raw = {k: 0 for k in d}
        for k in d:
            if isinstance(d[k], (int, float)):
                grand_raw[k] = grand_raw.get(k, 0) + d[k]
    if grand_raw:
        rows.append(_make_row('grand_total', '', '国际总计', grand_raw))

    result = {
        'title': '国贸签订、排产、发货两年对比',
        'date_prev_end': prev_end.strftime('%Y-%m-%d'),
        'date_curr_end': curr_end.strftime('%Y-%m-%d'),
        'year_prev': year_prev,
        'year_curr': year_curr,
        'metric_groups': TWO_YEAR_GROUPS,
        'region_order': region_order,
        'rows': rows,
    }

    # 存入缓存
    _two_year_cache = result
    _two_year_fingerprint = fp

    return result


# ── Excel 导出 ──────────────────────────────────────────

def export_two_year_comparison_xlsx():
    """生成带公式的两年对比表 Excel 文件，返回文件路径"""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
    from openpyxl.utils import get_column_letter

    data = get_two_year_comparison()
    rows = data['rows']
    groups = data['metric_groups']
    year_prev = data['year_prev']
    year_curr = data['year_curr']

    wb = Workbook()
    ws = wb.active
    ws.title = '两年对比'

    # 样式
    header_font = Font(name='微软雅黑', bold=True, size=10)
    header_fill = PatternFill('solid', fgColor='EEF2F7')
    data_font = Font(name='微软雅黑', size=10)
    subtotal_fill = PatternFill('solid', fgColor='D6E4F0')
    grand_fill = PatternFill('solid', fgColor='B4C6E7')
    bold_font = Font(name='微软雅黑', bold=True, size=10)
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    # 列宽：A=18, B=8, 每个指标组3列×12
    col_widths = [20, 8]
    for g in groups:
        n = 3 if g['has_growth'] else 2
        for _ in range(n):
            col_widths.append(12)

    for i, w in enumerate(col_widths):
        ws.column_dimensions[get_column_letter(i+1)].width = w

    # Row 1: 标题
    total_cols = 2 + sum(3 if g['has_growth'] else 2 for g in groups)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    c = ws.cell(row=1, column=1, value=data['title'])
    c.font = Font(name='微软雅黑', bold=True, size=14)
    c.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 30

    # Row 2: 表头第一层（组名）
    col = 1
    ws.cell(row=2, column=1, value='模块').font = header_font
    ws.cell(row=2, column=2, value='市场类别').font = header_font
    ws.merge_cells(start_row=2, start_column=1, end_row=3, end_column=1)
    ws.merge_cells(start_row=2, start_column=2, end_row=3, end_column=2)
    col = 3
    for g in groups:
        n = 3 if g['has_growth'] else 2
        ws.merge_cells(start_row=2, start_column=col, end_row=2, end_column=col+n-1)
        c = ws.cell(row=2, column=col, value=g['name'].replace('\n', ''))
        c.font = header_font
        c.alignment = center_align
        col += n

    # Row 3: 表头第二层（年份子列）
    col = 3
    for g in groups:
        ws.cell(row=3, column=col, value=str(year_prev)).font = header_font
        ws.cell(row=3, column=col+1, value=str(year_curr)).font = header_font
        if g['has_growth']:
            ws.cell(row=3, column=col+2, value='增长比例').font = header_font
            col += 3
        else:
            col += 2
    ws.row_dimensions[3].height = 20

    # 数据行（从 row 4 开始）
    excel_row = 4
    region_data_start = {}  # region → 第一个 data/trade 行的Excel行号

    # 预先计算每个 group 对应的列号
    group_cols = {}  # gid -> (col_prev, col_curr, col_growth)
    col = 3
    for g in groups:
        if g['has_growth']:
            group_cols[g['id']] = (col, col+1, col+2)
            col += 3
        else:
            group_cols[g['id']] = (col, col+1, None)
            col += 2

    def _col_letter(c):
        return get_column_letter(c)

    for row_data in rows:
        r = excel_row
        typ = row_data['type']

        # data 和 trade 行都参与 region 追踪，记录每个大区的起始行
        if typ in ('data', 'trade'):
            region_key = row_data.get('region', '')
            if region_key and region_key not in region_data_start:
                region_data_start[region_key] = r

        # 模块名和类别
        cell_a = ws.cell(row=r, column=1, value=row_data['module'])
        if typ in ('data', 'trade'):
            ws.cell(row=r, column=2, value=row_data.get('category', ''))
        elif typ in ('subtotal', 'grand_total'):
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)

        # 写各组数据
        for g in groups:
            gid = g['id']
            cp, cc, cg = group_cols[gid]
            prev_key = f'{gid}_prev'
            curr_key = f'{gid}_curr'
            growth_key = f'{gid}_growth'

            # === 签订额合计: =签订额+海外差额 ===
            if gid == 'sign_total':
                # 找到签订额和海外差额的列
                sa_cp, sa_cc, _ = group_cols['sign_amount']
                od_cp, od_cc, _ = group_cols['overseas_diff']
                if typ in ('data', 'trade'):
                    ws.cell(row=r, column=cp).value = f'={_col_letter(sa_cp)}{r}+{_col_letter(od_cp)}{r}'
                    ws.cell(row=r, column=cc).value = f'={_col_letter(sa_cc)}{r}+{_col_letter(od_cc)}{r}'
                elif typ == 'subtotal':
                    start_row = region_data_start.get(row_data['region'])
                    if start_row:
                        s, e = start_row, r - 1
                        ws.cell(row=r, column=cp).value = f'=SUM({_col_letter(cp)}{s}:{_col_letter(cp)}{e})'
                        ws.cell(row=r, column=cc).value = f'=SUM({_col_letter(cc)}{s}:{_col_letter(cc)}{e})'
                    else:
                        ws.cell(row=r, column=cp, value=row_data.get(prev_key))
                        ws.cell(row=r, column=cc, value=row_data.get(curr_key))
                elif typ == 'grand_total':
                    st_rows = [rr for rr in range(4, r) if ws.cell(row=rr, column=1).value and '合计' in str(ws.cell(row=rr, column=1).value or '')]
                    if st_rows:
                        ws.cell(row=r, column=cp).value = f'=SUM({",".join(_col_letter(cp)+str(sr) for sr in st_rows)})'
                        ws.cell(row=r, column=cc).value = f'=SUM({",".join(_col_letter(cc)+str(sr) for sr in st_rows)})'
                # 增长公式
                if cg:
                    ws.cell(row=r, column=cg).value = f'=IF({_col_letter(cp)}{r}=0,\"-\",({_col_letter(cc)}{r}-{_col_letter(cp)}{r})/{_col_letter(cp)}{r})'
                    ws.cell(row=r, column=cg).number_format = '0%'

            # === 回款额: =回款+海外回款及其他 ===
            elif gid == 'payment_total':
                py_cp, py_cc, _ = group_cols['payment']
                op_cp, op_cc, _ = group_cols['overseas_payment']
                if typ in ('data', 'trade'):
                    ws.cell(row=r, column=cp).value = f'={_col_letter(py_cp)}{r}+{_col_letter(op_cp)}{r}'
                    ws.cell(row=r, column=cc).value = f'={_col_letter(py_cc)}{r}+{_col_letter(op_cc)}{r}'
                elif typ == 'subtotal':
                    start_row = region_data_start.get(row_data['region'])
                    if start_row:
                        s, e = start_row, r - 1
                        ws.cell(row=r, column=cp).value = f'=SUM({_col_letter(cp)}{s}:{_col_letter(cp)}{e})'
                        ws.cell(row=r, column=cc).value = f'=SUM({_col_letter(cc)}{s}:{_col_letter(cc)}{e})'
                    else:
                        ws.cell(row=r, column=cp, value=row_data.get(prev_key))
                        ws.cell(row=r, column=cc, value=row_data.get(curr_key))
                elif typ == 'grand_total':
                    st_rows = [rr for rr in range(4, r) if ws.cell(row=rr, column=1).value and '合计' in str(ws.cell(row=rr, column=1).value or '')]
                    if st_rows:
                        ws.cell(row=r, column=cp).value = f'=SUM({",".join(_col_letter(cp)+str(sr) for sr in st_rows)})'
                        ws.cell(row=r, column=cc).value = f'=SUM({",".join(_col_letter(cc)+str(sr) for sr in st_rows)})'
                if cg:
                    ws.cell(row=r, column=cg).value = f'=IF({_col_letter(cp)}{r}=0,\"-\",({_col_letter(cc)}{r}-{_col_letter(cp)}{r})/{_col_letter(cp)}{r})'
                    ws.cell(row=r, column=cg).number_format = '0%'

            # === 普通列组 ===
            else:
                if typ in ('data', 'trade'):
                    pv = row_data.get(prev_key)
                    cv = row_data.get(curr_key)
                    if pv is not None:
                        ws.cell(row=r, column=cp, value=pv)
                    if cv is not None:
                        ws.cell(row=r, column=cc, value=cv)
                elif typ == 'subtotal':
                    start_row = region_data_start.get(row_data['region'])
                    if start_row:
                        s, e = start_row, r - 1
                        ws.cell(row=r, column=cp).value = f'=SUM({_col_letter(cp)}{s}:{_col_letter(cp)}{e})'
                        ws.cell(row=r, column=cc).value = f'=SUM({_col_letter(cc)}{s}:{_col_letter(cc)}{e})'
                    else:
                        ws.cell(row=r, column=cp, value=row_data.get(prev_key))
                        ws.cell(row=r, column=cc, value=row_data.get(curr_key))
                elif typ == 'grand_total':
                    st_rows = [rr for rr in range(4, r) if ws.cell(row=rr, column=1).value and '合计' in str(ws.cell(row=rr, column=1).value or '')]
                    if st_rows:
                        ws.cell(row=r, column=cp).value = f'=SUM({",".join(_col_letter(cp)+str(sr) for sr in st_rows)})'
                        ws.cell(row=r, column=cc).value = f'=SUM({",".join(_col_letter(cc)+str(sr) for sr in st_rows)})'
                # 增长比例（所有行类型统一使用公式）
                if cg:
                    ws.cell(row=r, column=cg).value = f'=IF({_col_letter(cp)}{r}=0,\"-\",({_col_letter(cc)}{r}-{_col_letter(cp)}{r})/{_col_letter(cp)}{r})'
                    ws.cell(row=r, column=cg).number_format = '0%'

        # 行样式
        for c in range(1, total_cols + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = data_font
            cell.alignment = center_align
            cell.border = thin_border

        if typ == 'subtotal':
            for c in range(1, total_cols + 1):
                ws.cell(row=r, column=c).fill = subtotal_fill
                ws.cell(row=r, column=c).font = bold_font
        elif typ == 'grand_total':
            for c in range(1, total_cols + 1):
                ws.cell(row=r, column=c).fill = grand_fill
                ws.cell(row=r, column=c).font = bold_font

        excel_row += 1

    # 表头样式
    for r in range(2, 4):
        for c in range(1, total_cols + 1):
            cell = ws.cell(row=r, column=c)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            cell.border = thin_border

    # 冻结表头
    ws.freeze_panes = 'A4'

    # 保存
    import os, tempfile
    tmp = os.path.join(tempfile.gettempdir(), 'two_year_comparison.xlsx')
    wb.save(tmp)
    return tmp
