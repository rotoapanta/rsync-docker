import os
import telegram
import logging
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters #
import threading # Para ejecutar la sincronización en un hilo separado

# Configurar logging para ver errores del bot
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Obtener TOKEN y CHAT_ID del entorno
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Inicializar el bot de Telegram (se usará para enviar mensajes y para el Updater)
bot = None
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    except Exception as e:
        logger.error(f"Error al inicializar el bot de Telegram: {e}")
else:
    logger.warning("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados. Las notificaciones no funcionarán.")

def send_telegram(message: str) -> None:
    """
    Envía un mensaje a un chat de Telegram.
    Esta función usa la instancia del bot inicializada globalmente.
    """
    if bot:
        try:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error al enviar mensaje a Telegram: {e}")
    else:
        logger.warning("Bot de Telegram no inicializado. No se pudo enviar el mensaje.")

# --- NUEVAS FUNCIONES PARA MANEJAR COMANDOS Y EL LISTENER ---

# Variable global para almacenar la función de sincronización (callback)
sync_function_callback = None

def start_sync_command(update, context): #
    """Maneja el comando /sync para iniciar la sincronización."""
    chat_id = update.message.chat_id
    user = update.message.from_user

    # Verificar que el comando viene de tu CHAT_ID configurado
    if str(chat_id) != TELEGRAM_CHAT_ID: #
        update.message.reply_text("Lo siento, no estás autorizado para ejecutar este comando.") #
        logger.warning(f"Intento de comando /sync no autorizado desde chat_id: {chat_id}, usuario: {user.username}")
        return

    update.message.reply_text("¡Comando /sync recibido! Iniciando la sincronización de datos ahora...") #
    logger.info(f"Comando /sync recibido de {user.username} (ID: {chat_id}). Iniciando sincronización.")

    # Llama a la función de sincronización que se le pasó desde main.py en un hilo separado
    if sync_function_callback:
        # Ejecuta en un hilo separado para no bloquear el bot
        sync_thread = threading.Thread(target=sync_function_callback, args=("from",))
        sync_thread.start()
    else:
        update.message.reply_text("Error interno: La función de sincronización no está configurada.")
        logger.error("sync_function_callback no configurada en telegram_utils.")

def error_handler(update, context): #
    """Registra errores causados por Updates."""
    logger.warning(f'Update "{update}" causó error "{context.error}"') #

def start_telegram_bot_listener(sync_func):
    """
    Inicializa y arranca el bot de Telegram para escuchar comandos.
    Recibe la función de sincronización como callback.
    """
    global sync_function_callback
    sync_function_callback = sync_func # Asigna la función de sincronización pasada desde main.py

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN no está configurado. No se puede iniciar el listener del bot.")
        return

    try:
        updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True) #
        dispatcher = updater.dispatcher #

        # Añadir manejador para el comando /sync
        dispatcher.add_handler(CommandHandler("sync", start_sync_command)) #

        # Añadir manejador de errores
        dispatcher.add_error_handler(error_handler) #

        # Iniciar el bot. Usa start_polling() para que el bot escuche en segundo plano.
        updater.start_polling() #
        logger.info("Bot de Telegram iniciado y escuchando comandos...")
    except Exception as e:
        logger.error(f"Error al iniciar el listener del bot de Telegram: {e}")