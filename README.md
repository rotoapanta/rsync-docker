# <p align="center">RSYNC-DOCKER: Automated Data Sync from Raspberry Pi

<p align="center">This project aims to automatically synchronize data from a Raspberry Pi using Docker and Rsync, with optional Telegram notifications.</p>

##

![Bash](https://img.shields.io/badge/bash-v4.4-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue)
![GitHub issues](https://img.shields.io/github/issues/rotoapanta/rsync-docker)
![Last Commit](https://img.shields.io/github/last-commit/rotoapanta/rsync-docker)
![GPLv3](https://img.shields.io/badge/license-GPLv3-blue.svg)
![GitHub repo size](https://img.shields.io/github/repo-size/rotoapanta/rsync-docker)
![Supported Platforms](https://img.shields.io/badge/platform-Linux%20|%20macOS-green)
[![Docker](https://img.shields.io/badge/Docker-Yes-brightgreen)](https://www.docker.com/)

# Contents

- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Configuration](#configuration)
  - [Clone the Repository](#1-clone-the-repository)
  - [Edit `.env` File](#2-create-and-edit-your-env-file)
  - [Set Up SSH Access](#3-set-up-ssh-access-to-raspberry-pi)
  - [Build and Run](#4-build-and-run-the-container)
- [Usage](#usage)
  - [Manual Test](#manual-test)
- [Cron Schedule](#cron-schedule)
- [Notifications](#notifications)
- [Feedback](#feedback)
- [Support](#support)
- [License](#license)
- [Authors](#authors)
- [More Info](#more-info)
- [Links](#links)

# Getting started

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

```plaintext
rsync-docker/
├── .env                  # Environment variables (not committed to Git)
├── .gitignore            # Files and folders ignored by Git
├── crontab.txt           # Cron job configuration
├── Dockerfile            # Docker image for the sync container
├── docker-compose.yml    # Docker service and volume orchestration
├── main.py               # Main entry point for manual sync execution
├── run_sync.sh           # Script called by cron to perform sync
├── start.sh              # Startup script inside the container
├── start_host.sh         # Helper script to build and run from the host
├── logs/                 # Folder for sync and error logs
│   ├── cron.log          # Cron activity log
│   ├── from_pi.log       # Sync log from Raspberry Pi
│   └── startup.log       # Initial diagnostics log
├── data/                 # Destination folder for synced files (mounted volume)
├── managers/
│   └── sync_manager.py   # Core logic for running rsync and sending notifications
└── utils/
    └── telegram_utils.py # Utility functions to send messages via Telegram

```

## Requirements

- Docker >= 20.x

- docker-compose >= v2.x
(On modern systems, docker compose replaces docker-compose command)

- SSH access to Raspberry Pi with public key (no password)

- Telegram Bot Token (optional for notifications)

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
```

3. Set Up SSH Access to Raspberry Pi:

Make sure your host machine can connect to the Raspberry Pi via SSH without password:

- Generate a key pair (on your host machine, not inside the container):

```bash
$ ssh-keygen -t rsa -b 2048 -f ~/.ssh/id_rsa_rsync
```
👉 If you already have one, do not overwrite it.

- Copy your public key to the Raspberry Pi:

```bash
$ ssh-copy-id -i ~/.ssh/id_rsa_rsync.pub pi@<raspberry_pi_ip_address>
```
Verify that the connection works without a password:

```bash
$ ssh -i ~/.ssh/id_rsa_rsync pi@<raspberry_pi_ip_address>
```

✅ You should be able to connect without entering a password.

4. Build and Run the Container:

```bash
$ ./start_host.sh
```
## Usage

1. Manual Test

Run a manual sync:

```bash
docker exec -it rsync_docker /app/run_sync.sh from
```

## Cron Schedule

The sync process is automatically scheduled inside the container using cron.

By default, the schedule is defined in the crontab.txt file:

```plaintext
*/30 * * * * /bin/bash /app/run_sync.sh from >> /logs/cron.log 2>&1
```
This means:

    The sync will run every 30 minutes

    You can change this schedule by editing the crontab.txt file and rebuilding the container (./start_host.sh).

### Example schedules:

| Schedule        | Description                           |
|-----------------|---------------------------------------|
| `*/5 * * * *`   | Run every 5 minutes                    |
| `0 * * * *`     | Run once every hour (at HH:00)         |
| `5 * * * *`     | Run once every hour (at HH:05)         |
| `*/30 * * * *`  | Run every 30 minutes                   |
| `0 2 * * *`     | Run daily at 02:00 AM                  |

## Notifications

You will receive Telegram notifications if:

    ✅ The synchronization was successful

    ❌  An error or failure occurred during the process

## Feedback

If you have any feedback, please reach out to us at robertocarlos.toapanta@gmail.com

## Support

For support, email robertocarlos.toapanta@gmail.com or join our Discord channel.

## License

[GPL v2](https://www.gnu.org/licenses/gpl-2.0)

## Authors

- [@rotoapanta](https://github.com/rotoapanta)

## More Info

* [Cómo usar Rsync para sincronizar directorios locales y remotos](https://www.digitalocean.com/community/tutorials/how-to-use-rsync-to-sync-local-and-remote-directories-es)

## Links

[![linkedin](https://img.shields.io/badge/linkedin-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/roberto-carlos-toapanta-g/)
[![twitter](https://img.shields.io/badge/twitter-1DA1F2?style=for-the-badge&logo=twitter&logoColor=white)](https://twitter.com/rotoapanta)
