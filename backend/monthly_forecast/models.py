"""
单月签排发填报 — 数据模型

独立模块，表名统一 mf_ 前缀，与既有 cc_* 表完全隔离。
4 张表：
- mf_monthly_input   : 模块月度填报（签单 + 排产，手填）
- mf_ship_selection  : 发货勾选明细（候选勾选 / 手工输入梯号）
- mf_submission      : 提交留存快照（版本可追溯）
- mf_user_scope      : 用户 → 模块 名单
"""
from datetime import datetime

from models import db


class MonthlyInput(db.Model):
    """模块月度填报 — 签单 / 排产台数金额（手填）"""
    __tablename__ = 'mf_monthly_input'
    __table_args__ = (
        db.UniqueConstraint('data_month', 'module_name', name='uq_mf_input'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    data_month = db.Column(db.String(7), index=True, nullable=False)        # YYYY-MM
    module_name = db.Column(db.String(100), index=True, nullable=False)     # 模块名
    sign_units = db.Column(db.Float, default=0.0)                           # 签单台数
    sign_amount = db.Column(db.Float, default=0.0)                          # 签单金额（万元）
    prod_units = db.Column(db.Float, default=0.0)                           # 排产台数
    prod_amount = db.Column(db.Float, default=0.0)                          # 排产金额（万元）
    ship_manual_units = db.Column(db.Float, default=0.0)                    # 无梯号发货预估：台数（手填）
    ship_manual_amount = db.Column(db.Float, default=0.0)                   # 无梯号发货预估：金额（万元，手填）
    status = db.Column(db.String(20), default='draft')                      # draft / submitted
    submitted_at = db.Column(db.DateTime, nullable=True)
    updated_by = db.Column(db.Integer, nullable=True)                       # user.id（不建外键，避免耦合既有表）
    updated_by_name = db.Column(db.String(50), default='')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'data_month': self.data_month,
            'module_name': self.module_name,
            'sign_units': self.sign_units or 0.0,
            'sign_amount': self.sign_amount or 0.0,
            'prod_units': self.prod_units or 0.0,
            'prod_amount': self.prod_amount or 0.0,
            'ship_manual_units': self.ship_manual_units or 0.0,
            'ship_manual_amount': self.ship_manual_amount or 0.0,
            'status': self.status or 'draft',
            'submitted_at': self.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if self.submitted_at else '',
            'updated_by_name': self.updated_by_name or '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else '',
        }


class ShipSelection(db.Model):
    """发货勾选明细 — 候选池勾选 or 手工输入梯号"""
    __tablename__ = 'mf_ship_selection'
    __table_args__ = (
        db.UniqueConstraint('data_month', 'module_name', 'ladder_no', name='uq_mf_ship'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    data_month = db.Column(db.String(7), index=True, nullable=False)
    module_name = db.Column(db.String(100), index=True, nullable=False)
    contract_no = db.Column(db.String(100), default='')
    ladder_no = db.Column(db.String(100), default='')
    unit_count = db.Column(db.Float, default=0.0)                           # 快照：台数
    amount_rmb = db.Column(db.Float, default=0.0)                           # 快照：合同额（人民币，元）
    is_manual = db.Column(db.Boolean, default=False)                        # True = 手工输入梯号
    created_by = db.Column(db.Integer, nullable=True)
    created_by_name = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'contract_no': self.contract_no or '',
            'ladder_no': self.ladder_no or '',
            'unit_count': self.unit_count or 0.0,
            'amount_wan': round((self.amount_rmb or 0.0) / 10000.0, 2),
            'is_manual': bool(self.is_manual),
            'created_by_name': self.created_by_name or '',
        }


class Submission(db.Model):
    """提交留存快照 — 每次提交生成一个新版本，历史不可覆盖"""
    __tablename__ = 'mf_submission'
    __table_args__ = (
        db.UniqueConstraint('data_month', 'module_name', 'version', name='uq_mf_sub'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    data_month = db.Column(db.String(7), index=True, nullable=False)
    module_name = db.Column(db.String(100), index=True, nullable=False)
    version = db.Column(db.Integer, default=1)
    payload = db.Column(db.Text, default='')                                # JSON：签排产 4 值 + 发货明细数组
    sign_units = db.Column(db.Float, default=0.0)
    sign_amount = db.Column(db.Float, default=0.0)
    prod_units = db.Column(db.Float, default=0.0)
    prod_amount = db.Column(db.Float, default=0.0)
    ship_units = db.Column(db.Float, default=0.0)
    ship_amount = db.Column(db.Float, default=0.0)
    submitted_by = db.Column(db.Integer, nullable=True)
    submitted_by_name = db.Column(db.String(50), default='')
    submitted_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'data_month': self.data_month,
            'module_name': self.module_name,
            'version': self.version,
            'sign_units': self.sign_units or 0.0,
            'sign_amount': self.sign_amount or 0.0,
            'prod_units': self.prod_units or 0.0,
            'prod_amount': self.prod_amount or 0.0,
            'ship_units': self.ship_units or 0.0,
            'ship_amount': self.ship_amount or 0.0,
            'submitted_by_name': self.submitted_by_name or '',
            'submitted_at': self.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if self.submitted_at else '',
        }


class UserScope(db.Model):
    """用户 → 模块 名单（名单导入只写本表，绝不修改 user 表）"""
    __tablename__ = 'mf_user_scope'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'module_name', name='uq_mf_scope'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, index=True, nullable=True)              # 匹配到的 user.id，未匹配为 NULL
    match_key = db.Column(db.String(50), default='')                        # 名单原文（工号或姓名）
    module_name = db.Column(db.String(100), index=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'match_key': self.match_key or '',
            'module_name': self.module_name,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }
