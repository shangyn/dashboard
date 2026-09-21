'''
单月签排发填报 — 复用既有「国家-市场-业务员」表，把「人名」解析成系统正式模块名

数据来源（只读，绝不修改既有模块的任何文件与数据）：
    backend/uploads/contract_completion/contract_mapping/国家-市场-业务员*.xlsx
    该文件由既有「合同完成情况」模块上传维护，本模块只读取其中最新的一份。

为什么必须做归一化：
    同一张表里同一个模块会写成多种形态，例如
        越南－1（工厂） / 越南-1（工厂）      全角、半角破折号
        朝鲜／韩国 / 朝鲜-韩国                全角斜杠
        商贸-1 / 商贸1                        多余破折号
        埃及一1 / 埃及-1                      「一」被误写成破折号
        英国／意大利 / 英国意大利             斜杠有无
    必须折算到系统正式模块名，否则归属判定对不上（台账口径用的是正式名）。

判定原则：宁可漏，不可错。
    一个原始模块名会生成若干等价写法，只有当所有能对上的写法都指向同一个正式模块时才算解析成功；
    对不上、或指向多个 → 视为未解析，交由人工处理。
'''
import os
import re

# 业务员表所在的既有上传目录（只读）
MAPPING_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'uploads', 'contract_completion', 'contract_mapping',
)
MAPPING_PREFIX = '国家-市场-业务员'

GAZAO_MODULE = '改造'

# 表头里这些列不是人名（子串匹配）
_SKIP_HEADER_PARTS = ('大区', '国家', '组织', '岗位', '序号', '备注')

# 表头「恰好」等于这些的列也不是人名（模块列本身单独处理）
_SKIP_HEADER_EXACT = ('模块', 'module')

# 这些不是模块，是表格里的标题行 / 合计行 / 组织名
_SKIP_MODULE_PARTS = ('大区', '合计', '小计', '个模块')

# 占位符，不是人名
_PLACEHOLDERS = ('（空）', '(空)', '空', '无', '待定', '/', '-', '—')

# 人名前后缀：前任、暂时接管
_PREFIXES = ('原', '前')
_SUFFIXES = ('暂时代管', '暂时兼管', '代管', '兼管')

_SPLIT_CHARS = '／/、,，;；'

_DASH_MAP = {'－': '-', '—': '-', '–': '-', '−': '-', '﹣': '-'}
_SLASH_MAP = {'／': '/'}
_PAREN_MAP = {'（': '(', '）': ')'}
_ONE = '一'

# 源表里的固定别名写法 -> 系统正式模块名
# 每一条都用「模主+助理对应模块」交叉验证过（同一个人在那张表里指向同一个模块）
_MODULE_ALIASES = {
    '秘鲁－1': '秘鲁',
    '秘鲁－2': '秘鲁2',
    '泰国－1': '泰国',
    '泰国－2': '泰国2',
    '孟加拉': '孟加拉-1',
    '菲律宾－1': '菲律宾',
    '菲律宾－2': '菲律宾-2',
    '日港台': '香港-台湾',
    '哈萨克斯坦－2／塔吉克斯坦': '塔吉克/哈萨克斯坦-2',
    '更新改造': '改造',
}

# 模主/模块对应关系的权威 sheet：逐人一行、专表专用；其它 sheet 只做补充
AUTHORITATIVE_SHEET = '任命令模块-模主'


def _text(value):
    return '' if value is None else str(value).strip()


def _base(text):
    '''基础归一化：去空白 + 全角转半角（破折号 / 斜杠 / 括号）'''
    value = _text(text)
    for src, dst in _DASH_MAP.items():
        value = value.replace(src, dst)
    for src, dst in _SLASH_MAP.items():
        value = value.replace(src, dst)
    for src, dst in _PAREN_MAP.items():
        value = value.replace(src, dst)
    return re.sub(r'\s+', '', value)


_ALIAS_TABLE = tuple((_base(key), value) for key, value in _MODULE_ALIASES.items())


def _variants(text):
    '''一个模块名的若干等价写法'''
    base = _base(text)
    if not base:
        return set()
    out = {base}
    out.add(base.replace(_ONE, '-'))
    out.add(base.replace('/', '+'))
    out.add(base.replace('/', '-'))
    out.add(base.replace('/', ''))
    out.add(base.replace('-', ''))
    out.add(base.replace('-', '/'))
    return {item for item in out if item}


class ModuleResolver:
    '''把各种写法的模块名折算成系统正式模块名'''

    def __init__(self, module_names):
        self._keys = {}
        for name in module_names:
            if name:
                self._keys.setdefault(_base(name), name)

    def resolve(self, raw):
        '''返回可能对应的正式模块名集合（空集 = 未解析）'''
        base = _base(raw)
        for alias, target in _ALIAS_TABLE:
            if base == alias:
                canonical = self._keys.get(_base(target))
                return {canonical} if canonical else set()
        hits = set()
        for variant in _variants(raw):
            canonical = self._keys.get(variant)
            if canonical:
                hits.add(canonical)
        return hits


