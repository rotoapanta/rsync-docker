"""
config.py
Centraliza la carga de configuración de la aplicación usando env_utils y constants.
No contiene lógica de negocio, solo exposición de configuración.
"""
from utils.env_utils import get_env_variable
from utils.constants import (
    DEFAULT_RASPBERRY_URL, DEFAULT_RSYNC_FROM, DEFAULT_RSYNC_TO, DEFAULT_RSYNC_OPTIONS
)

TELEGRAM_BOT_TOKEN = get_env_variable("TELEGRAM_BOT_TOKEN", required=True)
TELEGRAM_CHAT_ID = get_env_variable("TELEGRAM_CHAT_ID", required=True)
RASPBERRY_URL = get_env_variable("RASPBERRY_URL", default=DEFAULT_RASPBERRY_URL)
RSYNC_FROM = get_env_variable("RSYNC_FROM", default=DEFAULT_RSYNC_FROM)
RSYNC_DEST_HOST_PATH = get_env_variable("RSYNC_DEST_HOST_PATH", default=DEFAULT_RSYNC_TO)
RSYNC_MAX_RETRIES = int(get_env_variable("RSYNC_MAX_RETRIES", default=3))
RSYNC_RETRY_DELAY = int(get_env_variable("RSYNC_RETRY_DELAY", default=5))
DISK_SPACE_THRESHOLD_GB = int(get_env_variable("DISK_SPACE_THRESHOLD_GB", default=10))
FOLDER_LIST_THRESHOLD = int(get_env_variable("FOLDER_LIST_THRESHOLD", default=5))
