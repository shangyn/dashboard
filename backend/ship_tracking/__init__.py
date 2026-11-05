"""发货梯号追踪 — 独立模块入口。

只做三件事：
1. 注册 st_ 蓝图；
2. 幂等创建 st_ 表，不修改 cc_/mf_ 表；
3. 幂等补齐本模块的菜单/权限。旧角色只追加权限，不删除、不覆盖历史值。
"""
import os
import time

from models import db

PERMISSION = 'ship_tracking'
VIEW_PERMISSION = 'ship_tracking_view'
DAILY_PERMISSION = 'ship_tracking_daily_edit'
ADMIN_PERMISSION = 'ship_tracking_admin'
MODULE_NAME = '发货梯号明细'
MODULE_DESC = '按周填报预计发货梯号、每日实发、订舱与全量明细'
OLD_MODULE_NAME = '发货梯号追踪'
OLD_MODULE_DESC = '按周填报预计发货梯号、每日实发、订舱与全量追踪'
MODULE_URL = '/ship-tracking'
MODULE_ICON = 'Van'
MODULE_SORT = 11
DAILY_ROLE_NAME = '发货梯号实发'


def register(app):
    '''仅注册蓝图；必须在原项目 seed_database 完成后调用 initialize。'''
    from ship_tracking.blueprint import st_bp
    app.register_blueprint(st_bp)


def initialize(app):
    '''建表、补权限、首次导入。放在 seed_database 之后，避免新角色干扰原初始化判断。'''
    with app.app_context():
        lock_path = os.path.join(app.root_path, 'instance', '.ship_tracking_init.lock')
        acquired = _acquire_init_lock(lock_path)
        try:
            _create_tables()
            _ensure_tracking_columns()
            _ensure_daily_shipment_guard()
            _ensure_access()
            _bootstrap_plan_if_empty(app)
        finally:
            if acquired:
                _release_init_lock(lock_path)


def _acquire_init_lock(lock_path, timeout=20.0):
    '''多 worker 启动时串行执行建表/权限/首次导入。'''
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, ('%s' % os.getpid()).encode('ascii'))
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock_path) > 120:
                    os.remove(lock_path)
                    continue
            except OSError:
                pass
            time.sleep(0.2)
    print('[ShipTracking] 初始化锁等待超时，本 worker 跳过初始化；其余 worker 会完成建表与权限配置')
    return False


def _release_init_lock(lock_path):
    try:
        os.remove(lock_path)
    except OSError:
        pass


def _create_tables():
    from ship_tracking import models  # noqa: F401
    db.create_all()


def _ensure_tracking_columns():
    """为已存在的 st_ 表补新列；db.create_all 不会自动迁移旧表。"""
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    if 'st_tracking_item' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('st_tracking_item')}
    actual_ship_source_added = False
    if 'actual_ship_source' not in columns:
        db.session.execute(text(
            'ALTER TABLE st_tracking_item ADD COLUMN actual_ship_source VARCHAR(20)'
        ))
        db.session.commit()
        actual_ship_source_added = True
    payment_ratio_added = False
    if 'business_expected_raw' not in columns:
        db.session.execute(text(
            "ALTER TABLE st_tracking_item ADD COLUMN business_expected_raw VARCHAR(100) DEFAULT ''"
        ))
        db.session.commit()
    if 'payment_ratio' not in columns:
        db.session.execute(text(
            "ALTER TABLE st_tracking_item ADD COLUMN payment_ratio FLOAT"
        ))
        db.session.commit()
        payment_ratio_added = True
    # 新列首次上线时，从当前计划快照回填源值，便于页面直接解释日期来源。
    db.session.execute(text(
        "UPDATE st_tracking_item SET business_expected_raw = COALESCE(("
        "SELECT p.business_expected_raw FROM st_plan_item p "
        "WHERE p.ladder_key = st_tracking_item.ladder_key "
        "ORDER BY p.plan_version DESC, p.id DESC LIMIT 1), '') "
        "WHERE COALESCE(business_expected_raw, '') = ''"
    ))
    db.session.commit()
    # 新字段首次上线时回填全部已匹配梯号；后续台账上传/计划提交会自动同步。
    if payment_ratio_added or actual_ship_source_added:
        try:
            from ship_tracking.sync import sync_tracking_dates
            result = sync_tracking_dates(source='startup:schema_migration')
            if not result.get('ok'):
                print('[ShipTracking] 台账字段初始回填失败: %s' % result.get('message', ''))
        except Exception as exc:
            print('[ShipTracking] 台账字段初始回填异常: %s' % exc)


