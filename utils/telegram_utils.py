import os
import telegram
import logging
import threading

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Variables Globales para el Bot ---
# Estas variables se inicializan aquí leyendo del entorno.
# Es crucial que load_dotenv() se haya llamado ANTES de que este módulo se importe
# para que os.getenv() devuelva los valores correctos.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Inicializar el objeto bot si las variables están disponibles
bot = None
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    try:
        # Asegurarse de que TELEGRAM_CHAT_ID sea una cadena (string) para comparaciones futuras
        TELEGRAM_CHAT_ID = str(TELEGRAM_CHAT_ID)
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        logger.info(f"Bot de Telegram inicializado correctamente con token y CHAT_ID: {TELEGRAM_CHAT_ID}.")
    except Exception as e:
        logger.error(f"Error al inicializar el bot de Telegram con el token proporcionado: {e}")
        bot = None
else:
    logger.warning("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados. Las notificaciones y comandos del bot no funcionarán.")

# Variables globales para los callbacks de funciones desde main.py
sync_function_callback = None
change_cron_interval_callback = None
disable_auto_sync_callback = None
enable_auto_sync_callback = None

# Bandera para intentar detener la sincronización en curso
stop_sync_flag = threading.Event()


# --- Funciones de Utilidad para enviar mensajes ---
def send_telegram(message: str) -> None:
    # Esta función ahora solo usa las variables globales bot y TELEGRAM_CHAT_ID
    # que se inicializan al inicio del módulo telegram_utils.py.
    # Si la inicialización falló (bot is None), o si el CHAT_ID no se cargó, no intentará enviar.
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
    chat_id_from_update = str(update.message.chat_id) # Convertir a string para comparación
    user = update.message.from_user
    # TELEGRAM_CHAT_ID ya es global y convertido a string al inicio del módulo

    if chat_id_from_update != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para usar este bot.")
        logger.warning(f"Intento de comando /start no autorizado desde chat_id: {chat_id_from_update}, usuario: {user.username}")
        return

    welcome_message = (
        "Hello there! 👋 I'm your Raspberry Pi Data Sync Bot. 🤖\n\n"
        "I'm here to help keep your data synchronized. For a list of commands, use /help.\n"
        "Please ensure your Raspberry Pi is powered on and accessible. 📡"
    )
    update.message.reply_text(welcome_message, parse_mode='Markdown')
    logger.info(f"Comando /start recibido de {user.username} (ID: {chat_id_from_update}). Mensaje de bienvenida enviado.")


def help_command(update, context):
    chat_id_from_update = str(update.message.chat_id) # Convertir a string para comparación
    user = update.message.from_user
    # TELEGRAM_CHAT_ID ya es global y convertido a string al inicio del módulo

    if chat_id_from_update != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para usar este bot.")
        logger.warning(f"Intento de comando /help no autorizado desde chat_id: {chat_id_from_update}, usuario: {user.username}")
        return

    help_message = (
        "Hello there! 👋 I'm your Raspberry Pi Data Sync Bot. 🤖\n\n"
        "Here are the commands you can use:\n"
        "  `/sync` - Triggers a *manual data synchronization* from your Raspberry Pi. 🚀\n"
        "  `/set_interval <minutes>` - Changes the automatic sync interval (e.g., `/set_interval 60` for hourly). ⏱️\n"
        "  `/disable_sync` - **Disables** automatic scheduled synchronization. 🚫\n"
        "  `/enable_sync` - **Enables** automatic scheduled synchronization (uses current interval). ✅\n"
        "  `/stop` - Attempts to *stop* a currently running synchronization or prevents the next one from starting. 🛑\n"
        "  `/start` - Shows a welcome message and introduction to the bot.\n"
        "  `/help` - Shows this help message with available commands.\n\n"
        "Please ensure your Raspberry Pi is powered on and accessible. 📡\n"
        "You'll receive notifications for every sync! ✨"
    )
    update.message.reply_text(help_message, parse_mode='Markdown')
    logger.info(f"Comando /help recibido de {user.username} (ID: {chat_id_from_update}). Mensaje de ayuda enviado.")


def start_sync_command(update, context):
    chat_id_from_update = str(update.message.chat_id) # Convertir a string para comparación
    user = update.message.from_user
    # TELEGRAM_CHAT_ID ya es global y convertido a string al inicio del módulo

    if chat_id_from_update != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para ejecutar este comando.")
        logger.warning(f"Intento de comando /sync no autorizado desde chat_id: {chat_id_from_update}, usuario: {user.username}")
        return

    if stop_sync_flag.is_set():
        update.message.reply_text("Cannot start synchronization: a stop command was recently issued. Please wait or clear the flag if needed.")
        logger.warning("Attempted to start sync while stop_sync_flag is set.")
        return

    update.message.reply_text("`/sync` command received! Starting data synchronization now... 🚀")
    logger.info(f"Comando /sync recibido de {user.username} (ID: {chat_id_from_update}). Disparando sincronización.")

    if sync_function_callback:
        # Ejecutar la función de sincronización en un hilo separado para no bloquear el bot
        sync_thread = threading.Thread(target=sync_function_callback, args=("from",))
        sync_thread.start()
    else:
        update.message.reply_text("Internal error: Sync function is not configured.")
        logger.error("sync_function_callback not configured in telegram_utils. This is a programming error.")


