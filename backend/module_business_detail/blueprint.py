from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_current_user, jwt_required

from decorators import permission_required
from module_business_detail import PERMISSION
from module_business_detail import services as svc

mbd_bp = Blueprint('module_business_detail', __name__)


def _ok(data=None, msg='success'):
    return jsonify(code=200, msg=msg, data=data), 200


def _fail(msg, code=400):
    return jsonify(code=code, msg=msg, data=None), code


def _filters():
    return {
        'month': request.args.get('month') or '',
        'year': request.args.get('year') or '',
        'module': request.args.get('module') or '',
        'keyword': request.args.get('q') or '',
        'page': request.args.get('page') or 1,
        'page_size': request.args.get('page_size') or 50,
    }


@mbd_bp.route('/api/module-business-detail/context', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_context():
    try:
        return _ok(svc.get_context(get_current_user()))
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except Exception as exc:
        return _fail('加载失败: %s' % exc, 500)


@mbd_bp.route('/api/module-business-detail/overview', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_overview():
    args = _filters()
    try:
        return _ok(svc.get_overview(
            get_current_user(), month=args['month'], module=args['module'],
        ))
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('读取经营概览失败: %s' % exc, 500)


@mbd_bp.route('/api/module-business-detail/ladders', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_ladders():
    args = _filters()
    try:
        return _ok(svc.get_ladders(
            get_current_user(),
            month=args['month'],
            module=args['module'],
            keyword=args['keyword'],
            page=args['page'],
            page_size=args['page_size'],
        ))
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('读取梯号明细失败: %s' % exc, 500)


@mbd_bp.route('/api/module-business-detail/payments', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_payments():
    args = _filters()
    try:
        return _ok(svc.get_payments(
            get_current_user(),
            month=args['month'],
            year=args['year'] or None,
            module=args['module'],
            keyword=args['keyword'],
            page=args['page'],
            page_size=args['page_size'],
        ))
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('读取回款明细失败: %s' % exc, 500)


@mbd_bp.route('/api/module-business-detail/export', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_export():
    args = _filters()
    try:
        output = svc.export_workbook(
            get_current_user(),
            month=args['month'],
            module=args['module'],
            keyword=args['keyword'],
        )
        filename = '模块经营明细_%s.xlsx' % (args['month'] or '全部')
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
        return _fail('导出失败: %s' % exc, 500)
