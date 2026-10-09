#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单模块名 扫描 / 删除 / 改名（默认只扫描，不写库）
================================================================
用途：像「伊朗+阿曼」这种旧模块，拆分/改名后仍有残留数据留在库里，
      导致该模块继续出现在填报模块列表里。本脚本把它的残留清掉。

  * 扫描：遍历库里所有含 module_name 列的表，列出命中行数（不写库）
  * 删除：把命中的行删掉（--delete）
  * 改名：把命中的行改成另一个模块名（--rename-to，如 伊朗+阿曼 -> 伊朗）

安全设计（与 migrate_mf_module_names.py 同一套）：
  1) 默认不写库；只有同时给 --apply 才真正写。
  2) --apply 先用 SQLite 在线备份 API 生成一致性快照 <db>.bak-<时间戳>，
     并写改动流水 <备份>.journal.json。
  3) 所有改动放在一个事务里，出错整体回滚。
  4) 改名时若与已有行撞唯一键，该行【跳过并打印】，绝不覆盖。
  5) --rollback-latest / --rollback <文件> 一键还原（还原前也会先给当前库做快照）。

用法：
  # 不带 --module：跑内置预设（仅删 mf_ 四张填报表里的 伊朗+阿曼），默认只预览
  python3 remove_mf_module.py --db backend/instance/system.db
  python3 remove_mf_module.py --db backend/instance/system.db --apply

  # 指定单个模块名；--scope mf 只动填报四表，--scope all 动所有含 module_name 的表
  python3 remove_mf_module.py --db backend/instance/system.db --module "伊朗+阿曼" --scope mf
  python3 remove_mf_module.py --db backend/instance/system.db --module "伊朗+阿曼" --scope mf --show
  python3 remove_mf_module.py --db backend/instance/system.db --module "伊朗+阿曼" --scope mf --delete --apply
  python3 remove_mf_module.py --db backend/instance/system.db --module "伊朗+阿曼" --rename-to 阿曼 --apply
  python3 remove_mf_module.py --db backend/instance/system.db --rollback-latest
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 填报四表（签排发预计填报模块）
MF_TABLES = ["mf_monthly_input", "mf_ship_selection", "mf_submission", "mf_user_scope"]

# 内置预设（不指定 --module 时执行）
PRESETS = [
    {"module": "伊朗+阿曼", "action": "delete", "scope": "mf", "rename_to": None},
]


def ts():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def tables_with_module_name(cur):
    names = [r[0] for r in cur.execute(
        "select name from sqlite_master where type='table'").fetchall()]
    out = []
    for t in names:
        cols = [c[1] for c in cur.execute("pragma table_info(%s)" % t).fetchall()]
        if "module_name" in cols:
            out.append(t)
    return sorted(out)


def unique_keys(cur, table):
    keys = []
    for row in cur.execute("pragma index_list(%s)" % table).fetchall():
        name, uniq = row[1], row[2]
        if not uniq:
            continue
        cols = [c[2] for c in cur.execute("pragma index_info(%s)" % name).fetchall()]
        if any(c is None for c in cols):
            continue
        keys.append(cols)
    return keys


def backup_db(src, dst):
    if os.path.abspath(src) == os.path.abspath(dst):
        raise RuntimeError("备份路径不能与源库相同")
    con = sqlite3.connect(src)
    try:
        bck = sqlite3.connect(dst)
        try:
            con.backup(bck)
        finally:
            bck.close()
    finally:
        con.close()


def is_sqlite_file(path):
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def latest_backup(db):
    pat = re.compile(re.escape(os.path.normpath(db)) + r"\.bak-\d{8}-\d{6}$")
    cands = sorted(x for x in glob.glob(db + ".bak-*")
                   if pat.match(os.path.normpath(x)))
    return cands[-1] if cands else None


