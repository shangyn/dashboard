"""Optional OpenAI-compatible model client.

The model selects read-only actions and may rewrite already validated tool
output. It never receives database credentials, generates SQL, or computes data.
"""
import json
import datetime as dt
import re
import time
import urllib.error
import urllib.request

from flask import current_app


ACTIONS = (
    'performance',
    'ladders',
    'ladder_status',
    'diagnose',
    'contract_payment',
    'submission_status',
    'data_source',
    'unsupported',
)

ANSWER_MAX_ROWS = 8


def model_enabled():
    if not current_app.config.get('ASSISTANT_MODEL_ENABLED'):
        return False
    return bool(
        current_app.config.get('ASSISTANT_MODEL_API_KEY')
        and current_app.config.get('ASSISTANT_MODEL_BASE_URL')
    )


def answer_composition_enabled():
    return bool(
        model_enabled()
        and current_app.config.get('ASSISTANT_MODEL_ANSWER_ENABLED', True)
    )


def connection_status():
    """Return non-secret model configuration details for administrators."""
    return {
        'enabled': bool(current_app.config.get('ASSISTANT_MODEL_ENABLED')),
        'configured': model_enabled(),
        'model': current_app.config.get('ASSISTANT_MODEL_NAME') or 'deepseek-chat',
        'base_url': current_app.config.get('ASSISTANT_MODEL_BASE_URL') or '',
        'timeout': int(current_app.config.get('ASSISTANT_MODEL_TIMEOUT', 25) or 25),
        'answer_enabled': answer_composition_enabled(),
    }


def _endpoint():
    base = (current_app.config.get('ASSISTANT_MODEL_BASE_URL') or '').rstrip('/')
    return base + '/chat/completions'


def _call_model_detailed(messages, timeout=None, max_tokens=None):
    api_key = current_app.config.get('ASSISTANT_MODEL_API_KEY') or ''
    if not api_key:
        return {
            'ok': False,
            'error_code': 'not_configured',
            'message': '未配置模型 API Key。',
            'status_code': 0,
        }
    payload = {
        'model': current_app.config.get('ASSISTANT_MODEL_NAME') or 'deepseek-chat',
        'messages': messages,
        'temperature': 0.1,
        'stream': False,
    }
    if max_tokens:
        payload['max_tokens'] = max_tokens
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
            status_code = int(getattr(response, 'status', 200) or 200)
            raw = response.read().decode('utf-8')
        data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode('utf-8', 'replace')[:300]
        except Exception:
            body = ''
        return {
            'ok': False,
            'error_code': 'http_%s' % (exc.code or 0),
            'message': ('模型接口返回 HTTP %s。%s' % (exc.code or '', body)).strip(),
            'status_code': int(exc.code or 0),
        }
    except urllib.error.URLError as exc:
        return {
            'ok': False,
            'error_code': 'network_error',
            'message': '无法连接模型接口：%s' % (getattr(exc, 'reason', exc),),
            'status_code': 0,
        }
    except (TimeoutError, OSError) as exc:
        return {
            'ok': False,
            'error_code': 'network_error',
            'message': '模型请求失败：%s' % (exc,),
            'status_code': 0,
        }
    except ValueError:
        return {
            'ok': False,
            'error_code': 'invalid_json',
            'message': '模型接口返回的内容不是合法 JSON。',
            'status_code': 0,
        }
    if not isinstance(data, dict):
        return {
            'ok': False,
            'error_code': 'invalid_response',
            'message': '模型接口返回结构不正确。',
            'status_code': status_code,
        }
    choices = data.get('choices') or []
    if not choices:
        return {
            'ok': False,
            'error_code': 'empty_response',
            'message': '模型接口没有返回候选回答。',
            'status_code': status_code,
        }
    message = choices[0].get('message') or {}
    content = message.get('content')
    if not isinstance(content, str) or not content.strip():
        return {
            'ok': False,
            'error_code': 'empty_content',
            'message': '模型接口返回了空内容。',
            'status_code': status_code,
        }
    return {
        'ok': True,
        'content': content,
        'status_code': status_code,
        'model': data.get('model') or payload['model'],
    }


def _call_model(messages, timeout=None):
    result = _call_model_detailed(messages, timeout=timeout)
    return result.get('content') if result.get('ok') else None


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


