# -*- coding: utf-8 -*-
"""清空「发货梯号追踪」业务数据（仅 st_ 表）。

安全约定：
- 只允许删除固定的 7 张 st_ 表，绝不触碰 mf_ / cc_ / user / module 等表；
- 默认 dry-run，只打印条数；执行必须同时给 --execute 和 --confirm RESET_SHIP_TRACKING；
- 执行前用 SQLite backup API 生成一致性备份，并校验备份完整性；
- 单个事务内删除，提交前再次核对条数；任一步失败自动回滚；
- 不改表结构，不执行 VACUUM，不动 sqlite_sequence。

用法（在 backend 目录下）：
    python ship_tracking/cli_reset.py                       # dry-run，看条数
    python ship_tracking/cli_reset.py --execute --confirm RESET_SHIP_TRACKING

测试数据库副本需要显式加 --allow-custom-db：
    python ship_tracking/cli_reset.py --db E:/System/tmp_ui/tmp_reset.db \\
        --execute --confirm RESET_SHIP_TRACKING --allow-custom-db
"""
import argparse
import datetime as dt
import os
import shutil
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(BASE_DIR, 'instance', 'system.db')
DEFAULT_BACKUP_DIR = os.path.join(BASE_DIR, 'instance', 'backups')

# 子表/流水在前，批次在后；本模块没有声明数据库外键，顺序只作语义上的安全安排。
ST_TABLES = [
    'st_setting',
    'st_import_issue',
    'st_audit_log',
    'st_booking_record',
    'st_daily_shipment',
    'st_plan_item',
    'st_tracking_item',
    'st_import_batch',
]
CONFIRM_TOKEN = 'RESET_SHIP_TRACKING'


def _resolve_db_path(raw):
    path = os.path.abspath(raw or DEFAULT_DB)
    if path.startswith('sqlite:///'):
        path = path[len('sqlite:///'):]
    return path


def _connect(path):
    conn = sqlite3.connect(path, timeout=15)
    conn.isolation_level = None
    conn.execute('PRAGMA busy_timeout = 15000')
    return conn


def _tables(conn):
    return [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    )]


def _counts(conn, tables):
    result = {}
    for table in tables:
        result[table] = conn.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0]
    return result


def _print_counts(counts, title):
    print('\n%s' % title)
    width = max([len(name) for name in counts] + [4])
    for name in sorted(counts):
        print('  %-*s %d' % (width, name, counts[name]))


def _check_schema(conn):
    existing = set(_tables(conn))
    missing = [table for table in ST_TABLES if table not in existing]
    if missing:
        raise SystemExit('缺少 st_ 表：%s；请确认数据库路径是否正确。' % '、'.join(missing))
    # 检查是否有其他表通过外键引用 st_ 表
    for table in existing:
        if table in ST_TABLES:
            continue
        for row in conn.execute('PRAGMA foreign_key_list("%s")' % table):
            if row[2] in ST_TABLES:
                raise SystemExit('表 %s 通过外键引用 %s，拒绝清库。' % (table, row[2]))


