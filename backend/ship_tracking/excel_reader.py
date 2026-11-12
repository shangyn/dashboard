"""
轻量 XLSX 读取器。

本模块的计划源文件带有约 1.8 亿字节的外部链接缓存，openpyxl 会在加载阶段
解析这些与业务无关的部件，导致几十秒甚至更长时间阻塞。这里只读取：
- workbook.xml / workbook.xml.rels：确定当前激活的可见工作表
- sharedStrings.xml：共享字符串
- 目标 worksheet XML：流式读取单元格缓存值

它不计算公式、不加载样式、不解析外部链接；公式单元格读取 Excel 上次保存的缓存值。
"""
import datetime as _dt
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL_NS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PKG_REL_NS = '{http://schemas.openxmlformats.org/package/2006/relationships}'

MAX_RANGE_EXPAND = 300


def column_index(letters):
    value = 0
    for char in letters:
        value = value * 26 + ord(char.upper()) - 64
    return value


def cell_ref_parts(ref):
    match = re.match(r'^([A-Za-z]+)(\d+)$', ref or '')
    if not match:
        return None, None
    return match.group(1).upper(), int(match.group(2))


def normalize_text(value):
    if value is None:
        return ''
    text = str(value).replace('\u3000', ' ').strip()
    return re.sub(r'\s+', ' ', text)


def parse_number(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = normalize_text(value).replace(',', '').replace('，', '')
    if text in ('', '-', '--', '/', '#N/A', '#VALUE!', '#REF!', 'N/A'):
        return None
    text = text.replace('￥', '').replace('¥', '')
    try:
        return float(text)
    except Exception:
        return None


def parse_excel_date(value):
    """把常见 Excel 日期/日期序列号转为 date；明显异常值返回 None。"""
    if value is None or value == '' or isinstance(value, bool):
        return None
    if isinstance(value, _dt.datetime):
        result = value.date()
    elif isinstance(value, _dt.date):
        result = value
    else:
        text = normalize_text(value)
        if not text:
            return None
        if any(token in text for token in ('周', '星期', '待定', '未定', '#', 'N/A')):
            return None
        result = None
        match = re.match(r'^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?$', text)
        if match:
            try:
                result = _dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None
        else:
            match = re.match(r'^(\d{4})(\d{2})(\d{2})$', text)
            if match:
                try:
                    result = _dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                except ValueError:
                    return None
            else:
                number = parse_number(text)
                if number is not None and 20000 <= number <= 80000:
                    try:
                        result = (_dt.date(1899, 12, 30) + _dt.timedelta(days=int(number)))
                    except Exception:
                        return None
                elif number is not None and number not in (0,):
                    return None
        if result is None or not (2000 <= result.year <= 2100):
            return None
    if not (2000 <= result.year <= 2100):
        return None
    return result


def canonical_ladder(value):
    text = normalize_text(value).upper()
    text = text.replace('＃', '#').replace('／', '/')
    text = text.replace(' ', '')
    return text


def natural_ladder_key(value):
    """Return a key that sorts ladder numbers numerically (1#, 2#, 10#)."""
    text = canonical_ladder(value)
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in re.findall(r'\d+|\D+', text)
    )


def expand_ladder_ranges(value, contract_no=''):
    """展开 1#-3# / 1-3# 一类区间梯号；普通梯号原样返回。"""
    text = canonical_ladder(value)
    if not text:
        return []
    match = re.match(r'^(.*?/)(\d+)\s*#?\s*[-~～至]\s*(\d+)\s*#?$', text)
    if not match:
        prefix = canonical_ladder(contract_no) + '/' if contract_no and '/' not in text else ''
        match = re.match(r'^(\d+)\s*#?\s*[-~～至]\s*(\d+)\s*#?$', text)
        if not match:
            return [text]
        start, end = int(match.group(1)), int(match.group(2))
        prefix = canonical_ladder(contract_no) + '/'
    else:
        prefix = match.group(1)
        start, end = int(match.group(2)), int(match.group(3))
    if start > end:
        start, end = end, start
    if end - start + 1 > MAX_RANGE_EXPAND:
        return [text]
    return ['%s%d#' % (prefix, number) for number in range(start, end + 1)]


