#!py -3.11
"""
fill_trade_parts_june.py - 6月商贸配件数据填充（一站式入口）
============================================================
用法: py -3.11 fill_trade_parts_june.py --month 2026-06

先调用 generate_report_june.py 生成报表（含预算预测JSON），
再从 报表a.xls / 报表b.xls 匹配填充配件-1/配件-2的签单/排产/发货金额。
============================================================
"""
import argparse
import sys
import os
import datetime

import generate_report_june
from fill_trade_parts import fill_trade_cells
from generate_report import recalc_with_excel


def main():
    parser = argparse.ArgumentParser(description="6月商贸配件数据填充")
    parser.add_argument("--month", default=None, help="统计月份, 如 2026-06")
    parser.add_argument("--dir", default=os.getcwd(), help="输出目录")
    parser.add_argument("--source", default="数据源excel", help="数据源子目录（相对于--dir）")
    args = parser.parse_args()

    if args.month:
        target_month = args.month
    else:
        today = datetime.date.today()
        target_month = f"{today.year}-{today.month:02d}"

    work_dir = args.dir
    source_dir = os.path.join(work_dir, args.source)

    print(f"{'=' * 60}")
    print(f"  6月商贸配件数据填充")
    print(f"  月份: {target_month}")
    print(f"{'=' * 60}\n")

    # Step 1: 生成报表
    print("[Step 1] 生成报表...")
    try:
        report_path, unmatched = generate_report_june.generate_june_report(
            target_month, work_dir, source_dir)
    except FileNotFoundError as e:
        print(f"[错误] {e}")
        sys.exit(1)

    # 未匹配国家
    if unmatched:
        unmatched_path = os.path.join(work_dir, f"未匹配国家_{target_month}.txt")
        with open(unmatched_path, "w", encoding="utf-8") as f:
            for c in sorted(unmatched):
                f.write(f"{c}\n")
        print(f"[信息] 未匹配国家: {unmatched_path}")

    # Step 2: 填充配件数据
    print(f"\n[Step 2] 填充配件-1/配件-2数据...")
    fill_trade_cells(report_path, source_dir, target_month)

    # Step 3: Excel重算
    recalc_with_excel(report_path)

    print(f"\n{'=' * 60}")
    print(f"  完成!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