def clean_person(raw):
    '''规整人名为若干候选（可能一人多名，如 马月/马玉）'''
    text = re.sub(r'\s+', '', _text(raw))
    if not text or text in _PLACEHOLDERS:
        return []
    for suffix in _SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
    for prefix in _PREFIXES:
        if text.startswith(prefix) and len(text) > len(prefix) + 1:
            text = text[len(prefix):]
    results = []
    for part in re.split('[' + re.escape(_SPLIT_CHARS) + ']', text):
        part = part.strip()
        if not part or part in _PLACEHOLDERS:
            continue
        if len(part) > 20 or re.search(r'[0-9A-Za-z]', part):
            continue
        results.append(part)
    return results


def canonical_modules():
    '''系统正式模块名：国家映射表 + 商贸模块 + 改造'''
    from dashboards.contract_completion.models import CountryMapping, TradeModuleData

    names = {item.module_name for item in CountryMapping.query.all() if item.module_name}
    names.update(item.module_name for item in TradeModuleData.query.all() if item.module_name)
    names.add(GAZAO_MODULE)
    return names


def latest_mapping_file():
    '''最新的「国家-市场-业务员」表；找不到返回 None'''
    if not os.path.isdir(MAPPING_DIR):
        return None
    candidates = []
    for name in os.listdir(MAPPING_DIR):
        if not name.startswith(MAPPING_PREFIX):
            continue
        if not name.lower().endswith(('.xlsx', '.xls')):
            continue
        path = os.path.join(MAPPING_DIR, name)
        try:
            candidates.append((os.path.getmtime(path), path))
        except OSError:
            continue
    if not candidates:
        return None
    return max(candidates)[1]


def _load_sheet_rows(path):
    '''读取工作簿所有 sheet → {sheet 名: 二维文本列表}'''
    if path.lower().endswith('.xls'):
        import xlrd
        book = xlrd.open_workbook(path)
        result = {}
        for sheet in book.sheets():
            result[sheet.name] = [
                [_text(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
                for r in range(sheet.nrows)
            ]
        return result

    import openpyxl
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        result = {}
        for name in workbook.sheetnames:
            result[name] = [
                [_text(cell) for cell in row]
                for row in workbook[name].iter_rows(values_only=True)
            ]
        return result
    finally:
        workbook.close()


def _header_index(rows):
    '''表头所在行：表格首行常是标题，真正的表头在第 2 行'''
    for index in range(min(2, len(rows))):
        if any(cell == '模块' for cell in rows[index]):
            return index
    return None


def _is_module_row(value):
    if not value or value == '模块':
        return False
    return not any(part in value for part in _SKIP_MODULE_PARTS)


def extract_person_modules(path, resolver=None):
    '''从业务员表里抽出 人名 → 正式模块名集合，以及未解析的模块写法

    模主对应关系以「任命令模块-模主」为准：这张表里命中的人只认它的结果，
    即使模块名没认出来也不算其它 sheet 的推断值（宁可漏，不可错）；
    其余 sheet 只用来补这张表没覆盖到的人。
    '''
    resolver = resolver or ModuleResolver(canonical_modules())
    authoritative = {}
    fallback = {}
    authoritative_seen = set()
    unresolved = set()

    for sheet_name, rows in _load_sheet_rows(path).items():
        is_authoritative = sheet_name == AUTHORITATIVE_SHEET
        target = authoritative if is_authoritative else fallback
        header_index = _header_index(rows)
        if header_index is None:
            continue
        header = rows[header_index]
        module_col = None
        for index, cell in enumerate(header):
            if cell == '模块':
                module_col = index
                break
        if module_col is None:
            continue

        data_rows = rows[header_index + 1:]
        width = len(header)
        for row in data_rows:
            width = max(width, len(row))

        person_cols = []
        for index in range(width):
            if index == module_col:
                continue
            label = header[index] if index < len(header) else ''
            if label and (label in _SKIP_HEADER_EXACT
                          or any(part in label for part in _SKIP_HEADER_PARTS)):
                continue
            person_cols.append(index)
        if not person_cols:
            continue

        for row in data_rows:
            raw_module = row[module_col] if module_col < len(row) else ''
            if not _is_module_row(raw_module):
                continue
            modules = resolver.resolve(raw_module)
            if not modules:
                unresolved.add(raw_module)
                if is_authoritative:
                    for col in person_cols:
                        value = row[col] if col < len(row) else ''
                        for person in clean_person(value):
                            authoritative_seen.add(person)
                continue
            for col in person_cols:
                value = row[col] if col < len(row) else ''
                for person in clean_person(value):
                    if is_authoritative:
                        authoritative_seen.add(person)
                    target.setdefault(person, set()).update(modules)

    person2modules = dict(fallback)
    person2modules.update(authoritative)
    for person in authoritative_seen:
        person2modules.setdefault(person, set())

    return person2modules, unresolved, resolver


def load_person_modules(path=None):
    '''读取业务员表；表缺失时抛 FileNotFoundError'''
    path = path or latest_mapping_file()
    if not path:
        raise FileNotFoundError(
            '未找到「国家-市场-业务员」表，请先在「合同完成情况」模块上传该表'
        )
    person2modules, unresolved, resolver = extract_person_modules(path)
    return {
        'path': path,
        'person2modules': person2modules,
        'unresolved': unresolved,
        'resolver': resolver,
    }
