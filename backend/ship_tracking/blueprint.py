"""发货梯号追踪 - API 蓝图。"""
import os
import tempfile
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_current_user, jwt_required

from decorators import permission_required
from ship_tracking import PERMISSION
from ship_tracking import importer as imp
from ship_tracking import services as svc
from ship_tracking.models import ImportBatch, ImportIssue
from ship_tracking.excel_reader import parse_excel_date

st_bp = Blueprint('ship_tracking', __name__)


def _ok(data=None, msg='success'):
    return jsonify(code=200, msg=msg, data=data), 200


def _fail(msg, code=400, data=None):
    return jsonify(code=code, msg=msg, data=data), code


def _payload():
    return request.get_json(silent=True) or {}


def _filter_args():
    # 前端多选时把多个状态用逗号拼在同一个参数里，这里统一拆开，
    # 否则 getlist 会返回 ['committed,overdue'] 导致一条都匹配不上。
    raw_statuses = request.args.getlist('statuses') + request.args.getlist('status')
    statuses = [
        item.strip()
        for value in raw_statuses
        for item in (value or '').split(',')
        if item.strip()
    ]
    return {
        'keyword': request.args.get('keyword') or '',
        'month': request.args.get('month') or '',
        'module': request.args.get('module') or '',
        'region': request.args.get('region') or '',
        'booking_status': request.args.get('booking_status') or '',
        'actual_ship_source': request.args.get('actual_ship_source') or '',
        'payment_ratio': request.args.get('payment_ratio') or '',
        'statuses': statuses,
        'include_removed': request.args.get('include_removed') or '',
        'expected_start': request.args.get('expected_start') or '',
        'expected_end': request.args.get('expected_end') or '',
        'actual_start': request.args.get('actual_start') or '',
        'actual_end': request.args.get('actual_end') or '',
        'page': request.args.get('page') or 1,
        'page_size': request.args.get('page_size') or 50,
    }


def _save_upload(upload):
    suffix = os.path.splitext(upload.filename or '')[1] or '.xlsx'
    handle, path = tempfile.mkstemp(prefix='st_import_', suffix=suffix)
    os.close(handle)
    upload.save(path)
    return path


