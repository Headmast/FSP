# MCLI-011 — Черновики соискателя в клиенте

CLI поддерживает profile draft/publish/unpublish, invitations accept/decline и drafts list/show/cancel/open/prepare. Параметры из JSON отправляются только в подготовку; применение выполняется в браузере. MCP инструменты появляются при отдельно выданном candidate.draft, имеют схемы и не принимают контакты. HTTP диагностические логи подавлены в мосте.

Проверки: 7 клиентских unittest PASS, включая официальный SDK, запрет контактных полей и отсутствие инструмента применения; check_docs PASS; diff --check PASS. Сквозное подтверждение включено в MCLI-013.
