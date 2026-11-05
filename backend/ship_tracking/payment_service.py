# -*- coding: utf-8 -*-
"""回款比例计算服务：文件上传、后台任务、状态、审计下载。

只读写 st_ 表；表 C 只读 cc_ledger_contract。
"""
import hashlib
import io
import json
import os
import threading
import time
from datetime import datetime, timedelta

import pandas as pd
from flask import current_app
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import text
from werkzeug.utils import secure_filename

from models import User, db
from ship_tracking.excel_reader import canonical_ladder
from ship_tracking.models import (
    PaymentCalcDetail, PaymentCalcRun, PaymentFile, TrackingItem,
)
from ship_tracking.payment_calc import (
    calculate_payment_ratios, load_exchange_rates,
)
from ship_tracking.services import _audit


FILE_TYPES = {
    'table_b': {
        'label': '表B 外币回款台账',
        'extensions': ('.xlsx', '.xls'),
        'required': True,
        'hint': '24-26 年外币回款台账，需包含 2024/2025/2026 三个 sheet',
    },
    'table_e': {
        'label': '表E 抵佣金明细',
        'extensions': ('.xls', '.xlsx'),
        'required': True,
        'hint': 'gm_ht_hthkmx，合同回款明细，只取款项类型=抵佣金',
    },
    'table_r': {
        'label': '表R 人民币回款台账',
        'extensions': ('.xlsx', '.xls'),
        'required': True,
        'hint': '人民币回款台账，需包含 2025/2026 两个 sheet',
    },
    'exchange_rate': {
        'label': '汇率对应表',
        'extensions': ('.txt',),
        'required': True,
        'hint': '汇率对应 txt，格式为 1美元对人民币 6.8167',
    },
}
REQUIRED_FILE_TYPES = [key for key, value in FILE_TYPES.items() if value['required']]

PAYMENT_CONFIG = {
    'table_b': {
        'sheets': {
            2024: {
                'amount_col': '金额（小）', 'fee_col': '手续费',
                'contract_col': '合同号', 'currency_col': '币种',
                'tid_col': '梯号', 'remark_col': '备注',
            },
            2025: {
                'amount_col': '收款金额', 'fee_col': '实收手续费',
                'contract_col': '合同号', 'currency_col': '币种',
                'tid_col': '梯号', 'remark_col': '备注',
            },
            2026: {
                'amount_col': '收款金额', 'fee_col': '实收手续费',
                'contract_col': '合同号', 'currency_col': '币种',
                'tid_col': '梯号', 'remark_col': '备注',
            },
        },
    },
    'table_e': {
        'contract_col': '合同编号', 'elevator_col': '标的编号',
        'type_col': '款项类型', 'amount_col': '回款金额(原币)',
        'currency_col': '币种', 'header_rows': 2,
    },
    'table_r': {
        'sheets': ['2025', '2026'],
        'contract_col': '合同号', 'amount_col': '金额',
        'nature_col': '回款性质',
    },
}

LOCK_NAME = '.ship_tracking_payment_calc.lock'
LOCK_STALE_SECONDS = 1800
RUN_STALE_MINUTES = 30
_TASK_LOCK = threading.Lock()


def _payment_dir():
    configured = current_app.config.get('SHIP_TRACKING_PAYMENT_DIR')
    if configured:
        return configured
    return os.path.join(current_app.root_path, 'uploads', 'ship_tracking', 'payment_calc')


def _lock_path():
    return os.path.join(current_app.root_path, 'instance', LOCK_NAME)


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


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _file_type_label(file_type):
    return FILE_TYPES.get(file_type, {}).get('label', file_type)


def _active_files():
    rows = PaymentFile.query.filter_by(is_active=True)\
        .order_by(PaymentFile.uploaded_at.desc(), PaymentFile.id.desc()).all()
    result = {}
    for row in rows:
        if row.file_type not in result:
            result[row.file_type] = row
    return result


