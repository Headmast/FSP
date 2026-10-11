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
from hiring.models import Need,Company
from hiring.services import invite
call_command('seed_demo',verbosity=0)
candidate=User.objects.get(username='fixture-junior-01@demo.invalid')
employer=User.objects.get(username='fixture-company-alpha@demo.invalid')
company=Company.objects.get(user=employer)
need=Need.objects.filter(company=company,grade='Junior').first()
invitation=invite(company,need.pk,candidate.profile.pk)
items={}
for role,user in [('candidate',candidate),('employer',employer)]:
    items[role]={'candidate_id':candidate.profile.pk,'need_id':need.pk,'invitation_id':invitation.pk,
        'result_id':candidate.profile.attempt_set.filter(status='finished').first().pk}
    for kind in ['cli','mcp']:
        items[role][kind]=issue_token(user,'QA '+kind,kind,contacts=kind=='cli')[1]
path=Path(sys.argv[1]);path.write_text(json.dumps(items));path.chmod(0o600)
print('Synthetic fixture: ready')
