#!/usr/bin/env python3
"""Check duplicate draft application and competing descriptions on temporary SQLite."""
import json, os, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
with tempfile.TemporaryDirectory(prefix='fsp-draft-concurrency-') as directory:
    os.environ.update(FSP_ENV_FILE='/dev/null',DEBUG='1',DATABASE_PATH=str(Path(directory)/'check.sqlite3'),DJANGO_SETTINGS_MODULE='config.settings')
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connections
    from accounts.models import User
    from profiles.models import Profile
    from hiring.models import Need
    from assistant.models import Draft
    from assistant.drafts import create_draft,form_for,apply_draft,StaleDraft
    call_command('migrate',verbosity=0)
    employer=User.objects.create_user(username='draft-concurrent-e@demo.invalid',role='employer')
    need_draft=create_draft(employer,'need','Мок задач',{'grade':'Junior','skills':'Swift'})
    values={'title':'Демо роль','grade':'Junior','skills':'Swift','tasks':'Задачи','salary_min':100,'salary_max':200,
        'work_format':'remote','next_step':'Разговор','company_name':'Демо компания','company_email':'team@demo.invalid'}
    def need_apply(_):
        try:
            user=User.objects.get(pk=employer.pk);draft=Draft.objects.get(pk=need_draft.pk)
            form=form_for(draft,values);assert form.is_valid(),form.errors
            return apply_draft(user,draft.pk,form).applied_need_id
        finally:connections.close_all()
    with ThreadPoolExecutor(max_workers=8) as pool:ids=list(pool.map(need_apply,range(8)))
    assert len(set(ids))==1 and Need.objects.count()==1
    candidate=User.objects.create_user(username='draft-concurrent-c@demo.invalid',role='candidate')
    profile=Profile.objects.create(user=candidate,description='До черновиков')
    drafts=[create_draft(candidate,'profile','Мок',{}) for _ in range(2)]
    def description_apply(index):
        try:
            user=User.objects.get(pk=candidate.pk);draft=Draft.objects.get(pk=drafts[index%2].pk)
            form=form_for(draft,{'description':f'Проверенное описание {index%2}'})
            assert form.is_valid()
            try:return {'draft':draft.pk,'result':'applied','id':apply_draft(user,draft.pk,form).pk}
            except StaleDraft:return {'draft':draft.pk,'result':'stale'}
        finally:connections.close_all()
    with ThreadPoolExecutor(max_workers=8) as pool:outcomes=list(pool.map(description_apply,range(8)))
    applied=Draft.objects.filter(user=candidate,applied_at__isnull=False)
    assert applied.count()==1
    winner=applied.get();profile.refresh_from_db();assert profile.description==winner.payload['description']
    assert sum(o['result']=='applied' for o in outcomes)==4
    assert sum(o['result']=='stale' for o in outcomes)==4
    print(json.dumps({'status':'PASS','isolation':'temporary SQLite, no production data','calls_per_scenario':8,
        'need_rows':Need.objects.count(),'same_need_for_replays':len(set(ids))==1,
        'description_drafts_applied':applied.count(),'competing_description_conflicts':4},indent=2))
    connections.close_all()
