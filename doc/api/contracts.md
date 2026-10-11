# HTTP контракты FSP MVP

DOC-003: общий состав браузера, обучения, токенного API V1/V2 и веб-подтверждения UUID черновиков. [Проверки и границы](../responses/DOC-003-contracts.md). [Подробный контракт обучения](learning-mobile7.md).

Все маршруты текущего Django-приложения описаны в [OpenAPI 3.1.1](openapi.json). Здесь закреплены поля, роли, ответы, повторы и границы моков. HTML формы используют session/CSRF; три прежних JSON маршрута чтения и PDF — те же browser permissions. Интегрированный JSON API /api/v1 использует Bearer: [его отдельный контракт](mcp-cli.md). Схемы API включены в общую спецификацию с префиксом Api, не смешивающим их с формами.

## Авторизация, сериализация и ошибки

- Cookie sessionid задаёт пользователя. candidate/employer/both требуют подтверждённый email и processing-v1. Неверная роль/email — 403; без сессии — 302 на login с next; без обработки — 302 consent после проверки роли/email. authenticated у consent требует только входа. pending-session у confirm — исходная сессия регистрации, ещё без входа.
- Любой POST, включая register/login/confirm/logout, требует csrftoken cookie плюс csrfmiddlewaretoken из формы **или** X-CSRFToken. После входа сессия/CSRF обновляются. Отсутствие/несовпадение — 403 ещё до вызова view. GET не вызывает эту проверку.
- Для браузерных изменений поддерживаемые тела: application/x-www-form-urlencoded и multipart/form-data без загрузки файлов. JSON не разбирается в request.POST: поля игнорируются, итог зависит от формы/значений по умолчанию; 415 не обещается. Для browser изменений используйте формы; token V2 POST требует application/json, неверный JSON/media/поля дают JSON 400. Приватные поля не передавать в URL.
- Массивы — повтор одного имени: roles=developer&roles=reviewer и accepted_attempts=1&accepted_attempts=2. Суффикс [] не входит в имя поля. Checkbox принимает on/true, false выключает; отсутствие необязательного флажка означает false. Необязательные числовые поля могут быть пустыми в HTML; описание задаёт нормализацию.
- Веб action-draft pk — UUID; токенные V2 drafts также используют UUID. Остальные pk — положительный ID до 2^63−1. Query/form ID — 1..19 ASCII цифр в тех же границах, ведущие нули допустимы. Пробелы, Unicode цифры, отрицательное/слишком длинное значение или недоступный объект — 404. Пустой обязательный — 404; необязательный выбирает описанный default. Путь, не совпавший с URL converter, даёт 404 маршрутизатора.
- Обычные ошибки форм возвращают HTML 200. Для помощника/черновика 400/409/410/429/503 определены отдельно. Конфликты тестов и решения приглашения возвращают 302 с Django message. 302 содержит Location; клиент должен следовать ему и читать сообщение, а не считать каждый redirect успехом записи.
- Страницы с require_safe допускают GET/HEAD; HEAD возвращает заголовки без тела. Учебные страницы и список V2 drafts допускают только GET (HEAD 405). Формы с явным GET/POST не принимают HEAD. Login также допускает HEAD/OPTIONS, logout POST/OPTIONS. Остальные методы — 405 с Allow для пользователя, прошедшего внешние guard; auth/CSRF middleware может отвергнуть запрос раньше. Разрешённые методы перечислены ниже и проверяются по коду.
- Неизвестные обычные поля формы игнорируются; q_* проверяются по snapshot попытки, а experience-* — по formset. Параметры owner/score/confirmed_grade из браузера не выбирают владельца или результат. Нет обещания произвольного 500 в спецификации: такой ответ блокирует проверку.

GET/HEAD invitations фиксирует viewed_at; некоторые страницы работодателя создают собственную Company при первом чтении. Это явные побочные эффекты существующего веб-интерфейса. Нельзя переиспользовать их как обещание чистого чтения нового MCP API.

## Как получить воспроизводимый пример

Из собственного worktree: `uv sync --locked`, `uv run python scripts/build_client_release.py`, затем `uv run python scripts/build_http_spec.py --check` и `uv run python scripts/check_http_contracts.py --output .runtime/qa/http-contracts.json`. Проверка сама создаёт временную SQLite и синтетические аккаунты, выполняет примеры с реальными cookie/CSRF/Bearer и удаляет БД; production не используется. Архивы CLI читаются из собственных .runtime/downloads. [Подробные примеры](examples.md).

OpenAPI request examples показывают допустимую форму тела. ID=1 и токен-заглушку нужно заменить объектом и CSRF своей сессии; это не действующие доступы. JSON response examples синтетические. Источник семантики и генератор — scripts/http_contracts.py и scripts/build_http_spec.py; менять их вместе с кодом. --check сравнивает оба сохранённых результата, а checker отдельно сверяет методы и выполняет HTTP.

## Маршруты

### /drafts/ — Свои MCP/CLI черновики

Методы: **GET**. Роль: **both**.

Session only; active confirmed user and processing consent. Last 100 own immutable drafts, newest first. No apply on GET.

Повтор: Чтение текущего состояния.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Own draft list HTML |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /drafts/{pk}/ — Подтверждение MCP/CLI V2

Методы: **GET / POST**. Роль: **both**.

Owned UUID; kind must match current role. GET shows immutable payload and current before-state, including stale/expired/final state. POST action=apply requires acknowledgement and publication consent for profile.publish. action=cancel needs no acknowledgement. No bearer apply endpoint.

Повтор: Applied apply returns same state without another mutation even after expiry. Cancel repeated cancelled safe; cancelling applied is 409. Expired pending draft can be cancelled.

POST schema: **ActionApproval**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | GET draft state |
| GET | 302 | Successful apply/cancel: same draft URL |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 404 | Missing/foreign draft or inaccessible target |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 200 | GET draft state |
| POST | 302 | Successful apply/cancel: same draft URL |
| POST | 400 | Missing acknowledgement, publication consent or failed payload revalidation |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 404 | Missing/foreign draft or inaccessible target |
| POST | 409 | Stale target, cancelled/final conflict |
| POST | 410 | Expired pending draft |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /learning/ — Учебный маршрут

Методы: **GET**. Роль: **candidate**.

Own profile; selected track is persisted in Django session. Invalid track 404; missing track uses session then ios; invalid grade falls back Junior. Active exam shows return-to-exam screen with 200. Practice does not change category.

Повтор: Чтение текущего состояния.

Побочные эффекты чтения: Stores selected learning_track in session only.

Query (все необязательные):

| Поле | Тип / границы | Правила |
| --- | --- | --- |
| track | string; enum=ios, android, flutter, aurora | См. поведение маршрута. |
| grade | string; enum=Junior, Middle | См. поведение маршрута. |

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Track/progress or active-exam lock screen |
| GET | 404 | Unknown track/missing own profile |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /learning/lessons/{grade}/{topic}/ — Урок iOS (совместимый URL)

Методы: **GET**. Роль: **candidate**.

Legacy route always ios. Known grade/topic required; unknown values 404. Active exam returns 423 without lesson solutions.

Повтор: Чтение текущего состояния.

Побочные эффекты чтения: Stores ios track in session.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Lesson HTML |
| GET | 404 | Unknown grade/topic |
| GET | 423 | Active exam |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /learning/tracks/{track}/lessons/{grade}/{topic}/ — Урок выбранного трека

Методы: **GET**. Роль: **candidate**.

Known track/grade/topic only; own progress/version. Active exam returns 423.

Повтор: Чтение текущего состояния.

Побочные эффекты чтения: Stores selected track in session.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Lesson HTML |
| GET | 404 | Unknown track/grade/topic |
| GET | 423 | Active exam |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /learning/lessons/{grade}/{topic}/complete/ — Отметить изучение iOS

Методы: **POST**. Роль: **candidate**.

Known ios lesson. Requires exact read=on; missing/other value returns message + same canonical track lesson without mutation. Active exam rechecked inside transaction.

