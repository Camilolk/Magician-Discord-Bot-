# Magician 2.0 — Biblioteca interactiva

## Requisitos
- Python y dependencias de `requirements.txt`
- `.env` local con `DISCORD_TOKEN`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`
- Sesión de Telethon autenticada localmente. Nunca subas archivos `*.session`.

## Indexar Telegram
```powershell
.\.venv\Scripts\python.exe telegram_indexer.py --limit 100
```
Usa `--limit 0` para revisar el historial completo accesible. El proceso registra títulos y referencias de mensajes, no descarga archivos. Solo cataloga documentos para los que tengas autorización.

## Iniciar bot
```powershell
.\.venv\Scripts\python.exe main.py
```

## Comandos
- `m!ping`: conexión
- `m!buscar Azure Sword`: búsqueda aproximada
- `m!recientes`: últimos títulos
- `m!biblioteca`: catálogo paginado
- `m!ayuda`: ayuda

Los botones de navegación solo responden a quien inició la búsqueda y caducan después de 3 minutos. La búsqueda examina hasta 5000 registros y devuelve hasta 100 coincidencias, por lo que los catálogos mayores requerirán una optimización posterior.

## Limitaciones
- La indexación todavía es manual.
- El bot usa SQLite local: no compartas `magician.db` ni archivos de sesión.
- Los enlaces privados de Telegram no se publican automáticamente.
- Esta versión no descarga ni distribuye PDF.
