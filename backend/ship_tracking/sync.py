# -*- coding: utf-8 -*-
"""把台账的「排产完工日期」「整梯发货日期」「回款比例」「组A日期」同步到已追踪梯号。

口径：
- 台账行存在：同步排产完工、整梯发货、回款比例；实际发货日期取组A日期；
- 台账无该梯号：保留排产完工/整梯发货旧值，清空回款比例，实际发货日期回退到每日实发；
- 台账为空：保留排产完工/整梯发货/回款比例，仅按每日实发重算实际发货日期；
- 实际发货日期：台账组A日期优先，否则取有效每日实发，两边都没有则清空；
- 不修改模块、金额、人员、承诺、订舱等字段。
"""
import os
import time
from collections import defaultdict

from flask import current_app, has_app_context
from sqlalchemy import bindparam, text

from models import db
from ship_tracking.excel_reader import (
    canonical_ladder, parse_excel_date, parse_number,
)
from ship_tracking.models import AuditLog, DailyShipment, TrackingItem
from ship_tracking.services import _audit, _loads, iso

LOCK_NAME = '.ship_tracking_sync.lock'
LOCK_STALE_SECONDS = 600
MAX_ROW_AUDIT = 500


def _lock_path():
    if has_app_context():
        root = current_app.root_path
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, 'instance', LOCK_NAME)


def _acquire_lock(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode('ascii'))
        os.close(fd)
        return True
    except FileExistsError:
        try:
            if time.time() - os.path.getmtime(path) > LOCK_STALE_SECONDS:
                os.remove(path)
                return _acquire_lock(path)
        except OSError:
            pass
        return False


