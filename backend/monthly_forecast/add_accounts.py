# -*- coding: utf-8 -*-
'''单月签排发填报 — 服务器批量建号工具（一次性命令行）

把「DT号 + 人名」名单批量建成平台账号，可选同时写入模块归属。

安全约定：
    只新增账号，绝不修改 / 删除任何已存在的账号、角色、模块；
    重复执行安全（已存在的 username 直接跳过）；
    角色和模块入口不会自动创建，缺失时只提示该怎么建。

用法（在项目根目录执行）：
    python3 backend/monthly_forecast/add_accounts.py --file DT号+姓名.xlsx --dry-run
    python3 backend/monthly_forecast/add_accounts.py --file DT号+姓名.xlsx --with-scope

参数：
    --file                名单文件（xlsx / xls / csv，含 DT号 和 人名 两列）
    --role                角色名，默认 单月签排发填报（须已在平台上创建）
    --password            初始密码，默认 123456
    --with-scope          同时按业务员表的「任命令模块-模主」sheet 写模块归属
                          已有归属的账号不动（避免覆盖你手工加的），除非加 --reset-scope
    --reset-scope         重算并覆盖已有归属
    --only-mapping-sheet  只给该 sheet 里出现过的人建号
    --skip-dt            要跳过的 DT 号（可重复写），例如 --skip-dt DT190189
    --dry-run             只打印将要做什么，不写库
'''
import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 输出统一 UTF-8，避免 Windows 控制台按 GBK 编码时中文变乱码
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from monthly_forecast.handlers import (  # noqa: E402
    ACCOUNT_KEYS, NAME_KEYS, _cell_text, _find_col, _read_table,
)

DEFAULT_ROLE = '单月签排发填报'
PERMISSION = 'monthly_forecast'
AUTHORITATIVE_SHEET = '任命令模块-模主'


def log(text=''):
    print(text)


def read_roster(path):
    '''读名单 → [(dt号, 人名)]，按 DT 号去重'''
    table = [row for row in _read_table(path) if any(cell for cell in row)]
    if not table:
        raise ValueError('名单文件是空的')
    header = table[0]
    col_account = _find_col(header, ACCOUNT_KEYS)
    col_name = _find_col(header, NAME_KEYS)
    if col_account is None and col_name is None:
        raise ValueError('没找到 DT号 或 人名 列，请检查表头')
    rows, seen, dup = [], set(), []
    for row in table[1:]:
        dt = _cell_text(row[col_account]) if (col_account is not None and col_account < len(row)) else ''
        name = _cell_text(row[col_name]) if (col_name is not None and col_name < len(row)) else ''
        if not dt and not name:
            continue
        if dt and dt in seen:
            dup.append((dt, name))
            continue
        if dt:
            seen.add(dt)
        rows.append((dt, name))
    return rows, dup


def show_platform_check(Role, Module):
    '''只读检查平台侧前置条件，缺失时给出操作指引'''
    role = Role.query.filter_by(role_name=DEFAULT_ROLE).first()
    entry = Module.query.filter_by(permission=PERMISSION).first()
    log('--- 平台前置检查（只读）---')
    if role is None:
        log('  [缺] 角色「%s」不存在。请到 系统管理 → 角色管理 新建该角色，' % DEFAULT_ROLE)
        log('       权限勾选：单月签排发填报、合同工期统计（dashboard_schedule）。')
    else:
        perms = role.get_permissions()
        log('  [有] 角色「%s」 id=%s 权限=%s' % (role.role_name, role.id, perms))
    if entry is None:
        log('  [缺] 模块入口不存在。请到 系统管理 → 模块管理 新建：')
        log('       名称=单月签排发填报 权限标识=%s 路径=/monthly-forecast' % PERMISSION)
    else:
        log('  [有] 模块入口「%s」 权限标识=%s 路径=%s' % (entry.name, entry.permission, entry.url))
    log('')
    return role


