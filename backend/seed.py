import json
from flask_bcrypt import Bcrypt
from models import db, Role, User

bcrypt = Bcrypt()


def seed_database(app):
    """首次运行时自动创建管理员账号和角色"""
    with app.app_context():
        db.create_all()

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
