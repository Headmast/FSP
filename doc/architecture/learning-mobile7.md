# Учебный модуль mobile7

Задачи MOBILE7-001 и MOBILE7-002. Ветка mobile7 основана на main b78a89b. Владелец — чат разработки модуля. Это расширение существующего Django MVP: учебные треки iOS, Android, Flutter и ОС Аврора доступны кандидату после подтверждения demo email и согласия на обработку. Подтверждение категории использует существующий экзамен iOS; другие треки дают учебный результат.

## Сценарий

Кандидат выбирает трек и Junior/Middle, изучает одну из четырёх тем и отмечает урок изученным. Каждый трек содержит восемь уроков и 32 вопроса: всего 32 урока и 128 вопросов. Урок содержит объяснения, пример, список для проверки понимания и официальный источник.

| Трек | Стек | Темы | Версия контента |
|---|---|---|---|
| iOS | Swift / SwiftUI | Swift, ARC, Async, UI/Data | ios-learning-1 |
| Android | Kotlin / Jetpack Compose | Kotlin, Compose/Lifecycle, Coroutines, Данные/Тесты | android-learning-1 |
| Flutter | Dart / Widgets | Dart, Widgets/Layout, State/Async, Архитектура/Тесты | flutter-learning-1 |
| Аврора | C++ / Qt / QML | C++/Qt, QML/UI, Модели/Async, SDK/Пакеты | aurora-learning-1 |

Выбранный трек запоминается в Django session. Прогресс, рекомендации, история и активная практика на маршруте относятся к выбранному треку; отметки уроков дополнительно разделены по уровню и версии. Ссылки на урок, возврат с паузы и разбор сохраняют трек. Старые /learning/lessons/... и POST старта без track сохраняют поведение iOS.

Самопроверка по всем темам содержит восемь вопросов, по два на область. Практика одной темы содержит четыре вопроса. Каждый независимый банк содержит 32 вопроса (16 на уровень). Порядок вариантов перемешивается; правильный индекс меняется вместе с ним. В учебном банке нет вопросов или ID экзаменационного банка.

Вопросы показываются по одному. Сохранение переносит к первому вопросу без ответа. Кнопка «Сохранить и сделать паузу» записывает текущий выбор и возвращает к маршруту. Переход по номерам и обычным ссылкам сам по себе не сохраняет новый выбор; это объяснено на экране. Сохранённые ответы можно изменить до завершения. Нет таймера или задержки между учебными попытками.

Завершение считает неотвеченные вопросы ошибками, показывает балл, результат по темам, выбранный и правильный ответ, объяснение и ссылки на уроки. Повтор ошибок создаёт новую попытку из неверных и пропущенных вопросов выбранного завершённого результата. Если ошибок нет, повтор не создаётся. На маршруте выводятся слабые области последней общей самопроверки выбранного уровня и последние 20 результатов выбранного трека.

## Данные и границы

LessonProgress хранит кандидата, трек, уровень, тему, версию контента и время отметки. Уникальное ограничение исключает повторную запись одного урока одной версии в треке и уровне. Отметка означает самостоятельное подтверждение изучения, а не проверку квалификации.

PracticeSession хранит собственный снимок вопросов и вариантов, ответы, версию, режим check/review, трек, уровень, тему, время и результат по областям. У кандидата одна активная учебная попытка на трек: можно параллельно готовиться в четырёх направлениях. При повторном старте внутри того же трека возвращается существующая; перед началом другой в этом треке её нужно завершить. Уникальное ограничение в базе использует candidate + track. При возобновлении существующей попытки это сообщается в интерфейсе. Снимок не меняется при обновлении банка; повтор ошибок использует трек, уровень, версию и снимок принадлежащего кандидату завершённого источника. Подмена track/grade клиентом не переносит вопросы между платформами.

Учебный сервис не записывает confirmed_grade, test_score, grade_changed_at, достижения или публикацию профиля. Свидетельства iOS выдаются только существующим модулем assessments. В Android, Flutter и Авроре карточка и результат не предлагают подтверждение категории своей платформы. Подбор кандидатов и native приложение этим расширением не изменяются. Правила экзамена остаются прежними: 8 вопросов, 15 минут, минимум 6 правильных и минимум один в каждой области, серверный срок и ограничения повторов.

Все попытки и прогресс приватны для владельца; у работодателя нет доступа. Мутации выполняются POST с CSRF. Чужой источник повторения или попытка возвращает 404. Некорректные ID, вопросы и варианты отклоняются. В активном учебном HTML отсутствуют правильные индексы и объяснения. Серверные транзакции и ограничения защищают от дубликатов и потери ответов при одновременных запросах.

