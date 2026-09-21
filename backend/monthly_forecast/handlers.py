'''
单月签排发填报 — 名单上传解析

名单格式（两种都支持）：
    A) DT号 + 人名            模块从「国家-市场-业务员」表里按人名自动解析
    B) DT号 + 人名 + 模块      名单自带的模块优先，覆盖自动解析结果

匹配规则：
    账号：先用 DT号/工号 精确匹配 user.username，再用 人名 匹配 user.real_name
    模块：名单自带「模块」列 → 用该列；否则 → 按人名去业务员表解析
        命中 1 个模块 → 写入
        命中 0 个模块 → 不进名单，写入报告（人工处理）
        命中多个模块 → 整条略过，写入报告（人工处理）
    平台里查不到账号（离职 / 未入职）→ 整条略过，写入报告

重要：本处理器只读匹配 user 表，只写 mf_user_scope，绝不写回 user / role 表。
'''
import csv
import os
from datetime import datetime

from models import db, User
from monthly_forecast import mapping

ACCOUNT_KEYS = ('DT号', '工号', '员工号', '账号', '用户名', 'username', 'account', 'dt')
NAME_KEYS = ('人名', '姓名', '名字', '员工姓名', 'name')
MODULE_KEYS = ('模块', 'module')


def _cell_text(value):
    if value is None:
        return ''
    return str(value).strip()


def _read_table(file_path):
    '''读取表格 → 二维列表（文本）'''
    lower = file_path.lower()
    if lower.endswith('.csv'):
        return _read_csv(file_path)
    if lower.endswith('.xls'):
        return _read_xls(file_path)
    return _read_xlsx(file_path)


def _read_csv(file_path):
    for encoding in ('utf-8-sig', 'gbk', 'utf-8'):
        try:
            with open(file_path, 'r', encoding=encoding, newline='') as handle:
                return [[_cell_text(c) for c in row] for row in csv.reader(handle)]
        except UnicodeDecodeError:
            continue
    raise ValueError('CSV 编码无法识别（试过 utf-8-sig / gbk / utf-8）')


