import os
import telegram
import logging
import threading

from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Variables Globales para el Bot ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = None
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    try:
        TELEGRAM_CHAT_ID = str(TELEGRAM_CHAT_ID)
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        logger.info(f"Bot de Telegram inicializado correctamente con token y CHAT_ID: {TELEGRAM_CHAT_ID}.")
    except Exception as e:
        logger.error(f"Error al inicializar el bot de Telegram: {e}")
        bot = None
else:
    logger.warning("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados. El bot no funcionará.")

# --- Callbacks ---
sync_function_callback = None
change_cron_interval_callback = None
disable_auto_sync_callback = None
enable_auto_sync_callback = None
disk_status_callback = None
status_callback = None

# La variable stop_sync_flag se ha eliminado de este módulo
# ya que su control directo por el usuario a través del bot ya no es una funcionalidad deseada.

# --- Funciones de Utilidad ---
def send_telegram(message: str) -> None:
    if bot and TELEGRAM_CHAT_ID:
        try:
            # Importante: Si sigues viendo errores de "BadRequest: Can't parse entities: character '.' is reserved...",
            # deberás cambiar 'Markdown' a 'MarkdownV2' y escapar manualmente los caracteres problemáticos
            # en los mensajes, o implementar una función de escape global como se sugirió anteriormente.
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
            logger.info(f"Mensaje de Telegram enviado: {message[:50]}...")
        except telegram.error.Unauthorized:
            logger.error("Error: Token inválido.")
        except telegram.error.BadRequest as e:
            logger.error(f"Error BadRequest: {e}")
            # Agrega el log del mensaje original para depuración si ocurre un BadRequest
            logger.error(f"Message causing BadRequest: {message}")
        except Exception as e:
            logger.error(f"Error al enviar mensaje: {e}")
    else:
        logger.warning("Bot no inicializado o CHAT_ID no configurado.")

