# Документация MVP обратного найма

Прототип на моках и Django MVP опубликованы: профиль, тест, категория, предложение и контакты после согласия. [Адрес и краткий итог](delivery/mvp-release.md).

Весь обсуждённый MVP ещё не завершён. Начните с [списка оставшихся работ](plan/remaining-work.md) и [повторной проверки DOC-004](qa/scope-recheck.md): там отделены пропуски исходного плана, разрешённые моки и развитие.

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
- [Cron и постоянная страница демо](deployment/watchdog.md), [результаты](qa/watchdog-results.md)
- [Публикация и откат](deployment/runbook.md)
- [Отчёт о выпуске](delivery/mvp-release.md)
- [Рабочие промпты](prompts/README.md) и [ответы](responses/README.md)
- [Источники требований](sources/README.md)

Прототип опубликован: [результаты P0](qa/prototype-results.md). Технический Django сценарий проверен: [исторические проверки выпуска](qa/release-results.md). [Локальный запуск](development/local-run.md). PASS в документации означает только конкретную выполненную проверку, а не готовность всей системы или полного исходного плана.
