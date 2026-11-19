"""Resolve the data scope of the current user.

The assistant is available to every signed-in user, but returned data is
always limited to the user's existing business scope. Management/global
permissions keep the full-module view; ordinary users with mf_user_scope
rows are limited to those modules and get no business data otherwise.
"""
from module_business_detail.services import BUSINESS_ROLE
from monthly_forecast.models import UserScope
from monthly_forecast import services as mf_svc
from ship_tracking.excel_reader import normalize_text


GLOBAL_PERMISSIONS = {'user_manage', 'dashboard_contract_completion'}


def _permissions(user):
    return user.role.get_permissions() if (user and user.role) else []


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
    permissions = set(_permissions(user))
    role_name = user.role.role_name if (user and user.role) else ''
    is_business = role_name == BUSINESS_ROLE
    # 业务角色也拥有 dashboard_contract_completion 权限，但经营数据必须
    # 继续遵守 mf_user_scope，不能因为该共享权限看到全部模块。
    is_global = (
        bool(user and user.role and user.role.is_admin)
        or (not is_business and bool(permissions & GLOBAL_PERMISSIONS))
    )
    if is_global:
        return {
            'mode': 'global',
            'label': '全部模块',
            'modules': mf_svc.all_modules(),
            'scoped': False,
        }

    modules = _scoped_modules(user) if user else []
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


def requested_modules(scope, requested):
    """Validate a requested module filter against the resolved scope."""
    if not requested:
        return list(scope['modules'])
    if isinstance(requested, str):
        values = [requested]
    else:
        values = list(requested)
    allowed = set(scope['modules'])
    result = []
    for value in values:
        module = normalize_text(value)
        if not module:
            continue
        if module not in allowed:
            raise PermissionError('无权限查询该模块')
        if module not in result:
            result.append(module)
    return result
