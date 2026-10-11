#!/usr/bin/env python3
"""Generate the reviewed browser HTTP contract; --check fails on stale outputs."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from http_contracts import ENDPOINTS, build_spec

INTRO = '''# HTTP контракты FSP MVP

Проверенный первый срез DOC-003: b82b455 + source hashes этапа. Задача IN_PROGRESS: новые learning/token V2/UUID approvals более позднего main ещё требуют включения. [Статус и границы](../responses/DOC-003-contracts.md).

Все маршруты текущего Django-приложения описаны в [OpenAPI 3.1.1](openapi.json). Здесь закреплены поля, роли, ответы, повторы и границы моков. HTML формы используют session/CSRF; три прежних JSON маршрута чтения и PDF — те же browser permissions. Интегрированный JSON API /api/v1 использует Bearer: [его отдельный контракт](mcp-cli.md). Схемы API включены в общую спецификацию с префиксом Api, не смешивающим их с формами.

## Авторизация, сериализация и ошибки

- Cookie sessionid задаёт пользователя. candidate/employer/both требуют подтверждённый email и processing-v1. Неверная роль/email — 403; без сессии — 302 на login с next; без обработки — 302 consent после проверки роли/email. authenticated у consent требует только входа. pending-session у confirm — исходная сессия регистрации, ещё без входа.
- Любой POST, включая register/login/confirm/logout, требует csrftoken cookie плюс csrfmiddlewaretoken из формы **или** X-CSRFToken. После входа сессия/CSRF обновляются. Отсутствие/несовпадение — 403 ещё до вызова view. GET не вызывает эту проверку.
- Поддерживаемые тела: application/x-www-form-urlencoded и multipart/form-data без загрузки файлов. JSON не разбирается в request.POST: поля игнорируются, итог зависит от формы/значений по умолчанию; 415 не обещается. Для изменений используйте формы. Приватные поля не передавать в URL.
- Массивы — повтор одного имени: roles=developer&roles=reviewer и accepted_attempts=1&accepted_attempts=2. Суффикс [] не входит в имя поля. Checkbox принимает on/true, false выключает; отсутствие необязательного флажка означает false. Необязательные числовые поля могут быть пустыми в HTML; описание задаёт нормализацию.
- pk — положительный ID до 2^63−1. Query/form ID — 1..19 ASCII цифр в тех же границах, ведущие нули допустимы. Пробелы, Unicode цифры, отрицательное/слишком длинное значение или недоступный объект — 404. Пустой обязательный — 404; необязательный выбирает описанный default. Путь, не совпавший с URL converter, даёт 404 маршрутизатора.
- Обычные ошибки форм возвращают HTML 200. Для помощника/черновика 400/409/410/429/503 определены отдельно. Конфликты тестов и решения приглашения возвращают 302 с Django message. 302 содержит Location; клиент должен следовать ему и читать сообщение, а не считать каждый redirect успехом записи.
- Страницы чтения допускают GET/HEAD; HEAD возвращает заголовки без тела. Формы с явным GET/POST не принимают HEAD. Login также допускает HEAD/OPTIONS, logout POST/OPTIONS. Остальные методы — 405 с Allow для пользователя, прошедшего внешние guard; auth/CSRF middleware может отвергнуть запрос раньше. Разрешённые методы перечислены ниже и проверяются по коду.
- Неизвестные обычные поля формы игнорируются; q_* проверяются по snapshot попытки, а experience-* — по formset. Параметры owner/score/confirmed_grade из браузера не выбирают владельца или результат. Нет обещания произвольного 500 в спецификации: такой ответ блокирует проверку.

GET/HEAD invitations фиксирует viewed_at; некоторые страницы работодателя создают собственную Company при первом чтении. Это явные побочные эффекты существующего веб-интерфейса. Нельзя переиспользовать их как обещание чистого чтения нового MCP API.

## Как получить воспроизводимый пример

Из собственного worktree: `uv sync --locked`, `uv run python scripts/build_client_release.py`, затем `uv run python scripts/build_http_spec.py --check` и `uv run python scripts/check_http_contracts.py --output .runtime/qa/http-contracts.json`. Проверка сама создаёт временную SQLite и синтетические аккаунты, выполняет примеры с реальными cookie/CSRF/Bearer и удаляет БД; production не используется. Архивы CLI читаются из собственных .runtime/downloads. [Подробные примеры](examples.md).

OpenAPI request examples показывают допустимую форму тела. ID=1 и токен-заглушку нужно заменить объектом и CSRF своей сессии; это не действующие доступы. JSON response examples синтетические. Источник семантики и генератор — scripts/http_contracts.py и scripts/build_http_spec.py; менять их вместе с кодом. --check сравнивает оба сохранённых результата, а checker отдельно сверяет методы и выполняет HTTP.

## Маршруты
'''


def type_text(schema):
    if '$ref' in schema:
        return schema['$ref'].rsplit('/', 1)[-1]
    if 'anyOf' in schema:
        return ' / '.join(type_text(s) for s in schema['anyOf'])
    if 'const' in schema:
        return repr(schema['const'])
    kind = schema.get('type', 'object')
    if kind == 'array':
        kind = 'array[' + type_text(schema['items']) + ']'
    constraints = [f'{k}={schema[k]}' for k in ['minimum','maximum','minLength','maxLength','maxItems'] if k in schema]
    if 'enum' in schema:constraints.append('enum=' + ', '.join(str(v) or '(empty)' for v in schema['enum']))
    return str(kind) + ('; ' + '; '.join(constraints) if constraints else '')


def markdown(spec):
    out = [INTRO]
    for name, entry in ENDPOINTS.items():
        out += [f"### {entry['path']} — {entry['summary']}\n", f"Методы: **{' / '.join(entry['methods'])}**. Роль: **{entry['role']}**.\n",
            entry['detail'] + '\n', 'Повтор: ' + (entry['repeat'] or 'Чтение текущего состояния.') + '\n']
        if entry['effects']:out += ['Побочные эффекты чтения: ' + entry['effects'] + '\n']
        if entry['query']:
            out += ['Query (все необязательные):\n', '| Поле | Тип / границы | Правила |','| --- | --- | --- |']
            out += [f"| {key} | {type_text(schema)} | {schema.get('description','См. поведение маршрута.')} |" for key,schema in entry['query'].items()]
            out += ['']
        if entry['body']:
            out += [f"POST schema: **{entry['body']}**; поля см. ниже.\n"]
        out += ['| Метод | Статус | Значение |','| --- | --- | --- |']
        for method,op in spec['paths'][entry['path']].items():
            out += [f"| {method.upper()} | {status} | {response['description']} |" for status,response in op['responses'].items()]
        out += ['']
    out += ['## Token API /api/v1\n','API не использует browser session и CSRF. Каждая операция требует активный Bearer token своей роли/скоупа, подтверждённый аккаунт и processing consent. 60 запросов/минуту, срок 30 дней; revoke/expiry → 401, scope/role/consent → 403. Данные/ошибки JSON без HTML redirect. Cache-Control=no-store, X-Request-ID; 429 также Retry-After=60, 401 WWW-Authenticate=Bearer. На GET меняется только учёт использования токена, бизнес-данные не меняются. MCP не получает контакты/свободные приватные тексты/PDF; CLI private требует contacts.read и действующий grant. Все DTO приведены в схемах Api ниже.\n']
    for path,operations in spec['paths'].items():
        if not path.startswith('/api/v1'):continue
        op=operations['get'];out += [f'### GET {path}\n',op['description']+'\n']
        if op.get('parameters'):
            out += ['| Поле | Где | Тип / границы |','| --- | --- | --- |']
            out += [f"| {p['name']} | {p['in']} | {type_text(p['schema'])} |" for p in op['parameters']];out += ['']
        out += ['| Статус | Ответ |','| --- | --- |']
        out += [f"| {status} | {response['description']} |" for status,response in op['responses'].items()];out += ['']
    out += ['## Схемы полей\n', 'Числа/boolean ниже — логические типы после сериализации формы; на HTTP проводе URLencoded значения текстовые. Required относится к допустимому успешному POST. Схема не заменяет межполевую и владельческую проверку сервера.\n']
    for name,schema in spec['components']['schemas'].items():
        out += [f'### {name}\n']
        if schema.get('description'):out += [schema['description']+'\n']
        if 'anyOf' in schema:out += ['Варианты: '+', '.join(type_text(s) for s in schema['anyOf'])+'\n']
        if schema.get('properties'):
            out += ['| Поле | Обязательно | Тип / границы | Правила |','| --- | --- | --- | --- |']
            out += [f"| {key} | {'да' if key in schema.get('required',[]) else 'нет'} | {type_text(field)} | {field.get('description','—')} |" for key,field in schema['properties'].items()]
            out += ['']
        if schema.get('patternProperties'):
            out += ['Динамические поля:\n']
            out += [f'- `{pattern}`: {type_text(field)}.' for pattern,field in schema['patternProperties'].items()]
            out += ['']
    out += ['## Источники формата\n', 'Формат закреплён по [OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html); документ проверяет [openapi-spec-validator](https://openapi-spec-validator.readthedocs.io/en/latest/python.html), установленный только в dev группе lock. Production deploy использует --no-dev. Это описание нашего браузерного HTTP, не официального API ФСП.\n']
    return '\n'.join(out)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true');args=parser.parse_args()
    spec=build_spec()
    # Response examples do not include real identities, sessions or deployment keys.
    examples={'HealthOk':{'status':'ok'},'HealthUnavailable':{'status':'unavailable'},
        'Version':{'commit':'0'*40,'assistant_mode':'mock'},
        'FspHistory':{'source':'mock','status':'not_connected','changes_grade':False,'external_id':None,'events':[]}}
    examples['ClientManifest']={'version':'0.1.0','commit':'0'*40,'files':[{'filename':'fsp_client-0.1.0-py3-none-any.whl','bytes':1234,'sha256':'0'*64},{'filename':'fsp_client-0.1.0.tar.gz','bytes':1234,'sha256':'1'*64}]}
    for operations in spec['paths'].values():
        for op in operations.values():
            for response in op['responses'].values():
                media=response.get('content',{}).get('application/json')
                if media and '$ref' in media.get('schema',{}) and media['schema']['$ref'].rsplit('/',1)[-1] in examples:
                    media['examples']={'synthetic':{'value':examples[media['schema']['$ref'].rsplit('/',1)[-1]]}}
    outputs={'doc/api/openapi.json':json.dumps(spec,ensure_ascii=False,indent=2)+'\n','doc/api/contracts.md':markdown(spec)}
    stale=[]
    for name,content in outputs.items():
        path=ROOT/name
        if args.check:
            if not path.exists() or path.read_text()!=content:stale.append(name)
        else:path.write_text(content)
    if stale:
        print('FAIL: stale generated contract: '+', '.join(stale),file=sys.stderr);return 1
    print(('PASS: current' if args.check else 'Generated')+f" contracts, {len(spec['paths'])} paths / {sum(len(v) for v in spec['paths'].values())} operations.")
    return 0


if __name__=='__main__':raise SystemExit(main())
