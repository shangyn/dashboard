from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_current_user
from flask_bcrypt import Bcrypt
from models import db, User, Role
from decorators import permission_required

users_bp = Blueprint('users', __name__)
bcrypt = Bcrypt()


@users_bp.route('/api/users', methods=['GET'])
@jwt_required()
@permission_required('user_manage')
def get_users():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 10, type=int)
    username = request.args.get('username', '').strip()
    real_name = request.args.get('real_name', '').strip()

    query = User.query
    if username:
        query = query.filter(User.username.like(f'%{username}%'))
    if real_name:
        query = query.filter(User.real_name.like(f'%{real_name}%'))

    pagination = query.order_by(User.id.desc()).paginate(
        page=page, per_page=page_size, error_out=False
    )

    users_list = []
    for u in pagination.items:
        user_dict = u.to_dict()
        user_dict['role_name'] = u.role.role_name if u.role else ''
        users_list.append(user_dict)

    return jsonify(code=200, msg='success', data={
        'items': users_list,
        'total': pagination.total,
        'page': page,
        'page_size': page_size,
    }), 200


@users_bp.route('/api/users', methods=['POST'])
@jwt_required()
@permission_required('user_manage')
def create_user():
    data = request.get_json()

    username = data.get('username', '').strip()
    password = data.get('password', '')
    real_name = data.get('real_name', '').strip()
    role_id = data.get('role_id')
    is_active = data.get('is_active', True)

    if not username:
        return jsonify(code=400, msg='工号不能为空', data=None), 400
    if not password or len(password) < 6:
        return jsonify(code=400, msg='密码长度不能少于6位', data=None), 400

    if User.query.filter_by(username=username).first():
        return jsonify(code=400, msg=f'工号 {username} 已存在', data=None), 400

    user = User(
        username=username,
        password=bcrypt.generate_password_hash(password).decode('utf-8'),
        real_name=real_name,
        role_id=role_id if role_id else None,
        is_active=is_active,
    )
    db.session.add(user)
    db.session.commit()

    return jsonify(code=200, msg='用户创建成功', data=user.to_dict()), 200


@users_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@jwt_required()
@permission_required('user_manage')
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(code=404, msg='用户不存在', data=None), 404

    data = request.get_json()
    if 'real_name' in data:
        user.real_name = data['real_name']
    if 'role_id' in data:
        user.role_id = data['role_id']
    if 'is_active' in data:
        user.is_active = data['is_active']

    db.session.commit()
    return jsonify(code=200, msg='用户信息已更新', data=user.to_dict()), 200


@users_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
@permission_required('user_manage')
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(code=404, msg='用户不存在', data=None), 404

    current = get_current_user()
    if current and current.id == user.id:
        return jsonify(code=400, msg='不能删除自己', data=None), 400

    db.session.delete(user)
    db.session.commit()
    return jsonify(code=200, msg='用户已删除', data=None), 200


@users_bp.route('/api/users/<int:user_id>/reset-password', methods=['PUT'])
@jwt_required()
@permission_required('user_manage')
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(code=404, msg='用户不存在', data=None), 404

    new_password = '123456'
    user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()
    return jsonify(code=200, msg=f'密码已重置为 {new_password}', data=None), 200
