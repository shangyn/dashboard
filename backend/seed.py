import json
from flask_bcrypt import Bcrypt
from models import db, Role, User
from dashboards.contract_completion.models import (
    LedgerContract, CountryMapping, PaymentCollection, AnnualTarget,
    ScheduleTracking, ShipmentData
)

bcrypt = Bcrypt()


def seed_database(app):
    """首次运行时自动创建管理员账号和角色"""
    with app.app_context():
        db.create_all()

        # 兼容性迁移
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        with db.engine.connect() as conn:
            # upload_config: 加 parent_id
            uc_cols = [c['name'] for c in inspector.get_columns('upload_config')]
            if 'parent_id' not in uc_cols:
                conn.execute(text('ALTER TABLE upload_config ADD COLUMN parent_id INTEGER REFERENCES upload_config(id)'))
            if 'handler_script' not in uc_cols:
                conn.execute(text("ALTER TABLE upload_config ADD COLUMN handler_script VARCHAR(200) DEFAULT ''"))
            if 'dashboard_module_id' not in uc_cols:
                conn.execute(text("ALTER TABLE upload_config ADD COLUMN dashboard_module_id INTEGER REFERENCES module(id)"))
            if 'script_dir' not in uc_cols:
                conn.execute(text("ALTER TABLE upload_config ADD COLUMN script_dir VARCHAR(300) DEFAULT 'dashboards/generate_dashboard'"))
            # file_upload: 加 ip_address
            fu_cols = [c['name'] for c in inspector.get_columns('file_upload')]
            if 'ip_address' not in fu_cols:
                conn.execute(text("ALTER TABLE file_upload ADD COLUMN ip_address VARCHAR(50) DEFAULT ''"))
            # cc_schedule_tracking: 加 mech_warehouse_raw / elec_warehouse_raw
            st_cols = [c['name'] for c in inspector.get_columns('cc_schedule_tracking')]
            if 'mech_warehouse_raw' not in st_cols:
                conn.execute(text("ALTER TABLE cc_schedule_tracking ADD COLUMN mech_warehouse_raw VARCHAR(100)"))
            if 'elec_warehouse_raw' not in st_cols:
                conn.execute(text("ALTER TABLE cc_schedule_tracking ADD COLUMN elec_warehouse_raw VARCHAR(100)"))
            if 'data_date' not in st_cols:
                conn.execute(text("ALTER TABLE cc_schedule_tracking ADD COLUMN data_date DATE"))
            # cc_ledger_contract: 加 personal_module / personal_region（报表a个人业绩归属）
            lc_cols = [c['name'] for c in inspector.get_columns('cc_ledger_contract')]
            if 'personal_module' not in lc_cols:
                conn.execute(text("ALTER TABLE cc_ledger_contract ADD COLUMN personal_module VARCHAR(100)"))
            if 'personal_region' not in lc_cols:
                conn.execute(text("ALTER TABLE cc_ledger_contract ADD COLUMN personal_region VARCHAR(50)"))
            if 'whole_ship_date' not in lc_cols:
                conn.execute(text("ALTER TABLE cc_ledger_contract ADD COLUMN whole_ship_date DATE"))
            if 'schedule_finish_date' not in lc_cols:
                conn.execute(text("ALTER TABLE cc_ledger_contract ADD COLUMN schedule_finish_date DATE"))
            # mf_monthly_input: 加 ship_manual_units / ship_manual_amount（无梯号发货预估）
            mf_cols = [c['name'] for c in inspector.get_columns('mf_monthly_input')]
            if 'ship_manual_units' not in mf_cols:
                conn.execute(text('ALTER TABLE mf_monthly_input ADD COLUMN ship_manual_units FLOAT DEFAULT 0'))
            if 'ship_manual_amount' not in mf_cols:
                conn.execute(text('ALTER TABLE mf_monthly_input ADD COLUMN ship_manual_amount FLOAT DEFAULT 0'))
            if 'payment_amount' not in mf_cols:
                conn.execute(text('ALTER TABLE mf_monthly_input ADD COLUMN payment_amount FLOAT DEFAULT 0'))
            if 'commission_amount' not in mf_cols:
                conn.execute(text('ALTER TABLE mf_monthly_input ADD COLUMN commission_amount FLOAT DEFAULT 0'))
            if 'install_amount' not in mf_cols:
                conn.execute(text('ALTER TABLE mf_monthly_input ADD COLUMN install_amount FLOAT DEFAULT 0'))
            if 'travel_amount' not in mf_cols:
                conn.execute(text('ALTER TABLE mf_monthly_input ADD COLUMN travel_amount FLOAT DEFAULT 0'))
            if 'other_expense_amount' not in mf_cols:
                conn.execute(text('ALTER TABLE mf_monthly_input ADD COLUMN other_expense_amount FLOAT DEFAULT 0'))
            conn.commit()

        # 数据架构迁移：停用重复的上传配置，新增预算上传入口
        _migrate_upload_configs()

        # 种子年度指标 — 每次启动都检查（独立于角色初始化）
        _seed_annual_targets()

        if Role.query.count() > 0:
            return  # 已初始化，跳过

        # 创建管理员角色
        admin_permissions = [
            'dashboard',
            'user_manage', 'role_manage', 'module_manage', 'upload_manage',
            'dashboard_receivables', 'dashboard_performance',
            'dashboard_daily', 'dashboard_ledger',
            'dashboard_function', 'dashboard_spare_parts',
            'upload_performance', 'upload_module_target',
            'upload_payment', 'upload_spare_parts',
            'upload_trade', 'upload_delivery', 'upload_offline_quote',
            'dashboard_schedule', 'upload_schedule',
            'dashboard_contract_completion', 'upload_contract_completion',
            'upload_contract_ledger', 'upload_contract_mapping',
            'upload_contract_payment', 'upload_contract_report_a',
            'upload_contract_report_b',
            'upload_contract_trade_data',
            'upload_contract_trade_data_2025',
            'upload_contract_overseas_diff',
        ]

        admin_role = Role(
            role_name='管理员',
            is_admin=True,
        )
        admin_role.set_permissions(admin_permissions)
        db.session.add(admin_role)
        db.session.flush()

        # 创建管理员用户
        admin_user = User(
            username='admin',
            password=bcrypt.generate_password_hash('admin123').decode('utf-8'),
            real_name='管理员',
            role_id=admin_role.id,
            is_active=True,
        )
        db.session.add(admin_user)
        db.session.commit()
        print('[Seed] 管理员账号已创建: admin / admin123')


