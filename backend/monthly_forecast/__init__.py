'''
单月签排发填报 — 独立模块入口

由 app.py 调用 register(app) 单点接入：
1. 注册蓝图（import blueprint 的同时把 4 张 mf_ 表登记进 db.metadata）
2. 幂等建表：只创建缺失的表，不改动任何既有表结构

硬约束（需求方 2026-09-21 明确）：
    账户、角色一律不动。本模块**不写** user / role / module 任何一行。
    角色与模块入口由需求方在后台自行维护。
    这里只做**只读**检查，缺什么就在启动日志里提示，绝不自动创建。
'''
from models import db

ROLE_NAME = '单月签排发填报'
MODULE_NAME = '单月签排发填报'
MODULE_DESC = '各模块填报单月签单、排产、发货预测'
MODULE_URL = '/monthly-forecast'
MODULE_ICON = 'EditPen'
MODULE_SORT = 10
PERMISSION = 'monthly_forecast'

# 该角色应有的权限，仅供后台勾选时参考（本模块不会自动写入）
ROLE_PERMISSIONS = [PERMISSION, 'dashboard_schedule']


def register(app):
    '''注册蓝图 + 只建自己的表；不碰 user / role / module'''
    from monthly_forecast.blueprint import mf_bp

    app.register_blueprint(mf_bp)

    with app.app_context():
        _create_tables()
        _report_readiness()


def _create_tables():
    '''幂等建表：只创建缺失的表（含 4 张 mf_ 表），不改动既有表'''
    from monthly_forecast import models  # noqa: F401  保证模型已登记进 metadata

    db.create_all()


def _report_readiness():
    '''只读检查角色与模块入口是否已由需求方建好；缺了只提示，不自动创建'''
    from models import Module, Role

    if Role.query.filter_by(role_name=ROLE_NAME).first() is None:
        print('[MonthlyForecast] 提示：角色「%s」尚未创建，请在后台「角色管理」创建，'
              '并勾选权限：%s' % (ROLE_NAME, '、'.join(ROLE_PERMISSIONS)))

    if Module.query.filter_by(permission=PERMISSION).first() is None:
        print('[MonthlyForecast] 提示：模块入口尚未创建，请按以下信息在后台添加 —— '
              'name=%s, url=%s, icon=%s, permission=%s, sort=%s'
              % (MODULE_NAME, MODULE_URL, MODULE_ICON, PERMISSION, MODULE_SORT))
