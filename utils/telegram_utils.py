import os
import telegram
import logging
import threading

# Importar las clases necesarias de telegram.ext
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# Configurar logging para ver errores del bot y mensajes informativos
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Variables Globales para el Bot ---
# Obtener TOKEN y CHAT_ID del entorno
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Instancia del bot de Telegram (se inicializa una vez)
bot = None
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        logger.info("Bot de Telegram inicializado correctamente.")
    except Exception as e:
        logger.error(f"Error al inicializar el bot de Telegram con el token proporcionado: {e}")
        bot = None
else:
    logger.warning("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados. Las notificaciones y comandos del bot no funcionarán.")

# Variable global para almacenar la función de sincronización (callback)
sync_function_callback = None

# --- Funciones de Utilidad para enviar mensajes ---
def send_telegram(message: str) -> None:
    """
    Envía un mensaje a un chat de Telegram.
    Utiliza la instancia global 'bot' para la comunicación.
    """
    if bot and TELEGRAM_CHAT_ID:
        try:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
            logger.info(f"Mensaje de Telegram enviado: {message[:50]}...")
        except telegram.error.Unauthorized:
            logger.error("Error de Telegram: Token del bot inválido o no autorizado. Verifica TELEGRAM_BOT_TOKEN.")
        except telegram.error.BadRequest as e:
            logger.error(f"Error de Telegram (BadRequest): {e}. Posiblemente CHAT_ID incorrecto o formato de mensaje inválido.")
        except Exception as e:
            logger.error(f"Error desconocido al enviar mensaje a Telegram: {e}")
    else:
        logger.warning("Bot de Telegram no inicializado o CHAT_ID no configurado. No se pudo enviar el mensaje.")

# --- Funciones Handler para Comandos del Bot ---

def start_command(update, context):
    """
    Maneja el comando /start en Telegram.
    Envía un mensaje de bienvenida.
    """
    chat_id = update.message.chat_id
    user = update.message.from_user

    if str(chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para usar este bot.")
        logger.warning(f"Intento de comando /start no autorizado desde chat_id: {chat_id}, usuario: {user.username}")
        return

    welcome_message = (
        "Hello there! 👋 I'm your Raspberry Pi Data Sync Bot. 🤖\n\n"
        "I'm here to help keep your data synchronized. For a list of commands, use /help.\n"
        "Please ensure your Raspberry Pi is powered on and accessible. 📡"
    )
    update.message.reply_text(welcome_message, parse_mode='Markdown')
    logger.info(f"Comando /start recibido de {user.username} (ID: {chat_id}). Mensaje de bienvenida enviado.")


def help_command(update, context):
    """
    Maneja el comando /help en Telegram.
    Envía un mensaje con los comandos disponibles y su descripción.
    """
    chat_id = update.message.chat_id
    user = update.message.from_user

    if str(chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para usar este bot.")
        logger.warning(f"Intento de comando /help no autorizado desde chat_id: {chat_id}, usuario: {user.username}")
        return

    # --- MENSAJE DE AYUDA MODIFICADO ---
    help_message = (
        "Hello there! 👋 I'm your Raspberry Pi Data Sync Bot. 🤖\n\n"
        "Here are the commands you can use:\n"
        "  `/sync` - Triggers a *manual data synchronization* from your Raspberry Pi. 🚀\n"
        "  `/start` - Shows a welcome message and introduction to the bot.\n"
        "  `/help` - Shows this help message with available commands.\n\n" # Se auto-refiere
        "Please ensure your Raspberry Pi is powered on and accessible. 📡\n"
        "You'll receive notifications for every sync! ✨"
    )
    # --- FIN DEL MENSAJE DE AYUDA MODIFICADO ---

    update.message.reply_text(help_message, parse_mode='Markdown')
    logger.info(f"Comando /help recibido de {user.username} (ID: {chat_id}). Mensaje de ayuda enviado.")


def start_sync_command(update, context):
    """
    Maneja el comando /sync para iniciar la sincronización de datos.
    """
    chat_id = update.message.chat_id
    user = update.message.from_user

    if str(chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para ejecutar este comando.")
        logger.warning(f"Intento de comando /sync no autorizado desde chat_id: {chat_id}, usuario: {user.username}")
        return

    update.message.reply_text("`/sync` command received! Starting data synchronization now... 🚀")
    logger.info(f"Comando /sync recibido de {user.username} (ID: {chat_id}). Disparando sincronización.")

    if sync_function_callback:
        sync_thread = threading.Thread(target=sync_function_callback, args=("from",))
        sync_thread.start()
    else:
        update.message.reply_text("Internal error: Sync function is not configured.")
        logger.error("sync_function_callback not configured in telegram_utils. This is a programming error.")

def error_handler(update, context):
    """
    Registra los errores causados por Updates.
    """
    logger.warning(f'Update "{update}" caused error "{context.error}"')

# --- Función para iniciar el Listener del Bot ---
def start_telegram_bot_listener(sync_func):
    """
    Inicializa y arranca el bot de Telegram para escuchar comandos.
    Recibe la función de sincronización como callback.
    """
    global sync_function_callback
    sync_function_callback = sync_func

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not configured. Cannot start bot listener.")
        return

    if not bot:
        logger.error("Telegram bot instance is not available. Cannot start listener.")
        return

    try:
        updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
        dispatcher = updater.dispatcher

        dispatcher.add_handler(CommandHandler("start", start_command))
        dispatcher.add_handler(CommandHandler("help", help_command)) # Ahora usa help_command
        dispatcher.add_handler(CommandHandler("sync", start_sync_command))

        dispatcher.add_error_handler(error_handler)

        updater.start_polling()
        logger.info("Telegram Bot: Listener started and in polling mode.")

    except Exception as e:
        logger.error(f"Critical failure while starting Telegram bot listener: {e}")