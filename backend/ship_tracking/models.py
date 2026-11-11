"""
发货梯号追踪 - 数据模型

所有表统一使用 st_ 前缀，与既有 cc_ / mf_ 表完全隔离。
本模块只新增表，不修改既有表结构或历史数据。
"""
from datetime import datetime
import json

from models import db


class ImportBatch(db.Model):
    """一次 Excel 导入批次。预览和正式提交均留痕。"""
    __tablename__ = 'st_import_batch'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    data_type = db.Column(db.String(20), index=True, nullable=False)   # plan / plan_forecast / booking
    plan_month = db.Column(db.String(7), index=True, default='')
    version = db.Column(db.Integer, default=0)
    filename = db.Column(db.String(300), default='')
    file_hash = db.Column(db.String(64), index=True, default='')
    status = db.Column(db.String(20), index=True, default='preview')  # preview / committed / superseded / failed
    row_count = db.Column(db.Integer, default=0)
    unique_count = db.Column(db.Integer, default=0)
    total_units = db.Column(db.Float, default=0.0)
    duplicate_count = db.Column(db.Integer, default=0)
    warning_count = db.Column(db.Integer, default=0)
    error_count = db.Column(db.Integer, default=0)
    summary_json = db.Column(db.Text, default='{}')
    payload_json = db.Column(db.Text, default='[]')
    previous_batch_id = db.Column(db.Integer, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    created_by_name = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.now)
    committed_by = db.Column(db.Integer, nullable=True)
    committed_by_name = db.Column(db.String(50), default='')
    committed_at = db.Column(db.DateTime, nullable=True)

    def summary(self):
        try:
            return json.loads(self.summary_json or '{}')
        except Exception:
            return {}

    def to_dict(self):
        return {
            'id': self.id,
            'data_type': self.data_type,
            'plan_month': self.plan_month or '',
            'version': self.version or 0,
            'filename': self.filename or '',
            'file_hash': self.file_hash or '',
            'status': self.status or '',
            'row_count': self.row_count or 0,
            'unique_count': self.unique_count or 0,
            'total_units': self.total_units or 0,
            'duplicate_count': self.duplicate_count or 0,
            'warning_count': self.warning_count or 0,
            'error_count': self.error_count or 0,
            'summary': self.summary(),
            'previous_batch_id': self.previous_batch_id,
            'created_by_name': self.created_by_name or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'committed_by_name': self.committed_by_name or '',
            'committed_at': self.committed_at.strftime('%Y-%m-%d %H:%M:%S') if self.committed_at else '',
        }


class ImportIssue(db.Model):
    """导入行级异常/警告，预览和提交都可查询。"""
    __tablename__ = 'st_import_issue'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_id = db.Column(db.Integer, index=True, nullable=False)
    row_number = db.Column(db.Integer, nullable=True)
    severity = db.Column(db.String(20), default='warning')  # info / warning / error
    code = db.Column(db.String(50), default='')
    message = db.Column(db.Text, default='')
    raw_json = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'row_number': self.row_number,
            'severity': self.severity or 'warning',
            'code': self.code or '',
            'message': self.message or '',
            'raw': _loads(self.raw_json),
        }


