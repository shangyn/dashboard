"""模块经营明细 — 只读汇总、梯号明细与回款明细。"""
import datetime as dt
import io
from collections import defaultdict

from sqlalchemy import or_

from dashboards.contract_completion.constants import MODULE_REGION, REGION_DISPLAY
from dashboards.contract_completion.models import LedgerContract, PaymentCollection
from dashboards.contract_completion.services import AZT_MODULE_MAP, get_annual_completion
from monthly_forecast.models import UserScope
from monthly_forecast import services as mf_svc
from ship_tracking.excel_reader import canonical_ladder, normalize_text
from ship_tracking.models import TrackingItem

PERMISSION = 'module_business_detail'
BUSINESS_ROLE = '单月签排发填报'

ANNUAL_METRICS = (
    'sign_units', 'sign_amount', 'schedule_units', 'schedule_amount',
    'ship_units', 'ship_amount', 'payment_amount',
)
MONTH_METRICS = (
    'sign_units', 'sign_amount', 'prod_units', 'prod_amount',
    'ship_units', 'ship_amount', 'payment_amount',
)


def _safe_ratio(numerator, denominator):
    if not denominator:
        return 0.0
    return round(float(numerator or 0) / float(denominator), 4)


def _iso(value):
    return value.strftime('%Y-%m-%d') if value else ''


def _ratio(value):
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


def _ratio_label(value):
    return '—' if value is None else '%.2f%%' % (value * 100.0)


def _month_range(month):
    try:
        year, month_no = [int(part) for part in str(month).split('-')]
        start = dt.date(year, month_no, 1)
    except (TypeError, ValueError):
        raise ValueError('月份格式不正确，应为 YYYY-MM')
    if month_no == 12:
        end = dt.date(year + 1, 1, 1)
    else:
        end = dt.date(year, month_no + 1, 1)
    return start, end


def _year_range(year):
    return dt.date(int(year), 1, 1), dt.date(int(year) + 1, 1, 1)


def _year_value(value):
    try:
        year = int(value)
    except (TypeError, ValueError):
        raise ValueError('年份格式不正确，应为 YYYY')
    if not 2000 <= year <= 2100:
        raise ValueError('年份格式不正确，应为 YYYY')
    return year


def _empty_metrics(keys):
    return {key: 0.0 for key in keys}


def _is_business_user(user):
    return bool(user and user.role and user.role.role_name == BUSINESS_ROLE)


def _scoped_modules(user):
    if not user:
        return []
    rows = UserScope.query.filter_by(user_id=user.id).order_by(UserScope.module_name).all()
    return [row.module_name for row in rows if row.module_name]


def visible_modules(user):
    """返回 (可见模块, 是否仅限本人模块)。"""
    if not user or not user.role:
        return [], True
    if _is_business_user(user):
        return _scoped_modules(user), True
    return mf_svc.all_modules(), False


def _resolve_modules(user, requested):
    modules, scoped = visible_modules(user)
    if scoped and not modules:
        raise PermissionError('当前账号没有模块归属')
    requested = normalize_text(requested)
    if requested:
        if requested not in modules:
            raise PermissionError('无权限查看该模块')
        return [requested], scoped
    return modules, scoped


def _ledger_contracts():
    return LedgerContract.query.filter(
        LedgerContract.source == 'ledger',
        or_(
            LedgerContract.product_status == None,  # noqa: E711
            LedgerContract.product_status != '已作废',
        ),
    ).all()


def _module_maps(contracts, module_map):
    contract_modules = defaultdict(set)
    ladder_modules = {}
    contract_detail = {}
    for contract in contracts:
        module = mf_svc.resolve_module(contract, module_map)
        if not module:
            continue
        if contract.contract_no:
            contract_modules[contract.contract_no].add(module)
            contract_detail.setdefault(contract.contract_no, contract)
        key = canonical_ladder(contract.ladder_no or '')
        if key:
            if key in ladder_modules and ladder_modules[key] != module:
                ladder_modules[key] = None
            else:
                ladder_modules[key] = module
    return contract_modules, ladder_modules, contract_detail


