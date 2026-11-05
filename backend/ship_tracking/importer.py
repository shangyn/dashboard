"""发货梯号追踪 - 计划/订舱 Excel 导入与版本差异。"""
import datetime as dt
import hashlib
import json
import os
import re
from collections import Counter, defaultdict

from sqlalchemy import bindparam, func, text

from models import db
from ship_tracking.excel_reader import (
    canonical_ladder, column_index, expand_ladder_ranges, normalize_text,
    parse_excel_date, parse_number, read_sheet_rows,
)
from ship_tracking.plan_headers import (
    PlanHeaderError, read_plan_table,
)
from ship_tracking.models import (
    BookingRecord, ImportBatch, ImportIssue, PlanItem, TrackingItem,
)
from ship_tracking.services import (
    _audit, _dump, _loads, all_modules, can_import, default_month, iso,
    normalize_month, today, week_start,
)

MODULE_OVERRIDES = {
    'DHT-261237T': '俄罗斯（东部）',
    '124': '俄罗斯（东部）',
}
PLAN_FLAGS = {
    'duplicate_source', 'module_mapped', 'invalid_expected_date',
    'used_whole_ship_date', 'expected_from_seven_day', 'missing_expected_date', 'missing_project',
    'committed_plan_changed', 'plan_removed_committed', 'plan_removed_booked',
    'plan_removed_shipped',
}


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def infer_plan_month(filename):
    name = os.path.basename(filename or '')
    match = re.search(r'(20\d{2})[-_.年]?(0?[1-9]|1[0-2])', name)
    if match:
        return '%s-%02d' % (match.group(1), int(match.group(2)))
    return ''


def _pick(row, letter):
    return normalize_text(row.get(letter))


def _field(row, columns, field):
    """按表头映射取字段值；列不存在时返回空串。"""
    if columns is None or not columns.has(field):
        return ''
    return normalize_text(row.get(columns.letter(field)))


def _load_ledger(ladder_keys):
    keys = sorted(set(canonical_ladder(key) for key in ladder_keys if key))
    result = {}
    if not keys:
        return result
    statement = text(
        "SELECT ladder_no, contract_no, project_name, contract_amount_rmb, "
        "salesperson, business_region, mapped_module, personal_module, "
        "whole_ship_date, schedule_finish_date "
        "FROM cc_ledger_contract WHERE source = 'ledger' AND ladder_no IN :keys"
    ).bindparams(bindparam('keys', expanding=True))
    try:
        for start in range(0, len(keys), 500):
            chunk = keys[start:start + 500]
            rows = db.session.execute(statement, {'keys': chunk}).mappings().all()
            for row in rows:
                ladder = canonical_ladder(row.get('ladder_no'))
                if not ladder:
                    continue
                current = result.get(ladder)
                amount = parse_number(row.get('contract_amount_rmb')) or 0
                old_amount = parse_number(current.get('contract_amount_rmb')) if current else 0
                if current is None or amount > old_amount:
                    result[ladder] = dict(row)
    except Exception:
        db.session.rollback()
        return {}
    return result


def _clean_plan_row(row, row_number, ledger, seen, columns):
    issues = []
    ladder_raw = _field(row, columns, 'ladder')
    if not ladder_raw or ladder_raw in ('梯号', '梯号号'):
        return [], issues
    contract_no = _field(row, columns, 'contract_no')
    ladders = expand_ladder_ranges(ladder_raw, contract_no=contract_no)
    if not ladders:
        issues.append(_issue(row_number, 'error', 'missing_ladder', '梯号为空', row, columns))
        return [], issues
    unit_raw = _field(row, columns, 'unit_count')
    source_units = parse_number(unit_raw)
    project_raw = _field(row, columns, 'project_name')
    d_value = parse_number(project_raw)
    # 文件是否真的给了台数；没给时默认 1 只能用于新建行，不能覆盖已有值。
    unit_explicit = source_units is not None and source_units > 0
    if source_units is None and unit_raw == '' and d_value is not None and 0 < d_value <= 1000:
        source_units = d_value
        unit_explicit = True
    if source_units is None or source_units <= 0:
        source_units = 1
    unit_each = source_units / float(len(ladders))
    module_raw = _field(row, columns, 'module')
    base_module = module_raw
    if base_module in MODULE_OVERRIDES:
        base_module = MODULE_OVERRIDES[base_module]
    if not base_module:
        base_module = MODULE_OVERRIDES.get(contract_no, '')
    ledger_row = ledger.get(canonical_ladder(ladders[0]), {})
    ledger_module = ledger_row.get('mapped_module') or ledger_row.get('personal_module') or ''
    module = base_module or ledger_module or '未归属'
    # 只有文件显式给了模块、或台账命中模块时，才允许覆盖已有行的模块。
    module_explicit = bool(base_module or ledger_module)
    project_name = project_raw
    reporter = _field(row, columns, 'reporter')
    source = _field(row, columns, 'source')
    business_expected_raw = _field(row, columns, 'business_expected')
    seven_day_raw = _field(row, columns, 'seven_day')
    business_date = parse_excel_date(business_expected_raw)
    seven_day_date = parse_excel_date(seven_day_raw)
    flags = set()
    if base_module and base_module != module_raw:
        flags.add('module_mapped')
    # 预计发货日期只取「业务预计发货时间」和「7日前发货」两列（按表头识别）；
    # 「整梯发货日期」仅作展示，不再兜底。
    expected = business_date or seven_day_date
    if business_date:
        expected_source = 'business_expected'
        expected_raw = business_expected_raw
    elif seven_day_date:
        expected_source = 'seven_day'
        expected_raw = seven_day_raw
        flags.add('expected_from_seven_day')
    else:
        expected_source = ''
        expected_raw = business_expected_raw or seven_day_raw
        flags.add('missing_expected_date')
    if business_expected_raw and not business_date:
        flags.add('invalid_expected_date')
        if seven_day_date:
            message = ('业务预计发货时间「%s」不是有效日期，已改用 7日前发货「%s」'
                       % (business_expected_raw, seven_day_date.strftime('%Y-%m-%d')))
        else:
            message = '业务预计发货时间「%s」不是有效日期，且没有有效的 7日前发货' % business_expected_raw
        issues.append(_issue(
            row_number, 'warning', 'invalid_expected_date', message, row, columns,
        ))
    if not project_name:
        project_name = normalize_text(ledger_row.get('project_name'))
        if not project_name:
            flags.add('missing_project')
            issues.append(_issue(row_number, 'warning', 'missing_project', '缺少项目名称', row, columns))
    if not reporter:
        reporter = normalize_text(ledger_row.get('salesperson'))
    amount_rmb = parse_number(ledger_row.get('contract_amount_rmb'))
    if amount_rmb is None:
        contract_amount = parse_number(_field(row, columns, 'contract_amount_rmb'))
        if contract_amount is not None and contract_amount > 0:
            amount_rmb = contract_amount
    if amount_rmb is None:
        amount_wan = parse_number(_field(row, columns, 'amount_wan'))
        if amount_wan is not None and amount_wan > 0:
            amount_rmb = amount_wan * 10000.0
    if amount_rmb is None:
        amount_rmb = 0.0
    raw_letters = sorted(set(row) | set(columns.letters().values()), key=column_index)
    raw = {letter: _pick(row, letter) for letter in raw_letters}
    raw['_letters'] = columns.letters()
    raw['_expected_source'] = expected_source
    raw['_row_number'] = row_number
    result = []
    for ladder in ladders:
        ladder_ledger_row = ledger.get(canonical_ladder(ladder), {})
        item = {
            'ladder_key': ladder,
            'contract_no': contract_no or ladder.split('/')[0],
            'ladder_no': ladder,
            'module_name': module,
            'module_explicit': module_explicit,
            'project_name': project_name,
            'business_region': normalize_text(ledger_row.get('business_region')),
            'salesperson': reporter,
            'unit_count': unit_each,
            'unit_explicit': unit_explicit,
            'amount_rmb': amount_rmb / float(len(ladders)),
            'source': source,
            'reporter': reporter,
            # 排产完工 / 整梯发货只取台账；计划 Excel 的日期不参与。
            'schedule_finish_date': parse_excel_date(ladder_ledger_row.get('schedule_finish_date')),
            'whole_ship_date': parse_excel_date(ladder_ledger_row.get('whole_ship_date')),
            '_ledger_found': bool(ladder_ledger_row),
            'original_expected_ship_date': expected,
            'business_expected_raw': expected_raw,
            'validation_status': 'warning' if flags else 'ok',
            'data_flags': sorted(flags),
            'raw': raw,
        }
        if ladder in seen:
            kept = seen[ladder]
            kept['data_flags'] = sorted(set(kept.get('data_flags') or []) | {'duplicate_source'})
            kept['validation_status'] = 'warning'
            issues.append(_issue(
                row_number, 'warning', 'duplicate_ladder',
                '梯号「%s」与第 %s 行重复，已按重复导入处理，保留第一次出现的数据'
                % (ladder, kept.get('raw', {}).get('_row_number', '?')),
                row, columns,
            ))
            continue
        seen[ladder] = item
        result.append(item)
    return result, issues


