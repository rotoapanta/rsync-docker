# utils/constants.py

"""
Constantes compartidas para el sistema de sincronización y monitoreo.
Estas rutas y valores por defecto pueden ser usadas por múltiples módulos.
"""

# --- Default Raspberry Endpoint (usado si no se define en .env) ---
DEFAULT_RASPBERRY_URL = "http://192.168.100.29:8000/status"

# --- Rutas estándar dentro del contenedor ---
DATA_DIR = "/data"
CRONTAB_PATH = "/app/crontab.txt"
SYNC_SCRIPT_PATH = "/app/run_sync.sh"
CRON_LOG_PATH = "/app/logs/cron.log"


DEFAULT_RSYNC_FROM = "pi@192.168.190.29:/media/pi/BALER44"
DEFAULT_RSYNC_TO = "/data"
DEFAULT_RSYNC_OPTIONS = "-avz --delete"