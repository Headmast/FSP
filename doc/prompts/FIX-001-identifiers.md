# FIX-001 — безопасный разбор ID

Дата: 2026-10-11. Владелец: интегратор. Ветка: mvp/implementation; база a6280ea. Область: accounts/identifiers.py, hiring/assistant views и тесты.

Убрать воспроизведённые HTTP 500 на Unicode ID. Ограничить ID положительным ASCII числом диапазона SQLite; сохранить default для необязательного пустого ID и проверки владельца. Приёмка: ID-01–03 из [списка](../plan/remaining-work.md).