Повтор: Same candidate/track/grade/topic/version progress updated without duplicates.

POST schema: **LearningRead**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | Canonical /learning/tracks/ios/lessons/{grade}/{topic}/ |
| POST | 404 | Unknown lesson |
| POST | 423 | Active exam |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /learning/tracks/{track}/lessons/{grade}/{topic}/complete/ — Отметить изучение трека

Методы: **POST**. Роль: **candidate**.

Known lesson; exact read=on needed. Missing checkbox gives message+redirect without write. Exam lock rechecked in transaction.

Повтор: Same version progress is idempotent.

POST schema: **LearningRead**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | Canonical selected track lesson |
| POST | 404 | Unknown track/grade/topic |
| POST | 423 | Active exam |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /learning/start/ — Начать / продолжить самопроверку

Методы: **POST**. Роль: **candidate**.

One active practice per track. 8 questions for all, 4 for topic. Optional owned finished source overrides supplied track/grade/version and repeats errors. Invalid selection gives message+302 dashboard. Source parsed with Python int (including numeric Unicode/whitespace) and bounded positive ID.

Повтор: Active session in selected track reused; completed source repeat creates new session. No expiry/cooldown/grade assignment.

POST schema: **LearningStart**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | Session ?question=<next> or /learning/ on invalid selection |
| POST | 404 | Malformed/foreign/not-finished source |
| POST | 423 | Active exam |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /learning/sessions/{pk}/ — Своя самопроверка / разбор

Методы: **GET**. Роль: **candidate**.

Active session exposes current question without solution; question is a bounded zero-based index parsed by Python int. Finished session ignores question parameter and shows full review. Active exam hides content with 423.

Повтор: Чтение текущего состояния.

Побочные эффекты чтения: Stores session track in browser session.

Query (все необязательные):

| Поле | Тип / границы | Правила |
| --- | --- | --- |
| question | integer; minimum=0 | Less than tasks length; default first unanswered or last. Ignored when finished. |

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Question/review HTML |
| GET | 404 | Foreign/missing session or invalid active question index |
| GET | 423 | Active exam |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /learning/sessions/{pk}/answer/ — Сохранить / закончить практику

Методы: **POST**. Роль: **candidate**.

Own session; validates all q_ answers atomically. Unknown/invalid question gives message+302 unchanged; all non-q_ fields ignored. action=pause saves then dashboard; action=finish saves and computes practice result only. Active exam returns 423 including transactional recheck.

Повтор: Finished session returns unchanged result. Active save replaces only submitted valid answers.

POST schema: **LearningAnswers**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | Session/review or dashboard for pause |
| POST | 404 | Missing/foreign session |
| POST | 423 | Active exam |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /accounts/integrations/ — Персональные подключения CLI/MCP

Методы: **GET / POST**. Роль: **both**.

Own tokens only. Processing consent is checked before confirmed/active account here. Create action validates name/kind/contact/draft scopes, stores digest, shows secret once in no-store/no-referrer HTML. MCP contacts rejected. Revoke requires own positive id. No automatic web action from token.

Повтор: Create issues another token; revoke remains revoked on repeat.

POST schema: **TokenAction**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | GET list or successful create with one-time secret |
| GET | 302 | Revoke: /accounts/integrations/ |
| GET | 404 | Malformed/foreign token id |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 200 | GET list or successful create with one-time secret |
| POST | 400 | Invalid create form/action |
| POST | 302 | Revoke: /accounts/integrations/ |
| POST | 404 | Malformed/foreign token id |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /company/dashboard/ — Дашборд владельца

Методы: **GET**. Роль: **employer**.

Owned cohorts by send date; accepted conversion is current outcomes of same cohort. Period=7/30/90/all, hr=own positive ID or unassigned, need=own positive ID. Read does not create Company. No contact data. Seven-day overdue is reporting, not automatic expiry.

Повтор: Чтение текущего состояния.

Query (все необязательные):

| Поле | Тип / границы | Правила |
| --- | --- | --- |
| period | string; enum=7, 30, 90, all | См. поведение маршрута. |
| hr | integer; minimum=1; maximum=9223372036854775807 / '' / 'unassigned' | См. поведение маршрута. |
| need | integer; minimum=1; maximum=9223372036854775807 / '' | Omitted/empty selects the documented default; explicit ID must be owned/visible. |

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Dashboard HTML |
| GET | 404 | Invalid period/foreign or malformed filter |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /company/team/ — Команда и ответственный HR

Методы: **POST**. Роль: **employer**.

action=add creates own Recruiter from name. action=assign updates recruiter on own Need only; empty recruiter clears assignment. Existing invitation recruiter attribution is unchanged. Invalid fields show message and redirect, unknown action is 404.

Повтор: Add creates another Recruiter; assign repeats safely.

Побочные эффекты чтения: POST can create own Company if absent.

POST schema: **TeamAction**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | Success/form error: /company/dashboard/ |
| POST | 404 | Unknown action |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /downloads/{filename} — Артефакты CLI

Методы: **GET / HEAD**. Роль: **public**.

Only manifest.json, current-version fsp_client-<version>-py3-none-any.whl and fsp_client-<version>.tar.gz from owned .runtime/downloads. Missing/unknown artifact 404. No database or authentication; no arbitrary path reads.

Повтор: Чтение текущего состояния.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Versioned artifact attachment; manifest application/json, wheel octet-stream, tar.gz application/gzip |
| GET | 404 | Missing/unknown artifact |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | Versioned artifact attachment; manifest application/json, wheel octet-stream, tar.gz application/gzip |
| HEAD | 404 | Missing/unknown artifact |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### / — Главная / кабинет

Методы: **GET / HEAD**. Роль: **public**.

Anonymous sees welcome. Candidate redirects /profile/; employer sees cabinet. Authenticated without processing-v1 redirects /accounts/consent/.

Повтор: Same route choice; no business write.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Welcome/employer cabinet |
| GET | 302 | Own profile or consent |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | Welcome/employer cabinet |
| HEAD | 302 | Own profile or consent |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /accounts/privacy/ — Правила обработки

Методы: **GET / HEAD**. Роль: **public**.

Public processing-v1 and publication rules.

Повтор: Чтение текущего состояния.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Privacy HTML |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | Privacy HTML |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /accounts/register/ — Демонстрационная регистрация

Методы: **GET / POST**. Роль: **public**.

Only demo.invalid; explicit processing consent. Creates inactive user, candidate Profile if applicable, pending registration in this session and 30-minute one-use demo confirmation.

Повтор: Duplicate email: 200 form error. Not an idempotent creation endpoint.

POST schema: **Registration**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | GET form or invalid POST, no user created on error |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 200 | GET form or invalid POST, no user created on error |
| POST | 302 | Valid POST: /accounts/confirm/ |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 403 | Missing/mismatched csrf cookie + header/form token. |

### /accounts/confirm/ — Подтверждение demo email

Методы: **GET / POST**. Роль: **pending-session**.

GET requires pending session. POST requires same pending user + nonce and unexpired unused token. Successful confirmation activates/login user and clears pending state. Does not prove real mailbox ownership.

Повтор: After success pending session is cleared; repeat is 404.

POST schema: **Confirmation**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | GET demo token/form |
| GET | 404 | No pending session |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 302 | Valid POST: / |
| POST | 400 | Wrong/expired token with pending session |
| POST | 404 | No pending session |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 403 | Missing/mismatched csrf cookie + header/form token. |

### /accounts/login/ — Вход

Методы: **GET / POST / HEAD / OPTIONS**. Роль: **public**.

Django authentication, including active-account check. next is limited to allowed same host. GET/HEAD form; POST errors stay 200. OPTIONS empty response with Allow. PUT explicitly rejected.

Повтор: Already authenticated GET shows form (redirect_authenticated_user=False); POST rotates session/CSRF.

Query (все необязательные):

| Поле | Тип / границы | Правила |
| --- | --- | --- |
| next | string | См. поведение маршрута. |