def main():
    parser = argparse.ArgumentParser(description='单月签排发填报 批量建号')
    parser.add_argument('--file', required=True, help='名单文件（xlsx/xls/csv）')
    parser.add_argument('--role', default=DEFAULT_ROLE, help='角色名，默认 %s' % DEFAULT_ROLE)
    parser.add_argument('--password', default='123456', help='初始密码，默认 123456')
    parser.add_argument('--with-scope', action='store_true', help='同时写模块归属')
    parser.add_argument('--reset-scope', action='store_true',
                        help='覆盖已有归属（默认不动已有归属的行）')
    parser.add_argument('--only-mapping-sheet', action='store_true',
                        help='只给「%s」里出现过的人建号' % AUTHORITATIVE_SHEET)
    parser.add_argument('--skip-dt', action='append', default=[],
                        help='要跳过的 DT 号，可重复')
    parser.add_argument('--dry-run', action='store_true', help='只打印，不写库')
    args = parser.parse_args()

    if not os.path.exists(args.file):
        log('[错误] 找不到名单文件：%s' % args.file)
        return 2
    if len(args.password) < 6:
        log('[错误] 密码不能少于 6 位')
        return 2

    from app import create_app
    app = create_app()

    with app.app_context():
        from flask_bcrypt import Bcrypt
        from models import Module, Role, User, db
        from monthly_forecast import mapping
        from monthly_forecast.models import UserScope

        role = show_platform_check(Role, Module)
        if role is None:
            log('[中止] 请先在平台上建好角色「%s」，再跑本脚本。' % args.role)
            return 1
        if role.role_name != args.role:
            role = Role.query.filter_by(role_name=args.role).first()
            if role is None:
                log('[中止] 角色「%s」不存在。' % args.role)
                return 1

        rows, dup = read_roster(args.file)
        log('名单读取：%d 条（重复 DT 跳过 %d 条）' % (len(rows), len(dup)))
        for dt, name in dup:
            log('   重复 DT：%s %s' % (dt, name))

        person2modules = {}
        if args.with_scope or args.only_mapping_sheet:
            try:
                info = mapping.load_person_modules()
            except FileNotFoundError as exc:
                log('[中止] %s' % exc)
                return 1
            person2modules = info['person2modules']
            log('模块来源表：%s' % os.path.basename(info['path']))

        if args.only_mapping_sheet:
            sheet_names = set()
            sheets = mapping._load_sheet_rows(mapping.latest_mapping_file())
            for row in sheets.get(AUTHORITATIVE_SHEET, [])[1:]:
                for person in mapping.clean_person(row[2] if len(row) > 2 else ''):
                    sheet_names.add(person)
            before = len(rows)
            rows = [x for x in rows if x[1] in sheet_names]
            log('只保留「%s」里的人：%d → %d 条' % (AUTHORITATIVE_SHEET, before, len(rows)))

        bcrypt = Bcrypt()
        skip_dt = {str(x).strip() for x in args.skip_dt if str(x).strip()}
        created, skipped, no_module = [], [], []
        targets = []
        for dt, name in rows:
            if not dt:
                skipped.append((name, dt, '没有 DT 号'))
                continue
            if dt in skip_dt:
                skipped.append((name, dt, '按 --skip-dt 指定跳过'))
                continue
            existing = User.query.filter_by(username=dt).first()
            if existing is not None:
                skipped.append((name, dt, '账号已存在'))
                targets.append((existing, name, dt))
                continue
            user = User(username=dt, real_name=name, role_id=role.id, is_active=True)
            if not args.dry_run:
                user.password = bcrypt.generate_password_hash(args.password).decode('utf-8')
                db.session.add(user)
                db.session.flush()
            created.append((user, name, dt))
            targets.append((user, name, dt))

        if args.with_scope:
            kept_scope = 0
            for user, name, dt in targets:
                modules = set()
                for person in mapping.clean_person(name):
                    modules.update(person2modules.get(person, ()))
                if len(modules) != 1:
                    no_module.append((name, dt, '/'.join(sorted(modules)) or '查不到'))
                    continue
                if args.dry_run:
                    continue
                if UserScope.query.filter_by(user_id=user.id).count() and not args.reset_scope:
                    kept_scope += 1
                    continue
                module_name = sorted(modules)[0]
                UserScope.query.filter_by(user_id=user.id).delete()
                db.session.add(UserScope(user_id=user.id, match_key=dt, module_name=module_name))
            if kept_scope:
                log('  已有归属未改动：%d 个' % kept_scope)

        if not args.dry_run:
            db.session.commit()

        log('')
        log('--- 结果 ---')
        log('  %s新建账号：%d 个' % ('(演练) ' if args.dry_run else '', len(created)))
        log('  跳过：%d 个' % len(skipped))
        for name, dt, why in skipped:
            log('     %s %s —— %s' % (dt or '-', name, why))
        if args.with_scope:
            log('  未写模块归属：%d 个（多模块或查不到，请手动加）' % len(no_module))
            for name, dt, why in no_module:
                log('     %s %s —— %s' % (dt, name, why))
        log('')
        log('  原有账号、角色、模块均未改动。')

    return 0


if __name__ == '__main__':
    sys.exit(main())