def _read_xlsx(file_path):
    import openpyxl
    workbook = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    try:
        sheet = workbook.active
        return [[_cell_text(c) for c in row] for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _read_xls(file_path):
    import xlrd
    workbook = xlrd.open_workbook(file_path)
    sheet = workbook.sheet_by_index(0)
    rows = []
    for r in range(sheet.nrows):
        rows.append([_cell_text(sheet.cell_value(r, c)) for c in range(sheet.ncols)])
    return rows


def _find_col(header, keys):
    for index, cell in enumerate(header):
        text = cell.lower()
        for key in keys:
            if key.lower() in text:
                return index
    return None


def _lookup_user(account, name):
    '''只读匹配账号：先 DT号/工号（username），再 人名（real_name）'''
    if account:
        user = User.query.filter_by(username=account).first()
        if user is not None:
            return user
    if name:
        user = User.query.filter_by(real_name=name).first()
        if user is not None:
            return user
    return None


def _resolve_modules(raw_module, name, person2modules, resolver):
    '''返回 (正式模块名集合, 来源说明)'''
    if raw_module:
        return resolver.resolve(raw_module), '名单自带'
    hits = set()
    for person in mapping.clean_person(name):
        hits.update(person2modules.get(person, ()))
    return hits, '业务员表'


def import_scope(file_path):
    '''导入「用户 → 模块」名单（全量替换 mf_user_scope）'''
    from monthly_forecast.models import UserScope

    try:
        table = [row for row in _read_table(file_path) if any(cell for cell in row)]
    except Exception as exc:
        return {'success': False, 'message': '名单文件读取失败: %s' % exc, 'rows': 0}

    if not table:
        return {'success': False, 'message': '名单文件为空', 'rows': 0}

    header = table[0]
    col_account = _find_col(header, ACCOUNT_KEYS)
    col_name = _find_col(header, NAME_KEYS)
    col_module = _find_col(header, MODULE_KEYS)

    if col_account is None and col_name is None:
        return {
            'success': False,
            'message': '未找到「DT号」或「人名」列，请检查表头（需要 DT号 + 人名，模块列可选）',
            'rows': 0,
        }

    try:
        info = mapping.load_person_modules()
    except Exception as exc:
        return {'success': False, 'message': '读取「国家-市场-业务员」表失败: %s' % exc, 'rows': 0}

    person2modules = info['person2modules']
    resolver = info['resolver']

    UserScope.query.delete()
    seen = set()
    assigned = 0
    skipped_empty = 0
    no_account = []
    no_module = []
    multi_module = []
    bad_module = []

    for row in table[1:]:
        account = _cell_text(row[col_account]) if (col_account is not None and col_account < len(row)) else ''
        name = _cell_text(row[col_name]) if (col_name is not None and col_name < len(row)) else ''
        raw_module = _cell_text(row[col_module]) if (col_module is not None and col_module < len(row)) else ''
        if not account and not name:
            skipped_empty += 1
            continue

        user = _lookup_user(account, name)
        if user is None:
            no_account.append((account or name, name, raw_module))
            continue

        modules, _source = _resolve_modules(raw_module, name, person2modules, resolver)
        if not modules:
            if raw_module:
                bad_module.append((name or account, raw_module))
            else:
                no_module.append((name or account, account))
            continue
        if len(modules) > 1:
            multi_module.append((name or account, ' / '.join(sorted(modules))))
            continue

        module_name = sorted(modules)[0]
        key = (user.id, module_name)
        if key in seen:
            continue
        seen.add(key)
        db.session.add(UserScope(user_id=user.id, match_key=account or name, module_name=module_name))
        assigned += 1

    db.session.commit()

    report_path = _write_report(
        assigned, skipped_empty, no_account, no_module,
        multi_module, bad_module, sorted(info['unresolved']), info['path'],
    )

    parts = ['导入 %d 条' % assigned]
    if no_account:
        parts.append('%d 条平台无此账号' % len(no_account))
    if no_module:
        parts.append('%d 条查不到模块' % len(no_module))
    if multi_module:
        parts.append('%d 条对应多个模块已略过' % len(multi_module))
    if bad_module:
        parts.append('%d 条模块名无法识别' % len(bad_module))
    if skipped_empty:
        parts.append('%d 行空数据跳过' % skipped_empty)

    return {
        'success': True,
        'message': '，'.join(parts),
        'rows': assigned,
        'no_account': len(no_account),
        'no_module': len(no_module),
        'multi_module': len(multi_module),
        'bad_module': len(bad_module),
        'report_path': report_path,
        'source': os.path.basename(info['path']),
    }


def _write_report(assigned, skipped_empty, no_account, no_module,
                  multi_module, bad_module, unresolved, source_path):
    '''把需要人工处理的明细写入报告文件'''
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(base, 'uploads', 'monthly_forecast')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'scope_report.txt')

    line = '=' * 56
    lines = [
        '单月签排发填报 名单导入报告 - %s' % datetime.now().strftime('%Y-%m-%d %H:%M'),
        line,
        '模块来源文件：%s' % os.path.basename(source_path or ''),
        '成功写入 mf_user_scope: %d 条' % assigned,
        '空数据跳过: %d 行' % skipped_empty,
        '平台无此账号: %d 条' % len(no_account),
        '查不到模块: %d 条' % len(no_module),
        '对应多个模块已略过: %d 条' % len(multi_module),
        '模块名无法识别: %d 条' % len(bad_module),
        '',
    ]

    if no_account:
        lines.append('[平台无此账号] 可能已离职或尚未入职，本模块不做处理')
        lines.append('%-14s %-10s %s' % ('名单原文', '人名', '名单里的模块'))
        lines.append('-' * 56)
        for key, name, module in no_account:
            lines.append('%-14s %-10s %s' % (key, name, module))
        lines.append('')

    if no_module:
        lines.append('[查不到模块] 人名在业务员表里没有对应模块，请人工补')
        lines.append('%-10s %s' % ('人名', 'DT号'))
        lines.append('-' * 56)
        for name, account in no_module:
            lines.append('%-10s %s' % (name, account))
        lines.append('')

    if multi_module:
        lines.append('[对应多个模块] 按约定整条略过，请人工确认后单独添加')
        lines.append('%-10s %s' % ('人名', '对应模块'))
        lines.append('-' * 56)
        for name, modules in multi_module:
            lines.append('%-10s %s' % (name, modules))
        lines.append('')

    if bad_module:
        lines.append('[模块名无法识别] 名单自带的模块名在系统里不存在')
        lines.append('%-10s %s' % ('人名', '名单里的模块'))
        lines.append('-' * 56)
        for name, module in bad_module:
            lines.append('%-10s %s' % (name, module))
        lines.append('')

    if unresolved:
        lines.append('[业务员表里对不上系统模块的写法] 建议在源表里改成系统正式名')
        for item in unresolved:
            lines.append('  ' + item)
        lines.append('')

    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))
    return path
