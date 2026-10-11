# Локальный запуск Django MVP

Нужны Git, Python 3.13 и uv. Версии библиотек фиксируются uv.lock. Прототип запускается отдельно, см. [P0](../qa/prototype-results.md).

```sh
uv sync --locked
uv run python app/manage.py migrate
uv run python app/manage.py collectstatic --noinput
uv run python scripts/run_app.py
```

В основном checkout адрес http://127.0.0.1:8011. Worktree конфигурация задаёт собственный APP_PORT и DATABASE_PATH; settings читает .env.worktree автоматически. Для дополнительных настроек скопировать .env.example в .env. Переменные процесса имеют высший приоритет; локальный .env.worktree перекрывает файловые значения .env и FSP_ENV_FILE.

При DEBUG=0 обязательно задать DJANGO_SECRET_KEY, точные ALLOWED_HOSTS и CSRF_TRUSTED_ORIGINS. Секреты не включать в Git. Внешний HTTPS и прокси настраиваются при публикации; локальный DEBUG=1 предназначен для разработки.

## Аккаунты

Открыть регистрацию, выбрать роль и уникальный адрес @demo.invalid. Demo письмо показывается только создавшему его браузеру. Подтверждение одноразовое, срок 30 минут. Затем можно войти с этим адресом и паролем. Реальная почта не отправляется.

Профиль кандидата поддерживает фиксированный словарь навыков и отдельные скрытые контакты. Имя и город допускают буквы, пробелы и дефис; вставка email или номера в эти публичные поля отклоняется. Собственное резюме PDF содержит контакты и встроенный открытый шрифт DejaVu с кириллицей.

## Проверки

Перед тестами выполнить collectstatic: серверные шаблоны используют manifest статики, в том числе при тестовом DEBUG=False.

```sh
uv run python app/manage.py check
uv run python app/manage.py makemigrations --check --dry-run
uv run python app/manage.py test accounts profiles
python3 scripts/check_docs.py
```

scripts/check_accounts.cjs проверяет реальный браузерный путь и PDF; требует Playwright и запущенное приложение. В demo базе появляются новые синтетические аккаунты. Результаты и снимки сохраняются в исключённом из Git .runtime/qa.

Прочие модули добавляются следующими этапами. Наличие ссылок в общей навигации пока не означает завершение тестирования и найма.
