"""Verify real SQLite rollback/restore fences and retention on a disposable worktree-local database."""
import json,os,sys,sqlite3,shutil,tempfile,time
from pathlib import Path
from datetime import timedelta
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]


def main():
    (ROOT/'.runtime').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='privacy-restore-',dir=ROOT/'.runtime') as directory:
        target=Path(directory);db=target/'db.sqlite3';ledger=target/'privacy-ledger.jsonl'
        os.environ.update(DATABASE_PATH=str(db),PRIVACY_LEDGER_PATH=str(ledger),FSP_ENV_FILE='/dev/null',DJANGO_SETTINGS_MODULE='config.settings',DEBUG='1')
        sys.path.insert(0,str(ROOT/'app'))
        import django;django.setup()
        from django.core.management import call_command
        from django.db import connections
        from django.utils import timezone
        from accounts.models import User
        from profiles.models import Profile
        from profiles.privacy import request_action,reconcile,append_ledger
        from hiring.models import Company,Need,Invitation
        from hiring.services import invite,decide,contacts_allowed
        call_command('migrate',verbosity=0)
        def user(name,role):
            return User.objects.create_user(username=name+'@demo.invalid',email=name+'@demo.invalid',role=role,
                email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version='processing-v1')
        employer=user('restore-employer','employer');company=Company.objects.create(user=employer,name='Компания',contact_email='company@demo.invalid')
        need=Need.objects.create(company=company,title='Роль',grade='Junior',tasks='Тест',salary_min=1,salary_max=2,work_format='remote')
        checks=[]
        def backup(name):
            path=target/name
            source=sqlite3.connect(db);destination=sqlite3.connect(path)
            try:source.backup(destination)
            finally:destination.close();source.close()
            return path
        def restore(path):
            connections.close_all()
            for suffix in ['-wal','-shm']:Path(str(db)+suffix).unlink(missing_ok=True)
            shutil.copyfile(path,db)
        candidate=user('restore-clear','candidate')
        profile=Profile.objects.create(user=candidate,name='Имя',description='RESTORE_PRIVATE_DESCRIPTION',contact_email='RESTORE_PRIVATE_EMAIL@demo.invalid',published=True,confirmed_grade='Junior')
        obj=invite(company,need.pk,profile.pk,discussion='RESTORE_PRIVATE_SNAPSHOT');decide(profile,obj.pk,'accepted')
        before=backup('before-clear.sqlite3')
        request_action(candidate,'clear_profile',uuid4());restore(before)
        assert Profile.objects.get(pk=profile.pk).contact_email=='RESTORE_PRIVATE_EMAIL@demo.invalid'
        call_command('privacy_maintenance',reconcile_only=True,verbosity=0)
        restored=Profile.objects.get(pk=profile.pk)
        assert restored.contact_email=='' and not contacts_allowed(company,restored)
        assert Invitation.objects.get(pk=obj.pk).candidate_id is None
        checks.append('actual pre-clear SQLite backup restores old data, fence erases it before serving')
        restored.name='Новое Имя';restored.save()
        deleted=user('restore-delete','candidate')
        erased=Profile.objects.create(user=deleted,name='Другое Имя',contact_email='DELETE_PRIVATE_EMAIL@demo.invalid',published=True,confirmed_grade='Junior')
        offered=invite(company,need.pk,erased.pk);decide(erased,offered.pk,'accepted')
        before_delete=backup('before-delete.sqlite3');old_id=deleted.pk
        request_action(deleted,'delete_account',uuid4());restore(before_delete)
        assert User.objects.filter(pk=old_id).exists();reconcile()
        assert not User.objects.filter(pk=old_id).exists()
        assert Profile.objects.get(pk=restored.pk).name=='Новое Имя'
        assert Invitation.objects.get(pk=offered.pk).candidate_id is None
        checks.append('actual account-delete backup fenced; prior applied clear does not erase new profile data')
        old=timezone.now()-timedelta(days=181)
        aged=Invitation.objects.create(company=company,need=need,candidate=None,status='sent',snapshot={'privacy_redacted':True},candidate_erased_at=old)
        append_ledger({'id':str(uuid4()),'user_id':999999,'identity':'0'*64,'action':'clear_profile','company_id':None,'created_at':old.isoformat()})
        folder=target/'backups';folder.mkdir()
        expired=folder/(str(int((time.time()-8*86400)*1e9))+'.sqlite3');shutil.copyfile(before,expired)
        recent=folder/(str(time.time_ns())+'.sqlite3');shutil.copyfile(before_delete,recent)
        unrelated=folder/'unrelated.sqlite3';unrelated.write_bytes(b'Unrelated data')
        call_command('privacy_maintenance',verbosity=0)
        assert not expired.exists() and recent.exists() and unrelated.read_bytes()==b'Unrelated data'
        assert not Invitation.objects.filter(pk=aged.pk).exists()
        assert all(row['created_at']!=old.isoformat() for row in map(json.loads,ledger.read_text().splitlines()))
        assert (target/'privacy-floor-v1').read_text().strip()=='1'
        assert recent.stat().st_mode & 0o777==0o600
        checks.append('180-day anonymous history/ledger expiry, 7-day owned backup expiry, unrelated files preserved, floor survives')
        connections.close_all()
        assert b'RESTORE_PRIVATE_EMAIL@demo.invalid' not in db.read_bytes()
        assert b'DELETE_PRIVATE_EMAIL@demo.invalid' not in db.read_bytes()
        checks.append('secure_delete plus successful WAL truncate remove canaries from current SQLite bytes')
    report={'task':'PROD-004','status':'PASS','checks':checks,'database':'owned disposable SQLite/ledger/backups removed; production untouched'}
    output=ROOT/'.runtime/qa/PROD-004-restore.json';output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS:',len(checks),'real SQLite restore/retention assertions; no production data touched')


if __name__=='__main__':main()