# --- Comandos ---
def start_command(update, context):
    chat_id = str(update.message.chat_id)
    user = update.message.from_user

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado.")
        return

    welcome_message = (
        "Hello! 👋 I'm your Raspberry Pi Data Sync Bot. 🤖\n"
        "Choose an option or use /help for all commands:"
    )

    # Teclado sin botones de stop/clear
    keyboard = [
        [InlineKeyboardButton("🚀 Sync Now", callback_data='sync_now')],
        [InlineKeyboardButton("⏱️ Set Interval", callback_data='set_interval')],
        [InlineKeyboardButton("✅ Enable Auto Sync", callback_data='enable_sync'),
         InlineKeyboardButton("🚫 Disable Auto Sync", callback_data='disable_sync')],
        [InlineKeyboardButton("💾 Disk Status", callback_data='disk_status'),
         InlineKeyboardButton("📊 System Status", callback_data='status')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(welcome_message, reply_markup=reply_markup)
    logger.info(f"/start from {user.username} ({chat_id})")

def help_command(update, context):
    chat_id = str(update.message.chat_id)
    user = update.message.from_user

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado.")
        return

    # Mensaje de ayuda sin el comando /stop
    help_message = (
        "Here are the commands:\n"
        "`/sync` - Manual sync 🚀\n"
        "`/set_interval` - Change interval ⏱️\n"
        "`/disable_sync` - Disable auto sync 🚫\n"
        "`/enable_sync` - Enable auto sync ✅\n"
        "`/start` - Show menu with buttons\n"
        "`/disk_status` - Show disk usage 💾\n"
        "`/status` - Show system status 📊\n"
        "`/help` - This help\n"
    )
    update.message.reply_text(help_message, parse_mode='Markdown')

def start_sync_command(update, context):
    chat_id = str(update.message.chat_id)

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado.")
        return

    # Se elimina la verificación de stop_sync_flag aquí
    update.message.reply_text("`/sync` received! Starting sync... 🚀", parse_mode='Markdown')
    if sync_function_callback:
        threading.Thread(target=sync_function_callback, args=("from",)).start()

def set_interval_command(update, context):
    chat_id = str(update.message.chat_id)

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado.")
        return

    args = context.args
    if not args or not args[0].isdigit():
        update.message.reply_text("Usage: `/set_interval <minutes>`", parse_mode='Markdown')
        return

    minutes = int(args[0])
    if minutes <= 0:
        update.message.reply_text("Must be > 0 minutes.")
        return

    if change_cron_interval_callback:
        update.message.reply_text(f"Changing interval to every `{minutes}` min...")
        threading.Thread(target=change_cron_interval_callback, args=(minutes,)).start()

def disable_sync_command(update, context):
    chat_id = str(update.message.chat_id)

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado.")
        return

    if disable_auto_sync_callback:
        update.message.reply_text("Disabling auto sync... 🚫")
        threading.Thread(target=disable_auto_sync_callback).start()

def enable_sync_command(update, context):
    chat_id = str(update.message.chat_id)

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado.")
        return

    if enable_auto_sync_callback:
        update.message.reply_text("Enabling auto sync... ✅")
        threading.Thread(target=enable_auto_sync_callback).start()

# La función stop_sync_command se ha eliminado.

def disk_status_command(update, context):
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text("No autorizado.")
        return
    if disk_status_callback:
        update.message.reply_text("💾 Verificando estado del disco...")
        threading.Thread(target=disk_status_callback).start()

def status_command(update, context):
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text("📊 Verificando estado general del sistema...")
        if status_callback:
            threading.Thread(target=status_callback).start()

# --- Botón Callback ---
def button_callback(update, context):
    query = update.callback_query
    query.answer()
    chat_id = str(query.message.chat_id)

    if chat_id != TELEGRAM_CHAT_ID:
        query.edit_message_text("No autorizado.")
        return

    if query.data == 'sync_now':
        query.edit_message_text("Sync Now 🚀 ...")
        if sync_function_callback:
            threading.Thread(target=sync_function_callback, args=("from",)).start()

    elif query.data == 'enable_sync':
        query.edit_message_text("Enabling auto sync... ✅")
        if enable_auto_sync_callback:
            threading.Thread(target=enable_auto_sync_callback).start()

    elif query.data == 'disable_sync':
        query.edit_message_text("Disabling auto sync... 🚫")
        if disable_auto_sync_callback:
            threading.Thread(target=disable_auto_sync_callback).start()

    # Se eliminan los casos para 'stop_sync' y 'clear_stop' del callback.

    elif query.data == 'disk_status':
        query.edit_message_text("💾 Checking disk status...")
        if disk_status_callback:
            threading.Thread(target=disk_status_callback).start()

    elif query.data == 'set_interval':
        query.edit_message_text("Use `/set_interval <minutes>` ⏱️", parse_mode='Markdown')

    elif query.data == 'status':
        query.edit_message_text("📊 Gathering system status...")
        if status_callback:
            threading.Thread(target=status_callback).start()

def error_handler(update, context):
    logger.warning(f'Update "{update}" caused error "{context.error}"')

# --- Arranque del Listener ---
def start_telegram_bot_listener(sync_func, cron_change_func, disable_sync_func, enable_sync_func,
                                disk_func=None, status_func=None):
    global sync_function_callback
    global change_cron_interval_callback
    global disable_auto_sync_callback
    global enable_auto_sync_callback
    global disk_status_callback
    global status_callback

    sync_function_callback = sync_func
    change_cron_interval_callback = cron_change_func
    disable_auto_sync_callback = disable_sync_func
    enable_auto_sync_callback = enable_sync_func
    disk_status_callback = disk_func
    status_callback = status_func

    if not TELEGRAM_BOT_TOKEN or not bot:
        logger.error("No TELEGRAM_BOT_TOKEN. Bot no arrancará.")
        return

    try:
        updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
        dispatcher = updater.dispatcher

        dispatcher.add_handler(CommandHandler("start", start_command))
        dispatcher.add_handler(CommandHandler("help", help_command))
        dispatcher.add_handler(CommandHandler("sync", start_sync_command))
        dispatcher.add_handler(CommandHandler("set_interval", set_interval_command))
        dispatcher.add_handler(CommandHandler("disable_sync", disable_sync_command))
        dispatcher.add_handler(CommandHandler("enable_sync", enable_sync_command))
        # Se elimina el manejador para el comando /stop
        # dispatcher.add_handler(CommandHandler("stop", stop_sync_command))
        dispatcher.add_handler(CommandHandler("disk_status", disk_status_command))
        dispatcher.add_handler(CommandHandler("status", status_command))
        dispatcher.add_handler(CallbackQueryHandler(button_callback))
        dispatcher.add_error_handler(error_handler)

        updater.start_polling()
        logger.info("Telegram Bot: Listener iniciado.")
    except Exception as e:
        logger.error(f"Fallo al iniciar el bot: {e}")