"""Independent read-only business assistant API."""
import logging

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_current_user, jwt_required

from business_assistant import exporting
from business_assistant import services


assistant_bp = Blueprint('business_assistant', __name__)
logger = logging.getLogger(__name__)


def _ok(data=None, msg='success'):
    return jsonify(code=200, msg=msg, data=data), 200


def _fail(message, code=400):
    return jsonify(code=code, msg=message, data=None), code


def _admin_user():
    user = get_current_user()
    if not services.is_admin(user):
        return None
    return user


@assistant_bp.route('/api/business-assistant/admin/setting', methods=['GET'])
@jwt_required()
def api_admin_setting():
    user = _admin_user()
    if user is None:
        return _fail('仅管理员可以管理经营助手开关', 403)
    try:
        return _ok(services.get_setting())
    except Exception as exc:
        logger.exception('读取经营助手管理员设置失败')
        return _fail('读取设置失败: %s' % exc, 500)


@assistant_bp.route('/api/business-assistant/admin/setting', methods=['PUT'])
@jwt_required()
def api_update_admin_setting():
    user = _admin_user()
    if user is None:
        return _fail('仅管理员可以管理经营助手开关', 403)
    payload = request.get_json(silent=True) or {}
    enabled_value = payload.get('enabled')
    if not isinstance(enabled_value, bool) and enabled_value in (0, 1):
        enabled_value = bool(enabled_value)
    elif not isinstance(enabled_value, bool):
        return _fail('enabled 必须为布尔值', 400)
    try:
        setting = services.update_setting(user, enabled_value)
        logger.info(
            'assistant setting updated user=%s enabled=%s',
            user.id, setting.get('enabled'),
        )
        return _ok(setting, '经营助手开关已更新')
    except Exception as exc:
        logger.exception('更新经营助手管理员设置失败')
        return _fail('更新设置失败: %s' % exc, 500)


@assistant_bp.route('/api/business-assistant/context', methods=['GET'])
@jwt_required()
def api_context():
    try:
        return _ok(services.get_context(get_current_user()))
    except Exception as exc:
        logger.exception('读取经营助手上下文失败')
        return _fail('读取助手上下文失败: %s' % exc, 500)


@assistant_bp.route('/api/business-assistant/chat', methods=['POST'])
@jwt_required()
def api_chat():
    if not services.enabled():
        return _fail('经营助手暂未开启', 503)
    payload = request.get_json(silent=True) or {}
    question = payload.get('question') or ''
    page_context = payload.get('page_context') or {}
    user = get_current_user()
    try:
        result = services.answer(user, question, page_context=page_context)
        logger.info(
            'assistant query user=%s trace=%s action=%s',
            user.id,
            result.get('trace_id'),
            result.get('kind'),
        )
        return _ok(result)
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except RuntimeError as exc:
        return _fail(str(exc), 503)
    except Exception as exc:
        logger.exception('经营助手查询失败')
        return _fail('查询失败: %s' % exc, 500)


@assistant_bp.route('/api/business-assistant/export', methods=['GET'])
@jwt_required()
def api_export():
    if not services.enabled():
        return _fail('经营助手暂未开启', 503)
    token = request.args.get('token') or ''
    if not token:
        return _fail('缺少导出令牌')
    try:
        output, filename = exporting.export_workbook(get_current_user(), token)
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        logger.exception('经营助手导出失败')
        return _fail('导出失败: %s' % exc, 500)
