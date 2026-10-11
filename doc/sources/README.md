# Источники требований

В репозиторий добавлены исходные материалы для просмотра из чистого clone:

- [Техническое задание ФСП, PDF](materials/fsp-specification.pdf).
- [Письменные ответы постановщиков, XLSX](materials/fsp-written-answers.xlsx).
- [Конспект устного Q&A](materials/qa-summary-fsp-2026.md) — вторичный источник.
- [Исследование конкурентов](../research/competitor-analysis-2026-10-11.md) и [HTML-версия](../research/competitor-analysis-2026-10-11.html).
- [Презентация, текст и заметки](../../README.md#презентация).

Для сверки сохранены [исходный план](original-mvp-plan.md), [свод ТЗ и письменных уточнений](requirements-map.md) и [реестр обсуждений](discussion-map.md). Свод различает требования, ограничения и гипотезы; PDF/XLSX доступны по ссылкам выше. Личные голосовые сообщения и рабочие расшифровки остаются вне Git; реестр обсуждений передаёт необходимый контекст.

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

## Видео проекта

[Запись мокового прототипа, 1:10](../../video/6.mp4) и [каталог всех шести видео](../../video/README.md). Ролики 1–5 иллюстрируют концепцию. Видео может отличаться от текущего сайта по интерфейсу и составу функций.