def _backup(conn, db_path, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = os.path.join(backup_dir, 'system.db.bak-st-reset-%s' % stamp)
    usage = shutil.disk_usage(os.path.dirname(os.path.abspath(db_path)))
    db_size = os.path.getsize(db_path)
    if usage.free < db_size * 1.2:
        raise SystemExit('磁盘剩余空间不足：需要至少 %.1f MB，当前剩余 %.1f MB。'
                         % (db_size * 1.2 / 1048576.0, usage.free / 1048576.0))
    dest = sqlite3.connect(backup_path)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    check = sqlite3.connect(backup_path)
    try:
        integrity = check.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok':
            raise SystemExit('备份完整性校验失败：%s' % integrity)
        backup_counts = _counts(check, _tables(check))
    finally:
        check.close()
    return backup_path, backup_counts


def main(argv=None):
    parser = argparse.ArgumentParser(description='清空发货梯号追踪业务数据（仅 st_ 表）')
    parser.add_argument('--db', default=DEFAULT_DB, help='SQLite 数据库路径')
    parser.add_argument('--backup-dir', default=DEFAULT_BACKUP_DIR, help='备份目录')
    parser.add_argument('--execute', action='store_true', help='真正执行删除；默认只 dry-run')
    parser.add_argument('--confirm', default='', help='执行确认口令：%s' % CONFIRM_TOKEN)
    parser.add_argument('--allow-custom-db', action='store_true',
                        help='允许对非默认数据库执行删除（测试副本使用）')
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args.db)
    if not os.path.isfile(db_path):
        print('数据库不存在：%s' % db_path)
        return 2
    default_path = _resolve_db_path(DEFAULT_DB)
    print('数据库：%s' % db_path)
    print('备份目录：%s' % os.path.abspath(args.backup_dir))

    if args.execute:
        if args.confirm != CONFIRM_TOKEN:
            print('拒绝执行：需要 --confirm %s' % CONFIRM_TOKEN)
            return 2
        if os.path.normcase(db_path) != os.path.normcase(default_path) and not args.allow_custom_db:
            print('拒绝执行：非默认数据库需要同时加 --allow-custom-db')
            return 2
        print('提示：执行前请确认 Flask 服务已停止写入。')

    conn = _connect(db_path)
    try:
        _check_schema(conn)
        all_tables = _tables(conn)
        before = _counts(conn, all_tables)
        st_before = {table: before[table] for table in ST_TABLES}
        other_before = {table: value for table, value in before.items() if table not in ST_TABLES}
        _print_counts(st_before, '将清空的 st_ 表（当前条数）：')
        print('\n保护表（只校验，不修改）：')
        for name in ('mf_user_scope', 'mf_monthly_input', 'mf_ship_selection', 'mf_submission',
                     'cc_ledger_contract', 'user', 'module'):
            if name in before:
                print('  %-24s %d' % (name, before[name]))

        if not args.execute:
            print('\ndry-run：未修改任何数据。确认无误后加 --execute --confirm %s 执行。' % CONFIRM_TOKEN)
            return 0

        backup_path, backup_counts = _backup(conn, db_path, args.backup_dir)
        if backup_counts != before:
            print('备份条数与执行前不一致，已终止。')
            return 1
        print('\n备份完成：%s' % backup_path)

        conn.execute('BEGIN IMMEDIATE')
        try:
            locked_counts = _counts(conn, all_tables)
            if locked_counts != before:
                conn.execute('ROLLBACK')
                print('加锁后条数发生变化（可能有其他进程写入），已回滚，请重试。')
                return 2
            for table in ST_TABLES:
                conn.execute('DELETE FROM "%s"' % table)
            after = _counts(conn, all_tables)
            remaining = {table: after[table] for table in ST_TABLES if after[table]}
            changed = {table: (other_before[table], after[table])
                       for table in other_before if other_before[table] != after[table]}
            if remaining:
                conn.execute('ROLLBACK')
                print('删除后 st_ 表仍有数据：%s，已回滚。' % remaining)
                return 1
            if changed:
                conn.execute('ROLLBACK')
                print('保护表条数发生变化：%s，已回滚。' % changed)
                return 1
            integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
            if integrity != 'ok':
                conn.execute('ROLLBACK')
                print('提交前完整性校验失败：%s，已回滚。' % integrity)
                return 1
            conn.execute('COMMIT')
        except Exception:
            conn.execute('ROLLBACK')
            raise

        final = _counts(conn, all_tables)
        _print_counts({table: final[table] for table in ST_TABLES}, '清空后的 st_ 表：')
        print('\n保护表条数未变化：%s' % all(
            final[table] == other_before[table] for table in other_before
        ))
        print('已完成。备份：%s' % backup_path)
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