POST schema: **Login**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Form/error or empty OPTIONS |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 200 | Form/error or empty OPTIONS |
| POST | 302 | Valid login to safe next or / |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 403 | Missing/mismatched csrf cookie + header/form token. |
| HEAD | 200 | Form/error or empty OPTIONS |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| OPTIONS | 200 | Form/error or empty OPTIONS |
| OPTIONS | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /accounts/logout/ — Выход

Методы: **POST / OPTIONS**. Роль: **public**.

POST with CSRF clears browser session; anonymous valid POST also redirects. OPTIONS returns empty Allow response.

Повтор: Valid repeated POST redirects / without restoring session.

POST schema: **CsrfOnly**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | POST: / |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 403 | Missing/mismatched csrf cookie + header/form token. |
| OPTIONS | 200 | OPTIONS empty |
| OPTIONS | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /accounts/consent/ — Согласие processing-v1

Методы: **GET / POST**. Роль: **authenticated**.

Authenticated user. Email confirmation is not a separate guard here. Explicit checked boolean is required; processing consent event recorded by service.

Повтор: Reconfirming current consent does not duplicate identical event.

POST schema: **Consent**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | GET/form error |
| GET | 302 | POST success: / |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 200 | GET/form error |
| POST | 302 | POST success: / |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 403 | Missing/mismatched csrf cookie + header/form token. |

### /profile/ — Собственный профиль

Методы: **GET / POST**. Роль: **candidate**.

Confirmed candidate with processing consent. Only own Profile. Skills canonicalized; name/city exclude contact syntax. A publication transition records a separate consent event. Free text/experience/contact are private until the receiving company has an accepted invitation.

Повтор: Replaces current fields; omitted checkbox false. Same publication state does not duplicate consent.

POST schema: **Profile**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | GET or any form/formset validation error |
| GET | 302 | Valid save: /profile/ |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 200 | GET or any form/formset validation error |
| POST | 302 | Valid save: /profile/ |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /profile/resume.pdf — Собственный PDF

Методы: **GET / HEAD**. Роль: **candidate**.

Own candidate PDF with private descriptions, experience and contacts. Cyrillic font embedded. HEAD has headers only.

Повтор: Чтение текущего состояния.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | application/pdf attachment |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | application/pdf attachment |
| HEAD | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| HEAD | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /profile/fsp/ — Своя demo история ФСП

Методы: **GET / HEAD**. Роль: **candidate**.

JSON only for owner; changes_grade=false for all states; dates ISO YYYY-MM-DD. Mock identity is not a registry verification.

Повтор: Чтение текущего состояния.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | FspHistory JSON |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | FspHistory JSON |
| HEAD | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| HEAD | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /profile/fsp/link/ — Привязка / отзыв demo FSP ID

Методы: **GET / POST**. Роль: **candidate**.

DEMO-001..999 history, DEMO-EMPTY none, DEMO-DOWN unavailable. Explicit consent; unique external ID. action=unlink bypasses connect fields and removes own achievements/bonus, preserving grade.

Повтор: Connect refreshes without duplicate events; unlink already disconnected is safe.

POST schema: **FspAction**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | GET/form error, invalid or occupied external ID |
| GET | 302 | Connect/unlink success: /profile/fsp/link/ |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 200 | GET/form error, invalid or occupied external ID |
| POST | 302 | Connect/unlink success: /profile/fsp/link/ |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /company/ — Профиль компании

Методы: **GET / POST**. Роль: **employer**.

Only own Company. Email may remain empty here, but new invitation requires a valid email. Editing Company never rewrites old invitation snapshots.

Повтор: Same POST updates own Company.

Побочные эффекты чтения: GET may lazily create own Company if absent.

POST schema: **Company**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | GET/form error |
| GET | 302 | Save: /company/ |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 200 | GET/form error |
| POST | 302 | Save: /company/ |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /company/needs/ — Потребности компании

Методы: **GET / POST**. Роль: **employer**.

Lists own Needs. Valid POST creates one new Need and updates own Company name/email; salary max >= min required.

Повтор: Repeated valid POST creates another Need; no idempotency token.

Побочные эффекты чтения: GET may lazily create own Company if absent.

POST schema: **Need**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | GET/form error |
| GET | 302 | Creation: /candidates/ |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 200 | GET/form error |
| POST | 302 | Creation: /candidates/ |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /candidates/ — Фильтры и рейтинг

Методы: **GET / HEAD**. Роль: **employer**.

Owned need defaults to first own Need; grade defaults to selected need grade else Junior. grade must match chosen Need. Invalid grade/skill/fsp/mismatch displays 200 empty result with form error. Current specialisation is iOS/Swift. Declared match and test witness separated.

Повтор: Чтение текущего состояния.

Побочные эффекты чтения: GET may lazily create own Company if absent.

Query (все необязательные):

| Поле | Тип / границы | Правила |
| --- | --- | --- |
| need | integer; minimum=1; maximum=9223372036854775807 / '' | Omitted/empty selects the documented default; explicit ID must be owned/visible. |
| grade | string; enum=(empty), Junior, Middle | См. поведение маршрута. |
| skill | string | Comma-separated Swift, SwiftUI, UIKit, Combine, CoreData, Git, XCTest, URLSession; case/spacing aliases canonicalized; unknown skill is a form error. |
| fsp | string; enum=(empty), no_history, demo_history | См. поведение маршрута. |

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Search HTML, including invalid filter form |
| GET | 404 | Malformed/foreign selected need |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | Search HTML, including invalid filter form |
| HEAD | 404 | Malformed/foreign selected need |
| HEAD | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| HEAD | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /candidates/{pk}/ — Доступная карточка кандидата

Методы: **GET / HEAD**. Роль: **employer**.

Visible when published + confirmed category OR this Company has an accepted invitation. Private texts/contacts only under that Company grant. Optional need must be own; absent selects first own matching-grade need. Safe finished witnesses of current grade.

Повтор: Чтение текущего состояния.

Побочные эффекты чтения: May lazily create own Company.

Query (все необязательные):

| Поле | Тип / границы | Правила |
| --- | --- | --- |
| need | integer; minimum=1; maximum=9223372036854775807 / '' | Omitted/empty selects the documented default; explicit ID must be owned/visible. |

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Candidate HTML with grant-aware fields |
| GET | 404 | Invisible/missing candidate or malformed/foreign need |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | Candidate HTML with grant-aware fields |
| HEAD | 404 | Invisible/missing candidate or malformed/foreign need |
| HEAD | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| HEAD | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /candidates/{pk}/resume.pdf — PDF доступного кандидата

Методы: **GET / HEAD**. Роль: **employer**.

Same visibility and contact grant as HTML, including old grant after unpublishing. No contact leak in PDF without acceptance.

Повтор: Чтение текущего состояния.

Побочные эффекты чтения: May lazily create own Company.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | application/pdf attachment |
| GET | 404 | Invisible/missing candidate |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | application/pdf attachment |
| HEAD | 404 | Invisible/missing candidate |
| HEAD | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| HEAD | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /invitations/ — Свои предложения

Методы: **GET / HEAD**. Роль: **both**.

Candidate sees own invitations; employer sees own Company invitations. No cross-candidate data. Immutable conditions snapshot.

Повтор: Чтение текущего состояния.

Побочные эффекты чтения: Candidate GET/HEAD sets viewed_at for unseen items. Employer read may lazily create own Company.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Invitation list |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | Invitation list |
| HEAD | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| HEAD | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /invitations/send/ — Явная отправка предложения

Методы: **POST**. Роль: **employer**.

Need must be owned, candidate published and same category. New invitation requires Company email. Proof IDs belong to this candidate and are finished of the same grade (failed proof may be explicitly selected). Snapshot includes conditions/contact company/selected witnesses/discussion. No contacts of candidate opened yet.

Повтор: Unique (candidate,need). Duplicate preserves initial snapshot; route still requires candidate published/same current grade, and parses IDs before service duplicate check.

