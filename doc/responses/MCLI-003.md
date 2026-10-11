# MCLI-003 — подключение аккаунта

Токены random 256 bit, SHA-256, 30 дней; owner/kind/scopes/revoke/last use;
60 запросов/минуту на токен в атомарной SQLite транзакции. Browser CSRF для выдачи/отзыва.
MCP нельзя выдать contacts.read. API проверяет живые user/role/consent на каждом запросе.
Проверка: 4 новых теста — PASS, включая CSRF, чужой revoke, одноразовый показ,
expiry/revoke/role/consent/rate; docs и diff — PASS. Миграция accounts 0003.
