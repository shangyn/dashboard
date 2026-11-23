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
from monthly_forecast.models import MonthlyInput, ShipSelection, Submission
from ship_tracking.excel_reader import canonical_ladder, normalize_text
from ship_tracking.models import (
    DailyShipment, PaymentCalcDetail, PaymentCalcRun, PlanItem, TrackingItem,
)

from business_assistant.scope import requested_modules


LADDER_COLUMNS = [
    {'key': 'module_name', 'label': '模块'},
    {'key': 'contract_no', 'label': '合同号'},
    {'key': 'ladder_no', 'label': '梯号'},
    {'key': 'project_name', 'label': '项目名称'},
    {'key': 'unit_count', 'label': '台数'},
    {'key': 'amount_wan', 'label': '金额(万元)'},
    {'key': 'schedule_date', 'label': '排产日期'},
    {'key': 'schedule_finish_date', 'label': '排产完工日期'},
    {'key': 'whole_ship_date', 'label': '整梯发货日期'},
    {'key': 'delivery_date', 'label': '组A日期'},
    {'key': 'product_type', 'label': '产品型号'},
    {'key': 'capacity', 'label': '载重'},
    {'key': 'speed', 'label': '速度'},
    {'key': 'sign_date', 'label': '签订日期'},
    {'key': 'product_status', 'label': '产品状态'},
    {'key': 'salesperson', 'label': '业务员'},
    {'key': 'payment_ratio_label', 'label': '回款比例'},
    {'key': 'payment_ratio_source', 'label': '比例来源'},
]


DATE_DIMENSIONS = {
    'sign': {'field': 'sign_date', 'label': '签订日期'},
    'schedule': {'field': 'schedule_date', 'label': '排产日期'},
    'ship': {'field': 'delivery_date', 'label': '发货日期'},
    'whole_ship': {'field': 'whole_ship_date', 'label': '整梯发货日期'},
}
DATE_DIMENSION_ALIASES = {
    'sign': 'sign',
    'sign_date': 'sign',
    '签订': 'sign',
    '签订日期': 'sign',
    'schedule': 'schedule',
    'schedule_date': 'schedule',
    '排产': 'schedule',
    '排产日期': 'schedule',
    'ship': 'ship',
    'delivery': 'ship',
    'delivery_date': 'ship',
    '发货': 'ship',
    '发货日期': 'ship',
    '组a': 'ship',
    '组a日期': 'ship',
    'whole_ship': 'whole_ship',
    'whole_ship_date': 'whole_ship',
    '整梯发货': 'whole_ship',
    '整梯发货日期': 'whole_ship',
}
PERFORMANCE_METRICS = (
    ('sign_amount', '签单'),
    ('schedule_amount', '排产'),
    ('ship_amount', '发货'),
    ('payment_amount', '回款'),
)
MONTH_ACTUAL_KEYS = {
    'sign_amount': 'sign_amount',
    'schedule_amount': 'prod_amount',
    'ship_amount': 'ship_amount',
    'payment_amount': 'payment_amount',
}


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


def _payment_ratio_value(value):
    if value is None or value == '':
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        number = 0.0
    if number >= 1:
        number = 1.0
    return number


def _payment_ratio_label(value):
    return '—' if value is None else '%.2f%%' % (value * 100.0)


def _latest_payment_details():
    run = PaymentCalcRun.query.filter_by(status='success')\
        .order_by(PaymentCalcRun.id.desc()).first()
    if run is None:
        return None, {}
    details = PaymentCalcDetail.query.filter_by(run_id=run.id).all()
    result = {}
    for detail in details:
        ladder_key = canonical_ladder(detail.ladder_key or detail.ladder_no or '')
        if ladder_key:
            result[ladder_key] = detail
    return run, result


def _payment_ratio_source(detail, ledger_ratio, run):
    if detail is None:
        if ledger_ratio is not None and ledger_ratio >= 1:
            return '台账已满100%'
        if run is None:
            return '台账比例（无成功计算批次）'
        return '台账比例（未参与最近计算）'
    status = detail.status or ''
    if status == 'calculated':
        return '回款计算'
    if status == 'no_payment_keep_ledger':
        return '回款计算（无回款，保留台账）'
    if status == 'no_payment_zero':
        return '回款计算（无回款，0%）'
    if status == 'no_payment_no_ledger_ratio':
        return '回款计算（无回款，空值）'
    if status == 'no_contract_amount':
        return '台账比例（合同额无效）'
    if status == 'ledger_not_found':
        return '台账比例（计算未匹配台账）'
    if status == 'ledger_paid':
        return '台账已满100%'
    return '回款计算'


