"""Read-only tools used by the business assistant.

All tools receive an already resolved scope. They never accept a module
outside that scope and never write to existing business tables.
"""
import datetime as dt
import re

from dashboards.contract_completion.constants import MODULE_REGION, REGION_DISPLAY
from dashboards.contract_completion.models import LedgerContract, PaymentCollection
from dashboards.contract_completion.services import get_annual_completion, get_two_year_comparison
from module_business_detail.services import _build_ladder_rows, _monthly_actual
from monthly_forecast import services as mf_svc
from monthly_forecast.models import ShipSelection
from ship_tracking.excel_reader import canonical_ladder, normalize_text
from ship_tracking.models import DailyShipment, PlanItem, TrackingItem

from business_assistant.scope import requested_modules


LADDER_COLUMNS = [
    {'key': 'contract_no', 'label': '合同号'},
    {'key': 'ladder_no', 'label': '梯号'},
    {'key': 'project_name', 'label': '项目名称'},
    {'key': 'unit_count', 'label': '台数'},
    {'key': 'amount_wan', 'label': '金额(万元)'},
    {'key': 'schedule_finish_date', 'label': '排产完工日期'},
    {'key': 'whole_ship_date', 'label': '整梯发货日期'},
    {'key': 'delivery_date', 'label': '组A日期'},
    {'key': 'product_type', 'label': '产品型号'},
    {'key': 'capacity', 'label': '载重'},
    {'key': 'speed', 'label': '速度'},
    {'key': 'sign_date', 'label': '签订日期'},
    {'key': 'product_status', 'label': '产品状态'},
    {'key': 'salesperson', 'label': '业务员'},
    {'key': 'payment_ratio_label', 'label': '已回款比例'},
]


