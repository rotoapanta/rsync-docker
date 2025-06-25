import os
import sys
import time
import logging
import subprocess
import signal

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'managers'))
sys.path.append(os.path.join(current_dir, 'utils'))

from managers.sync_manager import SyncManager
from utils.telegram_utils import start_telegram_bot_listener, send_telegram, stop_sync_flag


# --- Funciones de Sincronización y Configuración de Cron ---

def perform_sync(direction: str):
    """
    Función que realiza la sincronización de datos.
    Puede ser llamada tanto por el cron como por el comando de Telegram.
    """
    logger.info(f"Iniciando sincronización para la dirección: {direction}")
    try:
        sync_manager = SyncManager()
        sync_manager.run_rsync(direction)
        logger.info(f"Sincronización {direction} finalizada.")
    except Exception as e:
        logger.error(f"Error inesperado durante la sincronización: {e}")
        send_telegram(f"❌ Error inesperado durante la sincronización: `{e}`")

def _update_crontab_entry(action: str, current_interval: int = None):
    """
    Función interna para modificar el crontab.
    Action: 'set_interval', 'disable', 'enable'
    """
    crontab_path = "/app/crontab.txt"
    sync_script_path = "/app/run_sync.sh"
    log_path = "/app/logs/cron.log"
     
    # Marcador para identificar la línea de sincronización automática
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
                    if not line.startswith("#"):
                        new_crontab_content.append(f"#{line}") # Comentar
                        logger.info(f"Comentando línea de sincronización: {line}")
                    else:
                        new_crontab_content.append(line) # Ya está comentada
                        logger.info(f"Línea de sincronización ya comentada: {line}")
                elif action == 'enable':
                    if line.startswith("#"):
                        new_crontab_content.append(line[1:]) # Descomentar
                        logger.info(f"Descomentando línea de sincronización: {line}")
                    else:
                        new_crontab_content.append(line) # Ya está descomentada
                        logger.info(f"Línea de sincronización ya descomentada: {line}")
                elif action == 'set_interval':
                    new_crontab_content.append(f"*/{current_interval} * * * * {sync_script_path} from >> {log_path} 2>&1")
                    logger.info(f"Actualizando intervalo de sincronización a {current_interval} minutos: {new_crontab_content[-1]}")
            else:
                new_crontab_content.append(line)
         
        # Si la línea de sincronización no se encontró y estamos intentando habilitarla o establecerla, la añadimos.
        if not sync_line_found and (action == 'enable' or action == 'set_interval'):
            if action == 'set_interval':
                new_crontab_content.append(f"*/{current_interval} * * * * {sync_script_path} from >> {log_path} 2>&1")
                logger.info(f"Añadiendo nueva línea de sincronización: {new_crontab_content[-1]}")
            else: # action == 'enable' pero no hay línea para descomentar
                # Podrías añadir una línea por defecto o informar que no hay una.
                # Aquí, añadimos una por defecto si no se encontró ninguna y se intentó habilitar.
                default_interval = 30 # Por ejemplo, 30 minutos
                new_crontab_content.append(f"*/{default_interval} * * * * {sync_script_path} from >> {log_path} 2>&1")
                send_telegram(f"⚠️ No se encontró una línea de sincronización automática. Se ha añadido una por defecto cada {default_interval} minutos.")
                logger.warning(f"No sync line found in crontab.txt. Added default: {new_crontab_content[-1]}")


        # Escribir el nuevo contenido al crontab.txt
        with open(crontab_path, "w") as f:
            for line in new_crontab_content:
                f.write(line + "\n")

        # Cargar el nuevo crontab en el sistema cron
        subprocess.run(["crontab", crontab_path], check=True, capture_output=True)
        return True, "" # Éxito

    except subprocess.CalledProcessError as e:
        error_msg = f"Error al modificar el cron (código: {e.returncode}): {e.stderr.decode('utf-8')}"
        return False, error_msg
    except Exception as e:
        error_msg = f"Error inesperado al modificar el cron: `{e}`"
        return False, error_msg


def change_cron_interval(minutes: int):
    """
    Cambia el intervalo de ejecución del cron para la sincronización.
    """
    success, msg = _update_crontab_entry('set_interval', minutes)
    if success:
        send_telegram(f"✅ Intervalo de sincronización automática cambiado a cada `{minutes}` minutos. El cambio debería ser efectivo pronto.")
        logger.info(f"Cron interval changed to every {minutes} minutes by Telegram command.")
    else:
        send_telegram(f"❌ {msg}")
        logger.error(f"Failed to change cron interval: {msg}")

def disable_auto_sync():
    """
    Desactiva la sincronización automática comentando la línea en crontab.
    """
    success, msg = _update_crontab_entry('disable')
    if success:
        send_telegram("🚫 Sincronización automática **desactivada**. Ya no se ejecutará periódicamente hasta que la habilites.")
        logger.info("Automatic sync disabled via Telegram command.")
    else:
        send_telegram(f"❌ Error al desactivar la sincronización automática: {msg}")
        logger.error(f"Failed to disable auto sync: {msg}")

def enable_auto_sync():
    """
    Activa la sincronización automática descomentando la línea en crontab.
    """
    success, msg = _update_crontab_entry('enable')
    if success:
        send_telegram("✅ Sincronización automática **activada**. Se ejecutará periódicamente según el intervalo configurado.")
        logger.info("Automatic sync enabled via Telegram command.")
    else:
        send_telegram(f"❌ Error al activar la sincronización automática: {msg}")
        logger.error(f"Failed to enable auto sync: {msg}")


if __name__ == "__main__":
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if telegram_bot_token and telegram_chat_id:
        logger.info("Intentando iniciar el listener del bot de Telegram...")
        try:
            # Pasa todas las funciones de callback al listener del bot
            start_telegram_bot_listener(
                perform_sync,
                change_cron_interval,
                disable_auto_sync,  # Nuevo callback
                enable_auto_sync    # Nuevo callback
            )
            send_telegram("✅ Servicio de sincronización iniciado. Para iniciar una descarga manual, usa el comando `/sync`.")
            logger.info("Bot de Telegram iniciado y mensaje de bienvenida enviado.")
        except Exception as e:
            logger.error(f"Fallo al iniciar el listener del bot de Telegram: {e}")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados. El bot de comandos no se iniciará.")

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "from":
            logger.info(f"Ejecutando sincronización '{command}' (desde cron o manualmente vía CLI)...")
            perform_sync(command)
        else:
            logger.warning(f"Comando '{command}' no reconocido. Uso: python3 main.py [from]")
            sys.exit(1)
    else:
        logger.info("No se especificó ningún comando CLI. Manteniendo el script en ejecución para el bot de Telegram.")
        logger.info("Para ejecutar sincronización manual vía CLI use: docker exec rsync_docker python3 /app/main.py from")
        while True:
            time.sleep(3600)