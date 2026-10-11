#!/usr/bin/env python3
"""Run on digitarium: fingerprint persistent entities and validate SQLite backup restoration."""
import hashlib,json,sqlite3,tempfile
from pathlib import Path
root=Path.home()/'fsp-mvp';db=root/'shared/db.sqlite3'
tables=['accounts_user','profiles_profile','assessments_attempt','hiring_company','hiring_need','hiring_invitation']
def snapshot(connection):
    result={}
    for table in tables:
        rows=connection.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
        result[table]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
    return result
with sqlite3.connect(db) as source:
    state=snapshot(source)
    with tempfile.TemporaryDirectory(prefix='fsp-backup-check-') as tmp:
        copy=Path(tmp)/'restored.sqlite3'
        with sqlite3.connect(copy) as restored:
            source.backup(restored)
            assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert snapshot(restored)==state
print(json.dumps({'status':'PASS','commit':(root/'current/REVISION').read_text().strip(),'backup_restore':'PASS','state':state},indent=2))
