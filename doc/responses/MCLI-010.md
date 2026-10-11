# MCLI-010 — подтверждение в браузере

Session-only /drafts, CSRF, явная acknowledge; publication consent отдельный checkbox.
Owner видит текущее состояние и immutable payload; employer invitation preview без контактов кандидата.
Atomically recheck actor/consent/role/target/fingerprint/expiry; применить один раз, повтор возвращает результат.
Применение через существующие invite/decide сохраняет snapshot, ограничения и accepted grant.
Проверка: 14 API/browser тестов — PASS (3.587 s), включая bearer без session, CSRF, ack,
stale/expiry/cancel/foreign/consent, публикацию, компанию/need/invite/accept и повтор.
