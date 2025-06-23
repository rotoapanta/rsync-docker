import os
import sys
import time # Importar time para mantener el script vivo si solo se usa el bot

# Ajusta el PATH para que Python encuentre los módulos en 'managers' y 'utils'
# Esto es crucial si tu Dockerfile copia a /app y tus imports son relativos
# Añade esto si no lo tienes ya en tu main.py
sys.path.append(os.path.join(os.path.dirname(__file__), 'managers'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))

from managers.sync_manager import SyncManager
from utils.telegram_utils import start_telegram_bot_listener, send_telegram # Importar la nueva función del bot

# Función que encapsula la lógica de sincronización
def perform_sync(direction: str):
    """
    Función que realiza la sincronización de datos.
    Puede ser llamada tanto por el cron como por el comando de Telegram.
    """
    print(f"Iniciando sincronización para la dirección: {direction}")
    sync_manager = SyncManager()
    sync_manager.run_rsync(direction)
    print(f"Sincronización {direction} finalizada.")

if __name__ == "__main__":
    # --- Parte para el Bot de Telegram ---
    # Iniciar el bot de Telegram para escuchar comandos en segundo plano
    # Le pasamos la función perform_sync para que el bot pueda llamarla cuando reciba /sync
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        print("Intentando iniciar el listener del bot de Telegram...")
        start_telegram_bot_listener(perform_sync)
    else:
        print("Advertencia: TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados. El bot de comandos no se iniciará.")

    # --- Parte para la ejecución por cron o manual (vía argumentos de línea de comandos) ---
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "from":
            print(f"Ejecutando sincronización '{command}' (desde cron o manualmente)...")
            perform_sync(command)
        else:
            print(f"Comando '{command}' no reconocido. Uso: python3 main.py [from]")
            sys.exit(1)
    else:
        # Si no se pasan argumentos, significa que el contenedor debe quedarse esperando
        # comandos de Telegram. Mantenemos el proceso vivo.
        print("No se especificó ningún comando. Manteniendo el script en ejecución para el bot de Telegram.")
        print("Para ejecutar sincronización manual use: docker exec rsync_docker python3 /app/main.py from")
        while True:
            # Duerme por un largo período para mantener el proceso vivo sin consumir CPU.
            # El bot de Telegram ya está escuchando en un hilo separado.
            time.sleep(3600) # Dormir por 1 hora