def parse_plan_file(path, plan_month):
    columns, data_rows, table_stats = read_plan_table(path)
    ledger_keys = []
    raw_rows = []
    for row_number, row in data_rows:
        ladder_raw = _field(row, columns, 'ladder')
        if not ladder_raw:
            continue
        raw_rows.append((row_number, row))
        contract_no = _field(row, columns, 'contract_no')
        ledger_keys.extend(expand_ladder_ranges(ladder_raw, contract_no=contract_no))
    ledger = _load_ledger(ledger_keys)
    seen = {}
    items = []
    issues = []
    duplicate_groups = []
    for row_number, row in raw_rows:
        parsed, row_issues = _clean_plan_row(row, row_number, ledger, seen, columns)
        items.extend(parsed)
        issues.extend(row_issues)
    duplicate_counter = Counter()
    for item in items:
        if 'duplicate_source' in item.get('data_flags', []):
            duplicate_counter[item['ladder_key']] += 1
    for item in items:
        if 'duplicate_source' in item.get('data_flags', []):
            duplicate_groups.append(item['ladder_key'])
    for issue in issues:
        if issue.get('code') == 'duplicate_ladder':
            message = issue.get('message') or ''
            match = re.search(r'梯号「([^」]+)」', message)
            issue['duplicate_key'] = match.group(1) if match else ''
    ignored_columns = columns.ignored + columns.unknown
    if ignored_columns:
        issues.append(_issue(
            None, 'info', 'ignored_columns',
            '表头中以下列不参与计划导入，已忽略：%s'
            % '、'.join('%s列「%s」' % (item['letter'], item['header']) for item in ignored_columns),
        ))
    summary = {
        'row_count': len(raw_rows),
        'data_row_count': table_stats['data_row_count'],
        'unique_count': len(items),
        'total_units': round(sum(item['unit_count'] for item in items), 2),
        'duplicate_count': len(duplicate_groups),
        'duplicate_groups': duplicate_groups,
        'module_count': len(set(item['module_name'] for item in items)),
        'missing_expected_date': sum(1 for item in items if not item['original_expected_ship_date']),
        'invalid_expected_date': sum(1 for item in items if 'invalid_expected_date' in item['data_flags']),
        'missing_module': sum(1 for item in items if item['module_name'] == '未归属'),
        'missing_project': sum(1 for item in items if 'missing_project' in item['data_flags']),
        'expected_with_date': sum(1 for item in items if item['original_expected_ship_date']),
        'header': columns.to_dict(),
    }
    return items, issues, summary


def _issue(row_number, severity, code, message, raw=None, columns=None):
    raw = raw or {}
    if columns is not None:
        letters = sorted(set(raw) | set(columns.letters().values()), key=column_index)
    else:
        letters = list('ABCDEFGHIJKLMNOP')
    data = {letter: _pick(raw, letter) for letter in letters}
    if columns is not None:
        data['_letters'] = columns.letters()
    return {
        'row_number': row_number,
        'severity': severity,
        'code': code,
        'message': message,
        'raw': data,
    }


def _has_activity(row):
    """判断一条追踪行是否已有业务活动，重传计划时不能静默移除。

    有预计/草稿/承诺/实发/订舱，或来自手工新增、单月填报的行，都属于有活动；
    只有完全没被用过、也没被业务补录过的纯计划行，才允许按新文件软移除。
    """
    return bool(
        row.original_expected_ship_date or row.expected_ship_date
        or row.draft_expected_ship_date or row.committed_expected_ship_date
        or row.actual_ship_date
        or (row.booking_status or '') == '已订舱'
        or (row.booking_record_count or 0) > 0
        or (row.commit_status or '') == 'committed'
        or row.source_kind == 'manual'
        or 'manual_added' in row.flags()
        or 'from_monthly_forecast' in row.flags()
    )


