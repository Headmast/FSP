# Источники требований

Исходный рабочий контекст находится вне Git репозитория в родительской папке FSP: Task/ФСП спец. трек ТЗ.pdf, Task/Ответы на вопросы трек ФСП ЛЦТ__.xlsx, Task/qa-summary-fsp-2026.md и Docs/competitor-analysis-2026-10-11.md. Эти файлы не выдаются за доступные в чистом clone; переносить их отдельно после проверки содержимого и необходимости.

Для сверки сохранены [исходный план из основного чата](original-mvp-plan.md), [свод ТЗ и письменных уточнений](requirements-map.md) и [реестр обсуждений](discussion-map.md). Исходные PDF/XLSX остаются вне clone; свод сохраняет ссылки на страницы/ячейки и различает требования, ограничения и гипотезы.

Текущая карта реализации — [критерии приёмки](../requirements/acceptance.md), [цель](../goal.md), [правила системы](../architecture/system.md) и [оставшиеся работы](../plan/remaining-work.md). При аудите выяснилось, что прежние R01–R11 покрывали сокращённый демо-состав, а не весь исходный план.

## Технические справочники

- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Django SQLite notes](https://docs.djangoproject.com/en/5.2/ref/databases/#sqlite-notes)
- [Git worktree](https://git-scm.com/docs/git-worktree)
- [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
- [Yandex модели](https://aistudio.yandex.ru/ru/docs/ai-studio/concepts/generation/models)
- [Yandex completion API](https://aistudio.yandex.ru/ru/docs/ai-studio/text-generation/api-ref/TextGeneration/completion)

Не переносить доступы из связанных чатов в sources, prompts или responses.

- [localhost.run HTTP и HTTPS туннели](https://localhost.run/docs/cli/)
- [Ограничения временных адресов localhost.run](https://localhost.run/docs/forever-free/)
