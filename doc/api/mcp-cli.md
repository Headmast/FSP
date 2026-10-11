# HTTP API для CLI и MCP

[OpenAPI 3.1](mcp-cli.openapi.json) — поля, роли, pagination, errors. База /api/v1 без trailing slash.
GET /openapi.json возвращает ту же спецификацию после Bearer auth; HTML routes остаются в [contracts](contracts.md).
JSON успех: data/meta, списки также pagination; ошибки error.code/message/meta.request_id.
meta: api_version=1, data_mode=demo. IDs 1..2^63-1, limit 1..100 (20), offset 0..2^31-1.
Даты timezone ISO 8601, зарплата RUB/gross/month. Search grade обязателен без need_id,
при need_id выводится из потребности; конфликт отклоняется. Сортировка существующего hiring.search.

Контакты/private/PDF только CLI; contacts.read дополнительно для private и PDF with_contacts=true.
Accepted grant принадлежит компании; снятие публикации не отзывает прошлый accepted grant.
MCP whitelist без description/tasks/discussion/next_step/external_id, safe labels вместо неподходящих имён.
Публичное свидетельство содержит только агрегаты: ни активных, ни завершённых questions/answers/keys.
GET не создаёт компанию, не меняет viewed_at и не завершает попытку. Попытка active: result=409 RESULT_NOT_READY.
Rate: 60/min/token, 429 Retry-After: 60; токены expired/revoked 401, scope/role/consent 403.
Лог: request ID/token ID/function/status/duration без query values, payload и секретов.
