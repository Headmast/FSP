"""Upgrade an isolated pre-PROD-001 database, retaining profiles, needs and old offers."""
import json
import os
import sys
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]


def main():
    (ROOT/'.runtime').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='conditions-upgrade-',dir=ROOT/'.runtime') as tmp:
        os.environ.update(FSP_ENV_FILE='/dev/null',DATABASE_PATH=str(Path(tmp)/'upgrade.sqlite3'),
                          DJANGO_SETTINGS_MODULE='config.settings',DEBUG='1')
        sys.path.insert(0,str(ROOT/'app'))
        import django
        django.setup()
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        old=[('profiles','0005_alter_profile_fsp_status_fsplink_achievement'),('hiring','0003_recruiter_invitation_recruiter_need_recruiter')]
        executor=MigrationExecutor(connection);executor.migrate(old)
        apps=executor.loader.project_state(old).apps
        User=apps.get_model('accounts','User');Profile=apps.get_model('profiles','Profile')
        Company=apps.get_model('hiring','Company');Need=apps.get_model('hiring','Need');Invitation=apps.get_model('hiring','Invitation')
        candidate=User.objects.create(username='upgrade-candidate@demo.invalid',role='candidate')
        employer=User.objects.create(username='upgrade-employer@demo.invalid',role='employer')
        profile=Profile.objects.create(user=candidate,name='Анна',confirmed_grade='Junior',test_score=.75,published=True)
        company=Company.objects.create(user=employer,name='Компания')
        need=Need.objects.create(company=company,title='iOS',grade='Junior',tasks='Задачи',salary_min=1,salary_max=2,work_format='remote')
        snapshot={'work_format':'Удалённо','salary_min':1,'salary_max':2,'grade':'Junior'}
        invitation=Invitation.objects.create(company=company,need=need,candidate=profile,snapshot=snapshot,status='accepted')
        executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
        from profiles.models import Profile as NewProfile
        from hiring.models import Need as NewNeed,Invitation as NewInvitation
        from profiles.conditions import compare_conditions,snapshot_conditions
        profile=NewProfile.objects.get(pk=profile.pk);need=NewNeed.objects.get(pk=need.pk)
        invitation=NewInvitation.objects.get(pk=invitation.pk)
        assert (profile.name,profile.confirmed_grade,profile.test_score,profile.published)==('Анна','Junior',.75,True)
        assert profile.preferred_work_formats==profile.preferred_employment_types==profile.preferred_task_types==[]
        assert need.employment_type=='' and need.task_types==[]
        assert (need.salary_min,need.salary_max,need.work_format)==(1,2,'remote')
        assert invitation.snapshot==snapshot and invitation.status=='accepted'
        assert len(compare_conditions(profile,need)['unknown'])==3
        assert len(snapshot_conditions(invitation.snapshot)['unknown'])==3
        connection.close()
    result={'task':'PROD-001','status':'PASS','checked_at':datetime.now(timezone.utc).isoformat(),
        'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'checks':['old-schema database created','existing data retained','five new fields default to unknown',
                  'accepted legacy invitation snapshot unchanged','three unknown conditions, no false match'],
        'database':'isolated temporary database removed'}
    target=ROOT/'.runtime/qa/PROD-001-migration.json';target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: isolated old-schema upgrade retained profiles, needs and accepted snapshots')


if __name__=='__main__':main()