def _answer_value(value, depth=0):
    # Keep model context small and serializable without hiding key facts.
    if depth >= 3:
        return str(value)[:120]
    if isinstance(value, dict):
        cleaned = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 30:
                break
            cleaned[str(key)[:80]] = _answer_value(item, depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        return [_answer_value(item, depth + 1) for item in list(value)[:20]]
    if isinstance(value, str):
        return value[:200]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:120]


def _column_labels(columns):
    return [
        str(item.get('label') or item.get('key') or '')
        for item in (columns or [])[:20]
        if isinstance(item, dict)
    ]


def _answer_context(result):
    context = {
        'status': result.get('status') or 'success',
        'message': result.get('message') or '',
        'period': result.get('period') or '',
        'scope_label': result.get('scope_label') or '',
        'data_date': result.get('data_date') or '',
        'row_count': len(result.get('rows') or []),
        'columns': _column_labels(result.get('columns')),
        'rows': _answer_value((result.get('rows') or [])[:ANSWER_MAX_ROWS]),
        'notes': _answer_value((result.get('notes') or [])[:5]),
    }
    sections = []
    for section in (result.get('sections') or [])[:3]:
        if not isinstance(section, dict):
            continue
        sections.append({
            'title': section.get('title') or section.get('action') or '',
            'status': section.get('status') or '',
            'message': section.get('message') or '',
            'period': section.get('period') or '',
            'failure_code': section.get('failure_code') or '',
            'row_count': len(section.get('rows') or []),
            'columns': _column_labels(section.get('columns')),
            'rows': _answer_value((section.get('rows') or [])[:ANSWER_MAX_ROWS]),
        })
    if sections:
        context['sections'] = sections
    return context


_NUMBER_TOKEN_RE = re.compile(r'\d+(?:\.\d+)?')
_TABLE_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+)')


def _number_tokens(text):
    normalized = re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))', '', text or '')
    tokens = set()
    for token in _NUMBER_TOKEN_RE.findall(normalized):
        if '.' in token:
            token = token.rstrip('0').rstrip('.')
        tokens.add(token or '0')
    return tokens


def _table_tokens(text):
    return {token.lower() for token in _TABLE_TOKEN_RE.findall(text or '')}


