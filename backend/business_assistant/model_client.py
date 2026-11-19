"""Optional OpenAI-compatible model client.

The model is only used for intent selection. All data access, permission
checks, calculations and answer wording stay in the backend tools.
"""
import json
import datetime as dt
import urllib.error
import urllib.request

from flask import current_app


ACTIONS = ('performance', 'ladders', 'ladder_status', 'diagnose')


def model_enabled():
    if not current_app.config.get('ASSISTANT_MODEL_ENABLED'):
        return False
    return bool(
        current_app.config.get('ASSISTANT_MODEL_API_KEY')
        and current_app.config.get('ASSISTANT_MODEL_BASE_URL')
    )


def _endpoint():
    base = (current_app.config.get('ASSISTANT_MODEL_BASE_URL') or '').rstrip('/')
    return base + '/chat/completions'


def _call_model(messages, timeout=None):
    api_key = current_app.config.get('ASSISTANT_MODEL_API_KEY') or ''
    if not api_key:
        return None
    payload = {
        'model': current_app.config.get('ASSISTANT_MODEL_NAME') or 'deepseek-chat',
        'messages': messages,
        'temperature': 0.1,
        'stream': False,
    }
    request = urllib.request.Request(
        _endpoint(),
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % api_key,
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout or current_app.config.get('ASSISTANT_MODEL_TIMEOUT', 25),
        ) as response:
            data = json.loads(response.read().decode('utf-8'))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    if not isinstance(data, dict):
        return None
    choices = data.get('choices') or []
    if not choices:
        return None
    message = choices[0].get('message') or {}
    content = message.get('content')
    return content if isinstance(content, str) else None


def _extract_json(text):
    if not text:
        return None
    start = text.find('{')
    end = text.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def plan_action(question, scope, page_context):
    """Ask the model to select one read-only action. Returns None on failure."""
    modules = scope.get('modules') or []
    system = (
        '你是经营数据查询路由器。只能从给定的只读动作中选择一个，'
        '不得编造数据，不得决定权限。只输出 JSON，不要 Markdown。'
    )
    user = {
        'question': question,
        'scope': {'mode': scope.get('mode'), 'modules': modules},
        'page_context': page_context or {},
        'today': dt.date.today().isoformat(),
        'actions': [
            {'name': 'performance', 'description': '查询模块年度或自然月签单、排产、发货、回款及目标完成率'},
            {'name': 'ladders', 'description': '查询或准备导出当前权限内的台账梯号明细'},
            {'name': 'ladder_status', 'description': '查询合同或梯号在台账、填报、发货计划、实发、回款中的状态'},
            {'name': 'diagnose', 'description': '解释梯号没有进入候选池或无法选择的原因'},
        ],
        'output_schema': {
            'action': 'performance|ladders|ladder_status|diagnose',
            'args': {
                'year': 'YYYY or empty',
                'month': 'YYYY-MM or empty',
                'module': 'module name or empty',
                'keyword': 'contract/ladder/project keyword or empty',
                'contract_no': 'contract number or empty',
                'ladder_no': 'ladder number or empty',
            },
        },
    }
    content = _call_model([
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': json.dumps(user, ensure_ascii=False)},
    ])
    data = _extract_json(content)
    if not isinstance(data, dict):
        return None
    action = data.get('action')
    if action not in ACTIONS:
        return None
    args = data.get('args') or {}
    return {'action': action, 'args': args if isinstance(args, dict) else {}}
