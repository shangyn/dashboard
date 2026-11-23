"""Business assistant orchestration."""
import datetime as dt
import json
import logging
import re
import time
import uuid

from flask import current_app
from sqlalchemy.exc import IntegrityError

from models import db
from monthly_forecast import services as mf_svc

from business_assistant import resolver, tools
from business_assistant.exporting import create_export_token
from business_assistant.model_client import (
    answer_composition_enabled,
    compose_answer,
    model_enabled,
    plan_actions,
)
from business_assistant.models import (
    BusinessAssistantConversation,
    BusinessAssistantMessage,
    BusinessAssistantQueryLog,
    BusinessAssistantSetting,
)
from business_assistant.scope import (
    ASSISTANT_FORBIDDEN_MESSAGE,
    assistant_allowed,
    resolve_requested_modules,
    resolve_scope,
)


logger = logging.getLogger(__name__)

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
HISTORY_LIMIT = 8
FOLLOW_UP_MARKERS = (
    '那', '这', '它', '该', '刚才', '上面', '上述', '同样', '再', '还有',
    '其中', '上个月', '上月', '本月', '这个月', '呢', '继续',
)
GLOBAL_MARKERS = (
    '全部模块', '所有模块', '各模块', '每个模块', '各区域', '所有区域',
    '整体', '全公司', '全量', '汇总', '全模块',
)
MODULE_REQUIRED_MARKERS = (
    '单模块', '单个模块', '某个模块', '某一模块', '本模块', '我模块',
    '我的模块', '自己的模块', '这个模块', '该模块',
)
UNSUPPORTED_MARKERS = (
    '天气', '笑话', '讲故事', '一首诗', '翻译', '新闻', '股票',
    '聊天', '讲个', '你是谁', '唱首歌',
)
DATA_SOURCE_MARKERS = (
    '哪个表', '哪张表', '什么表', '数据来源', '来源表', '从哪来', '从哪里来',
    '读取的', '取数',
)
DATE_DIMENSION_MARKERS = (
    ('whole_ship', ('整梯发货', '整梯发运')),
    ('ship', ('发货', '发运', '组A', '组a')),
    ('schedule', ('排产', '生产')),
    ('sign', ('签单', '签订', '签约')),
)
SUBMISSION_MARKERS = (
    '填报', '报送', '提交成功', '是否提交', '提交状态', '已经提交',
    '提交了吗', '未提交', '尚未提交',
)
DATA_SOURCE_TOPIC_RULES = (
    ('submission_status', ('填报', '报送', '提交', '发货勾选')),
    ('diagnose', ('候选池', '没有进入', '没进', '无法选择')),
    ('contract_payment', ('合同回款', '梯号回款', '回款汇总')),
    ('ladder_status', ('合同状态', '梯号状态', '状态', '上传')),
    ('ladders', ('合同', '梯号', '明细', '清单', '导出')),
    ('performance', ('签单', '排产', '发货', '回款', '经营', '业绩', '完成率')),
)
VALID_TIME_SCOPES = {'all', 'year', 'month'}
MAX_PLANS = 3
COMPOUND_SPLIT_RE = re.compile(
    r'(?:[，,；;。?？！!\n]+|并且|同时|另外|顺便|然后|再问|还要)'
)
EXPLICIT_MONTH_RE = re.compile(
    r'(?:20\d{2}|上个月|上月|本月|这个月|当月|去年|今年|\d{1,2}\s*月)'
)
ACTION_TITLES = {
    'performance': '经营情况',
    'ladders': '梯号明细',
    'ladder_status': '合同/梯号状态',
    'diagnose': '候选池诊断',
    'contract_payment': '合同回款',
    'submission_status': '填报提交状态',
    'data_source': '数据来源',
    'unsupported': '未识别',
}


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
    if assistant_allowed(user):
        scope = resolve_scope(user)
        context_enabled = enabled()
        months = mf_svc.month_options()
        questions = _default_questions(scope)
        current_model_enabled = model_enabled()
        current_model_answer_enabled = answer_composition_enabled()
    else:
        scope = {
            'mode': 'none',
            'label': '暂无经营助手权限',
            'modules': [],
            'scoped': True,
        }
        context_enabled = False
        months = []
        questions = []
        current_model_enabled = False
        current_model_answer_enabled = False
    return {
        'enabled': context_enabled,
        'scope': {
            'mode': scope['mode'],
            'label': scope['label'],
            'modules': scope['modules'],
            'module_count': len(scope['modules']),
        },
        'year': dt.date.today().year,
        'months': months,
        'data_date': (dt.date.today() - dt.timedelta(days=1)).isoformat(),
        'default_questions': questions,
        'model_enabled': current_model_enabled,
        'model_answer_enabled': current_model_answer_enabled,
        'version': '2026-11-20',
    }


def get_context(user):
    return _context_payload(user)


