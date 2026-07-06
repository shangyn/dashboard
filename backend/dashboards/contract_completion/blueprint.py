"""
合同完成情况表 — API Blueprint
"""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required
from dashboards.contract_completion.services import (
    get_region_summary,
    get_module_detail,
    get_salesperson_comparison,
    get_data_status,
    get_unmatched_contracts,
    get_regions,
    get_two_year_comparison,
    export_two_year_comparison_xlsx,
)

cc_bp = Blueprint('contract_completion', __name__)


@cc_bp.route('/api/contract-completion/region-summary', methods=['GET'])
@jwt_required()
def api_region_summary():
    """Sheet 1: 大区汇总"""
    year = request.args.get('year', 2026, type=int)
    region = request.args.get('region', None)
    try:
        data = get_region_summary(year=year, region_filter=region)
        return jsonify(code=200, msg='success', data=data), 200
    except Exception as e:
        return jsonify(code=500, msg=str(e), data=None), 500


@cc_bp.route('/api/contract-completion/module-detail', methods=['GET'])
@jwt_required()
def api_module_detail():
    """Sheet 2: 模块明细"""
    year = request.args.get('year', 2026, type=int)
    region = request.args.get('region', None)
    try:
        data = get_module_detail(year=year, region_filter=region)
        return jsonify(code=200, msg='success', data=data), 200
    except Exception as e:
        return jsonify(code=500, msg=str(e), data=None), 500


@cc_bp.route('/api/contract-completion/salesperson', methods=['GET'])
@jwt_required()
def api_salesperson():
    """Sheet 3: 业务员表"""
    year = request.args.get('year', 2026, type=int)
    region = request.args.get('region', None)
    try:
        data = get_salesperson_comparison(year=year, region_filter=region)
        return jsonify(code=200, msg='success', data=data), 200
    except Exception as e:
        return jsonify(code=500, msg=str(e), data=None), 500


@cc_bp.route('/api/contract-completion/data-status', methods=['GET'])
@jwt_required()
def api_data_status():
    """数据状态"""
    try:
        data = get_data_status()
        return jsonify(code=200, msg='success', data=data), 200
    except Exception as e:
        return jsonify(code=500, msg=str(e), data=None), 500


@cc_bp.route('/api/contract-completion/unmatched-contracts', methods=['GET'])
@jwt_required()
def api_unmatched():
    """未匹配合同列表"""
    try:
        data = get_unmatched_contracts()
        return jsonify(code=200, msg='success', data=data), 200
    except Exception as e:
        return jsonify(code=500, msg=str(e), data=None), 500


@cc_bp.route('/api/contract-completion/regions', methods=['GET'])
@jwt_required()
def api_regions():
    """可用大区列表"""
    try:
        data = get_regions()
        return jsonify(code=200, msg='success', data=data), 200
    except Exception as e:
        return jsonify(code=500, msg=str(e), data=None), 500


@cc_bp.route('/api/contract-completion/two-year-comparison', methods=['GET'])
@jwt_required()
def api_two_year_comparison():
    """两年对比表（无需参数，日期自动取当日）"""
    try:
        data = get_two_year_comparison()
        return jsonify(code=200, msg='success', data=data), 200
    except Exception as e:
        return jsonify(code=500, msg=str(e), data=None), 500


@cc_bp.route('/api/contract-completion/two-year-comparison/export', methods=['GET'])
@jwt_required()
def api_export_two_year():
    """导出两年对比表Excel（带公式），支持 ?hidden=sign_amount&hidden=overseas_diff 隐藏列"""
    try:
        hidden = request.args.getlist('hidden') or None
        filepath = export_two_year_comparison_xlsx(hidden_metric_ids=hidden)
        return send_file(filepath, as_attachment=True,
                         download_name='两年对比表.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        return jsonify(code=500, msg=str(e), data=None), 500


@cc_bp.route('/uploads/unmatched_contracts.txt', methods=['GET'])
def download_unmatched():
    """下载未匹配合同TXT"""
    import os
    base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    filepath = os.path.join(base, 'uploads', 'unmatched_contracts.txt')
    if os.path.isfile(filepath):
        return send_file(filepath, as_attachment=True, download_name='unmatched_contracts.txt')
    return jsonify(code=404, msg='文件不存在', data=None), 404
