import os
import sys
import time
import logging # Importar logging para un mejor manejo de mensajes

# Configurar logging básico para main.py
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Ajustar el PATH para que Python encuentre los módulos en 'managers' y 'utils'
# Esto es crucial si tu Dockerfile copia a /app y tus imports son relativos
# El __file__ se refiere a la ubicación de main.py
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'managers'))
sys.path.append(os.path.join(current_dir, 'utils'))

# Importar SyncManager y las funciones del bot de Telegram
from managers.sync_manager import SyncManager
from utils.telegram_utils import start_telegram_bot_listener, send_telegram

# Función que encapsula la lógica de sincronización
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


if __name__ == "__main__":
    # --- Parte para el Bot de Telegram ---
    # Iniciar el bot de Telegram para escuchar comandos en segundo plano
    # Le pasamos la función perform_sync para que el bot pueda llamarla
    # cuando reciba el comando /sync.
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if telegram_bot_token and telegram_chat_id:
        logger.info("Intentando iniciar el listener del bot de Telegram...")
        try:
            start_telegram_bot_listener(perform_sync)
            # Enviar un mensaje inicial al chat configurado una vez que el bot esté online.
            # Esto ayuda a confirmar que el bot ha iniciado correctamente.
            send_telegram("✅ Servicio de sincronización iniciado. Para iniciar una descarga manual, usa el comando `/sync`.")
            logger.info("Bot de Telegram iniciado y mensaje de bienvenida enviado.")
        except Exception as e:
            logger.error(f"Fallo al iniciar el listener del bot de Telegram: {e}")
            # No podemos enviar por Telegram si el bot no inició
    else:
        logger.warning("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados. El bot de comandos no se iniciará.")

    # --- Parte para la ejecución por cron o manual (vía argumentos de línea de comandos) ---
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "from":
            logger.info(f"Ejecutando sincronización '{command}' (desde cron o manualmente vía CLI)...")
            perform_sync(command)
        else:
            logger.warning(f"Comando '{command}' no reconocido. Uso: python3 main.py [from]")
            sys.exit(1)
    else:
        # Si no se pasan argumentos, significa que el contenedor debe quedarse esperando
        # comandos de Telegram. Mantenemos el proceso vivo.
        logger.info("No se especificó ningún comando CLI. Manteniendo el script en ejecución para el bot de Telegram.")
        logger.info("Para ejecutar sincronización manual vía CLI use: docker exec rsync_docker python3 /app/main.py from")
        while True:
            # Duerme por un largo período para mantener el proceso vivo sin consumir CPU.
            # El bot de Telegram ya está escuchando en un hilo separado.
            time.sleep(3600) # Dormir por 1 hora