def _missing_required_files(files):
    missing = []
    for key in REQUIRED_FILE_TYPES:
        record = files.get(key)
        if record is None or not record.stored_path or not os.path.exists(record.stored_path):
            missing.append(key)
    return missing


def _cleanup_stale_runs():
    deadline = datetime.now() - timedelta(minutes=RUN_STALE_MINUTES)
    stale = PaymentCalcRun.query.filter(
        PaymentCalcRun.status == 'running',
        PaymentCalcRun.started_at < deadline,
    ).all()
    if not stale:
        return
    for run in stale:
        run.status = 'failed'
        run.finished_at = datetime.now()
        run.message = '计算超时或进程中断，请重新计算'
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def _validate_header(path, sheet, required, header=0, engine=None):
    kwargs = {'sheet_name': sheet, 'header': header, 'nrows': 0}
    if engine:
        kwargs['engine'] = engine
    try:
        head = pd.read_excel(path, **kwargs)
    except Exception as exc:
        return False, '%s 读取失败: %s' % (sheet, exc)
    columns = {str(column).strip() for column in head.columns}
    missing = [name for name in required if str(name).strip() not in columns]
    if missing:
        return False, '%s 缺少列: %s' % (sheet, '、'.join(missing))
    return True, ''


def validate_payment_file(file_type, path):
    if file_type not in FILE_TYPES:
        return False, '未知文件类型: %s' % file_type
    extension = os.path.splitext(path)[1].lower()
    if extension not in FILE_TYPES[file_type]['extensions']:
        return False, '%s 只允许 %s' % (
            _file_type_label(file_type), ' / '.join(FILE_TYPES[file_type]['extensions']))
    if file_type == 'exchange_rate':
        try:
            rates = load_exchange_rates(path)
        except Exception as exc:
            return False, '汇率文件解析失败: %s' % exc
        if len(rates) <= 4:
            return False, '汇率文件没有解析到有效汇率'
        return True, ''
    if file_type == 'table_b':
        for sheet, cfg in PAYMENT_CONFIG['table_b']['sheets'].items():
            required = [
                cfg['contract_col'], cfg['tid_col'], cfg['amount_col'],
                cfg['fee_col'], cfg['currency_col'], cfg['remark_col'],
            ]
            ok, message = _validate_header(path, str(sheet), required)
            if not ok:
                return False, message
        return True, ''
    if file_type == 'table_e':
        cfg = PAYMENT_CONFIG['table_e']
        engine = 'openpyxl' if extension == '.xlsx' else 'xlrd'
        required = [
            cfg['contract_col'], cfg['elevator_col'], cfg['type_col'],
            cfg['amount_col'], cfg['currency_col'],
        ]
        return _validate_header(path, 0, required, header=cfg['header_rows'], engine=engine)
    if file_type == 'table_r':
        cfg = PAYMENT_CONFIG['table_r']
        required = [cfg['contract_col'], cfg['amount_col'], cfg['nature_col']]
        for sheet in cfg['sheets']:
            ok, message = _validate_header(path, str(sheet), required)
            if not ok:
                return False, message
        return True, ''
    return False, '未配置文件校验规则'