def _enrich_payment_ratios(rows):
    """Use the latest successful payment calculation, then fall back to ledger."""
    if not rows:
        return rows
    run, details = _latest_payment_details()
    for row in rows:
        ledger_ratio = _payment_ratio_value(row.get('payment_ratio'))
        ladder_key = canonical_ladder(row.get('ladder_no') or '')
        detail = details.get(ladder_key)
        if detail is not None:
            ratio = _payment_ratio_value(detail.calculated_ratio_display)
            if ratio is None:
                ratio = _payment_ratio_value(detail.calculated_ratio)
        else:
            ratio = ledger_ratio
        row['payment_ratio'] = ratio
        row['payment_ratio_label'] = _payment_ratio_label(ratio)
        row['payment_ratio_source'] = _payment_ratio_source(detail, ledger_ratio, run)
    return rows


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
            'target': _optional_number(row.get(key + '_target')) if is_current else None,
            'actual': _number(actual),
            'ratio': round(ratio * 100.0, 2) if ratio is not None else None,
            'previous': _optional_number(comparison_row.get(comparison_prefix + '_prev')) if is_current else None,
            'growth': _optional_number(comparison_row.get(comparison_prefix + '_growth')) if is_current else None,
        }
    return result


def _module_name(value):
    return normalize_text(value)


def _normalize_date_dimension(value, default='sign'):
    text = normalize_text(value).lower().replace('-', '_')
    if not text:
        return default
    return DATE_DIMENSION_ALIASES.get(text, default)


def _date_field(date_dimension):
    return DATE_DIMENSIONS.get(date_dimension, DATE_DIMENSIONS['sign'])['field']


def _date_dimension_label(date_dimension):
    return DATE_DIMENSIONS.get(date_dimension, DATE_DIMENSIONS['sign'])['label']


def _fact(fact_id, subject, metric, metric_key, value, unit='万元', period='',
          grain='', data_date='', source_table='', comparison=''):
    return {
        'fact_id': fact_id,
        'subject': subject,
        'metric': metric,
        'metric_key': metric_key,
        'value': value,
        'unit': unit,
        'period': period,
        'grain': grain,
        'comparison': comparison,
        'data_date': data_date,
        'source_table': source_table,
    }


def _schedule_date_index(modules):
    '''Read schedule dates without changing the shared ledger service.'''
    module_set = set(modules)
    if not module_set:
        return {}
    module_map = mf_svc.load_module_map()
    result = {}
    for contract in LedgerContract.query.filter(LedgerContract.source == 'ledger').all():
        if (contract.product_status or '') == '已作废':
            continue
        module = mf_svc.resolve_module(contract, module_map)
        if module not in module_set or not contract.schedule_date:
            continue
        contract_no = normalize_text(contract.contract_no).upper()
        ladder_key = canonical_ladder(contract.ladder_no or '')
        if contract_no and ladder_key:
            result[(module, contract_no, ladder_key)] = contract.schedule_date.isoformat()
    return result


def _enrich_schedule_dates(rows):
    if not rows:
        return rows
    modules = sorted({row.get('module_name') for row in rows if row.get('module_name')})
    index = _schedule_date_index(modules)
    for row in rows:
        contract_no = normalize_text(row.get('contract_no')).upper()
        ladder_key = canonical_ladder(row.get('ladder_no') or '')
        row['schedule_date'] = index.get(
            (row.get('module_name'), contract_no, ladder_key)
        ) or ''
    return rows


def _ladder_filters(scope, args):
    modules = requested_modules(scope, args.get('modules') or args.get('module'))
    year = _year(args.get('year') or dt.date.today().year)
    month = _month(args.get('month'))
    date_dimension = _normalize_date_dimension(
        args.get('date_dimension') or args.get('date_field')
    )
    keyword = normalize_text(args.get('keyword') or args.get('q')).upper()
    contract_no = normalize_text(args.get('contract_no')).upper()
    ladder_no = canonical_ladder(args.get('ladder_no') or '')
    return {
        'modules': modules,
        'year': year,
        'month': month,
        'date_dimension': date_dimension,
        'date_field': _date_field(date_dimension),
        'date_dimension_label': _date_dimension_label(date_dimension),
        'keyword': keyword,
        'contract_no': contract_no,
        'ladder_no': ladder_no,
    }


def _filter_ladder_rows(rows, filters):
    result = []
    date_field = filters.get('date_field') or 'sign_date'
    for row in rows:
        date_value = row.get(date_field) or ''
        if filters['month']:
            if date_value[:7] != filters['month']:
                continue
        elif date_value[:4] != str(filters['year']):
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


