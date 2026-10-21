"""
单月签排发填报 — API 蓝图

权限模型：
- 全部接口要求 monthly_forecast 权限
- 有模块归属（名单命中）→ 只能读写自己的模块，只能导出「预计签排发台数金额」
- 无模块归属（角色外 / 管理层）→ 全部模块只读汇总 + 导出两张，写接口一律 403
"""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_current_user

from decorators import permission_required
from monthly_forecast import PERMISSION
from monthly_forecast import services as svc
from monthly_forecast.handlers import import_scope

mf_bp = Blueprint('monthly_forecast', __name__)


# 内部工具

def _fail(msg, code=400):
    return jsonify(code=code, msg=msg, data=None), code


def _ok(data, msg='success'):
    return jsonify(code=200, msg=msg, data=data), 200


def _permissions_of(user):
    return user.role.get_permissions() if (user and user.role) else []


def _is_management(user):
    """管理层：管理员角色，或持有 user_manage 权限"""
    if not user or not user.role:
        return False
    return bool(user.role.is_admin or 'user_manage' in _permissions_of(user))


def _visible_modules(user):
    """返回 (可见模块列表, 是否受限于模块归属)"""
    scoped = svc.scope_modules(user.id)
    if scoped:
        return scoped, True
    return svc.all_modules(), False


def _resolve_month():
    month = svc.normalize_month(request.args.get('month') or '')
    return month


def _resolve_target_module(user, requested):
    """确定要读写的模块；返回 (module_name, error_response)"""
    scoped = svc.scope_modules(user.id)
    if not scoped:
        return None, _fail('当前账号没有模块填报归属，仅可查看汇总', 403)
    requested = (requested or '').strip()
    if not requested:
        if len(scoped) == 1:
            return scoped[0], None
        return None, _fail('请指定模块', 400)
    if requested not in scoped:
        return None, _fail('无权限操作该模块', 403)
    return requested, None


def _payload():
    return request.get_json(silent=True) or {}


# 上下文

