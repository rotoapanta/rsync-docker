RSYNC-DOCKER: Sincronización Automática de Datos con Raspberry Pi

Este proyecto proporciona una solución basada en Docker para sincronizar automáticamente datos desde una Raspberry Pi a una máquina local utilizando rsync y cron. Es ideal para escenarios donde necesitas recolectar datos generados por una Raspberry Pi (por ejemplo, de sensores, logs, o archivos de cámara) y tenerlos centralizados en tu sistema principal.

Características

    Sincronización Unidireccional: Diseñado específicamente para sincronizar datos desde la Raspberry Pi hacia tu máquina local.
    Automatización con Cron: Las sincronizaciones se ejecutan automáticamente a intervalos definidos (por defecto, cada 5 minutos).
    Dockerizado: Fácil de desplegar y aislar del resto de tu sistema gracias a Docker.
    Notificaciones de Telegram: Recibe alertas en tiempo real sobre el estado de la sincronización (éxito, fallo, con/sin cambios).
    Logs Detallados: Genera logs específicos para la sincronización y el cron para una fácil depuración.


    # 📦 rsync-docker

Sincronización automatizada de archivos desde Raspberry Pi hacia un servidor, utilizando Docker, `rsync`, `cron`, y notificaciones por Telegram. Ideal para respaldos periódicos o recolección de datos desde sensores remotos.

---

## 🚀 Características

- 🔁 Sincronización unidireccional con `rsync`
- ⏱️ Ejecución automática mediante `cron`
- 📩 Alertas de éxito o fallo vía Telegram
- 🐳 Totalmente contenido en Docker
- 📂 Montaje de volúmenes persistentes (`data/` y `logs/`)
- 🔐 Comunicación segura por clave SSH

---

## 📁 Estructura del proyecto

RSYNC-DOCKER/
├── .env                  # Variables de entorno (IGNORADO por Git)
├── .gitignore            # Archivos y carpetas a ignorar por Git
├── crontab.txt           # Configuración de los jobs de cron
├── Dockerfile            # Define la imagen Docker del servicio
├── docker-compose.yml    # Define el servicio Docker y sus volúmenes
├── main.py               # Punto de entrada principal para ejecutar la sincronización
├── run_sync.sh           # Script wrapper para ejecutar la sincronización desde cron
├── start.sh              # Script inicial que se ejecuta al iniciar el contenedor
├── start_host.sh         # (Opcional) Script para ejecutar commands específicos al host
├── logs/                 # Directorio para los archivos de log (IGNORADO por Git)
│   ├── cron.log
│   ├── from_pi.log
│   └── startup.log
├── data/                 # Directorio donde se guardan los datos sincronizados (IGNORADO por Git)
└── managers/
    └── sync_manager.py   # Lógica principal para ejecutar Rsync y manejar notificaciones
└── utils/
    └── telegram_utils.py # Funciones de utilidad para enviar mensajes a Telegram


---

## ⚙️ Configuración

1. Clona el repositorio:

```bash
$ git clone https://github.com/rotoapanta/rsync-docker.git
```
```bash
$ cd rsync-docker
```

Crea y edita el archivo .env:

# Token del bot de Telegram
TELEGRAM_BOT_TOKEN=TU_TOKEN

# ID del chat o grupo de Telegram
TELEGRAM_CHAT_ID=TU_CHAT_ID

# Ruta de origen en la Raspberry Pi
RSYNC_FROM=pi@192.168.1.100:/home/pi/Documents/mis-datos

# Ruta de destino en el contenedor (no cambiar si usas /data montado)
RSYNC_TO=/data

3. Asegúrate de haber copiado tu clave pública SSH a la Raspberry Pi:

ssh-copy-id -i ~/.ssh/id_rsa_rsync.pub pi@192.168.1.100

4. Construye y ejecuta el contenedor:

./start_host.sh

🧪 Prueba manual

Ejecuta una sincronización inmediata:

docker exec -it rsync_docker /app/run_sync.sh from

📬 Notificaciones

Recibirás notificaciones en Telegram si:

    ✅ La sincronización fue exitosa

    ❌ Ocurrió un error o fallo
