# 🪄 Magician Discord Bot

Bot de Discord para consultar un catálogo de novelas web y ligeras. Proyecto en Python.

## Estado
Primera versión: comandos `/ping`, `/buscar` y `/recientes` con SQLite. La sincronización de Telegram se implementará en una fase posterior. **No descarga ni redistribuye PDFs todavía.**

## Configuración desde GitHub Codespaces
1. Abre el repositorio en Codespaces.
2. Ejecuta `pip install -r requirements.txt`.
3. Configura `DISCORD_TOKEN` como secreto de Codespaces (no lo publiques). Opcionalmente configura `DISCORD_GUILD_ID` para sincronizar comandos rápidamente en tu servidor de pruebas.
4. Ejecuta `python main.py`.
5. Invita el bot con los scopes `bot` y `applications.commands` y permiso para enviar mensajes.

También puedes copiar `.env.example` a `.env` para pruebas locales, sin subir ese archivo a GitHub.

## Seguridad y derechos
Nunca publiques tokens, secretos ni archivos de sesión de Telegram. La disponibilidad pública de un PDF no implica permiso para redistribuirlo. Magician puede indexar metadatos y enlazar publicaciones accesibles; la entrega de archivos requerirá autorización.

## Próximas fases
- Indexador de historial de Telegram con Telethon y control de duplicados.
- Búsqueda aproximada y paginación.
- Entrega de archivos con licencia o permiso de redistribución.
- Alojamiento permanente: Codespaces no es hosting 24/7.
