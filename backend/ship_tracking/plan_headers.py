# -*- coding: utf-8 -*-
"""计划导入表头识别。

按表头名称（而不是列字母）定位字段，兼容新旧两种计划文件格式：

- 新格式（2026-11 起）：A 模块 / B 合同号 / C 梯号 / D 项目名称 / E 台数 /
  F 金额(万元) / G 来源 / H 填报人 / I 排产完工日期 / J 整梯发货日期 /
  K 业务预计发货时间 / L 备注
- 旧格式：在「整梯发货日期」之后还有「7日前发货」列，「业务预计发货时间」列位置也更靠右

列顺序变化、插入无关列不影响解析；表头缺失或必需列缺失会抛 PlanHeaderError，
由预览接口返回 400，避免按错误列位静默导入。
"""
import re
import unicodedata

from ship_tracking.excel_reader import column_index, read_sheet_rows

FIELD_LABELS = {
    'module': '模块',
    'contract_no': '合同号',
    'ladder': '梯号',
    'project_name': '项目名称',
    'unit_count': '台数',
    'amount_wan': '金额(万元)',
    'source': '来源',
    'reporter': '填报人',
    'schedule_finish_date': '排产完工日期',
    'whole_ship_date': '整梯发货日期',
    'business_expected': '业务预计发货时间',
    'seven_day': '7日前发货',
    'contract_amount_rmb': '合同额',
    'remark': '备注',
}

HEADER_ALIASES = {
    'module': ('模块', '模块名称', '模块名', '所属模块', '模块归属'),
    'contract_no': ('合同号', '合同编号', '合同号码', '合同编码'),
    'ladder': ('梯号', '梯号号', '梯号编号', '电梯梯号'),
    'project_name': ('项目名称', '项目名', '项目', '工程名称'),
    'unit_count': ('台数', '数量', '台量', '电梯台数', '发货台数'),
    'amount_wan': ('金额(万元)', '金额/万元', '金额(万)', '金额万元',
                   '合同金额(万元)', '合同金额(万)'),
    'source': ('来源', '数据来源', '计划来源', '来源类型'),
    'reporter': ('填报人', '填表人', '填报人员', '业务填报人', '汇报人'),
    'schedule_finish_date': ('排产完工日期', '排产完工', '排产完成日期', '排产完成',
                             '完工日期', '计划完工日期', '排产结束日期'),
    'whole_ship_date': ('整梯发货日期', '整梯发货', '整梯发货时间', '整梯发运日期',
                        '整梯发运时间', '整梯发运'),
    'business_expected': ('业务预计发货时间', '业务预计发货日期', '业务预计时间',
                          '业务预计日期', '业务预计发货', '预计发货时间', '预计发货日期',
                          '预计发货', '用户预计发货时间', '业务预计发运时间'),
    'seven_day': ('7日前发货', '7日前发货日期', '7日前发货时间', '7日前',
                  '七日前发货', '前7日发货', '7天前发货', '提前7日发货'),
    'contract_amount_rmb': ('合同额', '合同金额', '合同额(元)', '合同金额(元)',
                            '合同额(RMB)', '合同金额(RMB)', '合同额(人民币)',
                            '合同金额(人民币)'),
    'remark': ('备注', '备注说明', '原因备注', '未按时发货原因'),
}

# 已知但不参与计划导入的列：识别到只做提示，不阻断导入。
KNOWN_IGNORED_ALIASES = {
    '实际发货日期': '实际发货', '实际发货时间': '实际发货', '实际发货': '实际发货',
    '订舱状态': '订舱', '订舱情况': '订舱',
    '订舱审核状态': '订舱审核', '审核状态': '订舱审核',
    '序号': '辅助列', '计划月份': '辅助列',
    '当前节点': '订舱', '国家': '辅助列', '区域': '辅助列', '大区': '辅助列',
}

REQUIRED_FIELDS = ('ladder', 'contract_no')
DATE_FIELDS = ('business_expected', 'seven_day')
OPTIONAL_FIELDS = ('module', 'project_name', 'unit_count', 'amount_wan', 'source',
                   'reporter', 'schedule_finish_date', 'whole_ship_date',
                   'contract_amount_rmb', 'remark')