def scan(cur, module, scope="all"):
    """返回 [(table, [rowid...])]，仅含命中行"""
    res = []
    tabs = tables_with_module_name(cur)
    if scope == "mf":
        tabs = [t for t in tabs if t in MF_TABLES]
    for t in tabs:
        rows = cur.execute(
            "select id from %s where module_name = ?" % t, (module,)
        ).fetchall()
        if rows:
            res.append((t, [r[0] for r in rows]))
    return res


def show_rows(cur, table, ids):
    cols = [c[1] for c in cur.execute("pragma table_info(%s)" % table)]
    sel = ",".join(cols)
    for i in ids:
        r = cur.execute("select %s from %s where id = ?" % (sel, table), (i,)).fetchone()
        d = dict(zip(cols, r))
        d.pop("payload", None)
        print("      %s" % d)


def plan_conflicts(cur, table, old, new):
    """改名 old->new 时，返回会撞唯一键的 id 集合"""
    keys = unique_keys(cur, table)
    conflict = set()
    for k in keys:
        if "module_name" not in k:
            continue
        other = [c for c in k if c != "module_name"]
        if not other:
            continue
        rows = cur.execute(
            "select id,%s from %s where module_name = ?" % (",".join(other), table), (old,)
        ).fetchall()
        cond = " and ".join("%s IS ?" % c for c in other)
        for row in rows:
            i = row[0]
            vals = list(row[1:])
            hit = cur.execute(
                "select 1 from %s where module_name = ? and %s" % (table, cond),
                [new] + vals,
            ).fetchone()
            if hit:
                conflict.add(i)
    return conflict


def run(db, module, do_delete, rename_to, scope, show, apply_write):
    if not os.path.isfile(db):
        print("[错误] 找不到数据库: %s" % db)
        return 2
    if not module:
        print("[错误] 必须给 --module")
        return 2
    if do_delete and rename_to:
        print("[错误] --delete 和 --rename-to 不能同时用")
        return 2

    con = sqlite3.connect(db)
    cur = con.cursor()
    hits = scan(cur, module, scope)

    scope_name = "仅填报四表(mf_)" if scope == "mf" else "全部含 module_name 的表"
    print("\n================ 扫描结果：模块 '%s'（范围: %s） ================" % (module, scope_name))
    if not hits:
        print("  库里没有任何表包含该模块名。（线上填报列表若还显示，多半来自")
        print("  常量表/MODULE_REGION 或前端缓存，需要改代码或强刷页面。）")
        con.close()
        return 0
    total = 0
    total_conf = 0
    for t, ids in hits:
        total += len(ids)
        line = "  %-22s 命中 %d 行" % (t, len(ids))
        if rename_to:
            conf = plan_conflicts(cur, t, module, rename_to)
            if conf:
                total_conf += len(conf)
                line += "  冲突 %d 行 -> 将跳过" % len(conf)
        print(line)
        if show:
            show_rows(cur, t, ids)
    print("  ----------------------------------------------------")
    print("  合计命中 %d 行%s" % (total, ("，冲突 %d 行" % total_conf) if total_conf else ""))
    if total_conf:
        print("  ※ 冲突行不会自动改，需人工决定「合并/删除」。(用 --show 看明细)")

    if not apply_write:
        print("\n[dry-run] 未写入。确认无误后加 --apply 执行。")
        con.close()
        return 0
    if not (do_delete or rename_to):
        print("\n[提示] 已给 --apply 但没指定 --delete 或 --rename-to，未做任何改动。")
        con.close()
        return 0

    backup = "%s.bak-%s" % (db, ts())
    backup_db(db, backup)
    print("\n[备份] 已生成一致性快照: %s" % backup)

    journal = {"time": ts(), "db": os.path.abspath(db), "backup": os.path.abspath(backup),
               "module": module, "action": "delete" if do_delete else ("rename->%s" % rename_to),
               "changes": []}
    changed = 0
    skipped = 0
    try:
        for t, ids in hits:
            if do_delete:
                cur.executemany("delete from %s where id = ?" % t, [(i,) for i in ids])
                changed += len(ids)
                journal["changes"].append({"table": t, "action": "delete", "ids": ids})
                print("[删除] %s: %d 行" % (t, len(ids)))
            else:
                conf = plan_conflicts(cur, t, module, rename_to)
                todo = [i for i in ids if i not in conf]
                if conf:
                    skipped += len(conf)
                    print("[跳过] %s: %d 行与新名 '%s' 撞唯一键，未改（需人工决定合并/删除）"
                          % (t, len(conf), rename_to))
                if todo:
                    cur.executemany(
                        "update %s set module_name = ? where id = ?" % t,
                        [(rename_to, i) for i in todo])
                    changed += len(todo)
                    journal["changes"].append({"table": t, "action": "rename",
                                               "from": module, "to": rename_to, "ids": todo})
                    print("[改名] %s: %s -> %s, %d 行" % (t, module, rename_to, len(todo)))
        con.commit()
    except Exception as exc:
        con.rollback()
        con.close()
        print("[错误] 操作失败，已整体回滚，数据库未变: %s" % exc)
        print("       备份文件仍在: %s" % backup)
        return 1

    jp = backup + ".journal.json"
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(journal, f, ensure_ascii=False, indent=2)
    print("\n[完成] 变更 %d 行, 跳过 %d 行。" % (changed, skipped))
    print("[流水] %s" % jp)
    print("[还原] python3 %s --db %s --rollback-latest" % (os.path.basename(__file__), db))
    con.close()
    return 0


