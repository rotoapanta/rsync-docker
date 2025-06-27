import os
import sys
import time
import logging
import subprocess
import socket
import datetime
import requests
from shutil import disk_usage
from managers.sync_manager import SyncManager
from utils.telegram_utils import start_telegram_bot_listener, send_telegram, stop_sync_flag

# --- Configuración de logging ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'managers'))
sys.path.append(os.path.join(current_dir, 'utils'))

# --- URL del endpoint del Raspberry ---
RASPBERRY_URL = "http://192.168.190.29:8000/status"

# --- Función de sincronización manual ---
def perform_sync(direction: str):
    logger.info(f"Iniciando sincronización para la dirección: {direction}")
    try:
        sync_manager = SyncManager()
        sync_manager.run_rsync(direction)
        logger.info(f"Sincronización {direction} finalizada.")
    except Exception as e:
        logger.error(f"Error inesperado durante la sincronización: {e}")
        send_telegram(f"❌ Error inesperado durante la sincronización: `{e}`")

# --- Cron: actualización de intervalos ---
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

        if not sync_line_found and (action in ['enable', 'set_interval']):
            default_interval = 30
            new_crontab_content.append(f"*/{default_interval} * * * * {sync_script_path} from >> {log_path} 2>&1")
            send_telegram(f"⚠️ No se encontró una línea de sincronización automática. Se añadió una por defecto cada {default_interval} minutos.")

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
    send_telegram("✅ Intervalo actualizado." if success else f"❌ {msg}")

def disable_auto_sync():
    success, msg = _update_crontab_entry('disable')
    send_telegram("🚫 Auto sync desactivado." if success else f"❌ {msg}")

def enable_auto_sync():
    success, msg = _update_crontab_entry('enable')
    send_telegram("✅ Auto sync activado." if success else f"❌ {msg}")

# --- Recolectar información de la Raspberry remotamente ---
def fetch_raspberry_status():
    try:
        response = requests.get(RASPBERRY_URL, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error al obtener estado del Raspberry: {e}")
        return None

def status_report():
    try:
        import requests

        RASPBERRY_URL = "http://192.168.190.29:8000/status"
        raspberry_data = requests.get(RASPBERRY_URL, timeout=5).json()

        r_hostname = raspberry_data.get("hostname", "?")
        r_ip = raspberry_data.get("ip", "?")
        r_cpu = raspberry_data.get("cpu", 0)
        r_ram = raspberry_data.get("ram", 0)
        r_disk = raspberry_data.get("disk", 0)
        r_temp = raspberry_data.get("temp", 0)
        r_batt = raspberry_data.get("battery", {})
        r_volt = r_batt.get("voltage", "?")
        r_status = r_batt.get("status", "?")

        r_disk_info = raspberry_data.get("disk_info", {})
        r_total = r_disk_info.get("total", "?")
        r_used = r_disk_info.get("used", "?")
        r_free = r_disk_info.get("free", "?")

        usb_disks = raspberry_data.get("usb", [])

        def get_icon(value, thresholds=(50, 80)):
            if value >= thresholds[1]:
                return "🔴"
            elif value >= thresholds[0]:
                return "🟠"
            else:
                return "🟢"

        cpu_icon = get_icon(r_cpu)
        ram_icon = get_icon(r_ram)
        disk_icon = get_icon(r_disk)
        temp_icon = get_icon(r_temp, thresholds=(50, 70))

        message = (
            f"🍓 *Estado del Raspberry Pi*\n\n"
            f"🖥️ *Hostname:* `{r_hostname}`\n"
            f"🌐 *IP:* `{r_ip}`\n"
            f"{cpu_icon} *CPU:* `{r_cpu:.1f}%`\n"
            f"{ram_icon} *RAM:* `{r_ram:.1f}%`\n"
            f"{disk_icon} *Disco:* `{r_disk:.1f}%`\n"
            f"┌─── 📁 `/` ───┐\n"
            f"├ 🧱 Total: `{r_total} GB`\n"
            f"├ 📂 Usado: `{r_used} GB`\n"
            f"└ 📦 Libre: `{r_free} GB`\n"
            f"{temp_icon} *Temp:* `{r_temp} °C`\n"
            f"🔋 *Batería:* `{r_volt} V` | `{r_status}`"
        )

        if usb_disks:
            message += f"\n\n🧷 *USBs conectadas:*\n"
            for usb in usb_disks:
                mount = usb.get("mount", "?")
                device = usb.get("device", "?")
                total = usb.get("total", 0)
                used = usb.get("used", 0)
                free = usb.get("free", 0)
                percent = (used / total * 100) if total else 0

                icon = "🟢"
                alert = ""

                if percent >= 90:
                    icon = "🔴"
                    alert = "⚠️ *CRÍTICO* - Poco espacio libre"
                elif percent >= 80:
                    icon = "🟠"
                    alert = "⚠️ *ALERTA* - Bajo espacio libre"

                message += (
                    f"{icon} `{mount}` ({device})\n"
                    f"├ 💽 Total: `{total:.2f} GB`\n"
                    f"├ 📂 Usado: `{used:.2f} GB`\n"
                    f"└ 📦 Libre: `{free:.2f} GB`\n"
                )
                if alert:
                    message += f"   {alert}\n"

        send_telegram(message)

    except Exception as e:
        send_telegram(f"❌ Error al obtener estado del Raspberry Pi: `{e}`")


# --- Punto de entrada principal ---
if __name__ == "__main__":
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if telegram_bot_token and telegram_chat_id:
        logger.info("Iniciando listener del bot de Telegram...")
        try:
            start_telegram_bot_listener(
                perform_sync,
                change_cron_interval,
                disable_auto_sync,
                enable_auto_sync,
                disk_func=None,
                status_func=status_report
            )
            send_telegram("✅ Servicio de sincronización iniciado. Usa /sync para iniciar manualmente.")
        except Exception as e:
            logger.error(f"Fallo al iniciar bot de Telegram: {e}")
    else:
        logger.warning("Token o Chat ID no configurado. El bot no se iniciará.")

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "from":
            perform_sync("from")
        else:
            logger.warning(f"Comando no reconocido: {command}")
    else:
        while True:
            time.sleep(3600)