@mf_bp.route('/api/monthly-forecast/context', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_context():
    """页面初始化：模式（填报 / 只读汇总）、可选月份、模块列表、导出能力"""
    user = get_current_user()
    scoped = svc.scope_modules(user.id)
    try:
        return _ok({
            'months': svc.month_options(),
            'default_month': svc.default_month(),
            'scoped': bool(scoped),
            'my_modules': scoped,
            'all_modules': [] if scoped else svc.all_modules(),
            'can_export_shipping': not scoped,
            'can_import_scope': _is_management(user),
        })
    except Exception as exc:
        return _fail(f'加载失败: {exc}', 500)


@mf_bp.route('/api/monthly-forecast/months', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_months():
    try:
        return _ok({'months': svc.month_options(), 'default_month': svc.default_month()})
    except Exception as exc:
        return _fail(f'加载失败: {exc}', 500)


# 填报读写

@mf_bp.route('/api/monthly-forecast/entry', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_get_entry():
    user = get_current_user()
    month = _resolve_month()
    if not month:
        return _fail('月份格式不正确，应为 YYYY-MM')
    module, error = _resolve_target_module(user, request.args.get('module'))
    if error:
        return error
    try:
        return _ok(svc.get_entry(month, module))
    except Exception as exc:
        return _fail(f'读取失败: {exc}', 500)


@mf_bp.route('/api/monthly-forecast/entry', methods=['PUT'])
@jwt_required()
@permission_required(PERMISSION)
def api_save_entry():
    user = get_current_user()
    payload = _payload()
    month = svc.normalize_month(payload.get('month') or request.args.get('month') or '')
    if not month:
        return _fail('月份格式不正确，应为 YYYY-MM')
    module, error = _resolve_target_module(user, payload.get('module'))
    if error:
        return error
    try:
        return _ok(svc.save_draft(month, module, payload.get('data') or payload, user), '已保存')
    except Exception as exc:
        return _fail(f'保存失败: {exc}', 500)


@mf_bp.route('/api/monthly-forecast/entry/submit', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_submit_entry():
    user = get_current_user()
    payload = _payload()
    month = svc.normalize_month(payload.get('month') or request.args.get('month') or '')
    if not month:
        return _fail('月份格式不正确，应为 YYYY-MM')
    module, error = _resolve_target_module(user, payload.get('module'))
    if error:
        return error
    try:
        result = svc.submit(month, module, payload.get('data') or payload, user)
        return _ok(result, f'已提交，版本 {result.get("version")}')
    except Exception as exc:
        return _fail(f'提交失败: {exc}', 500)


@mf_bp.route('/api/monthly-forecast/submissions', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_submissions():
    user = get_current_user()
    month = _resolve_month()
    if not month:
        return _fail('月份格式不正确，应为 YYYY-MM')
    module, error = _resolve_target_module(user, request.args.get('module'))
    if error:
        return error
    try:
        return _ok(svc.list_submissions(month, module))
    except Exception as exc:
        return _fail(f'读取失败: {exc}', 500)


# 候选池与梯号校验

@mf_bp.route('/api/monthly-forecast/candidates', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_candidates():
    user = get_current_user()
    month = _resolve_month()
    if not month:
        return _fail('月份格式不正确，应为 YYYY-MM')
    module, error = _resolve_target_module(user, request.args.get('module'))
    if error:
        return error
    try:
        return _ok(svc.list_candidates(module, month, request.args.get('q')))
    except Exception as exc:
        return _fail(f'读取候选池失败: {exc}', 500)


@mf_bp.route('/api/monthly-forecast/ladder/validate', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_validate_ladder():
    user = get_current_user()
    payload = _payload()
    month = svc.normalize_month(payload.get('month') or '')
    if not month:
        return _fail('月份格式不正确，应为 YYYY-MM')
    module, error = _resolve_target_module(user, payload.get('module'))
    if error:
        return error
    try:
        result = svc.validate_ladder(module, month, payload.get('ladder_no'))
        return _ok(result, result['msg'])
    except Exception as exc:
        return _fail(f'校验失败: {exc}', 500)


# 汇总

@mf_bp.route('/api/monthly-forecast/summary', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_summary():
    user = get_current_user()
    month = _resolve_month()
    if not month:
        return _fail('月份格式不正确，应为 YYYY-MM')
    modules, scoped = _visible_modules(user)
    try:
        data = svc.get_summary(month, modules=modules)
        data['scoped'] = scoped
        return _ok(data)
    except Exception as exc:
        return _fail(f'读取汇总失败: {exc}', 500)


# 导出

@mf_bp.route('/api/monthly-forecast/export/forecast', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_export_forecast():
    """Excel 1：预计签排发台数金额（模块人员仅本模块，角色外全量）"""
    user = get_current_user()
    month = _resolve_month()
    if not month:
        return _fail('月份格式不正确，应为 YYYY-MM')
    modules, _ = _visible_modules(user)
    try:
        path = svc.export_forecast(month, modules=modules)
        return send_file(path, as_attachment=True,
                         download_name=f'{month}_预计签排发台数金额.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as exc:
        return _fail(f'导出失败: {exc}', 500)


@mf_bp.route('/api/monthly-forecast/export/shipping', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_export_shipping():
    """Excel 2：预计能发货的合同号梯号明细（仅角色外账号，模块人员 403）"""
    user = get_current_user()
    modules, scoped = _visible_modules(user)
    if scoped:
        return _fail('当前账号无导出明细权限', 403)
    month = _resolve_month()
    if not month:
        return _fail('月份格式不正确，应为 YYYY-MM')
    try:
        path = svc.export_shipping(month, modules=modules)
        return send_file(path, as_attachment=True,
                         download_name=f'{month}_预计发货合同梯号明细.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as exc:
        return _fail(f'导出失败: {exc}', 500)


# 名单

def _user_status(owner):
    """名单行的账号状态：active / inactive / missing"""
    if owner is None:
        return 'missing'
    return 'active' if owner.is_active else 'inactive'


@mf_bp.route('/api/monthly-forecast/scope', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_get_scope():
    user = get_current_user()
    if not _is_management(user):
        return _fail('无权限查看名单', 403)
    try:
        from models import User
        from monthly_forecast.models import UserScope
        rows = UserScope.query.order_by(UserScope.module_name, UserScope.user_id).all()
        users = {u.id: u for u in User.query.all()}
        data = []
        for row in rows:
            item = row.to_dict()
            owner = users.get(row.user_id)
            item['username'] = owner.username if owner else ''
            item['real_name'] = owner.real_name if owner else ''
            item['user_status'] = _user_status(owner)
            data.append(item)
        return _ok(data)
    except Exception as exc:
        return _fail(f'读取名单失败: {exc}', 500)


@mf_bp.route('/api/monthly-forecast/scope', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_import_scope():
    user = get_current_user()
    if not _is_management(user):
        return _fail('无权限导入名单', 403)
    if 'file' not in request.files:
        return _fail('未选择文件')
    upload = request.files['file']
    if not upload.filename:
        return _fail('文件名为空')
    if not upload.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
        return _fail('仅支持 .xlsx / .xls / .csv')
    try:
        import os
        import tempfile
        suffix = os.path.splitext(upload.filename)[1]
        temp_path = os.path.join(tempfile.gettempdir(), f'mf_scope_import{suffix}')
        upload.save(temp_path)
        result = import_scope(temp_path)
        os.remove(temp_path)
        return _ok(result, result.get('message', ''))
    except Exception as exc:
        return _fail(f'导入失败: {exc}', 500)


# 名单管理（逐条维护归属；只写 mf_user_scope，不动 user 表与填报数据）

@mf_bp.route('/api/monthly-forecast/scope/options', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_scope_options():
    """名单管理下拉数据：全部模块 + 全部账号"""
    user = get_current_user()
    if not _is_management(user):
        return _fail('无权限查看名单', 403)
    try:
        from models import User
        users = User.query.order_by(User.username).all()
        return _ok({
            'modules': svc.all_modules(),
            'users': [
                {
                    'id': u.id,
                    'username': u.username or '',
                    'real_name': u.real_name or '',
                    'is_active': bool(u.is_active),
                }
                for u in users
            ],
        })
    except Exception as exc:
        return _fail(f'读取人员失败: {exc}', 500)


@mf_bp.route('/api/monthly-forecast/scope/item', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_add_scope_item():
    """新增一条「账号 ↔ 模块」归属"""
    user = get_current_user()
    if not _is_management(user):
        return _fail('无权限修改名单', 403)
    from models import db, User
    from sqlalchemy.exc import IntegrityError
    from monthly_forecast.models import UserScope
    payload = _payload()
    try:
        user_id = int(payload.get('user_id'))
    except (TypeError, ValueError):
        return _fail('请选择账号')
    module_name = (payload.get('module_name') or '').strip()
    if not module_name:
        return _fail('请选择模块')
    try:
        owner = User.query.get(user_id)
        if not owner:
            return _fail('账号不存在')
        if module_name not in svc.all_modules():
            return _fail(f'模块不存在：{module_name}')
        if UserScope.query.filter_by(user_id=user_id, module_name=module_name).first():
            return _fail(f'该账号已在「{module_name}」模块')
        row = UserScope(user_id=user_id, match_key=owner.username or '',
                        module_name=module_name)
        db.session.add(row)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return _fail(f'该账号已在「{module_name}」模块')
        item = row.to_dict()
        item['username'] = owner.username or ''
        item['real_name'] = owner.real_name or ''
        item['user_status'] = _user_status(owner)
        return _ok(item, '已添加')
    except Exception as exc:
        db.session.rollback()
        return _fail(f'添加失败: {exc}', 500)


@mf_bp.route('/api/monthly-forecast/scope/item/<int:item_id>', methods=['DELETE'])
@jwt_required()
@permission_required(PERMISSION)
def api_delete_scope_item(item_id):
    """移除一条归属（只删名单行，不动账号与填报数据）"""
    user = get_current_user()
    if not _is_management(user):
        return _fail('无权限修改名单', 403)
    from models import db
    from monthly_forecast.models import UserScope
    try:
        row = UserScope.query.get(item_id)
        if not row:
            return _fail('归属不存在', 404)
        db.session.delete(row)
        db.session.commit()
        return _ok({'id': item_id}, '已移除')
    except Exception as exc:
        db.session.rollback()
        return _fail(f'移除失败: {exc}', 500)


@mf_bp.route('/api/monthly-forecast/scope/cleanup', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_cleanup_scope():
    """清理「账号已不存在」的无效归属"""
    user = get_current_user()
    if not _is_management(user):
        return _fail('无权限修改名单', 403)
    from models import db, User
    from monthly_forecast.models import UserScope
    try:
        valid_ids = {uid for (uid,) in db.session.query(User.id).all()}
        orphans = [row for row in UserScope.query.all()
                   if row.user_id is None or row.user_id not in valid_ids]
        for row in orphans:
            db.session.delete(row)
        if orphans:
            db.session.commit()
        return _ok({'removed': len(orphans)}, f'已清理 {len(orphans)} 条无效归属')
    except Exception as exc:
        db.session.rollback()
        return _fail(f'清理失败: {exc}', 500)