def _seed_annual_targets():
    """同步合同完成情况表的年度指标（2026-09-30 大区重构：2 大区 + 模块级指标）

    数据来源: dashboards/contract_completion/constants.py 的 ANNUAL_TARGETS
    （由 数据源/模块任务划分9.30.xlsx 生成）。
    表内 2026 年数据与当前大区/模块口径不一致时整体重建，保证「指标」列与任务表一致。
    写入两类行：
      模块级 (region, module_name=模块)  → 模块明细、年度完成比
      大区级 (region, module_name='')    → 大区汇总
    """
    from dashboards.contract_completion.constants import (
        REGION_ORDER, ANNUAL_TARGETS, ANNUAL_TARGET_METRIC_KEYS,
    )

    expected = {(region, '') for region in REGION_ORDER}
    expected |= {(region, module) for (region, module) in ANNUAL_TARGETS}

    existing = AnnualTarget.query.filter_by(target_year=2026).all()
    if {(t.region, t.module_name or '') for t in existing} == expected:
        return  # 已是当前口径，无需重建

    AnnualTarget.query.filter_by(target_year=2026).delete()
    db.session.flush()

    # 模块级指标
    for (region, module), targets in ANNUAL_TARGETS.items():
        for field, metric_key in ANNUAL_TARGET_METRIC_KEYS.items():
            db.session.add(AnnualTarget(
                target_year=2026, region=region, module_name=module,
                metric_key=metric_key, target_value=targets.get(field, 0) or 0,
            ))

    # 大区级指标 = 该大区各模块求和
    for region in REGION_ORDER:
        sums = {metric_key: 0 for metric_key in ANNUAL_TARGET_METRIC_KEYS.values()}
        for (r, _module), targets in ANNUAL_TARGETS.items():
            if r != region:
                continue
            for field, metric_key in ANNUAL_TARGET_METRIC_KEYS.items():
                sums[metric_key] += targets.get(field, 0) or 0
        for metric_key, total in sums.items():
            db.session.add(AnnualTarget(
                target_year=2026, region=region, module_name='',
                metric_key=metric_key, target_value=round(total, 2),
            ))

    db.session.commit()
    print('[Seed] 年度指标已按新口径重建: %d 大区 × %d 大区级 + %d 模块级 = %d 条'
          % (len(REGION_ORDER), len(ANNUAL_TARGET_METRIC_KEYS),
             len(ANNUAL_TARGETS), len(expected) * len(ANNUAL_TARGET_METRIC_KEYS)))


def _migrate_upload_configs():
    """数据架构迁移：停用重复上传配置，新增预算上传入口"""
    from models import UploadConfig

    # 1. 停用 generate_data A/B/C/D（台账/报表a/报表b/映射表 不再需要重复上传）
    deprecated_codes = ['generate_data_A', 'generate_data_B', 'generate_data_C', 'generate_data_D']
    for code in deprecated_codes:
        cfg = UploadConfig.query.filter_by(code=code).first()
        if cfg and cfg.is_active:
            cfg.is_active = False
            print(f'[Seed] 已停用上传配置: {code}')

    # 2. 停用 schedule_dashboard 下的 mapping_data
    schedule_mapping = UploadConfig.query.filter_by(code='mapping_data').first()
    if schedule_mapping and schedule_mapping.is_active:
        # 确认它是 schedule_dashboard 的子项
        parent = schedule_mapping.parent
        if parent and parent.code == 'schedule_dashboard':
            schedule_mapping.is_active = False
            print(f'[Seed] 已停用上传配置: mapping_data (schedule_dashboard)')

    # 3. 新增 generate_data_budget（月度预算，只存文件不解析）
    generate_data_parent = UploadConfig.query.filter_by(code='generate_data').first()
    if generate_data_parent:
        existing = UploadConfig.query.filter_by(code='generate_data_budget').first()
        if not existing:
            budget = UploadConfig(
                parent_id=generate_data_parent.id,
                code='generate_data_budget',
                name='月度预算表',
                permission=generate_data_parent.permission,
                is_active=True,
                sort_order=50,
            )
            db.session.add(budget)
            print(f'[Seed] 已新增上传配置: generate_data_budget (月度预算表)')

    # 4. 新增 contract_shipment_2025（2025发货额）
    cc_parent = UploadConfig.query.filter_by(code='contract_completion').first()
    if cc_parent and not UploadConfig.query.filter_by(code='contract_shipment_2025').first():
        shipment = UploadConfig(
            parent_id=cc_parent.id,
            code='contract_shipment_2025',
            name='发货额(2025)',
            permission=cc_parent.permission,
            file_types='.xlsx,.xls',
            is_active=True,
            sort_order=60,
        )
        db.session.add(shipment)
        print('[Seed] 已新增上传配置: contract_shipment_2025 (发货额2025)')

    db.session.commit()