def set_interval_command(update, context):
    chat_id_from_update = str(update.message.chat_id) # Convertir a string para comparación
    user = update.message.from_user
    # TELEGRAM_CHAT_ID ya es global y convertido a string al inicio del módulo

    if chat_id_from_update != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para ejecutar este comando.")
        logger.warning(f"Intento de comando /set_interval no autorizado desde chat_id: {chat_id_from_update}, usuario: {user.username}")
        return

    args = context.args
    if not args or not args[0].isdigit():
        update.message.reply_text("Usage: `/set_interval <minutes>` (e.g., `/set_interval 60` for every hour).")
        return

    interval_minutes = int(args[0])
    if interval_minutes <= 0:
        update.message.reply_text("The interval must be a positive number of minutes.")
        return

    if change_cron_interval_callback:
        update.message.reply_text(f"Attempting to change sync interval to every `{interval_minutes}` minutes... This may take a few seconds. ⏱️")
        logger.info(f"Comando /set_interval received from {user.username}. Interval: {interval_minutes} minutes.")
        threading.Thread(target=change_cron_interval_callback, args=(interval_minutes,)).start()
    else:
        update.message.reply_text("Internal error: The function to change cron is not configured.")
        logger.error("change_cron_interval_callback not configured in telegram_utils.")


def disable_sync_command(update, context):
    chat_id_from_update = str(update.message.chat_id) # Convertir a string para comparación
    user = update.message.from_user
    # TELEGRAM_CHAT_ID ya es global y convertido a string al inicio del módulo

    if chat_id_from_update != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para ejecutar este comando.")
        logger.warning(f"Intento de comando /disable_sync no autorizado desde chat_id: {chat_id_from_update}, usuario: {user.username}")
        return

    if disable_auto_sync_callback:
        update.message.reply_text("Attempting to **disable** automatic sync... 🚫")
        logger.info(f"Comando /disable_sync received from {user.username}.")
        threading.Thread(target=disable_auto_sync_callback).start()
    else:
        update.message.reply_text("Internal error: Disable sync function not configured.")
        logger.error("disable_auto_sync_callback not configured in telegram_utils.")


def enable_sync_command(update, context):
    chat_id_from_update = str(update.message.chat_id) # Convertir a string para comparación
    user = update.message.from_user
    # TELEGRAM_CHAT_ID ya es global y convertido a string al inicio del módulo

    if chat_id_from_update != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para ejecutar este comando.")
        logger.warning(f"Intento de comando /enable_sync no autorizado desde chat_id: {chat_id_from_update}, usuario: {user.username}")
        return

    if enable_auto_sync_callback:
        update.message.reply_text("Attempting to **enable** automatic sync... ✅")
        logger.info(f"Comando /enable_sync received from {user.username}.")
        threading.Thread(target=enable_auto_sync_callback).start()
    else:
        update.message.reply_text("Internal error: Enable sync function not configured.")
        logger.error("enable_auto_sync_callback not configured in telegram_utils.")


def stop_sync_command(update, context):
    chat_id_from_update = str(update.message.chat_id) # Convertir a string para comparación
    user = update.message.from_user
    # TELEGRAM_CHAT_ID ya es global y convertido a string al inicio del módulo

    if chat_id_from_update != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para ejecutar este comando.")
        logger.warning(f"Intento de comando /stop no autorizado desde chat_id: {chat_id_from_update}, usuario: {user.username}")
        return

    if stop_sync_flag.is_set():
        update.message.reply_text("Synchronization is already marked for stopping or no active sync can be stopped by command.")
        logger.info("Stop command received, but flag was already set.")
    else:
        stop_sync_flag.set()
        update.message.reply_text("`/stop` command received! The current synchronization will attempt to stop as soon as possible. 🛑")
        logger.info(f"Comando /stop received from {user.username}. Stop flag set.")


def error_handler(update, context):
    """Log Errors caused by Updates."""
    logger.warning(f'Update "{update}" caused error "{context.error}"')

# --- Función para iniciar el Listener del Bot ---
def start_telegram_bot_listener(sync_func, cron_change_func, disable_sync_func, enable_sync_func):
    """
    Inicializa y arranca el listener del bot de Telegram.
    Recibe las funciones de callback de main.py.
    """
    global sync_function_callback
    global change_cron_interval_callback
    global disable_auto_sync_callback
    global enable_auto_sync_callback
    # Las variables globales TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID y bot
    # ya se inicializan al cargar el módulo, no es necesario volver a leerlas aquí.

    # Asigna las funciones de callback
    sync_function_callback = sync_func
    change_cron_interval_callback = cron_change_func
    disable_auto_sync_callback = disable_sync_func
    enable_auto_sync_callback = enable_sync_func

    # Verifica si el token y la instancia del bot están disponibles (ya inicializados globalmente)
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN no configurado. No se puede iniciar el listener del bot.")
        return

    if not bot:
        logger.error("La instancia del bot de Telegram no está disponible. No se puede iniciar el listener.")
        return

    try:
        # Inicializa el Updater con el token (que ya debe estar cargado)
        updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
        dispatcher = updater.dispatcher

        # Añade los handlers de comandos
        dispatcher.add_handler(CommandHandler("start", start_command))
        dispatcher.add_handler(CommandHandler("help", help_command))
        dispatcher.add_handler(CommandHandler("sync", start_sync_command))
        dispatcher.add_handler(CommandHandler("set_interval", set_interval_command))
        dispatcher.add_handler(CommandHandler("disable_sync", disable_sync_command))
        dispatcher.add_handler(CommandHandler("enable_sync", enable_sync_command))
        dispatcher.add_handler(CommandHandler("stop", stop_sync_command))

        # Añade el handler de errores
        dispatcher.add_error_handler(error_handler)

        # Inicia el polling del bot (escuchando mensajes)
        updater.start_polling()
        logger.info("Telegram Bot: Listener iniciado y en modo polling.")

    except Exception as e:
        logger.error(f"Fallo crítico al iniciar el listener del bot de Telegram: {e}")