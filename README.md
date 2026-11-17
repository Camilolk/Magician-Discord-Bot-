# 🪄 Magician Discord Bot

Bot de Discord en Python para explorar metadatos de novelas web y ligeras indexadas desde Telegram, con SQLite y discord.py.

## Funciones actuales

- `m!ping`: comprobar conexión.
- `m!buscar título`: búsqueda aproximada y paginada.
- `m!recientes`: últimos documentos indexados.
- `m!biblioteca`: explorar documentos.
- `m!catalogo`: agrupación heurística por nombre de archivo y menú de selección.
- `m!novela título`: buscar archivos con números de volumen reconocibles.
- `m!estadisticas`: documentos y canales registrados.
- `m!ayuda`: mostrar comandos.

**Importante:** el catálogo de Discord usa la tabla local `novels` de `magician.db`, agrupada por nombres de archivos. Los informes `story_preview.json`, `story_assisted_review.json` y otros son herramientas de análisis separadas; sus correcciones todavía no se aplican al catálogo.

## Inicio local (Windows PowerShell)

1. Crear un entorno virtual si todavía no existe: `py -m venv .venv`.
2. Instalar dependencias: `.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt`.
3. Crear `.env` desde `.env.example` y configurar `DISCORD_TOKEN` (nunca publicarlo).
4. Indexar mensajes con `telegram_indexer.py` si la base de datos todavía está vacía; necesita acceso autorizado a Telegram y su propia configuración.
5. Iniciar el bot: `.\\.venv\\Scripts\\python.exe main.py`.
6. En Discord, probar `m!ping`, `m!estadisticas`, `m!buscar` y `m!catalogo`.

Los comandos con prefijo requieren habilitar **Message Content Intent** en el portal de desarrolladores de Discord, además de activarlo en el código.

## Seguridad y límites

No publicar `.env`, sesiones de Telegram, `magician.db` ni informes locales. El bot solo indexa metadatos y puede mostrar enlaces a publicaciones públicas; no descarga ni redistribuye archivos. Una publicación accesible no implica permiso de redistribución.

El bot debe permanecer ejecutándose para responder; Codespaces no garantiza alojamiento 24/7.