def _performance_facts(rows, period, grain, data_date):
    facts = [
        _fact(
            'performance:%s:total:module_count' % period,
            '当前范围', '模块数', 'module_count', len(rows), unit='个',
            period=period, grain=grain, data_date=data_date,
            source_table='cc_ledger_contract',
        ),
    ]
    source = 'cc_ledger_contract / cc_payment_collection'
    for row in rows:
        subject = row.get('module_name') or ''
        if grain == 'month':
            actual_values = row.get('month_actual') or {}
            plan_values = row.get('month_plan') or {}
            for key, label in PERFORMANCE_METRICS:
                actual_key = MONTH_ACTUAL_KEYS[key]
                facts.append(_fact(
                    'performance:%s:%s:%s:actual' % (period, subject, key),
                    subject, label, key, _number(actual_values.get(actual_key)),
                    period=period, grain='month', data_date=data_date,
                    source_table=source,
                ))
                facts.append(_fact(
                    'performance:%s:%s:%s:plan' % (period, subject, key),
                    subject, label + '计划', key + '_plan',
                    _number(plan_values.get(actual_key)),
                    period=period, grain='month', data_date=data_date,
                    source_table='mf_monthly_input',
                ))
        else:
            annual_values = row.get('annual') or {}
            for key, label in PERFORMANCE_METRICS:
                metric = annual_values.get(key) or {}
                facts.append(_fact(
                    'performance:%s:%s:%s:actual' % (period, subject, key),
                    subject, label, key, _number(metric.get('actual')),
                    period=period, grain='year', data_date=data_date,
                    source_table=source,
                ))
                if metric.get('target') is not None:
                    facts.append(_fact(
                        'performance:%s:%s:%s:target' % (period, subject, key),
                        subject, label + '目标', key + '_target',
                        _number(metric.get('target')),
                        period=period, grain='year', data_date=data_date,
                        source_table='cc_annual_target',
                    ))
                if metric.get('ratio') is not None:
                    facts.append(_fact(
                        'performance:%s:%s:%s:ratio' % (period, subject, key),
                        subject, label + '完成率', key + '_ratio',
                        _number(metric.get('ratio')), unit='%',
                        period=period, grain='year', data_date=data_date,
                        source_table='cc_annual_target',
                    ))
                if metric.get('growth') is not None:
                    facts.append(_fact(
                        'performance:%s:%s:%s:growth' % (period, subject, key),
                        subject, label + '同比', key + '_growth',
                        _number(metric.get('growth')), unit='%',
                        period=period, grain='year', data_date=data_date,
                        source_table=source,
                    ))
    if grain == 'month':
        for key, label in PERFORMANCE_METRICS:
            actual_key = MONTH_ACTUAL_KEYS[key]
            actual = round(sum(
                _number((row.get('month_actual') or {}).get(actual_key)) for row in rows
            ), 2)
            plan = round(sum(
                _number((row.get('month_plan') or {}).get(actual_key)) for row in rows
            ), 2)
            facts.append(_fact(
                'performance:%s:total:%s:actual' % (period, key),
                '当前范围', label, key, actual, period=period, grain='month',
                data_date=data_date, source_table=source,
            ))
            facts.append(_fact(
                'performance:%s:total:%s:plan' % (period, key),
                '当前范围', label + '计划', key + '_plan', plan,
                period=period, grain='month', data_date=data_date,
                source_table='mf_monthly_input',
            ))
    else:
        for key, label in PERFORMANCE_METRICS:
            metric_values = [row.get('annual', {}).get(key, {}) for row in rows]
            actual = round(sum(_number(item.get('actual')) for item in metric_values), 2)
            target_values = [
                item.get('target') for item in metric_values
                if item.get('target') is not None
            ]
            target = round(sum(_number(value) for value in target_values), 2) if target_values else None
            facts.append(_fact(
                'performance:%s:total:%s:actual' % (period, key),
                '当前范围', label, key, actual, period=period, grain='year',
                data_date=data_date, source_table=source,
            ))
            if target is not None:
                facts.append(_fact(
                    'performance:%s:total:%s:target' % (period, key),
                    '当前范围', label + '目标', key + '_target', target,
                    period=period, grain='year', data_date=data_date,
                    source_table='cc_annual_target',
                ))
                ratio = round(_ratio(actual, target) * 100, 2) if target else None
                if ratio is not None:
                    facts.append(_fact(
                        'performance:%s:total:%s:ratio' % (period, key),
                        '当前范围', label + '完成率', key + '_ratio', ratio,
                        unit='%', period=period, grain='year', data_date=data_date,
                        source_table='cc_annual_target',
                    ))
    return facts