POST schema: **Invitation**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | Success/duplicate: /invitations/; missing company email: /company/; invalid proof/discussion: /candidates/{id}/ with message |
| POST | 404 | Malformed/foreign need/candidate/proof ID or >20 proof IDs |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /invitations/{pk}/accept/ — Принять своё предложение

Методы: **POST**. Роль: **candidate**.

Only own invitation. sent -> accepted opens contact grant for sender Company only. Opposite terminal decision leaves state and displays message.

Повтор: Same terminal decision safe; opposite rejected by message + 302.

POST schema: **CsrfOnly**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | All owned decisions: /invitations/ |
| POST | 404 | Missing/foreign invitation |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /invitations/{pk}/decline/ — Отклонить своё предложение

Методы: **POST**. Роль: **candidate**.

Only own invitation. sent -> declined keeps contacts closed. Opposite terminal decision leaves state and displays message.

Повтор: Same terminal decision safe; opposite rejected by message + 302.

POST schema: **CsrfOnly**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | All owned decisions: /invitations/ |
| POST | 404 | Missing/foreign invitation |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /assessments/ — История и выбор теста

Методы: **GET / HEAD**. Роль: **candidate**.

Only own attempts and profile category. No answer keys exposed.

Повтор: Чтение текущего состояния.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Dashboard HTML |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | Dashboard HTML |
| HEAD | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| HEAD | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /assessments/start/ — Начать / продолжить попытку

Методы: **POST**. Роль: **candidate**.

8 questions, four areas, 15 minutes. A/B first distribution and later rotation; shuffled options. Invalid grade, 7-day repeat, 30-day category change and downgrade from Middle yield message + redirect. Expired active attempt is finalized before next eligibility check.

Повтор: Active unexpired attempt reused (even if another valid grade requested); otherwise cooldown/rules apply.

POST schema: **StartAttempt**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | Attempt URL on success/active reuse; /assessments/ on refused start |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /assessments/{pk}/ — Своя попытка / результат

Методы: **GET / HEAD**. Роль: **candidate**.

Owned attempt only. Active HTML shows id/area/prompt/options/selected, never correct keys. Finished HTML shows persisted result.

Повтор: Чтение текущего состояния.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Active/result HTML |
| GET | 404 | Missing/foreign attempt |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | Active/result HTML |
| HEAD | 404 | Missing/foreign attempt |
| HEAD | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| HEAD | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /assessments/{pk}/answer/ — Сохранить ответы

Методы: **POST**. Роль: **candidate**.

Valid own snapshot questions q_ID, options 0..3. No scoring/grade accepted from browser. Unknown question/invalid answer rejects entire write. Expired save rejected. Repeated finished attempt returns existing result.

Повтор: Replaces submitted answers within active deadline; finished safe no-op.

POST schema: **Answers**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | Own attempt URL with success/error message |
| POST | 404 | Missing/foreign attempt |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /assessments/{pk}/finish/ — Завершить попытку

Методы: **POST**. Роль: **candidate**.

Server scores >=6/8 and >=1 per area. Failed result does not demote. Expired finish ignores late submitted answers and uses already saved answers. Invalid current answers give message and keep active. Snapshot bank/rules immutable.

Повтор: Finished attempt is idempotent; ignores repeated body, score/category not rewritten.

POST schema: **Answers**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| POST | 302 | Own attempt URL with result/error |
| POST | 404 | Missing/foreign attempt |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /assessments/{pk}/proof/ — Безопасное свидетельство

Методы: **GET / HEAD**. Роль: **both**.

Finished own candidate attempt; employer requires visible profile and current grade. Witness fields: attempt_id/specialization/grade/finished_at/bank_version/rules_version/variant/areas/correct_count/total/passed/expired/criteria/limitations. No tasks/answers/keys.

Повтор: Чтение текущего состояния.

Побочные эффекты чтения: Employer may lazily create own Company.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | HTML witness |
| GET | 404 | Foreign/invisible/active/wrong-grade attempt |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | HTML witness |
| HEAD | 404 | Foreign/invisible/active/wrong-grade attempt |
| HEAD | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| HEAD | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /assistant/ — Мок помощника и черновики

Методы: **GET / POST**. Роль: **both**.

GET displays mode/selection and last ten own drafts, no provider call. POST profile/need creates private 24-hour Draft only; result/matching/conversation read allowed context. invitation preview has a separate explicit send form. Contacts/free private text/question keys excluded from provider. Usage 10/hour; failed provider calls count; active candidate test blocks POST.

Повтор: POST generation consumes usage and may create another Draft; never sends invitation/changes category.

Query (все необязательные):

| Поле | Тип / границы | Правила |
| --- | --- | --- |
| mode | string; enum=profile, need, result, matching, invitation, conversation | См. поведение маршрута. |
| need | integer; minimum=1; maximum=9223372036854775807 / '' | Omitted/empty selects the documented default; explicit ID must be owned/visible. |
| attempt | integer; minimum=1; maximum=9223372036854775807 / '' | Omitted/empty selects the documented default; explicit ID must be owned/visible. |
| candidate | integer; minimum=1; maximum=9223372036854775807 / '' | Omitted/empty selects the documented default; explicit ID must be owned/visible. |
| invitation | integer; minimum=1; maximum=9223372036854775807 / '' | Omitted/empty selects the documented default; explicit ID must be owned/visible. |

POST schema: **Assistant**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Mode form/editor/mock result |
| GET | 404 | Malformed/foreign/invisible explicit ID |
| GET | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 200 | Mode form/editor/mock result |
| POST | 400 | Invalid prompt or missing result/stage context |
| POST | 404 | Malformed/foreign/invisible explicit ID |
| POST | 409 | Candidate active assessment |
| POST | 429 | 10/hour generation limit |
| POST | 503 | Provider failure; manual forms remain available |
| POST | 302 | Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent. |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /assistant/drafts/{pk}/ — Проверить / применить свой черновик

Методы: **GET / POST**. Роль: **both**.

Own Draft + mode matches role. GET editor/status even after expiry. POST checked description or NeedForm, explicit browser action. Source Need deletion allowed; source reassignment/profile description conflict denied. No user-selected mode/owner/source/applied ID. Applying does not consume generation usage.

Повтор: Applied Draft POST redirects without second write or validation, even after expiry; candidate active test guard still 409.

POST schema: **DraftApply**; поля см. ниже.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | GET editor/status |
| GET | 302 | Authentication or consent redirect only; editor never applies on GET. |
| GET | 404 | Foreign/missing Draft |
| GET | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| POST | 302 | Applied profile: /profile/; need: /company/needs/ |
| POST | 400 | Invalid editable fields, no partial write |
| POST | 404 | Foreign/missing Draft |
| POST | 409 | Stale source/description or active candidate test |
| POST | 410 | Expired unapplied Draft |
| POST | 403 | Wrong role/unconfirmed email; POST additionally invalid CSRF. |
| POST | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /health/ — Готовность БД

Методы: **GET / HEAD**. Роль: **public**.

Read queries required tables. DatabaseError -> 503 without secrets. Not a full user journey or liveness/reboot proof.

Повтор: Чтение текущего состояния.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | HealthOk JSON |
| GET | 503 | HealthUnavailable JSON |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | HealthOk JSON |
| HEAD | 503 | HealthUnavailable JSON |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

### /version/ — Версия выпуска

Методы: **GET / HEAD**. Роль: **public**.

40-character Git SHA from deployed REVISION or local Git HEAD; mock mode. No configuration/tokens returned.

Повтор: Чтение текущего состояния.

| Метод | Статус | Значение |
| --- | --- | --- |
| GET | 200 | Version JSON |
| GET | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |
| HEAD | 200 | Version JSON |
| HEAD | 405 | Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first. |

## Token API /api/v1

