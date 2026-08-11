import os
import re
import time
import subprocess
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_current_user
from models import db, UploadConfig, FileUpload, OperationLog
from upload.handlers import HANDLERS

upload_bp = Blueprint('upload', __name__)


def _safe_name(filename):
    """保留中文和正常字符，只移除路径分隔符和空字符"""
    if not filename:
        return 'unnamed'
    name = filename.replace('\\', '_').replace('/', '_')
    name = re.sub(r'[\x00-\x1f]', '', name)
    name = name.lstrip('.')
    return name.strip() or 'unnamed'


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

    # 权限检查：子项继承父级权限
    user = get_current_user()
    perm_to_check = config.parent.permission if config.parent_id and config.parent else config.permission
    if not user or not user.role or perm_to_check not in user.role.get_permissions():
        return jsonify(code=403, msg='无上传权限', data=None), 403

    if 'file' not in request.files:
        return jsonify(code=400, msg='未选择文件', data=None), 400

    file = request.files['file']
    if not file.filename:
        return jsonify(code=400, msg='文件名为空', data=None), 400

    # 保存文件：uploads/<parent_code>/<child_code>/<filename>
    parent_code = config.parent.code if config.parent_id and config.parent else code
    child_code = code
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], parent_code, child_code)
    os.makedirs(upload_dir, exist_ok=True)

    # 清空该子项目录下的所有旧文件，确保只保留最新上传的一个文件
    failed = []
    for old_file in os.listdir(upload_dir):
        old_path = os.path.join(upload_dir, old_file)
        if os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except PermissionError:
                failed.append(old_file)
    if failed:
        return jsonify(code=409, msg=f'以下文件被占用无法删除，请关闭后重试: {", ".join(failed)}'), 409

    original_filename = _safe_name(file.filename)
    saved_path = os.path.join(upload_dir, original_filename)
    file.save(saved_path)

    file_size = os.path.getsize(saved_path)

    # 创建上传记录
    record = FileUpload(
        filename=original_filename,
        stored_path=saved_path,
        file_size=file_size,
        upload_config_id=config.id,
        user_id=user.id,
        status='stored',
        message='文件已保存',
        ip_address=request.remote_addr or '',
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
            if result.get('success'):
                try:
                    from dashboards.contract_completion.services import invalidate_two_year_cache
                    invalidate_two_year_cache()
                except Exception:
                    pass
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


@upload_bp.route('/api/generate-dashboard/<parent_code>', methods=['POST'])
@jwt_required()
def generate_dashboard(parent_code):
    """触发看板生成：收集子项文件 → subprocess 调脚本 → 输出 HTML"""
    user = get_current_user()

    parent = UploadConfig.query.filter_by(code=parent_code, is_active=True).first()
    if not parent:
        return jsonify(code=404, msg=f'上传配置不存在: {parent_code}', data=None), 404
    if not parent.handler_script:
        return jsonify(code=400, msg='该看板未配置生成脚本', data=None), 400

    # 权限检查
    if not user or not user.role or parent.permission not in user.role.get_permissions():
        return jsonify(code=403, msg='无权限', data=None), 403

    children = UploadConfig.query.filter_by(parent_id=parent.id, is_active=True).order_by(UploadConfig.sort_order, UploadConfig.id).all()
    if not children:
        return jsonify(code=400, msg='没有子上传项', data=None), 400

    # ── generate_data: 直接从 JSON/DB 生成（不走文件收集，预算优先读 JSON）──
    if parent_code == 'generate_data':
        month = (request.json or {}).get('month', '')
        if not month:
            from datetime import date
            month = date.today().strftime('%Y-%m')

        # generate_report_v3 内部有裸导入，需要 generate_dashboard 目录在 sys.path
        import sys
        _gen_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dashboards', 'generate_dashboard')
        if _gen_dir not in sys.path:
            sys.path.insert(0, _gen_dir)

        from dashboards.generate_dashboard.generate_report_v3 import (
            generate_report, generate_dashboard_html, build_forecast_from_json
        )

        # 记录操作日志
        log = OperationLog(
            user_id=user.id,
            username=user.username,
            ip_address=request.remote_addr or '',
            action_type='generate_dashboard',
            target_name=parent.name,
            result='success',
            message='',
        )

        base = os.path.dirname(os.path.dirname(__file__))
        script_dir = os.path.join(base, parent.script_dir or 'dashboards/generate_dashboard')
        output_path = os.path.join(os.path.dirname(script_dir), f'{parent_code}_dashboard.html')

        budget_file = None
        try:
            build_forecast_from_json()
            current_app.logger.info(f'[generate_dashboard] 使用预算JSON: {month}')
        except FileNotFoundError:
            # JSON 不存在，回退到上传文件
            upload_base = current_app.config['UPLOAD_FOLDER']
            file_map = {}
            for child in children:
                child_dir = os.path.join(upload_base, parent_code, child.code)
                if os.path.isdir(child_dir):
                    files = sorted(
                        [f for f in os.listdir(child_dir) if os.path.isfile(os.path.join(child_dir, f)) and not f.startswith('~$')],
                        key=lambda f: os.path.getmtime(os.path.join(child_dir, f)), reverse=True
                    )
                    if files:
                        file_map[child.code] = os.path.join(child_dir, files[0])

            budget_file = file_map.get('generate_data_budget')
            if not budget_file:
                log.result = 'error'
                log.message = '缺少预算数据。请先运行 import_budget.py 导入月度预算表，或上传预算Excel文件。'
                db.session.add(log)
                db.session.commit()
                return jsonify(code=400, msg=log.message, data=None), 400

        try:
            excel_output = os.path.join(script_dir, f'签单排产发货_{month[5:]}.xlsx')
            result = generate_report(month, budget_file, excel_output)
            if not result['success']:
                log.result = 'error'
                log.message = result['message']
                db.session.add(log)
                db.session.commit()
                return jsonify(code=500, msg=result['message'], data=None), 500

            html_result = generate_dashboard_html(month, result['excel_path'], output_path)
            if not html_result['success']:
                log.result = 'error'
                log.message = html_result['message']
                db.session.add(log)
                db.session.commit()
                return jsonify(code=500, msg=html_result['message'], data=None), 500

            log.message = '看板生成成功'
            db.session.add(log)
            db.session.commit()

            return jsonify(code=200, msg='看板生成成功', data={
                'dashboard_url': f'/dashboards/{parent_code}_dashboard.html',
                'module_id': parent.dashboard_module_id,
            }), 200

        except Exception as e:
            log.result = 'error'
            log.message = str(e)
            current_app.logger.error(f'[generate_dashboard] v3 异常: {log.message}')
            db.session.add(log)
            db.session.commit()
            return jsonify(code=500, msg=log.message, data=None), 500

    # ── 其他看板：收集子项文件 → 调用脚本 ──
    upload_base = current_app.config['UPLOAD_FOLDER']
    file_args = []
    missing = []
    for child in children:
        child_dir = os.path.join(upload_base, parent_code, child.code)
        file_path = None
        if os.path.isdir(child_dir):
            files = sorted(
                [f for f in os.listdir(child_dir)
                 if os.path.isfile(os.path.join(child_dir, f))
                 and not f.startswith('~$')],
                key=lambda f: os.path.getmtime(os.path.join(child_dir, f)),
                reverse=True
            )
            if files:
                file_path = os.path.join(child_dir, files[0])
        if file_path and os.path.isfile(file_path):
            file_args.extend([f'--{child.code}', file_path])
        else:
            missing.append(child.name)

    if missing:
        return jsonify(code=400, msg=f'缺少文件: {", ".join(missing)}', data=None), 400

    # 记录操作日志
    log = OperationLog(
        user_id=user.id,
        username=user.username,
        ip_address=request.remote_addr or '',
        action_type='generate_dashboard',
        target_name=parent.name,
        result='success',
        message='',
    )

    base = os.path.dirname(os.path.dirname(__file__))
    script_dir = os.path.join(base, parent.script_dir or 'dashboards/generate_dashboard')
    output_path = os.path.join(os.path.dirname(script_dir), f'{parent_code}_dashboard.html')

    # ── schedule_dashboard: 直接调用 Python 函数 ──
    if parent_code == 'schedule_dashboard':
        try:
            from dashboards.Project_Schedule.scripts.generate_schedule_dashboard_v2 import generate_schedule_dashboard

            result = generate_schedule_dashboard(output_path)
            if not result['success']:
                log.result = 'error'
                log.message = result['message']
                db.session.add(log)
                db.session.commit()
                return jsonify(code=500, msg=result['message'], data=None), 500

            log.message = '工期看板生成成功'
            db.session.add(log)
            db.session.commit()

            return jsonify(code=200, msg='看板生成成功', data={
                'dashboard_url': f'/dashboards/{parent_code}_dashboard.html',
                'module_id': parent.dashboard_module_id,
            }), 200

        except Exception as e:
            log.result = 'error'
            log.message = str(e)
            current_app.logger.error(f'[schedule_dashboard] v2 异常: {log.message}')
            db.session.add(log)
            db.session.commit()
            return jsonify(code=500, msg=log.message, data=None), 500

    # ── 其他看板: 保持原有 subprocess 方式 ──
    script_path = os.path.join(script_dir, parent.handler_script)

    if not os.path.isfile(script_path):
        log.result = 'error'
        log.message = f'脚本不存在: {parent.handler_script}'
        db.session.add(log)
        db.session.commit()
        return jsonify(code=500, msg=log.message, data=None), 500

    try:
        result = subprocess.run(
            ['py', '-3.11', script_path, '--output', output_path] + file_args,
            capture_output=True, text=True, timeout=300, cwd=script_dir
        )
        if result.returncode != 0:
            log.result = 'error'
            log.message = result.stderr or result.stdout or '脚本执行失败'
            current_app.logger.error(f'[generate_dashboard] 脚本返回非零: {log.message}')
            db.session.add(log)
            db.session.commit()
            return jsonify(code=500, msg=log.message, data=None), 500
    except subprocess.TimeoutExpired:
        log.result = 'error'
        log.message = '脚本执行超时（5分钟）'
        current_app.logger.error(f'[generate_dashboard] 脚本执行超时')
        db.session.add(log)
        db.session.commit()
        return jsonify(code=500, msg=log.message, data=None), 500
    except Exception as e:
        log.result = 'error'
        log.message = str(e)
        current_app.logger.error(f'[generate_dashboard] 异常: {log.message}')
        db.session.add(log)
        db.session.commit()
        return jsonify(code=500, msg=log.message, data=None), 500

    log.message = result.stdout or '看板生成成功'
    db.session.add(log)
    db.session.commit()

    dashboard_url = f'/dashboards/{parent_code}_dashboard.html'
    return jsonify(code=200, msg='看板生成成功', data={
        'dashboard_url': dashboard_url,
        'module_id': parent.dashboard_module_id,
        'output': result.stdout,
    }), 200