Пока действует активная экзаменационная попытка, уроки, старт/продолжение практики, отметки и разборы всех треков заблокированы. Истёкшая или завершённая экзаменационная попытка не блокирует обучение. Учебные данные сохраняются и доступны после экзамена.

HTML работает без JavaScript. Семантические формы, radio/fieldset/legend, подписи, видимый фокус, aria-current и текст статуса поддерживают клавиатуру и средства чтения. Локальная браузерная проверка не является сертификацией VoiceOver.

## Источники учебных материалов

Материалы написаны для этого модуля; технические правила сверены с первичными источниками:

- [Основы Swift](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/thebasics/)
- [Протоколы Swift](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/protocols/)
- [ARC](https://github.com/swiftlang/swift-book/blob/main/TSPL.docc/LanguageGuide/AutomaticReferenceCounting.md)
- [Concurrency](https://github.com/swiftlang/swift-book/blob/main/TSPL.docc/LanguageGuide/Concurrency.md)
- [State](https://developer.apple.com/documentation/swiftui/state)
- [StateObject](https://developer.apple.com/documentation/swiftui/stateobject)

Источники новых треков сверены 11.10.2026. Примеры — учебные фрагменты; набор модулей Qt, разрешений и архитектуру RPM следует выбирать по целевому SDK Авроры. Версионная документация Авроры 4.0.1 использована для базового C++/QML контракта, текущая документация — для состава проекта и подключения API.

- Android: [Kotlin null safety](https://kotlinlang.org/docs/null-safety.html), [data classes](https://kotlinlang.org/docs/data-classes.html), [coroutines](https://kotlinlang.org/docs/coroutines-basics.html), [обработка ошибок](https://kotlinlang.org/docs/exception-handling.html), [Compose state](https://developer.android.com/develop/ui/compose/state), [state hoisting](https://developer.android.com/develop/ui/compose/state-hoisting), [эффекты](https://developer.android.com/develop/ui/compose/side-effects), [data layer](https://developer.android.com/topic/architecture/data-layer), [coroutine tests](https://developer.android.com/kotlin/coroutines/test).
- Flutter: [Dart null safety](https://dart.dev/null-safety/understanding-null-safety), [class modifiers](https://dart.dev/language/class-modifiers), [concurrency](https://dart.dev/language/concurrency), [constraints](https://docs.flutter.dev/ui/layout/constraints), [performance](https://docs.flutter.dev/perf/best-practices), [mounted](https://api.flutter.dev/flutter/widgets/BuildContext/mounted.html), [State](https://api.flutter.dev/flutter/widgets/State-class.html), [widget tests](https://docs.flutter.dev/cookbook/testing/widget/introduction), [виды тестов](https://docs.flutter.dev/testing/overview).
- Аврора: [Qt в платформе](https://developer.auroraos.ru/doc/platform/architecture/qt), [первое приложение](https://developer.auroraos.ru/doc/software_development/first_experience/first_app_code), [зависимости и Permissions](https://developer.auroraos.ru/doc/software_development/reference/public_api/dependency_connection), [C++/QML](https://developer.auroraos.ru/doc/4.0.1/software_development/guides/qml/cpp_qml_integration), [QObject](https://doc.qt.io/qt-5/qobject.html), [property binding](https://doc.qt.io/qt-5/qtqml-syntax-propertybinding.html), [QAbstractListModel](https://doc.qt.io/qt-5/qabstractlistmodel.html), [сеть](https://doc.qt.io/archives/qt-5.15/qnetworkaccessmanager.html).

## Запуск и интеграция

В checkout mobile7: uv sync --locked, uv run python app/manage.py migrate, uv run python app/manage.py collectstatic --noinput, uv run python scripts/run_app.py. Адрес — http://127.0.0.1:8057/learning/. Войти своим demo кандидатом или зарегистрировать новый адрес @demo.invalid и подтвердить показанное demo письмо.

Новых зависимостей и изменений settings нет. Требуются миграции assessments/0003 и 0004. Миграция 0004 добавляет track с default=ios и расширяет уникальные ограничения. Старые снимки, ответы, версии, результаты и даты не пересоздаются; это проверено на данных схемы 0003. Откат кода и схемы после появления активных попыток нескольких треков требует отдельного плана: прежняя схема допускает только одну активную попытку кандидата. Перед интеграцией согласовать общий urls.py и base.html с изменениями других чатов, затем повторить затронутые проверки. Состояние ветки не означает публикацию текущего production MVP.

[HTTP контракты](../api/learning-mobile7.md), [QA треков](../qa/learning-tracks-mobile7.md), [исходная QA](../qa/learning-mobile7.md), [рабочий промпт](../prompts/MOBILE7-001-learning.md).

[Поручение новых треков](../prompts/MOBILE7-002-tracks.md), [результат](../responses/MOBILE7-002-tracks.md).