def _today_month():
    return dt.date.today().strftime('%Y-%m')


def _shift_month(value, delta):
    try:
        year, month = [int(part) for part in str(value or '').split('-')[:2]]
    except (TypeError, ValueError):
        year, month = dt.date.today().year, dt.date.today().month
    index = year * 12 + month - 1 + delta
    return '%04d-%02d' % (index // 12, index % 12 + 1)


def _page_month(page_context):
    query = (page_context or {}).get('query') or {}
    value = query.get('month') if isinstance(query, dict) else None
    return mf_svc.normalize_month(value) if value else None


def _is_global_question(question):
    text = question or ''
    return any(marker in text for marker in GLOBAL_MARKERS)


def _inherits_context(question):
    text = re.sub(r'\s+', '', question or '')
    if not text or _is_global_question(text):
        return False
    return any(marker in text for marker in FOLLOW_UP_MARKERS) or len(text) <= 14


def _extract_month(question, page_context, last_entities=None):
    text = question or ''
    last_entities = last_entities or {}
    reference = last_entities.get('month') or _page_month(page_context) or _today_month()

    if any(word in text for word in ('上个月', '上月', '上一个月')):
        return _shift_month(reference, -1)
    if any(word in text for word in ('本月', '这个月', '当月')):
        return _today_month()

    match = re.search(r'(20\d{2})\s*[-年/.]\s*(\d{1,2})', text)
    if match:
        return mf_svc.normalize_month('%s-%02d' % (match.group(1), int(match.group(2))))
    match = re.search(r'(\d{1,2})\s*月', text)
    if match:
        if '去年' in text:
            reference_year = str(int(reference[:4]) - 1) if len(reference) >= 4 else str(dt.date.today().year - 1)
        elif '今年' in text:
            reference_year = str(dt.date.today().year)
        else:
            reference_year = reference[:4] if len(reference) >= 4 else str(dt.date.today().year)
        return mf_svc.normalize_month('%s-%02d' % (reference_year, int(match.group(1))))

    if any(word in text for word in ('今年', '去年', '年度', '全年', '整年')):
        return ''
    if last_entities.get('month') and _inherits_context(text):
        return last_entities['month']
    page_value = _page_month(page_context)
    if page_value:
        return page_value
    return ''


def _extract_date_dimension(question, last_entities=None, default='sign'):
    text = question or ''
    if '整梯发货' in text or '整梯发运' in text:
        return 'whole_ship'
    matched = []
    for dimension, markers in DATE_DIMENSION_MARKERS:
        if any(marker in text for marker in markers):
            matched.append(dimension)
    if len(matched) == 1:
        return matched[0]
    last_dimension = (last_entities or {}).get('date_dimension')
    if last_dimension and _inherits_context(text):
        return last_dimension
    return default


def _extract_year(question, page_context, last_entities=None):
    text = question or ''
    last_entities = last_entities or {}
    query = (page_context or {}).get('query') or {}
    page_value = query.get('year') if isinstance(query, dict) else None
    reference_year = dt.date.today().year
    if last_entities.get('month') and len(last_entities['month']) >= 4:
        try:
            reference_year = int(last_entities['month'][:4])
        except ValueError:
            pass
    elif page_value:
        try:
            reference_year = int(page_value)
        except (TypeError, ValueError):
            pass

    match = re.search(r'(20\d{2})', text)
    if match:
        return int(match.group(1))
    if '去年' in text:
        return reference_year - 1

    month = _extract_month(text, page_context, last_entities)
    if month:
        return int(month[:4])
    if last_entities.get('year') and _inherits_context(text):
        return int(last_entities['year'])
    if page_value:
        try:
            return int(page_value)
        except (TypeError, ValueError):
            pass
    return reference_year


def _extract_identifier(question, page_context, last_entities=None):
    query = (page_context or {}).get('query') or {}
    if isinstance(query, dict):
        for key in ('ladder_no', 'ladder', 'contract_no', 'contract'):
            if query.get(key):
                return str(query[key]).strip()
    tokens = re.findall(r'[A-Za-z0-9][A-Za-z0-9#/_\.-]{3,}', question or '')
    ignored = {'2024', '2025', '2026', '2027'}
    candidates = [token for token in tokens if token not in ignored]
    if candidates:
        return max(candidates, key=len)
    last_entities = last_entities or {}
    if _inherits_context(question):
        return (
            last_entities.get('contract_no')
            or last_entities.get('ladder_no')
            or last_entities.get('keyword')
            or ''
        )
    return ''


def _extract_page_module(page_context):
    query = (page_context or {}).get('query') or {}
    if isinstance(query, dict):
        return (query.get('module') or '').strip()
    return ''


def _looks_like_data_source_question(question):
    return any(marker in (question or '') for marker in DATA_SOURCE_MARKERS)


def _looks_like_submission_question(question):
    return any(marker in (question or '') for marker in SUBMISSION_MARKERS)


def _extract_time_scope(question, month=''):
    text = question or ''
    if month:
        return 'month'
    if any(word in text for word in ('今年', '本年', '去年', '年度', '全年', '整年')):
        return 'year'
    return 'all'


def _data_source_topic(question, last_entities=None):
    text = question or ''
    for topic, markers in DATA_SOURCE_TOPIC_RULES:
        if any(marker in text for marker in markers):
            return topic
    last_action = (last_entities or {}).get('action')
    if last_action in tools.SOURCE_CATALOG:
        return last_action
    return 'general'


def _looks_unsupported(question):
    text = question or ''
    return any(marker in text for marker in UNSUPPORTED_MARKERS)


def _heuristic_plan(question, page_context, last_entities=None):
    text = question or ''
    last_entities = last_entities or {}
    year = _extract_year(text, page_context, last_entities)
    month = _extract_month(text, page_context, last_entities)
    date_dimension = _extract_date_dimension(text, last_entities)
    module = _extract_page_module(page_context)
    identifier = _extract_identifier(text, page_context, last_entities)
    args = {
        'year': year,
        'month': month,
        'module': module,
        'keyword': identifier,
        'contract_no': '',
        'ladder_no': '',
        'date_dimension': date_dimension,
        'topic': '',
        'time_scope': '',
    }

    if _looks_like_data_source_question(text):
        return {
            'action': 'data_source',
            'args': dict(args, topic=_data_source_topic(text, last_entities)),
        }
    if _looks_unsupported(text):
        return {'action': 'unsupported', 'args': args, 'reason': 'out_of_scope'}
    if any(word in text for word in ('候选池', '没有进入', '没进', '无法选择', '不能选')):
        return {'action': 'diagnose', 'args': args}
    if _looks_like_submission_question(text):
        return {
            'action': 'submission_status',
            'args': dict(args, time_scope=_extract_time_scope(text, month)),
        }
    if '回款' in text and (
        identifier or any(word in text for word in ('合同', '梯号'))
    ):
        return {
            'action': 'contract_payment',
            'args': dict(args, time_scope=_extract_time_scope(text, month)),
        }
    if any(word in text for word in ('状态', '上传', '提交')):
        return {'action': 'ladder_status', 'args': args}
    if '导出' in text or '明细' in text or '清单' in text:
        return {'action': 'ladders', 'args': args}
    if any(word in text for word in ('合同', '梯号')) and identifier:
        return {'action': 'ladder_status', 'args': args}
    if any(word in text for word in ('合同', '梯号')):
        return {'action': 'ladders', 'args': args}
    if (
        ('计划' in text and any(word in text for word in ('实际', '完成')))
        or any(word in text for word in ('本月计划', '月度计划'))
    ):
        return {'action': 'performance', 'args': args}
    if any(word in text for word in (
        '回款', '签单', '排产', '发货', '完成率', '同比', '经营', '业绩', '目标',
    )):
        return {'action': 'performance', 'args': args}
    if _inherits_context(text) and last_entities.get('action') in (
        'performance', 'ladders', 'ladder_status', 'diagnose',
        'contract_payment', 'submission_status',
    ):
        return {'action': last_entities['action'], 'args': args}
    return {'action': 'unsupported', 'args': args, 'reason': 'not_understood'}


def _split_compound_question(question):
    parts = []
    for part in COMPOUND_SPLIT_RE.split(question or ''):
        cleaned = part.strip(' \t\u3000')
        if cleaned:
            parts.append(cleaned)
    return parts or [question or '']


def _mentions_outside_scope(scope, text):
    if not scope.get('scoped'):
        return False
    mentioned = resolver.mentioned_modules({'modules': mf_svc.all_modules()}, text)
    allowed = set(scope.get('modules') or [])
    return any(module not in allowed for module in mentioned)


def _plan_signature(plan):
    args = plan.get('args') or {}
    relevant = {
        key: args.get(key) for key in (
            'year', 'month', 'module', 'modules', 'keyword', 'contract_no',
            'ladder_no', 'date_dimension', 'topic', 'time_scope',
        )
        if args.get(key)
    }
    return (plan.get('action') or '') + '|' + json.dumps(
        relevant, ensure_ascii=False, sort_keys=True, default=str
    )


def _heuristic_plans(scope, question, page_context, last_entities=None):
    clauses = _split_compound_question(question)
    if len(clauses) <= 1:
        return [_heuristic_plan(question, page_context, last_entities)]

    full_month = _extract_month(question, page_context, last_entities)
    full_year = _extract_year(question, page_context, last_entities)
    shared_modules = resolver.mentioned_modules(scope, question)
    plans = []
    seen = set()
    unsupported = None

    for clause in clauses:
        plan = _heuristic_plan(clause, page_context, last_entities)
        action = plan.get('action') or 'unsupported'
        args = dict(plan.get('args') or {})

        if action == 'data_source' and args.get('topic') in (None, '', 'general'):
            previous_action = next((
                item.get('action') for item in reversed(plans)
                if item.get('action') and item.get('action') != 'data_source'
            ), '')
            if previous_action:
                args['topic'] = previous_action
            else:
                args['topic'] = _data_source_topic(clause, last_entities)

        if action == 'unsupported':
            if unsupported is None:
                unsupported = plan
            continue

        if not EXPLICIT_MONTH_RE.search(clause):
            args['month'] = full_month or ''
        if not re.search(r'(?:20\d{2}|去年|今年)', clause):
            args['year'] = full_year

        if not _mentions_outside_scope(scope, clause):
            clause_modules = resolver.mentioned_modules(scope, clause)
            if clause_modules:
                args['modules'] = clause_modules
            elif len(shared_modules) == 1:
                args['modules'] = list(shared_modules)

        plan = dict(plan, args=args, question=clause)
        key = _plan_signature(plan)
        if key in seen:
            continue
        seen.add(key)
        plans.append(plan)
        if len(plans) >= MAX_PLANS:
            break

    if plans:
        return plans
    return [unsupported or _heuristic_plan(question, page_context, last_entities)]


def _execute(scope, action, args):
    if action == 'performance':
        return tools.performance(scope, args)
    if action == 'ladders':
        return tools.ladders(scope, args, limit=40)
    if action == 'ladder_status':
        return tools.ladder_status(scope, args)
    if action == 'diagnose':
        return tools.diagnose(scope, args)
    if action == 'contract_payment':
        return tools.contract_payment(scope, args)
    if action == 'submission_status':
        return tools.submission_status(scope, args)
    if action == 'data_source':
        return tools.data_source(scope, args)
    raise ValueError('不支持的查询类型')


def _suggestions(scope, action):
    if action == 'multi':
        return ['分别查询一个合同回款', '查询本月填报提交状态', '这些数据从哪张表读取']
    if action == 'ladders':
        return ['按月份筛选梯号明细', '查询某个梯号当前状态', '导出当前查询结果']
    if action == 'ladder_status':
        return ['为什么这个梯号没有进入候选池', '查看该合同的其他梯号', '查询本模块年度经营情况']
    if action == 'diagnose':
        return ['查看台账明细', '查询候选池状态', '检查整梯发货日期']
    if action == 'contract_payment':
        return ['查看该合同的梯号状态', '查询该合同今年回款', '回款数据从哪张表读取']
    if action == 'submission_status':
        return ['查看本月填报计划与实际', '为什么这个模块显示未提交', '填报数据从哪张表读取']
    if action == 'data_source':
        return ['查询本模块经营数据', '查询合同回款', '查看填报提交状态']
    if scope['mode'] == 'global':
        return ['按模块查看回款完成率', '查询异常合同或梯号', '导出全部模块梯号明细']
    return ['查看本月计划与实际', '查看年度累计', '导出本模块梯号明细']


def _module_question_suggestions(scope, suggestions=None, action=''):
    template = '%s 本月填报提交成功了吗' if action == 'submission_status' else '%s 回款怎么样'
    if suggestions:
        return [template % item for item in suggestions[:3]]
    modules = scope.get('modules') or []
    if modules:
        return [template % module for module in modules[:3]]
    return _default_questions(scope)


def _failure_result(scope, status, code, message, suggestions=None, notes=None, candidates=None):
    return {
        'kind': status,
        'status': status,
        'failure_code': code,
        'needs_input': status == 'needs_input',
        'message': message,
        'columns': [],
        'rows': [],
        'notes': notes or [],
        'suggestions': suggestions or _default_questions(scope),
        'candidates': candidates or [],
        'exportable': False,
    }


def _is_all_modules_value(value):
    if not value:
        return True
    if isinstance(value, (list, tuple, set)):
        return not value
    normalized = resolver.normalize_module(value)
    return normalized in {'全部', '所有', '各', '每个', '全部模块', '所有模块'}


def _select_modules(scope, question, page_context, plan_args, last_entities,
                    prefer_explicit=False):
    explicit = plan_args.get('modules') or plan_args.get('module')
    has_explicit = not _is_all_modules_value(explicit)
    if prefer_explicit and has_explicit:
        return resolve_requested_modules(scope, explicit), 'explicit'

    mentioned = resolver.mentioned_modules(scope, question)
    if mentioned:
        return resolve_requested_modules(scope, mentioned), 'question'

    if scope.get('scoped'):
        all_names = mf_svc.all_modules()
        outside = resolver.mentioned_modules({'modules': all_names}, question)
        if outside:
            return {
                'status': resolver.STATUS_FORBIDDEN,
                'modules': [],
                'message': '你提到的模块不在当前账号的权限范围内。',
                'suggestions': [],
            }, 'question'

    if has_explicit:
        return resolve_requested_modules(scope, explicit), 'explicit'

    last_modules = last_entities.get('modules') or []
    if last_modules and _inherits_context(question):
        return resolve_requested_modules(scope, last_modules), 'context'

    page_module = _extract_page_module(page_context)
    if page_module and not _is_global_question(question):
        return resolve_requested_modules(scope, page_module), 'page'

    return resolve_requested_modules(scope, None), 'all'


def _module_required(question, action, scope, module_source):
    if action not in ('performance', 'ladders', 'submission_status'):
        return False
    if module_source != 'all' or scope.get('mode') != 'global':
        return False
    return any(marker in (question or '') for marker in MODULE_REQUIRED_MARKERS)


def _query_value(page_context, keys):
    query = (page_context or {}).get('query') or {}
    if not isinstance(query, dict):
        return ''
    for key in keys:
        if query.get(key):
            return str(query[key]).strip()
    return ''


def _build_args(plan_args, question, page_context, last_entities, modules):
    month = plan_args.get('month') or _extract_month(question, page_context, last_entities)
    month = mf_svc.normalize_month(month) if month else ''
    year = plan_args.get('year') or _extract_year(question, page_context, last_entities)
    if month:
        year = int(month[:4])
    time_scope = plan_args.get('time_scope') or _extract_time_scope(question, month)
    if time_scope not in VALID_TIME_SCOPES:
        time_scope = ''
    topic = plan_args.get('topic') or ''
    extracted_dimension = _extract_date_dimension(question, last_entities)
    date_dimension = tools._normalize_date_dimension(
        plan_args.get('date_dimension') or extracted_dimension,
        default=extracted_dimension,
    )

    keyword = plan_args.get('keyword') or _extract_identifier(question, page_context, last_entities)
    contract_no = plan_args.get('contract_no') or _query_value(
        page_context, ('contract_no', 'contract')
    )
    ladder_no = plan_args.get('ladder_no') or _query_value(
        page_context, ('ladder_no', 'ladder')
    )
    if _inherits_context(question):
        contract_no = contract_no or last_entities.get('contract_no') or ''
        ladder_no = ladder_no or last_entities.get('ladder_no') or ''
        if not plan_args.get('keyword') and not keyword:
            keyword = last_entities.get('keyword') or ''

    return {
        'year': year,
        'month': month,
        'modules': list(modules),
        'keyword': keyword or '',
        'contract_no': contract_no or '',
        'ladder_no': ladder_no or '',
        'date_dimension': date_dimension,
        'topic': topic,
        'time_scope': time_scope,
    }


def _run_plan(user, scope, question, page_context, plan, last_entities,
              prefer_explicit=False):
    action = plan.get('action') or 'unsupported'
    plan_args = plan.get('args') or {}
    if not isinstance(plan_args, dict):
        plan_args = {}

    if action == 'unsupported' and _looks_like_data_source_question(question):
        action = 'data_source'

    if action == 'data_source':
        topic = plan_args.get('topic') or _data_source_topic(question, last_entities)
        safe_args = {'topic': topic}
        result = tools.data_source(scope, safe_args)
        result['status'] = 'success'
        # 来源表问题是元查询，不覆盖上一轮业务实体，便于继续追问原查询。
        return result, None, safe_args, 'none'

    if action == 'unsupported':
        reason = plan.get('reason') or ''
        message = '这个问题不属于经营数据查询范围。我只能查询当前权限范围内的签排发、回款、合同/梯号状态、填报提交状态和候选池原因。'
        if reason == 'not_understood':
            message = '暂时没有理解这个问题对应的业务查询。可以补充模块、月份、合同号或梯号后重试。'
        return _failure_result(scope, 'unsupported', 'out_of_scope', message), None, {}, 'none'

    resolution, module_source = _select_modules(
        scope, question, page_context, plan_args, last_entities,
        prefer_explicit=prefer_explicit,
    )
    if resolution['status'] == resolver.STATUS_FORBIDDEN:
        return _failure_result(
            scope,
            'forbidden',
            'module_forbidden',
            resolution['message'],
            suggestions=_default_questions(scope),
        ), None, {}, module_source
    if resolution['status'] == resolver.STATUS_NOT_FOUND:
        return _failure_result(
            scope,
            'needs_input',
            'module_not_found',
            resolution['message'],
            suggestions=_module_question_suggestions(
                scope, resolution.get('suggestions'), action
            ),
            candidates=resolution.get('suggestions') or [],
        ), None, {}, module_source

    modules = resolution.get('modules') or []
    if _module_required(question, action, scope, module_source):
        return _failure_result(
            scope,
            'needs_input',
            'missing_module',
            '没有识别到具体模块。请说明模块名称或简称，例如“埃及”“埃及-1”或“乌克兰”。',
            suggestions=_module_question_suggestions(scope, action=action),
        ), None, {}, module_source

    safe_args = _build_args(plan_args, question, page_context, last_entities, modules)
    result = _execute(scope, action, safe_args)
    result['status'] = 'needs_input' if result.get('needs_input') else 'success'
    if result['status'] == 'needs_input':
        result['failure_code'] = result.get('failure_code') or 'missing_information'

    notes = result.setdefault('notes', [])
    if resolution['status'] == resolver.STATUS_MULTIPLE:
        notes.append(resolution['message'])
    elif module_source == 'context' and modules:
        notes.append('已沿用上一轮模块：%s。' % '、'.join(modules))
    elif resolution.get('fuzzy') and modules:
        notes.append('模块名称按近似匹配识别为：%s。' % '、'.join(modules))

    specific_modules = modules if module_source != 'all' else []
    entities = {
        'modules': specific_modules,
        'month': safe_args.get('month') or '',
        'year': safe_args.get('year') or '',
        'contract_no': safe_args.get('contract_no') or '',
        'ladder_no': safe_args.get('ladder_no') or '',
        'date_dimension': safe_args.get('date_dimension') or '',
        'keyword': safe_args.get('keyword') or '',
        'time_scope': safe_args.get('time_scope') or '',
        'action': action,
    }
    return result, entities, safe_args, module_source


def _section_from_result(result, action):
    section = dict(result or {})
    section['action'] = action
    section['title'] = ACTION_TITLES.get(action, action)
    section.setdefault('kind', action)
    section.setdefault('status', 'success')
    section.setdefault('failure_code', '')
    section.setdefault('message', '')
    section.setdefault('columns', [])
    section.setdefault('rows', [])
    section.setdefault('notes', [])
    section.setdefault('exportable', False)
    return section


def _merge_entities(items):
    items = [item for item in items if isinstance(item, dict)]
    if not items:
        return None
    merged = dict(items[0])
    actions = []
    for item in items:
        action = item.get('action')
        if action and action not in actions:
            actions.append(action)
        for key in (
            'modules', 'month', 'year', 'contract_no', 'ladder_no',
            'date_dimension', 'keyword', 'time_scope',
        ):
            if not merged.get(key) and item.get(key):
                merged[key] = item[key]
    if actions:
        merged['actions'] = actions
        merged['action'] = actions[0]
    return merged


def _namespace_section_facts(section, section_no):
    facts = []
    for item in section.get('facts') or []:
        if not isinstance(item, dict):
            continue
        fact = dict(item)
        fact_id = str(fact.get('fact_id') or '')
        if fact_id:
            fact['fact_id'] = 'section%s:%s' % (section_no, fact_id)
        facts.append(fact)
    section['facts'] = facts
    return facts


def _run_plans(user, scope, question, page_context, plans, last_entities):
    sections = []
    steps = []
    entity_items = []
    suggestion_items = []
    periods = []
    facts = []

    for plan in list(plans or [])[:MAX_PLANS]:
        action = plan.get('action') or 'unsupported'
        plan_question = plan.get('question') or question
        if action == 'data_source':
            plan_args = dict(plan.get('args') or {})
            if plan_args.get('topic') in (None, '', 'general'):
                previous_action = next((
                    item.get('action') for item in reversed(sections)
                    if item.get('action') and item.get('action') != 'data_source'
                ), '')
                if previous_action:
                    plan_args['topic'] = previous_action
                    plan = dict(plan, args=plan_args)
        result, entities, safe_args, _module_source = _run_plan(
            user, scope, plan_question, page_context, plan, last_entities,
            prefer_explicit=True,
        )
        section = _section_from_result(result, action)
        section_facts = _namespace_section_facts(section, len(sections) + 1)
        if section.get('exportable') and section.get('status') == 'success':
            export_args = section.get('export_args') or safe_args
            section['export_kind'] = section.get('kind') or action
            section['export_token'] = create_export_token(
                user, section.get('kind') or action, export_args
            )
        sections.append(section)
        steps.append({
            'tool': action,
            'status': section.get('status') or 'success',
            'row_count': len(section.get('rows') or []),
            'failure_code': section.get('failure_code') or '',
        })
        if entities is not None and action != 'data_source':
            entity_items.append(entities)
        if section.get('suggestions'):
            suggestion_items.extend(section['suggestions'])
        period = section.get('period')
        if period and period not in periods:
            periods.append(period)
        facts.extend(section_facts)

    failures = [item for item in sections if item.get('status') != 'success']
    success_count = len(sections) - len(failures)
    if not failures:
        status = 'success'
        message = '已完成 %s 项查询：%s。' % (
            len(sections),
            '、'.join(item.get('title') or item.get('action') or '' for item in sections),
        )
    elif success_count:
        status = 'partial_success'
        message = '共处理 %s 项查询：%s 项成功，%s 项未完成。' % (
            len(sections), success_count, len(failures)
        )
    else:
        status = failures[0].get('status') or 'needs_input'
        message = '本次 %s 项查询均未完成。' % len(sections)

    unique_suggestions = []
    for item in suggestion_items:
        if item and item not in unique_suggestions:
            unique_suggestions.append(item)

    return {
        'kind': 'multi',
        'status': status,
        'failure_code': failures[0].get('failure_code') or '' if failures else '',
        'needs_input': any(item.get('status') == 'needs_input' for item in sections),
        'message': message,
        'period': '；'.join(periods),
        'columns': [],
        'rows': [],
        'facts': facts,
        'notes': [],
        'suggestions': unique_suggestions[:4],
        'sections': sections,
        'steps': steps,
        'exportable': False,
    }, _merge_entities(entity_items), {}, 'multi'


def _decorate_result(result, user, scope, conversation, trace_id, action, intent_source, model_used, safe_args):
    result.setdefault('columns', [])
    result.setdefault('rows', [])
    result.setdefault('facts', [])
    result.setdefault('notes', [])
    result.setdefault('exportable', False)
    result.setdefault('status', 'success')
    result.setdefault('failure_code', '')
    if not result.get('suggestions'):
        result['suggestions'] = _suggestions(scope, action)
    result.setdefault('answer_source', 'template')
    result.setdefault('answer_fallback_code', '')
    result['trace_id'] = trace_id
    result['conversation_id'] = conversation.id
    result['scope_label'] = scope['label']
    result['data_date'] = result.get('data_date') or (
        dt.date.today() - dt.timedelta(days=1)
    ).isoformat()
    result['intent_source'] = intent_source
    result['model_used'] = bool(model_used)
    if result.get('exportable') and result.get('status') == 'success':
        export_args = result.get('export_args') or safe_args
        result['export_kind'] = result.get('kind')
        result['export_token'] = create_export_token(user, result.get('kind'), export_args)
    return result


def _result_summary(result):
    sections = result.get('sections') or []
    return {
        'kind': result.get('kind') or '',
        'status': result.get('status') or '',
        'period': result.get('period') or '',
        'row_count': len(result.get('rows') or []),
        'total': result.get('total') or 0,
        'failure_code': result.get('failure_code') or '',
        'answer_source': result.get('answer_source') or 'template',
        'answer_fallback_code': result.get('answer_fallback_code') or '',
        'section_count': len(sections),
        'sections': [{
            'action': item.get('action') or '',
            'status': item.get('status') or '',
            'failure_code': item.get('failure_code') or '',
            'row_count': len(item.get('rows') or []),
        } for item in sections],
    }


def _recent_history(conversation):
    rows = BusinessAssistantMessage.query.filter_by(
        conversation_id=conversation.id
    ).order_by(BusinessAssistantMessage.id.desc()).limit(HISTORY_LIMIT).all()
    rows.reverse()
    return [
        {'role': row.role, 'content': row.content or ''}
        for row in rows
        if row.content
    ]


def _clean_conversation_id(value):
    text = str(value or '').strip()
    if re.match(r'^[A-Fa-f0-9]{32,36}$', text):
        return text
    return ''


def _start_turn(user, question, conversation_id, trace_id):
    conversation = None
    cleaned_id = _clean_conversation_id(conversation_id)
    if cleaned_id:
        conversation = BusinessAssistantConversation.query.filter_by(
            id=cleaned_id, user_id=user.id
        ).first()
    if conversation is None:
        conversation = BusinessAssistantConversation(
            user_id=user.id,
            title=question[:120],
        )
        db.session.add(conversation)
        db.session.flush()
    history = _recent_history(conversation)
    last_entities = conversation.get_last_entities()
    if not conversation.title:
        conversation.title = question[:120]
    db.session.add(BusinessAssistantMessage(
        conversation_id=conversation.id,
        role='user',
        content=question,
        trace_id=trace_id,
    ))
    db.session.commit()
    return conversation, history, last_entities


def _finish_turn(user, conversation, question, result, trace_id, action, intent_source,
                  model_used, entities, duration_ms):
    try:
        if entities is not None:
            conversation.set_last_entities(entities)
        conversation.summary = (result.get('message') or '')[:500]
        conversation.updated_at = dt.datetime.now()
        assistant_message = BusinessAssistantMessage(
            conversation_id=conversation.id,
            role='assistant',
            content=result.get('message') or '',
            intent=action,
            trace_id=trace_id,
        )
        assistant_message.set_result_summary(result.get('result_summary') or _result_summary(result))
        db.session.add(assistant_message)
        log = BusinessAssistantQueryLog(
            trace_id=trace_id,
            user_id=user.id,
            username=user.username or '',
            conversation_id=conversation.id,
            question=question,
            status=result.get('status') or 'success',
            failure_code=result.get('failure_code') or '',
            failure_reason=(
                result.get('authoritative_message') or result.get('message') or ''
            ) if result.get('status') != 'success' else '',
            action=action,
            intent_source=intent_source,
            model_enabled=bool(model_enabled()),
            duration_ms=int(duration_ms),
            scope_label=result.get('scope_label') or '',
        )
        log.set_result_summary(_result_summary(result))
        log.set_steps(result.get('steps') or [{
            'tool': action,
            'status': result.get('status') or 'success',
            'row_count': len(result.get('rows') or []),
        }])
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('保存经营助手会话或查询日志失败 user=%s trace=%s', user.id, trace_id)


def _finish_error(user, conversation, question, trace_id, action, intent_source,
                  model_used, duration_ms, exc):
    db.session.rollback()
    try:
        if conversation is not None:
            db.session.add(BusinessAssistantMessage(
                conversation_id=conversation.id,
                role='assistant',
                content='查询处理失败，原因已记录。请稍后重试或联系管理员。',
                trace_id=trace_id,
                intent=action,
            ))
        log = BusinessAssistantQueryLog(
            trace_id=trace_id,
            user_id=user.id,
            username=user.username or '',
            conversation_id=conversation.id if conversation is not None else '',
            question=question,
            status='error',
            failure_code='unhandled_error',
            failure_reason='%s: %s' % (type(exc).__name__, exc),
            action=action,
            intent_source=intent_source,
            model_enabled=bool(model_enabled()),
            duration_ms=int(duration_ms),
        )
        log.set_result_summary({'status': 'error', 'failure_code': 'unhandled_error'})
        log.set_steps([{'tool': action, 'status': 'error'}])
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('记录经营助手异常失败 user=%s trace=%s', user.id, trace_id)


def answer(user, question, page_context=None, conversation_id=None):
    if not assistant_allowed(user):
        raise PermissionError(ASSISTANT_FORBIDDEN_MESSAGE)
    if not enabled():
        raise RuntimeError('经营助手暂未开启')
    question = (question or '').strip()
    if not question:
        raise ValueError('请输入问题')
    if len(question) > 1000:
        raise ValueError('问题内容过长')

    started = time.perf_counter()
    trace_id = uuid.uuid4().hex
    scope = resolve_scope(user)
    conversation, history, last_entities = _start_turn(
        user, question, conversation_id, trace_id
    )

    action = ''
    intent_source = 'rule'
    model_used = False
    safe_args = {}
    model_was_enabled = model_enabled()

    try:
        if scope['mode'] == 'none':
            result = _failure_result(
                scope,
                'forbidden',
                'no_scope',
                '当前账号还没有配置模块归属，暂时不能查询模块经营数据。请联系管理员在单月填报名单中配置模块。',
            )
            result['suggestions'] = _default_questions(scope)
            entities = None
        else:
            plans = plan_actions(
                question, scope, page_context, history=history, last_entities=last_entities
            ) if model_was_enabled else None
            if plans:
                intent_source = 'model'
                model_used = True
            else:
                plans = _heuristic_plans(
                    scope, question, page_context, last_entities
                )
                intent_source = 'rule_fallback' if model_was_enabled else 'rule'
            plans = [plan for plan in plans if isinstance(plan, dict)][:MAX_PLANS]
            if len(plans) > 1:
                action = 'multi'
                result, entities, safe_args, _module_source = _run_plans(
                    user, scope, question, page_context, plans, last_entities
                )
            else:
                plan = plans[0] if plans else {
                    'action': 'unsupported', 'args': {}, 'reason': 'not_understood'
                }
                action = plan.get('action') or 'unsupported'
                result, entities, safe_args, _module_source = _run_plan(
                    user, scope, question, page_context, plan, last_entities
                )

        result = _decorate_result(
            result, user, scope, conversation, trace_id, action,
            intent_source, model_used, safe_args,
        )
        if (
            model_was_enabled
            and answer_composition_enabled()
            and result.get('status') in ('success', 'partial_success')
        ):
            composed = compose_answer(question, result)
            if composed.get('ok'):
                result['authoritative_message'] = result.get('message') or ''
                result['message'] = composed.get('answer') or result.get('message') or ''
                result['answer_source'] = 'model'
                result['answer_model'] = composed.get('model') or ''
                result['answer_fact_ids'] = composed.get('fact_ids') or []
            else:
                result['answer_source'] = 'template'
                result['answer_fallback_code'] = composed.get('error_code') or 'answer_failed'
        duration_ms = (time.perf_counter() - started) * 1000
        _finish_turn(
            user, conversation, question, result, trace_id, action,
            intent_source, model_used, entities, duration_ms,
        )
        return result
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        _finish_error(
            user, conversation, question, trace_id, action,
            intent_source, model_used, duration_ms, exc,
        )
        raise


def list_query_logs(status=None, limit=100):
    query = BusinessAssistantQueryLog.query
    if status:
        query = query.filter_by(status=status)
    rows = query.order_by(BusinessAssistantQueryLog.id.desc()).limit(limit).all()
    return [row.to_dict() for row in rows]
