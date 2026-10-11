# CLI и локальный MCP

Нужны Python 3.13 и uv, macOS Keychain либо Linux Secret Service/KWallet.
Установка из исходников: `uv tool install ./clients/python`.
Установка релиза: `uv tool install /path/fsp_client-0.1.0-py3-none-any.whl`.
CLI не зависит от Django; зависимости закреплены clients/python/uv.lock.

## Соискатель

1. Зарегистрируйте синтетический candidate аккаунт через web и подтвердите demo email.
2. /accounts/integrations/: создайте CLI токен; contacts.read включите только если нужны private/PDF с контактами.
3. `fsp auth login --connection demo-cli --server https://CURRENT-HOST` — скрытый ввод.
4. `fsp --connection demo-cli profile show --json`; `assessments list`, `assessments result ID`,
   `achievements show`, `invitations list`, `invitations show ID`.
5. Private: `profile private`, `invitations contacts ID`; PDF: `profile resume --output resume.pdf --with-contacts`.
6. Создайте отдельный MCP токен без contacts.read и подключение demo-ai тем же auth login.

## Работодатель

1. Отдельный employer аккаунт; через web заполните компанию и потребность.
2. Аналогично создайте CLI и отдельный MCP токены.
3. `fsp --connection demo-cli company show`; `needs list`, `needs show ID`.
4. `candidates search --need-id ID --json`, `candidates show ID --need-id NEED`, `candidates proofs ID`.
5. `candidates private ID` только после accepted своей компании и с contacts.read;
   `candidates resume ID --output resume.pdf` по умолчанию без контактов.
6. `invitations list/show/contacts` поддерживают соответствующую роль.

## Подключение AI

Настройте локальный MCP-процесс: executable `fsp`, args `--connection demo-ai mcp serve`.
Токен в настройку ассистента не вставлять: он читается из keyring.
CLI токен мост отклоняет. stdout только протокол, stderr диагностика.
Пример кандидата: «Сравни мои предложения по оплате и формату работы».
Пример работодателя: «Найди Junior для потребности 3, объясни совпадения и неизвестное».
Достижения ФСП синтетические, навыки/опыт — самоописание, short test без прокторинга.
Внешний ассистент интерпретирует данные; внутренний помощник приложения остаётся моковым.

## Секреты и ошибки

`auth status` проверяет доступ, `auth logout` удаляет локальный секрет. Серверный revoke — в web.
Config ~/.config/fsp/connections.json (или FSP_CONFIG_DIR) содержит только URL и secret reference;
секреты в системном keyring, без fallback файла. При смене адреса повторите auth login;
redirect никогда не пересылает токен. HTTP только localhost, остальное HTTPS с проверкой TLS.
JSON: --json; exit 0 success, 2 parameters, 3 auth/permissions, 4 object/state, 5 network/server.
Linux без активного secure storage возвращает понятную ошибку, а не сохраняет токен открыто.
PDF не перезаписывает существующий файл.

## Разработка и откат

Backend: uv sync --locked, migrate, collectstatic, тесты api и остальных модулей.
Client: `uv sync --locked --project clients/python`; unittest discover -s clients/python/tests.
Build: `uv build --project clients/python --out-dir .runtime/client-dist`.
Откат: предыдущий release приложения/пакета; добавленные token/draft таблицы не удалять.
Исторические gates не означают проверки этого релиза; результаты в отдельном MCLI evidence.
