# Воспроизведение некорректных ID

DOC-002, 2026-10-11, исходники `02cedf8e175bab87aac7144e3154b3ca3e979b23`. Ожидание: некорректное значение не даёт 500; [наблюдение](scope-audit-id.json): `²` даёт 500 в двух маршрутах. Другие проверенные значения 500 не дали.

Запускать в собственном worktree после установки зависимостей. Команда создаёт только временную SQLite, выполняет миграции/синтетический логин в ней и удаляет её после проверки. Production и рабочие базы не используются. Статика для этого изолированного HTTP опыта переведена на StaticFilesStorage; проверяется обработка ID, а не production static manifest.

```sh
uv run python - <<'PY'
import json, os, sys, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(prefix='fsp-audit-http-') as temporary:
    os.environ['DATABASE_PATH'] = str(Path(temporary) / 'audit.sqlite3')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    os.environ['DEBUG'] = '1'
    sys.path.insert(0, str(Path.cwd() / 'app'))
    import django
    django.setup()
    from django.core.management import call_command
    from django.test import Client, override_settings
    from django.db import connections
    from django.core.signals import got_request_exception
    from accounts.models import User
    from hiring.models import Company, Need
    call_command('migrate', verbosity=0)
    user = User.objects.create_user(username='audit-company@demo.invalid',
        password='synthetic', role='employer', email_confirmed=True)
    company = Company.objects.create(user=user, name='Аудит Демо')
    need = Need.objects.create(company=company, title='iOS', grade='Junior',
        skills='Swift', tasks='Демонстрация', salary_min=100, salary_max=200,
        work_format='remote')
    exceptions = []
    def record_exception(sender, request, **kwargs):
        error = sys.exc_info()[1]
        exceptions.append({'type':type(error).__name__, 'message':str(error)})
    got_request_exception.connect(record_exception)
    client = Client(raise_request_exception=False)
    client.force_login(user)
    results = []
    storage = {'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
        'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}
    with override_settings(DEBUG=False, SECURE_SSL_REDIRECT=False,
            ALLOWED_HOSTS=['testserver'], STORAGES=storage):
        for value in ['²', '9'*198, 'abc', '-1']:
            start = len(exceptions)
            response = client.get('/candidates/', {'need':value, 'grade':'Junior'})
            results.append({'route':'GET /candidates/', 'value':value[:32],
                'length':len(value), 'status':response.status_code,
                'exceptions':exceptions[start:]})
            start = len(exceptions)
            response = client.post('/assistant/', {'mode':'need', 'identifier':value})
            results.append({'route':'POST /assistant/', 'value':value[:32],
                'length':len(value), 'status':response.status_code,
                'exceptions':exceptions[start:]})
        response = client.post('/assistant/', {'mode':'need', 'identifier':str(need.pk)})
        results.append({'route':'POST /assistant/', 'value':'own valid ID',
            'status':response.status_code})
    print(json.dumps({'isolation':'Temporary SQLite only', 'results':results},
        ensure_ascii=False, indent=2))
    connections.close_all()
PY
```

При фактическом аудите использован Python существующего окружения репозитория вместо создания второго окружения. Модуль приложения импортирован из нового worktree. После исправления FIX-001 сохранённое FAIL остаётся историческим; новый результат записывается отдельным evidence с новым SHA.
