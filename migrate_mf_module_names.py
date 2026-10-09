#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性数据迁移：单月签排发填报(mf_*) 旧模块名 -> 新模块名
================================================================
背景（2026-09-30 大区/模块重构）：
  部分"旧模块名"仍残留在填报数据里，导致旧模块继续显示、新模块为空。
  本脚本把 4 张 mf_ 表里的旧模块名改成新名，使"填报数据"和"模主归属
  (mf_user_scope)"一并转到新模块。

安全设计：
  1) 默认 dry-run，只统计、不写库。
  2) --apply：
       - 先用 SQLite 在线备份 API 生成一致性快照 <db>.bak-<时间戳>（含 WAL）
       - 记录改动流水 <备份>.journal.json（表/旧名/新名/受影响行id）
       - 全部改动放在一个事务里，出错自动回滚，绝不半途
       - 有唯一键冲突的行会被【跳过并打印】，绝不覆盖
  3) --rollback <备份文件>：用备份还原数据库；还原前也会先给"当前库"做快照。

用法：
  python3 migrate_mf_module_names.py --db backend/instance/system.db                    # 预览
  python3 migrate_mf_module_names.py --db backend/instance/system.db --apply             # 执行
  python3 migrate_mf_module_names.py --db backend/instance/system.db --rollback <备份文件>  # 还原