HEADER_SCAN_LIMIT = 10


def normalize_header_key(value):
    """表头归一化：全角转半角、去空白/不可见字符、去首尾符号。"""
    text = unicodedata.normalize('NFKC', str(value or ''))
    text = text.replace('　', ' ')
    text = re.sub(r'[\s​﻿ ]+', '', text)
    return text.strip('*:：')


def _build_alias_index():
    index = {}
    for field, names in HEADER_ALIASES.items():
        for name in names:
            key = normalize_header_key(name)
            existing = index.get(key)
            if existing and existing != field:
                raise RuntimeError('计划表头别名冲突：%s 同时属于 %s 和 %s' % (name, existing, field))
            index[key] = field
    return index


_ALIAS_INDEX = _build_alias_index()
_IGNORED_INDEX = {normalize_header_key(key): value
                  for key, value in KNOWN_IGNORED_ALIASES.items()}


class PlanHeaderError(ValueError):
    """表头校验失败：预览接口据此返回 400 和结构化细节。"""

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


class PlanColumnMap(object):
    def __init__(self, fields, labels, header_row, header_format, recognized,
                 ignored, unknown, missing_optional, data_row_count):
        self.fields = dict(fields)
        self.labels = dict(labels)
        self.header_row = header_row
        self.format = header_format
        self.recognized = list(recognized)
        self.ignored = list(ignored)
        self.unknown = list(unknown)
        self.missing_optional = list(missing_optional)
        self.data_row_count = data_row_count

    def has(self, field):
        return field in self.fields

    def letter(self, field):
        return self.fields.get(field, '')

    def letters(self):
        return dict(self.fields)

    def value(self, row, field):
        letter = self.fields.get(field)
        if not letter:
            return ''
        return row.get(letter)

    def to_dict(self):
        return {
            'row_number': self.header_row,
            'format': self.format,
            'recognized': self.recognized,
            'ignored': self.ignored,
            'unknown': self.unknown,
            'missing_optional': self.missing_optional,
            'fields': dict(self.fields),
            'data_row_count': self.data_row_count,
        }


def _cell_text(row, letter):
    value = row.get(letter)
    if value is None:
        return ''
    text = str(value)
    text = text.replace('　', ' ').strip()
    return re.sub(r'\s+', ' ', text)


def _find_header_row(rows):
    for row_number, row in rows:
        for value in row.values():
            key = normalize_header_key(value)
            if key and key in _ALIAS_INDEX and _ALIAS_INDEX[key] == 'ladder':
                return row_number, row
    return None, None


