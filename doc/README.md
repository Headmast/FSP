# Документация MVP обратного найма

Прототип на моках и Django MVP опубликованы: профиль, тест, категория, предложение и контакты после согласия. [Постоянный вход LLM Love](https://llmlove.ru/dreamwork/fsp-demo.html); опубликованный выпуск PROD-004 — `11399cc`.

Весь обсуждённый MVP ещё не завершён. Начните с [списка оставшихся работ](plan/remaining-work.md) и [актуальной сверки DOC-010](plan/implementation-gaps-2026-10-12.md): там отделены пропуски исходного плана, разрешённые моки и развитие.

## Материалы проекта

[Информационный бот Telegram/MAX на моках](../bots/README.md), [результат и проверки BOT-001](responses/BOT-001.md).

[Корневое оглавление](../README.md) объединяет документацию, презентацию, демо, прототип и дополнительные материалы.

- [Все видео проекта](../video/README.md), [запись прототипа](../video/6.mp4), [галерея](../video/index.html).
- [Презентация PPTX](presentation/trudyazhki-fsp.pptx), [HTML](presentation/trudyazhki-fsp.html), [текст выступления](presentation/trudyazhki-fsp.md).
- [Исходное ТЗ и уточнения](sources/README.md).
- [Исследование конкурентов](research/competitor-analysis-2026-10-11.md).

## Начать работу

1. Прочитать [цель](goal.md), [план реализации](plan/implementation.md) и [задачи](plan/backlog.md).
2. Перед новой функцией прочитать [правила параллельной работы](development/worktrees.md).
3. Реализовать задачу вместе с документацией и пройти применимые [quality gates](qa/quality-gates.md).
4. Сохранить результаты проверки и сделать коммит завершённого этапа.

## Разделы

- [Требования и приёмка](requirements/acceptance.md)
- [Архитектура и правила системы](architecture/system.md)
- [Технические решения](decisions/README.md)
- [Прототип и демонстрация](prototype/specification.md)
- [HTTP интерфейсы](api/contracts.md)
- [Проверки и сценарии](qa/test-plan.md)
- [Статусы проверок](qa/gates.json)
- [Результаты подготовки документации и worktree](qa/preparation-results.md)
- [Результаты аккаунтов и профиля](qa/accounts-results.md)
- [Результаты оценивания](qa/assessment-results.md)
- [Учебный модуль mobile7](architecture/learning-mobile7.md): уроки, самопроверка, повтор ошибок; [QA](qa/learning-mobile7.md)
- [Cron и постоянная страница демо](deployment/watchdog.md), [результаты](qa/watchdog-results.md)
- [Публикация и откат](deployment/runbook.md)
- [Отчёт о выпуске](delivery/mvp-release.md)
- [Рабочие промпты](prompts/README.md) и [ответы](responses/README.md)
- [Источники требований](sources/README.md)

Прототип опубликован: [результаты P0](qa/prototype-results.md). Технический Django сценарий проверен: [исторические проверки выпуска](qa/release-results.md). [Локальный запуск](development/local-run.md). PASS в документации означает только конкретную выполненную проверку, а не готовность всей системы или полного исходного плана.

## Работа HR

[Дашборд владельца OWNER-001](responses/OWNER-001.md): показатели приглашений, назначения HR, фильтры, методика и границы. [Проверки и снимки](qa/owner-dashboard.md).


[Что ещё реализовать — актуальная сверка 12 октября](plan/implementation-gaps-2026-10-12.md): 9 открытых задач исходной цели, пять дополнительных поручений/приёмок, приоритеты и проверки завершения.


[Полный HTTP/OpenAPI контракт DOC-003](responses/DOC-003-contracts.md) закрыт на своём SHA: 69 маршрутов/111 операций. PROD-004 обновила схему до 71/114 и прошла server/browser/live приёмку.


[Актуальный комплект сдачи DEL-001](delivery/README.md): руководство PDF, PPTX/HTML/PDF, карта требований, реальные записи и manifest. [Открыть публично](https://llmlove.ru/dreamwork/doc/delivery/index.html). Текущий прогресс: 18/27 DONE, 9 открыты; следующая PROD-003.

PROD-001 опубликована: [условия кандидата и сравнение до контакта](architecture/conditions.md), [проверки и результат](responses/PROD-001-conditions.md). Прежний комплект DEL-001 сохраняет явный SHA своего проверенного снимка; итоговый сводный экспорт обновляется перед полной сдачей.

[Повторная проверка DOC-010](qa/.project-brief/runs/2026-10-12-DOC-010.md): код, main и опубликованный выпуск сопоставлены отдельно; открытые задачи не повышены до DONE.

[PROD-004 завершена](responses/PROD-004-privacy.md): отзыв доступа, очистка/удаление и защита при восстановлении. [Правила](architecture/privacy-controls.md), [приёмка](qa/PROD-004-complete.json).

[Историческая проверка полноты DOC-011](responses/DOC-011-completeness.md): 17/27 DONE, 10 открыты; PROD-002 прошла browser33 и интеграцию, публикация ещё не принята.

PROD-002 завершена: [адресное задание](architecture/gap-challenges.md), [приёмка](qa/PROD-002-complete.json), [результат](responses/PROD-002-challenges.md). 18/27 DONE, 9 открыты; browser33/live29, cron/floor2 приняты.
