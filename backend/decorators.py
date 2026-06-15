from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_current_user


def permission_required(permission):
    """检查当前登录用户是否拥有指定权限"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user or not user.role:
                return jsonify(code=403, msg='无权限：未登录或未分配角色', data=None), 403
            perms = user.role.get_permissions()
            if permission not in perms:
                return jsonify(code=403, msg=f'无权限：缺少 {permission}', data=None), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