def _plan_diff(items, overwrite_expected=False):
    new_by_key = {item['ladder_key']: item for item in items}
    current = {row.ladder_key: row for row in TrackingItem.query.all()}
    added = []
    removed = []
    preserved_absent = []
    expected_changed = []
    expected_preserved = []
    expected_filled = []
    module_changed = []
    committed_conflicts = []
    shipped_absent = []
    booked_absent = []
    unchanged = 0
    for key, item in new_by_key.items():
        row = current.get(key)
        if row is None:
            added.append(key)
            continue
        old_expected = row.original_expected_ship_date
        file_expected = item.get('original_expected_ship_date')
        # 草稿不再写入 expected，也不参与预览/提交的已有日期判断。
        existing_expected = (
            row.original_expected_ship_date or row.expected_ship_date
            or row.committed_expected_ship_date
        )
        if file_expected and not existing_expected:
            expected_filled.append({
                'ladder_key': key,
                'old': '',
                'new': iso(file_expected),
                'committed': row.commit_status == 'committed',
            })
        elif file_expected and existing_expected and file_expected != existing_expected:
            entry = {
                'ladder_key': key,
                'old': iso(existing_expected),
                'new': iso(file_expected),
                'committed': row.commit_status == 'committed',
            }
            expected_changed.append(entry)
            if not overwrite_expected:
                expected_preserved.append(entry)
            if row.commit_status == 'committed':
                committed_conflicts.append(key)
        if overwrite_expected and file_expected:
            effective_expected = file_expected
        else:
            effective_expected = existing_expected or file_expected
        # 与提交逻辑保持一致：只有文件/台账真正给了模块，才算模块变更。
        module_explicit = item.get('module_explicit')
        if module_explicit is None:
            module_explicit = bool(item.get('module_name')) and item.get('module_name') != '未归属'
        module_changed_this = bool(
            module_explicit and item.get('module_name')
            and (row.module_name or '') != item.get('module_name')
        )
        if module_changed_this:
            module_changed.append({
                'ladder_key': key,
                'old': row.module_name or '',
                'new': item.get('module_name') or '',
            })
        if old_expected == effective_expected and not module_changed_this and row.plan_status == 'active':
            unchanged += 1
    for key, row in current.items():
        if row.plan_status != 'active' or key in new_by_key:
            continue
        if _has_activity(row):
            preserved_absent.append(key)
            if row.actual_ship_date:
                shipped_absent.append(key)
            if row.booking_status == '已订舱' or (row.booking_record_count or 0) > 0:
                booked_absent.append(key)
            continue
        removed.append(key)
    return {
        'added_count': len(added),
        'removed_count': len(removed),
        'preserved_absent_count': len(preserved_absent),
        'expected_changed_count': len(expected_changed),
        'expected_preserved_count': len(expected_preserved),
        'expected_filled_count': len(expected_filled),
        'module_changed_count': len(module_changed),
        'committed_conflict_count': len(set(committed_conflicts)),
        'shipped_absent_count': len(shipped_absent),
        'booked_absent_count': len(booked_absent),
        # 兼容旧前端字段：默认保留后不会再有「已实发/已订舱后移除」。
        'shipped_removed_count': 0,
        'booked_removed_count': 0,
        'unchanged_count': unchanged,
        'added_sample': added[:80],
        'removed_sample': removed[:80],
        'preserved_absent_sample': preserved_absent[:80],
        'expected_changed_sample': expected_changed[:80],
        'expected_preserved_sample': expected_preserved[:80],
        'expected_filled_sample': expected_filled[:80],
        'module_changed_sample': module_changed[:80],
        'committed_conflict_sample': list(dict.fromkeys(committed_conflicts))[:80],
        'shipped_absent_sample': shipped_absent[:80],
        'booked_absent_sample': booked_absent[:80],
        'shipped_removed_sample': [],
        'booked_removed_sample': [],
    }


def _store_issues(batch_id, issues):
    for issue in issues:
        db.session.add(ImportIssue(
            batch_id=batch_id,
            row_number=issue.get('row_number'),
            severity=issue.get('severity') or 'warning',
            code=issue.get('code') or '',
            message=issue.get('message') or '',
            raw_json=_dump(issue.get('raw') or {}),
        ))


def preview_plan_import(path, filename, plan_month, user):
    if not can_import(user):
        raise PermissionError('无导入权限')
    month = normalize_month(plan_month) or infer_plan_month(filename) or default_month()
    items, issues, parsed_summary = parse_plan_file(path, month)
    if not items:
        raise ValueError('未读取到任何有效梯号，请检查文件是否为当前激活的预计发货明细表')
    errors = [issue for issue in issues if issue.get('severity') == 'error']
    warnings = [issue for issue in issues if issue.get('severity') == 'warning']
    file_hash = file_sha256(path)
    previous = ImportBatch.query.filter_by(
        data_type='plan', plan_month=month, status='committed'
    ).order_by(ImportBatch.version.desc()).first()
    version = (previous.version if previous else 0) + 1
    duplicate_import = ImportBatch.query.filter_by(
        data_type='plan', file_hash=file_hash, status='committed'
    ).order_by(ImportBatch.id.desc()).first()
    diff = _plan_diff(items)
    summary = dict(parsed_summary)
    summary.update(diff)
    summary['source'] = 'excel'
    summary['plan_month'] = month
    summary['duplicate_import_batch_id'] = duplicate_import.id if duplicate_import else None
    summary['duplicate_import'] = bool(duplicate_import)
    summary['warning_count'] = len(warnings)
    summary['error_count'] = len(errors)
    batch = ImportBatch(
        data_type='plan',
        plan_month=month,
        version=version,
        filename=os.path.basename(filename),
        file_hash=file_hash,
        status='preview',
        row_count=parsed_summary['row_count'],
        unique_count=parsed_summary['unique_count'],
        total_units=parsed_summary['total_units'],
        duplicate_count=parsed_summary['duplicate_count'],
        warning_count=len(warnings),
        error_count=len(errors),
        summary_json=_dump(summary),
        payload_json=_dump(items),
        previous_batch_id=previous.id if previous else None,
        created_by=user.id,
        created_by_name=user.real_name or user.username,
    )
    db.session.add(batch)
    db.session.flush()
    _store_issues(batch.id, issues)
    db.session.commit()
    result = batch.to_dict()
    result['issues'] = [dict(issue, id=None) for issue in issues[:300]]
    result['issue_total'] = len(issues)
    return result


def _parse_iso_date(value):
    return parse_excel_date(value) if value else None


