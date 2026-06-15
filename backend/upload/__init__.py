import os
import time
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_current_user
from werkzeug.utils import secure_filename
from models import db, UploadConfig, FileUpload
from upload.handlers import HANDLERS

upload_bp = Blueprint('upload', __name__)


def get_db_size():
    """获取 SQLite 数据库文件大小（MB）"""
    db_path = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if db_path.startswith('sqlite:///'):
        db_file = db_path.replace('sqlite:///', '')
        if os.path.isfile(db_file):
            return round(os.path.getsize(db_file) / (1024 * 1024), 2)
    return 0


@upload_bp.route('/api/upload/<code>', methods=['POST'])
@jwt_required()
def upload_file(code):
    """文件上传端点 — 根据 code 匹配 upload_config"""
    config = UploadConfig.query.filter_by(code=code, is_active=True).first()
    if not config:
        return jsonify(code=404, msg=f'上传配置不存在: {code}', data=None), 404

    # 权限检查
    user = get_current_user()
    if not user or not user.role or config.permission not in user.role.get_permissions():
        return jsonify(code=403, msg='无上传权限', data=None), 403

    if 'file' not in request.files:
        return jsonify(code=400, msg='未选择文件', data=None), 400

    file = request.files['file']
    if not file.filename:
        return jsonify(code=400, msg='文件名为空', data=None), 400

    # 保存文件
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], code)
    os.makedirs(upload_dir, exist_ok=True)

    original_filename = secure_filename(file.filename)
    timestamp = int(time.time())
    saved_filename = f'{timestamp}_{original_filename}'
    saved_path = os.path.join(upload_dir, saved_filename)
    file.save(saved_path)

    file_size = os.path.getsize(saved_path)

    # 创建上传记录
    record = FileUpload(
        filename=original_filename,
        stored_path=saved_path,
        file_size=file_size,
        upload_config_id=config.id,
        user_id=user.id,
        status='uploading',
        message='',
    )
    db.session.add(record)
    db.session.commit()

    # 查找并调用 handler
    handler = HANDLERS.get(code)
    if handler:
        try:
            result = handler(saved_path)
            record.status = 'parsed' if result.get('success') else 'error'
            record.message = result.get('message', '')
        except Exception as e:
            record.status = 'error'
            record.message = f'解析失败: {str(e)}'
    else:
        record.status = 'stored'
        record.message = '文件已保存，暂不支持自动解析'

    db.session.commit()

    return jsonify(code=200, msg='上传完成', data=record.to_dict()), 200


@upload_bp.route('/api/upload-history', methods=['GET'])
@jwt_required()
def upload_history():
    """当前用户的文件上传历史"""
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    pagination = FileUpload.query.filter_by(user_id=user.id) \
        .order_by(FileUpload.uploaded_at.desc()) \
        .paginate(page=page, per_page=page_size, error_out=False)

    return jsonify(code=200, msg='success', data={
        'items': [r.to_dict() for r in pagination.items],
        'total': pagination.total,
    }), 200


@upload_bp.route('/api/upload-stats', methods=['GET'])
@jwt_required()
def upload_stats():
    """上传统计数据"""
    user = get_current_user()
    upload_count = FileUpload.query.filter_by(user_id=user.id).count()
    parsed_count = FileUpload.query.filter_by(user_id=user.id, status='parsed').count()
    db_size = get_db_size()

    return jsonify(code=200, msg='success', data={
        'upload_count': upload_count,
        'parsed_count': parsed_count,
        'db_size_mb': db_size,
    }), 200
