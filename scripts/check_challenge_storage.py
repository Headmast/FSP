"""Actual file-backed SQLite races and rollback privacy fences, using disposable own fixtures."""
import hashlib,json,os,shutil,sqlite3,sys,tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]


def main():
    (ROOT/'.runtime').mkdir(exist_ok=True)
    checks=[]
    with tempfile.TemporaryDirectory(prefix='challenge-storage-',dir=ROOT/'.runtime') as directory:
        folder=Path(directory);db=folder/'db.sqlite3';ledger=folder/'privacy-ledger.jsonl'
        os.environ.update(FSP_ENV_FILE='/dev/null',DATABASE_PATH=str(db),PRIVACY_LEDGER_PATH=str(ledger),DEBUG='1',DJANGO_SETTINGS_MODULE='config.settings')
        sys.path.insert(0,str(ROOT/'app'))
        import django;django.setup()
        from django.core.management import call_command
        from django.db import connections
        from django.utils import timezone
        from accounts.models import User
        from profiles.models import Profile
        from profiles.privacy import request_action,reconcile
        from hiring.models import Company,Need,GapChallenge
        from hiring.services import invite,decide,contacts_allowed
        from hiring import challenges as service
        from hiring.challenge_projection import data as projection
        call_command('migrate',verbosity=0)
        def user(name,role):return User.objects.create_user(username=name+'@demo.invalid',email=name+'@demo.invalid',role=role,
            email_confirmed=True,processing_consented_at=timezone.now(),processing_consent_version='processing-v1')
        candidate=user('storage-candidate','candidate');employer=user('storage-employer','employer')
        profile=Profile.objects.create(user=candidate,name='Тестовый Кандидат',confirmed_grade='Junior',test_score=.75,published=True,skills='Swift')
        company=Company.objects.create(user=employer,name='Тестовая Компания',contact_email='company@demo.invalid')
        need=Need.objects.create(company=company,title='iOS',grade='Junior',skills='Swift, Combine, XCTest',tasks='Экран',salary_min=1,salary_max=2,work_format='remote')
        invitation=invite(company,need.pk,profile.pk);decide(profile,invitation.pk,'accepted')
        def task(skill):
            return service.send(employer,invitation.pk,request_id=uuid4(),skill=skill,title='Проверка навыка',
                instructions='CHALLENGE_STORAGE_PRIVATE',criteria=['Решение','Обоснование'],pass_points=3,duration_minutes=15,
                deadline_at=timezone.now()+timedelta(days=7))[0]
        def race(first,second):
            barrier=Barrier(2)
            def run(fn):
                try:
                    barrier.wait(timeout=10);fn();return 'applied'
                except service.ChallengeConflict:return 'conflict'
                finally:connections.close_all()
            connections.close_all()
            with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(run,[first,second]))
        obj=task('Combine');service.action(candidate,obj.pk,'accept',revision=0,acknowledge=True)
        results=race(lambda:service.action(candidate,obj.pk,'submit',revision=1,acknowledge=True,answer='Первый ответ'),
            lambda:service.action(candidate,obj.pk,'submit',revision=1,acknowledge=True,answer='Второй ответ'))
        assert sorted(results)==['applied','conflict'];obj.refresh_from_db();assert obj.revision==2 and obj.state=='submitted'
        results=race(lambda:service.review(employer,obj.pk,revision=2,scores=[2,2],note='Первая оценка',acknowledge=True),
            lambda:service.review(employer,obj.pk,revision=2,scores=[1,1],note='Вторая оценка',acknowledge=True))
        assert sorted(results)==['applied','conflict'];obj.refresh_from_db();assert obj.revision==3 and obj.state=='reviewed'
        checks.append('file-backed SQLite simultaneous submit/review: one fixed result and one conflict, no duplicates or overwrite')
        other=task('XCTest');service.action(candidate,other.pk,'accept',revision=0,acknowledge=True)
        service.action(candidate,other.pk,'submit',revision=1,answer='CHALLENGE_STORAGE_PRIVATE',acknowledge=True)
        results=race(lambda:service.action(candidate,other.pk,'revoke',revision=2,acknowledge=True),
            lambda:service.review(employer,other.pk,revision=2,scores=[2,2],note='Оценка до отзыва',acknowledge=True))
        other.refresh_from_db();assert other.state=='revoked' and other.consent_revoked_at and not service.share_open(other)
        assert projection(other,employer)['result'] is None
        checks.append('simultaneous owner revoke and company review: final share always closed, stale revision cannot block revoke')
        def backup(name):
            path=folder/name;source=sqlite3.connect(db);target=sqlite3.connect(path)
            try:source.backup(target)
            finally:target.close();source.close()
            return path
        def restore(path):
            connections.close_all()
            for suffix in ['-wal','-shm']:Path(str(db)+suffix).unlink(missing_ok=True)
            shutil.copyfile(path,db)
        # The first task is reviewed and not revoked. Restore a real pre-revoke copy.
        before_revoke=backup('before-revoke.sqlite3')
        service.action(candidate,obj.pk,'revoke',revision=0,acknowledge=True);restore(before_revoke)
        obj=GapChallenge.objects.get(pk=obj.pk);assert service.share_open(obj)
        reconcile();obj.refresh_from_db();assert obj.consent_revoked_at and not service.share_open(obj)
        checks.append('actual pre-task-revoke SQLite backup restores old consent; durable task UUID fence closes it before serving')
        before_clear=backup('before-clear.sqlite3');assert b'CHALLENGE_STORAGE_PRIVATE' in before_clear.read_bytes()
        request_action(candidate,'clear_profile',uuid4());restore(before_clear);assert GapChallenge.objects.filter(candidate=profile).exists()
        reconcile();assert not GapChallenge.objects.filter(candidate=profile).exists()
        for archived in GapChallenge.objects.all():
            assert archived.state=='erased' and not archived.answer and not archived.instructions and archived.criteria==[]
            assert archived.review_scores==[] and not archived.review_note and not archived.reviewed_by_id
        checks.append('actual pre-clear backup: profile fence erases all challenge text/results and detaches rows again')
        old=timezone.now()-timedelta(days=181);GapChallenge.objects.update(candidate_erased_at=old)
        call_command('privacy_maintenance',verbosity=0);assert not GapChallenge.objects.exists()
        assert (folder/'privacy-floor-v1').read_text().strip()=='2'
        connections.close_all();assert b'CHALLENGE_STORAGE_PRIVATE' not in db.read_bytes()
        checks.append('180-day challenge archive expiry, floor2 retained, secure_delete/WAL truncate remove task canary from live DB bytes')
    report={'task':'PROD-002','status':'PASS','checks':checks,'database':'disposable own SQLite/ledger/fixtures removed; production untouched',
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['app/hiring/challenges.py','app/hiring/models.py','app/profiles/privacy.py','scripts/check_challenge_storage.py']}}
    target=ROOT/'.runtime/qa/PROD-002-storage.json';target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('PASS:',len(checks),'actual SQLite concurrency/restore/privacy assertions')


if __name__=='__main__':main()
