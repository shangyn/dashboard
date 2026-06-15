from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_current_user
from models import db, Module
from decorators import permission_required

modules_bp = Blueprint('modules', __name__)


@modules_bp.route('/api/modules', methods=['GET'])
@jwt_required()
@permission_required('module_manage')
def get_modules():
    modules = Module.query.order_by(Module.sort_order, Module.id).all()
    return jsonify(code=200, msg='success', data=[m.to_dict() for m in modules]), 200


@modules_bp.route('/api/modules', methods=['POST'])
@jwt_required()
@permission_required('module_manage')
def create_module():
    data = request.get_json()
    module = Module(
        name=data.get('name', ''),
        description=data.get('description', ''),
        permission=data.get('permission', ''),
        url=data.get('url', ''),
        icon=data.get('icon', ''),
        sort_order=data.get('sort_order', 0),
        is_active=data.get('is_active', True),
    )
    if not module.name or not module.permission:
        return jsonify(code=400, msg='模块名称和权限标识不能为空', data=None), 400

    db.session.add(module)
    db.session.commit()
    return jsonify(code=200, msg='模块创建成功', data=module.to_dict()), 200


@modules_bp.route('/api/modules/<int:module_id>', methods=['PUT'])
@jwt_required()
@permission_required('module_manage')
def update_module(module_id):
    module = db.session.get(Module, module_id)
    if not module:
        return jsonify(code=404, msg='模块不存在', data=None), 404

    data = request.get_json()
    for field in ['name', 'description', 'permission', 'url', 'icon', 'sort_order', 'is_active']:
        if field in data:
            setattr(module, field, data[field])

    db.session.commit()
    return jsonify(code=200, msg='模块已更新', data=module.to_dict()), 200


@modules_bp.route('/api/modules/<int:module_id>', methods=['DELETE'])
@jwt_required()
@permission_required('module_manage')
def delete_module(module_id):
    module = db.session.get(Module, module_id)
    if not module:
        return jsonify(code=404, msg='模块不存在', data=None), 404
    db.session.delete(module)
    db.session.commit()
    return jsonify(code=200, msg='模块已删除', data=None), 200


@modules_bp.route('/api/my-modules', methods=['GET'])
@jwt_required()
def my_modules():
    """返回当前用户可见的模块列表（根据角色权限过滤）"""
    user = get_current_user()
    if not user or not user.role:
        return jsonify(code=200, msg='success', data=[]), 200

    permissions = user.role.get_permissions()
    modules = Module.query.filter(
        Module.is_active == True,
        Module.permission.in_(permissions)
    ).order_by(Module.sort_order, Module.id).all()

    return jsonify(code=200, msg='success', data=[m.to_dict() for m in modules]), 200