def performance(scope, args=None):
    args = args or {}
    modules = requested_modules(scope, args.get('modules') or args.get('module'))
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
    time_grain = 'month' if month else 'year'
    if month:
        actual_totals = {}
        plan_totals = {}
        for metric_key, _label in PERFORMANCE_METRICS:
            actual_key = MONTH_ACTUAL_KEYS[metric_key]
            plan_key = MONTH_ACTUAL_KEYS[metric_key]
            actual_totals[metric_key] = round(sum(
                _number((row.get('month_actual') or {}).get(actual_key)) for row in rows
            ), 2)
            plan_totals[metric_key] = round(sum(
                _number((row.get('month_plan') or {}).get(plan_key)) for row in rows
            ), 2)
        message = (
            '%s，当前范围共 %s 个模块；月度实际签单 %s 万元（计划 %s），'
            '月度实际排产 %s 万元（计划 %s），月度实际发货 %s 万元（计划 %s），'
            '月度实际回款 %s 万元（计划 %s）。'
        ) % (
            period, len(rows),
            actual_totals['sign_amount'], plan_totals['sign_amount'],
            actual_totals['schedule_amount'], plan_totals['schedule_amount'],
            actual_totals['ship_amount'], plan_totals['ship_amount'],
            actual_totals['payment_amount'], plan_totals['payment_amount'],
        )
    elif year == current_year:
        sign_target_present = any(
            row['annual']['sign_amount']['target'] is not None for row in rows
        )
        payment_target_present = any(
            row['annual']['payment_amount']['target'] is not None for row in rows
        )
        sign_target_text = (
            '目标 %s，完成率 %s%%' % (
                round(sign_target, 2), _ratio(sign_total, sign_target) * 100,
            )
            if sign_target_present else '目标未维护'
        )
        payment_target_text = (
            '目标 %s，完成率 %s%%' % (
                round(payment_target, 2), _ratio(payment_total, payment_target) * 100,
            )
            if payment_target_present else '目标未维护'
        )
        message = (
            '%s，当前范围共 %s 个模块；签单额 %s 万元（%s），'
            '回款额 %s 万元（%s）。'
        ) % (
            period, len(rows), round(sign_total, 2), sign_target_text,
            round(payment_total, 2), payment_target_text,
        )
    else:
        message = '%s，当前范围共 %s 个模块；签单额 %s 万元，回款额 %s 万元。' % (
            period, len(rows), round(sign_total, 2), round(payment_total, 2))
    data_date = annual_data.get('data_date') if year == current_year else comparison_data.get('date_prev_end', '')
    facts = _performance_facts(rows, period, time_grain, data_date)
    return {
        'kind': 'performance',
        'scope_label': scope['label'],
        'period': period,
        'time_grain': time_grain,
        'data_date': data_date,
        'columns': columns,
        'rows': rows,
        'facts': facts,
        'message': message,
        'notes': [
            '年度金额沿用两年对比/年度完成情况口径，含已上传海外差额。' ,
            '月度计划来自单月签排发填报，月度实际来自台账与实际回款。' ,
            '月度问题只使用月度实际和月度计划，不把年度累计当作月度数据。' ,
            '完成率与同比按当前数据截止日计算；上年目标未维护时不展示完成率。' ,
        ],
        'exportable': True,
    }


def _ladders_facts(rows, filters, units, amount):
    data_date = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    period = filters['month'] or ('%s年度' % filters['year'])
    source = 'cc_ledger_contract'
    facts = [
        _fact('ladders:%s:total:row_count' % period, '当前范围', '梯号行数',
              'row_count', len(rows), unit='行', period=period,
              grain='period', data_date=data_date, source_table=source),
        _fact('ladders:%s:total:units' % period, '当前范围', '台数',
              'units', units, unit='台', period=period,
              grain='period', data_date=data_date, source_table=source),
        _fact('ladders:%s:total:amount' % period, '当前范围', '合同金额',
              'amount_wan', amount, period=period, grain='period',
              data_date=data_date, source_table=source),
    ]
    grouped = {}
    for row in rows:
        module = row.get('module_name') or ''
        item = grouped.setdefault(module, {'rows': 0, 'units': 0, 'amount': 0.0})
        item['rows'] += 1
        item['units'] += _number(row.get('unit_count'))
        item['amount'] += _number(row.get('amount_wan'))
    for module, item in grouped.items():
        facts.append(_fact(
            'ladders:%s:%s:units' % (period, module), module, '台数',
            'units', round(item['units'], 2), unit='台', period=period,
            grain='period', data_date=data_date, source_table=source,
        ))
        facts.append(_fact(
            'ladders:%s:%s:amount' % (period, module), module, '合同金额',
            'amount_wan', round(item['amount'], 2), period=period,
            grain='period', data_date=data_date, source_table=source,
        ))
    return facts