def _release_lock(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _amount(row):
    value = parse_number(row.get('contract_amount_rmb'))
    return value if value is not None else 0


def load_daily_shipment_dates(ladder_keys):
    keys = sorted({canonical_ladder(key) for key in ladder_keys if key})
    if not keys:
        return {}
    result = {}
    for start in range(0, len(keys), 500):
        chunk = keys[start:start + 500]
        rows = DailyShipment.query.filter(
            DailyShipment.is_void.is_(False),
            DailyShipment.ladder_key.in_(chunk),
        ).order_by(DailyShipment.id.desc()).all()
        for row in rows:
            ladder = canonical_ladder(row.ladder_key)
            if ladder and ladder not in result and row.ship_date:
                result[ladder] = row.ship_date
    return result


def load_ledger_dates(ladder_keys):
    """返回 ({ladder_key: {schedule_finish_date, whole_ship_date, payment_ratio}}, ok, error)。"""
    keys = sorted({canonical_ladder(key) for key in ladder_keys if key})
    if not keys:
        return {}, True, '', 0
    statement = text(
        "SELECT id, ladder_no, contract_amount_rmb, schedule_finish_date, whole_ship_date, payment_ratio "
        "FROM cc_ledger_contract WHERE source = 'ledger' AND ladder_no IN :keys"
    ).bindparams(bindparam('keys', expanding=True))
    grouped = defaultdict(list)
    delivery_grouped = defaultdict(list)
    delivery_by_id = {}
    delivery_statement = text(
        'SELECT id, ladder_no, contract_amount_rmb, delivery_date '
        'FROM cc_ledger_contract WHERE source = :source AND ladder_no IN :keys'
    ).bindparams(bindparam('keys', expanding=True))
    try:
        for start in range(0, len(keys), 500):
            chunk = keys[start:start + 500]
            rows = db.session.execute(statement, {'keys': chunk}).mappings().all()
            for row in rows:
                ladder = canonical_ladder(row.get('ladder_no'))
                if ladder:
                    grouped[ladder].append(row)
            delivery_rows = db.session.execute(
                delivery_statement, {'source': 'ledger', 'keys': chunk}
            ).mappings().all()
            for row in delivery_rows:
                delivery_by_id[row.get('id')] = row.get('delivery_date')
                ladder = canonical_ladder(row.get('ladder_no'))
                if ladder:
                    delivery_grouped[ladder].append(row)
        total = db.session.execute(text(
            "SELECT COUNT(*) FROM cc_ledger_contract WHERE source = 'ledger'"
        )).scalar() or 0
    except Exception as exc:
        db.session.rollback()
        return {}, False, str(exc), 0
    if total == 0:
        return {}, True, '', 0

    result = {}
    for ladder, rows in grouped.items():
        # 同梯号多行时合同额最大者为主，主行日期为空再用其它行非空值补齐。
        primary = max(rows, key=_amount)
        schedule = parse_excel_date(primary.get('schedule_finish_date'))
        whole = parse_excel_date(primary.get('whole_ship_date'))
        ratio = parse_number(primary.get('payment_ratio'))
        delivery = parse_excel_date(delivery_by_id.get(primary.get('id')))
        if schedule is None:
            for row in rows:
                schedule = parse_excel_date(row.get('schedule_finish_date'))
                if schedule:
                    break
        if whole is None:
            for row in rows:
                whole = parse_excel_date(row.get('whole_ship_date'))
                if whole:
                    break
        if delivery is None:
            for row in delivery_grouped.get(ladder, []):
                delivery = parse_excel_date(row.get('delivery_date'))
                if delivery:
                    break
        result[ladder] = {
            'schedule_finish_date': schedule,
            'whole_ship_date': whole,
            'payment_ratio': ratio,
            'delivery_date': delivery,
        }
    return result, True, '', total


def _stats(scanned, matched, missing, updated, schedule_changed, whole_changed,
           ratio_changed, started):
    return {
        'scanned': scanned,
        'matched': matched,
        'ledger_missing': missing,
        'updated': updated,
        'schedule_changed': schedule_changed,
        'whole_changed': whole_changed,
        'ratio_changed': ratio_changed,
        'actual_changed': 0,
        'source_changed': 0,
        'duration_ms': int((time.time() - started) * 1000),
    }


def _record_run(user, source, status, stats):
    _audit(
        user, 'sync', 'sync_run', reason=source,
        new_values=dict(stats, status=status),
    )


def sync_tracking_dates(user=None, source='manual', dry_run=False):
    started = time.time()
    lock_path = _lock_path()
    if not _acquire_lock(lock_path):
        return {
            'ok': True,
            'skipped': True,
            'message': '已有同步任务在运行，本次跳过',
        }
    stats = _stats(0, 0, 0, 0, 0, 0, 0, started)
    try:
        rows = TrackingItem.query.order_by(TrackingItem.id).all()
        stats['scanned'] = len(rows)
        if not rows:
            _record_run(user, source, 'ok', stats)
            if dry_run:
                db.session.rollback()
            else:
                db.session.commit()
            return dict(stats, ok=True)

        dates, ok, error, ledger_total = load_ledger_dates([row.ladder_key for row in rows])
        if not ok:
            stats['message'] = error
            _record_run(user, source, 'error', stats)
            if dry_run:
                db.session.rollback()
            else:
                db.session.commit()
            return dict(stats, ok=False)

        matched = 0
        missing = 0
        updated_keys = set()
        schedule_changed = 0
        whole_changed = 0
        ratio_changed = 0
        audit_count = 0
        for row in rows:
            info = dates.get(canonical_ladder(row.ladder_key))
            if info is None:
                missing += 1
                if ledger_total == 0:
                    continue
                # 回款比例没有“保留旧值”的意义：台账已无该梯号时清空，页面显示为“—”。
                if row.payment_ratio is not None:
                    old_values = {'payment_ratio': row.payment_ratio}
                    new_values = {'payment_ratio': None}
                    row.payment_ratio = None
                    ratio_changed += 1
                    updated_keys.add(row.ladder_key)
                    if audit_count < MAX_ROW_AUDIT:
                        _audit(
                            user, 'sync', 'sync_update', row.ladder_key,
                            old_values=old_values, new_values=new_values,
                        )
                        audit_count += 1
                continue
            matched += 1
            old_values = {}
            new_values = {}
            new_schedule = info.get('schedule_finish_date')
            new_whole = info.get('whole_ship_date')
            if row.schedule_finish_date != new_schedule:
                old_values['schedule_finish_date'] = iso(row.schedule_finish_date)
                new_values['schedule_finish_date'] = iso(new_schedule)
                row.schedule_finish_date = new_schedule
                schedule_changed += 1
            if row.whole_ship_date != new_whole:
                old_values['whole_ship_date'] = iso(row.whole_ship_date)
                new_values['whole_ship_date'] = iso(new_whole)
                row.whole_ship_date = new_whole
                whole_changed += 1
            new_ratio = info.get('payment_ratio')
            if row.payment_ratio != new_ratio:
                old_values['payment_ratio'] = row.payment_ratio
                new_values['payment_ratio'] = new_ratio
                row.payment_ratio = new_ratio
                ratio_changed += 1
            if new_values:
                updated_keys.add(row.ladder_key)
                if audit_count < MAX_ROW_AUDIT:
                    _audit(
                        user, 'sync', 'sync_update', row.ladder_key,
                        old_values=old_values, new_values=new_values,
                    )
                    audit_count += 1

        daily_dates = load_daily_shipment_dates([row.ladder_key for row in rows])
        actual_changed = 0
        source_changed = 0
        for row in rows:
            key = canonical_ladder(row.ladder_key)
            info = dates.get(key)
            ledger_delivery = info.get('delivery_date') if info else None
            daily_delivery = daily_dates.get(key)
            new_actual = ledger_delivery or daily_delivery
            new_source = 'ledger' if ledger_delivery else ('daily' if daily_delivery else None)
            old_values = {}
            new_values = {}
            if row.actual_ship_date != new_actual:
                old_values['actual_ship_date'] = iso(row.actual_ship_date)
                new_values['actual_ship_date'] = iso(new_actual)
                row.actual_ship_date = new_actual
                actual_changed += 1
            if (row.actual_ship_source or None) != new_source:
                old_values['actual_ship_source'] = row.actual_ship_source
                new_values['actual_ship_source'] = new_source
                row.actual_ship_source = new_source
                source_changed += 1
            if new_values:
                updated_keys.add(row.ladder_key)
                if audit_count < MAX_ROW_AUDIT:
                    _audit(
                        user, 'sync', 'sync_update', row.ladder_key,
                        old_values=old_values, new_values=new_values,
                    )
                    audit_count += 1

        stats.update({
            'matched': matched,
            'ledger_missing': missing,
            'updated': len(updated_keys),
            'schedule_changed': schedule_changed,
            'whole_changed': whole_changed,
            'ratio_changed': ratio_changed,
            'actual_changed': actual_changed,
            'source_changed': source_changed,
            'duration_ms': int((time.time() - started) * 1000),
        })
        stats['audit_truncated'] = max(0, len(updated_keys) - audit_count)
        _record_run(user, source, 'ok', stats)
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
        return dict(stats, ok=True)
    except Exception as exc:
        db.session.rollback()
        stats['message'] = str(exc)
        stats['duration_ms'] = int((time.time() - started) * 1000)
        try:
            _record_run(user, source, 'error', stats)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return dict(stats, ok=False)
    finally:
        _release_lock(lock_path)


def get_sync_status():
    row = AuditLog.query.filter_by(
        category='sync', action='sync_run'
    ).order_by(AuditLog.id.desc()).first()
    if not row:
        return {
            'last_run_at': '',
            'status': '',
            'operator_name': '',
            'source': '',
            'message': '尚未执行过台账字段同步',
            'stats': {},
        }
    values = dict(_loads(row.new_values, {}))
    status = values.pop('status', '')
    message = values.pop('message', '')
    return {
        'last_run_at': row.created_at.strftime('%Y-%m-%d %H:%M:%S') if row.created_at else '',
        'status': status,
        'operator_name': row.operator_name or '系统',
        'source': row.reason or '',
        'message': message,
        'stats': values,
    }
