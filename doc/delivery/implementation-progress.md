# Прогресс выполнения 27 задач

**Кратко:** 10 задач реализованы локально, 17 остаются открытыми. Полный MVP и расширенная цель не завершены. Публичный checkpoint на момент этой записи — ba3d270 (FIX-001 и OPS-002); остальные изменения требуют нового выпуска и проверки на сервере.

Ветка: mvp/implementation, worktree ../FSP-worktrees/implementation, порт 8041, исходный SHA a6280ea. Изолированы DB/runtime; серверная БД не использовалась в локальных тестах. [Полный список с приёмкой](../plan/remaining-work.md), [backlog](../plan/backlog.md), [исторический аудит](../qa/scope-audit.md).

## Успешные этапы и коммиты

| SHA | Этап |
|---|---|
| 0982d51 | fix: reject malformed identifiers before database lookups (FIX-001) |
| ba3d270 | fix: require database and rendered entry readiness in watchdog (OPS-002) |
| 090dbe8 | docs: record deployed readiness checkpoint (OPS-002) |
| 94f3e14 | fix: canonicalize skill aliases across profiles and matching (FIX-002) |
| a87362a | feat: complete candidate profile and consent-aware resume (MVP-006) |
| 16a49e2 | feat: add company profile and require invitation contact (MVP-007) |
| b71bae5 | feat: require explicit versioned processing and publication consent (MVP-008) |
| 5e1febf | feat: add consented mock FSP identity and achievements (MVP-009) |
| b964b2c | feat: snapshot assessment witnesses accepted for each invitation (MVP-010) |
| 6fc36fc | feat: explain declared matches gaps and unknown evidence (MVP-011) |
| 1707eb5 | fix: distribute assessment variants across new candidates (MVP-012) |

Каждый функциональный этап имеет отдельные prompt/response, evidence с базовым SHA и хешами проверенного кода. Ссылка на response стоит рядом с соответствующим пунктом списка. Исторический FAIL исходного аудита сохранён, новым PASS он не подменяется.

## Остаётся реализовать и проверить

1. QA-001: независимые синтетические ответы/эталоны, test–retest и сравнение A/B; метод и пороги фиксируются до запуска.
2. MVP-013, AI-001: черновик до создания потребности, редактирование и применение после подтверждения; помощь подбору/приглашению/разговору на явно отмеченных моках.
3. DOC-003, DEL-001: полные HTTP контракты/OpenAPI, актуальные материалы сдачи, PDF/презентация/резервное демо в clone и репетиция.
4. OPS-003, OPS-004: доказательство reboot, постоянный endpoint, автозапуск/backup/restore и выпуск.
5. INT-001–003: SMTP, ФСП, Yandex — нужны живые доступы и согласованный контракт; отсутствие ключей не означает выполнение.
6. PROD-001–005: условия кандидата, адресное задание, этапы/уведомления, удаление/отзыв гранта, компании/жалобы/споры.
7. QA-002: фактический пилот полезности с людьми. FUT-001: вакансии/отклики, чат, ATS, новые роли, кодовая песочница, прокторинг и автономные агенты — отдельная декомпозиция внутри расширенной цели.

## Проверки и ограничения

Целевые тесты и результаты каждого этапа приведены в response/evidence. После объединения повторяются весь набор приложения, tools/worktree tests, docs и переносимый запуск. C1–C6 не объявлены PASS по сумме локальных тестов: черновики/валидация/комплект/живые интеграции/эксплуатация ещё не закрыты.

Перед публикацией миграций согласий: резервная копия DB; прежние аккаунты проходят processing-v1, прежние профили заново разрешают publication-v1. Миграция не выдумывает согласия, seed не меняет существующие аккаунты. Отзыв старого принятого гранта пока входит в PROD-004.
