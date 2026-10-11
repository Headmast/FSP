# MCLI-006 — CLI пакет

Отдельный fsp-client 0.1.0, Python 3.13, HTTPX, keyring, argparse; uv.lock независим.
МCP SDK фактически разрешён в mcp==2.3.0 (публичная документация проверена).
4 теста — PASS: routes/JSON/exit codes, redirect rejection, protected storage, config без секрета.
Wheel и sdist собраны в .runtime/client-v1; macOS build PASS, Linux execution NOT_RUN на этапе.
