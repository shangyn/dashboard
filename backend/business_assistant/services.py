"""Business assistant orchestration."""
import datetime as dt
import re
import uuid

from flask import current_app
from sqlalchemy.exc import IntegrityError

from models import db
from monthly_forecast import services as mf_svc

from business_assistant import tools
from business_assistant.exporting import create_export_token
from business_assistant.model_client import model_enabled, plan_action
from business_assistant.models import BusinessAssistantSetting
from business_assistant.scope import resolve_scope


GLOBAL_QUESTIONS = [
    '各模块今年签单、排产、发货、回款、目标完成率及同比',
    '各模块本月计划与实际完成情况',
    '查询某个合同或梯号当前状态',
    '为什么某个梯号没有进入候选池',
    '导出全部模块今年梯号明细',
]

MODULE_QUESTIONS = [
    '我模块今年签单、排产、发货、回款、目标完成率及同比',
    '我模块本月计划与实际完成情况',
    '查询某个梯号当前状态',
    '为什么某个梯号没有进入候选池',
    '导出我模块今年梯号明细',
]

LIMITED_QUESTIONS = [
    '我能查看哪些经营数据',
    '为什么当前账号没有模块经营数据',
    '合同和梯号数据从哪里来',
]

SETTING_ID = 1


def enabled():
    return bool(_setting_row().enabled)


def _setting_row():
    row = db.session.get(BusinessAssistantSetting, SETTING_ID)
    if row is not None:
        return row
    row = BusinessAssistantSetting(
        id=SETTING_ID,
        enabled=bool(current_app.config.get('ASSISTANT_ENABLED', True)),
    )
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        row = db.session.get(BusinessAssistantSetting, SETTING_ID)
    return row


def is_admin(user):
    return bool(user and user.role and user.role.is_admin)


def get_setting():
    return _setting_row().to_dict()


def update_setting(user, enabled_value):
    row = _setting_row()
    row.enabled = bool(enabled_value)
    row.updated_by = user.id
    row.updated_by_name = user.real_name or user.username or ''
    db.session.commit()
    return row.to_dict()


def _default_questions(scope):
    if scope['mode'] == 'global':
        return GLOBAL_QUESTIONS
    if scope['mode'] == 'module':
        return MODULE_QUESTIONS
    return LIMITED_QUESTIONS


def _context_payload(user):
    scope = resolve_scope(user)
    return {
        'enabled': enabled(),
        'scope': {
            'mode': scope['mode'],
            'label': scope['label'],
            'modules': scope['modules'],
            'module_count': len(scope['modules']),
        },
        'year': dt.date.today().year,
        'months': mf_svc.month_options(),
        'data_date': (dt.date.today() - dt.timedelta(days=1)).isoformat(),
        'default_questions': _default_questions(scope),
        'model_enabled': model_enabled(),
        'version': '2026-11-19',
    }


def get_context(user):
    return _context_payload(user)


def _page_month(page_context):
    query = (page_context or {}).get('query') or {}
    value = query.get('month') if isinstance(query, dict) else None
    return mf_svc.normalize_month(value) if value else None


def _extract_month(question, page_context):
    page_value = _page_month(page_context)
    if page_value:
        return page_value
    match = re.search(r'(20\d{2})[-年/](\d{1,2})', question or '')
    if match:
        return mf_svc.normalize_month('%s-%02d' % (match.group(1), int(match.group(2))))
    match = re.search(r'(\d{1,2})\s*月', question or '')
    if match:
        return mf_svc.normalize_month('%s-%02d' % (dt.date.today().year, int(match.group(1))))
    if '本月' in (question or ''):
        return dt.date.today().strftime('%Y-%m')
    return ''


def _extract_year(question, page_context):
    query = (page_context or {}).get('query') or {}
    value = query.get('year') if isinstance(query, dict) else None
    if value:
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    match = re.search(r'(20\d{2})', question or '')
    return int(match.group(1)) if match else dt.date.today().year


