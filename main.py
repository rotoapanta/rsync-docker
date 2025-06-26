import os
import sys
import time
import logging
import subprocess
import signal

from managers.sync_manager import SyncManager
from utils.telegram_utils import start_telegram_bot_listener, send_telegram, stop_sync_flag

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'managers'))
sys.path.append(os.path.join(current_dir, 'utils'))

# --- Funciones de Sincronización y Configuración de Cron ---

def perform_sync(direction: str):
    logger.info(f"Iniciando sincronización para la dirección: {direction}")
    try:
        sync_manager = SyncManager()
        sync_manager.run_rsync(direction)
        logger.info(f"Sincronización {direction} finalizada.")
    except Exception as e:
        logger.error(f"Error inesperado durante la sincronización: {e}")
        send_telegram(f"❌ Error inesperado durante la sincronización: `{e}`")

def _update_crontab_entry(action: str, current_interval: int = None):
    crontab_path = "/app/crontab.txt"
    sync_script_path = "/app/run_sync.sh"
    log_path = "/app/logs/cron.log"
    sync_line_marker = f"{sync_script_path} from"
    try:
        existing_lines = []
        if os.path.exists(crontab_path):
            with open(crontab_path, "r") as f:
                existing_lines = [line.strip() for line in f]
        new_crontab_content = []
        sync_line_found = False
        for line in existing_lines:
            if sync_line_marker in line:
                sync_line_found = True
                if action == 'disable':
                    new_crontab_content.append(f"#{line}" if not line.startswith("#") else line)
                elif action == 'enable':
                    new_crontab_content.append(line[1:] if line.startswith("#") else line)
                elif action == 'set_interval':
                    new_crontab_content.append(f"*/{current_interval} * * * * {sync_script_path} from >> {log_path} 2>&1")
            else:
                new_crontab_content.append(line)
        if not sync_line_found and (action == 'enable' or action == 'set_interval'):
            default_interval = 30
            new_crontab_content.append(f"*/{default_interval} * * * * {sync_script_path} from >> {log_path} 2>&1")
            send_telegram(f"⚠️ No se encontró una línea de sincronización automática. Se ha añadido una por defecto cada {default_interval} minutos.")
        with open(crontab_path, "w") as f:
            for line in new_crontab_content:
                f.write(line + "\n")
        subprocess.run(["crontab", crontab_path], check=True, capture_output=True)
        return True, ""
    except subprocess.CalledProcessError as e:
        return False, f"Error al modificar el cron (código: {e.returncode}): {e.stderr.decode('utf-8')}"
    except Exception as e:
        return False, f"Error inesperado al modificar el cron: `{e}`"

def change_cron_interval(minutes: int):
    success, msg = _update_crontab_entry('set_interval', minutes)
    if success:
        send_telegram(f"✅ Intervalo de sincronización automática cambiado a cada `{minutes}` minutos.")
    else:
        send_telegram(f"❌ {msg}")

def disable_auto_sync():
    success, msg = _update_crontab_entry('disable')
    if success:
        send_telegram("🚫 Sincronización automática **desactivada**.")
    else:
        send_telegram(f"❌ {msg}")

def enable_auto_sync():
    success, msg = _update_crontab_entry('enable')
    if success:
        send_telegram("✅ Sincronización automática **activada**.")
    else:
        send_telegram(f"❌ {msg}")

def check_disk_status():
    try:
        from shutil import disk_usage
        path = "/data"
        total, used, free = disk_usage(path)
        total_gb = total / (1024 ** 3)
        used_gb = used / (1024 ** 3)
        free_gb = free / (1024 ** 3)
        message = (
            f"📮 *Disk Usage Info (`{path}`)*:\n"
            f"• Total: `{total_gb:.2f} GB`\n"
            f"• Used: `{used_gb:.2f} GB`\n"
            f"• Free: `{free_gb:.2f} GB`"
        )
        send_telegram(message)
    except Exception as e:
        send_telegram(f"❌ Error checking disk status: `{e}`")

if __name__ == "__main__":
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if telegram_bot_token and telegram_chat_id:
        logger.info("Intentando iniciar el listener del bot de Telegram...")
        try:
            start_telegram_bot_listener(
                perform_sync,
                change_cron_interval,
                disable_auto_sync,
                enable_auto_sync,
                disk_func=check_disk_status
            )
            send_telegram("\u2705 Servicio de sincronización iniciado. Usa /sync para iniciar manualmente.")
        except Exception as e:
            logger.error(f"Fallo al iniciar el listener del bot de Telegram: {e}")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados. El bot no se iniciará.")

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "from":
            logger.info("Ejecutando sincronización manual desde CLI...")
            perform_sync(command)
        else:
            logger.warning(f"Comando '{command}' no reconocido. Uso: python3 main.py [from]")
            sys.exit(1)
    else:
        logger.info("Sin comando CLI. Ejecutando en modo escucha para Telegram bot.")
        while True:
            time.sleep(3600)
