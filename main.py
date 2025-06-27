import os
import sys
import time
import logging
import subprocess
import socket
import datetime
import requests
from shutil import disk_usage

# Ajusta el sys.path para que pueda encontrar el módulo utils y managers
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'managers'))
sys.path.append(os.path.join(current_dir, 'utils'))

from utils.telegram_utils import start_telegram_bot_listener, send_telegram
from managers.sync_manager import SyncManager

# --- Configuración de logging ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- URL del endpoint del Raspberry ---
RASPBERRY_URL = "http://192.168.190.29:8000/status"

# --- Constante del directorio de datos ---
DATA_DIR = "/data" # Directorio de destino local en el contenedor

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
        found_and_updated = False

        for line in existing_lines:
            if sync_line_marker in line and not found_and_updated:
                if action == 'disable':
                    new_crontab_content.append(f"#{line}" if not line.startswith("#") else line)
                elif action == 'enable':
                    new_crontab_content.append(line[1:] if line.startswith("#") else line)
                elif action == 'set_interval':
                    new_crontab_content.append(f"*/{current_interval} * * * * {sync_script_path} from >> {log_path} 2>&1")
                found_and_updated = True
            elif sync_line_marker in line and found_and_updated:
                pass # Eliminamos líneas duplicadas
            else:
                new_crontab_content.append(line)

        if not found_and_updated and (action in ['enable', 'set_interval']):
            default_interval = 30
            new_crontab_content.append(f"*/{current_interval if action == 'set_interval' else default_interval} * * * * {sync_script_path} from >> {log_path} 2>&1")
            send_telegram(f"⚠️ No se encontró una línea de sincronización automática. Se añadió una por defecto cada {current_interval if action == 'set_interval' else default_interval} minutos.")

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

# --- Funciones para obtener información de disco y sistema ---

def _get_local_disk_info(path: str) -> tuple[float, float, float]:
    """
    Obtiene el espacio total, usado y libre en GB para una ruta local.
    Devuelve (total_gb, used_gb, free_gb).
    """
    total, used, free = disk_usage(path)
    total_gb = total / (1024**3)
    used_gb = used / (1024**3)
    free_gb = free / (1024**3)
    return total_gb, used_gb, free_gb

def get_icon(value, thresholds=(50, 80)):
    """Función auxiliar para obtener iconos basados en umbrales."""
    if value >= thresholds[1]:
        return "🔴"
    elif value >= thresholds[0]:
        return "🟠"
    else:
        return "🟢"

# Nueva función para obtener el intervalo de sincronización actual
def _get_current_sync_interval() -> str:
    """
    Obtiene el intervalo de sincronización actual del crontab.
    Retorna el intervalo en minutos o 'Desconocido/Desactivado' si no se encuentra.
    """
    try:
        # Ejecuta crontab -l para listar las tareas
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=True)
        crontab_output = result.stdout

        sync_script_path = "/app/run_sync.sh from"
        
        for line in crontab_output.splitlines():
            # Busca la línea que contiene el script de sincronización
            if sync_script_path in line:
                # Si la línea está comentada, está desactivado
                if line.strip().startswith('#'):
                    return "Desactivado"
                
                # Extrae la parte de los minutos (la primera sección del cron)
                parts = line.strip().split()
                if len(parts) > 0:
                    minutes_part = parts[0]
                    # Si es */N, extrae N
                    if minutes_part.startswith('*/'):
                        try:
                            interval = int(minutes_part[2:])
                            return f"Cada {interval} minutos"
                        except ValueError:
                            return "Intervalo irregular" # Si no es un número
                    elif minutes_part == '*':
                        return "Cada minuto"
                    elif minutes_part.isdigit():
                        return f"A los {minutes_part} minutos de cada hora"
                    else:
                        return "Intervalo personalizado" # Para casos más complejos (e.g., "0,30")
        
        return "No configurado" # Si no se encuentra la línea de sync
    except subprocess.CalledProcessError:
        logger.error("Error al ejecutar crontab -l. Cron no instalado o permiso denegado.")
        return "Error al leer cron"
    except Exception as e:
        logger.error(f"Error inesperado al obtener intervalo de cron: {e}")
        return "Error al leer cron"