API не использует browser session и CSRF. Каждая операция требует активный Bearer token своей роли/скоупа, подтверждённый аккаунт и processing consent. 60 запросов/минуту, срок 30 дней; revoke/expiry → 401, scope/role/consent → 403. Данные/ошибки JSON без HTML redirect. Cache-Control=no-store, X-Request-ID; 429 также Retry-After=60, 401 WWW-Authenticate=Bearer. На GET меняется только учёт использования токена, бизнес-данные не меняются. MCP не получает контакты/свободные приватные тексты/PDF; CLI private требует contacts.read и действующий grant. Все DTO приведены в схемах Api ниже.

### GET /api/v1/me

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read OR employer.read

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/catalog

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read OR employer.read

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/me/profile

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/me/profile/private

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read; contacts.read; kind=cli

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/me/assessments

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read

| Поле | Где | Тип / границы |
| --- | --- | --- |
| limit | query | integer; minimum=1; maximum=100 |
| offset | query | integer; minimum=0; maximum=2147483647 |

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/me/assessments/{pk}/result

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read

| Поле | Где | Тип / границы |
| --- | --- | --- |
| pk | path | integer; minimum=1; maximum=9223372036854775807 |

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/me/achievements

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/me/company

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. employer.read

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/needs

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. employer.read

| Поле | Где | Тип / границы |
| --- | --- | --- |
| limit | query | integer; minimum=1; maximum=100 |
| offset | query | integer; minimum=0; maximum=2147483647 |

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/needs/{pk}

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. employer.read

| Поле | Где | Тип / границы |
| --- | --- | --- |
| pk | path | integer; minimum=1; maximum=9223372036854775807 |

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/candidates

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. employer.read

| Поле | Где | Тип / границы |
| --- | --- | --- |
| limit | query | integer; minimum=1; maximum=100 |
| offset | query | integer; minimum=0; maximum=2147483647 |
| need_id | query | integer; minimum=1 |
| grade | query | object; enum=Junior, Middle |
| skill | query | string |
| fsp_status | query | object; enum=no_history, demo_history |

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/candidates/{pk}

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. employer.read

| Поле | Где | Тип / границы |
| --- | --- | --- |
| pk | path | integer; minimum=1; maximum=9223372036854775807 |
| need_id | query | integer; minimum=1 |

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/candidates/{pk}/proofs

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. employer.read

| Поле | Где | Тип / границы |
| --- | --- | --- |
| pk | path | integer; minimum=1; maximum=9223372036854775807 |
| limit | query | integer; minimum=1; maximum=100 |
| offset | query | integer; minimum=0; maximum=2147483647 |

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/candidates/{pk}/private

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. employer.read; contacts.read; kind=cli

| Поле | Где | Тип / границы |
| --- | --- | --- |
| pk | path | integer; minimum=1; maximum=9223372036854775807 |

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/invitations

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read OR employer.read

| Поле | Где | Тип / границы |
| --- | --- | --- |
| limit | query | integer; minimum=1; maximum=100 |
| offset | query | integer; minimum=0; maximum=2147483647 |

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/invitations/{pk}

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read OR employer.read

| Поле | Где | Тип / границы |
| --- | --- | --- |
| pk | path | integer; minimum=1; maximum=9223372036854775807 |

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/invitations/{pk}/contacts

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read OR employer.read; contacts.read; kind=cli

| Поле | Где | Тип / границы |
| --- | --- | --- |
| pk | path | integer; minimum=1; maximum=9223372036854775807 |

| Статус | Ответ |
| --- | --- |
| 200 | Success; MCP omits free text and contact fields |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 429 | API error |
| 503 | API error |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/me/profile/resume.pdf

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read; kind=cli; contacts.read when with_contacts=true

| Поле | Где | Тип / границы |
| --- | --- | --- |
| with_contacts | query | boolean |

| Статус | Ответ |
| --- | --- |
| 200 | PDF, contacts opt-in subject to accepted grant |
| 400 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/candidates/{pk}/resume.pdf

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. employer.read; kind=cli; contacts.read when with_contacts=true

| Поле | Где | Тип / границы |
| --- | --- | --- |
| pk | path | integer |
| with_contacts | query | boolean |

| Статус | Ответ |
| --- | --- |
| 200 | PDF, contacts opt-in subject to accepted grant |
| 400 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/drafts

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.read OR employer.read  Drafts are immutable for 24 hours. GET projects payload only to CLI contacts.read; otherwise safe preview. Prepare needs current role.draft scope; cancel repeats safely for cancelled or expired pending, applied cancel 409. Applying is browser-only, rechecks owner/role/consent/fingerprint and is idempotent after apply.

| Поле | Где | Тип / границы |
| --- | --- | --- |
| limit | query | integer; minimum=1; maximum=100 |
| offset | query | integer; minimum=0; maximum=2147483647 |

| Статус | Ответ |
| --- | --- |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 410 | API error |
| 429 | API error |
| 503 | API error |
| 200 | Own drafts |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### POST /api/v1/drafts

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.draft OR employer.draft Prepare only. Contacts/experience require CLI contacts.read. No API apply endpoint. Drafts are immutable for 24 hours. GET projects payload only to CLI contacts.read; otherwise safe preview. Prepare needs current role.draft scope; cancel repeats safely for cancelled or expired pending, applied cancel 409. Applying is browser-only, rechecks owner/role/consent/fingerprint and is idempotent after apply.

| Статус | Ответ |
| --- | --- |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 410 | API error |
| 429 | API error |
| 503 | API error |
| 201 | Own draft; MCP and non-private CLI projections hide contact/private values |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/drafts/{pk}

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404.   Drafts are immutable for 24 hours. GET projects payload only to CLI contacts.read; otherwise safe preview. Prepare needs current role.draft scope; cancel repeats safely for cancelled or expired pending, applied cancel 409. Applying is browser-only, rechecks owner/role/consent/fingerprint and is idempotent after apply.

| Поле | Где | Тип / границы |
| --- | --- | --- |
| pk | path | string |

| Статус | Ответ |
| --- | --- |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 410 | API error |
| 429 | API error |
| 503 | API error |
| 200 | Own draft; MCP and non-private CLI projections hide contact/private values |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### POST /api/v1/drafts/{pk}/cancel

Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. Integer IDs use bounded positive parser; draft UUIDs use Python UUID parser; malformed/foreign IDs 404. candidate.draft OR employer.draft  Drafts are immutable for 24 hours. GET projects payload only to CLI contacts.read; otherwise safe preview. Prepare needs current role.draft scope; cancel repeats safely for cancelled or expired pending, applied cancel 409. Applying is browser-only, rechecks owner/role/consent/fingerprint and is idempotent after apply.

| Поле | Где | Тип / границы |
| --- | --- | --- |
| pk | path | string |

| Статус | Ответ |
| --- | --- |
| 400 | API error |
| 401 | API error |
| 403 | API error |
| 404 | API error |
| 405 | API error |
| 409 | API error |
| 410 | API error |
| 429 | API error |
| 503 | API error |
| 200 | Own draft; MCP and non-private CLI projections hide contact/private values |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/openapi.json

Same token authentication, rate limit and JSON error boundary as /api/v1/me. Unknown route GET returns 404 after valid auth; unsupported method 405.

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 200 | OpenAPI of token API module |

### GET /api/v1/

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### POST /api/v1/

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### PUT /api/v1/

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### PATCH /api/v1/

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### DELETE /api/v1/

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### HEAD /api/v1/

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### OPTIONS /api/v1/

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### GET /api/v1/{unknown}

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Поле | Где | Тип / границы |
| --- | --- | --- |
| unknown | path | string; minLength=1 |

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### POST /api/v1/{unknown}

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Поле | Где | Тип / границы |
| --- | --- | --- |
| unknown | path | string; minLength=1 |

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### PUT /api/v1/{unknown}

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Поле | Где | Тип / границы |
| --- | --- | --- |
| unknown | path | string; minLength=1 |

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### PATCH /api/v1/{unknown}

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Поле | Где | Тип / границы |
| --- | --- | --- |
| unknown | path | string; minLength=1 |

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### DELETE /api/v1/{unknown}

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Поле | Где | Тип / границы |
| --- | --- | --- |
| unknown | path | string; minLength=1 |

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### HEAD /api/v1/{unknown}

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Поле | Где | Тип / границы |
| --- | --- | --- |
| unknown | path | string; minLength=1 |

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

