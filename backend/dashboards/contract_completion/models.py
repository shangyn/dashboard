"""
合同完成情况表 - 数据库模型

4张核心表：
- cc_ledger_contract: 台账合同 + 商贸配件（来自报表a/b）
- cc_country_mapping: 国家→大区/模块/业务员映射
- cc_payment_collection: 回款明细
- cc_annual_target: 年度指标（预种子，不随上传覆盖）
"""
from datetime import datetime
from models import db


class LedgerContract(db.Model):
    """台账合同表 — 每日全量替换"""
    __tablename__ = 'cc_ledger_contract'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    source = db.Column(db.String(20), default='ledger')                 # ledger / report_a / report_b
    contract_no = db.Column(db.String(100), index=True)                  # 合同号
    ladder_no = db.Column(db.String(100))                                 # 梯号
    project_name = db.Column(db.String(300))                              # 项目名称
    currency = db.Column(db.String(20))                                   # 币种
    contract_amount_orig = db.Column(db.Float, default=0.0)              # 合同额（原币）
    unit_count = db.Column(db.Integer, default=0)                         # 台数
    exchange_rate = db.Column(db.Float, default=0.0)                     # 汇率
    contract_amount_rmb = db.Column(db.Float, default=0.0)               # 合同额（人民币），单位：元
    elevator_type = db.Column(db.String(50))                              # 梯种
    elevator_class = db.Column(db.String(50))                             # 电梯类型
    product_type = db.Column(db.String(200))                              # 产品型号
    capacity = db.Column(db.Float, default=0.0)                           # 载重
    speed = db.Column(db.Float, default=0.0)                              # 速度
    floors = db.Column(db.String(100))                                    # 层/站/门
    agent = db.Column(db.String(200))                                     # 代理商
    sign_date = db.Column(db.Date, index=True)                            # 签订日期 (col23)
    schedule_date = db.Column(db.Date, index=True)                        # 排产日期 (col42)
    delivery_date = db.Column(db.Date, index=True)                        # 发货日期 (col51 实际发运日期)
    product_status = db.Column(db.String(50))                             # 产品状态
    salesperson = db.Column(db.String(50))                                # 业务员（台账自带）
    country = db.Column(db.String(100), index=True)                       # 国家（台账自带col55）
    business_region = db.Column(db.String(50))                            # 大区（台账自带col56）
    sub_region = db.Column(db.String(50))                                 # 小区域（台账自带col57）

    # 映射后字段（上传时根据映射表填充，或在查询时动态关联）
    mapped_region = db.Column(db.String(50))                              # 映射后的大区
    mapped_module = db.Column(db.String(100))                             # 映射后的模块
    mapped_manager = db.Column(db.String(50))                             # 映射后的模块经理

    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {c.name: getattr(self, c.name)
                for c in self.__table__.columns
                if c.name not in ('id',)}


class CountryMapping(db.Model):
    """国家-市场-业务员对应表 — 每日全量替换"""
    __tablename__ = 'cc_country_mapping'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    country = db.Column(db.String(100), unique=True, index=True)          # 国家
    module_name = db.Column(db.String(100))                                # 模块
    region = db.Column(db.String(50))                                      # 大区（九大区）
    module_manager = db.Column(db.String(50))                              # 模块经理
    salesperson = db.Column(db.String(50))                                 # 业务负责人
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {c.name: getattr(self, c.name)
                for c in self.__table__.columns
                if c.name not in ('id',)}


class PaymentCollection(db.Model):
    """回款明细表 — 每日全量替换"""
    __tablename__ = 'cc_payment_collection'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_no = db.Column(db.String(100), index=True)                   # 合同编号
    ladder_no = db.Column(db.String(100))                                  # 梯号
    project_name = db.Column(db.String(300))                               # 项目名称
    sign_date = db.Column(db.Date, index=True)                             # 签订日期
    contract_type = db.Column(db.String(50))                               # 合同类型
    product_status = db.Column(db.String(50))                              # 产品状态
    region = db.Column(db.String(50))                                      # 大区（回款表自带）
    sub_region = db.Column(db.String(50))                                  # 小区域
    node_type = db.Column(db.String(50))                                   # 节点类型（预付款/发货前/发货后/质保金）
    payment_method = db.Column(db.String(50))                              # 付款方式
    payment_amount_orig = db.Column(db.Float, default=0.0)                # 回款额(原币)
    product_model = db.Column(db.String(100))                              # 型号
    agent_name = db.Column(db.String(200))                                 # 代理商
    payment_amount_rmb = db.Column(db.Float, default=0.0)                 # 回款额(人民币)
    payment_date = db.Column(db.Date, index=True)                          # 回款日期
    currency = db.Column(db.String(20))                                    # 币种
    remark = db.Column(db.String(500))                                     # 备注
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {c.name: getattr(self, c.name)
                for c in self.__table__.columns
                if c.name not in ('id',)}


