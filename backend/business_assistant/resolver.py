"""Permission-safe module name resolution for assistant questions."""
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

from ship_tracking.excel_reader import normalize_text


STATUS_ALL = 'all'
STATUS_SINGLE = 'single'
STATUS_MULTIPLE = 'multiple'
STATUS_NOT_FOUND = 'not_found'
STATUS_FORBIDDEN = 'forbidden'
STATUS_EMPTY = 'empty'

_PUNCT_RE = re.compile(
    r'[\s\u3000\-—_‐·/\\|,，.。;；:：!！?？\'"“”‘’()（）\[\]【】{}<>《》]+'
)
_LEADING_RE = re.compile(r'^(?:请问|查询|查一下|查查|看看|看一下|帮我查|关于)+')
_TRAILING_RE = re.compile(
    r'(?:模块|数据|情况|业绩|回款|签单|排产|发货|目标|完成率|怎么样|如何|多少|呢|吗|呀|啊)+$'
)
_PAREN_RE = re.compile(r'[（(][^）)]*[）)]')
_NUMBER_SUFFIX_RE = re.compile(r'[-_－—]?\d+$')
_PART_SPLIT_RE = re.compile(r'[/、,，;；|]+')


def normalize_module(value):
    """Normalize module names without changing the business name itself."""
    text = unicodedata.normalize('NFKC', normalize_text(value)).lower()
    text = _PUNCT_RE.sub('', text)
    text = _LEADING_RE.sub('', text)
    while True:
        stripped = _TRAILING_RE.sub('', text)
        if stripped == text:
            break
        text = stripped
    return text.strip()


def _add_alias(values, value):
    alias = normalize_module(value)
    if len(alias) >= 2:
        values.add(alias)


@lru_cache(maxsize=512)
def module_aliases(module_name):
    """Return common aliases for one module, longest match first."""
    text = normalize_text(module_name)
    values = set()
    if not text:
        return ()

    _add_alias(values, text)
    no_paren = _PAREN_RE.sub('', text)
    _add_alias(values, no_paren)
    _add_alias(values, _NUMBER_SUFFIX_RE.sub('', no_paren))

    for part in _PART_SPLIT_RE.split(text):
        part = part.strip()
        if not part:
            continue
        part = _PAREN_RE.sub('', part)
        _add_alias(values, part)
        _add_alias(values, _NUMBER_SUFFIX_RE.sub('', part))

    return tuple(sorted(values, key=lambda item: (-len(item), item)))


@lru_cache(maxsize=16)
def _alias_index(modules):
    index = {}
    for module in modules:
        for alias in module_aliases(module):
            index.setdefault(alias, []).append(module)
    return index


def _ordered_unique(modules, allowed):
    wanted = set(modules)
    return [module for module in allowed if module in wanted]


def _suggestions(query, modules, limit=5):
    if len(query) < 2:
        return []
    scored = []
    for module in modules:
        score = max(
            SequenceMatcher(None, query, alias).ratio()
            for alias in module_aliases(module)
        )
        if score >= 0.55:
            scored.append((score, module))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [module for _score, module in scored[:limit]]