def _year(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return dt.date.today().year
    return number if 2000 <= number <= 2100 else dt.date.today().year


def _month(value):
    return mf_svc.normalize_month(normalize_text(value))


def _number(value, digits=2):
    try:
        return round(float(value or 0), digits)
    except (TypeError, ValueError):
        return 0.0


def _optional_number(value, digits=2):
    if value is None or value == '':
        return None
    return _number(value, digits)


def _ratio(actual, target):
    if not target:
        return 0.0
    return round(float(actual or 0) / float(target), 4)


def _annual_values(row, comparison_row, year, current_year):
    metric_keys = {
        'sign_amount': 'sign_total',
        'schedule_amount': 'schedule_total',
        'ship_amount': 'ship_total',
        'payment_amount': 'payment_total',
    }
    result = {}
    for key, comparison_prefix in metric_keys.items():
        is_current = year == current_year
        actual = row.get(key + '_actual') if is_current else comparison_row.get(comparison_prefix + '_prev')
        ratio = _optional_number(row.get(key + '_ratio')) if is_current else None
        result[key] = {
            'target': _number(row.get(key + '_target')) if is_current else None,
            'actual': _number(actual),
            'ratio': round(ratio * 100.0, 2) if ratio is not None else None,
            'previous': _optional_number(comparison_row.get(comparison_prefix + '_prev')) if is_current else None,
            'growth': _optional_number(comparison_row.get(comparison_prefix + '_growth')) if is_current else None,
        }
    return result


def _module_name(value):
    return normalize_text(value)


def _ladder_filters(scope, args):
    modules = requested_modules(scope, args.get('module'))
    year = _year(args.get('year') or dt.date.today().year)
    month = _month(args.get('month'))
    keyword = normalize_text(args.get('keyword') or args.get('q')).upper()
    contract_no = normalize_text(args.get('contract_no')).upper()
    ladder_no = canonical_ladder(args.get('ladder_no') or '')
    return {
        'modules': modules,
        'year': year,
        'month': month,
        'keyword': keyword,
        'contract_no': contract_no,
        'ladder_no': ladder_no,
    }


def _filter_ladder_rows(rows, filters):
    result = []
    for row in rows:
        sign_date = row.get('sign_date') or ''
        if filters['month']:
            if sign_date[:7] != filters['month']:
                continue
        elif sign_date[:4] != str(filters['year']):
            continue
        if filters['contract_no'] and (row.get('contract_no') or '').upper() != filters['contract_no']:
            continue
        if filters['ladder_no'] and canonical_ladder(row.get('ladder_no') or '') != filters['ladder_no']:
            continue
        if filters['keyword']:
            text = ' '.join([
                row.get('contract_no') or '', row.get('ladder_no') or '',
                row.get('project_name') or '', row.get('product_type') or '',
                row.get('product_status') or '', row.get('salesperson') or '',
            ]).upper()
            if filters['keyword'] not in text:
                continue
        result.append(row)
    return result


def performance(scope, args=None):
    args = args or {}
    modules = requested_modules(scope, args.get('module'))
    year = _year(args.get('year') or dt.date.today().year)
    month = _month(args.get('month'))
    comparison_data = get_two_year_comparison()
    current_year = comparison_data.get('year_curr') or dt.date.today().year
    previous_year = comparison_data.get('year_prev') or (current_year - 1)
    if year not in (current_year, previous_year):
        raise ValueError('当前经营数据仅支持 %s、%s 年' % (previous_year, current_year))

    annual_data = get_annual_completion()
    annual_rows = {}
    for row in annual_data.get('rows') or []:
        if row.get('type') in ('data', 'trade'):
            annual_rows[row.get('module')] = row
    comparison_rows = {}
    for row in comparison_data.get('rows') or []:
        if row.get('type') in ('data', 'trade'):
            comparison_rows[row.get('module')] = row

    plan_rows = {}
    actual_rows = {}
    if month:
        plan_rows = {
            row.get('module_name'): row
            for row in mf_svc.get_summary(month, modules).get('rows') or []
        }
        actual_rows = _monthly_actual(modules, month)

    rows = []
    for module in modules:
        annual_row = annual_rows.get(module) or {}
        comparison_row = comparison_rows.get(module) or {}
        plan_row = plan_rows.get(module) or {}
        actual_row = actual_rows.get(module) or {}
        region = annual_row.get('region') or comparison_row.get('region') or MODULE_REGION.get(module, '')
        item = {
            'module_name': module,
            'region': REGION_DISPLAY.get(region, region),
            'annual': _annual_values(annual_row, comparison_row, year, current_year),
        }
        if month:
            item['month_plan'] = {
                'sign_amount': _number(plan_row.get('sign_amount')),
                'prod_amount': _number(plan_row.get('prod_amount')),
                'ship_amount': _number(plan_row.get('ship_amount')),
                'payment_amount': _number(plan_row.get('payment_amount')),
            }
            item['month_actual'] = {
                'sign_amount': _number(actual_row.get('sign_amount')),
                'prod_amount': _number(actual_row.get('prod_amount')),
                'ship_amount': _number(actual_row.get('ship_amount')),
                'payment_amount': _number(actual_row.get('payment_amount')),
            }
        rows.append(item)

    metric_labels = (
        ('sign_amount', '签单'),
        ('schedule_amount', '排产'),
        ('ship_amount', '发货'),
        ('payment_amount', '回款'),
    )
    columns = [
        {'key': 'module_name', 'label': '模块'},
        {'key': 'region', 'label': '大区'},
    ]
    for key, label in metric_labels:
        columns.append({'key': 'annual.%s.actual' % key, 'label': '年%s额' % label})
        if year == current_year:
            columns.extend([
                {'key': 'annual.%s.target' % key, 'label': '%s目标' % label},
                {'key': 'annual.%s.ratio' % key, 'label': '%s完成率(%%)' % label},
                {'key': 'annual.%s.growth' % key, 'label': '%s同比(%%)' % label},
            ])
    if month:
        columns.extend([
            {'key': 'month_plan.sign_amount', 'label': '本月计划签单'},
            {'key': 'month_plan.prod_amount', 'label': '本月计划排产'},
            {'key': 'month_plan.ship_amount', 'label': '本月计划发货'},
            {'key': 'month_plan.payment_amount', 'label': '本月计划回款'},
            {'key': 'month_actual.sign_amount', 'label': '本月实际签单'},
            {'key': 'month_actual.prod_amount', 'label': '本月实际排产'},
            {'key': 'month_actual.ship_amount', 'label': '本月实际发货'},
            {'key': 'month_actual.payment_amount', 'label': '本月实际回款'},
        ])

    sign_total = sum(row['annual']['sign_amount']['actual'] for row in rows)
    sign_target = sum(row['annual']['sign_amount']['target'] or 0 for row in rows)
    payment_total = sum(row['annual']['payment_amount']['actual'] for row in rows)
    payment_target = sum(row['annual']['payment_amount']['target'] or 0 for row in rows)
    period = month or ('%s年度' % year)
    if year == current_year:
        message = (
            '%s，当前范围共 %s 个模块；签单额 %s 万元（目标 %s，完成率 %s），'
            '回款额 %s 万元（目标 %s，完成率 %s）。'
        ) % (
            period, len(rows), round(sign_total, 2), round(sign_target, 2),
            _ratio(sign_total, sign_target) * 100,
            round(payment_total, 2), round(payment_target, 2),
            _ratio(payment_total, payment_target) * 100,
        )
    else:
        message = '%s，当前范围共 %s 个模块；签单额 %s 万元，回款额 %s 万元。' % (
            period, len(rows), round(sign_total, 2), round(payment_total, 2))
    return {
        'kind': 'performance',
        'scope_label': scope['label'],
        'period': period,
        'data_date': annual_data.get('data_date') if year == current_year else comparison_data.get('date_prev_end', ''),
        'columns': columns,
        'rows': rows,
        'message': message,
        'notes': [
            '年度金额沿用两年对比/年度完成情况口径，含已上传海外差额。' ,
            '月度计划来自单月签排发填报，月度实际来自台账与实际回款。' ,
            '完成率与同比按当前数据截止日计算；上年目标未维护时不展示完成率。' ,
        ],
        'exportable': True,
    }


def ladders(scope, args=None, limit=30):
    args = args or {}
    filters = _ladder_filters(scope, args)
    rows = _filter_ladder_rows(_build_ladder_rows(filters['modules']), filters)
    units = round(sum(_number(row.get('unit_count')) for row in rows), 2)
    amount = round(sum(_number(row.get('amount_wan')) for row in rows), 2)
    shown = rows if limit is None else rows[:limit]
    return {
        'kind': 'ladders',
        'scope_label': scope['label'],
        'period': filters['month'] or ('%s年度' % filters['year']),
        'columns': LADDER_COLUMNS,
        'rows': shown,
        'total': len(rows),
        'units': units,
        'amount_wan': amount,
        'message': '共找到 %s 行梯号，台数 %s，合同金额 %s 万元。' % (len(rows), units, amount),
        'notes': [
            '明细直接来自台账 cc_ledger_contract，按签订日期筛选，不按梯号去重。' ,
            '已回款比例取台账 payment_ratio，不重新计算回款分摊。' ,
        ],
        'exportable': bool(rows),
        'export_args': {
            'year': filters['year'],
            'month': filters['month'] or '',
            'module': args.get('module') or '',
            'keyword': args.get('keyword') or '',
            'contract_no': args.get('contract_no') or '',
            'ladder_no': args.get('ladder_no') or '',
        },
    }


def _matching_ladder_rows(scope, args):
    filters = _ladder_filters(scope, {
        'module': args.get('module'),
        'year': args.get('year'),
        'month': args.get('month'),
        'keyword': args.get('keyword'),
        'contract_no': args.get('contract_no'),
        'ladder_no': args.get('ladder_no'),
    })
    if filters['month']:
        filters['month'] = ''
    rows = _build_ladder_rows(filters['modules'])
    if filters['contract_no']:
        rows = [row for row in rows if (row.get('contract_no') or '').upper() == filters['contract_no']]
    if filters['ladder_no']:
        rows = [row for row in rows if canonical_ladder(row.get('ladder_no') or '') == filters['ladder_no']]
    if filters['keyword']:
        key = filters['keyword']
        rows = [row for row in rows if key in ' '.join([
            row.get('contract_no') or '', row.get('ladder_no') or '', row.get('project_name') or '',
        ]).upper()]
    return rows, filters


def ladder_status(scope, args=None):
    args = args or {}
    if not any(args.get(key) for key in ('contract_no', 'ladder_no', 'keyword')):
        return {
            'kind': 'ladder_status',
            'needs_input': True,
            'message': '请提供合同号或梯号，我再查询它在台账、填报、发货计划和回款中的状态。' ,
            'columns': [], 'rows': [], 'exportable': False,
        }
    rows, filters = _matching_ladder_rows(scope, args)
    if not rows:
        return {
            'kind': 'ladder_status',
            'message': '当前权限范围内没有找到匹配的合同或梯号。' ,
            'columns': [], 'rows': [], 'exportable': False,
        }
    result = []
    for row in rows[:10]:
        key = canonical_ladder(row.get('ladder_no') or '')
        selections = ShipSelection.query.filter_by(module_name=row.get('module_name')).all()
        selected = [item for item in selections if canonical_ladder(item.ladder_no or '') == key]
        tracking = TrackingItem.query.filter_by(ladder_key=key).first()
        plan = PlanItem.query.filter_by(ladder_key=key).order_by(PlanItem.plan_month.desc(), PlanItem.plan_version.desc()).first()
        payments = PaymentCollection.query.filter_by(contract_no=row.get('contract_no') or '').all()
        payment_rows = [item for item in payments if canonical_ladder(item.ladder_no or '') == key]
        contract_payments = [item for item in payments if not canonical_ladder(item.ladder_no or '')]
        payment_scope = '梯号级' if payment_rows else ('合同级' if contract_payments else '未匹配')
        payment_amount = sum((item.payment_amount_rmb or 0) for item in (payment_rows or contract_payments)) / 10000.0
        actual_date = row.get('delivery_date') or ''
        if not actual_date and tracking and tracking.actual_ship_date:
            actual_date = tracking.actual_ship_date.strftime('%Y-%m-%d')
        result.append({
            'contract_no': row.get('contract_no') or '',
            'ladder_no': row.get('ladder_no') or '',
            'ledger': '已存在' if row else '不存在',
            'forecast': ('已选择 ' + '、'.join(sorted(set(item.data_month for item in selected))) if selected else '未选择'),
            'ship_plan': ((plan.plan_month + ' / 版本 ' + str(plan.plan_version)) if plan else '未导入'),
            'actual_ship': actual_date or '未实发',
            'payment_match': payment_scope,
            'payment_wan': round(payment_amount, 2),
            'payment_ratio': row.get('payment_ratio_label') or '—',
        })
    return {
        'kind': 'ladder_status',
        'scope_label': scope['label'],
        'message': '找到 %s 个匹配梯号，以下展示前 %s 个。' % (len(rows), len(result)),
        'columns': [
            {'key': 'contract_no', 'label': '合同号'},
            {'key': 'ladder_no', 'label': '梯号'},
            {'key': 'ledger', 'label': '台账'},
            {'key': 'forecast', 'label': '单月填报'},
            {'key': 'ship_plan', 'label': '发货计划'},
            {'key': 'actual_ship', 'label': '实际发货'},
            {'key': 'payment_match', 'label': '回款匹配'},
            {'key': 'payment_wan', 'label': '回款(万元)'},
            {'key': 'payment_ratio', 'label': '已回款比例'},
        ],
        'rows': result,
        'notes': ['回款只展示汇总和匹配状态，不展示逐笔日期、节点、付款方式或备注。'],
        'exportable': False,
    }


def diagnose(scope, args=None):
    args = args or {}
    if not any(args.get(key) for key in ('contract_no', 'ladder_no', 'keyword')):
        return {
            'kind': 'diagnose',
            'needs_input': True,
            'message': '请提供要诊断的合同号或梯号。' ,
            'columns': [], 'rows': [], 'exportable': False,
        }
    rows, filters = _matching_ladder_rows(scope, args)
    if not rows:
        return {
            'kind': 'diagnose',
            'message': '当前权限范围内没有找到该合同或梯号的台账记录。' ,
            'columns': [], 'rows': [], 'exportable': False,
        }
    month = _month(args.get('month')) or mf_svc.default_month()
    results = []
    for row in rows[:10]:
        key = canonical_ladder(row.get('ladder_no') or '')
        candidates = mf_svc.list_candidates(row.get('module_name'), month)
        candidate_keys = {
            canonical_ladder(
                (item.get('ladder_no') if isinstance(item, dict) else item.ladder_no) or ''
            )
            for item in candidates
        }
        selected = ShipSelection.query.filter_by(
            data_month=month, module_name=row.get('module_name')
        ).all()
        selected = [item for item in selected if canonical_ladder(item.ladder_no or '') == key]
        reasons = []
        if row.get('product_status') == '已作废':
            reasons.append('产品状态为已作废，台账统计会排除。' )
        if row.get('delivery_date'):
            reasons.append('已有组A/实际发货日期，不再进入发货候选池。' )
        if not row.get('schedule_finish_date'):
            reasons.append('排产完工日期为空，请核对是否已排产。' )
        if row.get('whole_ship_date') and row['whole_ship_date'][:7] > month:
            reasons.append('整梯发货日期晚于填报月份，候选池会排除。' )
        if key in candidate_keys:
            reasons.append('当前在候选池中，可以勾选。' )
        else:
            reasons.append('当前不在候选池，请核对国家映射、排产日期、整梯发货日期和签订日期。' )
        if selected:
            reasons.append('该梯号已在 %s 发货明细中存在。' % month)
        results.append({
            'contract_no': row.get('contract_no') or '',
            'ladder_no': row.get('ladder_no') or '',
            'module_name': row.get('module_name') or '',
            'month': month,
            'diagnosis': '；'.join(reasons),
        })
    return {
        'kind': 'diagnose',
        'scope_label': scope['label'],
        'message': '已检查 %s 个匹配梯号。' % len(results),
        'columns': [
            {'key': 'contract_no', 'label': '合同号'},
            {'key': 'ladder_no', 'label': '梯号'},
            {'key': 'module_name', 'label': '模块'},
            {'key': 'month', 'label': '月份'},
            {'key': 'diagnosis', 'label': '诊断'},
        ],
        'rows': results,
        'notes': ['诊断只解释现有规则，不会修改台账、计划或填报数据。'],
        'exportable': False,
    }
