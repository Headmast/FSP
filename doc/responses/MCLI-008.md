# MCLI-008 — V1

98 Django тестов — PASS (14.627 s); после дополнительного error boundary/audit изменения
8 API тестов — PASS (2.016 s). OpenAPI 3.1 official validator — PASS.
HTTP сквозной путь: кандидат 9, работодатель 10 маршрутов; ответы проверены JSON Schema.
Реальный stdio subprocess official Client — обе роли в auto и legacy, PASS.
macOS native keyring + packaged CLI — обе роли PASS. Linux x86_64 Python 3.13.5:
6 клиентских тестов PASS (0.285 s), wheel/sdist PASS, native SecretService round trip PASS
в изолированной dbus/gnome-keyring сессии; пакеты извлечены в QA каталог, system install не выполнялась.

Клиент 0.1.0 и manifest SHA-256 собираются scripts/build_client_release.py, доступны через /downloads/.
Две ролевые инструкции: [запуск](../development/mcp-cli.md), [контракты](../api/mcp-cli.md).
Production публикация и SHA фиксируются отдельным проверенным checkpoint, не заменяются локальным PASS.