@st_bp.route('/api/ship-tracking/context', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_context():
    try:
        user = get_current_user()
        return _ok(svc.build_context(user))
    except Exception as exc:
        return _fail('加载上下文失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/weekly', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_weekly():
    try:
        user = get_current_user()
        data = svc.get_weekly(
            user,
            module_name=request.args.get('module') or '',
            include_future=(request.args.get('include_future') or '') in ('1', 'true', 'True'),
            keyword=request.args.get('q') or '',
        )
        return _ok(data)
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 403 if '权限' in str(exc) or '归属' in str(exc) else 400)
    except Exception as exc:
        return _fail('读取填报数据失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/weekly/draft', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_weekly_draft():
    try:
        user = get_current_user()
        payload = _payload()
        return _ok(svc.save_weekly_draft(
            user,
            payload.get('module_name') or payload.get('module') or '',
            payload.get('items') or [],
            target_week=payload.get('target_week_start') or svc.target_week_start(),
        ), '草稿已保存')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('保存失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/weekly/submit', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_weekly_submit():
    try:
        user = get_current_user()
        payload = _payload()
        return _ok(svc.submit_weekly(
            user,
            payload.get('module_name') or payload.get('module') or '',
            payload.get('items') or [],
            target_week=payload.get('target_week_start') or svc.target_week_start(),
        ), '已提交发货计划')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('提交失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/weekly/withdraw', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_weekly_withdraw():
    try:
        user = get_current_user()
        payload = _payload()
        return _ok(svc.withdraw_weekly(
            user,
            payload.get('module_name') or payload.get('module') or '',
            payload.get('ladder_keys') or [],
        ), '已撤回')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('撤回失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/weekly/adjust', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_weekly_adjust():
    try:
        user = get_current_user()
        payload = _payload()
        return _ok(svc.adjust_weekly(
            user,
            payload.get('module_name') or payload.get('module') or '',
            payload.get('items') or [],
        ), '发货日期已调整')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('调整失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/weekly/manual', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_weekly_manual():
    try:
        return _ok(
            svc.add_weekly_ladder(get_current_user(), _payload()),
            '梯号已加入发货明细',
        )
    except svc.ManualAddConflict as exc:
        return _fail(str(exc), 409, dict(exc.data, code=exc.code))
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('添加失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/weekly/remark', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_weekly_remark():
    try:
        payload = _payload()
        return _ok(
            svc.save_weekly_remark(
                get_current_user(),
                payload.get('module_name') or payload.get('module') or '',
                payload.get('ladder_key') or payload.get('ladder_no') or '',
                payload.get('remark') or '',
            ),
            '备注已保存',
        )
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('保存备注失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/weekly/remarks', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_weekly_remarks():
    try:
        payload = _payload()
        return _ok(
            svc.save_weekly_remarks(
                get_current_user(),
                payload.get('module_name') or payload.get('module') or '',
                payload.get('ladder_keys') or [],
                payload.get('remark') or '',
            ),
            '备注已批量保存',
        )
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('批量保存备注失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/items', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_items():
    try:
        user = get_current_user()
        return _ok(svc.query_tracking(user, _filter_args()))
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except Exception as exc:
        return _fail('读取发货明细失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/history', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_history():
    try:
        user = get_current_user()
        return _ok(svc.get_history(user, request.args.get('ladder_key') or ''))
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('读取历史失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/daily', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_daily():
    try:
        user = get_current_user()
        payload = _payload()
        result = svc.record_daily_shipments(
            user,
            payload.get('items') or [],
            reason=payload.get('reason') or '',
        )
        return _ok(result, '实发已保存')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('实发保存失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/daily/external/preview', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_daily_external_preview():
    try:
        user = get_current_user()
        payload = _payload()
        result = svc.preview_external_ladders(
            user,
            payload.get('ladder_no') or '',
            payload.get('contract_no') or '',
        )
        return _ok(result, '梯号识别完成')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('识别梯号失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/daily/delete', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_daily_delete():
    try:
        user = get_current_user()
        payload = _payload()
        result = svc.delete_daily_shipments(
            user,
            payload.get('ladder_keys') or [],
        )
        return _ok(result, '实发已删除')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('删除实发失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/unlock', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_unlock():
    try:
        user = get_current_user()
        payload = _payload()
        return _ok(svc.unlock(
            user,
            payload.get('type') or '',
            payload.get('ladder_keys') or [],
            payload.get('reason') or '',
        ), '已解锁')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('解锁失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/import/plan/preview', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_plan_preview():
    path = None
    try:
        user = get_current_user()
        if 'file' not in request.files:
            return _fail('未选择文件')
        upload = request.files['file']
        if not upload.filename:
            return _fail('文件名为空')
        if not upload.filename.lower().endswith(('.xlsx', '.xls')):
            return _fail('仅支持 .xlsx / .xls')
        path = _save_upload(upload)
        return _ok(imp.preview_plan_import(
            path, upload.filename,
            request.form.get('plan_month') or '',
            user,
        ), '计划文件已解析，请核对差异后提交')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except imp.PlanHeaderError as exc:
        return _fail(str(exc), 400, exc.details)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('计划预览失败: %s' % exc, 500)
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@st_bp.route('/api/ship-tracking/import/plan/commit', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_plan_commit():
    try:
        user = get_current_user()
        payload = _payload()
        return _ok(imp.commit_plan_import(
            int(payload.get('batch_id')),
            user,
            force=bool(payload.get('force')),
            overwrite_expected=bool(payload.get('overwrite_expected')),
            overwrite_remark=bool(payload.get('overwrite_remark')),
        ), '月度计划已生成新版本')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except (TypeError, ValueError) as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('计划提交失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/import/plan/from-forecast/preview', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_plan_from_forecast_preview():
    try:
        return _ok(
            imp.preview_plan_from_forecast(_payload().get('month'), get_current_user()),
            '单月填报已解析，请核对后提交',
        )
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('单月填报预览失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/import/plan/from-forecast/commit', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_plan_from_forecast_commit():
    try:
        payload = _payload()
        return _ok(
            imp.commit_forecast_import(int(payload.get('batch_id')), get_current_user()),
            '单月填报梯号已并入发货明细',
        )
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except (TypeError, ValueError) as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('单月填报提交失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/import/booking/preview', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_booking_preview():
    path = None
    try:
        user = get_current_user()
        if 'file' not in request.files:
            return _fail('未选择文件')
        upload = request.files['file']
        if not upload.filename:
            return _fail('文件名为空')
        if not upload.filename.lower().endswith(('.xlsx', '.xls')):
            return _fail('仅支持 .xlsx / .xls')
        path = _save_upload(upload)
        return _ok(imp.preview_booking_import(path, upload.filename, user),
                   '订舱文件已解析，请核对匹配结果后提交')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('订舱预览失败: %s' % exc, 500)
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@st_bp.route('/api/ship-tracking/import/booking/commit', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_booking_commit():
    try:
        user = get_current_user()
        payload = _payload()
        return _ok(imp.commit_booking_import(
            int(payload.get('batch_id')),
            user,
            force=bool(payload.get('force')),
        ), '订舱状态已更新')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except (TypeError, ValueError) as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('订舱提交失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/imports', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_imports():
    try:
        user = get_current_user()
        if not svc.can_import(user):
            return _fail('无导入管理权限', 403)
        data_type = request.args.get('data_type') or ''
        include_preview = (request.args.get('include_preview') or '') in ('1', 'true', 'True')
        query = ImportBatch.query
        if data_type:
            query = query.filter_by(data_type=data_type)
        if not include_preview:
            query = query.filter(ImportBatch.status != 'preview')
        rows = query.order_by(ImportBatch.id.desc()).limit(100).all()
        return _ok([row.to_dict() for row in rows])
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except Exception as exc:
        return _fail('读取导入批次失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/imports/preview', methods=['DELETE'])
@jwt_required()
@permission_required(PERMISSION)
def api_cleanup_preview_batches():
    try:
        data_type = request.args.get('data_type') or ''
        return _ok(imp.cleanup_preview_batches(get_current_user(), data_type), '预览批次已清理')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except Exception as exc:
        return _fail('清理预览批次失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/imports/<int:batch_id>', methods=['DELETE'])
@jwt_required()
@permission_required(PERMISSION)
def api_delete_import_batch(batch_id):
    try:
        return _ok(imp.delete_import_batch(batch_id, get_current_user()), '预览批次已删除')
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('删除预览批次失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/imports/<int:batch_id>/issues', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_import_issues(batch_id):
    try:
        user = get_current_user()
        if not svc.can_import(user):
            return _fail('无导入管理权限', 403)
        batch = ImportBatch.query.get(batch_id)
        if not batch:
            return _fail('批次不存在', 404)
        rows = ImportIssue.query.filter_by(batch_id=batch_id).order_by(ImportIssue.id).limit(2000).all()
        return _ok({'batch': batch.to_dict(), 'issues': [row.to_dict() for row in rows]})
    except Exception as exc:
        return _fail('读取导入异常失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/export', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_export():
    try:
        user = get_current_user()
        filters = _filter_args()
        filters['page_size'] = 'all'
        output = svc.export_tracking(user, filters)
        filename = '%s_发货梯号明细.xlsx' % (request.args.get('month') or svc.default_month())
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except PermissionError as exc:
        return _fail(str(exc), 403)
    except Exception as exc:
        return _fail('导出失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/sync', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_sync():
    try:
        user = get_current_user()
        if not svc.can_import(user):
            return _fail('无同步管理权限', 403)
        from ship_tracking import sync as st_sync
        result = st_sync.sync_tracking_dates(user, source='manual')
        try:
            from ship_tracking.payment_service import maybe_auto_calc
            result['payment_calc'] = maybe_auto_calc(user, trigger='auto:manual_sync')
        except Exception as exc:
            result['payment_calc'] = {'started': False, 'message': str(exc)}
        return _ok(result)
    except Exception as exc:
        return _fail('台账字段同步失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/sync/status', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_sync_status():
    try:
        user = get_current_user()
        if not svc.can_import(user):
            return _fail('无同步管理权限', 403)
        from ship_tracking import sync as st_sync
        return _ok(st_sync.get_sync_status())
    except Exception as exc:
        return _fail('读取同步状态失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/import/template', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_template():
    kind = request.args.get('type') or 'plan'
    if kind == 'booking':
        output = svc.make_booking_template()
        filename = '订舱申请流程报表_导入模板.xlsx'
    else:
        output = svc.make_plan_template()
        filename = '预计发货合同梯号明细_导入模板.xlsx'
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


# ── 回款比例计算 ──────────────────────────────────────────────

@st_bp.route('/api/ship-tracking/payment/status', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_payment_status():
    try:
        from ship_tracking import payment_service as pay_svc
        return _ok(pay_svc.get_payment_status())
    except Exception as exc:
        return _fail('读取回款计算状态失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/payment/files/<file_type>', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_payment_upload(file_type):
    try:
        from ship_tracking import payment_service as pay_svc
        upload = request.files.get('file')
        if upload is None:
            return _fail('请选择要上传的文件')
        record = pay_svc.save_payment_file(file_type, upload, get_current_user())
        return _ok(record.to_dict(), '上传成功，文件校验通过')
    except ValueError as exc:
        return _fail(str(exc), 400)
    except Exception as exc:
        return _fail('回款文件上传失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/payment/calculate', methods=['POST'])
@jwt_required()
@permission_required(PERMISSION)
def api_payment_calculate():
    try:
        from ship_tracking import payment_service as pay_svc
        payload = _payload()
        background = payload.get('background', True)
        data = pay_svc.start_payment_calc(
            get_current_user(),
            trigger=payload.get('trigger') or 'manual',
            background=bool(background),
        )
        return _ok(data, data.get('message') or '计算已开始')
    except Exception as exc:
        return _fail('启动回款计算失败: %s' % exc, 500)


@st_bp.route('/api/ship-tracking/payment/report', methods=['GET'])
@jwt_required()
@permission_required(PERMISSION)
def api_payment_report():
    try:
        from ship_tracking import payment_service as pay_svc
        run_id = request.args.get('run_id', type=int)
        output, run = pay_svc.build_payment_report(run_id)
        filename = '回款计算审计_%s.xlsx' % (run.id if run else datetime.now().strftime('%Y%m%d%H%M%S'))
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except ValueError as exc:
        return _fail(str(exc), 404)
    except Exception as exc:
        return _fail('下载回款审计失败: %s' % exc, 500)
