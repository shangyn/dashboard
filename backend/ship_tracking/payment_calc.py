# -*- coding: utf-8 -*-
"""未满 100% 回款比例计算核心。

本模块只做文件解析、回款分摊和比例计算，不写数据库。
数据库读写、后台任务和页面状态由 payment_service.py 负责。
"""
import math
import os
import re
from collections import defaultdict

import pandas as pd

from ship_tracking.excel_reader import canonical_ladder, normalize_text


RMB_CURRENCIES = {'人民币', '人民币元', 'CNY', 'RMB'}
CURRENCY_ALIAS = {
    '美金': '美元',
    'USD': '美元',
    'US$': '美元',
    '澳币': '澳元',
    'AUD': '澳元',
    'EUR': '欧元',
    'GBP': '英镑',
    'SGD': '新元',
    'HKD': '港元',
    'JPY': '日元',
    '人民币元': '人民币',
    'CNY': '人民币',
    'RMB': '人民币',
}
CURRENCY_NAMES = [
    '西非法郎元', '人民币', '美元', '美金', '欧元', '澳元', '澳币',
    '英镑', '新元', '港元', '日元', 'USD', 'US$', 'AUD', 'EUR',
    'GBP', 'SGD', 'HKD', 'JPY', 'CNY', 'RMB',
]
_CUR_PATTERN = '|'.join(re.escape(name) for name in sorted(CURRENCY_NAMES, key=len, reverse=True))

_RE_CONTRACT = re.compile(r'(D[HY]T-\d{5,6}[TAEC]?)', re.IGNORECASE)
_RE_RANGE = re.compile(r'(\d+)\s*#?\s*[-~～至]\s*(\d+)\s*#?')
_RE_SINGLE = re.compile(r'(\d+)\s*#')
_RE_ADJUST = re.compile(r'原.{0,30}?后调至')
_RE_FILL_THEN_REST = re.compile(
    r'(.+?)(?:回满|回款\s*100(?:\.0+)?\s*%)\s*[，,;；]\s*'
    r'(?:剩余|剩下)(?:放|分到|分给|转至|转|的)?\s*(.+)'
)
_RE_REMARK = re.compile(
    r'折合\s*(?:(?P<amt1>\d+(?:\.\d+)?)\s*(?P<cur1>' + _CUR_PATTERN + r')'
    r'|(?P<cur2>' + _CUR_PATTERN + r')\s*(?P<amt2>\d+(?:\.\d+)?))'
)
_SKIP_CONTRACT_VALUES = {'见拆分', 'NAN', 'NONE', 'NAN', ''}
_RE_CONTRACT_COMPACT = re.compile(r'^(D[HY]T)(\d{5,6}[TAEC]?)$', re.IGNORECASE)

MAX_RANGE_EXPAND = 300


def clean_text(value):
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except Exception:
        pass
    return normalize_text(value)


def normalize_contract_no(value):
    text = clean_text(value).upper()
    if not text:
        return ''
    match = _RE_CONTRACT_COMPACT.match(text)
    if match:
        return '%s-%s' % (match.group(1), match.group(2))
    return text


def clean_contract(value):
    text = clean_text(value)
    if not text:
        return ''
    if text.upper() in _SKIP_CONTRACT_VALUES:
        return ''
    return normalize_contract_no(text)


def to_float(value):
    try:
        if value is None or value == '':
            return 0.0
        if isinstance(value, bool):
            return 0.0
        return float(str(value).replace(',', '').replace('，', '').strip())
    except (TypeError, ValueError):
        return 0.0


def extract_contract(value):
    text = clean_text(value)
    if not text:
        return ''
    match = _RE_CONTRACT.search(text)
    return normalize_contract_no(match.group(1)) if match else ''


def normalize_currency(value):
    text = clean_text(value)
    if not text:
        return ''
    text = CURRENCY_ALIAS.get(text, text)
    if text in RMB_CURRENCIES or text == '人民币':
        return '人民币'
    return text


def is_rmb(currency):
    return normalize_currency(currency) == '人民币'