class TradeModuleData(db.Model):
    """商贸模块汇总数据 — 从商贸数据.xlsx上传（全量替换当前年份）"""
    __tablename__ = 'cc_trade_module_data'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    data_year = db.Column(db.Integer, index=True, default=2026)           # 数据年份
    module_name = db.Column(db.String(50))                                 # 模块名（商贸1/商贸2/商贸3）
    sign_amount = db.Column(db.Float, default=0.0)                        # 签订额（元）
    payment_amount = db.Column(db.Float, default=0.0)                     # 回款额（元）
    schedule_amount = db.Column(db.Float, default=0.0)                    # 排产额（元）
    ship_amount = db.Column(db.Float, default=0.0)                        # 发货额（元）
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {c.name: getattr(self, c.name)
                for c in self.__table__.columns
                if c.name not in ('id',)}


class OverseasDiff(db.Model):
    """海外差值数据 — 从海外差值.xlsx上传（全量替换当前年份）

    每行 = 一个模块的一年海外差额数据
    单位：万元（与前端展示单位一致）
    """
    __tablename__ = 'cc_overseas_diff'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    data_year = db.Column(db.Integer, index=True, default=2026)           # 数据年份
    module_name = db.Column(db.String(100), index=True)                    # 模块名
    sign_diff = db.Column(db.Float, nullable=True)                         # 签订海外差额（万元）
    schedule_diff = db.Column(db.Float, nullable=True)                     # 排产海外差额（万元）
    ship_diff = db.Column(db.Float, nullable=True)                         # 发货海外差额（万元）
    payment_diff = db.Column(db.Float, nullable=True)                      # 回款海外差额（万元）
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {c.name: getattr(self, c.name)
                for c in self.__table__.columns
                if c.name not in ('id',)}


class ScheduleTracking(db.Model):
    """工期统计表 — 上传全量替换"""
    __tablename__ = 'cc_schedule_tracking'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_no = db.Column(db.String(100), index=True)
    elevator_no = db.Column(db.String(100))
    project_name = db.Column(db.String(200))
    elevator_type = db.Column(db.String(50))
    elevator_model = db.Column(db.String(100))
    quantity = db.Column(db.Integer, default=0)
    person = db.Column(db.String(50))
    order_end_date = db.Column(db.Date)
    design_done_date = db.Column(db.Date)
    mech_warehouse_date = db.Column(db.Date)
    mech_warehouse_raw = db.Column(db.String(100))
    mech_delay_days = db.Column(db.Integer)
    elec_warehouse_date = db.Column(db.Date)
    elec_warehouse_raw = db.Column(db.String(100))
    elec_delay_days = db.Column(db.Integer)
    audit_done_date = db.Column(db.Date)
    designer_mech = db.Column(db.String(50))
    designer_elec = db.Column(db.String(50))
    design_cycle = db.Column(db.Integer)
    production_cycle = db.Column(db.Integer)
    total_cycle = db.Column(db.Integer)
    is_rejected = db.Column(db.Boolean, default=False)
    reject_node = db.Column(db.String(100))
    reject_reason = db.Column(db.String(200))
    scheduled_finish = db.Column(db.Date)
    delivery_finish = db.Column(db.Date)
    remark = db.Column(db.String(500))
    mapped_region = db.Column(db.String(100))
    mapped_module = db.Column(db.String(100))
    stage = db.Column(db.String(30))
    category = db.Column(db.String(30))
    l_class = db.Column(db.String(20))
    n_class = db.Column(db.String(20))
    data_date = db.Column(db.Date)   # 数据统计日期（来自上传文件名）
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {c.name: getattr(self, c.name)
                for c in self.__table__.columns
                if c.name not in ('id',)}


class AnnualTarget(db.Model):
    """年度指标表 — 预种子，不随上传覆盖"""
    __tablename__ = 'cc_annual_target'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    target_year = db.Column(db.Integer, index=True, default=2026)         # 目标年份
    region = db.Column(db.String(50), index=True)                          # 大区
    module_name = db.Column(db.String(100), default='')                    # 模块名（空=大区级指标）
    metric_key = db.Column(db.String(50))                                  # 指标标识
    target_value = db.Column(db.Float, default=0.0)                       # 指标值
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 指标标识常量
    METRIC_SIGN_UNITS = 'sign_units'
    METRIC_SIGN_AMOUNT = 'sign_amount'
    METRIC_PAYMENT_AMOUNT = 'payment_amount'
    METRIC_SHIP_UNITS = 'ship_units'
    METRIC_SHIP_AMOUNT = 'ship_amount'
    METRIC_SCHEDULE_UNITS = 'schedule_units'
    METRIC_SCHEDULE_AMOUNT = 'schedule_amount'

    @classmethod
    def all_metrics(cls):
        return [cls.METRIC_SIGN_UNITS, cls.METRIC_SIGN_AMOUNT,
                cls.METRIC_PAYMENT_AMOUNT,
                cls.METRIC_SHIP_UNITS, cls.METRIC_SHIP_AMOUNT,
                cls.METRIC_SCHEDULE_UNITS, cls.METRIC_SCHEDULE_AMOUNT]

    def to_dict(self):
        return {c.name: getattr(self, c.name)
                for c in self.__table__.columns
                if c.name not in ('id',)}
