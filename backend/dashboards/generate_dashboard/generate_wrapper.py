#!py -3.11
"""
generate_wrapper.py - 通用看板生成包装脚本
============================================
接收显式文件路径，构建工作目录，调用实际的生成脚本。

用法（由 Flask backend 调用）:
  py -3.11 generate_wrapper.py --output <html_path> \
      --ledger <台账路径> --budget <预算路径> --mapping <映射路径> \
      --report_a <报表a> --report_b <报表b> ...
"""
import argparse
import json
import os
import sys
import shutil
import datetime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, help='看板HTML输出路径')
    args, unknown = parser.parse_known_args()

    # 解析 --key value 格式的子项文件映射
    file_map = {}
    i = 0
    while i < len(unknown):
        if unknown[i].startswith('--') and i + 1 < len(unknown):
            key = unknown[i][2:]  # remove --
            val = unknown[i + 1]
            file_map[key] = val
            i += 2
        else:
            i += 1

    if not file_map:
        print('[错误] 未提供任何输入文件', file=sys.stderr)
        sys.exit(1)

    # 验证所需文件都存在
    for key, path in file_map.items():
        if not os.path.isfile(path):
            print(f'[错误] 文件不存在: {key} = {path}', file=sys.stderr)
            sys.exit(1)

    # 构建工作目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    source_dir = os.path.join(script_dir, '数据源excel')
    os.makedirs(source_dir, exist_ok=True)

    # 读取上次复制的文件清单，清理旧文件（只删 wrapper 自己复制的，不动用户手工文件）
    manifest_path = os.path.join(source_dir, '.wrapper_manifest.json')
    prev_manifest = {}
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                prev_manifest = json.loads(f.read())
        except Exception:
            prev_manifest = {}

    # 删除本次要更新的子项对应的旧文件
    for key in file_map:
        old_name = prev_manifest.get(key)
        if old_name:
            old_path = os.path.join(source_dir, old_name)
            if os.path.isfile(old_path):
                try:
                    os.remove(old_path)
                    print(f'[清理] {old_name}')
                except PermissionError:
                    print(f'[警告] 无法删除 {old_name}（文件被占用），将尝试覆盖写入')

    # 构建新清单
    new_manifest = dict(prev_manifest)

    # 复制文件到数据源目录
    for key, path in file_map.items():
        original_name = os.path.basename(path)
        dest = os.path.join(source_dir, original_name)
        try:
            shutil.copy2(path, dest)
        except PermissionError:
            # 目标文件被占用时，尝试先强制删除再复制
            deleted = False
            try:
                os.chmod(dest, 0o777)
                os.remove(dest)
                deleted = True
            except Exception:
                pass
            if deleted:
                shutil.copy2(path, dest)
            else:
                print(f'[警告] 目标文件 {original_name} 被占用且无法删除，跳过复制', file=sys.stderr)
                continue
        new_manifest[key] = original_name
        print(f'[复制] {original_name} → 数据源excel/')

    # 保存新清单
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(new_manifest, f, ensure_ascii=False)

    today_str = datetime.date.today().strftime('%m-%d')
    target_month = '2026-07'

    # Step 1: 生成报表 Excel
    print(f'\n[Step 1] 生成报表... (月份: {target_month})')
    try:
        import generate_report_june
    except ImportError:
        print('[提示] generate_report_june.py 未找到，跳过报表生成，使用已有 Excel')

    if 'generate_report_june' in sys.modules:
        try:
            report_path, unmatched = generate_report_june.generate_june_report(
                target_month, script_dir, '数据源excel')
            print(f'[报表] {report_path}')
        except FileNotFoundError as e:
            print(f'[警告] 报表生成失败: {e}', file=sys.stderr)
            # 尝试找已有 Excel
            import glob
            candidates = sorted(glob.glob(os.path.join(script_dir, '签单排产发货_*.xlsx')), reverse=True)
            if candidates:
                report_path = candidates[0]
                print(f'[信息] 使用已有 Excel: {os.path.basename(report_path)}')
            else:
                print('[错误] 无可用 Excel 文件', file=sys.stderr)
                sys.exit(1)

        # Step 1.5: 填充配件数据
        try:
            from fill_trade_parts import fill_trade_cells
            fill_trade_cells(report_path, source_dir, target_month)
            print('[配件] 填充完成')
        except Exception as e:
            print(f'[警告] 配件填充失败: {e}')

    # Step 2: 生成看板 HTML
    print(f'\n[Step 2] 生成看板 HTML...')
    excel_path = report_path if 'report_path' in dir() else None
    if not excel_path:
        import glob
        candidates = sorted(glob.glob(os.path.join(script_dir, '签单排产发货_*.xlsx')), reverse=True)
        if candidates:
            excel_path = candidates[0]
        else:
            print('[错误] 未找到签单排产发货_*.xlsx', file=sys.stderr)
            sys.exit(1)

    from generate_dashboard import read_dashboard_data, read_table_rows, generate_html
    import openpyxl as _openpyxl
    _wb = _openpyxl.load_workbook(excel_path, data_only=True)
    try:
        region_data, grand = read_dashboard_data(excel_path, workbook=_wb)
        table_rows = read_table_rows(excel_path, workbook=_wb)
        generate_html(region_data, grand, target_month, args.output, table_rows, excel_path)
    finally:
        _wb.close()

    print(f'\n[完成] 看板已生成: {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