class PlanItem(db.Model):
    """月度计划快照。每个版本、每个梯号一行，历史版本永久保留。"""
    __tablename__ = 'st_plan_item'
    __table_args__ = (
        db.UniqueConstraint('plan_month', 'plan_version', 'ladder_key', name='uq_st_plan_version_ladder'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_id = db.Column(db.Integer, index=True, nullable=False)
    plan_month = db.Column(db.String(7), index=True, nullable=False)
    plan_version = db.Column(db.Integer, index=True, nullable=False)
    ladder_key = db.Column(db.String(150), index=True, nullable=False)
    contract_no = db.Column(db.String(100), default='')
    ladder_no = db.Column(db.String(150), default='')
    module_name = db.Column(db.String(100), index=True, default='')
    project_name = db.Column(db.String(300), default='')
    business_region = db.Column(db.String(100), default='')
    salesperson = db.Column(db.String(50), default='')
    unit_count = db.Column(db.Float, default=1.0)
    amount_rmb = db.Column(db.Float, default=0.0)
    source = db.Column(db.String(100), default='')
    reporter = db.Column(db.String(50), default='')
    schedule_finish_date = db.Column(db.Date, nullable=True)
    whole_ship_date = db.Column(db.Date, nullable=True)
    original_expected_ship_date = db.Column(db.Date, nullable=True)
    business_expected_raw = db.Column(db.String(100), default='')
    remark = db.Column(db.Text, default='')
    validation_status = db.Column(db.String(20), default='ok')  # ok / warning / error
    data_flags = db.Column(db.Text, default='[]')
    raw_json = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def flags(self):
        return _loads(self.data_flags, [])


class TrackingItem(db.Model):
    """一个梯号一条当前追踪主记录。实际发货和订舱状态独立保存，重导计划不删除事实数据。"""
    __tablename__ = 'st_tracking_item'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ladder_key = db.Column(db.String(150), unique=True, index=True, nullable=False)
    plan_month = db.Column(db.String(7), index=True, default='')
    plan_version = db.Column(db.Integer, default=0)
    plan_batch_id = db.Column(db.Integer, nullable=True)
    plan_status = db.Column(db.String(20), index=True, default='active')  # active / removed
    contract_no = db.Column(db.String(100), index=True, default='')
    ladder_no = db.Column(db.String(150), default='')
    module_name = db.Column(db.String(100), index=True, default='')
    project_name = db.Column(db.String(300), default='')
    business_region = db.Column(db.String(100), default='')
    salesperson = db.Column(db.String(50), default='')
    unit_count = db.Column(db.Float, default=1.0)
    amount_rmb = db.Column(db.Float, default=0.0)
    payment_ratio = db.Column(db.Float, nullable=True)  # 台账 BN 列回款比例原始值
    source = db.Column(db.String(100), default='')
    reporter = db.Column(db.String(50), default='')
    business_expected_raw = db.Column(db.String(100), default='')
    schedule_finish_date = db.Column(db.Date, nullable=True)
    whole_ship_date = db.Column(db.Date, nullable=True)

    original_expected_ship_date = db.Column(db.Date, nullable=True)
    expected_ship_date = db.Column(db.Date, index=True, nullable=True)
    draft_expected_ship_date = db.Column(db.Date, nullable=True)
    draft_week_start = db.Column(db.Date, nullable=True)
    committed_expected_ship_date = db.Column(db.Date, nullable=True)
    committed_week_start = db.Column(db.Date, index=True, nullable=True)
    committed_on_week_start = db.Column(db.Date, nullable=True)
    commit_status = db.Column(db.String(20), index=True, default='unplanned')  # unplanned / committed / withdrawn
    committed_at = db.Column(db.DateTime, nullable=True)
    committed_by = db.Column(db.Integer, nullable=True)
    committed_by_name = db.Column(db.String(50), default='')
    plan_change_count = db.Column(db.Integer, default=0)
    plan_removed_at = db.Column(db.DateTime, nullable=True)

    actual_ship_date = db.Column(db.Date, index=True, nullable=True)
    actual_ship_source = db.Column(db.String(20), nullable=True)
    loan_status = db.Column(db.String(30), default='')  # reserved for later
    booking_status = db.Column(db.String(20), index=True, default='未订舱')
    booking_audit_status = db.Column(db.String(20), default='')
    booking_record_count = db.Column(db.Integer, default=0)
    booking_last_date = db.Column(db.Date, nullable=True)

    source_kind = db.Column(db.String(30), default='plan')  # plan / actual_only / manual
    data_flags = db.Column(db.Text, default='[]')
    business_remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def flags(self):
        return _loads(self.data_flags, [])

    def set_flags(self, values):
        self.data_flags = json.dumps(sorted(set(values or [])), ensure_ascii=False)


class DailyShipment(db.Model):
    """每日实发记录。一个梯号只允许一条有效实发；作废记录保留审计痕迹。"""
    __tablename__ = 'st_daily_shipment'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ladder_key = db.Column(db.String(150), index=True, nullable=False)
    ship_date = db.Column(db.Date, index=True, nullable=False)
    unit_count = db.Column(db.Float, default=1.0)
    operator_id = db.Column(db.Integer, nullable=True)
    operator_name = db.Column(db.String(50), default='')
    source = db.Column(db.String(30), default='daily')
    remark = db.Column(db.Text, default='')
    reason = db.Column(db.Text, default='')
    is_void = db.Column(db.Boolean, default=False, index=True)
    void_reason = db.Column(db.Text, default='')
    void_by = db.Column(db.Integer, nullable=True)
    void_by_name = db.Column(db.String(50), default='')
    void_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class BookingRecord(db.Model):
    """订舱报表行快照。只把当前批次作为匹配依据，历史批次保留。"""
    __tablename__ = 'st_booking_record'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_id = db.Column(db.Integer, index=True, nullable=False)
    ladder_key = db.Column(db.String(150), index=True, default='')
    document_no = db.Column(db.String(100), default='')
    audit_status = db.Column(db.String(30), index=True, default='')
    current_node = db.Column(db.String(100), default='')
    application_date = db.Column(db.Date, nullable=True)
    contract_no = db.Column(db.String(100), default='')
    ladder_raw = db.Column(db.String(200), default='')
    full_ladder_no = db.Column(db.String(150), default='')
    elevator_type = db.Column(db.String(100), default='')
    price_term = db.Column(db.String(100), default='')
    is_current = db.Column(db.Boolean, default=True, index=True)
    raw_json = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=datetime.now)


class AuditLog(db.Model):
    """模块内统一操作流水，记录谁在何时因何原因改了什么。"""
    __tablename__ = 'st_audit_log'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category = db.Column(db.String(30), index=True, default='')
    action = db.Column(db.String(50), index=True, default='')
    ladder_key = db.Column(db.String(150), index=True, default='')
    batch_id = db.Column(db.Integer, nullable=True)
    operator_id = db.Column(db.Integer, nullable=True)
    operator_name = db.Column(db.String(50), default='')
    reason = db.Column(db.Text, default='')
    old_values = db.Column(db.Text, default='{}')
    new_values = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'category': self.category or '',
            'action': self.action or '',
            'ladder_key': self.ladder_key or '',
            'batch_id': self.batch_id,
            'operator_name': self.operator_name or '',
            'reason': self.reason or '',
            'old_values': _loads(self.old_values),
            'new_values': _loads(self.new_values),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


def _loads(value, default=None):
    if default is None:
        default = {}
    try:
        if value is None or value == '':
            return default
        return json.loads(value)
    except Exception:
        return default

class PaymentFile(db.Model):
    """回款计算源文件。每次上传新增一行，同一类型只保留一个 active。"""
    __tablename__ = 'st_payment_file'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    file_type = db.Column(db.String(20), index=True, nullable=False)  # table_b / table_e / table_r / exchange_rate
    filename = db.Column(db.String(300), default='')
    stored_path = db.Column(db.String(500), default='')
    file_size = db.Column(db.Integer, default=0)
    file_hash = db.Column(db.String(64), index=True, default='')
    is_active = db.Column(db.Boolean, default=True, index=True)
    status = db.Column(db.String(20), default='stored')  # stored / validated / error
    message = db.Column(db.Text, default='')
    uploaded_by = db.Column(db.Integer, nullable=True)
    uploaded_by_name = db.Column(db.String(50), default='')
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'file_type': self.file_type or '',
            'filename': self.filename or '',
            'stored_path': self.stored_path or '',
            'file_size': self.file_size or 0,
            'file_hash': self.file_hash or '',
            'is_active': bool(self.is_active),
            'status': self.status or '',
            'message': self.message or '',
            'uploaded_by': self.uploaded_by,
            'uploaded_by_name': self.uploaded_by_name or '',
            'uploaded_at': self.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if self.uploaded_at else '',
        }