def commit_plan_import(batch_id, user, force=False, overwrite_expected=False):
    if not can_import(user):
        raise PermissionError('无导入权限')
    batch = db.session.get(ImportBatch, batch_id)
    if not batch or batch.data_type != 'plan':
        raise ValueError('导入批次不存在')
    if batch.status == 'committed':
        raise ValueError('该批次已提交，不能重复提交')
    if batch.status == 'superseded':
        raise ValueError('该批次已被新版本替代')
    duplicate = ImportBatch.query.filter(
        ImportBatch.id != batch.id,
        ImportBatch.data_type == 'plan',
        ImportBatch.file_hash == batch.file_hash,
        ImportBatch.status == 'committed',
    ).first()
    if duplicate and not force:
        raise ValueError('相同文件已导入过，如确认要重新生成版本，请勾选强制执行')
    items = _loads(batch.payload_json, [])
    if not items:
        raise ValueError('批次没有可提交的数据')

    previous = ImportBatch.query.filter(
        ImportBatch.id != batch.id,
        ImportBatch.data_type == 'plan',
        ImportBatch.plan_month == batch.plan_month,
        ImportBatch.status == 'committed',
    ).order_by(ImportBatch.version.desc()).first()
    if previous:
        batch.version = max(batch.version or 0, (previous.version or 0) + 1)
    now = dt.datetime.now()
    current_rows = {row.ladder_key: row for row in TrackingItem.query.all()}
    new_by_key = {item['ladder_key']: item for item in items}

    for item in items:
        expected = _parse_iso_date(item.get('original_expected_ship_date'))
        row = PlanItem(
            batch_id=batch.id,
            plan_month=batch.plan_month,
            plan_version=batch.version,
            ladder_key=item['ladder_key'],
            contract_no=item.get('contract_no') or '',
            ladder_no=item.get('ladder_no') or item['ladder_key'],
            module_name=item.get('module_name') or '',
            project_name=item.get('project_name') or '',
            business_region=item.get('business_region') or '',
            salesperson=item.get('salesperson') or '',
            unit_count=float(item.get('unit_count') or 1),
            amount_rmb=float(item.get('amount_rmb') or 0),
            source=item.get('source') or '',
            reporter=item.get('reporter') or '',
            schedule_finish_date=_parse_iso_date(item.get('schedule_finish_date')),
            whole_ship_date=_parse_iso_date(item.get('whole_ship_date')),
            original_expected_ship_date=expected,
            business_expected_raw=item.get('business_expected_raw') or '',
            validation_status=item.get('validation_status') or 'ok',
            data_flags=_dump(item.get('data_flags') or []),
            raw_json=_dump(item.get('raw') or {}),
        )
        db.session.add(row)

    changed_keys = []
    for key, item in new_by_key.items():
        expected = _parse_iso_date(item.get('original_expected_ship_date'))
        row = current_rows.get(key)
        new_flags = set(item.get('data_flags') or [])
        if row is None:
            row = TrackingItem(
                ladder_key=key,
                plan_month=batch.plan_month,
                plan_version=batch.version,
                plan_batch_id=batch.id,
                plan_status='active',
                contract_no=item.get('contract_no') or '',
                ladder_no=item.get('ladder_no') or key,
                module_name=item.get('module_name') or '',
                project_name=item.get('project_name') or '',
                business_region=item.get('business_region') or '',
                salesperson=item.get('salesperson') or '',
                unit_count=float(item.get('unit_count') or 1),
                amount_rmb=float(item.get('amount_rmb') or 0),
                source=item.get('source') or '',
                reporter=item.get('reporter') or '',
                business_expected_raw=item.get('business_expected_raw') or '',
                schedule_finish_date=_parse_iso_date(item.get('schedule_finish_date')),
                whole_ship_date=_parse_iso_date(item.get('whole_ship_date')),
                original_expected_ship_date=expected,
                expected_ship_date=expected,
                commit_status='unplanned',
                booking_status='未订舱',
                source_kind='plan',
            )
            row.set_flags(new_flags)
            db.session.add(row)
            current_rows[key] = row
            changed_keys.append(key)
            _audit(user, 'plan', 'add', key, batch_id=batch.id,
                   new_values={'expected_ship_date': iso(expected)})
            continue

        old = {
            'module_name': row.module_name or '',
            'expected_ship_date': iso(row.original_expected_ship_date),
            'unit_count': row.unit_count,
            'amount_rmb': row.amount_rmb,
            'plan_status': row.plan_status,
        }
        old_expected = row.original_expected_ship_date
        file_expected = expected
        # 草稿不再写入 expected，也不参与已有日期判断。
        existing_expected = (
            row.original_expected_ship_date or row.expected_ship_date
            or row.committed_expected_ship_date
        )
        # 已有预计日期一律保留；只有空值才用文件补。
        # overwrite_expected 是预览弹窗里显式勾选的高级选项，默认关闭。
        if overwrite_expected and file_expected:
            effective_expected = file_expected
        else:
            effective_expected = existing_expected or file_expected
        if old_expected != effective_expected:
            row.plan_change_count = (row.plan_change_count or 0) + 1
        row.plan_month = batch.plan_month
        row.plan_version = batch.version
        row.plan_batch_id = batch.id
        row.plan_status = 'active'
        row.plan_removed_at = None
        if row.source_kind == 'actual_only':
            row.source_kind = 'plan'
            new_flags.discard('plan_external_actual')
        row.contract_no = item.get('contract_no') or row.contract_no
        row.ladder_no = item.get('ladder_no') or row.ladder_no
        # 文件没给模块（台账也没命中）时保留已有模块，不能被「未归属」覆盖。
        # 旧预览批次没有 module_explicit 标记，按「非空且不是未归属」兼容。
        module_explicit = item.get('module_explicit')
        if module_explicit is None:
            module_explicit = bool(item.get('module_name')) and item.get('module_name') != '未归属'
        if module_explicit and item.get('module_name'):
            row.module_name = item.get('module_name')
        row.project_name = item.get('project_name') or row.project_name
        row.business_region = item.get('business_region') or row.business_region
        row.salesperson = item.get('salesperson') or row.salesperson
        # 文件没给台数时保留已有台数，不能把已有值重置成解析默认值 1。
        if item.get('unit_explicit'):
            row.unit_count = float(item.get('unit_count') or row.unit_count or 1)
        row.amount_rmb = float(item.get('amount_rmb') or row.amount_rmb or 0)
        row.source = item.get('source') or row.source
        row.reporter = item.get('reporter') or row.reporter
        new_raw = normalize_text(item.get('business_expected_raw'))
        if new_raw and (overwrite_expected or not row.business_expected_raw):
            row.business_expected_raw = new_raw
        new_schedule = _parse_iso_date(item.get('schedule_finish_date'))
        new_whole = _parse_iso_date(item.get('whole_ship_date'))
        ledger_found = item.get('_ledger_found')
        if ledger_found is True:
            # 台账有该梯号：允许覆盖，也允许按台账空值清空。
            row.schedule_finish_date = new_schedule
            row.whole_ship_date = new_whole
        elif ledger_found is False:
            # 台账没有该梯号：保留旧值，等台账进数后再同步。
            pass
        else:
            # 部署前生成的预览批次没有 _ledger_found 标记，保持旧语义。
            row.schedule_finish_date = new_schedule or row.schedule_finish_date
            row.whole_ship_date = new_whole or row.whole_ship_date
        row.original_expected_ship_date = effective_expected
        preserved_flags = set(row.flags()) - PLAN_FLAGS
        if (
            row.commit_status == 'committed'
            and file_expected
            and row.committed_expected_ship_date
            and file_expected != row.committed_expected_ship_date
        ):
            # 文件想改已提交承诺的日期：只提示冲突，不改承诺。
            new_flags.add('committed_plan_changed')
        if row.commit_status != 'committed':
            # 草稿只存在于 draft_* 字段，不再参与预计日期优先级，
            # 否则旧草稿会压过本次文件日期。
            row.expected_ship_date = (
                (file_expected if overwrite_expected else None)
                or row.expected_ship_date
                or effective_expected
            )
        row.set_flags(preserved_flags | new_flags)
        changed = any([
            old['module_name'] != (row.module_name or ''),
            old['expected_ship_date'] != iso(effective_expected),
            old['unit_count'] != row.unit_count,
            old['amount_rmb'] != row.amount_rmb,
            old['plan_status'] != 'active',
        ])
        if changed:
            changed_keys.append(key)
            _audit(user, 'plan', 'update', key, batch_id=batch.id,
                   old_values=old, new_values={
                       'module_name': row.module_name or '',
                       'expected_ship_date': iso(effective_expected),
                       'unit_count': row.unit_count,
                       'amount_rmb': row.amount_rmb,
                   })

    preserved_absent = []
    for key, row in current_rows.items():
        if key in new_by_key or row.plan_status != 'active':
            continue
        if _has_activity(row):
            # 有预计/草稿/承诺/实发/订舱，或手工/单月填报痕迹的行，
            # 即使本次文件没包含，也保留原状态，不静默移除。
            preserved_absent.append(key)
            continue
        old = {'plan_status': row.plan_status, 'expected_ship_date': iso(row.expected_ship_date)}
        row.plan_status = 'removed'
        row.plan_removed_at = now
        flags = set(row.flags())
        if row.commit_status == 'committed':
            flags.add('plan_removed_committed')
        if row.actual_ship_date:
            flags.add('plan_removed_shipped')
        if row.booking_status == '已订舱':
            flags.add('plan_removed_booked')
        row.set_flags(flags)
        _audit(user, 'plan', 'remove', key, batch_id=batch.id,
               old_values=old, new_values={'plan_status': 'removed'})
        changed_keys.append(key)

    if previous:
        previous.status = 'superseded'
    batch.status = 'committed'
    batch.committed_by = user.id
    batch.committed_by_name = user.real_name or user.username
    batch.committed_at = now
    _audit(user, 'import', 'commit_plan', batch_id=batch.id,
           new_values={
               'plan_month': batch.plan_month,
               'version': batch.version,
               'unique_count': batch.unique_count,
               'changed_count': len(set(changed_keys)),
           })
    db.session.commit()
    try:
        from ship_tracking.sync import sync_tracking_dates
        sync_result = sync_tracking_dates(user, source='plan_commit')
    except Exception as exc:
        sync_result = {'ok': False, 'message': str(exc)}
    return {
        'batch_id': batch.id,
        'plan_month': batch.plan_month,
        'version': batch.version,
        'unique_count': batch.unique_count,
        'total_units': batch.total_units,
        'changed_count': len(set(changed_keys)),
        'preserved_absent_count': len(preserved_absent),
        'sync': sync_result,
    }