def run_rollback(db, backup):
    if backup is None:
        backup = latest_backup(db)
        if not backup:
            print("[错误] 未找到备份文件: %s.bak-*" % db)
            return 2
        print("[还原] 使用最近备份: %s" % backup)
    if not os.path.isfile(backup):
        print("[错误] 找不到备份文件: %s" % backup)
        return 2
    if not is_sqlite_file(backup):
        print("[错误] 这不是一个 SQLite 数据库文件，拒绝还原: %s" % backup)
        return 2
    if os.path.isfile(db):
        pre = "%s.pre-rollback-%s" % (db, ts())
        backup_db(db, pre)
        print("[快照] 当前库已另存: %s" % pre)
    shutil.copy2(backup, db)
    for ext in ("-wal", "-shm"):
        p = db + ext
        if os.path.isfile(p):
            os.remove(p)
    print("[还原] 已用 %s 还原 -> %s" % (backup, db))
    return 0


def main():
    ap = argparse.ArgumentParser(description="单模块名 扫描/删除/改名（默认只扫描）")
    ap.add_argument("--db", default="backend/instance/system.db", help="SQLite 数据库路径")
    ap.add_argument("--module", help="要处理的模块名，如 伊朗+阿曼")
    ap.add_argument("--delete", action="store_true", help="删除命中的行")
    ap.add_argument("--rename-to", metavar="NEW", help="把命中的行改成该模块名")
    ap.add_argument("--show", action="store_true", help="打印命中行的明细")
    ap.add_argument("--scope", choices=["all", "mf"], default="all",
                    help="处理范围: all=所有含module_name的表(默认), mf=仅填报四表")
    ap.add_argument("--apply", action="store_true", help="真正写入（默认只扫描）")
    ap.add_argument("--rollback", metavar="BACKUP", help="用备份文件还原数据库")
    ap.add_argument("--rollback-latest", action="store_true", help="用最近一次备份还原")
    a = ap.parse_args()
    if a.rollback or a.rollback_latest:
        return run_rollback(a.db, a.rollback)
    if a.module:
        return run(a.db, a.module, a.delete, a.rename_to, a.scope, a.show, a.apply)
    print("[预设] 未指定 --module，执行内置任务:")
    for p in PRESETS:
        act = ("删除" if p["action"] == "delete" else ("改名 -> %s" % p["rename_to"]))
        print("       模块 '%s': %s（范围: %s）" % (p["module"], act, "仅填报四表" if p["scope"] == "mf" else "全部表"))
    rc = 0
    for p in PRESETS:
        rc = run(a.db, p["module"], p["action"] == "delete", p.get("rename_to"),
                 p.get("scope", "all"), a.show, a.apply) or rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