class PaymentCalcRun(db.Model):
    """一次回款比例计算批次。"""
    __tablename__ = 'st_payment_calc_run'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    status = db.Column(db.String(20), index=True, default='running')  # running / success / failed / skipped
    trigger_source = db.Column(db.String(50), default='manual')
    operator_id = db.Column(db.Integer, nullable=True)
    operator_name = db.Column(db.String(50), default='')
    started_at = db.Column(db.DateTime, default=datetime.now)
    finished_at = db.Column(db.DateTime, nullable=True)
    target_count = db.Column(db.Integer, default=0)
    calculated_count = db.Column(db.Integer, default=0)
    changed_count = db.Column(db.Integer, default=0)
    kept_ledger_count = db.Column(db.Integer, default=0)
    zero_count = db.Column(db.Integer, default=0)
    missing_ledger_count = db.Column(db.Integer, default=0)
    no_payment_count = db.Column(db.Integer, default=0)
    error_count = db.Column(db.Integer, default=0)
    warning_count = db.Column(db.Integer, default=0)
    duration_ms = db.Column(db.Integer, default=0)
    message = db.Column(db.Text, default='')
    stats_json = db.Column(db.Text, default='{}')

    def stats(self):
        return _loads(self.stats_json, {})

    def to_dict(self):
        return {
            'id': self.id,
            'status': self.status or '',
            'trigger_source': self.trigger_source or '',
            'operator_id': self.operator_id,
            'operator_name': self.operator_name or '',
            'started_at': self.started_at.strftime('%Y-%m-%d %H:%M:%S') if self.started_at else '',
            'finished_at': self.finished_at.strftime('%Y-%m-%d %H:%M:%S') if self.finished_at else '',
            'target_count': self.target_count or 0,
            'calculated_count': self.calculated_count or 0,
            'changed_count': self.changed_count or 0,
            'kept_ledger_count': self.kept_ledger_count or 0,
            'zero_count': self.zero_count or 0,
            'missing_ledger_count': self.missing_ledger_count or 0,
            'no_payment_count': self.no_payment_count or 0,
            'error_count': self.error_count or 0,
            'warning_count': self.warning_count or 0,
            'duration_ms': self.duration_ms or 0,
            'message': self.message or '',
            'stats': self.stats(),
        }


