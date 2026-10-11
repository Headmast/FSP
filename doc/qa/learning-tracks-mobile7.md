# MOBILE7-002 · Android, Flutter и Аврора

Проверено 11.10.2026 в изолированном checkout mobile7, порт 8057, база этой ветки. Базовый коммит расширения: 9e2c7cc. Проверенные исходники перечислены с SHA-256 в [сводном evidence](MOBILE7-002-results.json); Коммит кода: 0733d0165112e8b0dc7a54902b6261e150a82862. Все отпечатки сверены с его содержимым. Новых зависимостей нет; среда uv.lock: Python 3.13, Django 5.2.18.

## Результаты

| Проверка | Фактический результат |
|---|---|
| Полный набор accounts/profiles/assessments/hiring/assistant | PASS · 102 теста, включая 11 новых проверок треков и 21 прежнюю проверку обучения |
| После уточнения ссылок экзамена: повтор assessments | PASS · 47 тестов; повтор браузера треков и iOS — PASS |
| Django check | PASS · ошибок нет |
| makemigrations --check --dry-run | PASS · No changes detected |
| Переход с assessments/0003 на 0004 на непустой временной SQLite | PASS · снимки, ответы, версии, даты, активная попытка, завершённый результат и отметка iOS сохранены; старый сеанс продолжается и завершается |
| Применение 0004 в локальной базе ветки и collectstatic | PASS |
| Конкурентные записи SQLite, четыре потока | PASS · одна активная попытка на трек, нет потери ответов, идемпотентное завершение, отдельные уроки и баллы четырёх треков |
| Chromium, scripts/check_learning_tracks.cjs, JavaScript выключен | PASS · выбор трека, 24 урока обоих уровней, три одновременные практики, пауза/возврат, сохранённый выбор, разбор, повтор ошибок, Middle по 8 вопросов, история и повторный вход |
| Регрессия прежнего iOS сценария scripts/check_learning.cjs | PASS · включая экзаменационную блокировку, продолжение после экзамена, сохранение категории |
| Адаптивность 320/390/768/1280 px | PASS · маршрут, все новые уроки, активный вопрос и результат без горизонтального выхода страницы |
| Визуальный просмотр Android/Flutter маршрутов и результата Авроры | PASS · формы, текст, карточки, разбор и подпись платформы читаемы |
| scripts/worktree.py check | PASS · собственные база и порт |
| scripts/check_docs.py и git diff --check | PASS |

Новые серверные проверки покрывают 128 уникальных независимых вопросов, баланс по треку/уровню/теме, оба уровня и все темы, отдельные активные сеансы, прогресс уровней/версий, историю/рекомендации, сохранение выбранного трека, совместимость старых iOS URL и POST, переход подготовки к экзамену iOS после выбора другой платформы, повтор по исходному треку при подмене track/grade, невалидные треки и чужие темы, права чужих попыток, CSRF, запрет GET для записей, подтверждение изучения и блокировку всех треков действующим экзаменом. Учебный результат не меняет категорию профиля; Android/Flutter/Аврора не предлагаются как квалификационный экзамен.

## Evidence и снимки

- [Новые треки в браузере](MOBILE7-002-browser.json), [регрессия iOS](MOBILE7-002-ios-browser.json).
- [Миграция старых данных](MOBILE7-002-migration.json), [конкурентность](MOBILE7-002-concurrency.json), [сводка и отпечатки](MOBILE7-002-results.json).
- Android: [маршрут 320 px](MOBILE7-002-android-mobile.png), [разбор](MOBILE7-002-android-result.png).
- Flutter: [маршрут 320 px](MOBILE7-002-flutter-mobile.png), [разбор](MOBILE7-002-flutter-result.png).
- Аврора: [маршрут 320 px](MOBILE7-002-aurora-mobile.png), [разбор](MOBILE7-002-aurora-result.png).

## Воспроизведение

Из checkout mobile7: uv sync --locked; uv run python app/manage.py migrate; uv run python app/manage.py collectstatic --noinput; uv run python scripts/run_app.py. Проверка полного набора: uv run python app/manage.py test accounts profiles assessments hiring assistant --verbosity 1. Нужны явные labels: запуск manage.py test из корня без них не находит тесты под app/ и не подтверждает PASS.

Миграция: uv run python scripts/check_learning_migration.py. Конкурентность: uv run python scripts/check_learning_concurrency.py. Эти скрипты создают отдельную временную SQLite и удаляют её после проверки.

Браузер: NODE_PATH=<bundled node_modules> <bundled node> scripts/check_learning_tracks.cjs http://127.0.0.1:8057; регрессия — тот же запуск для scripts/check_learning.cjs. Скрипты допускают только localhost, создают собственные синтетические аккаунты @demo.invalid и сохраняют evidence в .runtime/qa. Сохранённые doc/qa материалы относятся к этой приёмке.

## Границы проверки

Разработан веб-модуль обучения в отдельной ветке. Интеграция в main, публикация, JSON API для native клиента, компиляция учебных фрагментов через Android/Flutter/Аврора SDK и аудит VoiceOver не выполнялись. Подтверждение категории других платформ требует отдельного банка экзамена и модели квалификаций; текущий экзамен iOS не расширялся. Предыдущая приёмка MOBILE7-001 остаётся историческим результатом своего SHA.

[Архитектура](../architecture/learning-mobile7.md), [HTTP](../api/learning-mobile7.md), [поручение](../prompts/MOBILE7-002-tracks.md), [результат](../responses/MOBILE7-002-tracks.md).