def _extract_identifier(question, page_context):
    query = (page_context or {}).get('query') or {}
    if isinstance(query, dict):
        for key in ('ladder_no', 'ladder', 'contract_no', 'contract'):
            if query.get(key):
                return str(query[key]).strip()
    tokens = re.findall(r'[A-Za-z0-9][A-Za-z0-9#/_\.-]{3,}', question or '')
    ignored = {'2024', '2025', '2026', '2027'}
    candidates = [token for token in tokens if token not in ignored]
    return max(candidates, key=len) if candidates else ''


def _extract_page_module(page_context):
    query = (page_context or {}).get('query') or {}
    if isinstance(query, dict):
        return (query.get('module') or '').strip()
    return ''


def _heuristic_plan(question, page_context):
    text = question or ''
    month = _extract_month(text, page_context)
    year = _extract_year(text, page_context)
    module = _extract_page_module(page_context)
    identifier = _extract_identifier(text, page_context)
    args = {
        'year': year,
        'month': month,
        'module': module,
        'keyword': identifier,
        'contract_no': '',
        'ladder_no': '',
    }
    if any(word in text for word in ('候选池', '没有进入', '没进', '无法选择', '不能选')):
        return {'action': 'diagnose', 'args': args}
    if any(word in text for word in ('状态', '上传')):
        return {'action': 'ladder_status', 'args': args}
    if '导出' in text or '明细' in text:
        return {'action': 'ladders', 'args': args}
    if any(word in text for word in ('梯号', '合同')):
        return {'action': 'ladders', 'args': args}
    return {'action': 'performance', 'args': args}


def _execute(scope, action, args):
    if action == 'performance':
        result = tools.performance(scope, args)
    elif action == 'ladders':
        result = tools.ladders(scope, args, limit=40)
    elif action == 'ladder_status':
        result = tools.ladder_status(scope, args)
    elif action == 'diagnose':
        result = tools.diagnose(scope, args)
    else:
        raise ValueError('不支持的查询类型')
    return result


def _suggestions(scope, action):
    if action == 'ladders':
        return ['按月份筛选梯号明细', '查询某个梯号当前状态', '导出当前查询结果']
    if action == 'ladder_status':
        return ['为什么这个梯号没有进入候选池', '查看该合同的其他梯号', '查询本模块年度经营情况']
    if action == 'diagnose':
        return ['查看台账明细', '查询候选池状态', '检查整梯发货日期']
    if scope['mode'] == 'global':
        return ['按模块查看回款完成率', '查询异常合同或梯号', '导出全部模块梯号明细']
    return ['查看本月计划与实际', '查看年度累计', '导出本模块梯号明细']


def answer(user, question, page_context=None):
    if not enabled():
        raise RuntimeError('经营助手暂未开启')
    question = (question or '').strip()
    if not question:
        raise ValueError('请输入问题')
    if len(question) > 1000:
        raise ValueError('问题内容过长')
    scope = resolve_scope(user)
    if scope['mode'] == 'none':
        return {
            'trace_id': uuid.uuid4().hex,
            'message': '当前账号还没有配置模块归属，暂时不能查询模块经营数据。请联系管理员在单月填报名单中配置模块。',
            'columns': [],
            'rows': [],
            'notes': [],
            'exportable': False,
            'suggestions': _default_questions(scope),
        }

    plan = plan_action(question, scope, page_context) if model_enabled() else None
    if not plan:
        plan = _heuristic_plan(question, page_context)
    action = plan['action']
    args = plan.get('args') or {}
    if not isinstance(args, dict):
        args = {}
    safe_args = {
        key: args.get(key)
        for key in ('year', 'month', 'module', 'keyword', 'contract_no', 'ladder_no')
        if args.get(key) not in (None, '')
    }
    result = _execute(scope, action, safe_args)
    result['trace_id'] = uuid.uuid4().hex
    result['scope_label'] = scope['label']
    result['suggestions'] = _suggestions(scope, action)
    result['data_date'] = result.get('data_date') or (dt.date.today() - dt.timedelta(days=1)).isoformat()
    if result.get('exportable'):
        export_args = result.get('export_args') or safe_args
        result['export_kind'] = result.get('kind')
        result['export_token'] = create_export_token(user, result.get('kind'), export_args)
    return result
