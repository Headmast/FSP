# MCLI-007 — MCP stdio

Официальный MCPServer, purpose=mcp, role-specific tools, structured output и input bounds.
Нет generic HTTP/SQL/shell/contacts инструмента. SDK проверяет schema до API call.
Проверка: 6 клиентских тестов — PASS, включая official Client in-process для обеих ролей,
output schemas, annotations, отказ CLI credentials и invalid ID. Subprocess проверяется в MCLI-008.
