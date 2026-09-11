import sqlite3
c = sqlite3.connect(r"E:\System\backend\instance\system.db")
cur = c.cursor()
cur.execute("select id,code,name,parent_id from upload_config where code like 'contract%' or code like '%schedule%'")
for r in cur.fetchall():
    print(r)
print('--- last 25 uploads for contract_ledger ---')
cur.execute("""
select f.id, f.filename, f.file_size, f.status, f.uploaded_at, f.ip_address, substr(coalesce(f.message,''),1,200)
from file_upload f join upload_config u on u.id = f.upload_config_id
where u.code='contract_ledger' order by f.id desc limit 25
""")
for r in cur.fetchall():
    print(r)
print('--- counts by code/status ---')
cur.execute("""
select u.code, f.status, count(*), max(f.uploaded_at)
from file_upload f join upload_config u on u.id=f.upload_config_id
group by u.code, f.status order by u.code
""")
for r in cur.fetchall():
    print(r)