def _ensure_daily_shipment_guard():
    """同一梯号只允许一条有效实发；并发提交由数据库唯一索引兜底。"""
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    if 'st_daily_shipment' not in inspector.get_table_names():
        return
    existing = {row['name'] for row in inspector.get_indexes('st_daily_shipment')}
    if 'uq_st_daily_shipment_active' in existing:
        return
    duplicates = db.session.execute(text(
        "SELECT ladder_key, COUNT(1) AS c FROM st_daily_shipment "
        "WHERE is_void = 0 GROUP BY ladder_key HAVING COUNT(1) > 1"
    )).mappings().all()
    if duplicates:
        # 不自动删除历史事实，避免误改数据；先提示人工核对后再建索引。
        print('[ShipTracking] 警告：存在重复有效实发，未创建唯一索引: %s'
              % [dict(row) for row in duplicates[:20]])
        return
    db.session.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_st_daily_shipment_active "
        "ON st_daily_shipment(ladder_key) WHERE is_void = 0"
    ))
    db.session.commit()
    print('[ShipTracking] 已创建有效实发唯一索引 uq_st_daily_shipment_active')


def _ensure_access():
    from models import Module, Role

    module = Module.query.filter_by(permission=PERMISSION).first()
    if module is None:
        module = Module(
            name=MODULE_NAME,
            description=MODULE_DESC,
            permission=PERMISSION,
            url=MODULE_URL,
            icon=MODULE_ICON,
            sort_order=MODULE_SORT,
            is_active=True,
        )
        db.session.add(module)
    else:
        # 旧库中已有模块行：只把旧默认名/描述迁移为新名，保留管理员自定义过的值。
        if not module.name or module.name == OLD_MODULE_NAME:
            module.name = MODULE_NAME
        if not module.description or module.description == OLD_MODULE_DESC:
            module.description = MODULE_DESC
        module.url = module.url or MODULE_URL
        module.icon = module.icon or MODULE_ICON
        module.is_active = True

    # 管理员与现有查看角色：模块入口 + 全量查看；填报角色只获得入口。
    role_specs = {
        '管理员': [PERMISSION, VIEW_PERMISSION, ADMIN_PERMISSION],
        '查看上传': [PERMISSION, VIEW_PERMISSION],
        '仅查看不上传': [PERMISSION, VIEW_PERMISSION],
        '单月签排发填报': [PERMISSION],
    }
    changed_roles = []
    for role in Role.query.all():
        wanted = list(role_specs.get(role.role_name, []))
        if role.is_admin and PERMISSION not in wanted:
            wanted.append(PERMISSION)
        if not wanted:
            continue
        current = role.get_permissions()
        additions = [permission for permission in wanted if permission not in current]
        if additions:
            role.set_permissions(current + additions)
            changed_roles.append({'role': role.role_name, 'added': additions})

    daily_role = Role.query.filter_by(role_name=DAILY_ROLE_NAME).first()
    if daily_role is None:
        daily_role = Role(role_name=DAILY_ROLE_NAME, is_admin=False)
        daily_role.set_permissions([PERMISSION, VIEW_PERMISSION, DAILY_PERMISSION])
        db.session.add(daily_role)
        daily_role_note = '已创建角色「%s」，请到用户管理为专有实发人员分配，不要分配给业务填报人员' % DAILY_ROLE_NAME
    else:
        existing = daily_role.get_permissions()
        additions = [permission for permission in (PERMISSION, VIEW_PERMISSION, DAILY_PERMISSION)
                     if permission not in existing]
        if additions:
            daily_role.set_permissions(existing + additions)
        daily_role_note = ''

    db.session.commit()
    if changed_roles:
        print('[ShipTracking] 权限已追加: %s' % changed_roles)
    if daily_role_note:
        print('[ShipTracking] ' + daily_role_note)


def _bootstrap_plan_if_empty(app):
    """开发环境可选：首次启动自动导入仓库中的计划文件。

    默认关闭，避免清库后重启被旧文件意外回填；需要时设置
    SHIP_TRACKING_AUTO_BOOTSTRAP=1。
    """
    if os.environ.get('SHIP_TRACKING_AUTO_BOOTSTRAP', '0') != '1':
        return
    from ship_tracking.models import ImportBatch, TrackingItem
    if ImportBatch.query.filter_by(data_type='plan', status='committed').first():
        return
    if TrackingItem.query.count() > 0:
        return
    candidates = [
        os.path.join(os.path.dirname(app.root_path), '11月梯号发货明细.xlsx'),
        os.path.join(app.root_path, '..', '11月梯号发货明细.xlsx'),
    ]
    source = next((path for path in candidates if os.path.isfile(path)), None)
    if not source:
        print('[ShipTracking] 未找到默认 2026-11 计划文件，请通过导入管理上传')
        return
    try:
        from models import User
        from ship_tracking.importer import commit_plan_import, preview_plan_import
        admin = User.query.filter_by(username='admin').first()
        if admin is None:
            print('[ShipTracking] 未找到 admin 账号，跳过默认计划导入')
            return
        preview = preview_plan_import(source, os.path.basename(source), '2026-11', admin)
        result = commit_plan_import(preview['id'], admin, force=True)
        print('[ShipTracking] 默认计划已导入: %s 台 / %s 个唯一梯号，版本 %s'
              % (result['total_units'], result['unique_count'], result['version']))
    except Exception as exc:
        db.session.rollback()
        print('[ShipTracking] 默认计划自动导入失败: %s' % exc)
