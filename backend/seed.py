import json
from flask_bcrypt import Bcrypt
from models import db, Role, User
from dashboards.contract_completion.models import (
    LedgerContract, CountryMapping, PaymentCollection, AnnualTarget,
    ScheduleTracking
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
    """种子合同完成情况表的年度指标数据"""
    if AnnualTarget.query.first() is not None:
        return  # 已种子

    # 从模板 Excel 提取的大区级年度指标
    # 单位：台数(台)、金额(万元)
    region_targets = {
        '俄罗斯':   {'sign_units':5256,'sign_amount':101740.12,'payment_amount':39289.15,'ship_units':2300,'ship_amount':41357,'schedule_units':2300,'schedule_amount':41357},
        '亚洲':     {'sign_units':1339,'sign_amount':13439.85,'payment_amount':5228.8,'ship_units':553,'ship_amount':5504,'schedule_units':553,'schedule_amount':5504},
        '亚洲1':    {'sign_units':1328,'sign_amount':31010,'payment_amount':11972.21,'ship_units':583,'ship_amount':12602.33,'schedule_units':583,'schedule_amount':12602.33},
        '亚洲2':    {'sign_units':1823,'sign_amount':15128.25,'payment_amount':5933.93,'ship_units':503,'ship_amount':6246.25,'schedule_units':503,'schedule_amount':6246.25},
        '美洲':     {'sign_units':2622,'sign_amount':36539.8,'payment_amount':14130.3,'ship_units':1145,'ship_amount':14874,'schedule_units':1145,'schedule_amount':14874},
        '中东':     {'sign_units':2063,'sign_amount':23240,'payment_amount':8827.4,'ship_units':815,'ship_amount':9292,'schedule_units':815,'schedule_amount':9292},
        '非洲':     {'sign_units':1381,'sign_amount':10360,'payment_amount':4088.65,'ship_units':555.62,'ship_amount':4303.84,'schedule_units':555.62,'schedule_amount':4303.84},
        '欧洲':     {'sign_units':118,'sign_amount':1540,'payment_amount':589.95,'ship_units':45,'ship_amount':621,'schedule_units':45,'schedule_amount':621},
        '商贸合计': {'sign_units':0,'sign_amount':12002,'payment_amount':4940,'ship_units':0,'ship_amount':5200,'schedule_units':0,'schedule_amount':5200},
    }

    count = 0
    for region, metrics in region_targets.items():
        for mk, tv in metrics.items():
            db.session.add(AnnualTarget(
                target_year=2026, region=region,
                module_name='', metric_key=mk, target_value=tv
            ))
            count += 1

    db.session.commit()
    print(f'[Seed] 年度指标已种子: {count} 条记录')


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

    db.session.commit()
