"""
配件回款 vs 财务 合同回款对比（2026年）
输出金额不一致的合同号
"""
import pandas as pd

TOLERANCE = 1.0  # ±1元以内算一致

# ── 1. 读取配件回款.xls ─────────────────────────────────
df_parts = pd.read_excel('配件回款.xls', sheet_name='Sheet_1', header=None, skiprows=3)
df_parts.columns = [
    '合同编号', '项目名称', '签约日期', '金额_汇率', '客户名称',
    '回款额原币', '回款额本币', '回款日期', '模板', '币种', '备注'
]

# 筛选：模板 ∈ {配件-1, 配件-2}，回款日期 >= 2026-01-01
df_parts = df_parts[df_parts['模板'].isin(['配件-1', '配件-2'])].copy()
df_parts['回款日期_dt'] = pd.to_datetime(df_parts['回款日期'], errors='coerce')
df_parts = df_parts[df_parts['回款日期_dt'] >= '2026-01-01'].copy()
df_parts['金额'] = pd.to_numeric(df_parts['回款额本币'], errors='coerce').fillna(0)
print(f'配件回款 2026年记录数: {len(df_parts)}')

# ── 2. 读取财务.xlsx ─────────────────────────────────────
df_finance = pd.read_excel('财务.xlsx', sheet_name='sheet1')
df_finance.columns = ['数据号', '合同编号', '原币发生额', '本币发生额', '发生日期', '凭证号']

df_finance['发生日期_dt'] = pd.to_datetime(df_finance['发生日期'], errors='coerce')
df_finance = df_finance[df_finance['发生日期_dt'] >= '2026-01-01'].copy()
df_finance['金额'] = pd.to_numeric(df_finance['本币发生额'], errors='coerce').fillna(0)
print(f'财务 2026年记录数: {len(df_finance)}')

# ── 3. 配件回款按合同号汇总 ─────────────────────────────
# 记录每个合同号出现在哪些模板
contract_modules = (
    df_parts.groupby('合同编号')['模板']
    .apply(lambda x: '+'.join(sorted(set(x))))
    .to_dict()
)

parts_agg = df_parts.groupby('合同编号')['金额'].sum().reset_index()
parts_agg.columns = ['合同编号', '配件回款总额']
parts_agg['配件来源'] = parts_agg['合同编号'].map(contract_modules)
parts_agg['跨模板'] = parts_agg['配件来源'].str.contains('\+')
print(f'配件回款合同号: {len(parts_agg)} 个（其中跨模板: {parts_agg["跨模板"].sum()} 个）')

# ── 4. 财务按合同号汇总 ──────────────────────────────
finance_agg = df_finance.groupby('合同编号')['金额'].sum().reset_index()
finance_agg.columns = ['合同编号', '财务金额']
print(f'财务合同号: {len(finance_agg)} 个')

# ── 5. 全外连接对比 ────────────────────────────────────
merged = parts_agg.merge(finance_agg, on='合同编号', how='outer', indicator=True)
merged['配件回款总额'] = merged['配件回款总额'].fillna(0)
merged['财务金额'] = merged['财务金额'].fillna(0)
merged['差额'] = merged['配件回款总额'] - merged['财务金额']
merged['是否一致'] = merged['差额'].abs() <= TOLERANCE

def source_label(r):
    if r['_merge'] == 'both':   return '两边都有'
    elif r['_merge'] == 'left_only': return '仅配件'
    else:                        return '仅财务'

merged['来源'] = merged.apply(source_label, axis=1)
# 补充单边数据的配件来源
for idx in merged[merged['配件来源'].isna()].index:
    merged.at[idx, '配件来源'] = ''
merged['跨模板'] = merged['跨模板'].fillna(False)

# ── 6. 输出结果 ────────────────────────────────────────
mismatch = merged[(merged['_merge'] == 'both') & (~merged['是否一致'])]
only_one  = merged[merged['_merge'] != 'both']

print('\n' + '=' * 80)
print('                    合同回款对比结果（2026年）')
print('=' * 80)
print(f'\n总览:')
print(f'  配件回款: {len(parts_agg)} 个合同号, {parts_agg["配件回款总额"].sum():,.2f} 元')
print(f'  财务:     {len(finance_agg)} 个合同号, {finance_agg["财务金额"].sum():,.2f} 元')
print(f'  两边都有: {(merged["_merge"]=="both").sum()} 个')
print(f'  一致:     {(merged["_merge"]=="both").sum() - len(mismatch)} 个')
print(f'  [!!] 不一致: {len(mismatch)} 个')
print(f'  仅配件:   {(merged["_merge"]=="left_only").sum()} 个')
print(f'  仅财务:   {(merged["_merge"]=="right_only").sum()} 个')

if len(mismatch) > 0:
    print(f'\n{"=" * 80}')
    print(f'  [!!] 金额不一致的合同号（{len(mismatch)} 个）')
    print(f'{"=" * 80}')
    mm = mismatch.sort_values('差额', key=abs, ascending=False)
    print(f'{"合同编号":<22} {"配件回款(元)":>14} {"财务金额(元)":>14} {"差额(元)":>14} {"配件来源":<12} {"跨模板"}')
    print('-' * 90)
    for _, r in mm.iterrows():
        print(f'{r["合同编号"]:<22} {r["配件回款总额"]:>14,.2f} {r["财务金额"]:>14,.2f} {r["差额"]:>14,.2f} {r.get("配件来源",""):<12} {"[!]是" if r["跨模板"] else "否"}')

if len(only_one) > 0:
    print(f'\n{"=" * 80}')
    print(f'  [!] 仅单边存在的合同号（{len(only_one)} 个）')
    print(f'{"=" * 80}')
    oo = only_one.sort_values('来源')
    print(f'{"合同编号":<22} {"配件回款(元)":>14} {"财务金额(元)":>14} {"来源":<10}')
    print('-' * 65)
    for _, r in oo.iterrows():
        print(f'{r["合同编号"]:<22} {r["配件回款总额"]:>14,.2f} {r["财务金额"]:>14,.2f} {r["来源"]:<10}')

# ── 7. 导出Excel ────────────────────────────────────────
out_cols = ['合同编号', '配件回款总额', '财务金额', '差额', '是否一致', '配件来源', '跨模板', '来源']
out_all = merged[out_cols].sort_values('差额', key=abs, ascending=False)

with pd.ExcelWriter('合同回款对比结果.xlsx', engine='openpyxl') as w:
    out_all.to_excel(w, sheet_name='全部对比', index=False)
    mismatch[out_cols].sort_values('差额', key=abs, ascending=False).to_excel(w, sheet_name='金额不一致', index=False)
    only_one[out_cols].sort_values('来源').to_excel(w, sheet_name='仅单边存在', index=False)

print(f'\n[OK] 结果已导出至: 合同回款对比结果.xlsx')
