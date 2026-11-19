"""Excel export for the business assistant.

The browser receives only a short-lived, signed token. The backend re-resolves
the current user's scope and rebuilds the workbook from the same read-only
tools used by the chat answer.
"""
import datetime as dt
import io

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from business_assistant import tools
from business_assistant.scope import resolve_scope


SALT = 'business-assistant-export'


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=SALT)


def create_export_token(user, kind, query):
    payload = {
        'uid': user.id,
        'kind': kind,
        'query': query or {},
        'created_at': dt.datetime.now().isoformat(timespec='seconds'),
    }
    return _serializer().dumps(payload)


def load_export_payload(token):
    try:
        max_age = int(current_app.config.get('ASSISTANT_EXPORT_MAX_AGE', 900))
        return _serializer().loads(token, max_age=max_age)
    except SignatureExpired:
        raise ValueError('导出链接已过期，请重新查询')
    except BadSignature:
        raise ValueError('导出链接无效')


def _style_header(worksheet):
    from openpyxl.styles import Alignment, Font, PatternFill

    fill = PatternFill('solid', fgColor='DCE8F8')
    font = Font(bold=True, color='17365D')
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    for cell in worksheet[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = center
    worksheet.freeze_panes = 'A2'


def _append_summary(worksheet, scope, result):
    worksheet.append(['项目', '内容'])
    worksheet.append(['查询范围', scope['label']])
    worksheet.append(['权限模块数', len(scope['modules'])])
    worksheet.append(['数据截止日期', result.get('data_date') or ''])
    worksheet.append(['时间口径', result.get('period') or ''])
    worksheet.append(['查询类型', result.get('kind') or ''])
    worksheet.append(['说明', '；'.join(result.get('notes') or [])])
    _style_header(worksheet)


def _append_ladders(workbook, result):
    sheet = workbook.create_sheet('梯号明细')
    headers = [
        '合同号', '梯号', '项目名称', '台数', '金额(万元)', '排产完工日期',
        '整梯发货日期', '组A日期', '产品型号', '载重', '速度', '签订日期',
        '产品状态', '业务员', '已回款比例',
    ]
    sheet.append(headers)
    for row in result.get('rows') or []:
        sheet.append([
            row.get('contract_no') or '',
            row.get('ladder_no') or '',
            row.get('project_name') or '',
            row.get('unit_count') or 0,
            row.get('amount_wan') or 0,
            row.get('schedule_finish_date') or '',
            row.get('whole_ship_date') or '',
            row.get('delivery_date') or '',
            row.get('product_type') or '',
            row.get('capacity') or 0,
            row.get('speed') or 0,
            row.get('sign_date') or '',
            row.get('product_status') or '',
            row.get('salesperson') or '',
            row.get('payment_ratio_label') or '—',
        ])
    _style_header(sheet)


def _append_performance(workbook, result):
    sheet = workbook.create_sheet('模块汇总')
    metric_labels = (('sign_amount', '签单'), ('schedule_amount', '排产'),
                     ('ship_amount', '发货'), ('payment_amount', '回款'))
    headers = ['模块', '大区']
    for _key, label in metric_labels:
        headers.extend([
            '年%s额' % label, '%s目标' % label,
            '%s完成率(%%)' % label, '%s同比(%%)' % label,
        ])
    if result.get('period', '').count('-') == 1:
        headers.extend([
            '本月计划签单', '本月计划排产', '本月计划发货', '本月计划回款',
            '本月实际签单', '本月实际排产', '本月实际发货', '本月实际回款',
        ])
    sheet.append(headers)
    for row in result.get('rows') or []:
        annual = row.get('annual') or {}
        values = [row.get('module_name') or '', row.get('region') or '']
        for key, _label in metric_labels:
            metric = annual.get(key) or {}
            values.extend([
                metric.get('actual', 0), metric.get('target'),
                metric.get('ratio'), metric.get('growth'),
            ])
        if result.get('period', '').count('-') == 1:
            plan = row.get('month_plan') or {}
            actual = row.get('month_actual') or {}
            values.extend([
                plan.get('sign_amount', 0), plan.get('prod_amount', 0),
                plan.get('ship_amount', 0), plan.get('payment_amount', 0),
                actual.get('sign_amount', 0), actual.get('prod_amount', 0),
                actual.get('ship_amount', 0), actual.get('payment_amount', 0),
            ])
        sheet.append(values)
    _style_header(sheet)


def export_workbook(user, token):
    payload = load_export_payload(token)
    if int(payload.get('uid') or 0) != int(user.id):
        raise PermissionError('无权下载该导出文件')
    scope = resolve_scope(user)
    if scope['mode'] == 'none':
        raise PermissionError('当前账号没有经营数据权限')

    kind = payload.get('kind')
    query = payload.get('query') or {}
    if kind == 'ladders':
        result = tools.ladders(scope, query, limit=None)
        filename = '经营助手_梯号明细_%s.xlsx' % (result.get('period') or '查询结果')
    elif kind == 'performance':
        result = tools.performance(scope, query)
        filename = '经营助手_模块汇总_%s.xlsx' % (result.get('period') or '查询结果')
    else:
        raise ValueError('不支持的导出类型')

    from openpyxl import Workbook

    workbook = Workbook()
    summary = workbook.active
    summary.title = '查询摘要'
    _append_summary(summary, scope, result)
    if kind == 'ladders':
        _append_ladders(workbook, result)
    else:
        _append_performance(workbook, result)

    notes = workbook.create_sheet('口径说明')
    notes.append(['说明'])
    notes.append(['实际业绩、月度预计和发货计划是不同口径，导出结果按查询类型展示。'])
    notes.append(['已回款比例直接取台账 payment_ratio，不在本导出中重新分摊回款。'])
    notes.append(['回款逐笔日期、节点、付款方式、备注不纳入本导出。'])
    notes.append(['导出行数：%s' % (result.get('total') or len(result.get('rows') or []))])
    notes.append(['生成时间：%s' % dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    _style_header(notes)

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output, filename
