# MCLI-009 — черновики действий

Immutable UUID draft, owner/kind/target/payload/fingerprint/source/24h/state.
Prepare/read/list/cancel API; отдельно выданный draft scope, без API apply.
Form/model validation и owned IDs при подготовке. MCP не получает private payload;
CLI без contacts.read не получает контакты из черновика другого своего подключения.
Проверка: 11 API тестов — PASS (39.513 s), включая prepare без записи business objects,
immutability, scope, чужой draft/target, private redaction и отмену. api 0001 migration.