def save_payment_file(file_type, upload, user=None):
    if file_type not in FILE_TYPES:
        raise ValueError('未知文件类型')
    original_name = os.path.basename(upload.filename or '')
    if not original_name:
        raise ValueError('文件名不能为空')
    extension = os.path.splitext(original_name)[1].lower()
    if extension not in FILE_TYPES[file_type]['extensions']:
        raise ValueError('%s 只允许 %s' % (
            _file_type_label(file_type), ' / '.join(FILE_TYPES[file_type]['extensions'])))
    safe_name = secure_filename(original_name)
    if not safe_name:
        safe_name = 'upload%s' % extension
    folder = os.path.join(_payment_dir(), file_type)
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    stored_path = os.path.join(folder, '%s_%s' % (stamp, safe_name))
    upload.save(stored_path)
    try:
        ok, message = validate_payment_file(file_type, stored_path)
        if not ok:
            raise ValueError(message)
        file_hash = _sha256(stored_path)
        PaymentFile.query.filter_by(file_type=file_type, is_active=True)\
            .update({'is_active': False}, synchronize_session=False)
        record = PaymentFile(
            file_type=file_type,
            filename=original_name,
            stored_path=stored_path,
            file_size=os.path.getsize(stored_path),
            file_hash=file_hash,
            is_active=True,
            status='validated',
            message='文件校验通过',
            uploaded_by=user.id if user else None,
            uploaded_by_name=(user.real_name or user.username) if user else '系统',
        )
        db.session.add(record)
        db.session.commit()
        return record
    except Exception:
        try:
            os.remove(stored_path)
        except OSError:
            pass
        db.session.rollback()
        raise


def get_payment_status():
    _cleanup_stale_runs()
    files = _active_files()
    latest_run = PaymentCalcRun.query.order_by(PaymentCalcRun.id.desc()).first()
    running = PaymentCalcRun.query.filter_by(status='running')\
        .order_by(PaymentCalcRun.id.desc()).first()
    missing = _missing_required_files(files)
    return {
        'files': {
            key: files[key].to_dict() if key in files else None
            for key in FILE_TYPES
        },
        'file_types': {
            key: {
                'label': value['label'],
                'hint': value['hint'],
                'extensions': list(value['extensions']),
                'required': value['required'],
            }
            for key, value in FILE_TYPES.items()
        },
        'missing': missing,
        'missing_labels': [_file_type_label(key) for key in missing],
        'last_run': latest_run.to_dict() if latest_run else None,
        'running': running.to_dict() if running else None,
        'can_calculate': not missing and running is None,
        'scope_note': '只更新发货梯号明细的回款比例，不改台账、合同看板和其他模块。',
    }


def _create_run(trigger_source, user):
    run = PaymentCalcRun(
        status='running',
        trigger_source=trigger_source,
        operator_id=user.id if user else None,
        operator_name=(user.real_name or user.username) if user else '系统',
        started_at=datetime.now(),
    )
    db.session.add(run)
    db.session.commit()
    return run


def _create_skipped_run(trigger_source, user, message):
    run = PaymentCalcRun(
        status='skipped',
        trigger_source=trigger_source,
        operator_id=user.id if user else None,
        operator_name=(user.real_name or user.username) if user else '系统',
        started_at=datetime.now(),
        finished_at=datetime.now(),
        message=message,
    )
    db.session.add(run)
    db.session.commit()
    return run


def start_payment_calc(user=None, trigger='manual', background=True):
    _cleanup_stale_runs()
    files = _active_files()
    missing = _missing_required_files(files)
    if missing:
        run = _create_skipped_run(trigger, user, '缺少文件: %s' % '、'.join(
            _file_type_label(key) for key in missing))
        return {'started': False, 'run_id': run.id, 'message': run.message}
    lock_path = _lock_path()
    if not _TASK_LOCK.acquire(blocking=False):
        return {'started': False, 'message': '已有计算任务在运行'}
    try:
        if not _acquire_lock(lock_path):
            _TASK_LOCK.release()
            return {'started': False, 'message': '已有计算任务在运行'}
        run = _create_run(trigger, user)
    except Exception:
        _TASK_LOCK.release()
        raise

    if not background:
        try:
            _run_calc(run.id)
            return {'started': True, 'run_id': run.id, 'finished': True}
        finally:
            _TASK_LOCK.release()
            _release_lock(lock_path)

    app = current_app._get_current_object()
    try:
        thread = threading.Thread(
            target=_run_calc_thread,
            args=(app, run.id, lock_path),
            daemon=True,
            name='ship-tracking-payment-calc',
        )
        thread.start()
    except Exception:
        _TASK_LOCK.release()
        _release_lock(lock_path)
        _update_run_failed(run.id, '计算线程启动失败')
        raise
    return {'started': True, 'run_id': run.id, 'message': '计算已开始'}