def ladders(scope, args=None, limit=30):
    args = args or {}
    filters = _ladder_filters(scope, args)
    rows = _build_ladder_rows(filters['modules'])
    rows = _enrich_schedule_dates(rows)
    rows = _filter_ladder_rows(_enrich_payment_ratios(rows), filters)
    units = round(sum(_number(row.get('unit_count')) for row in rows), 2)
    amount = round(sum(_number(row.get('amount_wan')) for row in rows), 2)
    shown = rows if limit is None else rows[:limit]
    facts = _ladders_facts(rows, filters, units, amount)
    return {
        'kind': 'ladders',
        'scope_label': scope['label'],
        'period': filters['month'] or ('%s年度' % filters['year']),
        'date_dimension': filters['date_dimension'],
        'date_dimension_label': filters['date_dimension_label'],
        'columns': LADDER_COLUMNS,
        'rows': shown,
        'facts': facts,
        'total': len(rows),
        'units': units,
        'amount_wan': amount,
        'message': '按%s筛选，共找到 %s 行梯号，台数 %s，合同金额 %s 万元。' % (
            filters['date_dimension_label'], len(rows), units, amount
        ),
        'notes': [
            '明细直接来自台账 cc_ledger_contract，不按梯号去重。' ,
            '时间筛选维度：%s。' % filters['date_dimension_label'],
            '回款比例优先取发货梯号明细最近一次成功回款计算；未参与计算的梯号回退台账比例。' ,
            '“比例来源”用于区分回款计算、台账回退和已满 100% 的梯号。' ,
        ],
        'exportable': bool(rows),
        'export_args': {
            'year': filters['year'],
            'month': filters['month'] or '',
            'modules': filters['modules'],
            'module': args.get('module') or '',
            'date_dimension': filters['date_dimension'],
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
    rows = _enrich_payment_ratios(_build_ladder_rows(filters['modules']))
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
            'payment_ratio_source': row.get('payment_ratio_source') or '',
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
            {'key': 'payment_ratio', 'label': '回款比例'},
            {'key': 'payment_ratio_source', 'label': '比例来源'},
        ],
        'rows': result,
        'notes': [
            '回款只展示汇总和匹配状态，不展示逐笔日期、节点、付款方式或备注。',
            '回款比例优先取最近一次成功回款计算，未参与计算的梯号回退台账比例。',
        ],
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


CONTRACT_PAYMENT_COLUMNS = [
    {'key': 'contract_no', 'label': '合同号'},
    {'key': 'module_name', 'label': '模块'},
    {'key': 'project_name', 'label': '项目名称'},
    {'key': 'ladder_count', 'label': '梯号数'},
    {'key': 'ladder_nos', 'label': '梯号'},
    {'key': 'ledger_amount_wan', 'label': '合同金额(万元)'},
    {'key': 'ladder_payment_wan', 'label': '梯号级回款(万元)'},
    {'key': 'contract_payment_wan', 'label': '合同级回款(万元)'},
    {'key': 'other_payment_wan', 'label': '其他梯号回款(万元)'},
    {'key': 'payment_wan', 'label': '回款合计(万元)'},
    {'key': 'payment_count', 'label': '回款笔数'},
    {'key': 'payment_match', 'label': '回款匹配'},
    {'key': 'first_payment_date', 'label': '首次回款'},
    {'key': 'last_payment_date', 'label': '最近回款'},
    {'key': 'payment_ratio', 'label': '回款比例'},
    {'key': 'payment_ratio_source', 'label': '比例来源'},
]


def _contract_payment_facts(rows, period, matched_count=None):
    data_date = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    facts = [
        _fact(
            'contract_payment:%s:total:contract_count' % period,
            '当前范围', '合同数', 'contract_count', len(rows), unit='个',
            period=period, grain='period', data_date=data_date,
            source_table='cc_ledger_contract',
        ),
    ]
    if matched_count is not None:
        facts.append(_fact(
            'contract_payment:%s:total:paid_contract_count' % period,
            '当前范围', '有回款合同数', 'paid_contract_count',
            matched_count, unit='个', period=period, grain='period',
            data_date=data_date,
            source_table='cc_payment_collection',
        ))
    source = 'cc_payment_collection / st_payment_calc_detail'
    metrics = (
        ('ladder_payment_wan', '梯号级回款', 'ladder_payment'),
        ('contract_payment_wan', '合同级回款', 'contract_payment'),
        ('other_payment_wan', '其他梯号回款', 'other_payment'),
        ('payment_wan', '回款合计', 'payment_total'),
    )
    for row in rows:
        subject = row.get('contract_no') or ''
        for key, label, metric_key in metrics:
            facts.append(_fact(
                'contract_payment:%s:%s:%s' % (period, subject, metric_key),
                subject, label, metric_key, _number(row.get(key)),
                period=period, grain='period', data_date=data_date,
                source_table=source,
            ))
        facts.append(_fact(
            'contract_payment:%s:%s:payment_count' % (period, subject),
            subject, '回款笔数', 'payment_count', _number(row.get('payment_count')),
            unit='笔', period=period, grain='period', data_date=data_date,
            source_table='cc_payment_collection',
        ))
    for key, label, metric_key in metrics:
        facts.append(_fact(
            'contract_payment:%s:total:%s' % (period, metric_key),
            '当前范围', label, metric_key,
            round(sum(_number(row.get(key)) for row in rows), 2),
            period=period, grain='period', data_date=data_date,
            source_table=source,
        ))
    return facts


def contract_payment(scope, args=None):
    """Summarize payments for contracts or ladders already in the user's scope."""
    args = args or {}
    if not any(args.get(key) for key in ('contract_no', 'ladder_no', 'keyword')):
        return {
            'kind': 'contract_payment',
            'status': 'needs_input',
            'failure_code': 'missing_contract',
            'needs_input': True,
            'message': '请提供合同号或梯号，我再查询对应回款汇总。',
            'columns': [],
            'rows': [],
            'notes': [],
            'exportable': False,
        }

    ledger_rows, filters = _matching_ladder_rows(scope, args)
    if not ledger_rows:
        scoped = bool(scope.get('scoped'))
        return {
            'kind': 'contract_payment',
            'status': 'needs_input',
            'failure_code': 'contract_forbidden' if scoped else 'contract_not_found',
            'needs_input': True,
            'message': (
                '当前账号无法查询这个合同或梯号的回款，请确认号码是否属于你负责的模块。'
                if scoped else
                '当前权限范围内没有找到匹配的合同或梯号，请核对合同号或梯号后重试。'
            ),
            'columns': [],
            'rows': [],
            'notes': ['回款查询先通过台账确认合同归属，再做权限校验。'],
            'exportable': False,
        }

    contract_rows = {}
    for row in ledger_rows:
        contract_no = normalize_text(row.get('contract_no')).upper()
        if not contract_no:
            continue
        contract_rows.setdefault(contract_no, []).append(row)

    contracts = sorted(contract_rows)
    if not contracts:
        return {
            'kind': 'contract_payment',
            'message': '匹配记录缺少合同号，无法汇总回款。',
            'columns': [],
            'rows': [],
            'notes': [],
            'exportable': False,
        }

    payments = PaymentCollection.query.filter(
        PaymentCollection.contract_no.in_(contracts)
    ).all()
    month = _month(args.get('month'))
    time_scope = normalize_text(args.get('time_scope')) or 'all'
    year = _year(args.get('year'))
    if month:
        payments = [
            item for item in payments
            if item.payment_date and item.payment_date.strftime('%Y-%m') == month
        ]
    elif time_scope == 'year':
        payments = [
            item for item in payments
            if item.payment_date and item.payment_date.year == year
        ]

    payments_by_contract = {}
    for item in payments:
        key = normalize_text(item.contract_no).upper()
        payments_by_contract.setdefault(key, []).append(item)

    result_rows = []
    for contract_no in contracts:
        rows = contract_rows[contract_no]
        ladder_keys = {
            canonical_ladder(row.get('ladder_no') or '') for row in rows
            if canonical_ladder(row.get('ladder_no') or '')
        }
        contract_payments = payments_by_contract.get(contract_no, [])
        ladder_payments = [
            item for item in contract_payments
            if item.ladder_no and canonical_ladder(item.ladder_no) in ladder_keys
        ]
        contract_level_payments = [
            item for item in contract_payments
            if not canonical_ladder(item.ladder_no or '')
        ]
        other_payments = [
            item for item in contract_payments
            if canonical_ladder(item.ladder_no or '')
            and canonical_ladder(item.ladder_no or '') not in ladder_keys
        ]
        matched = ladder_payments + contract_level_payments + other_payments
        match_labels = []
        if ladder_payments:
            match_labels.append('梯号级')
        if contract_level_payments:
            match_labels.append('合同级')
        if other_payments:
            match_labels.append('其他梯号')
        payment_match = '+'.join(match_labels) if match_labels else '未匹配'

        dates = sorted(
            item.payment_date for item in contract_payments if item.payment_date
        )
        ladder_nos = sorted({
            normalize_text(row.get('ladder_no')) for row in rows if row.get('ladder_no')
        })
        modules = sorted({
            normalize_text(row.get('module_name')) for row in rows if row.get('module_name')
        })
        projects = sorted({
            normalize_text(row.get('project_name')) for row in rows if row.get('project_name')
        })
        ladder_payment_wan = round(sum(
            (item.payment_amount_rmb or 0) for item in ladder_payments
        ) / 10000.0, 2)
        contract_payment_wan = round(sum(
            (item.payment_amount_rmb or 0) for item in contract_level_payments
        ) / 10000.0, 2)
        other_payment_wan = round(sum(
            (item.payment_amount_rmb or 0) for item in other_payments
        ) / 10000.0, 2)
        amount = round(ladder_payment_wan + contract_payment_wan + other_payment_wan, 2)
        ledger_amount = round(sum(_number(row.get('amount_wan')) for row in rows), 2)
        ratio_amount_rmb = 0.0
        paid_equivalent_rmb = 0.0
        ratio_sources = []
        for row in rows:
            ratio = _payment_ratio_value(row.get('payment_ratio'))
            if ratio is not None:
                row_amount_rmb = _number(row.get('amount_rmb'))
                ratio_amount_rmb += row_amount_rmb
                paid_equivalent_rmb += row_amount_rmb * ratio
            source = row.get('payment_ratio_source') or ''
            if source:
                ratio_sources.append(source)
        contract_ratio = None
        if ratio_amount_rmb > 0:
            contract_ratio = _payment_ratio_value(
                paid_equivalent_rmb / ratio_amount_rmb
            )
        calc_source_count = sum(
            1 for source in ratio_sources if source.startswith('回款计算')
        )
        if ratio_sources and calc_source_count == len(ratio_sources):
            ratio_source = '回款计算汇总'
        elif calc_source_count:
            ratio_source = '回款计算 + 台账回退'
        elif ratio_sources:
            ratio_source = '台账比例汇总'
        else:
            ratio_source = ''
        result_rows.append({
            'contract_no': contract_no,
            'module_name': '、'.join(modules),
            'project_name': '、'.join(projects[:2]) + ('等' if len(projects) > 2 else ''),
            'ladder_count': len(ladder_nos),
            'ladder_nos': '、'.join(ladder_nos[:8]) + ('等' if len(ladder_nos) > 8 else ''),
            'ledger_amount_wan': ledger_amount,
            'ladder_payment_wan': ladder_payment_wan,
            'contract_payment_wan': contract_payment_wan,
            'other_payment_wan': other_payment_wan,
            'payment_wan': amount,
            'payment_count': len(matched),
            'payment_match': payment_match,
            'first_payment_date': dates[0].isoformat() if dates else '',
            'last_payment_date': dates[-1].isoformat() if dates else '',
            'payment_ratio': _payment_ratio_label(contract_ratio),
            'payment_ratio_source': ratio_source,
        })

    if month:
        period = month
    elif time_scope == 'year':
        period = '%s年' % year
    else:
        period = '全部日期'
    total_ladder = round(sum(row['ladder_payment_wan'] for row in result_rows), 2)
    total_contract = round(sum(row['contract_payment_wan'] for row in result_rows), 2)
    total_other = round(sum(row['other_payment_wan'] for row in result_rows), 2)
    total_payment = round(total_ladder + total_contract + total_other, 2)
    matched_count = sum(1 for row in result_rows if row['payment_count'])
    facts = _contract_payment_facts(result_rows, period, matched_count)
    return {
        'kind': 'contract_payment',
        'scope_label': scope['label'],
        'period': period,
        'message': (
            '共匹配 %s 个合同，其中 %s 个有回款记录；'
            '梯号级回款 %s 万元，合同级回款 %s 万元，其他梯号回款 %s 万元，合计 %s 万元。'
        ) % (
            len(result_rows), matched_count, total_ladder, total_contract,
            total_other, total_payment
        ),
        'columns': CONTRACT_PAYMENT_COLUMNS,
        'rows': result_rows,
        'facts': facts,
        'notes': [
            '回款金额按人民币汇总，不展示逐笔日期、节点、付款方式或备注。',
            '梯号级、合同级和其他梯号回款分别列示，不做静默取舍；合计为三类记录相加。',
            '回款比例优先取发货梯号明细最近一次成功回款计算，并按合同金额加权汇总。',
            '未参与计算的梯号回退台账比例，结果中会标明“回款计算 + 台账回退”。',
            '查询前已通过台账确认合同归属，只统计当前账号权限范围内的合同。',
        ],
        'exportable': False,
    }


SUBMISSION_COLUMNS = [
    {'key': 'module_name', 'label': '模块'},
    {'key': 'month', 'label': '月份'},
    {'key': 'status_label', 'label': '提交状态'},
    {'key': 'submitted_at', 'label': '提交时间'},
    {'key': 'submitted_by_name', 'label': '提交人'},
    {'key': 'submission_version', 'label': '快照版本'},
    {'key': 'ship_selection_count', 'label': '发货勾选数'},
]


def submission_status(scope, args=None):
    """Check monthly forecast input submission status for scoped modules."""
    args = args or {}
    modules = requested_modules(scope, args.get('modules') or args.get('module'))
    month = _month(args.get('month')) or mf_svc.default_month()

    inputs = MonthlyInput.query.filter_by(data_month=month).filter(
        MonthlyInput.module_name.in_(modules)
    ).all()
    submissions = Submission.query.filter_by(data_month=month).filter(
        Submission.module_name.in_(modules)
    ).all()
    selections = ShipSelection.query.filter_by(data_month=month).filter(
        ShipSelection.module_name.in_(modules)
    ).all()

    input_map = {item.module_name: item for item in inputs}
    submission_map = {}
    for item in submissions:
        current = submission_map.get(item.module_name)
        if current is None or (item.version or 0) > (current.version or 0):
            submission_map[item.module_name] = item
    selection_count = {}
    for item in selections:
        selection_count[item.module_name] = selection_count.get(item.module_name, 0) + 1

    rows = []
    for module in modules:
        input_row = input_map.get(module)
        submission = submission_map.get(module)
        submitted = bool(input_row and input_row.status == 'submitted')
        status_label = '已提交' if submitted else ('草稿未提交' if input_row else '未填报')
        submitted_at = ''
        submitted_by_name = ''
        if input_row:
            submitted_by_name = input_row.updated_by_name or ''
            if input_row.submitted_at:
                submitted_at = input_row.submitted_at.strftime('%Y-%m-%d %H:%M:%S')
        if not submitted_at and submission and submission.submitted_at:
            submitted_at = submission.submitted_at.strftime('%Y-%m-%d %H:%M:%S')
            submitted_by_name = submission.submitted_by_name or submitted_by_name
        rows.append({
            'module_name': module,
            'month': month,
            'status_label': status_label,
            'submitted_at': submitted_at or '—',
            'submitted_by_name': submitted_by_name or '—',
            'submission_version': submission.version if submission else '—',
            'ship_selection_count': selection_count.get(module, 0),
        })

    submitted_count = sum(1 for row in rows if row['status_label'] == '已提交')
    return {
        'kind': 'submission_status',
        'scope_label': scope['label'],
        'period': month,
        'message': '%s 共检查 %s 个模块，其中 %s 个已提交。' % (
            month, len(rows), submitted_count
        ),
        'columns': SUBMISSION_COLUMNS,
        'rows': rows,
        'notes': [
            '“已提交”取单月填报状态；“快照版本”取该月最新提交快照。',
            '发货勾选数来自该月发货明细，仅作为提交完整性参考。',
        ],
        'exportable': False,
    }


SOURCE_CATALOG = {
    'performance': [
        ('签单、合同、梯号', 'cc_ledger_contract', '台账合同与梯号明细'),
        ('模块归属', 'cc_country_mapping', '国家到模块、大区和业务员映射'),
        ('年度目标', 'cc_annual_target', '年度签单、排产、发货、回款目标'),
        ('实际回款', 'cc_payment_collection', '回款明细汇总'),
        ('月度填报', 'mf_monthly_input', '单月签单、排产、回款预计'),
        ('商贸数据', 'cc_trade_module_data', '商贸模块汇总数据'),
        ('发货额数据', 'cc_shipment_data', '年度发货额和台数'),
    ],
    'ladders': [
        ('合同、梯号、签排发日期', 'cc_ledger_contract', '台账合同与梯号明细'),
        ('模块归属', 'cc_country_mapping', '国家到模块映射'),
        ('回款计算批次', 'st_payment_calc_run', '最近一次成功回款计算的批次与统计'),
        ('梯号回款计算结果', 'st_payment_calc_detail', '梯号计算比例、已回款和台账回退状态'),
    ],
    'ladder_status': [
        ('合同和梯号', 'cc_ledger_contract', '台账基础信息与产品状态'),
        ('回款', 'cc_payment_collection', '合同级或梯号级回款汇总'),
        ('单月发货勾选', 'mf_ship_selection', '该月填报选中的发货梯号'),
        ('发货计划', 'st_plan_item', '计划版本与预计发货日期'),
        ('每日实发', 'st_tracking_item', '实际发货和订舱跟踪'),
        ('梯号回款计算结果', 'st_payment_calc_detail', '梯号回款比例及其计算状态'),
    ],
    'diagnose': [
        ('台账与产品状态', 'cc_ledger_contract', '判断作废、排产和发货日期'),
        ('国家模块映射', 'cc_country_mapping', '判断模块归属'),
        ('候选池选择', 'mf_ship_selection', '判断是否已经勾选'),
    ],
    'contract_payment': [
        ('合同归属', 'cc_ledger_contract', '先确认合同和梯号在当前权限范围内'),
        ('回款汇总', 'cc_payment_collection', '按合同号汇总人民币回款'),
        ('梯号回款计算结果', 'st_payment_calc_detail', '按合同金额加权汇总梯号回款比例'),
    ],
    'submission_status': [
        ('单月填报', 'mf_monthly_input', '当前填报状态与提交时间'),
        ('提交快照', 'mf_submission', '每次提交保留的版本快照'),
        ('发货勾选', 'mf_ship_selection', '该月已选择的发货梯号'),
    ],
}


def data_source(scope, args=None):
    """Explain the fixed database tables behind a read-only assistant action."""
    args = args or {}
    topic = normalize_text(args.get('topic')) or 'general'
    items = SOURCE_CATALOG.get(topic)
    if not items:
        items = []
        seen = set()
        for source_items in SOURCE_CATALOG.values():
            for item in source_items:
                if item[1] not in seen:
                    seen.add(item[1])
                    items.append(item)
    rows = [
        {'data_name': name, 'table_name': table, 'description': description}
        for name, table, description in items
    ]
    return {
        'kind': 'data_source',
        'scope_label': scope['label'],
        'message': '本次说明来自后端固定的数据来源清单；助手只通过只读工具访问这些表。',
        'columns': [
            {'key': 'data_name', 'label': '数据内容'},
            {'key': 'table_name', 'label': '来源表'},
            {'key': 'description', 'label': '用途'},
        ],
        'rows': rows,
        'notes': [
            '模型不会直接连接数据库，也不会生成或执行任意 SQL。',
            '权限过滤在查询合同、梯号和回款之前由后端完成。',
        ],
        'exportable': False,
    }