def _annual_payment_contract_map(module_map):
    """回款模块归属与两年对比保持一致：合同号 → 模块。"""
    contract_modules = {}
    contracts = LedgerContract.query.filter(LedgerContract.source == 'ledger').all()
    for contract in contracts:
        if not contract.contract_no or not contract.country:
            continue
        if contract.product_type and '改造' in str(contract.product_type):
            contract_modules[contract.contract_no] = '改造'
        else:
            module = module_map.get(contract.country)
            if module:
                contract_modules[contract.contract_no] = module
    contract_modules.update(AZT_MODULE_MAP)
    return contract_modules


def _annual_payment_query(start, end):
    return PaymentCollection.query.filter(
        PaymentCollection.payment_date >= start,
        PaymentCollection.payment_date < end,
        ~PaymentCollection.node_type.in_(['抵佣金', '手续费']),
        PaymentCollection.agent_name != '新加坡分公司(关联方)',
        ~PaymentCollection.contract_no.like('DHN%'),
        ~PaymentCollection.contract_no.like('YBN%'),
    )


def _payment_module(payment, annual_contract_modules):
    return annual_contract_modules.get(payment.contract_no or '') or ''


def _monthly_actual(modules, month):
    start, end = _month_range(month)
    module_set = set(modules)
    module_map = mf_svc.load_module_map()
    contracts = _ledger_contracts()
    annual_contract_modules = _annual_payment_contract_map(module_map)
    result = {module: _empty_metrics(MONTH_METRICS) for module in modules}

    for contract in contracts:
        module = mf_svc.resolve_module(contract, module_map)
        if module not in module_set:
            continue
        metrics = result[module]
        if contract.sign_date and start <= contract.sign_date < end:
            metrics['sign_units'] += contract.unit_count or 0
            metrics['sign_amount'] += contract.contract_amount_rmb or 0
        if contract.schedule_date and start <= contract.schedule_date < end:
            metrics['prod_units'] += contract.unit_count or 0
            metrics['prod_amount'] += contract.contract_amount_rmb or 0
        if contract.delivery_date and start <= contract.delivery_date < end:
            metrics['ship_units'] += contract.unit_count or 0
            metrics['ship_amount'] += contract.contract_amount_rmb or 0

    payments = _annual_payment_query(start, end).all()
    for payment in payments:
        module = _payment_module(payment, annual_contract_modules)
        if module in module_set:
            result[module]['payment_amount'] += payment.payment_amount_rmb or 0

    for metrics in result.values():
        for key in ('sign_amount', 'prod_amount', 'ship_amount', 'payment_amount'):
            metrics[key] = round((metrics[key] or 0) / 10000.0, 2)
        for key in ('sign_units', 'prod_units', 'ship_units'):
            metrics[key] = round(metrics[key] or 0, 2)
    return result


def _annual_entry(row):
    entry = {}
    for key in ANNUAL_METRICS:
        prefix = 'payment' if key == 'payment_amount' else key
        entry[key] = {
            'target': round(float(row.get(prefix + '_target') or 0), 2),
            'actual': round(float(row.get(prefix + '_actual') or 0), 2),
            'ratio': float(row.get(prefix + '_ratio') or 0),
        }
    return entry


def _month_plan_entry(row):
    return {
        'sign_units': row.get('sign_units') or 0,
        'sign_amount': row.get('sign_amount') or 0,
        'prod_units': row.get('prod_units') or 0,
        'prod_amount': row.get('prod_amount') or 0,
        'ship_units': row.get('ship_units') or 0,
        'ship_amount': row.get('ship_amount') or 0,
        'payment_amount': row.get('payment_amount') or 0,
        'status': row.get('status') or '',
        'submitted_at': row.get('submitted_at') or '',
        'updated_by_name': row.get('updated_by_name') or '',
    }


def get_context(user):
    modules, scoped = visible_modules(user)
    if scoped and not modules:
        raise PermissionError('当前账号没有模块归属')
    months = mf_svc.month_options()
    default_month = mf_svc.default_month()
    return {
        'modules': modules,
        'scoped': scoped,
        'months': months,
        'default_month': default_month,
        'year': dt.date.today().year,
        'user': {
            'id': user.id,
            'username': user.username or '',
            'real_name': user.real_name or '',
        },
        'role_name': user.role.role_name if user.role else '',
    }


