# Magician — despliegue en Oracle Cloud Always Free

Esta configuración **no crea automáticamente una cuenta ni una VM**. Requiere una VM Ubuntu Always Free con Docker Engine y Docker Compose plugin instalados, y Git. Selecciona únicamente recursos etiquetados **Always Free**. Oracle puede requerir verificación de pago y puede no tener capacidad en la región.

## 1. Preparar la VM (una sola vez)

Conéctate por SSH a tu VM Ubuntu. Instala Docker Engine y el plugin Compose siguiendo la guía oficial de Docker para Ubuntu: https://docs.docker.com/engine/install/ubuntu/ . Instala Git con `sudo apt update && sudo apt install -y git`.

Clona el repositorio en el HOME del usuario SSH:

```bash
git clone https://github.com/Camilolk/Magician-Discord-Bot-.git
cd Magician-Discord-Bot-
```

Crea un archivo privado `.env` en la VM (no en GitHub) con `DISCORD_TOKEN=TU_TOKEN`. Limita permisos con `chmod 600 .env`. Nunca publiques su contenido.

Para iniciar el bot:

```bash
docker compose up --build -d
docker compose logs --tail=50 magician
```

La base de datos SQLite vive en el volumen persistente `magician_data`. No uses `docker compose down -v` si quieres conservar el catálogo.

**Importante:** detén la instancia antigua de Codespaces cuando la VM esté funcionando; no mantengas dos procesos conectados con el mismo token.

## 2. Activar despliegue automático (una sola vez)

Crea una clave SSH de despliegue independiente y autoriza su clave **pública** en `~/.ssh/authorized_keys` del usuario de la VM. Mantén la clave privada únicamente en GitHub Actions Secrets.

En GitHub → Settings → Environments crea `production`. En sus secretos configura:

- `ORACLE_HOST`: IP pública o DNS de la VM
- `ORACLE_USER`: usuario SSH de la VM (normalmente `ubuntu`)
- `ORACLE_SSH_KEY`: clave SSH privada de despliegue
- `ORACLE_SSH_KNOWN_HOSTS`: línea verificada de host SSH (por ejemplo, salida de `ssh-keyscan` **después de contrastar la huella digital** con la VM)

La VM debe aceptar SSH desde el runner de GitHub. Restringe la exposición de SSH siempre que sea posible y considera un runner propio o mecanismo de despliegue por extracción para evitar abrir SSH ampliamente.

En GitHub → Actions → **Deploy Magician to Oracle VM** → Run workflow puedes desplegar manualmente. Una comprobación exitosa de la rama `main` también dispara el despliegue.

## 3. Comprobación

```bash
docker compose ps
docker compose logs --tail=100 magician
```

Verifica `m!ping` en Discord. El flujo de Actions no demuestra por sí solo que Discord esté conectado: comprueba los logs y el comando.

## Límites

Codespaces y los secretos de Codespaces son independientes de Oracle. La VM debe tener su propio `.env`. GitHub Actions no mantiene el bot ejecutándose: solo despliega. El volumen Docker persiste mientras la VM y su disco sobrevivan; haz copias de seguridad. Oracle puede recuperar recursos gratuitos inactivos y puede haber indisponibilidad de capacidad.