def parse_ladder_numbers(value):
    text = clean_text(value)
    if not text:
        return []
    text = _RE_CONTRACT.sub(' ', text)
    numbers = set()
    for match in _RE_RANGE.finditer(text):
        start, end = int(match.group(1)), int(match.group(2))
        if start > end:
            start, end = end, start
        if end - start + 1 > MAX_RANGE_EXPAND:
            continue
        numbers.update(range(start, end + 1))
    text = _RE_RANGE.sub(' ', text)
    for match in _RE_SINGLE.finditer(text):
        numbers.add(int(match.group(1)))
    return sorted(numbers)


def parse_fill_then_rest(value):
    text = clean_text(value)
    if not text:
        return None
    match = _RE_FILL_THEN_REST.search(text)
    if not match:
        return None
    fill_numbers = parse_ladder_numbers(match.group(1))
    rest_numbers = parse_ladder_numbers(match.group(2))
    if fill_numbers and rest_numbers:
        return fill_numbers, rest_numbers
    return None


def has_adjust_remark(value):
    text = clean_text(value)
    return bool(text and _RE_ADJUST.search(text))


def parse_remark_parts(value):
    text = clean_text(value)
    if not text:
        return {}
    parts = {}
    for match in _RE_REMARK.finditer(text):
        if match.group('amt1') is not None:
            currency = normalize_currency(match.group('cur1'))
            amount = float(match.group('amt1'))
        else:
            currency = normalize_currency(match.group('cur2'))
            amount = float(match.group('amt2'))
        if currency:
            parts[currency] = round(parts.get(currency, 0.0) + amount, 6)
    return parts


def _resolve_usecols(filepath, sheet, needed_names, header=0, engine=None):
    kwargs = {'sheet_name': sheet, 'nrows': 0, 'header': header}
    if engine:
        kwargs['engine'] = engine
    try:
        head = pd.read_excel(filepath, **kwargs)
    except Exception:
        return None
    actual_map = {str(column).strip(): column for column in head.columns}
    result = []
    for name in needed_names:
        if name is None:
            continue
        key = str(name).strip()
        if key in actual_map:
            result.append(actual_map[key])
    return result or None


def _rename_std(df, mapping):
    actual_map = {str(column).strip(): column for column in df.columns}
    rename_map = {}
    for std_name, source_name in mapping.items():
        if source_name is None:
            continue
        key = str(source_name).strip()
        if key in actual_map:
            rename_map[actual_map[key]] = std_name
    return df.rename(columns=rename_map)


def read_table_b(filepath, config):
    frames = []
    for year, col_map in config['table_b']['sheets'].items():
        needed = [
            col_map.get('contract_col'), col_map.get('tid_col'),
            col_map.get('amount_col'), col_map.get('fee_col'),
            col_map.get('currency_col'), col_map.get('remark_col'),
        ]
        usecols = _resolve_usecols(filepath, str(year), needed)
        if not usecols:
            raise ValueError('外币回款台账 %s sheet 缺少必要列' % year)
        df = pd.read_excel(filepath, sheet_name=str(year), usecols=usecols)
        df = _rename_std(df, {
            'contract_no': col_map.get('contract_col'),
            'tid': col_map.get('tid_col'),
            'amount': col_map.get('amount_col'),
            'fee': col_map.get('fee_col'),
            'currency': col_map.get('currency_col'),
            'remark': col_map.get('remark_col'),
        })
        if 'amount' in df.columns:
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
        if 'fee' in df.columns:
            df['fee'] = pd.to_numeric(df['fee'], errors='coerce').fillna(0)
        if 'tid' in df.columns and 'contract_no' in df.columns:
            extracted = df['tid'].map(extract_contract)
            mask = extracted.ne('')
            df.loc[mask, 'contract_no'] = extracted[mask]
        keep = [c for c in ['contract_no', 'tid', 'amount', 'fee', 'currency', 'remark'] if c in df.columns]
        df = df[keep].copy()
        df['year'] = int(year)
        df['row_number'] = range(2, len(df) + 2)
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def read_table_e(filepath, config):
    cfg = config['table_e']
    header = cfg.get('header_rows', 2)
    engine = 'openpyxl' if str(filepath).lower().endswith('.xlsx') else 'xlrd'
    needed = [
        cfg.get('contract_col'), cfg.get('elevator_col'), cfg.get('type_col'),
        cfg.get('amount_col'), cfg.get('currency_col'),
    ]
    usecols = _resolve_usecols(filepath, 0, needed, header=header, engine=engine)
    if not usecols:
        raise ValueError('抵佣金明细缺少必要列')
    df = pd.read_excel(filepath, engine=engine, header=header, usecols=usecols)
    df = _rename_std(df, {
        'contract_no': cfg.get('contract_col'),
        'elevator_no': cfg.get('elevator_col'),
        'payment_type': cfg.get('type_col'),
        'amount': cfg.get('amount_col'),
        'currency': cfg.get('currency_col'),
    })
    if 'amount' in df.columns:
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
    keep = [c for c in ['contract_no', 'elevator_no', 'payment_type', 'amount', 'currency'] if c in df.columns]
    df = df[keep].copy()
    df['row_number'] = range(header + 2, len(df) + header + 2)
    return df


