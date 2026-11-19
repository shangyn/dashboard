"""模块经营明细 — 独立只读模块入口。"""
from models import db

PERMISSION = 'module_business_detail'
MODULE_NAME = '模块经营明细'
MODULE_DESC = '按模块查看台账合同与梯号明细（只读）'
MODULE_URL = '/module-business-detail'
MODULE_ICON = 'DataLine'
MODULE_SORT = 12


def register(app):
    from module_business_detail.blueprint import mbd_bp

    app.register_blueprint(mbd_bp)


def initialize(app):
    with app.app_context():
        _ensure_module()


def _ensure_module():
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
        if not module.name:
            module.name = MODULE_NAME
        if module.description in ('', '按模块查看合同、梯号、签排发、回款与计划明细（只读）'):
            module.description = MODULE_DESC
        if not module.url:
            module.url = MODULE_URL
        if not module.icon:
            module.icon = MODULE_ICON
        if not module.sort_order:
            module.sort_order = MODULE_SORT
    db.session.commit()

    roles = [
        role.role_name for role in Role.query.all()
        if PERMISSION in role.get_permissions()
    ]
    if not roles:
        print('[ModuleBusinessDetail] 模块入口已创建；请在角色管理中为需要的角色勾选“模块经营明细”权限')
