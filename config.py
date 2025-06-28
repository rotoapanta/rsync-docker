import os
from dotenv import load_dotenv

# Carga el archivo .env en el entorno
load_dotenv()

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- RSYNC ---
RSYNC_FROM = os.getenv("RSYNC_FROM")
RSYNC_DEST_HOST_PATH = os.getenv("RSYNC_DEST_HOST_PATH")
RSYNC_TO = os.getenv("RSYNC_TO", "/data")  # Valor por defecto si no está en .env

# --- Raspberry Pi Backend URL ---
RASPBERRY_URL = os.getenv("RASPBERRY_URL", "http://127.0.0.1:8000/status")

# --- Umbrales de sistema ---
CPU_WARN = int(os.getenv("CPU_WARN", "50"))
CPU_CRITICAL = int(os.getenv("CPU_CRITICAL", "80"))
TEMP_WARN = int(os.getenv("TEMP_WARN", "50"))
TEMP_CRITICAL = int(os.getenv("TEMP_CRITICAL", "70"))
DISK_WARN = int(os.getenv("DISK_WARN", "80"))
DISK_CRITICAL = int(os.getenv("DISK_CRITICAL", "90"))
