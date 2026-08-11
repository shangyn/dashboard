from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, OperationLog
from decorators import permission_required

operations_bp = Blueprint('operations', __name__)


@operations_bp.route('/api/operation-logs', methods=['GET'])
@jwt_required()
@permission_required('upload_manage')
def get_operation_logs():
    """操作日志列表（管理员）"""
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    action_type = request.args.get('action_type', '')
    username = request.args.get('username', '')

    query = OperationLog.query
    if action_type:
        query = query.filter_by(action_type=action_type)
    if username:
        query = query.filter(OperationLog.username.like(f'%{username}%'))

    pagination = query.order_by(OperationLog.created_at.desc()) \
        .paginate(page=page, per_page=page_size, error_out=False)

    return jsonify(code=200, msg='success', data={
        'items': [r.to_dict() for r in pagination.items],
        'total': pagination.total,
    }), 200