### OPTIONS /api/v1/{unknown}

Authenticated explicit unknown-route fallback; GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS return JSON 404. TRACE is rejected with 405 after authentication.

| Поле | Где | Тип / границы |
| --- | --- | --- |
| unknown | path | string; minLength=1 |

| Статус | Ответ |
| --- | --- |
| 401 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 403 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 404 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 405 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 429 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 503 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |
| 500 | Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route. |

## Схемы полей

Числа/boolean ниже — логические типы после сериализации формы; на HTTP проводе URLencoded значения текстовые. Required относится к допустимому успешному POST. Схема не заменяет межполевую и владельческую проверку сервера.

### Registration

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| email | да | string; maxLength=254 | Unique @demo.invalid address, trimmed/lowercased. No real email is sent. |
| role | да | string; minLength=1; enum=candidate, employer | — |
| password1 | да | string; minLength=8 | Minimum configured length 8; common passwords rejected; must equal password2. |
| password2 | да | string; minLength=8 | Must equal password1. |
| processing_consent | да | True | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### Login

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| username | да | string; minLength=1; maxLength=150 | — |
| password | да | string; minLength=1 | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |
| next | нет | string | Optional safe redirect on same host; unsafe destination replaced by /. |

### Consent

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| processing_consent | да | True | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### Profile

Experience formset is validated only when TOTAL_FORMS is present; INITIAL_FORMS then required. At most 20 entries. Empty extra rows are skipped; existing id must be owned; hidden profile must match own Profile if present. Any error prevents the entire profile/formset save.

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| name | нет | string; maxLength=80 | Letters, spaces, hyphens; required when published=true. |
| city | нет | string; maxLength=80 | Letters, spaces, hyphens; contacts belong in private fields. |
| skills | нет | string; maxLength=200 | Comma-separated Swift, SwiftUI, UIKit, Combine, CoreData, Git, XCTest, URLSession; case/spacing aliases canonicalized; unknown skill is a form error. |
| specialization | нет | string; enum=(empty), ios_swift | Empty/omitted becomes ios_swift. |
| experience_months | нет | integer; minimum=0; maximum=600 | Omitted/empty becomes 0; self-reported. |
| roles | нет | array[string; enum=developer, reviewer, mentor, lead] | — |
| soft_skills | нет | array[string; enum=communication, teamwork, planning, feedback] | — |
| description | нет | string; maxLength=3000 | Private until this company has an accepted invitation. Plain text, not HTML. |
| contact_email | нет | string; maxLength=254 | Valid email when non-empty. |
| contact_phone | нет | string; maxLength=40 | — |
| desired_grade | да | string; minLength=1; enum=Junior, Middle | — |
| published | нет | boolean | Separate publication consent. Omitted checkbox is false; accepted invitation grants survive unpublishing. |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |
| experience-TOTAL_FORMS | нет | integer; minimum=0; maximum=20 | — |
| experience-INITIAL_FORMS | нет | integer; minimum=0; maximum=20 | — |
| experience-MIN_NUM_FORMS | нет | integer; minimum=0 | — |
| experience-MAX_NUM_FORMS | нет | integer; minimum=0 | — |

Динамические поля:

- `^experience-[0-9]+-(organization|role)$`: string; maxLength=120.
- `^experience-[0-9]+-months$`: integer; minimum=0; maximum=600.
- `^experience-[0-9]+-description$`: string; maxLength=2000.
- `^experience-[0-9]+-(id|profile)$`: integer; minimum=1; maximum=9223372036854775807 / ''.
- `^experience-[0-9]+-DELETE$`: boolean.

### FspConnect

Explicit fsp-mock-v1 consent; external ID unique in this app, not verified by a real registry.

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| external_id | да | string; minLength=1; maxLength=40 | — |
| consent | да | True | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### Company

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| name | да | string; minLength=1; maxLength=120 | — |
| industry | нет | string; maxLength=120 | — |
| description | нет | string; maxLength=3000 | — |
| contact_email | нет | string; maxLength=254 | Valid email when non-empty. |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### Need

salary_min/max are positive rubles before tax per month; max >= min. Creates a new Need and updates own company name/email. No edit of existing Need.

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| title | да | string; minLength=1; maxLength=120 | — |
| grade | да | string; minLength=1; enum=Junior, Middle | — |
| skills | нет | string; maxLength=200 | Comma-separated Swift, SwiftUI, UIKit, Combine, CoreData, Git, XCTest, URLSession; case/spacing aliases canonicalized; unknown skill is a form error. |
| tasks | да | string; minLength=1; maxLength=1500 | — |
| salary_min | да | integer; minimum=1; maximum=9223372036854775807 | — |
| salary_max | да | integer; minimum=1; maximum=9223372036854775807 | — |
| work_format | да | string; minLength=1; enum=remote, office, hybrid | — |
| next_step | да | string; minLength=1; maxLength=200 | — |
| recruiter | нет | integer; minimum=1; maximum=9223372036854775807 / '' | Optional HR of own Company; empty means unassigned. Invitation stores current HR separately; reassigning Need does not rewrite old invitations. |
| company_name | да | string; minLength=1; maxLength=120 | — |
| company_email | нет | string; maxLength=320 | Valid email when non-empty. |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### NeedPrompt

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| grade | нет | string; enum=(empty), Junior, Middle | — |
| skills | нет | string; maxLength=200 | Comma-separated Swift, SwiftUI, UIKit, Combine, CoreData, Git, XCTest, URLSession; case/spacing aliases canonicalized; unknown skill is a form error. |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### ProfileDraft

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| description | да | string; minLength=1; maxLength=3000 | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### Recruiter

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| name | да | string; minLength=1; maxLength=120 | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### Assignment

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| need | да | integer; minimum=1; maximum=9223372036854775807 | Owned dropdown object. Invalid selection is a form error, not necessarily 404; see endpoint. |
| recruiter | нет | integer; minimum=1; maximum=9223372036854775807 / '' | Owned dropdown object. Invalid selection is a form error, not necessarily 404; see endpoint. |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### Token

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| name | да | string; minLength=1; maxLength=80 | — |
| kind | да | string; minLength=1; enum=cli, mcp | — |
| contacts | нет | boolean | — |
| drafts | нет | boolean | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### Approval

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| acknowledge | да | True | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### ExperienceInput

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| organization | да | string; minLength=1; maxLength=120 | — |
| role | да | string; minLength=1; maxLength=120 | — |
| months | да | integer; minimum=0; maximum=600 | — |
| description | нет | string; maxLength=2000 | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### LearningRead

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| read | да | 'on' | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### LearningStart

Finished source overrides track/grade/topic; supplied selectors ignored and may be omitted. Source accepts Python int syntax then positive ID bounds. Without source normal selector fields apply.

Варианты: object, object

Вариант 1:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| track | нет | string; enum=ios, android, flutter, aurora |
| grade | да | string; enum=Junior, Middle |
| topic | нет | string |
| source | нет | integer; minimum=1; maximum=9223372036854775807 / '' |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 |

Вариант 2:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| source | да | integer; minimum=1; maximum=9223372036854775807 |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 |

### LearningAnswers

Unknown q_ key or invalid answer rejects the entire save. Non-q_ fields ignored. Missing/unknown action saves; pause redirects to dashboard; finish computes immutable practice result. No time limit or category change.

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| action | нет | string; enum=save, pause, finish | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

Динамические поля:

- `^q_.+$`: integer; minimum=0; maximum=3.

### ActionApproval

Publication consent=true additionally required for profile.publish; all other kinds need acknowledge=true. Values edited here never replace immutable draft payload. Browser session only, Bearer is ignored.

Варианты: object, object