def read_table_r(filepath, config):
    cfg = config['table_r']
    frames = []
    for sheet in cfg['sheets']:
        needed = [cfg.get('contract_col'), cfg.get('amount_col'), cfg.get('nature_col')]
        usecols = _resolve_usecols(filepath, str(sheet), needed)
        if not usecols:
            raise ValueError('人民币回款台账 %s sheet 缺少必要列' % sheet)
        df = pd.read_excel(filepath, sheet_name=str(sheet), usecols=usecols)
        df = _rename_std(df, {
            'contract_no': cfg.get('contract_col'),
            'amount': cfg.get('amount_col'),
            'nature': cfg.get('nature_col'),
        })
        if 'amount' in df.columns:
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
        keep = [c for c in ['contract_no', 'amount', 'nature'] if c in df.columns]
        df = df[keep].copy()
        df['year'] = int(sheet)
        df['row_number'] = range(2, len(df) + 2)
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_exchange_rates(filepath):
    rates = {'人民币': 1.0, '人民币元': 1.0, 'CNY': 1.0, 'RMB': 1.0}
    if not filepath or not os.path.exists(filepath):
        return rates
    last_error = None
    for encoding in ('utf-8-sig', 'utf-8', 'gb18030', 'gbk'):
        try:
            df = pd.read_csv(filepath, sep='\t', dtype=str, encoding=encoding)
            break
        except Exception as exc:
            last_error = exc
            df = None
    if df is None:
        raise ValueError('汇率文件读取失败: %s' % last_error)
    for _, row in df.iterrows():
        name = clean_text(row.iloc[0])
        rate_text = clean_text(row.iloc[1])
        match = re.search(r'1(.+?)对人民币', name)
        if not match:
            continue
        currency = normalize_currency(match.group(1))
        try:
            rates[currency] = float(rate_text)
        except (TypeError, ValueError):
            continue
    return rates


def prepare_b_records(df):
    records = []
    for _, row in df.iterrows():
        contract_no = clean_contract(row.get('contract_no'))
        if not contract_no:
            continue
        remark = row.get('remark')
        if has_adjust_remark(remark):
            continue
        amount = to_float(row.get('amount'))
        fee = to_float(row.get('fee'))
        tid = clean_text(row.get('tid'))
        remark_parts = parse_remark_parts(remark)
        base = {
            'source': 'B',
            'year': int(row.get('year') or 0),
            'row_number': int(row.get('row_number') or 0),
            'contract_no': contract_no,
            'tid': tid,
            'remark': clean_text(remark),
        }
        if remark_parts:
            for currency, part_amount in remark_parts.items():
                item = dict(base)
                item.update({'currency': currency, 'amount': part_amount, 'note': '折合备注'})
                records.append(item)
        else:
            item = dict(base)
            item.update({
                'currency': normalize_currency(row.get('currency')),
                'amount': round(amount + fee, 2),
                'note': '',
            })
            records.append(item)
    return records


