from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, Role, User
from decorators import permission_required

roles_bp = Blueprint('roles', __name__)


@roles_bp.route('/api/roles', methods=['GET'])
@jwt_required()
def get_roles():
    """查询所有角色（登录用户均可调用，用于用户管理的角色下拉）"""
    roles = Role.query.order_by(Role.id).all()
    return jsonify(code=200, msg='success', data=[r.to_dict() for r in roles]), 200


@roles_bp.route('/api/roles', methods=['POST'])
@jwt_required()
@permission_required('role_manage')
def create_role():
    data = request.get_json()
    role_name = data.get('role_name', '').strip()
    is_admin = data.get('is_admin', False)
    permissions = data.get('permissions', [])

    if not role_name:
        return jsonify(code=400, msg='角色名称不能为空', data=None), 400

    if Role.query.filter_by(role_name=role_name).first():
        return jsonify(code=400, msg=f'角色 {role_name} 已存在', data=None), 400

    role = Role(role_name=role_name, is_admin=is_admin)
    role.set_permissions(permissions)
    db.session.add(role)
    db.session.commit()

    return jsonify(code=200, msg='角色创建成功', data=role.to_dict()), 200


@roles_bp.route('/api/roles/<int:role_id>', methods=['PUT'])
@jwt_required()
@permission_required('role_manage')
def update_role(role_id):
    role = db.session.get(Role, role_id)
    if not role:
        return jsonify(code=404, msg='角色不存在', data=None), 404

    data = request.get_json()
    if 'role_name' in data:
        existing = Role.query.filter(
            Role.role_name == data['role_name'], Role.id != role_id
        ).first()
        if existing:
            return jsonify(code=400, msg=f'角色名称 {data["role_name"]} 已存在', data=None), 400
        role.role_name = data['role_name']
    if 'is_admin' in data:
        role.is_admin = data['is_admin']
    if 'permissions' in data:
        role.set_permissions(data['permissions'])

    db.session.commit()
    return jsonify(code=200, msg='角色已更新', data=role.to_dict()), 200


@roles_bp.route('/api/roles/<int:role_id>', methods=['DELETE'])
@jwt_required()
@permission_required('role_manage')
def delete_role(role_id):
    role = db.session.get(Role, role_id)
    if not role:
        return jsonify(code=404, msg='角色不存在', data=None), 404

    if User.query.filter_by(role_id=role_id).count() > 0:
        return jsonify(code=400, msg='该角色下有关联用户，无法删除', data=None), 400

    db.session.delete(role)
    db.session.commit()
    return jsonify(code=200, msg='角色已删除', data=None), 200