Вариант 1:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| action | да | 'cancel' |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 |

Вариант 2:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| action | да | 'apply' |
| acknowledge | да | True |
| publication_consent | нет | boolean |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 |

### CsrfOnly

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### Confirmation

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| token | да | string; minLength=1 | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### FspAction

Варианты: FspConnect, object

Вариант 2:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| action | да | 'unlink' |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 |

### StartAttempt

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| grade | да | string; enum=Junior, Middle | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### Answers

q_<task-id> from this attempt, choice 0..3. Missing answers remain stored/unanswered. Non-q_ fields ignored; unknown task/invalid answer gives 302 + message with no partial save.

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

Динамические поля:

- `^q_.+$`: integer; minimum=0; maximum=3.

### Invitation

Own Need, published candidate of same category. Selected results must be finished, owned by candidate, same grade; employer explicitly accepts them. Contact company email required for a new invitation.

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| need | да | integer; minimum=1; maximum=9223372036854775807 | Positive ASCII decimal, at most 19 digits on the wire; leading zeroes accepted. Foreign/malformed ID returns 404. |
| candidate | да | integer; minimum=1; maximum=9223372036854775807 | Positive ASCII decimal, at most 19 digits on the wire; leading zeroes accepted. Foreign/malformed ID returns 404. |
| accepted_attempts | нет | array[integer; minimum=1; maximum=9223372036854775807]; maxItems=20 | — |
| discussion | нет | string; maxLength=2000 | — |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### Assistant

Mode default depends on role. profile/result: candidate; need/matching/invitation: employer; conversation: either role. Matching/invitation require need + candidate; conversation requires invitation. Partial stage selection GET shows form; POST returns 400 before ownership resolution. Complete stage selection resolves ownership/visibility. For result identifier selects own finished attempt, else latest. For need identifier selects own Need, else last unless new_need=on; a new employer may start without Company/Need.

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| mode | нет | string; enum=profile, need, result, matching, invitation, conversation | — |
| identifier | нет | integer; minimum=1; maximum=9223372036854775807 / '' | Omitted/empty selects the documented default; explicit ID must be owned/visible. |
| new_need | нет | string; enum=on, (empty) | — |
| grade | нет | string; enum=(empty), Junior, Middle | — |
| skills | нет | string; maxLength=200 | Comma-separated Swift, SwiftUI, UIKit, Combine, CoreData, Git, XCTest, URLSession; case/spacing aliases canonicalized; unknown skill is a form error. |
| need | нет | integer; minimum=1; maximum=9223372036854775807 / '' | Omitted/empty selects the documented default; explicit ID must be owned/visible. |
| candidate | нет | integer; minimum=1; maximum=9223372036854775807 / '' | Omitted/empty selects the documented default; explicit ID must be owned/visible. |
| invitation | нет | integer; minimum=1; maximum=9223372036854775807 / '' | Omitted/empty selects the documented default; explicit ID must be owned/visible. |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 | CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field. |

### DraftApply

Actual stored Draft.mode selects the form. Profile applies description only; need creates a new own Need. Body cannot choose mode/owner/grade of Profile.

Варианты: ProfileDraft, Need

### TeamAction

Варианты: object, object

Вариант 1:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| name | да | string; minLength=1; maxLength=120 |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 |
| action | да | 'add' |

Вариант 2:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| need | да | integer; minimum=1; maximum=9223372036854775807 |
| recruiter | нет | integer; minimum=1; maximum=9223372036854775807 / '' |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 |
| action | да | 'assign' |

### TokenAction

Create displays token once in no-store HTML. MCP cannot request contacts. Revoke only own token; repeated revoke is safe. Draft scope may be reserved before V2 paths exist.

Варианты: object, object

Вариант 1:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| name | да | string; minLength=1; maxLength=80 |
| kind | да | string; minLength=1; enum=cli, mcp |
| contacts | нет | boolean |
| drafts | нет | boolean |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 |
| action | да | 'create' |

Вариант 2:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| action | да | 'revoke' |
| id | да | integer; minimum=1; maximum=9223372036854775807 |
| csrfmiddlewaretoken | нет | string; minLength=32; maxLength=64 |

### ClientArtifact

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| filename | да | string | — |
| bytes | да | integer; minimum=1 | — |
| sha256 | да | string | — |

### ClientManifest

Actual wheel and source archive of this client version; hashes and byte sizes checked by build_client_release.py and contract verifier.

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| version | да | string; minLength=1 | — |
| commit | да | string | — |
| files | да | array[ClientArtifact]; maxItems=2 | — |

### HealthOk

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| status | да | 'ok' | — |

### HealthUnavailable

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| status | да | 'unavailable' | — |

### Version

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| commit | да | string | — |
| assistant_mode | да | 'mock' | — |

### FspEvent

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| event_id | да | string | — |
| source | да | 'mock' | — |
| event_name | да | string | — |
| occurred_on | да | string | — |
| discipline | да | string | — |
| result | да | string | — |
| team | да | boolean | — |
| prize | да | boolean | — |

### FspHistory

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| source | да | 'mock' | — |
| status | да | string; enum=not_connected, no_history, demo_history, unavailable | — |
| changes_grade | да | False | — |
| external_id | да | ['string', 'null'] | — |
| events | да | array[FspEvent] | — |

### ApiMeta

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| api_version | да | '1' | — |
| data_mode | да | 'demo' | — |
| request_id | да | string | — |

### ApiPagination

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| limit | да | integer | — |
| offset | да | integer | — |
| total | да | integer | — |

### ApiIdentity

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| id | да | integer | — |
| role | да | object; enum=candidate, employer | — |
| token_kind | да | object; enum=cli, mcp | — |
| scopes | да | array[string] | — |
| expires_at | да | string | — |

### ApiProfile

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| id | да | integer | — |
| name | да | string | — |
| city | да | string | — |
| skills | да | array[string] | — |
| specialization | да | 'ios_swift' | — |
| experience_months | да | integer | — |
| roles | да | array[string] | — |
| soft_skills | да | array[string] | — |
| published | да | boolean | — |
| desired_grade | да | string | — |
| confirmed_grade | да | string | — |
| test_score | да | number | — |
| fsp_status | да | string | — |
| self_declared | да | array[string] | — |

### ApiExperience

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| id | да | integer | — |
| organization | да | string | — |
| role | да | string | — |
| months | да | integer | — |
| description | да | string | — |

### ApiPrivateProfile

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| id | да | integer | — |
| contact_email | да | string | — |
| contact_phone | да | string | — |
| description | да | string | — |
| experiences | да | array[ApiExperience] | — |

### ApiProof

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| attempt_id | да | ['integer', 'null'] | — |
| specialization | да | string | — |
| grade | да | string | — |
| finished_at | да | ['string', 'null'] | — |
| bank_version | да | string | — |
| rules_version | да | string | — |
| variant | да | ['string', 'null'] | — |
| areas | да | object | — |
| correct_count | да | integer | — |
| total | да | integer | — |
| passed | да | boolean | — |
| expired | да | boolean | — |
| criteria | да | object | — |
| limitations | да | string | — |

### ApiAssessment

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| id | да | integer | — |
| grade | да | string | — |
| status | да | string | — |
| started_at | да | string | — |
| expires_at | да | string | — |
| result | да | ApiProof / null | — |

### ApiCompany

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| id | да | integer | — |
| name | да | string | — |
| industry | нет | string | — |
| description | нет | string | — |

### ApiCompanyState

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| state | да | object; enum=ready, company_not_created | — |
| company | да | ApiCompany / null | — |

### ApiNeed

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| id | да | integer | — |
| company_id | да | integer | — |
| title | да | string | — |
| grade | да | string | — |
| skills | да | array[string] | — |
| salary_min | да | integer | — |
| salary_max | да | integer | — |
| currency | да | 'RUB' | — |
| salary_period | да | 'month' | — |
| salary_tax | да | 'gross' | — |
| work_format | да | string | — |
| tasks | нет | string | — |
| next_step | нет | string | — |