def _run_calc_thread(app, run_id, lock_path):
    try:
        with app.app_context():
            try:
                _run_calc(run_id)
            finally:
                db.session.remove()
    finally:
        _TASK_LOCK.release()
        _release_lock(lock_path)


def _update_run_failed(run_id, message):
    try:
        run = PaymentCalcRun.query.get(run_id)
        if run:
            run.status = 'failed'
            run.finished_at = datetime.now()
            run.message = str(message)[:4000]
            db.session.commit()
    except Exception:
        db.session.rollback()


def _load_target_rows():
    ledger_rows = db.session.execute(text(
        "SELECT ladder_no, contract_no, currency, contract_amount_orig, "
        "contract_amount_rmb, exchange_rate, payment_ratio "
        "FROM cc_ledger_contract WHERE source = 'ledger'"
    )).mappings().all()
    ledger_ratio = {}
    for row in ledger_rows:
        ladder = canonical_ladder(row.get('ladder_no'))
        if ladder:
            ledger_ratio[ladder] = row.get('payment_ratio')

    tracking_rows = []
    for item in TrackingItem.query.order_by(TrackingItem.id).all():
        ladder = canonical_ladder(item.ladder_no)
        ratio = ledger_ratio.get(ladder)
        try:
            ratio_value = float(ratio) if ratio is not None else None
        except (TypeError, ValueError):
            ratio_value = None
        if ratio_value is not None and ratio_value >= 1:
            continue
        tracking_rows.append({
            'id': item.id,
            'ladder_key': item.ladder_key or ladder,
            'ladder_no': item.ladder_no or ladder,
            'contract_no': item.contract_no or '',
            'payment_ratio': item.payment_ratio,
        })
    return [dict(row) for row in ledger_rows], tracking_rows