def _forecast_plan_items(month):
    """从单月填报的最新已提交版本生成计划行（只读 mf_submission）。

    只取 data_month == 计划月份、每个模块 version 最大的一条；
    草稿（mf_ship_selection）不参与。返回 (items, issues, stats)。
    """
    from monthly_forecast.models import Submission

    submissions = Submission.query.filter_by(data_month=month).order_by(
        Submission.module_name, Submission.version.desc()
    ).all()
    latest = {}
    for sub in submissions:
        if sub.module_name in latest:
            continue
        latest[sub.module_name] = sub
    if not latest:
        raise ValueError('该月份没有已提交的模块填报')

    selections = []
    for module in sorted(latest):
        sub = latest[module]
        payload = _loads(sub.payload, {})
        for sel in payload.get('ship_selections') or []:
            sel = sel or {}
            ladder = canonical_ladder(sel.get('ladder_no'))
            if ladder:
                selections.append((module, sub, sel, ladder))
    if not selections:
        raise ValueError('该月份已提交填报中没有发货梯号')

    ledger = _load_ledger([ladder for _, _, _, ladder in selections])
    items = []
    issues = []
    seen = {}
    ledger_missing = 0
    duplicate_submission = 0
    module_mismatch = 0
    module_breakdown = {}
    for module, sub, sel, ladder in selections:
        entry = module_breakdown.setdefault(
            module, {'version': sub.version, 'selections': 0}
        )
        entry['selections'] += 1
        if ladder in seen:
            duplicate_submission += 1
            issues.append(_issue(
                None, 'warning', 'duplicate_submission_ladder',
                '梯号「%s」同时出现在模块 %s / %s，保留前者'
                % (ladder, seen[ladder], module),
            ))
            continue
        seen[ladder] = module
        ledger_row = ledger.get(ladder)
        if not ledger_row:
            ledger_missing += 1
            issues.append(_issue(
                None, 'warning', 'forecast_ledger_missing',
                '梯号「%s」台账未命中，已跳过' % ladder,
            ))
            continue
        flags = ['from_monthly_forecast']
        ledger_module = normalize_text(ledger_row.get('mapped_module'))
        if ledger_module and ledger_module != module:
            flags.append('forecast_module_mismatch')
            module_mismatch += 1
        unit_count = parse_number(sel.get('unit_count'))
        if unit_count is None or unit_count <= 0:
            unit_count = 1
        amount_rmb = parse_number(ledger_row.get('contract_amount_rmb'))
        if amount_rmb is None:
            amount_wan = parse_number(sel.get('amount_wan'))
            amount_rmb = (amount_wan or 0) * 10000.0
        project_name = (
            normalize_text(ledger_row.get('project_name'))
            or normalize_text(sel.get('project_name'))
        )
        items.append({
            'ladder_key': ladder,
            'contract_no': (
                normalize_text(ledger_row.get('contract_no'))
                or normalize_text(sel.get('contract_no'))
                or ladder.split('/')[0]
            ),
            'ladder_no': normalize_text(ledger_row.get('ladder_no')) or ladder,
            'module_name': module,
            'project_name': project_name,
            'business_region': normalize_text(ledger_row.get('business_region')),
            'salesperson': normalize_text(ledger_row.get('salesperson')),
            'unit_count': unit_count,
            'amount_rmb': amount_rmb,
            'source': '单月填报',
            'reporter': sub.submitted_by_name or '',
            'schedule_finish_date': parse_excel_date(ledger_row.get('schedule_finish_date')),
            'whole_ship_date': parse_excel_date(ledger_row.get('whole_ship_date')),
            '_ledger_found': True,
            'original_expected_ship_date': None,
            'business_expected_raw': '',
            'validation_status': 'warning' if flags else 'ok',
            'data_flags': flags,
            'raw': {
                '_source': 'monthly_forecast',
                '_module': module,
                '_version': sub.version,
                '_submission_id': sub.id,
                '_submitted_at': sub.submitted_at.strftime('%Y-%m-%d %H:%M:%S')
                if sub.submitted_at else '',
            },
        })
    if not items:
        raise ValueError('该月份已提交填报中的梯号均未匹配到台账，未生成计划')

    stats = {
        'submission_versions': {module: sub.version for module, sub in sorted(latest.items())},
        'submission_module_count': len(latest),
        'selection_count': len(selections),
        'unique_count': len(items),
        'ledger_missing_count': ledger_missing,
        'duplicate_submission_count': duplicate_submission,
        'module_mismatch_count': module_mismatch,
        'module_breakdown': module_breakdown,
    }
    return items, issues, stats