def split_ladder_values(value, contract_no=''):
    """处理逗号分隔梯号，同时展开区间。"""
    text = normalize_text(value)
    if not text:
        return []
    parts = [part for part in re.split(r'[,，;；\n]+', text) if normalize_text(part)]
    result = []
    seen = set()
    for part in parts:
        for ladder in expand_ladder_ranges(part, contract_no=contract_no):
            if ladder not in seen:
                seen.add(ladder)
                result.append(ladder)
    return result


def _ladder_number_range(value):
    text = normalize_text(value).replace(' ', '')
    match = re.fullmatch(r'(\d+)#?[-~～至—–](\d+)#?', text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.fullmatch(r'(\d+)#?', text)
    if match:
        number = int(match.group(1))
        return number, number
    return None


def parse_ladder_batch(value, contract_no=''):
    """解析手工录入的多梯号，返回规范化梯号、错误和警告。"""
    text = normalize_text(value)
    if not text:
        return {'ladders': [], 'errors': ['请输入梯号'], 'warnings': []}
    text = (text.replace('，', ',').replace('；', ';').replace('、', ',')
            .replace('＃', '#').replace('／', '/'))
    text = re.sub(r'\s*/\s*', '/', text)
    text = re.sub(r'\s*([-~～至—–])\s*', r'\1', text)
    tokens = [part for part in re.split(r'[,;\s]+', text) if part.strip()]
    contract_base = canonical_ladder(contract_no).rstrip('/')
    explicit_bases = []
    for token in tokens:
        token = canonical_ladder(token)
        if '/' in token:
            base = canonical_ladder(token.rsplit('/', 1)[0]).rstrip('/')
            if base:
                explicit_bases.append(base)
    active_base = explicit_bases[0] if explicit_bases else contract_base

    ladders = []
    errors = []
    warnings = []
    seen = set()
    duplicate_count = 0
    for token in tokens:
        token = canonical_ladder(token)
        if not token:
            continue
        if '/' in token:
            base_text, suffix = token.rsplit('/', 1)
            base = canonical_ladder(base_text).rstrip('/')
            if base:
                active_base = base
            else:
                base = active_base
            if not base:
                errors.append('梯号 %s 缺少完整前缀' % token)
                continue
            numbers = _ladder_number_range(suffix)
            if numbers is None:
                candidates = [token]
            else:
                start, end = numbers
                if start > end:
                    start, end = end, start
                if end - start + 1 > MAX_RANGE_EXPAND:
                    errors.append('梯号 %s 展开数量超过 %d 台' % (token, MAX_RANGE_EXPAND))
                    continue
                candidates = ['%s/%d#' % (base, number) for number in range(start, end + 1)]
        else:
            numbers = _ladder_number_range(token)
            if numbers is None:
                candidates = [token]
            else:
                if not active_base:
                    errors.append('梯号 %s 缺少完整前缀，请补充合同号或完整梯号' % token)
                    continue
                start, end = numbers
                if start > end:
                    start, end = end, start
                if end - start + 1 > MAX_RANGE_EXPAND:
                    errors.append('梯号 %s 展开数量超过 %d 台' % (token, MAX_RANGE_EXPAND))
                    continue
                candidates = ['%s/%d#' % (active_base, number)
                              for number in range(start, end + 1)]
        for ladder in candidates:
            ladder = canonical_ladder(ladder)
            if not ladder:
                continue
            if ladder in seen:
                duplicate_count += 1
                continue
            seen.add(ladder)
            ladders.append(ladder)
    if duplicate_count:
        warnings.append('已自动去重 %d 个重复梯号' % duplicate_count)
    if not ladders and not errors:
        errors.append('未识别到有效梯号')
    return {'ladders': ladders, 'errors': errors, 'warnings': warnings}


class XlsxReader(object):
    def __init__(self, path):
        self.path = path
        self.archive = zipfile.ZipFile(path)
        self.shared_strings = []
        self._load_shared_strings()
        self.sheet_path = self._resolve_sheet_path()

    def close(self):
        try:
            self.archive.close()
        except Exception:
            pass

    def _load_shared_strings(self):
        name = 'xl/sharedStrings.xml'
        if name not in self.archive.namelist():
            return
        with self.archive.open(name) as handle:
            for _event, element in ET.iterparse(handle, events=('end',)):
                if element.tag == NS + 'si':
                    self.shared_strings.append(self._text_of(element))
                    element.clear()

    def _text_of(self, element):
        parts = []
        for node in element.iter():
            if node.tag == NS + 't':
                parts.append(node.text or '')
        return ''.join(parts)

    def _resolve_sheet_path(self):
        workbook = ET.fromstring(self.archive.read('xl/workbook.xml'))
        sheets_node = workbook.find(NS + 'sheets')
        sheets = list(sheets_node) if sheets_node is not None else []
        if not sheets:
            raise ValueError('Excel 中没有工作表')

        active_tab = 0
        views = workbook.find(NS + 'bookViews')
        if views is not None:
            view = views.find(NS + 'workbookView')
            if view is not None:
                try:
                    active_tab = int(view.get('activeTab') or 0)
                except ValueError:
                    active_tab = 0

        target = None
        if 0 <= active_tab < len(sheets):
            candidate = sheets[active_tab]
            if (candidate.get('state') or 'visible') == 'visible':
                target = candidate
        if target is None:
            for sheet in sheets:
                if (sheet.get('state') or 'visible') == 'visible':
                    target = sheet
                    break
        if target is None:
            target = sheets[0]

        rel_id = target.get(REL_NS + 'id')
        rel_path = 'xl/_rels/workbook.xml.rels'
        if rel_id and rel_path in self.archive.namelist():
            rels = ET.fromstring(self.archive.read(rel_path))
            for rel in rels:
                if rel.get('Id') == rel_id:
                    target_path = rel.get('Target') or ''
                    if target_path.startswith('/'):
                        return target_path.lstrip('/')
                    return posixpath.normpath(posixpath.join('xl', target_path))
        return 'xl/worksheets/sheet1.xml'

    def iter_rows(self, min_row=1, max_row=None):
        with self.archive.open(self.sheet_path) as handle:
            for _event, row in ET.iterparse(handle, events=('end',)):
                if row.tag != NS + 'row':
                    continue
                row_number = int(row.get('r') or 0)
                if row_number < min_row:
                    row.clear()
                    continue
                if max_row and row_number > max_row:
                    break
                values = {}
                for cell in row.findall(NS + 'c'):
                    ref = cell.get('r') or ''
                    letters, _number = cell_ref_parts(ref)
                    if not letters:
                        continue
                    values[letters] = self._cell_value(cell)
                yield row_number, values
                row.clear()

    def _cell_value(self, cell):
        cell_type = cell.get('t') or ''
        if cell_type == 'inlineStr':
            inline = cell.find(NS + 'is')
            return self._text_of(inline) if inline is not None else ''
        value_node = cell.find(NS + 'v')
        raw = value_node.text if value_node is not None and value_node.text is not None else ''
        if cell_type == 's':
            try:
                return self.shared_strings[int(raw)]
            except (ValueError, IndexError):
                return ''
        if cell_type == 'str':
            return raw
        if cell_type == 'e':
            return raw
        if cell_type == 'b':
            return 'TRUE' if raw == '1' else 'FALSE'
        return raw


def column_letters(index):
    value = int(index) + 1
    result = ''
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def read_sheet_rows(path, min_row=1, max_row=None):
    if str(path).lower().endswith('.xls'):
        for row in _read_xls_rows(path, min_row=min_row, max_row=max_row):
            yield row
        return
    reader = XlsxReader(path)
    try:
        for row in reader.iter_rows(min_row=min_row, max_row=max_row):
            yield row
    finally:
        reader.close()


def _read_xls_rows(path, min_row=1, max_row=None):
    import xlrd
    workbook = xlrd.open_workbook(path, on_demand=True)
    sheet = None
    for index in range(workbook.nsheets):
        candidate = workbook.sheet_by_index(index)
        if getattr(candidate, 'visibility', 0) == 0:
            sheet = candidate
            break
    if sheet is None:
        sheet = workbook.sheet_by_index(0)
    last_row = sheet.nrows if max_row is None else min(sheet.nrows, max_row)
    for row_index in range(max(min_row - 1, 0), last_row):
        values = {}
        for column_index in range(sheet.ncols):
            cell = sheet.cell(row_index, column_index)
            value = cell.value
            if cell.ctype == xlrd.XL_CELL_DATE:
                try:
                    value = xlrd.xldate.xldate_as_datetime(value, workbook.datemode).strftime('%Y-%m-%d')
                except Exception:
                    value = ''
            values[column_letters(column_index)] = value
        yield row_index + 1, values
    workbook.release_resources()