"""
import argparse
import datetime
import json
import os
import shutil
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 旧模块名 -> 新模块名（源自 2026-09-30 重构改名表；伊朗+阿曼是 1->2，暂不处理）
MAP = {
    "乌兹别克斯坦": "乌兹别克斯坦-1",
    "孟加拉-1": "孟加拉",
    "巴西": "巴西-1",
    "秘鲁": "秘鲁-1",
    "秘鲁2": "秘鲁-2",
    "菲律宾": "菲律宾-1",
    "金三角": "泰国",
    "香港-台湾": "日港台",
}

# 要迁移的表（都含 module_name 列）
TABLES = ["mf_monthly_input", "mf_ship_selection", "mf_submission", "mf_user_scope"]

# 每张表唯一键里【除 module_name 之外】的列，用于查"改名后是否会撞唯一键"
KEYCOLS = {
    "mf_monthly_input": ["data_month"],
    "mf_ship_selection": ["data_month", "ladder_no"],
    "mf_submission": ["data_month", "version"],
    "mf_user_scope": ["user_id"],
}


def ts():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def table_exists(cur, name):
    return cur.execute(
        "select 1 from sqlite_master where type='table' and name=?", (name,)
    ).fetchone() is not None


def backup_db(src, dst):
    """用 SQLite 在线备份 API 生成一致性快照（WAL 也安全）"""
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


def build_plan(cur, olds):
    """返回 [(table, old, new, [rowids], conflict_count)]"""
    plan = []
    for t in TABLES:
        if not table_exists(cur, t):
            print("[跳过] 无此表: %s" % t)
            continue
        for old in olds:
            rows = cur.execute(
                "select id from %s where module_name = ?" % t, (old,)
            ).fetchall()
            if not rows:
                continue
            ids = [r[0] for r in rows]
            new = MAP[old]
            ks = KEYCOLS[t]
            # 冲突：存在一条"新名"行，且除 module_name 外的唯一键与某条旧名行相同
            #（SQLite 的 IS 是空值安全的相等比较）
            cond = " and ".join("n.%s IS o.%s" % (k, k) for k in ks)
            conflict = cur.execute(
                "select count(*) from {t} o where o.module_name = ? and exists ("
                "  select 1 from {t} n where n.module_name = ? and {cond})".format(
                    t=t, cond=cond
                ),
                (old, new),
            ).fetchone()[0]
            plan.append((t, old, new, ids, conflict))
    return plan


def print_plan(plan):
    if not plan:
        print("\n没有需要迁移的旧模块名（已经是新名或数据为空）。")
        return
    print("\n================ 迁移计划（预览） ================")
    total_rows = total_conf = 0
    for t, old, new, ids, conflict in plan:
        total_rows += len(ids)
        total_conf += conflict
        mark = "  冲突 %d 行 -> 将跳过" % conflict if conflict else ""
        print("  %-18s  %-12s -> %-12s  命中 %d 行%s" % (t, old, new, len(ids), mark))
    print("  -------------------------------------------------")
    print("  合计: 命中 %d 行, 冲突 %d 行" % (total_rows, total_conf))
    if total_conf:
        print("  ※ 有冲突的行不会自动改，需要人工决定「合并/删除」后再处理。")


def run_migrate(db, apply_write):
    if not os.path.isfile(db):
        print("[错误] 找不到数据库: %s" % db); return 2
    con = sqlite3.connect(db)
    cur = con.cursor()
    olds = list(MAP)
    plan = build_plan(cur, olds)
    print_plan(plan)

    if not apply_write:
        print("\n[dry-run] 未写入。确认无误后加 --apply 执行。")
        con.close()
        return 0

    if not plan:
        con.close()
        return 0

    # 1) 一致性备份
    backup = "%s.bak-%s" % (db, ts())
    backup_db(db, backup)
    print("\n[备份] 已生成一致性快照: %s" % backup)

    # 2) 事务内改名（冲突行跳过）
    journal = {"time": ts(), "db": os.path.abspath(db), "backup": os.path.abspath(backup),
               "changes": []}
    changed = 0
    try:
        for t, old, new, ids, conflict in plan:
            if conflict:
                # 只改"没有冲突"的行；冲突行保持原样
                ks = KEYCOLS[t]
                cond = " and ".join("n.%s IS o.%s" % (k, k) for k in ks)
                ids = [r[0] for r in cur.execute(
                    "select o.id from {t} o where o.module_name = ? and not exists ("
                    "  select 1 from {t} n where n.module_name = ? and {cond})".format(
                        t=t, cond=cond), (old, new)).fetchall()]
            if not ids:
                continue
            cur.executemany(
                "update %s set module_name = ? where id = ?" % t,
                [(new, i) for i in ids],
            )
            changed += len(ids)
            journal["changes"].append({"table": t, "old": old, "new": new, "ids": ids})
            print("[改名] %s: %s -> %s, %d 行" % (t, old, new, len(ids)))
        con.commit()
    except Exception as exc:
        con.rollback()
        con.close()
        print("[错误] 迁移失败，已整体回滚，数据库未变: %s" % exc)
        print("       备份文件仍在: %s" % backup)
        return 1

    # 3) 写改动流水（便于审计/核对；还原用备份文件即可）
    jp = backup + ".journal.json"
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(journal, f, ensure_ascii=False, indent=2)
    print("\n[完成] 共改名 %d 行。" % changed)
    print("[流水] %s" % jp)
    print("[还原] 如需还原: python3 %s --db %s --rollback %s"
          % (os.path.basename(__file__), db, backup))
    con.close()
    return 0


def latest_backup(db):
    """只认 <db>.bak-YYYYmmdd-HHMMSS，避免误选到 .journal.json"""
    import glob
    import re
    pat = re.compile(re.escape(os.path.normpath(db)) + r"\.bak-\d{8}-\d{6}$")
    cands = sorted(x for x in glob.glob(db + ".bak-*")
                   if pat.match(os.path.normpath(x)))
    return cands[-1] if cands else None


def is_sqlite_file(path):
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def run_rollback(db, backup):
    if not os.path.isfile(backup):
        print("[错误] 找不到备份文件: %s" % backup); return 2
    if not is_sqlite_file(backup):
        print("[错误] 这不是一个 SQLite 数据库文件，拒绝还原: %s" % backup); return 2
    if not os.path.isfile(db):
        print("[警告] 目标库不存在，将直接用备份创建。")
    else:
        pre = "%s.pre-rollback-%s" % (db, ts())
        backup_db(db, pre)
        print("[快照] 当前库已另存: %s" % pre)
    # 用备份覆盖目标库，并清掉可能残留的 WAL/SHM（备份本身是完整快照）
    shutil.copy2(backup, db)
    for ext in ("-wal", "-shm"):
        p = db + ext
        if os.path.isfile(p):
            os.remove(p)
    print("[还原] 已用 %s 还原 -> %s" % (backup, db))
    return 0


def main():
    ap = argparse.ArgumentParser(description="mf_* 旧模块名 -> 新模块名 数据迁移")
    ap.add_argument("--db", default="backend/instance/system.db", help="SQLite 数据库路径")
    ap.add_argument("--apply", action="store_true", help="真正写入（默认只预览）")
    ap.add_argument("--rollback", metavar="BACKUP", help="用备份文件还原数据库")
    ap.add_argument("--rollback-latest", action="store_true",
                    help="自动用最近一次 <db>.bak-* 备份还原")
    a = ap.parse_args()
    if a.rollback_latest:
        bk = latest_backup(a.db)
        if not bk:
            print("[错误] 未找到备份文件: %s.bak-*" % a.db); return 2
        print("[还原] 使用最近备份: %s" % bk)
        return run_rollback(a.db, bk)
    if a.rollback:
        return run_rollback(a.db, a.rollback)
    return run_migrate(a.db, a.apply)


if __name__ == "__main__":
    sys.exit(main())