def get_overview(user, month=None, module=None, year=None):
    month = normalize_text(month)
    year = _year_value(year or dt.date.today().year)
    modules, scoped = _resolve_modules(user, module)
    annual_data = get_annual_completion()
    annual_year = _year_value(annual_data.get('year') or year)
    annual_rows = {
        row.get('module'): row
        for row in annual_data.get('rows', [])
        if row.get('type') in ('data', 'trade') and row.get('module') in set(modules)
    }
    if month:
        plan_rows = {
            row.get('module_name'): row
            for row in mf_svc.get_summary(month, modules).get('rows', [])
        }
        actual_rows = _monthly_actual(modules, month)
    else:
        plan_rows = {}
        actual_rows = {}

    rows = []
    for module_name in modules:
        annual_row = annual_rows.get(module_name) or {}
        plan_row = plan_rows.get(module_name) or {}
        region = annual_row.get('region') or MODULE_REGION.get(module_name, '')
        rows.append({
            'module_name': module_name,
            'region': REGION_DISPLAY.get(region, region),
            'annual': _annual_entry(annual_row),
            'month_plan': _month_plan_entry(plan_row),
            'month_actual': {
                key: round((actual_rows.get(module_name) or {}).get(key, 0) or 0, 2)
                for key in MONTH_METRICS
            },
        })

    totals_annual = {}
    for key in ANNUAL_METRICS:
        actual = sum((row['annual'][key]['actual'] or 0) for row in rows)
        target = sum((row['annual'][key]['target'] or 0) for row in rows)
        totals_annual[key] = {
            'actual': round(actual, 2),
            'target': round(target, 2),
            'ratio': _safe_ratio(actual, target),
        }
    totals_plan = {
        key: round(sum((row['month_plan'][key] or 0) for row in rows), 2)
        for key in MONTH_METRICS
    }
    totals_actual = {
        key: round(sum((row['month_actual'][key] or 0) for row in rows), 2)
        for key in MONTH_METRICS
    }
    return {
        'month': month,
        'year': annual_year,
        'mode': 'month' if month else 'year',
        'period_label': month or ('%s年度' % annual_year),
        'data_date': annual_data.get('data_date') or '',
        'scoped': scoped,
        'modules': rows,
        'totals': {
            'annual': totals_annual,
            'month_plan': totals_plan,
            'month_actual': totals_actual,
        },
        'metric_config': annual_data.get('metric_config') or [],
    }


def _row_key(contract_no, ladder_no):
    key = canonical_ladder(ladder_no or '')
    return key or ('%s|%s' % (contract_no or '', ladder_no or ''))


def _tracking_status(item):
    if item.actual_ship_date:
        return 'shipped', '已发货'
    if item.plan_status == 'removed':
        return 'removed', '已移除'
    if item.expected_ship_date and item.expected_ship_date < dt.date.today():
        return 'overdue', '已逾期'
    if item.expected_ship_date or item.commit_status == 'committed':
        return 'committed', '已提交待发货'
    return 'pending', '未提交待发货'


def _commit_label(value):
    return {
        'committed': '已提交',
        'withdrawn': '已撤回',
    }.get(value or '', '未提交')