class PaymentCalcDetail(db.Model):
    """一次计算中每个梯号的落库结果与分摊留痕。"""
    __tablename__ = 'st_payment_calc_detail'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    run_id = db.Column(db.Integer, index=True, nullable=False)
    ladder_key = db.Column(db.String(150), index=True, default='')
    contract_no = db.Column(db.String(100), index=True, default='')
    ladder_no = db.Column(db.String(150), default='')
    ledger_ratio = db.Column(db.Float, nullable=True)
    calculated_ratio = db.Column(db.Float, nullable=True)
    calculated_ratio_display = db.Column(db.Float, nullable=True)
    paid_rmb = db.Column(db.Float, default=0.0)
    pending_rmb = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(40), index=True, default='')
    message = db.Column(db.Text, default='')
    payments_json = db.Column(db.Text, default='{}')
    allocations_json = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'run_id': self.run_id,
            'ladder_key': self.ladder_key or '',
            'contract_no': self.contract_no or '',
            'ladder_no': self.ladder_no or '',
            'ledger_ratio': self.ledger_ratio,
            'calculated_ratio': self.calculated_ratio,
            'calculated_ratio_display': self.calculated_ratio_display,
            'paid_rmb': self.paid_rmb or 0.0,
            'pending_rmb': self.pending_rmb or 0.0,
            'status': self.status or '',
            'message': self.message or '',
            'payments': _loads(self.payments_json, {}),
            'allocations': _loads(self.allocations_json, []),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }
