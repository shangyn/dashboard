"""Resolve the data scope of the current user.

The assistant is available only to explicitly allowlisted roles. Global
roles can query every module; the monthly fill role can query only modules
assigned in mf_user_scope. All other roles have no assistant access.
"""
from monthly_forecast.models import UserScope
from monthly_forecast import services as mf_svc
from ship_tracking.excel_reader import normalize_text

from business_assistant import resolver


ALL_MODULE_ROLES = frozenset({'管理员', '查看上传', '仅查看不上传'})
MODULE_SCOPED_ROLES = frozenset({'单月签排发填报'})
ASSISTANT_FORBIDDEN_MESSAGE = '当前账号没有经营助手使用权限'


def _role_name(user):
    if not user or not user.role:
        return ''
    return normalize_text(user.role.role_name)


def assistant_allowed(user):
    if not user or not user.role:
        return False
    if bool(user.role.is_admin):
        return True
    return _role_name(user) in (ALL_MODULE_ROLES | MODULE_SCOPED_ROLES)


def _scoped_modules(user):
    rows = UserScope.query.filter_by(user_id=user.id).order_by(UserScope.module_name).all()
    result = []
    for row in rows:
        module = normalize_text(row.module_name)
        if module and module not in result:
            result.append(module)
    return result


def resolve_scope(user):
    """Return a permission-safe scope descriptor for the assistant."""
    if not assistant_allowed(user):
        raise PermissionError(ASSISTANT_FORBIDDEN_MESSAGE)
    role_name = _role_name(user)
    if bool(user.role.is_admin) or role_name in ALL_MODULE_ROLES:
        return {
            'mode': 'global',
            'label': '全部模块',
            'modules': mf_svc.all_modules(),
            'scoped': False,
        }

    if role_name in MODULE_SCOPED_ROLES:
        modules = _scoped_modules(user)
        if modules:
            return {
                'mode': 'module',
                'label': '本人模块',
                'modules': modules,
                'scoped': True,
            }

        return {
            'mode': 'none',
            'label': '暂无经营数据权限',
            'modules': [],
            'scoped': True,
        }

    raise PermissionError(ASSISTANT_FORBIDDEN_MESSAGE)


def resolve_requested_modules(scope, requested):
    """Resolve a module filter and distinguish missing from forbidden names."""
    all_module_names = scope['modules'] if not scope.get('scoped') else mf_svc.all_modules()
    return resolver.resolve_modules(scope, requested, all_module_names)


def requested_modules(scope, requested):
    """Validate a requested module filter against the resolved scope."""
    if not requested:
        return list(scope['modules'])
    resolution = resolve_requested_modules(scope, requested)
    if resolution['status'] == resolver.STATUS_FORBIDDEN:
        raise PermissionError(resolution['message'])
    if resolution['status'] == resolver.STATUS_NOT_FOUND:
        raise ValueError(resolution['message'])
    return resolution['modules']
