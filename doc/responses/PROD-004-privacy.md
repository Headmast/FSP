# PROD-004 · Серверный этап, задача продолжается

Реализованы четыре собственных действия: отзыв у одной/всех компаний, очистка профиля с сохранением входа и удаление аккаунта. Исправлен API путь invitation contacts, обходивший общий grant. Добавлены redaction/nullable архив, чистка связанных проверок/черновиков/токенов, инвалидирование сессий, readonly privacy API/CLI/MCP и защитный журнал восстановления.

[Архитектура и точные правила](../architecture/privacy-controls.md). Политика 180 дней для сокращённой истории, 7 дней для backup, максимум 30 дней для экзаменационных ограничений реализована maintenance; floor не допускает старый код без enforcement. Отдельная проверка фактической SQLite restore/retention прошла.

182 серверных теста (20 новых), 13 клиентских и 23 инструментальных; 602 HTTP случая, 71 path / 114 operations, 118 примеров и четыре контрпроверки — PASS. Реальные HTTP/native CLI/modern+legacy MCP и четыре фактические SQLite restore/retention проверки — PASS. [Evidence этапа](../qa/PROD-004-stage.json), [HTTP](../qa/PROD-004-http-stage.json), [restore](../qa/PROD-004-restore-stage.json). Для DONE ещё нужны clean clone/browser обеих ролей, визуальная приёмка destructive flow, интеграция/публикация и live checkpoint на собственных синтетических аккаунтах. Пока **16/27 DONE, 11 открыты**, PROD-004 IN_PROGRESS. Реальные данные VPS не удалялись.