def preview_plan_from_forecast(month, user):
    """导入管理预览：从单月填报生成增量计划批次，不写追踪表。"""
    if not can_import(user):
        raise PermissionError('无导入权限')
    month = normalize_month(month)
    if not month:
        raise ValueError('请选择计划月份（YYYY-MM）')
    items, issues, stats = _forecast_plan_items(month)

    current_rows = {row.ladder_key: row for row in TrackingItem.query.all()}
    added = existing = restored = skipped_shipped = 0
    breakdown = stats.get('module_breakdown') or {}
    for item in items:
        entry = breakdown.setdefault(
            item['module_name'],
            {'version': stats['submission_versions'].get(item['module_name'], 0),
             'selections': 0, 'added': 0, 'existing': 0, 'restored': 0},
        )
        entry.setdefault('added', 0)
        entry.setdefault('existing', 0)
        entry.setdefault('restored', 0)
        row = current_rows.get(item['ladder_key'])
        if row is None:
            added += 1
            entry['added'] += 1
        elif row.actual_ship_date or row.source_kind == 'actual_only':
            skipped_shipped += 1
        elif row.plan_status == 'active':
            existing += 1
            entry['existing'] += 1
        else:
            restored += 1
            entry['restored'] += 1

    warnings = [issue for issue in issues if issue.get('severity') == 'warning']
    errors = [issue for issue in issues if issue.get('severity') == 'error']
    version = (db.session.query(func.max(ImportBatch.version)).filter(
        ImportBatch.data_type == 'plan_forecast',
        ImportBatch.plan_month == month,
        ImportBatch.status == 'committed',
    ).scalar() or 0) + 1
    summary = {
        'source': 'monthly_forecast',
        'data_month': month,
        'plan_month': month,
        'submission_versions': stats['submission_versions'],
        'submission_module_count': stats['submission_module_count'],
        'selection_count': stats['selection_count'],
        'unique_count': len(items),
        'ledger_missing_count': stats['ledger_missing_count'],
        'duplicate_submission_count': stats['duplicate_submission_count'],
        'module_mismatch_count': stats['module_mismatch_count'],
        'added_count': added,
        'existing_count': existing,
        'restored_count': restored,
        'skipped_shipped_count': skipped_shipped,
        'module_breakdown': breakdown,
        'warning_count': len(warnings),
        'error_count': len(errors),
    }
    file_hash = hashlib.sha256(
        _dump({'month': month, 'versions': stats['submission_versions']}).encode('utf-8')
    ).hexdigest()
    batch = ImportBatch(
        data_type='plan_forecast',
        plan_month=month,
        version=version,
        filename='单月填报生成_%s' % month,
        file_hash=file_hash,
        status='preview',
        row_count=stats['selection_count'],
        unique_count=len(items),
        total_units=round(sum(float(item.get('unit_count') or 0) for item in items), 2),
        duplicate_count=stats['duplicate_submission_count'],
        warning_count=len(warnings),
        error_count=len(errors),
        summary_json=_dump(summary),
        payload_json=_dump(items),
        created_by=user.id,
        created_by_name=user.real_name or user.username,
    )
    db.session.add(batch)
    db.session.flush()
    _store_issues(batch.id, issues)
    db.session.commit()
    result = batch.to_dict()
    result['issues'] = [dict(issue, id=None) for issue in issues[:300]]
    result['issue_total'] = len(issues)
    return result


