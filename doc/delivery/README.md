# Комплект сдачи текущего MVP

**Кратко:** руководство, карта требований, восемь актуальных слайдов и две записи доступны из этого clone без сети. Материалы показывают реализованный Django MVP на коде `34942b5`; исходная концептуальная презентация сохраняется отдельно.

| Материал | Файл |
| --- | --- |
| Техническое руководство, карта и индекс всех HTTP маршрутов — 9 страниц | [PDF](mvp-handbook.pdf) · [Markdown](current-mvp.md) |
| Карта требований с доказательствами и границами моков | [requirements-coverage.md](requirements-coverage.md) |
| Восемь слайдов текущего демо | [HTML](current-mvp-slides.html) · [редактируемый PPTX](current-mvp.pptx) · [PDF](current-mvp-slides.pdf) |
| Текст и заметки для выступления | [current-mvp-slides.md](current-mvp-slides.md) |
| Основной путь, проверка приватности и дополнительные экраны — реальный Chromium/Django | [current-demo.mp4](assets/current-demo.mp4) |
| Полная автоматизированная репетиция, 4:28 | [timed-rehearsal.mp4](assets/timed-rehearsal.mp4) |
| Порядок показа и fallback без сети | [demo-script.md](demo-script.md) |
| Версия, размер и SHA-256 всех файлов | [package-manifest.json](package-manifest.json) |

Речь репетиции синтезирована локально голосом Milena; браузерная часть записана с реальными запросами к чистому Django worktree и вымышленными данными. Применён рабочий 10-минутный лимит существующей презентации; это не утверждение об официальном тайминге организаторов. Человеческое выступление, пилот и ручной экранный диктор отдельно не проверены.

Стек демо: Python 3.13 / Django 5.2 / SQLite / Gunicorn / uv lock. Экзамен — iOS/Swift Junior/Middle; четыре платформы есть как учебные треки. AI/FSP/email/мессенджеры — моки или демонстрационные состояния. Имя опубликованного кандидата видно; контакты адресно закрыты. [Полный HTTP контракт](../api/contracts.md), [OpenAPI](../api/openapi.json), [примеры](../api/examples.md), [исходное ТЗ](../sources/materials/fsp-specification.pdf), [письменные уточнения](../sources/materials/fsp-written-answers.xlsx).

## Проверка и воспроизведение

Для чтения и показа достаточно файлов clone, браузера/PDF/PPTX/MP4 просмотрщика. PDF слайдов — визуальная копия; редактируемый источник — PPTX, текст — Markdown. Основной PDF содержит выделяемый текст.

```sh
uv sync --locked
uv run python scripts/check_delivery.py
python3 scripts/check_docs.py
```

Для полной проверки видео нужен FFmpeg/ffprobe. Python PDF parser pypdf закреплён в dev-группе lock; production ставится с `--no-dev`. Сборка руководства: `uv run python scripts/build_delivery_pdf.py`.

Запись собственного демо: `python3 scripts/record_delivery.py --ref <SHA> --node <путь-к-Node> --output .runtime/qa/delivery-record`. Playwright должен быть установлен в указанном Node runtime (NODE_PATH). Проверка создаёт отдельный Git clone/worktree, новую БД, фикстуры и сервер; после записи убирает временный checkout и процесс. Запись не обращается к production.

Презентация создаётся `scripts/build_delivery_slides.mjs` с @oai/artifact-tool и валидаторами скилла Presentations. Пути FSP_DELIVERY_ROOT, FSP_PRESENTATION_SKILL, FSP_RUNTIME_PYTHON и RUNTIME_NODE/RUNTIME_NODE_MODULES задаёт авторская среда; копию mjs запускать из приватного build каталога с node_modules этой среды. Для финального среза FSP_DELIVERY_SCREENSHOTS указывает директорию успешной записи. Эта среда нужна только для пересборки PPTX, не для чтения/демо из clone.

Репетиция: `python3 scripts/build_delivery_rehearsal.py --limit-seconds 600 --playback-check`; нужна macOS Milena и FFmpeg, восьмистраничные PNG из авторской сборки. Скрипт измеряет созданную запись, декодирует её и затем действительно проигрывает поток в реальном времени. Альтернативный регламент задаётся явно.

[Запуск приложения](../development/local-run.md), [worktrees](../development/worktrees.md), [runbook](../deployment/runbook.md), [протокол DEL-001](../responses/DEL-001-package.md). Короткий SHA материалов относится к исходникам приложения; итоговый commit комплекта фиксируется evidence отдельно. Неизменность кода между срезами проверяется, разные SHA документации не скрываются.