def _build_ladder_rows(modules):
    module_set = set(modules)
    module_map = mf_svc.load_module_map()
    contracts = _ledger_contracts()
    rows_by_key = {}

    for contract in contracts:
        module = mf_svc.resolve_module(contract, module_map)
        if module not in module_set:
            continue
        key = _row_key(contract.contract_no, contract.ladder_no)
        if key in rows_by_key:
            continue
        ratio = _ratio(contract.payment_ratio)
        rows_by_key[key] = {
            'ladder_key': key,
            'contract_no': contract.contract_no or '',
            'ladder_no': contract.ladder_no or '',
            'module_name': module,
            'project_name': contract.project_name or '',
            'country': contract.country or '',
            'region': contract.mapped_region or contract.business_region or '',
            'salesperson': contract.salesperson or '',
            'currency': contract.currency or '',
            'unit_count': contract.unit_count or 0,
            'amount_wan': round((contract.contract_amount_rmb or 0) / 10000.0, 2),
            'payment_ratio': ratio,
            'payment_ratio_label': _ratio_label(ratio),
            'sign_date': _iso(contract.sign_date),
            'schedule_date': _iso(contract.schedule_date),
            'schedule_finish_date': _iso(contract.schedule_finish_date),
            'delivery_date': _iso(contract.delivery_date),
            'whole_ship_date': _iso(contract.whole_ship_date),
            'plan_month': '',
            'expected_ship_date': '',
            'actual_ship_date': _iso(contract.delivery_date),
            'commit_status': 'unplanned',
            'commit_label': '未提交',
            'booking_status': '',
            'business_remark': '',
            'plan_status': '',
            'status': 'shipped' if contract.delivery_date else 'ledger',
            'status_label': '已发货' if contract.delivery_date else '台账明细',
            'data_source': '台账',
        }

    items = TrackingItem.query.all()
    for item in items:
        key = _row_key(item.contract_no, item.ladder_no or item.ladder_key)
        row = rows_by_key.get(key)
        if row is None:
            if item.module_name not in module_set:
                continue
            ratio = _ratio(item.payment_ratio)
            status, status_label = _tracking_status(item)
            row = {
                'ladder_key': item.ladder_key or key,
                'contract_no': item.contract_no or '',
                'ladder_no': item.ladder_no or '',
                'module_name': item.module_name or '',
                'project_name': item.project_name or '',
                'country': '',
                'region': item.business_region or '',
                'salesperson': item.salesperson or '',
                'currency': '',
                'unit_count': item.unit_count or 0,
                'amount_wan': round((item.amount_rmb or 0) / 10000.0, 2),
                'payment_ratio': ratio,
                'payment_ratio_label': _ratio_label(ratio),
                'sign_date': '',
                'schedule_date': '',
                'schedule_finish_date': _iso(item.schedule_finish_date),
                'delivery_date': '',
                'whole_ship_date': _iso(item.whole_ship_date),
                'plan_month': item.plan_month or '',
                'expected_ship_date': _iso(item.expected_ship_date),
                'actual_ship_date': _iso(item.actual_ship_date),
                'commit_status': item.commit_status or 'unplanned',
                'commit_label': _commit_label(item.commit_status),
                'booking_status': item.booking_status or '',
                'business_remark': item.business_remark or '',
                'plan_status': item.plan_status or '',
                'status': status,
                'status_label': status_label,
                'data_source': '计划',
            }
            rows_by_key[key] = row
            continue

        ratio = _ratio(item.payment_ratio)
        if ratio is not None:
            row['payment_ratio'] = ratio
            row['payment_ratio_label'] = _ratio_label(ratio)
        status, status_label = _tracking_status(item)
        row.update({
            'plan_month': item.plan_month or '',
            'expected_ship_date': _iso(item.expected_ship_date),
            'actual_ship_date': _iso(item.actual_ship_date) or row.get('actual_ship_date', ''),
            'commit_status': item.commit_status or 'unplanned',
            'commit_label': _commit_label(item.commit_status),
            'booking_status': item.booking_status or '',
            'business_remark': item.business_remark or '',
            'plan_status': item.plan_status or '',
            'status': status,
            'status_label': status_label,
            'data_source': '台账+计划',
        })

    rows = [
        row for row in rows_by_key.values()
        if row.get('plan_status') != 'removed' or row.get('actual_ship_date')
    ]
    rows.sort(key=lambda row: (
        row.get('module_name') or '',
        row.get('expected_ship_date') or '9999-12-31',
        row.get('ladder_no') or '',
    ))
    return rows


def _matches_month(row, month):
    if not month:
        return True
    for key in (
        'plan_month', 'expected_ship_date', 'actual_ship_date', 'delivery_date',
        'schedule_date', 'sign_date', 'schedule_finish_date', 'whole_ship_date',
    ):
        value = row.get(key) or ''
        if value[:7] == month:
            return True
    return False


def _matches_year(row, year):
    if not year:
        return True
    prefix = str(year)
    for key in (
        'plan_month', 'expected_ship_date', 'actual_ship_date', 'delivery_date',
        'schedule_date', 'sign_date', 'schedule_finish_date', 'whole_ship_date',
    ):
        value = row.get(key) or ''
        if value[:4] == prefix:
            return True
    return False


