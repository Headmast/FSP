"""Synthetic, ignored QA fixtures only. Never print tokens."""
import json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'app'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.core.management import call_command
from accounts.models import User
from api.core import issue_token
from hiring.models import Need,Company,GapChallenge
from hiring.services import invite,decide
from hiring import challenges
from profiles.skills import SKILLS,normalized
from django.utils import timezone
from datetime import timedelta
from uuid import uuid4
call_command('seed_demo',verbosity=0)
candidate=User.objects.get(username='fixture-junior-01@demo.invalid')
employer=User.objects.get(username='fixture-company-alpha@demo.invalid')
company=Company.objects.get(user=employer)
need=Need.objects.filter(company=company,grade='Junior').first()
invitation=invite(company,need.pk,candidate.profile.pk)
decide(candidate.profile,invitation.pk,'accepted')
skill=next(value for value in SKILLS if value.casefold() in normalized(need.skills))
challenge=GapChallenge.objects.filter(invitation=invitation,skill=skill).first()
if challenge is None:
    challenge=challenges.send(employer,invitation.pk,request_id=uuid4(),skill=skill,title='Проверка навыка',
        instructions='MCLI_TASK_PRIVATE',criteria=['Решение','Обоснование'],pass_points=3,duration_minutes=15,
        deadline_at=timezone.now()+timedelta(days=7))[0]
if challenge.state=='offered':challenge=challenges.action(candidate,challenge.pk,'accept',revision=challenge.revision,acknowledge=True)[0]
if challenge.state=='accepted':challenge=challenges.action(candidate,challenge.pk,'submit',revision=challenge.revision,answer='MCLI_ANSWER_PRIVATE',acknowledge=True)[0]
if challenge.state=='submitted':challenge=challenges.review(employer,challenge.pk,revision=challenge.revision,scores=[2,2],note='MCLI_REVIEW_PRIVATE',acknowledge=True,credit=True)[0]
items={}
for role,user in [('candidate',candidate),('employer',employer)]:
    items[role]={'candidate_id':candidate.profile.pk,'need_id':need.pk,'invitation_id':invitation.pk,'challenge_id':challenge.pk,
        'result_id':candidate.profile.attempt_set.filter(status='finished').first().pk}
    for kind in ['cli','mcp']:
        items[role][kind]=issue_token(user,'QA '+kind,kind,contacts=kind=='cli',drafts=True)[1]
path=Path(sys.argv[1]);path.write_text(json.dumps(items));path.chmod(0o600)
print('Synthetic fixture: ready')
