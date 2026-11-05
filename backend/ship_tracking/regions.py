# -*- coding: utf-8 -*-
"""按「国家-业务员表」实时计算大区1/大区2。

规则：
1. 梯号在台账（source='ledger'）中有国家，且 cc_country_mapping 命中该国家
   → 使用映射表的 region；
2. 台账无该梯号 / 无国家 / 映射未命中 → 回退到 MODULE_REGION[module_name]；
3. 模块也不在常量表 → 空字符串。

结果只在查询时计算并返回给前端，不写入 st_tracking_item，也不改任何表结构。
"""
from sqlalchemy import bindparam, text

from dashboards.contract_completion.constants import MODULE_REGION, REGION_DISPLAY
from models import db
from ship_tracking.excel_reader import canonical_ladder, normalize_text

REGION_VALUES = ('大区1', '大区2')


def _country_key(value):
    return normalize_text(value).upper()


def region_of_module(module_name):
    return MODULE_REGION.get(normalize_text(module_name), '')


def _load_ledger_countries(ladder_keys):
    """一次分块查询台账国家；同梯号按合同额最大行取国家。"""
    keys = sorted({canonical_ladder(key) for key in ladder_keys if key})
    result = {}
    amounts = {}
    if not keys:
        return result
    statement = text(
        "SELECT ladder_no, country, contract_amount_rmb FROM cc_ledger_contract "
        "WHERE source = 'ledger' AND ladder_no IN :keys"
    ).bindparams(bindparam('keys', expanding=True))
    try:
        for start in range(0, len(keys), 500):
            chunk = keys[start:start + 500]
            rows = db.session.execute(statement, {'keys': chunk}).mappings().all()
            for row in rows:
                ladder = canonical_ladder(row.get('ladder_no'))
                country = normalize_text(row.get('country'))
                if not ladder or not country:
                    continue
                amount = row.get('contract_amount_rmb') or 0
                try:
                    amount = float(amount)
                except (TypeError, ValueError):
                    amount = 0
                if ladder not in result or amount > amounts.get(ladder, float('-inf')):
                    result[ladder] = country
                    amounts[ladder] = amount
    except Exception:
        db.session.rollback()
        return {}
    return result


def _load_country_regions():
    """读取国家 → 大区1/大区2 映射，兼容「陈/刘」和「陈总/刘总」写法。"""
    result = {}
    try:
        rows = db.session.execute(text(
            "SELECT country, region FROM cc_country_mapping"
        )).mappings().all()
    except Exception:
        db.session.rollback()
        return result
    for row in rows:
        country = _country_key(row.get('country'))
        if not country:
            continue
        region = normalize_text(row.get('region'))
        region = REGION_DISPLAY.get(region, region)
        if region in REGION_VALUES:
            result[country] = region
    return result


def build_region_map(tracking_rows):
    """返回 {ladder_key: {'region': '大区1'/'大区2'/'', 'region_source': ...}}。"""
    rows = list(tracking_rows or [])
    if not rows:
        return {}
    countries = _load_ledger_countries(row.ladder_key for row in rows)
    country_regions = _load_country_regions()
    result = {}
    for row in rows:
        ladder = canonical_ladder(row.ladder_key)
        country = countries.get(ladder, '')
        region = country_regions.get(_country_key(country), '') if country else ''
        source = 'country' if region else ''
        if not region:
            region = region_of_module(row.module_name)
            source = 'module' if region else 'none'
        result[row.ladder_key] = {'region': region, 'region_source': source}
    return result