def _filter_ladder_rows(rows, month='', year=None, module='', keyword=''):
    month = normalize_text(month)
    module = normalize_text(module)
    keyword = normalize_text(keyword).upper()
    result = []
    for row in rows:
        if module and row.get('module_name') != module:
            continue
        if month and not _matches_month(row, month):
            continue
        if not month and not _matches_year(row, year):
            continue
        if keyword:
            text = ' '.join([
                row.get('contract_no') or '', row.get('ladder_no') or '',
                row.get('project_name') or '', row.get('module_name') or '',
                row.get('country') or '', row.get('salesperson') or '',
                row.get('business_remark') or '',
            ]).upper()
            if keyword not in text:
                continue
        result.append(row)
    return result


def _paginate(rows, page, page_size):
    page = max(1, int(page or 1))
    raw_size = page_size
    if raw_size in (0, '0', 'all', None, ''):
        return rows, page, len(rows)
    size = max(1, int(raw_size))
    start = (page - 1) * size
    return rows[start:start + size], page, size


def get_ladders(user, month=None, year=None, module=None, keyword='', page=1, page_size=50):
    month = normalize_text(month)
    year = _year_value(year or dt.date.today().year)
    modules, scoped = _resolve_modules(user, module)
    rows = _filter_ladder_rows(
        _build_ladder_rows(modules),
        month=month,
        year=None if month else year,
        module=module,
        keyword=keyword,
    )
    summary = {
        'total': len(rows),
        'units': round(sum(row.get('unit_count') or 0 for row in rows), 2),
        'shipped': sum(1 for row in rows if row.get('actual_ship_date')),
        'shipped_units': round(sum(
            row.get('unit_count') or 0 for row in rows if row.get('actual_ship_date')
        ), 2),
        'overdue': sum(1 for row in rows if row.get('status') == 'overdue'),
    }
    page_rows, page, page_size = _paginate(rows, page, page_size)
    return {
        'rows': page_rows,
        'summary': summary,
        'page': page,
        'page_size': page_size,
        'scoped': scoped,
    }


def _build_payment_rows(user, month=None, year=None, module=None, include_unmatched=False):
    modules, scoped = _resolve_modules(user, module)
    module_set = set(modules)
    module_map = mf_svc.load_module_map()
    contracts = _ledger_contracts()
    _, _, contract_detail = _module_maps(contracts, module_map)
    annual_contract_modules = _annual_payment_contract_map(module_map)

    if month:
        start, end = _month_range(month)
    else:
        start, end = _year_range(year or dt.date.today().year)
    payments = _annual_payment_query(start, end).all()

    result = []
    for payment in payments:
        owner = _payment_module(payment, annual_contract_modules)
        if owner:
            if owner not in module_set:
                continue
        elif scoped or not include_unmatched:
            continue
        contract = contract_detail.get(payment.contract_no or '')
        result.append({
            'module_name': owner or '未匹配',
            'contract_no': payment.contract_no or '',
            'ladder_no': payment.ladder_no or '',
            'project_name': payment.project_name or (contract.project_name if contract else ''),
            'payment_date': _iso(payment.payment_date),
            'payment_amount_orig': round(payment.payment_amount_orig or 0, 2),
            'currency': payment.currency or '',
            'payment_amount_rmb': round(payment.payment_amount_rmb or 0, 2),
            'payment_amount_wan': round((payment.payment_amount_rmb or 0) / 10000.0, 2),
            'node_type': payment.node_type or '',
            'payment_method': payment.payment_method or '',
            'region': payment.region or '',
            'remark': payment.remark or '',
        })
    result.sort(key=lambda row: (row.get('payment_date') or '', row.get('contract_no') or ''), reverse=True)
    return result