def prepare_e_records(df):
    records = []
    for _, row in df.iterrows():
        if clean_text(row.get('payment_type')) != '抵佣金':
            continue
        contract_no = clean_contract(row.get('contract_no'))
        if not contract_no:
            continue
        ladder_no = canonical_ladder(row.get('elevator_no'))
        records.append({
            'source': 'E',
            'year': 0,
            'row_number': int(row.get('row_number') or 0),
            'contract_no': contract_no,
            'ladder_no': ladder_no,
            'currency': normalize_currency(row.get('currency')),
            'amount': round(to_float(row.get('amount')), 2),
            'note': '抵佣金',
        })
    return records


def prepare_r_records(df):
    records = []
    for _, row in df.iterrows():
        contract_no = clean_contract(row.get('contract_no'))
        nature = clean_text(row.get('nature'))
        extracted = extract_contract(nature)
        if extracted:
            contract_no = extracted
        if not contract_no:
            continue
        fill_rest = parse_fill_then_rest(nature)
        numbers = parse_ladder_numbers(nature) if not fill_rest else []
        records.append({
            'source': 'R',
            'year': int(row.get('year') or 0),
            'row_number': int(row.get('row_number') or 0),
            'contract_no': contract_no,
            'nature': nature,
            'ladder_numbers': numbers,
            'fill_rest': fill_rest,
            'currency': '人民币',
            'amount': round(to_float(row.get('amount')), 2),
            'note': '',
        })
    return records


def build_ledger_index(ledger_rows):
    index = {}
    contract_ladders = defaultdict(set)
    ladder_to_key = {}
    for raw in ledger_rows:
        ladder_no = canonical_ladder(raw.get('ladder_no'))
        if not ladder_no:
            continue
        contract_no = normalize_contract_no(raw.get('contract_no')) or ladder_no.split('/', 1)[0].upper()
        ladder_no = ladder_no.upper()
        info = {
            'contract_no': contract_no,
            'ladder_no': ladder_no,
            'currency': normalize_currency(raw.get('currency')),
            'orig_amount': to_float(raw.get('contract_amount_orig')),
            'contract_amount': to_float(raw.get('contract_amount_rmb')),
            'rate': to_float(raw.get('exchange_rate')),
            'payment_ratio': raw.get('payment_ratio'),
        }
        key = (contract_no, ladder_no)
        old = index.get(key)
        if old is None or info['contract_amount'] >= old['contract_amount']:
            index[key] = info
        contract_ladders[contract_no].add(ladder_no)
        ladder_to_key.setdefault(ladder_no, key)
    for contract_no, ladders in contract_ladders.items():
        ladders = sorted(ladders)
        contract_ladders[contract_no] = ladders
    return index, contract_ladders, ladder_to_key


def rate_for(info, currency, exchange_rates):
    currency = normalize_currency(currency)
    if currency in RMB_CURRENCIES:
        return 1.0
    ladder_currency = normalize_currency(info.get('currency'))
    if currency and ladder_currency and currency == ladder_currency:
        rate = to_float(info.get('rate'))
        if rate > 0:
            return rate
    return to_float(exchange_rates.get(currency)) or 1.0


def split_even(amount, keys, decimals=2):
    if not keys:
        return {}
    total_cents = int(round(float(amount) * (10 ** decimals)))
    base, remainder = divmod(total_cents, len(keys))
    result = {}
    for index, key in enumerate(keys):
        result[key] = round((base + (1 if index < remainder else 0)) / (10 ** decimals), decimals)
    return result


def split_by_weights(amount, keys, weights, decimals=2):
    keys = list(dict.fromkeys(keys))
    if not keys:
        return {}
    positive = [key for key in keys if to_float(weights.get(key)) > 0]
    if not positive:
        return split_even(amount, keys, decimals)
    total_cents = int(round(float(amount) * (10 ** decimals)))
    total_weight = sum(to_float(weights.get(key)) for key in positive)
    raw = [to_float(weights.get(key)) / total_weight * total_cents for key in positive]
    base = [int(math.floor(value)) for value in raw]
    remainder = total_cents - sum(base)
    order = sorted(range(len(positive)), key=lambda i: raw[i] - base[i], reverse=True)
    for index in order[:remainder]:
        base[index] += 1
    result = {key: 0.0 for key in keys}
    for key, cents in zip(positive, base):
        result[key] = round(cents / (10 ** decimals), decimals)
    return result