def disk_status_report():
    """
    Reporta el estado del disco del contenedor Docker (donde se monta /data)
    y el estado de los discos conectados a la Raspberry Pi (partición root y USBs).
    """
    message = "💾 *Estado del Almacenamiento*\n\n"

    # 1. Información del disco del contenedor Docker (ruta /data)
    try:
        total_docker_gb, used_docker_gb, free_docker_gb = _get_local_disk_info(DATA_DIR)
        message += (
            f"📦 *Contenedor Docker* (`{DATA_DIR}`):\n"
            f"├ 🧱 Total: `{total_docker_gb:.2f} GB`\n"
            f"├ 📂 Usado: `{used_docker_gb:.2f} GB`\n"
            f"└ 📦 Libre: `{free_docker_gb:.2f} GB`\n\n"
        )
        if free_docker_gb < 10: # Puedes ajustar este umbral
            message += "⚠️ *Alerta: Bajo espacio en disco en el contenedor Docker!*\n\n"
    except Exception as e:
        message += f"❌ Error al obtener espacio del contenedor: `{e}`\n\n"
        logger.error(f"Error al obtener espacio del contenedor: {e}")

    # 2. Información del disco de la Raspberry Pi (partición root y USBs)
    try:
        response = requests.get(RASPBERRY_URL, timeout=5)
        response.raise_for_status()
        raspberry_data = response.json()

        r_disk_info = raspberry_data.get("disk_info", {})
        r_total = r_disk_info.get("total", "?")
        r_used = r_disk_info.get("used", "?")
        r_free = r_disk_info.get("free", "?")
        r_disk_percent = raspberry_data.get("disk", 0) # Porcentaje de uso del disco principal de la Pi

        disk_icon = get_icon(r_disk_percent)

        message += (
            f"🍓 *Raspberry Pi* (Partición Root `/`):\n"
            f"┌─── {disk_icon} *Uso:* `{r_disk_percent:.1f}%` ───┐\n"
            f"├ 🧱 Total: `{r_total} GB`\n"
            f"├ 📂 Usado: `{r_used} GB`\n"
            f"└ 📦 Libre: `{r_free} GB`\n"
        )
        if r_free < 10: # Puedes ajustar este umbral
            message += "⚠️ *Alerta: Bajo espacio en disco en la Raspberry Pi!*"

        # Añadir información de USBs conectadas a la Raspberry Pi
        usb_disks = raspberry_data.get("usb", [])
        if usb_disks:
            message += f"\n\n🧷 *USBs conectadas al Raspberry Pi:*\n"
            for usb in usb_disks:
                mount = usb.get("mount", "?")
                device = usb.get("device", "?")
                total = usb.get("total", 0)
                used = usb.get("used", 0)
                free = usb.get("free", 0)
                percent = (used / total * 100) if total else 0

                icon = get_icon(percent, thresholds=(80, 90)) # Umbrales más estrictos para USBs

                alert = ""
                if percent >= 90:
                    alert = "⚠️ *CRÍTICO* - Poco espacio libre"
                elif percent >= 80:
                    alert = "⚠️ *ALERTA* - Bajo espacio libre"

                message += (
                    f"{icon} `{mount}` ({device})\n"
                    f"├ 💽 Total: `{total:.2f} GB`\n"
                    f"├ 📂 Usado: `{used:.2f} GB`\n"
                    f"└ 📦 Libre: `{free:.2f} GB`\n"
                )
                if alert:
                    message += f"    {alert}\n"

    except Exception as e:
        message += f"❌ Error al obtener estado de disco de Raspberry Pi: `{e}`"
        logger.error(f"Error al obtener estado de disco de Raspberry Pi: {e}")

    send_telegram(message)

def status_report():
    """
    Reporta el estado general del sistema de la Raspberry Pi (CPU, RAM, Temp, Batería, etc.).
    """
    try:
        response = requests.get(RASPBERRY_URL, timeout=5)
        response.raise_for_status()
        raspberry_data = response.json()

        r_hostname = raspberry_data.get("hostname", "?")
        r_ip = raspberry_data.get("ip", "?")
        r_cpu = raspberry_data.get("cpu", 0)
        r_ram = raspberry_data.get("ram", 0)
        r_temp = raspberry_data.get("temp", 0)
        r_batt = raspberry_data.get("battery", {})
        r_volt = r_batt.get("voltage", "?")
        r_status = r_batt.get("status", "?")

        cpu_icon = get_icon(r_cpu)
        ram_icon = get_icon(r_ram)
        temp_icon = get_icon(r_temp, thresholds=(50, 70))

        # Obtener el intervalo de sincronización actual
        sync_interval_info = _get_current_sync_interval()

        message = (
            f"🍓 *Estado del Raspberry Pi (Sistema)*\n\n"
            f"🖥️ *Hostname:* `{r_hostname}`\n"
            f"🌐 *IP:* `{r_ip}`\n"
            f"{cpu_icon} *CPU:* `{r_cpu:.1f}%`\n"
            f"{ram_icon} *RAM:* `{r_ram:.1f}%`\n"
            f"{temp_icon} *Temp:* `{r_temp} °C`\n"
            f"🔋 *Batería:* `{r_volt} V` | `{r_status}`\n"
            f"🔄 *Sinc. Auto:* `{sync_interval_info}`" # <--- ¡Nueva línea!
        )
        send_telegram(message)

    except Exception as e:
        send_telegram(f"❌ Error al obtener estado general del Raspberry Pi: `{e}`")


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
                disk_func=disk_status_report, # Se pasa la función de reporte de estado del disco
                status_func=status_report     # Se pasa la función de reporte de estado general
            )
            send_telegram("✅ Servicio de sincronización iniciado\. Usa /sync para iniciar manualmente\.")
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
        logger.info("Modo de ejecución principal: Manteniendo el servicio de bot y cron...")
        while True:
            time.sleep(3600)