def get_payments(user, month=None, year=None, module=None, keyword='', page=1, page_size=50):
    modules, scoped = _resolve_modules(user, module)
    rows = _build_payment_rows(
        user,
        month=month,
        year=year,
        module=module,
        include_unmatched=not scoped and not module,
    )
    keyword = normalize_text(keyword).upper()
    if keyword:
        rows = [
            row for row in rows
            if keyword in ' '.join([
                row.get('contract_no') or '', row.get('ladder_no') or '',
                row.get('project_name') or '', row.get('module_name') or '',
                row.get('remark') or '',
            ]).upper()
        ]
    summary = {
        'total': len(rows),
        'amount_rmb': round(sum(row.get('payment_amount_rmb') or 0 for row in rows), 2),
        'amount_wan': round(sum(row.get('payment_amount_wan') or 0 for row in rows), 2),
        'unmatched': sum(1 for row in rows if row.get('module_name') == '未匹配'),
    }
    page_rows, page, page_size = _paginate(rows, page, page_size)
    return {
        'rows': page_rows,
        'summary': summary,
        'page': page,
        'page_size': page_size,
        'scoped': scoped,
    }


def export_workbook(user, month=None, module=None, keyword='', year=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    overview = get_overview(user, month=month, module=module, year=year)
    ladders = get_ladders(
        user, month=month, year=overview.get('year'), module=module,
        keyword=keyword, page_size=0,
    )
    payments = get_payments(
        user, month=month, year=overview.get('year'), module=module,
        keyword=keyword, page_size=0,
    )

    workbook = Workbook()
    header_fill = PatternFill('solid', fgColor='DCE8F8')
    header_font = Font(bold=True, color='17365D')
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)

    sheet = workbook.active
    sheet.title = '经营概览'
    headers = [
        '模块', '大区', '年签单额', '年签单目标',
        '年排产额', '年发货额', '年回款额',
    ]
    if month:
        headers.extend([
            '本月计划签单额', '本月计划排产额', '本月计划发货额', '本月计划回款额',
            '本月实际签单额', '本月实际排产额', '本月实际发货额', '本月实际回款额',
        ])
    sheet.append(headers)
    for row in overview['modules']:
        annual = row['annual']
        plan = row['month_plan']
        actual = row['month_actual']
        values = [
            row['module_name'], row['region'],
            annual['sign_amount']['actual'], annual['sign_amount']['target'],
            annual['schedule_amount']['actual'], annual['ship_amount']['actual'],
            annual['payment_amount']['actual'],
        ]
        if month:
            values.extend([
                plan['sign_amount'], plan['prod_amount'], plan['ship_amount'], plan['payment_amount'],
                actual['sign_amount'], actual['prod_amount'], actual['ship_amount'], actual['payment_amount'],
            ])
        sheet.append(values)
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center
    sheet.freeze_panes = 'A2'

    sheet = workbook.create_sheet('梯号明细')
    headers = [
        '模块', '合同号', '梯号', '项目名称', '国家', '大区', '业务员', '台数', '金额(万元)',
        '币种', '回款比例', '签订日期', '排产日期', '排产完工日期', '整梯发货日期',
        '计划月份', '预计发货日期', '实际发货日期', '提交状态', '订舱状态', '业务备注',
    ]
    sheet.append(headers)
    for row in ladders['rows']:
        sheet.append([
            row['module_name'], row['contract_no'], row['ladder_no'], row['project_name'],
            row['country'], row['region'], row['salesperson'], row['unit_count'],
            row['amount_wan'], row['currency'], row['payment_ratio_label'], row['sign_date'],
            row['schedule_date'], row['schedule_finish_date'], row['whole_ship_date'],
            row['plan_month'], row['expected_ship_date'], row['actual_ship_date'],
            row['commit_label'], row['booking_status'], row['business_remark'],
        ])
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center
    sheet.freeze_panes = 'A2'

    sheet = workbook.create_sheet('回款明细')
    headers = [
        '模块', '合同号', '梯号', '项目名称', '回款日期', '原币金额', '币种',
        '人民币金额', '折万元', '节点', '付款方式', '大区', '备注',
    ]
    sheet.append(headers)
    for row in payments['rows']:
        sheet.append([
            row['module_name'], row['contract_no'], row['ladder_no'], row['project_name'],
            row['payment_date'], row['payment_amount_orig'], row['currency'],
            row['payment_amount_rmb'], row['payment_amount_wan'], row['node_type'],
            row['payment_method'], row['region'], row['remark'],
        ])
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center
    sheet.freeze_panes = 'A2'

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output