def _match(query, modules):
    normalized = normalize_module(query)
    if not normalized:
        return {'status': STATUS_EMPTY, 'modules': [], 'query': query}

    for module in modules:
        if normalize_module(module) == normalized:
            return {'status': STATUS_SINGLE, 'modules': [module], 'query': query}

    index = _alias_index(tuple(modules))
    exact = index.get(normalized)
    if exact:
        matched = _ordered_unique(exact, modules)
        status = STATUS_SINGLE if len(matched) == 1 else STATUS_MULTIPLE
        return {'status': status, 'modules': matched, 'query': query}

    contained = []
    for alias, matched_modules in index.items():
        if len(alias) >= 2 and (normalized in alias or alias in normalized):
            contained.append((alias, matched_modules))
    if contained:
        best_length = max(len(alias) for alias, _modules in contained)
        matched = []
        for alias, matched_modules in contained:
            if len(alias) == best_length:
                matched.extend(matched_modules)
        matched = _ordered_unique(matched, modules)
        status = STATUS_SINGLE if len(matched) == 1 else STATUS_MULTIPLE
        return {'status': status, 'modules': matched, 'query': query}

    suggestions = _suggestions(normalized, modules)
    close = []
    if len(normalized) >= 3:
        for module in modules:
            score = max(
                SequenceMatcher(None, normalized, alias).ratio()
                for alias in module_aliases(module)
            )
            if score >= 0.84:
                close.append((score, module))
    close.sort(key=lambda item: (-item[0], item[1]))
    if close:
        matched = _ordered_unique([item[1] for item in close[:2]], modules)
        return {
            'status': STATUS_SINGLE if len(matched) == 1 else STATUS_MULTIPLE,
            'modules': matched,
            'query': query,
            'fuzzy': True,
        }

    return {
        'status': STATUS_NOT_FOUND,
        'modules': [],
        'query': query,
        'suggestions': suggestions,
    }


def resolve_modules(scope, requested, all_module_names=None):
    """Resolve one or more requested names, never returning a forbidden module."""
    allowed = list(scope.get('modules') or [])
    if not requested:
        return {
            'status': STATUS_ALL,
            'modules': allowed,
            'query': '',
            'message': '',
            'suggestions': [],
        }

    if isinstance(requested, (list, tuple, set)):
        values = [value for value in requested if normalize_module(value)]
    else:
        values = [requested] if normalize_module(requested) else []
    if not values:
        return {
            'status': STATUS_ALL,
            'modules': allowed,
            'query': '',
            'message': '',
            'suggestions': [],
        }

    selected = []
    fuzzy = False
    for value in values:
        result = _match(value, allowed)
        if result['status'] == STATUS_NOT_FOUND:
            outside = None
            if all_module_names:
                outside = _match(value, list(all_module_names))
            if outside and outside.get('modules'):
                return {
                    'status': STATUS_FORBIDDEN,
                    'modules': [],
                    'query': value,
                    'message': '“%s”不在当前账号的模块权限范围内。' % value,
                    'suggestions': [],
                }
            return {
                'status': STATUS_NOT_FOUND,
                'modules': [],
                'query': value,
                'message': '没有识别到模块“%s”。请说明具体模块名称或简称。' % value,
                'suggestions': result.get('suggestions') or [],
            }
        if result['status'] == STATUS_EMPTY:
            continue
        selected.extend(result['modules'])
        fuzzy = fuzzy or bool(result.get('fuzzy'))

    selected = _ordered_unique(selected, allowed)
    if not selected:
        return {
            'status': STATUS_ALL,
            'modules': allowed,
            'query': '',
            'message': '',
            'suggestions': [],
        }
    if len(selected) == 1:
        return {
            'status': STATUS_SINGLE,
            'modules': selected,
            'query': values[0],
            'message': '',
            'suggestions': [],
            'fuzzy': fuzzy,
        }
    return {
        'status': STATUS_MULTIPLE,
        'modules': selected,
        'query': '、'.join(str(value) for value in values),
        'message': '已匹配到多个模块，将按模块拆分展示：%s。' % '、'.join(selected),
        'suggestions': [],
        'fuzzy': fuzzy,
    }


def mentioned_modules(scope, text):
    """Return modules explicitly mentioned in free text, longest alias wins."""
    modules = list(scope.get('modules') or [])
    normalized = normalize_module(text)
    if not normalized:
        return []

    index = _alias_index(tuple(modules))
    matches = []
    for alias, matched_modules in index.items():
        if len(alias) >= 2 and alias in normalized:
            matches.append((alias, matched_modules))
    matches.sort(key=lambda item: (-len(item[0]), item[0]))

    selected_aliases = []
    selected_modules = []
    for alias, matched_modules in matches:
        if any(alias in chosen for chosen in selected_aliases):
            continue
        selected_aliases.append(alias)
        selected_modules.extend(matched_modules)
    return _ordered_unique(selected_modules, modules)
