"""发货梯号追踪 - 权限、周填报、实发、查询与导出服务。"""
import datetime as dt
import io
import json
from collections import Counter, defaultdict

from flask import current_app
from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError

from models import db, User
from monthly_forecast.models import UserScope
from ship_tracking.models import (
    AuditLog, BookingRecord, DailyShipment, ImportBatch, TrackingItem,
)
from ship_tracking.excel_reader import (
    canonical_ladder, normalize_text, parse_excel_date, parse_ladder_batch,
)
from ship_tracking.regions import build_region_map

PERMISSION = 'ship_tracking'
VIEW_PERMISSION = 'ship_tracking_view'
DAILY_PERMISSION = 'ship_tracking_daily_edit'
ADMIN_PERMISSION = 'ship_tracking_admin'

STATUS_LABELS = {
    'shipped': '已发货',
    'overdue': '已逾期',
    'committed': '已提交待发货',
    'pending': '未提交待发货',
    'removed': '计划已移除',
}

FLAG_LABELS = {
    'duplicate_source': '源表重复行',
    'module_mapped': '模块归属已修正',
    'invalid_expected_date': '源表业务预计时间不是有效日期',
    'used_whole_ship_date': '参考整梯发货日期（旧口径）',
    'expected_from_seven_day': '7日前发货作为预计日期',
    'missing_expected_date': '缺少预计发货日期',
    'missing_project': '缺少项目名称',
    'committed_plan_changed': '计划日期与已提交承诺不一致',
    'plan_removed_shipped': '计划已移除但已实发',
    'plan_removed_booked': '有订舱但当前计划已移除',
    'plan_removed_committed': '已提交后计划被移除',
    'plan_external_actual': '计划外实发',
    'date_corrected': '日期已修正',
    'manual_added': '业务手工新增',
    'from_monthly_forecast': '来自单月填报',
    'restored_from_forecast': '单月填报恢复',
    'forecast_module_mismatch': '台账模块与填报模块不一致',
}


class ManualAddConflict(ValueError):
    """手工新增需要前端二次确认的冲突（如恢复已移除计划）。"""

    def __init__(self, message, code='', data=None):
        super().__init__(message)
        self.code = code
        self.data = data or {}


def today():
    return dt.date.today()


def week_start(value=None):
    value = value or today()
    return value - dt.timedelta(days=value.weekday())


def target_week_start(value=None):
    return week_start(value) + dt.timedelta(days=7)


def week_end(start):
    return start + dt.timedelta(days=6)


def month_start(value=None):
    value = value or today()
    return value.replace(day=1)


def next_month_start(value=None):
    start = month_start(value)
    if start.month == 12:
        return dt.date(start.year + 1, 1, 1)
    return dt.date(start.year, start.month + 1, 1)


def month_end(value=None):
    return next_month_start(value) - dt.timedelta(days=1)


def fill_window(value=None):
    current = value or today()
    next_start = next_month_start(current)
    if current >= next_start - dt.timedelta(days=7):
        default_date = next_start
        end = month_end(next_start)
    else:
        default_date = month_start(current)
        end = month_end(current)
    return {
        'start': current,
        'end': end,
        'month': default_date.strftime('%Y-%m'),
        'default_date': default_date,
    }