def _run_calc(run_id):
    run = PaymentCalcRun.query.get(run_id)
    if run is None or run.status != 'running':
        return
    started = time.time()
    try:
        files = _active_files()
        missing = _missing_required_files(files)
        if missing:
            raise ValueError('缺少文件: %s' % '、'.join(
                _file_type_label(key) for key in missing))
        file_paths = {
            'table_b': files['table_b'].stored_path,
            'table_e': files['table_e'].stored_path,
            'table_r': files['table_r'].stored_path,
        }
        exchange_rate_path = files['exchange_rate'].stored_path
        for path in list(file_paths.values()) + [exchange_rate_path]:
            if not path or not os.path.exists(path):
                raise ValueError('文件不存在: %s' % path)

        ledger_rows, target_rows = _load_target_rows()
        # 文件解析通常需要数秒到十几秒；先结束只读事务，避免 SQLite 读锁期间影响其他用户录入。
        db.session.commit()
        if not target_rows:
            run.status = 'success'
            run.finished_at = datetime.now()
            run.duration_ms = int((time.time() - started) * 1000)
            run.message = '没有未满 100% 的梯号需要计算'
            db.session.commit()
            return

        result = calculate_payment_ratios(
            ledger_rows, target_rows, file_paths, exchange_rate_path, PAYMENT_CONFIG)
        results = result['results']
        stats = dict(result['stats'])
        warnings = result.get('warnings') or []
        record_counts = result.get('record_counts') or {}

        items = TrackingItem.query.order_by(TrackingItem.id).all()
        by_ladder = {canonical_ladder(item.ladder_no): item for item in items}
        changed = 0
        kept = 0
        errors = 0
        for row in results:
            item = by_ladder.get(canonical_ladder(row.get('ladder_no')))
            if item is None:
                errors += 1
                continue
            write_ratio = row.get('write_ratio')
            if write_ratio is None:
                kept += 1
            else:
                old_ratio = item.payment_ratio
                if old_ratio is None or abs(float(old_ratio) - float(write_ratio)) > 1e-9:
                    item.payment_ratio = float(write_ratio)
                    changed += 1
            detail = PaymentCalcDetail(
                run_id=run.id,
                ladder_key=item.ladder_key or canonical_ladder(item.ladder_no),
                contract_no=row.get('contract_no') or '',
                ladder_no=row.get('ladder_no') or '',
                ledger_ratio=row.get('ledger_ratio'),
                calculated_ratio=row.get('calculated_ratio'),
                calculated_ratio_display=row.get('display_ratio'),
                paid_rmb=row.get('paid_rmb') or 0.0,
                pending_rmb=row.get('pending_rmb') or 0.0,
                status=row.get('status') or '',
                message=row.get('message') or '',
                payments_json=json.dumps(row.get('payments') or {}, ensure_ascii=False),
                allocations_json=json.dumps(row.get('allocations') or [], ensure_ascii=False),
            )
            db.session.add(detail)

        run.status = 'success'
        run.finished_at = datetime.now()
        run.target_count = stats.get('target_count', len(results))
        run.calculated_count = stats.get('calculated_count', 0)
        run.changed_count = changed
        run.kept_ledger_count = stats.get('kept_ledger_count', kept)
        run.zero_count = stats.get('zero_count', 0)
        run.missing_ledger_count = stats.get('missing_ledger_count', 0)
        run.no_payment_count = stats.get('no_payment_count', 0)
        run.error_count = errors
        run.warning_count = len(warnings)
        run.duration_ms = int((time.time() - started) * 1000)
        run.message = '计算完成：目标 %s，更新 %s，保留 %s，异常 %s' % (
            run.target_count, changed, run.kept_ledger_count, errors)
        run.stats_json = json.dumps({
            **stats,
            'warnings': warnings[:500],
            'record_counts': record_counts,
            'duration_ms': run.duration_ms,
        }, ensure_ascii=False)
        _audit(
            User.query.get(run.operator_id) if run.operator_id else None,
            'payment', 'calc_run', reason=run.trigger_source,
            new_values={
                'run_id': run.id,
                'target_count': run.target_count,
                'changed_count': changed,
                'kept_ledger_count': kept,
                'error_count': errors,
                'duration_ms': run.duration_ms,
            },
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        run = PaymentCalcRun.query.get(run_id)
        if run is not None:
            run.status = 'failed'
            run.finished_at = datetime.now()
            run.duration_ms = int((time.time() - started) * 1000)
            run.message = str(exc)[:4000]
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()


def maybe_auto_calc(user=None, trigger='auto:ledger_sync'):
    files = _active_files()
    missing = _missing_required_files(files)
    if missing:
        return {'started': False, 'message': '缺少回款计算文件，已跳过自动重算'}
    running = PaymentCalcRun.query.filter_by(status='running').first()
    if running:
        return {'started': False, 'message': '已有计算任务在运行'}
    # 台账同步会先把明细回款比例改回台账 BN 原值，因此不能用“刚算过”做时间去重，
    # 否则同步后可能跳过重算并把已计算值晾成台账值。并发由任务锁和 running 批次拦截。
    return start_payment_calc(user=user, trigger=trigger, background=True)


def _ratio_text(value):
    if value is None:
        return ''
    return '%.2f%%' % (float(value) * 100.0)


def build_payment_report(run_id=None):
    if run_id:
        run = PaymentCalcRun.query.get(run_id)
    else:
        run = PaymentCalcRun.query.filter_by(status='success')\
            .order_by(PaymentCalcRun.id.desc()).first()
    if run is None:
        raise ValueError('没有可下载的计算记录')
    details = PaymentCalcDetail.query.filter_by(run_id=run.id)\
        .order_by(PaymentCalcDetail.ladder_no).all()

    workbook = Workbook()
    summary = workbook.active
    summary.title = '计算汇总'
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='4472C4')
    summary.append(['项目', '值'])
    for cell in summary[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    summary_rows = [
        ('计算批次', run.id),
        ('状态', run.status),
        ('触发方式', run.trigger_source),
        ('操作人', run.operator_name),
        ('开始时间', run.started_at.strftime('%Y-%m-%d %H:%M:%S') if run.started_at else ''),
        ('结束时间', run.finished_at.strftime('%Y-%m-%d %H:%M:%S') if run.finished_at else ''),
        ('目标梯号', run.target_count),
        ('已计算', run.calculated_count),
        ('实际更新', run.changed_count),
        ('保留台账', run.kept_ledger_count),
        ('写 0%', run.zero_count),
        ('无回款记录', run.no_payment_count),
        ('异常', run.error_count),
        ('警告', run.warning_count),
        ('耗时(毫秒)', run.duration_ms),
        ('说明', run.message),
    ]
    for row in summary_rows:
        summary.append(row)
    summary.column_dimensions['A'].width = 18
    summary.column_dimensions['B'].width = 80

    detail_sheet = workbook.create_sheet('梯号明细')
    detail_header = [
        '梯号', '合同号', '台账比例', '计算比例原始值', '页面显示比例',
        '已回款人民币', '待回款人民币', '状态', '说明', '回款币种金额',
    ]
    detail_sheet.append(detail_header)
    for cell in detail_sheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    for detail in details:
        payments = json.loads(detail.payments_json or '{}')
        detail_sheet.append([
            detail.ladder_no,
            detail.contract_no,
            detail.ledger_ratio,
            detail.calculated_ratio,
            detail.calculated_ratio_display,
            detail.paid_rmb,
            detail.pending_rmb,
            detail.status,
            detail.message,
            json.dumps(payments, ensure_ascii=False),
        ])
    for row in detail_sheet.iter_rows(min_row=2):
        for index in (2, 3, 4):
            row[index].number_format = '0.00%'
        for index in (5, 6):
            row[index].number_format = '#,##0.00'
    widths = [20, 18, 12, 16, 14, 16, 16, 24, 36, 40]
    for index, width in enumerate(widths, start=1):
        detail_sheet.column_dimensions[get_column_letter(index)].width = width
    detail_sheet.freeze_panes = 'A2'

    allocation_sheet = workbook.create_sheet('分摊明细')
    allocation_header = [
        '梯号', '合同号', '来源', '年份', '行号', '说明', '币种', '金额', '原始备注',
    ]
    allocation_sheet.append(allocation_header)
    for cell in allocation_sheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    for detail in details:
        try:
            allocations = json.loads(detail.allocations_json or '[]')
        except Exception:
            allocations = []
        for item in allocations:
            allocation_sheet.append([
                item.get('ladder_no') or detail.ladder_no,
                item.get('contract_no') or detail.contract_no,
                item.get('source') or '',
                item.get('year') or '',
                item.get('row_number') or '',
                item.get('note') or '',
                item.get('currency') or '',
                item.get('amount'),
                item.get('remark') or '',
            ])
    for row in allocation_sheet.iter_rows(min_row=2):
        row[7].number_format = '#,##0.00'
    allocation_sheet.freeze_panes = 'A2'
    for index, width in enumerate([20, 18, 10, 8, 8, 24, 10, 14, 40], start=1):
        allocation_sheet.column_dimensions[get_column_letter(index)].width = width

    issue_sheet = workbook.create_sheet('异常清单')
    issue_sheet.append(['类型', '梯号', '合同号', '状态', '说明'])
    for cell in issue_sheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    for detail in details:
        if detail.status not in ('calculated', 'ledger_paid'):
            issue_sheet.append(['梯号', detail.ladder_no, detail.contract_no, detail.status, detail.message])
    stats = run.stats()
    for warning in stats.get('warnings') or []:
        issue_sheet.append(['分摊警告', '', '', '', warning])
    for index, width in enumerate([12, 22, 18, 24, 80], start=1):
        issue_sheet.column_dimensions[get_column_letter(index)].width = width

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output, run