def allocate_capped(amount, keys, weights, capacities):
    """在容量上限内按权重分摊；返回实际分出的金额（不超过 amount）。"""
    keys = [key for key in dict.fromkeys(keys) if to_float(capacities.get(key)) > 0]
    result = {key: 0.0 for key in keys}
    if not keys:
        return result
    remaining_cents = int(round(float(amount) * 100))
    capacity_cents = {key: max(0, int(round(to_float(capacities.get(key)) * 100))) for key in keys}
    while remaining_cents > 0:
        active = [key for key in keys if capacity_cents[key] > 0]
        if not active:
            break
        total_weight = sum(max(to_float(weights.get(key)), 0.000001) for key in active)
        shares = {}
        for key in active:
            weight = max(to_float(weights.get(key)), 0.000001)
            shares[key] = remaining_cents * weight / total_weight
        allocated = 0
        for key in active:
            cents = min(int(math.floor(shares[key])), capacity_cents[key])
            if cents > 0:
                result[key] = round((result[key] * 100 + cents) / 100, 2)
                capacity_cents[key] -= cents
                allocated += cents
        if allocated == 0:
            key = max(active, key=lambda item: shares[item])
            cents = min(1, capacity_cents[key])
            if cents > 0:
                result[key] = round((result[key] * 100 + cents) / 100, 2)
                capacity_cents[key] -= cents
                allocated = cents
        remaining_cents -= allocated
    return result