def commit_forecast_import(batch_id, user):
    """把单月填报批次增量并入追踪表：只新增/恢复，不改已有有效行。"""
    if not can_import(user):
        raise PermissionError('无导入权限')
    batch = db.session.get(ImportBatch, batch_id)
    if not batch or batch.data_type != 'plan_forecast':
        raise ValueError('导入批次不存在')
    if batch.status == 'committed':
        raise ValueError('该批次已提交，不能重复提交')
    if batch.status == 'superseded':
        raise ValueError('该批次已被新版本替代')
    # 预览不再推进版本号，提交时按已生效批次重算。
    previous = ImportBatch.query.filter(
        ImportBatch.id != batch.id,
        ImportBatch.data_type == 'plan_forecast',
        ImportBatch.plan_month == batch.plan_month,
        ImportBatch.status == 'committed',
    ).order_by(ImportBatch.version.desc()).first()
    if previous:
        batch.version = max(batch.version or 0, (previous.version or 0) + 1)
    items = _loads(batch.payload_json, [])
    if not items:
        raise ValueError('批次没有可提交的数据')

    current_rows = {row.ladder_key: row for row in TrackingItem.query.all()}
    now = dt.datetime.now()
    added = restored = skipped_existing = skipped_shipped = 0
    for item in items:
        key = item['ladder_key']
        row = current_rows.get(key)
        if row is not None:
            if row.actual_ship_date or row.source_kind == 'actual_only':
                skipped_shipped += 1
                continue
            if row.plan_status == 'active':
                skipped_existing += 1
                continue
            # 已移除但未实发：恢复计划状态，日期/承诺/订舱原样保留。
            flags = {flag for flag in row.flags() if not str(flag).startswith('plan_removed_')}
            flags.add('restored_from_forecast')
            row.set_flags(flags)
            row.plan_status = 'active'
            row.plan_removed_at = None
            row.plan_month = batch.plan_month
            _audit(user, 'forecast', 'restore', key, batch_id=batch.id,
                   old_values={'plan_status': 'removed'},
                   new_values={'plan_status': 'active', 'module_name': row.module_name or ''})
            restored += 1
            continue

        row = TrackingItem(
            ladder_key=key,
            plan_month=batch.plan_month,
            plan_version=0,
            plan_batch_id=batch.id,
            plan_status='active',
            contract_no=item.get('contract_no') or '',
            ladder_no=item.get('ladder_no') or key,
            module_name=item.get('module_name') or '',
            project_name=item.get('project_name') or '',
            business_region=item.get('business_region') or '',
            salesperson=item.get('salesperson') or '',
            unit_count=float(item.get('unit_count') or 1),
            amount_rmb=float(item.get('amount_rmb') or 0),
            source=item.get('source') or '单月填报',
            reporter=item.get('reporter') or '',
            business_expected_raw='',
            schedule_finish_date=_parse_iso_date(item.get('schedule_finish_date')),
            whole_ship_date=_parse_iso_date(item.get('whole_ship_date')),
            original_expected_ship_date=None,
            expected_ship_date=None,
            commit_status='unplanned',
            booking_status='未订舱',
            source_kind='plan',
        )
        flags = set(item.get('data_flags') or [])
        flags.add('from_monthly_forecast')
        row.set_flags(flags)
        db.session.add(row)
        current_rows[key] = row
        _audit(user, 'forecast', 'add', key, batch_id=batch.id,
               new_values={
                   'module_name': row.module_name or '',
                   'source': '单月填报',
                   'version': (item.get('raw') or {}).get('_version'),
               })
        added += 1

    batch.status = 'committed'
    batch.committed_by = user.id
    batch.committed_by_name = user.real_name or user.username
    batch.committed_at = now
    _audit(user, 'import', 'commit_forecast', batch_id=batch.id,
           new_values={
               'plan_month': batch.plan_month,
               'added_count': added,
               'restored_count': restored,
           })
    db.session.commit()
    try:
        from ship_tracking.sync import sync_tracking_dates
        sync_result = sync_tracking_dates(user, source='forecast_commit')
    except Exception as exc:
        sync_result = {'ok': False, 'message': str(exc)}
    return {
        'batch_id': batch.id,
        'plan_month': batch.plan_month,
        'version': batch.version,
        'added_count': added,
        'restored_count': restored,
        'skipped_existing': skipped_existing,
        'skipped_shipped': skipped_shipped,
        'sync': sync_result,
    }


def parse_booking_file(path):
    rows = []
    issues = []
    for row_number, row in read_sheet_rows(path, min_row=3):
        audit_status = _pick(row, 'C')
        full_ladder = _pick(row, 'AG')
        ladder_raw = _pick(row, 'K')
        document_no = _pick(row, 'B')
        application_date = parse_excel_date(_pick(row, 'H'))
        contract_no = _pick(row, 'AE')
        if not any([audit_status, full_ladder, document_no]):
            continue
        if not full_ladder:
            issues.append(_issue(row_number, 'warning', 'blank_booking_ladder',
                                 '订舱行没有 AG 列完整梯号，未参与匹配', row))
            continue
        ladder_key = canonical_ladder(full_ladder)
        rows.append({
            'ladder_key': ladder_key,
            'document_no': document_no,
            'audit_status': audit_status,
            'current_node': _pick(row, 'D'),
            'application_date': application_date,
            'contract_no': contract_no,
            'ladder_raw': ladder_raw,
            'full_ladder_no': full_ladder,
            'elevator_type': _pick(row, 'AH'),
            'price_term': _pick(row, 'AI'),
            'raw': {letter: _pick(row, letter) for letter in (
                'B', 'C', 'D', 'H', 'K', 'AE', 'AG', 'AH', 'AI'
            )},
        })
    statuses = Counter(item['audit_status'] or '未填写' for item in rows)
    groups = defaultdict(list)
    for item in rows:
        groups[item['ladder_key']].append(item)
    for key, group in groups.items():
        unique_statuses = set(item['audit_status'] for item in group)
        if len(group) > 1 or len(unique_statuses) > 1:
            issues.append({
                'row_number': None,
                'severity': 'info',
                'code': 'multiple_booking_rows',
                'message': '梯号「%s」有 %d 条订舱记录，状态：%s' %
                           (key, len(group), ' / '.join(sorted(unique_statuses))),
                'raw': {},
            })
    summary = {
        'row_count': len(rows),
        'unique_ladder_count': len(groups),
        'blank_ladder_count': sum(1 for issue in issues if issue.get('code') == 'blank_booking_ladder'),
        'status_counts': dict(statuses),
        'multiple_ladder_count': sum(1 for group in groups.values() if len(group) > 1),
    }
    return rows, issues, summary


def _booking_aggregates(rows):
    groups = defaultdict(list)
    for row in rows:
        normalized = dict(row)
        normalized['application_date'] = parse_excel_date(row.get('application_date'))
        groups[normalized['ladder_key']].append(normalized)
    result = {}
    for key, group in groups.items():
        non_void = [row for row in group if row.get('audit_status') != '已作废']
        completed = [row for row in non_void if row.get('audit_status') == '已完成']
        if completed:
            chosen = sorted(
                completed,
                key=lambda row: (row.get('application_date') or dt.date.min, row.get('document_no') or ''),
                reverse=True,
            )[0]
            status = '已订舱'
            audit = '已完成'
        elif non_void:
            chosen = sorted(
                non_void,
                key=lambda row: (row.get('application_date') or dt.date.min, row.get('document_no') or ''),
                reverse=True,
            )[0]
            status = '已订舱'
            audit = chosen.get('audit_status') or '审批中'
        else:
            chosen = sorted(
                group,
                key=lambda row: (row.get('application_date') or dt.date.min, row.get('document_no') or ''),
                reverse=True,
            )[0]
            status = '未订舱'
            audit = '已作废'
        dates = [row.get('application_date') for row in non_void if row.get('application_date')]
        result[key] = {
            'booking_status': status,
            'booking_audit_status': audit,
            'booking_record_count': len(group),
            'booking_last_date': max(dates) if dates else None,
            'chosen': chosen,
        }
    return result