def compose_answer(question, result, timeout=None):
    # Turn validated tool output into a concise answer, never calculating data.
    if not answer_composition_enabled():
        return {
            'ok': False,
            'error_code': 'answer_not_configured',
            'message': '答复整理未启用。',
        }
    if (result or {}).get('status') not in ('success', 'partial_success'):
        return {
            'ok': False,
            'error_code': 'answer_not_applicable',
            'message': '当前结果不需要模型整理。',
        }

    context = _answer_context(result)
    system = (
        '你是经营数据助手的答复整理器。后端只读工具已经完成权限校验、查询和计算。'
        '只能使用给定 tool_result 中的事实，不得新增、推测或重算任何金额、数量、百分比、'
        '日期、模块、合同号、梯号或表名。不得生成 SQL，不得声称访问了未提供的数据，'
        '不得回答经营数据之外的话题。若 status 为 partial_success，必须说明哪些子查询未完成；'
        '若某项需要补充信息，要明确缺少什么。用简洁中文回答 1 到 3 句，不要 Markdown、'
        '不要表格、不要复述全部字段。只输出一个 JSON 对象，字段名为 answer，值为字符串。'
    )
    user = json.dumps({
        'question': question,
        'tool_result': context,
    }, ensure_ascii=False)
    response = _call_model_detailed(
        [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        timeout=timeout or current_app.config.get('ASSISTANT_MODEL_TIMEOUT', 25),
        max_tokens=420,
    )
    if not response.get('ok'):
        return {
            'ok': False,
            'error_code': 'answer_' + (response.get('error_code') or 'model_error'),
            'message': response.get('message') or '模型答复整理失败。',
        }

    data = _extract_json(response.get('content'))
    answer = data.get('answer') if isinstance(data, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        return {
            'ok': False,
            'error_code': 'answer_invalid_json',
            'message': '模型没有返回合法的答复 JSON。',
        }
    answer = re.sub(r'\s+', ' ', answer).strip()
    if len(answer) > 600 or '```' in answer or answer.startswith('#'):
        return {
            'ok': False,
            'error_code': 'answer_invalid_format',
            'message': '模型答复格式不符合要求。',
        }

    context_text = json.dumps(context, ensure_ascii=False, default=str)
    new_numbers = _number_tokens(answer) - _number_tokens(context_text)
    if new_numbers:
        return {
            'ok': False,
            'error_code': 'answer_unverified_number',
            'message': '模型答复包含工具结果中不存在的数字，已退回固定答复。',
        }
    new_tables = _table_tokens(answer) - _table_tokens(context_text)
    if new_tables:
        return {
            'ok': False,
            'error_code': 'answer_unverified_table',
            'message': '模型答复包含工具结果中不存在的表名，已退回固定答复。',
        }
    return {
        'ok': True,
        'answer': answer,
        'model': response.get('model') or '',
    }


def plan_actions(question, scope, page_context, history=None, last_entities=None):
    """Ask the model to select up to three read-only actions."""
    modules = scope.get('modules') or []
    system = (
        '你是经营数据助手，不是开放式聊天机器人。只能从给定的只读动作中选择一个或多个，'
        '不得编造数据、模块名或权限。问题与经营数据无关时选择 unsupported；'
        '需要业务数据但信息不足时，选择对应动作并把缺少的参数留空，由后端追问。'
        '结合最近对话和上一轮实体理解“那上个月呢”“这个合同呢”等追问。'
        '简单问题只返回一个动作；一个复合问题确实包含多个独立查询时，可返回最多三个动作，'
        '不要把同一动作拆成多个，也不要为同一个查询重复返回动作。'
        '问某类数据来自哪张表、从哪里读取时选择 data_source，并在 topic 中填写对应的'
        '业务动作；没有明确新主题时沿用 last_entities.action。'
        '只问某个合同或梯号的回款选择 contract_payment；问模块单月填报是否提交选择'
        'submission_status。不得直接回答数据库内容，也不得生成 SQL。'
        '只输出 JSON，不要 Markdown。'
    )
    user = {
        'question': question,
        'scope': {'mode': scope.get('mode'), 'modules': modules},
        'page_context': page_context or {},
        'recent_messages': history or [],
        'last_entities': last_entities or {},
        'today': dt.date.today().isoformat(),
        'actions': [
            {'name': 'performance', 'description': '查询模块年度或自然月签单、排产、发货、回款及目标完成率'},
            {'name': 'ladders', 'description': '查询或准备导出当前权限内的梯号明细；回款比例优先使用回款计算结果'},
            {'name': 'ladder_status', 'description': '查询合同或梯号在台账、填报、发货计划、实发、回款中的状态，并标注回款比例来源'},
            {'name': 'diagnose', 'description': '解释梯号没有进入候选池或无法选择的原因'},
            {'name': 'contract_payment', 'description': '查询某个合同或梯号的回款汇总和计算口径回款比例；没有合同号或梯号时留空，由后端追问'},
            {'name': 'submission_status', 'description': '查询模块某月单月签排发填报是否已提交、提交时间、快照版本'},
            {'name': 'data_source', 'description': '说明当前业务查询读取了哪些固定数据库表；用于“从哪张表读取”的追问'},
            {'name': 'unsupported', 'description': '问题与经营数据无关，或当前版本没有可用的只读工具'},
        ],
        'output_schema': {
            'actions': [{
                'action': 'performance|ladders|ladder_status|diagnose|contract_payment|submission_status|data_source|unsupported',
                'reason': 'brief reason for unsupported or missing information, or empty',
                'args': {
                    'year': 'YYYY or empty',
                    'month': 'YYYY-MM or empty',
                    'module': 'module name or alias from the question or context, or empty',
                    'keyword': 'contract/ladder/project keyword or empty',
                    'contract_no': 'contract number or empty',
                    'ladder_no': 'ladder number or empty',
                    'topic': 'for data_source: performance|ladders|ladder_status|diagnose|contract_payment|submission_status|general',
                    'time_scope': 'all|year|month or empty',
                },
            }],
        },
    }
    content = _call_model([
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': json.dumps(user, ensure_ascii=False)},
    ])
    data = _extract_json(content)
    if not isinstance(data, dict):
        return None
    raw_actions = data.get('actions')
    if not isinstance(raw_actions, list):
        raw_actions = [data] if data.get('action') else []
    plans = []
    seen = set()
    for item in raw_actions:
        if not isinstance(item, dict):
            continue
        action = item.get('action')
        if action not in ACTIONS:
            continue
        args = item.get('args') or {}
        if not isinstance(args, dict):
            args = {}
        reason = item.get('reason')
        plan = {
            'action': action,
            'args': args,
            'reason': reason if isinstance(reason, str) else '',
        }
        key = action + '|' + json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        plans.append(plan)
        if len(plans) >= 3:
            break
    if any(plan['action'] != 'unsupported' for plan in plans):
        plans = [plan for plan in plans if plan['action'] != 'unsupported']
    return plans or None


def plan_action(question, scope, page_context, history=None, last_entities=None):
    """Backward-compatible single-action entry point."""
    plans = plan_actions(
        question, scope, page_context, history=history, last_entities=last_entities
    )
    return plans[0] if plans else None


def test_connection(timeout=None):
    """Perform one real model call and verify a safe action-shaped response."""
    started = time.perf_counter()
    checked_at = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status = connection_status()
    base = {
        'configured': status['configured'],
        'enabled': status['enabled'],
        'model': status['model'],
        'base_url': status['base_url'],
        'checked_at': checked_at,
        'latency_ms': 0,
        'routing_latency_ms': 0,
        'reachable': False,
        'action': '',
        'action_ok': False,
        'error_code': '',
        'status_code': 0,
        'response_preview': '',
        'answer_checked': False,
        'answer_ok': False,
        'answer_message': '',
    }
    if not status['configured']:
        base.update({
            'success': False,
            'error_code': 'not_configured',
            'message': '模型未启用或 API Key、接口地址未配置完整。',
        })
        return base

    system = (
        '你是经营数据意图路由助手。只能从给定动作中选择，不能回答数据库内容，'
        '不能生成 SQL。只输出 JSON，不要 Markdown。'
    )
    user = json.dumps({
        'question': '合同 HT-TEST-001 回款多少？',
        'allowed_actions': ['contract_payment', 'ladder_status', 'unsupported'],
        'output_schema': {
            'actions': [{
                'action': 'contract_payment|ladder_status|unsupported',
                'args': {'contract_no': 'contract number or empty'},
            }]
        },
    }, ensure_ascii=False)
    result = _call_model_detailed(
        [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        timeout=timeout or min(status['timeout'], 20),
        max_tokens=320,
    )
    base['routing_latency_ms'] = int((time.perf_counter() - started) * 1000)
    base['latency_ms'] = base['routing_latency_ms']
    base['status_code'] = int(result.get('status_code') or 0)
    if not result.get('ok'):
        base.update({
            'success': False,
            'error_code': result.get('error_code') or 'model_error',
            'message': result.get('message') or '模型调用失败。',
        })
        return base

    base['reachable'] = True
    base['model'] = result.get('model') or base['model']
    content = result.get('content') or ''
    base['response_preview'] = content[:300]
    data = _extract_json(content)
    raw_actions = data.get('actions') if isinstance(data, dict) else None
    if not isinstance(raw_actions, list):
        action = data.get('action') if isinstance(data, dict) else ''
    else:
        action = raw_actions[0].get('action') if raw_actions and isinstance(raw_actions[0], dict) else ''
    if action not in ACTIONS:
        base.update({
            'success': False,
            'error_code': 'invalid_action',
            'message': '模型接口可访问，但没有返回合法的动作 JSON。',
        })
        return base

    base['action'] = action
    base['action_ok'] = action == 'contract_payment'
    if base['action_ok']:
        base.update({
            'success': True,
            'message': '模型连接成功，并正确识别为合同回款查询。',
        })
    else:
        base.update({
            'success': False,
            'error_code': 'unexpected_action',
            'message': '模型连接成功，但识别动作为 %s，与预期的合同回款动作不一致。' % action,
        })
    if base.get('success') and answer_composition_enabled():
        synthetic = {
            'status': 'success',
            'message': '共匹配 1 个合同，回款合计 1234.5 万元。',
            'period': '全部日期',
            'scope_label': '全部模块',
            'columns': [
                {'key': 'contract_no', 'label': '合同号'},
                {'key': 'payment_wan', 'label': '回款(万元)'},
            ],
            'rows': [{'contract_no': 'HT-TEST-001', 'payment_wan': 1234.5}],
            'notes': [],
        }
        composed = compose_answer(
            '合同 HT-TEST-001 回款多少？',
            synthetic,
            timeout=min(status['timeout'], 15),
        )
        base['answer_checked'] = True
        base['answer_ok'] = bool(composed.get('ok'))
        if base['answer_ok']:
            base['answer_message'] = '答复整理验证通过。'
        else:
            base['answer_message'] = composed.get('message') or '答复整理验证失败。'
            base.update({
                'success': False,
                'error_code': 'answer_check_failed',
                'message': '模型路由可用，但答复整理验证失败：%s' % base['answer_message'],
            })
    base['latency_ms'] = int((time.perf_counter() - started) * 1000)
    return base
