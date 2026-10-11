# MCLI-002 — общий доступ

hiring.access содержит queries без get_or_create и update, доступ профиля/need/invitation/proof.
HTML proof и карточки используют те же правила; старый web inbox сохраняет viewed_at.
Проверка: 90 Django тестов accounts/profiles/assessments/hiring/assistant — PASS (20.773 s),
collectstatic, check_docs, diff --check. Функциональные API проверки добавляются MCLI-004/005.
