# RSYNC-DOCKER: Automated Data Sync from Raspberry Pi

![Bash](https://img.shields.io/badge/bash-v4.4-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue)
![GitHub issues](https://img.shields.io/github/issues/rotoapanta/rsync-docker)
![Last Commit](https://img.shields.io/github/last-commit/rotoapanta/rsync-docker)
![License](https://img.shields.io/github/license/rotoapanta/rsync-docker)
![GitHub repo size](https://img.shields.io/github/repo-size/rotoapanta/rsync-docker)
![Supported Platforms](https://img.shields.io/badge/platform-Linux%20|%20macOS-green)

## Overview

This project provides a Docker-based solution to automatically synchronize data from a Raspberry Pi to a central host using `rsync` and `cron`. It is ideal for scenarios such as collecting data from sensors, logs, or camera files on remote Raspberry Pi devices and keeping them centralized and backed up.

---
## Features

- 🔁 One-way file synchronization from Raspberry Pi to host
- ⏱️ Scheduled tasks using `cron` inside Docker
- 📩 Notifications via Telegram on success or failure
- 🐳 Full Docker support for easy deployment and portability
- 🔐 Secure SSH authentication using private key
- 📂 Log and data volume separation for safe persistence

## Project Structure

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


RSYNC-DOCKER/
├── .env # Variables de entorno (IGNORADO por Git)
├── .gitignore # Archivos y carpetas a ignorar por Git
├── crontab.txt # Configuración de los jobs de cron
├── Dockerfile # Define la imagen Docker del servicio
├── docker-compose.yml # Define el servicio Docker y sus volúmenes
├── main.py # Punto de entrada principal para ejecutar la sincronización
├── run_sync.sh # Script wrapper para ejecutar la sincronización desde cron
├── start.sh # Script inicial que se ejecuta al iniciar el contenedor
├── start_host.sh # (Opcional) Script para ejecutar commands específicos al host
├── logs/ # Directorio para los archivos de log (IGNORADO por Git)
│ ├── cron.log
│ ├── from_pi.log
│ └── startup.log
├── data/ # Directorio donde se guardan los datos sincronizados (IGNORADO por Git)
├── managers/
│ └── sync_manager.py # Lógica principal para ejecutar Rsync y manejar notificaciones
└── utils/
└── telegram_utils.py # Funciones de utilidad para enviar mensajes a Telegram

---

## Configuration

1. **Clone the repository**:

```bash
$ git clone https://github.com/rotoapanta/rsync-docker.git
```
```bash
$ cd rsync-docker
```

2. **Create and edit your `.env` file**:

Create a `.env` file in the root of the project with the following environment variables:

```env
# Telegram bot token
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Telegram chat ID (user or group)
TELEGRAM_CHAT_ID=your_chat_id_here

# Source path on the Raspberry Pi
RSYNC_FROM=pi@192.168.1.100:/home/pi/Documents/my-data

# Destination path inside the container (keep as /data if using Docker volume)
RSYNC_TO=/data



3. Ensure your SSH key is installed on the Raspberry Pi:

```bash
ssh-copy-id -i ~/.ssh/id_rsa_rsync.pub pi@192.168.1.100
```
4. Construye y ejecuta el contenedor:

```bash
./start_host.sh
```

🧪 Prueba manual

Ejecuta una sincronización inmediata:

docker exec -it rsync_docker /app/run_sync.sh from

📬 Notificaciones

Recibirás notificaciones en Telegram si:

    ✅ La sincronización fue exitosa

    ❌ Ocurrió un error o fallo