def iso(value):
    if not value:
        return ''
    if isinstance(value, dt.datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return value.strftime('%Y-%m-%d')


def normalize_month(value):
    text_value = normalize_text(value)
    if not text_value:
        return ''
    import re
    match = re.match(r'^(\d{4})[-/.年](\d{1,2})', text_value)
    if not match:
        return ''
    month = int(match.group(2))
    if month < 1 or month > 12:
        return ''
    return '%s-%02d' % (match.group(1), month)


def permissions_of(user):
    if not user or not user.role:
        return []
    return user.role.get_permissions()


def is_admin(user):
    return bool(user and user.role and user.role.is_admin)


def is_monthly_fill_role(user):
    return bool(user and user.role and user.role.role_name == '单月签排发填报')


def can_full_view(user):
    if not user:
        return False
    if is_admin(user):
        return True
    # 只有「单月签排发填报」固定角色走填报页；其余有查看权限的角色始终看全量。
    # 模块归属只决定填报数据范围，不再降级查看能力。
    if is_monthly_fill_role(user):
        return False
    return VIEW_PERMISSION in permissions_of(user)


def can_daily_edit(user):
    # 实发与计划填报严格分离；管理员也不能代替实发角色写入实际日期。
    if not user or is_monthly_fill_role(user):
        return False
    return DAILY_PERMISSION in permissions_of(user)


def can_admin(user):
    return is_admin(user) or ADMIN_PERMISSION in permissions_of(user)


def can_import(user):
    """导入管理面向所有可查看全量明细的角色开放。"""
    return bool(can_full_view(user) or can_admin(user))


def scoped_modules(user):
    if not user:
        return []
    rows = UserScope.query.filter_by(user_id=user.id).order_by(UserScope.module_name).all()
    return [row.module_name for row in rows if row.module_name]


def all_modules():
    values = set()
    for (name,) in db.session.query(TrackingItem.module_name).distinct().all():
        if name:
            values.add(name)
    for (name,) in db.session.query(UserScope.module_name).distinct().all():
        if name:
            values.add(name)
    return sorted(values)


def month_options():
    values = [row[0] for row in db.session.query(TrackingItem.plan_month).distinct().all() if row[0]]
    return sorted(values, reverse=True)


def default_month():
    months = month_options()
    return months[0] if months else today().strftime('%Y-%m')


def _loads(value, default=None):
    if default is None:
        default = {}
    try:
        if value is None or value == '':
            return default
        return json.loads(value)
    except Exception:
        return default


def _dump(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def _audit(user, category, action, ladder_key='', batch_id=None, reason='',
           old_values=None, new_values=None):
    row = AuditLog(
        category=category,
        action=action,
        ladder_key=ladder_key or '',
        batch_id=batch_id,
        operator_id=user.id if user else None,
        operator_name=(user.real_name or user.username) if user else '系统',
        reason=reason or '',
        old_values=_dump(old_values or {}),
        new_values=_dump(new_values or {}),
    )
    db.session.add(row)
    return row


def build_context(user):
    modules = scoped_modules(user)
    perms = permissions_of(user)
    full_view = can_full_view(user)
    daily = can_daily_edit(user)
    admin = can_admin(user)
    fill = bool(modules) and (is_monthly_fill_role(user) or 'monthly_forecast' in perms or PERMISSION in perms)
    fill_period = fill_window()
    if full_view:
        mode = 'tracking'
    elif modules:
        mode = 'fill'
    else:
        mode = 'none'
    return {
        'mode': mode,
        'can_fill': fill,
        'can_full_view': full_view,
        'can_daily_edit': daily,
        'can_admin': admin,
        'can_import': can_import(user),
        'my_modules': modules,
        'modules': all_modules() if full_view else modules,
        'months': month_options(),
        'default_month': default_month(),
        'today': iso(today()),
        'current_week_start': iso(week_start()),
        'target_week_start': iso(target_week_start()),
        'target_week_end': iso(week_end(target_week_start())),
        'fill_month': fill_period['month'],
        'fill_start': iso(fill_period['start']),
        'fill_end': iso(fill_period['end']),
        'fill_default_date': iso(fill_period['default_date']),
        'role_name': user.role.role_name if user and user.role else '',
        'user': {
            'id': user.id,
            'username': user.username or '',
            'real_name': user.real_name or '',
        },
    }


def _require_owned_module(user, requested):
    modules = scoped_modules(user)
    if not modules:
        raise ValueError('当前账号没有模块填报归属')
    requested = normalize_text(requested)
    if not requested:
        if len(modules) == 1:
            return modules[0]
        raise ValueError('请选择模块')
    if requested not in modules:
        raise ValueError('无权限操作该模块')
    return requested


def _payment_ratio_value(value):
    """台账 BN 回款比例：空值不当作 0，达到 1 统一按 100% 处理。"""
    if value is None or value == '':
        return None
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return None
    if ratio < 0:
        ratio = 0.0
    if ratio >= 1:
        ratio = 1.0
    return ratio


def _payment_ratio_label(value):
    if value is None:
        return '—'
    return '%.2f%%' % (value * 100.0)


def _tracking_dict(item, region='', region_source=''):
    expected = item.expected_ship_date
    flags = item.flags()
    if item.actual_ship_date:
        status = 'shipped'
    elif item.plan_status == 'removed':
        status = 'removed'
    elif expected and expected < today():
        status = 'overdue'
    elif expected or item.commit_status == 'committed':
        # 有预计发货日期（计划导入自带或业务填写）且未发货，就算已提交待发货；
        # 完全没有预计日期的才落到未提交待发货。
        status = 'committed'
    else:
        status = 'pending'
    plan_week = week_start(expected) if expected else None
    payment_ratio = _payment_ratio_value(getattr(item, 'payment_ratio', None))
    return {
        'id': item.id,
        'ladder_key': item.ladder_key or '',
        'contract_no': item.contract_no or '',
        'ladder_no': item.ladder_no or '',
        'module_name': item.module_name or '',
        'region': region or '',
        'region_source': region_source or '',
        'project_name': item.project_name or '',
        'business_region': item.business_region or '',
        'salesperson': item.salesperson or '',
        'unit_count': item.unit_count or 0,
        'amount_wan': round((item.amount_rmb or 0) / 10000.0, 2),
        'amount_rmb': item.amount_rmb or 0,
        'payment_ratio': payment_ratio,
        'payment_ratio_raw': getattr(item, 'payment_ratio', None),
        'payment_ratio_label': _payment_ratio_label(payment_ratio),
        'payment_ratio_group': (
            '100' if payment_ratio is not None and payment_ratio >= 1 else 'other'
        ),
        'payment_ratio_source': 'ledger_bn' if payment_ratio is not None else '',
        'source': item.source or '',
        'reporter': item.reporter or '',
        'business_expected_raw': item.business_expected_raw or '',
        'schedule_finish_date': iso(item.schedule_finish_date),
        'whole_ship_date': iso(item.whole_ship_date),
        'original_expected_ship_date': iso(item.original_expected_ship_date),
        'expected_ship_date': iso(expected),
        'draft_expected_ship_date': iso(item.draft_expected_ship_date),
        'committed_expected_ship_date': iso(item.committed_expected_ship_date),
        'committed_week_start': iso(item.committed_week_start),
        'committed_on_week_start': iso(item.committed_on_week_start),
        'plan_week': iso(plan_week),
        'plan_month': item.plan_month or '',
        'plan_version': item.plan_version or 0,
        'plan_status': item.plan_status or '',
        'plan_change_count': item.plan_change_count or 0,
        'commit_status': item.commit_status or 'unplanned',
        'committed_at': iso(item.committed_at),
        'committed_by_name': item.committed_by_name or '',
        'actual_ship_date': iso(item.actual_ship_date),
        'actual_ship_source': item.actual_ship_source or '',
        'actual_ship_source_label': (
            '台账组A日期' if item.actual_ship_source == 'ledger'
            else '系统每日实发' if item.actual_ship_source == 'daily'
            else ''
        ),
        'booking_status': item.booking_status or '未订舱',
        'booking_audit_status': item.booking_audit_status or '',
        'booking_record_count': item.booking_record_count or 0,
        'booking_last_date': iso(item.booking_last_date),
        'status': status,
        'status_label': STATUS_LABELS.get(status, status),
        'data_flags': flags,
        'flag_labels': [FLAG_LABELS.get(flag, flag) for flag in flags],
        'source_kind': item.source_kind or 'plan',
        'business_remark': item.business_remark or '',
    }


def _ledger_delivery_date(ladder_key):
    from dashboards.contract_completion.models import LedgerContract

    key = canonical_ladder(ladder_key)
    if not key:
        return None
    rows = LedgerContract.query.filter(
        LedgerContract.source == 'ledger',
        LedgerContract.ladder_no == key,
    ).all()
    if not rows:
        return None
    primary = max(rows, key=lambda row: row.contract_amount_rmb or 0)
    if primary.delivery_date:
        return primary.delivery_date
    for row in rows:
        if row.delivery_date:
            return row.delivery_date
    return None


def _resolve_weekly_modules(user, module_name=None):
    # 只有固定填报角色（或管理员权限）可以读写周计划；查看/实发角色即使
    # 误配了模块归属，也不能通过接口写填报数据。
    if not (is_monthly_fill_role(user) or can_admin(user)):
        raise PermissionError('当前角色无周填报权限')
    modules = scoped_modules(user)
    if not modules:
        raise ValueError('当前账号没有模块填报归属')
    requested = normalize_text(module_name)
    if requested and requested not in modules:
        raise ValueError('无权限操作该模块')
    return [requested] if requested else modules


def add_weekly_ladder(user, payload):
    """业务按登记台账手工补录一个梯号到当前月追踪计划。

    按用户确认：梯号必须已在台账中（source='ledger'），不允许先录入；
    台账已作废、台账解析不出模块、模块不在本人填报范围，一律拒绝。
    已移除的历史行需要 reactivate=True 才恢复，恢复时保留原日期/承诺/订舱。
    """
    payload = payload or {}
    modules = _resolve_weekly_modules(user, payload.get('module_name'))
    ladder_input = normalize_text(payload.get('ladder_no'))
    key = canonical_ladder(ladder_input)
    if not key:
        raise ValueError('请输入完整梯号')

    from dashboards.contract_completion.models import LedgerContract
    from monthly_forecast.services import GAIZAO_MODULE, load_module_map

    contract = LedgerContract.query.filter(
        LedgerContract.source == 'ledger',
        or_(
            LedgerContract.ladder_no == ladder_input,
            LedgerContract.ladder_no == key,
        ),
    ).order_by(LedgerContract.contract_amount_rmb.desc()).first()
    if contract is None:
        raise ValueError('台账中无此梯号，请先上传台账再添加')
    if (contract.product_status or '') == '已作废':
        raise ValueError('该梯号台账已作废，不能加入发货明细')

    module_map = load_module_map()
    owner = normalize_text(
        module_map.get(contract.country or '')
        or contract.mapped_module
        or contract.personal_module
        or (GAIZAO_MODULE if contract.product_type and GAIZAO_MODULE in str(contract.product_type) else '')
    )
    if not owner:
        raise ValueError('台账未解析出模块，无法判断填报范围')
    if owner not in modules:
        raise ValueError('该梯号台账归属模块「%s」，不在你的填报范围' % owner)
    requested = normalize_text(payload.get('module_name'))
    if requested and requested != owner:
        raise ValueError('模块与台账归属不一致（台账归属：%s）' % owner)

    key = canonical_ladder(contract.ladder_no) or key
    row = TrackingItem.query.filter_by(ladder_key=key).first()
    if row is not None:
        if row.actual_ship_date:
            raise ValueError('该梯号已实发，不能重复加入')
        if row.plan_status == 'active':
            raise ValueError('该梯号已在发货明细中')
        if not payload.get('reactivate'):
            raise ManualAddConflict(
                '该梯号曾在计划中，后被移除。是否恢复？',
                code='removed',
                data={
                    'ladder_key': key,
                    'ladder_no': row.ladder_no or contract.ladder_no or key,
                    'module_name': row.module_name or owner,
                },
            )
        flags = {flag for flag in row.flags() if not str(flag).startswith('plan_removed_')}
        flags.add('manual_added')
        row.set_flags(flags)
        row.plan_status = 'active'
        row.plan_removed_at = None
        row.plan_month = default_month()
        row.payment_ratio = contract.payment_ratio
        _audit(user, 'weekly', 'manual_add', key,
               old_values={'plan_status': 'removed'},
               new_values={'plan_status': 'active', 'module_name': row.module_name or owner,
                           'source': '手工新增'})
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise ValueError('该梯号已被并发添加，请刷新')
        return _tracking_dict(row)

    row = TrackingItem(
        ladder_key=key,
        plan_month=default_month(),
        plan_version=0,
        plan_batch_id=None,
        plan_status='active',
        contract_no=contract.contract_no or '',
        ladder_no=contract.ladder_no or ladder_input,
        module_name=owner,
        project_name=contract.project_name or '',
        business_region=contract.business_region or '',
        salesperson=contract.salesperson or '',
        unit_count=float(contract.unit_count or 1),
        amount_rmb=float(contract.contract_amount_rmb or 0),
        payment_ratio=contract.payment_ratio,
        source='手工新增',
        reporter=(user.real_name or user.username or '') if user else '',
        business_expected_raw='',
        schedule_finish_date=contract.schedule_finish_date,
        whole_ship_date=contract.whole_ship_date,
        original_expected_ship_date=None,
        expected_ship_date=None,
        commit_status='unplanned',
        booking_status='未订舱',
        source_kind='manual',
    )
    row.set_flags({'manual_added'})
    db.session.add(row)
    _audit(user, 'weekly', 'manual_add', key,
           new_values={
               'module_name': owner,
               'contract_no': contract.contract_no or '',
               'source': '手工新增',
           })
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('该梯号已被并发添加，请刷新')
    return _tracking_dict(row)


def get_weekly(user, module_name=None, include_future=None, keyword=''):
    """返回候选池和本模块整体发货明细。

    候选池只显示未进入整体明细的待填报梯号：有效计划、未发货、未提交且
    没有预计发货日期。下方整体发货明细包含本模块已有预计日期、已提交或
    已实发的梯号，并明确排除候选池，避免同一梯号上下重复。

    include_future 参数保留只是为了兼容旧前端传参，已不参与过滤。
    """
    modules = _resolve_weekly_modules(user, module_name)
    # 模块下拉里的条数要覆盖「我的全部模块」，否则选中一个模块后，
    # 其他模块的选项会被算成 0 条，看起来像失败。
    count_modules = _resolve_weekly_modules(user, '')
    target = target_week_start()
    window = fill_window()
    current = today()
    rows = TrackingItem.query.filter(
        TrackingItem.module_name.in_(count_modules),
    ).all()
    visible_modules = set(modules)
    candidates = []
    submitted = []
    draft = []
    module_counts = {}

    def bump(module, field):
        entry = module_counts.setdefault(
            module or '', {'candidates': 0, 'submitted': 0})
        entry[field] += 1

    for item in rows:
        visible = item.module_name in visible_modules
        if item.actual_ship_date:
            if visible:
                submitted.append(item)
            bump(item.module_name, 'submitted')
            continue
        # 已移除且未实发的计划不进入业务视角；已实发的仍保留在下方明细。
        if item.plan_status != 'active':
            continue
        if item.commit_status == 'committed' or item.expected_ship_date:
            if visible:
                submitted.append(item)
            bump(item.module_name, 'submitted')
            continue
        if visible:
            # 只认可填窗口内的草稿；窗口外的旧草稿不再预填，避免带出过期日期。
            if (item.draft_expected_ship_date
                    and window['start'] <= item.draft_expected_ship_date <= window['end']):
                draft.append(item)
            candidates.append(item)
        bump(item.module_name, 'candidates')

    def matches(item):
        text_value = normalize_text(keyword).upper()
        if not text_value:
            return True
        haystack = ' '.join([
            item.module_name or '', item.contract_no or '', item.ladder_no or '',
            item.project_name or '',
        ]).upper()
        return text_value in haystack

    candidates = [item for item in candidates if matches(item)]
    draft = [item for item in draft if matches(item)]
    submitted = [item for item in submitted if matches(item)]
    def history_sort_key(item):
        if item.actual_ship_date:
            return (
                1, item.module_name or '', -item.actual_ship_date.toordinal(),
                item.ladder_key or '',
            )
        return (
            0, item.module_name or '', item.expected_ship_date or dt.date.max,
            item.ladder_key or '',
        )

    submitted.sort(key=history_sort_key)
    candidates.sort(key=lambda item: (
        item.module_name or '', item.expected_ship_date or dt.date.max, item.ladder_key or ''
    ))
    return {
        'module_name': normalize_text(module_name) or '全部我的模块',
        'modules': modules,
        'target_week_start': iso(target),
        'target_week_end': iso(week_end(target)),
        'fill_month': window['month'],
        'fill_start': iso(window['start']),
        'fill_end': iso(window['end']),
        'fill_default_date': iso(window['default_date']),
        'today': iso(current),
        'candidates': [_tracking_dict(item) for item in candidates],
        'submitted': [_tracking_dict(item) for item in submitted],
        'drafts': [_tracking_dict(item) for item in draft],
        'module_counts': module_counts,
    }


def _validate_week_items(user, module, items, target, require_committed=False):
    modules = _resolve_weekly_modules(user, module)
    window = fill_window()
    if not isinstance(items, list) or not items:
        raise ValueError('请选择梯号并填写预计发货日期')
    keys = []
    seen = set()
    for entry in items:
        key = canonical_ladder(entry.get('ladder_key') or entry.get('ladder_no') or '')
        if not key:
            raise ValueError('存在空梯号')
        if key in seen:
            raise ValueError('梯号 %s 在本批次重复' % key)
        seen.add(key)
        date_value = parse_excel_date(entry.get('expected_ship_date') or entry.get('ship_date'))
        if not date_value:
            raise ValueError('梯号 %s 未选择预计发货日期' % key)
        if date_value < window['start'] or date_value > window['end']:
            raise ValueError('梯号 %s 的预计发货日期必须在 %s 至 %s 之间'
                             % (key, iso(window['start']), iso(window['end'])))
        keys.append((key, date_value))
    rows = TrackingItem.query.filter(TrackingItem.ladder_key.in_([key for key, _ in keys])).all()
    by_key = {row.ladder_key: row for row in rows}
    result = []
    for key, date_value in keys:
        row = by_key.get(key)
        if not row:
            raise ValueError('梯号 %s 不在当前月度计划中' % key)
        if row.module_name not in modules:
            raise ValueError('梯号 %s 不属于当前可填报模块' % key)
        if row.plan_status != 'active':
            raise ValueError('梯号 %s 的计划已移除，不能填报' % key)
        if row.actual_ship_date:
            raise ValueError('梯号 %s 已实发，不能修改周计划' % key)
        if require_committed and row.commit_status != 'committed':
            raise ValueError('梯号 %s 尚未提交' % key)
        if not require_committed and row.commit_status == 'committed':
            raise ValueError('梯号 %s 已提交，请在已提交区域处理' % key)
        result.append((row, date_value))
    return result


def save_weekly_draft(user, module_name, items, target_week=None):
    window = fill_window()
    pairs = _validate_week_items(user, module_name, items, window['start'])
    for row, date_value in pairs:
        old = _tracking_dict(row)
        # 草稿只记录在 draft_* 字段，不改预计发货日期：
        # 只有真正提交后才让全量页显示「已提交待发货」。
        row.draft_expected_ship_date = date_value
        row.draft_week_start = week_start(date_value)
        _audit(user, 'weekly', 'draft_save', row.ladder_key,
               old_values=old, new_values={'draft_expected_ship_date': iso(date_value)})
    db.session.commit()
    return {
        'saved': len(pairs),
        'target_week_start': iso(target_week_start()),
        'fill_month': window['month'],
        'fill_start': iso(window['start']),
        'fill_end': iso(window['end']),
    }


def save_weekly_remark(user, module_name, ladder_key, remark):
    """保存业务对整体发货明细中未发货梯号的最新备注。"""
    modules = _resolve_weekly_modules(user, module_name)
    key = canonical_ladder(ladder_key)
    if not key:
        raise ValueError('梯号不能为空')
    row = TrackingItem.query.filter_by(ladder_key=key).first()
    if row is None:
        raise ValueError('梯号 %s 不存在' % key)
    if row.module_name not in modules:
        raise ValueError('梯号 %s 不属于当前可填报模块' % key)
    if row.actual_ship_date:
        raise ValueError('梯号 %s 已发货，不能再修改备注' % key)
    if row.plan_status != 'active':
        raise ValueError('梯号 %s 的计划已移除，不能修改备注' % key)
    if row.commit_status != 'committed' and not row.expected_ship_date:
        raise ValueError('梯号 %s 尚未进入整体发货明细，不能填写备注' % key)

    remark_text = str(remark or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if len(remark_text) > 500:
        raise ValueError('备注不能超过 500 个字符')
    old_remark = row.business_remark or ''
    if old_remark == remark_text:
        return _tracking_dict(row)

    row.business_remark = remark_text
    _audit(
        user, 'weekly', 'remark_update', key,
        old_values={'business_remark': old_remark},
        new_values={'business_remark': remark_text},
    )
    db.session.commit()
    return _tracking_dict(row)


def submit_weekly(user, module_name, items, target_week=None):
    window = fill_window()
    pairs = _validate_week_items(user, module_name, items, window['start'])
    now = dt.datetime.now()
    submitted_week = week_start()
    for row, date_value in pairs:
        old = _tracking_dict(row)
        committed_week = week_start(date_value)
        row.commit_status = 'committed'
        row.committed_week_start = committed_week
        row.committed_on_week_start = submitted_week
        row.committed_expected_ship_date = date_value
        row.committed_at = now
        row.committed_by = user.id
        row.committed_by_name = user.real_name or user.username
        row.expected_ship_date = date_value
        row.draft_expected_ship_date = None
        row.draft_week_start = None
        _audit(user, 'weekly', 'submit', row.ladder_key,
               old_values=old, new_values={
                   'expected_ship_date': iso(date_value),
                   'committed_week_start': iso(committed_week),
               })
    db.session.commit()
    return {
        'submitted': len(pairs),
        'target_week_start': iso(target_week_start()),
        'target_week_end': iso(week_end(target_week_start())),
        'fill_month': window['month'],
        'fill_start': iso(window['start']),
        'fill_end': iso(window['end']),
    }


def withdraw_weekly(user, module_name, ladder_keys):
    rows = _load_owned_ladders(user, module_name, ladder_keys)
    current_week = week_start()
    changed = 0
    for row in rows:
        if row.commit_status != 'committed':
            raise ValueError('梯号 %s 尚未提交' % row.ladder_key)
        if row.committed_on_week_start != current_week and not can_admin(user):
            raise ValueError('梯号 %s 已跨周，需管理员解锁' % row.ladder_key)
        old = _tracking_dict(row)
        row.commit_status = 'withdrawn'
        row.committed_week_start = None
        row.committed_on_week_start = None
        row.committed_expected_ship_date = None
        row.committed_at = None
        row.committed_by = None
        row.committed_by_name = ''
        row.expected_ship_date = row.original_expected_ship_date
        row.draft_expected_ship_date = None
        row.draft_week_start = None
        _audit(user, 'weekly', 'withdraw', row.ladder_key, old_values=old,
               new_values={'expected_ship_date': iso(row.expected_ship_date)})
        changed += 1
    db.session.commit()
    return {'withdrawn': changed}


def adjust_weekly(user, module_name, items):
    window = fill_window()
    rows_payload = []
    for entry in items or []:
        key = canonical_ladder(entry.get('ladder_key') or '')
        if not key:
            raise ValueError('存在空梯号')
        date_value = parse_excel_date(entry.get('expected_ship_date'))
        if not date_value:
            raise ValueError('梯号 %s 未选择预计发货日期' % key)
        rows_payload.append({'ladder_key': key, 'expected_ship_date': date_value})
    keys = [entry['ladder_key'] for entry in rows_payload]
    rows = _load_owned_ladders(user, module_name, keys)
    current_week = week_start()
    by_key = {entry['ladder_key']: entry for entry in rows_payload}
    changed = 0
    for row in rows:
        if row.commit_status != 'committed':
            raise ValueError('梯号 %s 尚未提交' % row.ladder_key)
        if row.committed_on_week_start != current_week and not can_admin(user):
            raise ValueError('梯号 %s 已跨周，需管理员解锁' % row.ladder_key)
        date_value = by_key[row.ladder_key]['expected_ship_date']
        if date_value < window['start'] or date_value > window['end']:
            raise ValueError('梯号 %s 的日期必须在 %s 至 %s 之间'
                             % (row.ladder_key, iso(window['start']), iso(window['end'])))
        old = _tracking_dict(row)
        row.committed_week_start = week_start(date_value)
        row.committed_expected_ship_date = date_value
        row.expected_ship_date = date_value
        _audit(user, 'weekly', 'adjust', row.ladder_key, old_values=old,
               new_values={
                   'expected_ship_date': iso(date_value),
                   'committed_week_start': iso(row.committed_week_start),
               })
        changed += 1
    db.session.commit()
    return {'adjusted': changed}


def _load_owned_ladders(user, module, ladder_keys):
    modules = _resolve_weekly_modules(user, module)
    keys = [canonical_ladder(key) for key in (ladder_keys or []) if canonical_ladder(key)]
    if not keys:
        raise ValueError('请选择梯号')
    rows = TrackingItem.query.filter(TrackingItem.ladder_key.in_(keys)).all()
    by_key = {row.ladder_key: row for row in rows}
    result = []
    for key in keys:
        row = by_key.get(key)
        if not row:
            raise ValueError('梯号 %s 不存在' % key)
        if row.module_name not in modules:
            raise ValueError('梯号 %s 不属于当前可填报模块' % key)
        if row.actual_ship_date:
            raise ValueError('梯号 %s 已实发' % key)
        result.append(row)
    return result


def unlock(user, unlock_type, ladder_keys, reason=''):
    if not can_admin(user):
        raise PermissionError('无管理员解锁权限')
    if not normalize_text(reason):
        raise ValueError('请填写解锁原因')
    keys = [canonical_ladder(key) for key in (ladder_keys or []) if canonical_ladder(key)]
    if not keys:
        raise ValueError('请选择梯号')
    rows = TrackingItem.query.filter(TrackingItem.ladder_key.in_(keys)).all()
    count = 0
    skipped = 0
    now = dt.datetime.now()
    for row in rows:
        if unlock_type == 'weekly':
            # 只回退已提交且未实发的记录；其余行不动，避免误清日期。
            if row.commit_status != 'committed' or row.actual_ship_date:
                skipped += 1
                continue
            old = _tracking_dict(row)
            row.commit_status = 'withdrawn'
            row.committed_week_start = None
            row.committed_on_week_start = None
            row.committed_expected_ship_date = None
            row.committed_at = None
            row.committed_by = None
            row.committed_by_name = ''
            row.expected_ship_date = row.original_expected_ship_date
            # 与业务撤回保持一致：草稿字段一并清理。
            row.draft_expected_ship_date = None
            row.draft_week_start = None
            flags = [flag for flag in row.flags()
                     if flag not in ('committed_plan_changed', 'plan_removed_committed')]
            row.set_flags(flags)
            _audit(user, 'weekly', 'admin_unlock', row.ladder_key,
                   reason=reason, old_values=old, new_values={'commit_status': 'withdrawn'})
            count += 1
        elif unlock_type == 'shipment':
            active = DailyShipment.query.filter_by(ladder_key=row.ladder_key, is_void=False).all()
            if not active:
                skipped += 1
                continue
            old_actual = iso(row.actual_ship_date)
            old_source = row.actual_ship_source or ''
            for shipment in active:
                old = {
                    'ship_date': iso(shipment.ship_date),
                    'unit_count': shipment.unit_count,
                }
                shipment.is_void = True
                shipment.void_reason = reason
                shipment.void_by = user.id
                shipment.void_by_name = user.real_name or user.username
                shipment.void_at = now
                _audit(user, 'daily', 'admin_void_shipment', row.ladder_key,
                       reason=reason, old_values=old, new_values={'is_void': True})
                count += 1
            ledger_delivery = _ledger_delivery_date(row.ladder_key)
            if ledger_delivery:
                row.actual_ship_date = ledger_delivery
                row.actual_ship_source = 'ledger'
                flags = [flag for flag in row.flags() if flag != 'shipped_voided']
            else:
                row.actual_ship_date = None
                row.actual_ship_source = None
                flags = row.flags()
                if 'shipped_voided' not in flags:
                    flags.append('shipped_voided')
            row.set_flags(flags)
            _audit(user, 'daily', 'admin_void_actual', row.ladder_key,
                   reason=reason,
                   old_values={'actual_ship_date': old_actual, 'actual_ship_source': old_source},
                   new_values={'actual_ship_date': iso(row.actual_ship_date),
                               'actual_ship_source': row.actual_ship_source or ''})
        else:
            raise ValueError('不支持的解锁类型')
    db.session.commit()
    return {'unlocked': count, 'skipped': skipped}


def record_daily_shipments(user, items, reason=''):
    """批量录入实发；仅允许每日实发角色写入。"""
    if not can_daily_edit(user):
        raise PermissionError('无每日实发权限')
    if not isinstance(items, list) or not items:
        raise ValueError('请选择要实发的梯号')
    now = dt.datetime.now()
    current = today()
    changed = []
    seen = set()
    for entry in items:
        key = canonical_ladder(entry.get('ladder_key') or entry.get('ladder_no') or '')
        if not key:
            raise ValueError('存在空梯号')
        if key in seen:
            raise ValueError('梯号 %s 在本批次重复' % key)
        seen.add(key)
        ship_date = parse_excel_date(entry.get('ship_date'))
        if not ship_date:
            raise ValueError('梯号 %s 未选择实际发货日期' % key)
        if ship_date > current:
            raise ValueError('梯号 %s 的实际发货日期不能晚于今天' % key)
        if ship_date < current and not normalize_text(reason or entry.get('reason')):
            raise ValueError('梯号 %s 为补录历史日期，请填写原因' % key)
        item = TrackingItem.query.filter_by(ladder_key=key).first()
        if item is None:
            contract_no = normalize_text(entry.get('contract_no'))
            ladder_no = normalize_text(entry.get('ladder_no')) or key
            module_name = normalize_text(entry.get('module_name'))
            if not module_name:
                raise ValueError('计划外梯号 %s 必须选择模块' % key)
            from dashboards.contract_completion.models import LedgerContract
            ledger_contract = LedgerContract.query.filter(
                LedgerContract.source == 'ledger',
                or_(LedgerContract.ladder_no == key, LedgerContract.ladder_no == ladder_no),
            ).order_by(LedgerContract.contract_amount_rmb.desc()).first()
            item = TrackingItem(
                ladder_key=key,
                contract_no=contract_no,
                ladder_no=ladder_no,
                module_name=module_name,
                project_name=normalize_text(entry.get('project_name')),
                unit_count=float(entry.get('unit_count') or 1),
                payment_ratio=ledger_contract.payment_ratio if ledger_contract else None,
                plan_status='removed',
                plan_month=default_month(),
                commit_status='unplanned',
                source_kind='actual_only',
            )
            item.set_flags(['plan_external_actual'])
            db.session.add(item)
            db.session.flush()
        existing = DailyShipment.query.filter_by(ladder_key=key, is_void=False).order_by(DailyShipment.id.desc()).first()
        if existing:
            same_day_entry = existing.created_at and existing.created_at.date() == current
            if not same_day_entry:
                raise ValueError('梯号 %s 已有实发记录，需管理员解锁后才能修改' % key)
            if not normalize_text(reason or entry.get('reason')):
                raise ValueError('修改梯号 %s 的实发记录必须填写原因' % key)
            old = {
                'ship_date': iso(existing.ship_date),
                'unit_count': existing.unit_count,
                'remark': existing.remark or '',
            }
            existing.ship_date = ship_date
            existing.unit_count = float(entry.get('unit_count') or item.unit_count or 1)
            existing.remark = normalize_text(entry.get('remark'))
            existing.reason = normalize_text(reason or entry.get('reason'))
            existing.operator_id = user.id
            existing.operator_name = user.real_name or user.username
            shipment = existing
            action = 'update_shipment'
        else:
            shipment = DailyShipment(
                ladder_key=key,
                ship_date=ship_date,
                unit_count=float(entry.get('unit_count') or item.unit_count or 1),
                operator_id=user.id,
                operator_name=user.real_name or user.username,
                source='daily',
                remark=normalize_text(entry.get('remark')),
                reason=normalize_text(reason or entry.get('reason')),
            )
            db.session.add(shipment)
            old = {}
            action = 'create_shipment'
        ledger_delivery = _ledger_delivery_date(key)
        if ledger_delivery:
            item.actual_ship_date = ledger_delivery
            item.actual_ship_source = 'ledger'
        else:
            item.actual_ship_date = ship_date
            item.actual_ship_source = 'daily'
        _audit(user, 'daily', action, key, reason=normalize_text(reason or entry.get('reason')),
               old_values=old, new_values={
                   'ship_date': iso(ship_date),
                   'unit_count': shipment.unit_count,
                   'actual_ship_date': iso(item.actual_ship_date),
                   'actual_ship_source': item.actual_ship_source or '',
               })
        changed.append({
            'ladder_key': key,
            'ship_date': iso(ship_date),
            'actual_ship_date': iso(item.actual_ship_date),
            'actual_ship_source': item.actual_ship_source or '',
        })
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('该梯号已有有效实发记录，可能由并发提交产生，请刷新后重试')
    return {'shipped': len(changed), 'items': changed}


def preview_external_ladders(user, value, contract_no=''):
    """识别计划外实发录入的多梯号文本，供页面逐行预览确认。"""
    if not (can_daily_edit(user) or can_admin(user)):
        raise PermissionError('无计划外实发录入权限')
    return parse_ladder_batch(value, contract_no=contract_no)


def delete_daily_shipments(user, ladder_keys):
    """业务删除实发；只作废系统实发记录，跨天可用，不要求填写原因。"""
    if not (can_daily_edit(user) or can_admin(user)):
        raise PermissionError('无删除实发权限')
    keys = []
    for value in ladder_keys or []:
        key = canonical_ladder(value)
        if key and key not in keys:
            keys.append(key)
    if not keys:
        raise ValueError('请选择要删除的实发梯号')

    rows = TrackingItem.query.filter(TrackingItem.ladder_key.in_(keys)).all()
    by_key = {row.ladder_key: row for row in rows}
    now = dt.datetime.now()
    deleted = 0
    skipped = 0
    for key in keys:
        row = by_key.get(key)
        if row is None or row.actual_ship_source != 'daily':
            skipped += 1
            continue
        active = DailyShipment.query.filter_by(ladder_key=key, is_void=False).all()
        if not active:
            skipped += 1
            continue
        primary = active[0]
        old_actual = iso(row.actual_ship_date)
        old_source = row.actual_ship_source or ''
        for shipment in active:
            shipment.is_void = True
            shipment.void_reason = '业务删除实发'
            shipment.void_by = user.id
            shipment.void_by_name = user.real_name or user.username
            shipment.void_at = now
        ledger_delivery = _ledger_delivery_date(key)
        if ledger_delivery:
            row.actual_ship_date = ledger_delivery
            row.actual_ship_source = 'ledger'
            flags = [flag for flag in row.flags() if flag != 'shipped_voided']
        else:
            row.actual_ship_date = None
            row.actual_ship_source = None
            flags = row.flags()
            if 'shipped_voided' not in flags:
                flags.append('shipped_voided')
        row.set_flags(flags)
        _audit(user, 'daily', 'delete_shipment', key,
               reason='业务删除实发',
               old_values={
                   'ship_date': iso(primary.ship_date),
                   'unit_count': primary.unit_count,
                   'actual_ship_date': old_actual,
                   'actual_ship_source': old_source,
               },
               new_values={
                   'actual_ship_date': iso(row.actual_ship_date),
                   'actual_ship_source': row.actual_ship_source or '',
               })
        deleted += 1
    db.session.commit()
    return {'deleted': deleted, 'skipped': skipped}


def _status_filter(item, statuses):
    if not statuses:
        return True
    return item['status'] in statuses or item.get('status_label') in statuses


def query_tracking(user, filters=None):
    if not can_full_view(user):
        raise PermissionError('当前账号无全量明细权限')
    filters = filters or {}
    keyword = normalize_text(filters.get('keyword')).upper()
    month = normalize_text(filters.get('month'))
    module = normalize_text(filters.get('module'))
    region = normalize_text(filters.get('region'))
    booking = normalize_text(filters.get('booking_status'))
    actual_source = normalize_text(filters.get('actual_ship_source')).lower()
    payment_ratio_filter = normalize_text(filters.get('payment_ratio')).lower()
    statuses = filters.get('statuses') or []
    if isinstance(statuses, str):
        statuses = [statuses]
    include_removed = filters.get('include_removed') in (True, 1, '1', 'true', 'True')
    expected_start = parse_excel_date(filters.get('expected_start'))
    expected_end = parse_excel_date(filters.get('expected_end'))
    actual_start = parse_excel_date(filters.get('actual_start'))
    actual_end = parse_excel_date(filters.get('actual_end'))
    page = max(1, int(filters.get('page') or 1))
    raw_page_size = filters.get('page_size')
    unlimited = raw_page_size in (0, '0', 'all')
    page_size = None if unlimited else max(10, int(raw_page_size or 50))

    rows = TrackingItem.query.all()
    region_map = build_region_map(rows)
    result = []
    for item in rows:
        region_info = region_map.get(item.ladder_key) or {}
        data = _tracking_dict(
            item,
            region=region_info.get('region', ''),
            region_source=region_info.get('region_source', ''),
        )
        if month and data['plan_month'] != month:
            continue
        if module and data['module_name'] != module:
            continue
        if region and data['region'] != region:
            continue
        if not include_removed and data['plan_status'] == 'removed' and not data['actual_ship_date']:
            continue
        if keyword:
            haystack = ' '.join([
                data['contract_no'], data['ladder_no'], data['project_name'],
                data['module_name'], data['salesperson'], data['business_remark'],
            ]).upper()
            if keyword not in haystack:
                continue
        if booking and data['booking_status'] != booking:
            continue
        if actual_source and data['actual_ship_source'] != actual_source:
            continue
        if payment_ratio_filter in ('100', '100%'):
            if data['payment_ratio_group'] != '100':
                continue
        elif payment_ratio_filter in ('other', '其他'):
            if data['payment_ratio_group'] != 'other':
                continue
        if not _status_filter(data, statuses):
            continue
        expected = item.expected_ship_date
        actual = item.actual_ship_date
        if expected_start and (not expected or expected < expected_start):
            continue
        if expected_end and (not expected or expected > expected_end):
            continue
        if actual_start and (not actual or actual < actual_start):
            continue
        if actual_end and (not actual or actual > actual_end):
            continue
        result.append(data)

    def sort_key(row):
        expected = row.get('expected_ship_date')
        if expected:
            date_order = -dt.date.fromisoformat(expected).toordinal()
        else:
            date_order = 999999999
        return (row.get('module_name') or '', date_order, row.get('ladder_key') or '')

    result.sort(key=sort_key)
    shipped_rows = [row for row in result if row['status'] == 'shipped']
    target_end = fill_window()['end']
    summary = {
        'total': len(result),
        'units': round(sum(row['unit_count'] or 0 for row in result), 2),
        'shipped': len(shipped_rows),
        'shipped_units': round(sum(row['unit_count'] or 0 for row in shipped_rows), 2),
        'committed': sum(1 for row in result if row['status'] == 'committed'),
        'overdue': sum(1 for row in result if row['status'] == 'overdue'),
        'pending': sum(1 for row in result if row['status'] == 'pending'),
        'removed': sum(1 for row in result if row['status'] == 'removed'),
        'booked': sum(1 for row in result if row['booking_status'] == '已订舱'),
        'unbooked': sum(1 for row in result if row['booking_status'] != '已订舱'),
        'missing_expected': sum(
            1 for row in result
            if row['status'] != 'shipped' and not row['expected_ship_date']
        ),
        'uncommitted': sum(
            1 for row in result
            if row['status'] != 'shipped' and row['plan_status'] == 'active'
            and row['commit_status'] != 'committed'
            and (
                not row['expected_ship_date']
                or dt.date.fromisoformat(row['expected_ship_date']) <= target_end
            )
        ),
        'uncommitted_later': sum(
            1 for row in result
            if row['status'] != 'shipped' and row['plan_status'] == 'active'
            and row['commit_status'] != 'committed'
            and row['expected_ship_date']
            and dt.date.fromisoformat(row['expected_ship_date']) > target_end
        ),
        'external_actual': sum(1 for row in result if row['source_kind'] == 'actual_only'),
        'removed_shipped': sum(
            1 for row in result
            if row['plan_status'] == 'removed' and row['actual_ship_date']
        ),
        'with_flags': sum(1 for row in result if row['data_flags']),
    }
    if page_size is None:
        page_items = result
    else:
        start = (page - 1) * page_size
        page_items = result[start:start + page_size]
    return {
        'items': page_items,
        'total': len(result),
        'page': page,
        'page_size': len(page_items),
        'summary': summary,
        'modules': all_modules(),
        'months': month_options(),
        'status_options': STATUS_LABELS,
    }


def get_history(user, ladder_key):
    if not can_full_view(user) and not can_admin(user):
        raise PermissionError('无权限查看操作历史')
    key = canonical_ladder(ladder_key)
    if not key:
        raise ValueError('梯号不能为空')
    rows = AuditLog.query.filter_by(ladder_key=key).order_by(AuditLog.id.desc()).limit(500).all()
    return [row.to_dict() for row in rows]


def _excel_date(value):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return value


def _excel_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _export_sort_key(row):
    """已发货排在最前并按实际发货日期；未发货按预计日期，缺日期排最后。"""
    if row['status'] == 'shipped' or row['actual_ship_date']:
        return (0, row['actual_ship_date'] or '', row['ladder_no'] or '')
    return (1, row['expected_ship_date'] or '9999-12-31',
            row['module_name'] or '', row['ladder_no'] or '')


def export_tracking(user, filters=None):
    if not can_full_view(user):
        raise PermissionError('当前账号无全量明细导出权限')
    filters = dict(filters or {})
    data = query_tracking(user, dict(filters, page=1, page_size=999999))
    items = sorted(data['items'], key=_export_sort_key)
    # 不选月份时导出全部数据，汇总页也写「全部」，与文件名口径一致。
    month = filters.get('month') or '全部'
    today_text = today().isoformat()
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = '发货明细'
    headers = [
        '大区', '模块', '合同号', '梯号', '项目名称', '台数', '金额(万元)', '来源', '填报人',
        '排产完工日期', '整梯发货日期', '预计发货日期', '实际发货日期',
        '实际发货日期来源', '订舱状态', '订舱审核状态', '回款比例', '备注',
    ]
    sheet.append(headers)
    header_fill = PatternFill('solid', fgColor='172554')
    header_font = Font(name='微软雅黑', size=11, color='FFFFFF', bold=True)
    thin = Side(style='thin', color='D9E2F3')
    cell_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    sheet.row_dimensions[1].height = 32
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = cell_border

    shipped_fill = PatternFill('solid', fgColor='E8F5E9')
    overdue_fill = PatternFill('solid', fgColor='FDE7E9')
    band_fill = PatternFill('solid', fgColor='F5F9FF')
    body_font = Font(name='微软雅黑', size=10)
    shipped_font = Font(name='微软雅黑', size=10, color='1B5E20', bold=True)
    for row in items:
        shipped = bool(row['actual_ship_date'])
        overdue = (
            not shipped and row['expected_ship_date']
            and row['expected_ship_date'] < today_text
        )
        sheet.append([
            row['region'], row['module_name'], row['contract_no'], row['ladder_no'],
            row['project_name'],
            _excel_number(row['unit_count']), _excel_number(row['amount_wan']),
            row['source'], row['reporter'],
            _excel_date(row['schedule_finish_date']), _excel_date(row['whole_ship_date']),
            _excel_date(row['expected_ship_date']), _excel_date(row['actual_ship_date']),
            row['actual_ship_source_label'], row['booking_status'],
            row['booking_audit_status'], row['payment_ratio'], row['business_remark'],
        ])
        excel_row = sheet.max_row
        if shipped:
            fill = shipped_fill
        elif overdue:
            fill = overdue_fill
        elif excel_row % 2 == 0:
            fill = band_fill
        else:
            fill = None
        for cell in sheet[excel_row]:
            cell.alignment = Alignment(vertical='center')
            cell.font = body_font
            cell.border = cell_border
            if fill is not None:
                cell.fill = fill
        if shipped:
            sheet.cell(excel_row, 13).font = shipped_font

    widths = [8, 18, 16, 22, 30, 8, 12, 11, 10, 13, 13, 13, 13, 14, 10, 12, 12, 30]
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for excel_row in range(2, sheet.max_row + 1):
        for column in (10, 11, 12, 13):
            sheet.cell(excel_row, column).number_format = 'yyyy-mm-dd'
            sheet.cell(excel_row, column).alignment = Alignment(
                horizontal='center', vertical='center'
            )
        sheet.cell(excel_row, 6).number_format = '0.##'
        sheet.cell(excel_row, 7).number_format = '#,##0.00'
        sheet.cell(excel_row, 17).number_format = '0.00%'
        sheet.cell(excel_row, 18).alignment = Alignment(
            vertical='top', wrap_text=True
        )
    sheet.freeze_panes = 'E2'
    sheet.auto_filter.ref = 'A1:R%d' % sheet.max_row
    sheet.sheet_view.showGridLines = False

    # 汇总页：先看总数和颜色含义，再回到明细逐行核对。
    summary = workbook.create_sheet('发货汇总')
    summary.sheet_view.showGridLines = False
    summary.merge_cells('A1:F1')
    summary['A1'] = '发货梯号明细 · 导出汇总'
    summary['A1'].font = Font(size=15, bold=True, color='172554')
    summary['A2'] = '计划月份：%s　导出时间：%s' % (
        month, dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    )
    summary['A2'].font = Font(size=10, color='5B6B7F')
    summary['A3'] = '说明：明细按「已发货 → 未发货」排序；回款比例取台账 BN 列，达到 100% 统一显示 100.00%。'
    summary['A3'].font = Font(size=10, color='5B6B7F')

    total_units = sum(row['unit_count'] or 0 for row in items)
    shipped_rows = [row for row in items if row['actual_ship_date']]
    shipped_units = sum(row['unit_count'] or 0 for row in shipped_rows)
    overdue_rows = [
        row for row in items
        if not row['actual_ship_date'] and row['expected_ship_date']
        and row['expected_ship_date'] < today_text
    ]
    stats = [
        ('计划梯号总数', len(items), total_units),
        ('已发货', len(shipped_rows), shipped_units),
        ('未发货', len(items) - len(shipped_rows), total_units - shipped_units),
        ('其中：已过预计日期未发货', len(overdue_rows),
         sum(row['unit_count'] or 0 for row in overdue_rows)),
    ]
    summary['A4'] = '指标'
    summary['B4'] = '梯号数'
    summary['C4'] = '台数'
    for cell in summary[4][:3]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    for offset, values in enumerate(stats, 5):
        for column, value in enumerate(values, 1):
            cell = summary.cell(offset, column, value)
            cell.border = Border(bottom=thin)
            if column > 1:
                cell.alignment = Alignment(horizontal='right')
    rate_row = 5 + len(stats)
    summary.cell(rate_row, 1, '发货率（按梯号）')
    summary.cell(rate_row, 2, (len(shipped_rows) / len(items)) if items else 0)
    summary.cell(rate_row, 2).number_format = '0.0%'
    summary.merge_cells(start_row=rate_row, start_column=2, end_row=rate_row, end_column=3)
    summary.cell(rate_row, 2).alignment = Alignment(horizontal='left')
    summary.cell(rate_row, 1).border = Border(bottom=thin)
    summary.cell(rate_row, 2).border = Border(bottom=thin)

    legend_row = rate_row + 2
    summary.cell(legend_row, 1, '颜色说明').font = Font(bold=True, color='172554')
    legend = [
        ('已发货', shipped_fill),
        ('未发货且已过预计发货日期', overdue_fill),
        ('未发货', None),
    ]
    for offset, (label, fill) in enumerate(legend, legend_row + 1):
        swatch = summary.cell(offset, 1, '')
        swatch.fill = fill or PatternFill('solid', fgColor='F5F9FF')
        swatch.border = Border(
            left=Side(style='thin', color='B7C4D4'),
            right=Side(style='thin', color='B7C4D4'),
            top=Side(style='thin', color='B7C4D4'),
            bottom=Side(style='thin', color='B7C4D4'),
        )
        summary.cell(offset, 2, label)

    module_row = legend_row + len(legend) + 2
    summary.cell(module_row, 1, '分模块发货情况').font = Font(bold=True, color='172554')
    module_headers = ['模块', '计划梯号', '已发货', '未发货', '发货率']
    for column, label in enumerate(module_headers, 1):
        cell = summary.cell(module_row + 1, column, label)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    module_stats = defaultdict(lambda: [0, 0])
    for row in items:
        key = row['module_name'] or '未归属'
        module_stats[key][0] += 1
        if row['actual_ship_date']:
            module_stats[key][1] += 1
    for offset, (name, (count, shipped_count)) in enumerate(
            sorted(module_stats.items(), key=lambda item: (-item[1][0], item[0])),
            module_row + 2):
        summary.cell(offset, 1, name)
        summary.cell(offset, 2, count)
        summary.cell(offset, 3, shipped_count)
        summary.cell(offset, 4, count - shipped_count)
        rate = summary.cell(offset, 5, shipped_count / count if count else 0)
        rate.number_format = '0.0%'
        rate.alignment = Alignment(horizontal='right')
        for column in range(1, 6):
            summary.cell(offset, column).border = Border(bottom=thin)

    summary.column_dimensions['A'].width = 30
    summary.column_dimensions['B'].width = 16
    summary.column_dimensions['C'].width = 14
    summary.column_dimensions['D'].width = 14
    summary.column_dimensions['E'].width = 12

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def make_plan_template():
    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = '预计发货明细'
    headers = ['模块', '合同号', '梯号', '项目名称', '台数', '金额(万元)', '来源', '填报人',
               '排产完工日期', '整梯发货日期', '业务预计发货时间', '备注']
    sheet.append(headers)
    sheet.append(['示例模块', 'DHT-000000T', 'DHT-000000T/1#', '示例项目', 1, 10.0,
                  '候选勾选', '张三', '2026-11-10', '2026-11-10', '2026-11-10', ''])
    sheet.column_dimensions['L'].width = 36
    sheet.freeze_panes = 'A2'
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def make_booking_template():
    """订舱模板：列位与解析器一致（B/C/D/H/K/AE/AG/AH/AI），第 3 行起为数据区。"""
    from openpyxl import Workbook
    from openpyxl.utils import column_index_from_string

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = '订舱申请流程报表'
    headers = {
        'B': '单据号', 'C': '审核状态', 'D': '当前节点', 'H': '申请日期',
        'K': '梯号', 'AE': '合同编号', 'AG': '完整梯号',
        'AH': '梯种', 'AI': '价格条款',
    }
    for letter, title in headers.items():
        sheet.cell(row=1, column=column_index_from_string(letter), value=title)
    # 第 2 行只放说明，不参与解析；从第 3 行开始填数据。
    sheet.cell(
        row=2, column=1,
        value=('从第 3 行开始填写；AG 列「完整梯号」必填，缺少 AG 列的行不参与匹配。'
               '示例：B=DD-000000，C=审批中，D=业务审批，H=2026-11-01，'
               'K=1#，AE=DHT-000000T，AG=DHT-000000T/1#，AH=乘客电梯，AI=FOB。'),
    )
    sheet.column_dimensions['AG'].width = 28
    sheet.freeze_panes = 'A3'
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output
