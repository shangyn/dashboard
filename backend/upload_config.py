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
        parent_id=data.get('parent_id') or None,
        handler_script=data.get('handler_script', ''),
        script_dir=data.get('script_dir', 'dashboards/generate_dashboard'),
        dashboard_module_id=data.get('dashboard_module_id') or None,
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
    for field in ['name', 'description', 'code', 'permission', 'file_types', 'required_columns', 'sort_order', 'is_active', 'parent_id', 'handler_script', 'dashboard_module_id', 'script_dir']:
        if field in data:
            value = data[field]
            if field == 'code' and value != config.code:
                if UploadConfig.query.filter_by(code=value).first():
                    return jsonify(code=400, msg=f'code {value} 已存在', data=None), 400
            if field == 'parent_id' and (value is None or value == '' or value == 0):
                value = None
            if field == 'dashboard_module_id' and (value is None or value == '' or value == 0):
                value = None
            setattr(config, field, value)

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
    """返回当前用户可用的上传配置（树形结构，父级嵌套子项）"""
    user = get_current_user()
    if not user or not user.role:
        return jsonify(code=200, msg='success', data=[]), 200

    permissions = user.role.get_permissions()

    # 一次性加载所有活跃配置
    all_configs = UploadConfig.query.filter(
        UploadConfig.is_active == True
    ).order_by(UploadConfig.sort_order, UploadConfig.id).all()

    # 按权限过滤：子项查父级权限，顶层查自身权限
    by_id = {c.id: c for c in all_configs}
    roots = []
    for c in all_configs:
        if c.parent_id:
            parent = by_id.get(c.parent_id)
            if parent and parent.permission not in permissions:
                continue  # 父级无权限，跳过该子项
        else:
            if c.permission not in permissions:
                continue  # 顶层且自身无权限，跳过

        if c.parent_id is None:
            roots.append(c)

    # 手动构建树：to_dict 不再递归，这里按需嵌套 children
    def build_node(config):
        d = config.to_dict()
        # 仅包含通过权限过滤的活跃子项
        active_children = [c for c in config.children if c.is_active and c.id in by_id]
        d['children'] = [build_node(c) for c in active_children]
        return d

    return jsonify(code=200, msg='success', data=[build_node(r) for r in roots]), 200


@upload_config_bp.route('/api/upload-file-times/<int:parent_id>', methods=['GET'])
@jwt_required()
def upload_file_times(parent_id):
    """返回父级下每个子项的最新上传时间"""
    parent = db.session.get(UploadConfig, parent_id)
    if not parent:
        return jsonify(code=404, msg='上传配置不存在', data=None), 404

    from models import FileUpload
    children = UploadConfig.query.filter_by(parent_id=parent_id, is_active=True).order_by(UploadConfig.sort_order, UploadConfig.id).all()

    times = []
    for child in children:
        last_upload = FileUpload.query.filter_by(upload_config_id=child.id).order_by(FileUpload.uploaded_at.desc()).first()
        times.append({
            'id': child.id,
            'name': child.name,
            'code': child.code,
            'last_upload': last_upload.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if last_upload else None,
        })

    return jsonify(code=200, msg='success', data={'children': times}), 200
