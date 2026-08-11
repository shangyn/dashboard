import sys; sys.path.insert(0, r'E:\System\backend')
from app import create_app
app = create_app()
with app.app_context():
    from models import db
    from dashboards.contract_completion.models import LedgerContract, CountryMapping
    from sqlalchemy import or_
    from collections import defaultdict
    from datetime import date

    # Current mapping
    mapping_count = CountryMapping.query.count()
    print('=== 1. 映射表状态 ===')
    print(f'cc_country_mapping总数: {mapping_count}')

    mapping = {m.country: m for m in CountryMapping.query.all()}
    print(f'唯一国家数: {len(mapping)}')

    # Check format
    has_manager = sum(1 for m in mapping.values() if m.module_manager)
    print(f'有模块经理(Sheet2格式): {has_manager}')
    print(f'无模块经理(Sheet3格式): {len(mapping)-has_manager}')

    # Sample
    print('映射样本:')
    for i, (country, m) in enumerate(list(mapping.items())[:5]):
        print(f'  {country} -> mod={m.module_name}, region={m.region}, mgr={m.module_manager}')

    # Ledger contracts
    contracts = LedgerContract.query.filter(
        LedgerContract.source == 'ledger',
        or_(LedgerContract.product_status == None, LedgerContract.product_status != '已作废')
    ).all()
    print(f'\n=== 2. 台账合同 ===')
    print(f'总数(排除已作废): {len(contracts)}')

    matched = 0
    unmatched = 0
    empty_country = 0
    unmatched_detail = defaultdict(lambda: [0, 0.0])

    for c in contracts:
        if not c.country:
            empty_country += 1
            continue
        if c.country in mapping:
            matched += 1
        else:
            unmatched += 1
            unmatched_detail[c.country][0] += 1
            unmatched_detail[c.country][1] += c.contract_amount_rmb or 0

    print(f'匹配成功: {matched}')
    print(f'未匹配: {unmatched}')
    print(f'国家为空: {empty_country}')
    print(f'匹配率: {matched/(matched+unmatched)*100:.1f}%')

    # Unmatched top
    sorted_um = sorted(unmatched_detail.items(), key=lambda x: x[1][0], reverse=True)
    print(f'\n=== 3. 未匹配Top20 ===')
    for country, info in sorted_um[:20]:
        print(f'{country}: {info[0]}条, {info[1]:.0f}元')

    # Amount stats
    total_amt = sum(c.contract_amount_rmb or 0 for c in contracts)
    unmatched_amt = sum(v[1] for v in unmatched_detail.values())
    print(f'\n=== 4. 金额 ===')
    print(f'全部: {total_amt:,.0f}元 = {total_amt/1e8:.1f}亿')
    print(f'未匹配: {unmatched_amt:,.0f}元 = {unmatched_amt/1e8:.1f}亿')
    print(f'未匹配占比: {unmatched_amt/total_amt*100:.1f}%')

    # Check specific unmatched countries against ledger
    print(f'\n=== 5. 台账中国家实际名称样本 ===')
    all_countries = defaultdict(int)
    for c in contracts:
        if c.country:
            all_countries[c.country] += 1
    sorted_c = sorted(all_countries.items(), key=lambda x: x[1], reverse=True)
    print(f'台账国家种类: {len(all_countries)}')
    for country, cnt in sorted_c[:30]:
        in_map = 'Y' if country in mapping else 'N'
        print(f'  [{in_map}] {country}: {cnt}条')