def preview_booking_import(path, filename, user):
    if not can_import(user):
        raise PermissionError('无导入权限')
    rows, issues, parsed_summary = parse_booking_file(path)
    if not rows:
        raise ValueError('未读取到订舱数据，请确认 AG 列存在完整梯号')
    aggregates = _booking_aggregates(rows)
    tracking = {row.ladder_key: row for row in TrackingItem.query.all()}
    matched = [key for key in aggregates if key in tracking]
    unmatched = [key for key in aggregates if key not in tracking]
    current_booked = sum(1 for row in tracking.values() if row.booking_status == '已订舱')
    # 提交时未出现在报表中的追踪行会统一重置为未订舱，预览先把范围和样本说清楚。
    reset_keys = sorted(key for key in tracking if key not in aggregates)
    summary = dict(parsed_summary)
    summary.update({
        'matched_plan_count': len(matched),
        'unmatched_plan_count': len(unmatched),
        'current_booked_count': current_booked,
        'preview_booked_count': sum(1 for value in aggregates.values() if value['booking_status'] == '已订舱'),
        'unmatched_sample': unmatched[:80],
        'matched_sample': matched[:80],
        'reset_count': len(reset_keys),
        'reset_sample': reset_keys[:80],
    })
    file_hash = file_sha256(path)
    version = (db.session.query(func.max(ImportBatch.version)).filter(
        ImportBatch.data_type == 'booking',
        ImportBatch.status == 'committed',
    ).scalar() or 0) + 1
    batch = ImportBatch(
        data_type='booking',
        plan_month=default_month(),
        version=version,
        filename=os.path.basename(filename),
        file_hash=file_hash,
        status='preview',
        row_count=len(rows),
        unique_count=len(aggregates),
        duplicate_count=parsed_summary.get('multiple_ladder_count', 0),
        warning_count=sum(1 for issue in issues if issue.get('severity') == 'warning'),
        error_count=0,
        summary_json=_dump(summary),
        payload_json=_dump(rows),
        created_by=user.id,
        created_by_name=user.real_name or user.username,
    )
    db.session.add(batch)
    db.session.flush()
    _store_issues(batch.id, issues)
    db.session.commit()
    result = batch.to_dict()
    result['issues'] = [dict(issue, id=None) for issue in issues[:300]]
    result['issue_total'] = len(issues)
    return result


def commit_booking_import(batch_id, user, force=False):
    if not can_import(user):
        raise PermissionError('无导入权限')
    batch = db.session.get(ImportBatch, batch_id)
    if not batch or batch.data_type != 'booking':
        raise ValueError('导入批次不存在')
    if batch.status == 'committed':
        raise ValueError('该批次已提交，不能重复提交')
    duplicate = ImportBatch.query.filter(
        ImportBatch.id != batch.id,
        ImportBatch.data_type == 'booking',
        ImportBatch.file_hash == batch.file_hash,
        ImportBatch.status == 'committed',
    ).first()
    if duplicate and not force:
        raise ValueError('相同订舱文件已导入过，如确认重新导入，请勾选强制执行')
    # 预览不再推进版本号，提交时按已生效批次重算，保证版本单调递增。
    previous = ImportBatch.query.filter(
        ImportBatch.id != batch.id,
        ImportBatch.data_type == 'booking',
        ImportBatch.status == 'committed',
    ).order_by(ImportBatch.version.desc()).first()
    if previous:
        batch.version = max(batch.version or 0, (previous.version or 0) + 1)
    rows = _loads(batch.payload_json, [])
    if not rows:
        raise ValueError('批次没有可提交的数据')
    aggregates = _booking_aggregates(rows)
    BookingRecord.query.filter_by(is_current=True).update({'is_current': False})
    for item in rows:
        db.session.add(BookingRecord(
            batch_id=batch.id,
            ladder_key=item.get('ladder_key') or '',
            document_no=item.get('document_no') or '',
            audit_status=item.get('audit_status') or '',
            current_node=item.get('current_node') or '',
            application_date=_parse_iso_date(item.get('application_date')),
            contract_no=item.get('contract_no') or '',
            ladder_raw=item.get('ladder_raw') or '',
            full_ladder_no=item.get('full_ladder_no') or '',
            elevator_type=item.get('elevator_type') or '',
            price_term=item.get('price_term') or '',
            is_current=True,
            raw_json=_dump(item.get('raw') or {}),
        ))
    matched = 0
    reset_count = 0
    for row in TrackingItem.query.all():
        aggregate = aggregates.get(row.ladder_key)
        if aggregate:
            row.booking_status = aggregate['booking_status']
            row.booking_audit_status = aggregate['booking_audit_status']
            row.booking_record_count = aggregate['booking_record_count']
            row.booking_last_date = aggregate['booking_last_date']
            matched += 1
        else:
            reset_count += 1
            row.booking_status = '未订舱'
            row.booking_audit_status = ''
            row.booking_record_count = 0
            row.booking_last_date = None
    batch.status = 'committed'
    batch.committed_by = user.id
    batch.committed_by_name = user.real_name or user.username
    batch.committed_at = dt.datetime.now()
    _audit(user, 'import', 'commit_booking', batch_id=batch.id,
           new_values={'matched_plan_count': matched, 'row_count': len(rows)})
    db.session.commit()
    return {
        'batch_id': batch.id,
        'row_count': len(rows),
        'unique_count': batch.unique_count,
        'matched_plan_count': matched,
        'reset_count': reset_count,
    }


def delete_import_batch(batch_id, user):
    """删除未提交的预览批次；已生效/已替代的批次必须保留留痕。"""
    if not can_import(user):
        raise PermissionError('无导入权限')
    batch = db.session.get(ImportBatch, batch_id)
    if not batch:
        raise ValueError('导入批次不存在')
    if batch.status != 'preview':
        raise ValueError('只有预览状态的批次可以删除')
    ImportIssue.query.filter_by(batch_id=batch.id).delete(synchronize_session=False)
    _audit(user, 'import', 'delete_preview_batch', batch_id=batch.id,
           reason='清理预览批次',
           old_values={'filename': batch.filename, 'data_type': batch.data_type,
                       'plan_month': batch.plan_month, 'version': batch.version})
    db.session.delete(batch)
    db.session.commit()
    return {'deleted': batch_id}


def cleanup_preview_batches(user, data_type=''):
    """一键清理预览批次，返回删除条数。"""
    if not can_import(user):
        raise PermissionError('无导入权限')
    query = ImportBatch.query.filter(ImportBatch.status == 'preview')
    if data_type:
        query = query.filter(ImportBatch.data_type == data_type)
    batches = query.all()
    ids = [batch.id for batch in batches]
    if ids:
        ImportIssue.query.filter(ImportIssue.batch_id.in_(ids)).delete(synchronize_session=False)
        _audit(user, 'import', 'cleanup_preview_batches',
               reason='批量清理预览批次',
               new_values={'deleted': len(ids), 'batch_ids': ids[:100]})
        ImportBatch.query.filter(ImportBatch.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
    return {'deleted': len(ids)}
