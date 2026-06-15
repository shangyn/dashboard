from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required, get_current_user,
)
from flask_bcrypt import Bcrypt
from models import db, User, Role

auth_bp = Blueprint('auth', __name__)
bcrypt = Bcrypt()


@auth_bp.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify(code=400, msg='工号和密码不能为空', data=None), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify(code=401, msg='工号或密码错误', data=None), 401

    if not user.is_active:
        return jsonify(code=403, msg='账号已被禁用，请联系管理员', data=None), 403

    if not bcrypt.check_password_hash(user.password, password):
        return jsonify(code=401, msg='工号或密码错误', data=None), 401

    token = create_access_token(identity=str(user.id))

    user_dict = user.to_dict()
    role_data = None
    if user.role:
        role_data = user.role.to_dict()

    return jsonify(code=200, msg='登录成功', data={
        'token': token,
        'user': {
            **user_dict,
            'role': role_data,
        }
    }), 200


@auth_bp.route('/api/current-user', methods=['GET'])
@jwt_required()
def current_user():
    user = get_current_user()
    if not user:
        return jsonify(code=404, msg='用户不存在', data=None), 404

    role_data = user.role.to_dict() if user.role else None

    return jsonify(code=200, msg='success', data={
        **user.to_dict(),
        'role': role_data,
    }), 200


@auth_bp.route('/api/change-password', methods=['PUT'])
@jwt_required()
def change_password():
    user = get_current_user()
    data = request.get_json()
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return jsonify(code=400, msg='旧密码和新密码不能为空', data=None), 400

    if not bcrypt.check_password_hash(user.password, old_password):
        return jsonify(code=400, msg='旧密码错误', data=None), 400

    if len(new_password) < 6:
        return jsonify(code=400, msg='新密码长度不能少于6位', data=None), 400

    user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()

    return jsonify(code=200, msg='密码修改成功', data=None), 200