def calculate_payment_ratios(ledger_rows, tracking_rows, file_paths, exchange_rate_path,
                             config):
    """返回计算结果、分摊明细和异常。不写数据库。"""
    index, contract_ladders, ladder_to_key = build_ledger_index(ledger_rows)
    exchange_rates = load_exchange_rates(exchange_rate_path)

    df_b = read_table_b(file_paths['table_b'], config)
    df_e = read_table_e(file_paths['table_e'], config)
    df_r = read_table_r(file_paths['table_r'], config)

    b_records = prepare_b_records(df_b)
    e_records = prepare_e_records(df_e)
    r_records = prepare_r_records(df_r)

    target_contracts = set()
    for row in tracking_rows:
        ladder_no = canonical_ladder(row.get('ladder_no'))
        contract_no = normalize_contract_no(row.get('contract_no')) or ladder_no.split('/', 1)[0].upper()
        if contract_no:
            target_contracts.add(contract_no)
    b_records = [r for r in b_records
                 if normalize_contract_no(r.get('contract_no')) in target_contracts]
    e_records = [r for r in e_records
                 if normalize_contract_no(r.get('contract_no')) in target_contracts]
    r_records = [r for r in r_records
                 if normalize_contract_no(r.get('contract_no')) in target_contracts]

    payments = defaultdict(lambda: defaultdict(float))
    paid_rmb_specific = defaultdict(float)
    allocations = []
    warnings = []
    warning_seen = set()

    def _warn(message):
        message = str(message)
        if message not in warning_seen:
            warning_seen.add(message)
            warnings.append(message)

    pool = defaultdict(lambda: defaultdict(float))
    pool_notes = defaultdict(list)

    def add_allocation(key, currency, amount, meta, specific=True):
        amount = round(float(amount), 2)
        if not key or abs(amount) < 0.005:
            return
        contract_no, ladder_no = key
        currency = normalize_currency(currency)
        payments[key][currency] = round(payments[key].get(currency, 0.0) + amount, 2)
        info = index.get(key)
        if specific and info:
            paid_rmb_specific[key] = round(
                paid_rmb_specific[key] + amount * rate_for(info, currency, exchange_rates), 6)
        allocations.append({
            'contract_no': contract_no,
            'ladder_no': ladder_no,
            'currency': currency,
            'amount': amount,
            'source': meta.get('source', ''),
            'year': meta.get('year', 0),
            'row_number': meta.get('row_number', 0),
            'note': meta.get('note', ''),
            'remark': meta.get('remark', ''),
        })

    def contract_keys(contract_no):
        return [(contract_no, ladder_no) for ladder_no in contract_ladders.get(contract_no, [])]

    def weights_for(keys):
        return {key: to_float(index[key].get('contract_amount')) for key in keys if key in index}

    def allocate_group(amount, currency, keys, meta, allowed_keys=None):
        if allowed_keys is not None:
            allowed = set(allowed_keys)
            keys = [key for key in keys if key in allowed]
        keys = [key for key in keys if key in index]
        if not keys:
            return False
        parts = split_by_weights(amount, keys, weights_for(keys))
        for key, value in parts.items():
            add_allocation(key, currency, value, meta, specific=True)
        return True

    def add_pool(contract_no, currency, amount, meta):
        currency = normalize_currency(currency)
        pool[contract_no][currency] = round(pool[contract_no].get(currency, 0.0) + amount, 2)
        pool_notes[contract_no].append(dict(meta, currency=currency, amount=round(amount, 2)))

    def handle_special_fill(record):
        contract_no = record['contract_no']
        amount = to_float(record['amount'])
        currency = normalize_currency(record['currency'])
        fill_numbers, rest_numbers = record['fill_rest']
        fill_keys = [(contract_no, '%s/%d#' % (contract_no, number)) for number in fill_numbers]
        rest_keys = [(contract_no, '%s/%d#' % (contract_no, number)) for number in rest_numbers]
        fill_keys = [key for key in fill_keys if key in index]
        rest_keys = [key for key in rest_keys if key in index]
        if not fill_keys:
            return False
        # 回满规则目前按人民币金额和人民币合同额计算；外币行退回普通分摊。
        if currency != '人民币':
            return allocate_group(amount, currency, fill_keys + rest_keys, record)
        weights = weights_for(fill_keys)
        capacities = {
            key: max(0.0, to_float(index[key].get('contract_amount')) - paid_rmb_specific.get(key, 0.0))
            for key in fill_keys
        }
        total_capacity = round(sum(capacities.values()), 2)
        if total_capacity <= amount + 0.005:
            filled = allocate_capped(total_capacity, fill_keys, weights, capacities)
            for key, value in filled.items():
                add_allocation(key, currency, value, dict(record, note='回满优先'), specific=True)
            remainder = round(amount - sum(filled.values()), 2)
            if remainder > 0.005:
                target_keys = rest_keys or contract_keys(contract_no)
                if target_keys:
                    parts = split_by_weights(remainder, target_keys, weights_for(target_keys))
                    for key, value in parts.items():
                        add_allocation(key, currency, value, dict(record, note='回满后剩余'), specific=True)
                else:
                    _warn('%s 回满后无可分配梯号，剩余 %.2f 元' % (contract_no, remainder))
        else:
            filled = allocate_capped(amount, fill_keys, weights, capacities)
            for key, value in filled.items():
                add_allocation(key, currency, value, dict(record, note='回满优先（不足额）'), specific=True)
        return True

    # 第一轮：所有指定梯号的回款，先 B、再 E、再 R。
    for record in b_records:
        contract_no = record['contract_no']
        numbers = parse_ladder_numbers(record.get('tid'))
        if numbers:
            keys = [(contract_no, '%s/%d#' % (contract_no, number)) for number in numbers]
            existing = [key for key in keys if key in index]
            if not existing:
                _warn('B %s/%s 指定梯号不存在，转入合同池' % (contract_no, record.get('tid')))
                add_pool(contract_no, record['currency'], record['amount'], record)
            else:
                allocate_group(record['amount'], record['currency'], keys, record)
        else:
            add_pool(contract_no, record['currency'], record['amount'], record)

    for record in e_records:
        contract_no = record['contract_no']
        ladder_no = record.get('ladder_no') or ''
        key = None
        if ladder_no:
            key = (contract_no, ladder_no)
            if key not in index and '/' not in ladder_no:
                key = (contract_no, '%s/%s' % (contract_no, ladder_no))
        if key and key in index:
            add_allocation(key, record['currency'], record['amount'], record, specific=True)
        else:
            add_pool(contract_no, record['currency'], record['amount'], record)

    for record in r_records:
        contract_no = record['contract_no']
        if record.get('fill_rest'):
            if not handle_special_fill(record):
                _warn('R %s 回满规则无法落梯，转入合同池' % contract_no)
                add_pool(contract_no, record['currency'], record['amount'], record)
            continue
        numbers = record.get('ladder_numbers') or []
        if numbers:
            keys = [(contract_no, '%s/%d#' % (contract_no, number)) for number in numbers]
            existing = [key for key in keys if key in index]
            if not existing:
                _warn('R %s 指定梯号不存在，转入合同池' % contract_no)
                add_pool(contract_no, record['currency'], record['amount'], record)
            else:
                allocate_group(record['amount'], record['currency'], keys, record)
        else:
            add_pool(contract_no, record['currency'], record['amount'], record)

    # 第二轮：合同池按合同下全部梯号的合同额比例分摊。
    for contract_no, currencies in pool.items():
        keys = contract_keys(contract_no)
        if not keys:
            _warn('合同 %s 在台账中没有梯号，合同池 %.2f 元未分配' % (
                contract_no, sum(currencies.values())))
            continue
        weights = weights_for(keys)
        for currency, amount in currencies.items():
            parts = split_by_weights(amount, keys, weights)
            for key, value in parts.items():
                add_allocation(key, currency, value, {
                    'source': 'POOL',
                    'note': '合同池按合同额比例',
                }, specific=False)

    # 第三轮：逐梯号计算比例。
    results = []
    allocations_by_ladder = defaultdict(list)
    for item in allocations:
        allocations_by_ladder[(item['contract_no'], item['ladder_no'])].append(item)

    for row in tracking_rows:
        ladder_no = canonical_ladder(row.get('ladder_no'))
        contract_no = clean_text(row.get('contract_no')) or ladder_no.split('/', 1)[0]
        contract_no = contract_no.upper()
        ladder_no = ladder_no.upper()
        key = (contract_no, ladder_no)
        if key not in index:
            key = ladder_to_key.get(ladder_no)
        info = index.get(key) if key else None
        if info is None:
            results.append({
                'ladder_key': row.get('ladder_key') or ladder_no,
                'contract_no': contract_no,
                'ladder_no': ladder_no,
                'ledger_ratio': None,
                'calculated_ratio': None,
                'display_ratio': None,
                'paid_rmb': 0.0,
                'pending_rmb': 0.0,
                'status': 'ledger_not_found',
                'message': '台账中找不到该梯号',
                'payments': {},
                'allocations': [],
                'write_ratio': None,
            })
            continue
        ledger_ratio = info.get('payment_ratio')
        try:
            ledger_ratio = float(ledger_ratio) if ledger_ratio is not None else None
        except (TypeError, ValueError):
            ledger_ratio = None
        if ledger_ratio is not None and ledger_ratio >= 1:
            results.append({
                'ladder_key': row.get('ladder_key') or ladder_no,
                'contract_no': key[0],
                'ladder_no': key[1],
                'ledger_ratio': ledger_ratio,
                'calculated_ratio': None,
                'display_ratio': 1.0,
                'paid_rmb': 0.0,
                'pending_rmb': 0.0,
                'status': 'ledger_paid',
                'message': '台账已回款 100%，不重算',
                'payments': {},
                'allocations': [],
                'write_ratio': None,
            })
            continue

        ladder_payments = dict(payments.get(key, {}))
        if not ladder_payments:
            if ledger_ratio is not None and ledger_ratio > 0:
                status = 'no_payment_keep_ledger'
                message = '没有匹配到回款记录，保留台账比例'
                write_ratio = ledger_ratio
            elif ledger_ratio is not None:
                status = 'no_payment_zero'
                message = '没有匹配到回款记录，写 0%'
                write_ratio = 0.0
            else:
                status = 'no_payment_no_ledger_ratio'
                message = '没有匹配到回款记录，台账比例为空，保留空值'
                write_ratio = None
            results.append({
                'ladder_key': row.get('ladder_key') or ladder_no,
                'contract_no': key[0],
                'ladder_no': key[1],
                'ledger_ratio': ledger_ratio,
                'calculated_ratio': write_ratio,
                'display_ratio': min(write_ratio, 1.0) if write_ratio is not None else None,
                'paid_rmb': 0.0,
                'pending_rmb': to_float(info.get('contract_amount')) if write_ratio is not None else 0.0,
                'status': status,
                'message': message,
                'payments': {},
                'allocations': [],
                'write_ratio': write_ratio,
            })
            continue

        ladder_currency = normalize_currency(info.get('currency'))
        orig_amount = to_float(info.get('orig_amount'))
        contract_amount = to_float(info.get('contract_amount'))
        paid_rmb = 0.0
        ratio = None
        pending_rmb = 0.0
        message = ''
        status = 'calculated'

        if len(ladder_payments) == 1 and ladder_currency and orig_amount > 0:
            currency, paid = next(iter(ladder_payments.items()))
            if normalize_currency(currency) == ladder_currency:
                ratio = paid / orig_amount if orig_amount else 0.0
                rate = rate_for(info, currency, exchange_rates)
                paid_rmb = round(paid * rate, 2)
                pending_rmb = (orig_amount - paid) * rate
            else:
                paid_rmb = sum(
                    amount * rate_for(info, currency_item, exchange_rates)
                    for currency_item, amount in ladder_payments.items()
                )
        if ratio is None:
            paid_rmb = 0.0
            for currency, amount in ladder_payments.items():
                paid_rmb += amount * rate_for(info, currency, exchange_rates)
            paid_rmb = round(paid_rmb, 2)
            if contract_amount <= 0:
                status = 'no_contract_amount'
                message = '合同额无效，保留台账比例'
                ratio = ledger_ratio
            else:
                ratio = paid_rmb / contract_amount
            pending_rmb = contract_amount - paid_rmb

        if ratio is None:
            ratio = 0.0
        if ratio < 0:
            ratio = 0.0
        display_ratio = min(ratio, 1.0)
        if status == 'calculated':
            message = '已按回款台账计算'
        results.append({
            'ladder_key': row.get('ladder_key') or ladder_no,
            'contract_no': key[0],
            'ladder_no': key[1],
            'ledger_ratio': ledger_ratio,
            'calculated_ratio': round(ratio, 6),
            'display_ratio': round(display_ratio, 6),
            'paid_rmb': round(paid_rmb, 2),
            'pending_rmb': round(pending_rmb, 2),
            'status': status,
            'message': message,
            'payments': {currency: round(amount, 2) for currency, amount in ladder_payments.items()},
            'allocations': allocations_by_ladder.get(key, []),
            'write_ratio': round(ratio, 6) if status == 'calculated' else ledger_ratio,
        })

    stats = {
        'target_count': len(tracking_rows),
        'calculated_count': sum(1 for row in results if row['status'] == 'calculated'),
        'ledger_paid_count': sum(1 for row in results if row['status'] == 'ledger_paid'),
        'kept_ledger_count': sum(1 for row in results if row['status'] in (
            'no_payment_keep_ledger', 'no_contract_amount', 'ledger_not_found')),
        'zero_count': sum(1 for row in results if row['status'] == 'no_payment_zero'),
        'missing_ledger_count': sum(1 for row in results if row['status'] == 'ledger_not_found'),
        'no_payment_count': sum(1 for row in results if row['status'].startswith('no_payment_')),
        'empty_ledger_count': sum(1 for row in results if row['status'] == 'no_payment_no_ledger_ratio'),
        'warning_count': len(warnings),
    }
    return {
        'results': results,
        'allocations': allocations,
        'warnings': warnings,
        'stats': stats,
        'exchange_rates': exchange_rates,
        'record_counts': {
            'table_b': len(b_records),
            'table_e': len(e_records),
            'table_r': len(r_records),
        },
    }