def map_plan_headers(row_number, header_row, data_row_count=0):
    entries = []
    seen_headers = {}
    duplicate_headers = []
    for letter in sorted(header_row, key=column_index):
        label = _cell_text(header_row, letter)
        key = normalize_header_key(label)
        if not key:
            continue
        if key in seen_headers:
            duplicate_headers.append({
                'key': key,
                'header': label,
                'letters': [seen_headers[key], letter],
            })
            continue
        seen_headers[key] = letter
        entries.append((letter, label, key))

    field_hits = {}
    ignored = []
    unknown = []
    for letter, label, key in entries:
        field = _ALIAS_INDEX.get(key)
        if field:
            field_hits.setdefault(field, []).append({'letter': letter, 'header': label})
        elif key in _IGNORED_INDEX:
            ignored.append({'letter': letter, 'header': label,
                            'category': _IGNORED_INDEX[key]})
        else:
            unknown.append({'letter': letter, 'header': label})

    recognized = []
    duplicate_fields = []
    for field in sorted(field_hits, key=lambda name: column_index(field_hits[name][0]['letter'])):
        hits = field_hits[field]
        if len(hits) > 1:
            duplicate_fields.append({
                'field': field,
                'label': FIELD_LABELS.get(field, field),
                'columns': hits,
            })
            continue
        recognized.append({
            'field': field,
            'label': FIELD_LABELS.get(field, field),
            'header': hits[0]['header'],
            'letter': hits[0]['letter'],
        })

    details = {
        'header_row': row_number,
        'duplicate_headers': duplicate_headers,
        'duplicate_fields': duplicate_fields,
        'unknown': unknown,
        'ignored': ignored,
    }

    if duplicate_headers:
        item = duplicate_headers[0]
        raise PlanHeaderError(
            '表头重名：第 %s 列和第 %s 列都是「%s」，请只保留一列。'
            % ('/'.join(item['letters']), item['letters'][-1], item['header']),
            details,
        )
    if duplicate_fields:
        item = duplicate_fields[0]
        pairs = '、'.join('第%s列「%s」' % (hit['letter'], hit['header']) for hit in item['columns'])
        raise PlanHeaderError(
            '表头字段重复：%s 都被识别为「%s」，请只保留一列。' % (pairs, item['label']),
            details,
        )

    missing_required = []
    for field in REQUIRED_FIELDS:
        if field not in {item['field'] for item in recognized}:
            missing_required.append({
                'field': field,
                'label': FIELD_LABELS[field],
                'aliases': list(HEADER_ALIASES[field]),
            })
    if missing_required:
        labels = '、'.join(
            '「%s」（可用写法：%s）' % (item['label'], '、'.join(item['aliases']))
            for item in missing_required
        )
        details['missing_required'] = missing_required
        raise PlanHeaderError('计划表头校验失败：缺少必需列 %s。' % labels, details)

    if not any(item['field'] in DATE_FIELDS for item in recognized):
        details['missing_date'] = list(DATE_FIELDS)
        raise PlanHeaderError(
            '计划表头校验失败：需要「业务预计发货时间」或「7日前发货」至少一列，'
            '否则所有梯号都会变成未提交待发货。',
            details,
        )

    present_fields = {item['field'] for item in recognized}
    missing_optional = [
        {'field': field, 'label': FIELD_LABELS[field]}
        for field in OPTIONAL_FIELDS
        if field not in present_fields and field != 'contract_amount_rmb'
    ]
    details['missing_optional'] = missing_optional

    if 'business_expected' in present_fields and 'seven_day' in present_fields:
        header_format = 'hybrid'
    elif 'business_expected' in present_fields:
        header_format = 'new'
    else:
        header_format = 'legacy'

    fields = {item['field']: item['letter'] for item in recognized}
    labels = {item['field']: item['header'] for item in recognized}
    return PlanColumnMap(
        fields=fields,
        labels=labels,
        header_row=row_number,
        header_format=header_format,
        recognized=recognized,
        ignored=ignored,
        unknown=unknown,
        missing_optional=missing_optional,
        data_row_count=data_row_count,
    )


def read_plan_table(path, scan_limit=HEADER_SCAN_LIMIT):
    """定位表头并返回 (列映射, 数据行列表, 统计)。

    先扫描前 scan_limit 行找表头（兼容标题行），再从表头下一行开始读取数据。
    同一文件会打开两次，但读取器是轻量流式实现，开销可接受。
    """
    scanned = list(read_sheet_rows(path, min_row=1, max_row=scan_limit))
    header_row_number, header_row = _find_header_row(scanned)
    if header_row is None:
        first_rows = [
            {'row': number, 'values': [_cell_text(row, letter) for letter in sorted(row, key=column_index)]}
            for number, row in scanned[:3]
        ]
        raise PlanHeaderError(
            '未找到表头：前 %d 行没有包含「梯号」的表头行。请确认文件使用导入模板，'
            '表头行需包含「梯号」「合同号」和「业务预计发货时间」。' % scan_limit,
            {'scanned_rows': first_rows},
        )

    data_rows = [
        (number, row)
        for number, row in read_sheet_rows(path, min_row=header_row_number + 1)
        if any(_cell_text(row, letter) for letter in row)
    ]
    columns = map_plan_headers(header_row_number, header_row, data_row_count=len(data_rows))
    return columns, data_rows, {
        'header_row': header_row_number,
        'data_row_count': len(data_rows),
    }