### ApiExplanation

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| declared_matches | да | array[string] | — |
| declared_gaps | да | array[string] | — |
| confirmation | да | ApiProof / null | — |
| unknown | да | array[string] | — |

### ApiMatch

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| profile | да | ApiProfile | — |
| score | да | number | — |
| parts | да | object | — |
| explanation | да | ApiExplanation | — |

### ApiCandidate

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| profile | да | ApiProfile | — |
| contacts_allowed | да | boolean | — |
| explanation | да | ApiExplanation | — |

### ApiInvitation

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| id | да | integer | — |
| candidate_id | да | integer | — |
| need_id | да | integer | — |
| company_id | да | integer | — |
| company | да | ['string', 'null'] | — |
| title | да | ['string', 'null'] | — |
| grade | да | string | — |
| salary_min | да | ['integer', 'null'] | — |
| salary_max | да | ['integer', 'null'] | — |
| currency | да | string | — |
| salary_period | да | string | — |
| salary_tax | да | string | — |
| work_format | да | ['string', 'null'] | — |
| status | да | string | — |
| created_at | да | string | — |
| responded_at | да | ['string', 'null'] | — |
| accepted_results | да | array[ApiProof] | — |
| company_description | нет | string | — |
| company_industry | нет | string | — |
| tasks | нет | string | — |
| next_step | нет | string | — |
| discussion | нет | string | — |

### ApiCompanyContact

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| company_id | да | integer | — |
| contact_email | да | string | — |

### ApiAchievement

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| id | да | integer | — |
| source | да | 'mock' | — |
| event_name | да | string | — |
| occurred_on | да | string | — |
| team | да | boolean | — |
| prize | да | boolean | — |
| event_id | нет | string | — |
| discipline | нет | string | — |
| result | нет | string | — |

### ApiAchievements

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| source | да | 'mock' | — |
| status | да | string | — |
| changes_grade | да | False | — |
| events | да | array[ApiAchievement] | — |
| external_id | нет | ['string', 'null'] | — |

### ApiCatalog

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| specializations | да | array[string] | — |
| grades | да | array[string] | — |
| skills | да | array[string] | — |
| roles | да | object | — |
| soft_skills | да | object | — |
| features | да | array[string] | — |
| fsp_source | да | 'mock' | — |

### ApiError

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| error | да | object | — |
| meta | да | ApiMeta | — |

### ApiContactUnion

### ApiDraft

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| id | да | string | — |
| kind | да | string | — |
| target_id | да | ['integer', 'null'] | — |
| status | да | object; enum=pending, applied, cancelled, expired | — |
| source | да | object; enum=cli, mcp | — |
| expires_at | да | string | — |
| created_at | да | string | — |
| approval_path | да | string | — |
| applied_target_id | да | ['integer', 'null'] | — |
| fields | да | array[string] | — |
| payload | нет | object | — |
| preview | нет | object | — |

### ActionExperience

| Поле | Обязательно | Тип / границы | Правила |
| --- | --- | --- | --- |
| organization | да | string; minLength=1; maxLength=120 | — |
| role | да | string; minLength=1; maxLength=120 | — |
| months | да | integer; minimum=0; maximum=600 | — |
| description | нет | string; maxLength=2000 | — |
| id | нет | integer; minimum=1; maximum=9223372036854775807 / null | — |

### ActionPrepare

Prepare only, no business mutation. Each role may prepare its own kinds with role.draft scope. profile/company partial patches merge existing values and validate whole form. MCP rejects contact_email/contact_phone/experiences; CLI requires contacts.read. salary_max>=salary_min; IDs owned and current. Empty action payload may be omitted. Private/free text accepted when allowed is not reflected in MCP safe preview. Publishing requires separate consent at browser apply.

Вариант 1:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| kind | да | 'profile.update' |
| target_id | нет | integer; minimum=1; maximum=9223372036854775807 / null |
| payload | да | object |

Поля payload:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| name | нет | string; maxLength=80 |
| city | нет | string; maxLength=80 |
| skills | нет | string; maxLength=200 |
| specialization | нет | string; enum=(empty), ios_swift |
| experience_months | нет | integer; minimum=0; maximum=600 |
| roles | нет | array[string; enum=developer, reviewer, mentor, lead] |
| soft_skills | нет | array[string; enum=communication, teamwork, planning, feedback] |
| description | нет | string; maxLength=3000 |
| contact_email | нет | string; maxLength=254 |
| contact_phone | нет | string; maxLength=40 |
| desired_grade | нет | string; minLength=1; enum=Junior, Middle |
| experiences | нет | array[ActionExperience]; maxItems=20 |

Вариант 2:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| kind | да | 'company.update' |
| target_id | нет | integer; minimum=1; maximum=9223372036854775807 / null |
| payload | да | object |

Поля payload:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| name | нет | string; minLength=1; maxLength=120 |
| industry | нет | string; maxLength=120 |
| description | нет | string; maxLength=3000 |
| contact_email | нет | string; maxLength=254 |

Вариант 3:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| kind | да | 'need.create' |
| target_id | нет | null |
| payload | да | object |

Поля payload:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| title | да | string; minLength=1; maxLength=120 |
| grade | да | string; minLength=1; enum=Junior, Middle |
| skills | нет | string; maxLength=200 |
| tasks | да | string; minLength=1; maxLength=1500 |
| salary_min | да | integer; minimum=1; maximum=9223372036854775807 |
| salary_max | да | integer; minimum=1; maximum=9223372036854775807 |
| work_format | да | string; minLength=1; enum=remote, office, hybrid |
| next_step | нет | string; minLength=1; maxLength=200 |
| recruiter | нет | integer; minimum=1; maximum=9223372036854775807 / null / '' |

Вариант 4:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| kind | да | 'need.update' |
| target_id | да | integer; minimum=1; maximum=9223372036854775807 |
| payload | да | object |

Поля payload:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| title | нет | string; minLength=1; maxLength=120 |
| grade | нет | string; minLength=1; enum=Junior, Middle |
| skills | нет | string; maxLength=200 |
| tasks | нет | string; minLength=1; maxLength=1500 |
| salary_min | нет | integer; minimum=1; maximum=9223372036854775807 |
| salary_max | нет | integer; minimum=1; maximum=9223372036854775807 |
| work_format | нет | string; minLength=1; enum=remote, office, hybrid |
| next_step | нет | string; minLength=1; maxLength=200 |
| recruiter | нет | integer; minimum=1; maximum=9223372036854775807 / null / '' |

Вариант 5:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| kind | да | 'invitation.send' |
| target_id | да | integer; minimum=1; maximum=9223372036854775807 |
| payload | да | object |

Поля payload:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| candidate_id | да | integer; minimum=1; maximum=9223372036854775807 |
| accepted_attempts | нет | array[integer; minimum=1; maximum=9223372036854775807]; maxItems=20 |
| discussion | нет | string; maxLength=2000 |

Вариант 6:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| kind | да | 'profile.publish' |
| target_id | нет | integer; minimum=1; maximum=9223372036854775807 / null |
| payload | нет | object |

Вариант 7:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| kind | да | 'profile.unpublish' |
| target_id | нет | integer; minimum=1; maximum=9223372036854775807 / null |
| payload | нет | object |

Вариант 8:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| kind | да | 'invitation.accept' |
| target_id | да | integer; minimum=1; maximum=9223372036854775807 |
| payload | нет | object |

Вариант 9:

| Поле | Обязательно | Тип / границы |
| --- | --- | --- |
| kind | да | 'invitation.decline' |
| target_id | да | integer; minimum=1; maximum=9223372036854775807 |
| payload | нет | object |

## Источники формата

Формат закреплён по [OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html); документ проверяет [openapi-spec-validator](https://openapi-spec-validator.readthedocs.io/en/latest/python.html), установленный только в dev группе lock. Production deploy использует --no-dev. Это описание нашего браузерного HTTP, не официального API ФСП.
