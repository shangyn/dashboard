from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_current_user
from models import db, UploadConfig
from decorators import permission_required

upload_config_bp = Blueprint('upload_config', __name__)


@upload_config_bp.route('/api/upload-configs', methods=['GET'])
@jwt_required()
@permission_required('upload_manage')
def get_upload_configs():
    configs = UploadConfig.query.order_by(UploadConfig.sort_order, UploadConfig.id).all()
    return jsonify(code=200, msg='success', data=[c.to_dict() for c in configs]), 200


@upload_config_bp.route('/api/upload-configs', methods=['POST'])
@jwt_required()
@permission_required('upload_manage')
def create_upload_config():
    data = request.get_json()
    config = UploadConfig(
        name=data.get('name', ''),
        description=data.get('description', ''),
        code=data.get('code', ''),
        permission=data.get('permission', ''),
        file_types=data.get('file_types', '.xlsx,.xls'),
        required_columns=data.get('required_columns', ''),
        sort_order=data.get('sort_order', 0),
        is_active=data.get('is_active', True),
    )
    if not config.name or not config.code or not config.permission:
        return jsonify(code=400, msg='名称、code、权限标识不能为空', data=None), 400

    if UploadConfig.query.filter_by(code=config.code).first():
        return jsonify(code=400, msg=f'code {config.code} 已存在', data=None), 400

    db.session.add(config)
    db.session.commit()
    return jsonify(code=200, msg='上传配置创建成功', data=config.to_dict()), 200


@upload_config_bp.route('/api/upload-configs/<int:config_id>', methods=['PUT'])
@jwt_required()
@permission_required('upload_manage')
def update_upload_config(config_id):
    config = db.session.get(UploadConfig, config_id)
    if not config:
        return jsonify(code=404, msg='上传配置不存在', data=None), 404

    data = request.get_json()
    for field in ['name', 'description', 'code', 'permission', 'file_types', 'required_columns', 'sort_order', 'is_active']:
        if field in data:
            if field == 'code' and data[field] != config.code:
                if UploadConfig.query.filter_by(code=data[field]).first():
                    return jsonify(code=400, msg=f'code {data[field]} 已存在', data=None), 400
            setattr(config, field, data[field])

    db.session.commit()
    return jsonify(code=200, msg='上传配置已更新', data=config.to_dict()), 200


@upload_config_bp.route('/api/upload-configs/<int:config_id>', methods=['DELETE'])
@jwt_required()
@permission_required('upload_manage')
def delete_upload_config(config_id):
    config = db.session.get(UploadConfig, config_id)
    if not config:
        return jsonify(code=404, msg='上传配置不存在', data=None), 404
    db.session.delete(config)
    db.session.commit()
    return jsonify(code=200, msg='上传配置已删除', data=None), 200


@upload_config_bp.route('/api/my-upload-configs', methods=['GET'])
@jwt_required()
def my_upload_configs():
    """返回当前用户可用的上传配置列表（根据权限过滤）"""
    user = get_current_user()
    if not user or not user.role:
        return jsonify(code=200, msg='success', data=[]), 200

    permissions = user.role.get_permissions()
    configs = UploadConfig.query.filter(
        UploadConfig.is_active == True,
        UploadConfig.permission.in_(permissions)
    ).order_by(UploadConfig.sort_order, UploadConfig.id).all()

    return jsonify(code=200, msg='success', data=[c.to_dict() for c in configs]), 200
