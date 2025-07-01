"""
File: utils/telegram_utils.py
Description: This module provides utility functions and command handlers for a Telegram bot
             that interacts with a Raspberry Pi synchronization service. It handles
             communication with the Telegram API, processes user commands, and triggers
             corresponding actions in the main application logic (e.g., synchronization,
             cron job modifications, system status reports).

Author: Roberto Toapanta
Date: 2025-06-27
Version: 1.0.0
License: MIT License
"""

import os
import telegram
import logging
import threading

from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from utils.env_utils import get_env_variable  # 👈 integración desde env_utils

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Global Variables for the Bot ---
TELEGRAM_BOT_TOKEN = get_env_variable("TELEGRAM_BOT_TOKEN", required=True)
TELEGRAM_CHAT_ID = str(get_env_variable("TELEGRAM_CHAT_ID", required=True))

bot = None
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    try:
        TELEGRAM_CHAT_ID = str(TELEGRAM_CHAT_ID)
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        logger.info(f"Telegram bot initialized successfully with token and CHAT_ID: {TELEGRAM_CHAT_ID}.")
    except Exception as e:
        logger.error(f"Error initializing Telegram bot: {e}")
        bot = None
else:
    logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured. Bot will not function.")

# --- Callbacks ---
# These global variables will hold references to functions from main.py
# to be called by Telegram bot commands/buttons. They are set in start_telegram_bot_listener.
sync_function_callback = None
change_cron_interval_callback = None
disable_auto_sync_callback = None
enable_auto_sync_callback = None
disk_status_callback = None
status_callback = None
change_sync_directory_callback = None # <--- AÑADIDO: Nuevo callback para cambiar el directorio de sincronización

# --- Utility Functions ---
def send_telegram(message: str) -> None:
    """
    Sends a message to the configured Telegram chat.

    Args:
        message (str): The message text to send. Supports Markdown parsing.
    """
    if bot and TELEGRAM_CHAT_ID:
        try:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
            logger.info(f"Telegram message sent: {message[:50]}...")
        except telegram.error.Unauthorized:
            logger.error("Error: Invalid bot token.")
        except telegram.error.BadRequest as e:
            logger.error(f"Error BadRequest: {e}")
            logger.error(f"Message causing BadRequest: {message}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")
    else:
        logger.warning("Bot not initialized or CHAT_ID not configured.")

# --- Command Handlers ---
def close_command(update: Update, context: CallbackContext) -> None:
    """
    Handles the /close command. Pauses the system and solicita nueva IP.
    """
    chat_id = str(update.message.chat_id)
    user = update.message.from_user

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Sorry, you are not authorized to use this bot.")
        logger.warning(f"Unauthorized /close command from {user.username} ({chat_id})")
        return

    welcome_message = (
        "Hello Roberto! 👋 I'm your Raspberry Pi Data Sync Bot. 🤖\n"
        "Por favor, ingresa la IP del host remoto para sincronizar (ejemplo: 192.168.1.100):"
    )
    context.user_data['awaiting_remote_ip'] = True
    # Crear flag para pausar sincronización automática
    try:
        with open("/logs/awaiting_ip.flag", "w") as f:
            f.write("waiting for remote ip\n")
    except Exception as e:
        logger.error(f"No se pudo crear el flag de pausa de sincronización: {e}")
    update.message.reply_text("🔴 Conexión cerrada. Por favor, inicia nuevamente /start e ingresa la nueva IP para continuar.")
    # update.message.reply_text(welcome_message)
    logger.info(f"/close command received from {user.username} ({chat_id})")

def start_command(update: Update, context: CallbackContext) -> None:
    """
    Handles the /start command. Sends a welcome message and requests the remote IP.
    Only authorized chat IDs can use this command.
    """
    chat_id = str(update.message.chat_id)
    user = update.message.from_user

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Sorry, you are not authorized to use this bot.")
        logger.warning(f"Unauthorized /start command from {user.username} ({chat_id})")
        return

    welcome_message = (
        "Hello Roberto! 👋 I'm your Raspberry Pi Data Sync Bot. 🤖\n"
        "Por favor, ingresa la IP del host remoto para sincronizar (ejemplo: 192.168.1.100):"
    )
    context.user_data['awaiting_remote_ip'] = True
    # Crear flag para pausar sincronización automática
    try:
        with open("/logs/awaiting_ip.flag", "w") as f:
            f.write("waiting for remote ip\n")
    except Exception as e:
        logger.error(f"No se pudo crear el flag de pausa de sincronización: {e}")
    update.message.reply_text(welcome_message)
    logger.info(f"/start command received from {user.username} ({chat_id})")

def help_command(update: Update, context: CallbackContext) -> None:
    """
    Handles the /help command. Sends a list of available commands.
    Only authorized chat IDs can use this command.
    """
    chat_id = str(update.message.chat_id)
    user = update.message.from_user

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Sorry, you are not authorized to use this bot.")
        logger.warning(f"Unauthorized /help command from {user.username} ({chat_id})")
        return

    help_message = (
        "Here are the commands:\n"
        "`/sync` - Manual sync 🚀\n"
        "`/set_interval` - Change auto sync interval <minutes> (manual) ⏱️\n"
        "`/set_interval` - Show interval options ⏱️\n"
        "`/disable_sync` - Disable auto sync 🚫\n"
        "`/enable_sync` - Enable auto sync ✅\n"
        "`/change_source <user@host:/path>` - Change the remote sync source 🔄\n" # <--- AÑADIDO: Descripción del nuevo comando
        "`/start` - Show menu with buttons\n"
        "`/disk_status` - Show disk usage 💾\n"
        "`/status` - Show system status 📊\n"
        "`/help` - This help\n"
    )
    update.message.reply_text(help_message, parse_mode='Markdown')
    logger.info(f"/help command received from {user.username} ({chat_id})")

def start_sync_command(update: Update, context: CallbackContext) -> None:
    """
    Handles the /sync command. Triggers a manual synchronization operation.
    Only authorized chat IDs can use this command.
    """
    chat_id = str(update.message.chat_id)

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Sorry, you are not authorized to use this bot.")
        logger.warning(f"Unauthorized /sync command from {chat_id}")
        return

    update.message.reply_text("`/sync` received! Starting sync... 🚀", parse_mode='Markdown')
    if sync_function_callback:
        # Run the sync function in a separate thread to avoid blocking the bot's main loop
        threading.Thread(target=sync_function_callback, args=("from",)).start()
    logger.info(f"/sync command received from {chat_id}")

def set_interval_command(update: Update, context: CallbackContext) -> None:
    """
    Handles the /set_interval command. If no arguments are provided, it displays
    a menu for predefined intervals. If an argument (minutes) is provided, it
    attempts to set the cron interval manually.
    Only authorized chat IDs can use this command.
    """
    chat_id = str(update.message.chat_id)

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Sorry, you are not authorized to use this bot.")
        logger.warning(f"Unauthorized /set_interval command from {chat_id}")
        return

    args = context.args
    if not args:
        # If no arguments, display the interval selection menu
        keyboard = [
            [InlineKeyboardButton("Every 1 minute", callback_data='set_interval_1')],
            [InlineKeyboardButton("Every 15 minutes", callback_data='set_interval_15')],
            [InlineKeyboardButton("Every 30 minutes", callback_data='set_interval_30')],
            [InlineKeyboardButton("Every hour (60 min)", callback_data='set_interval_60')],
            [InlineKeyboardButton("Every 4 hours (240 min)", callback_data='set_interval_240')],
            [InlineKeyboardButton("Every 24 hours (1440 min)", callback_data='set_interval_1440')],
            [InlineKeyboardButton("Enter manually", callback_data='set_interval_manual_prompt')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Select a sync interval or enter one manually:", reply_markup=reply_markup)
        logger.info(f"/set_interval command (menu) received from {chat_id}")
        return

    # If arguments are provided, attempt to set the interval manually
    try:
        minutes = int(args[0])
        if minutes <= 0:
            update.message.reply_text("The interval must be a positive number of minutes.")
            logger.warning(f"/set_interval command with invalid argument '{args[0]}' from {chat_id}")
            return

        if change_cron_interval_callback:
            update.message.reply_text(f"Changing interval to every `{minutes}` minutes...", parse_mode='Markdown')
            threading.Thread(target=change_cron_interval_callback, args=(minutes,)).start()
            logger.info(f"/set_interval command (manual: {minutes} min) received from {chat_id}")
    except ValueError:
        update.message.reply_text("Incorrect usage. Please enter a valid number of minutes, or use `/set_interval` without arguments to see options.", parse_mode='Markdown')
        logger.warning(f"/set_interval command with non-numeric argument '{args[0]}' from {chat_id}")


def disable_sync_command(update: Update, context: CallbackContext) -> None:
    """
    Handles the /disable_sync command. Disables automatic synchronization in cron.
    Only authorized chat IDs can use this command.
    """
    chat_id = str(update.message.chat_id)

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Sorry, you are not authorized to use this bot.")
        logger.warning(f"Unauthorized /disable_sync command from {chat_id}")
        return

    if disable_auto_sync_callback:
        update.message.reply_text("Disabling auto synchronization... 🚫")
        threading.Thread(target=disable_auto_sync_callback).start()
    logger.info(f"/disable_sync command received from {chat_id}")

def enable_sync_command(update: Update, context: CallbackContext) -> None:
    """
    Handles the /enable_sync command. Enables automatic synchronization in cron.
    Only authorized chat IDs can use this command.
    """
    chat_id = str(update.message.chat_id)

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Sorry, you are not authorized to use this bot.")
        logger.warning(f"Unauthorized /enable_sync command from {chat_id}")
        return

    if enable_auto_sync_callback:
        update.message.reply_text("Enabling auto synchronization... ✅")
        threading.Thread(target=enable_auto_sync_callback).start()
    logger.info(f"/enable_sync command received from {chat_id}")

def disk_status_command(update: Update, context: CallbackContext) -> None:
    """
    Handles the /disk_status command. Requests a disk status report.
    Only authorized chat IDs can use this command.
    """
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text("Unauthorized.")
        logger.warning(f"Unauthorized /disk_status command from {str(update.message.chat_id)}")
        return
    if disk_status_callback:
        update.message.reply_text("💾 Checking disk status...")
        threading.Thread(target=disk_status_callback).start()
    logger.info(f"/disk_status command received from {str(update.message.chat_id)}")

def status_command(update: Update, context: CallbackContext) -> None:
    """
    Handles the /status command. Requests a general system status report.
    Only authorized chat IDs can use this command.
    """
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text("Unauthorized.")
        logger.warning(f"Unauthorized /status command from {str(update.message.chat_id)}")
        return
    update.message.reply_text("📊 Checking general system status...")
    if status_callback:
        threading.Thread(target=status_callback).start()
    logger.info(f"/status command received from {str(update.message.chat_id)}")

# <--- AÑADIDO: Nuevo comando para cambiar el directorio de sincronización ---
def change_sync_directory_command(update: Update, context: CallbackContext) -> None:
    """
    Handles the /change_source <user@host:/path> command.
    Changes the remote rsync source path.
    Only authorized chat IDs can use this command.
    """
    chat_id = str(update.message.chat_id)

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Sorry, you are not authorized to use this bot.")
        logger.warning(f"Unauthorized /change_source command from {chat_id}")
        return

    args = context.args
    if not args:
        update.message.reply_text("Usage: `/change_source <user@host:/path/to/source>`\n\nExample: `/change_source pi@192.168.1.100:/home/pi/data`", parse_mode='Markdown')
        logger.warning(f"/change_source command with no arguments from {chat_id}")
        return

    new_path = args[0]
    # Validar formato: debe contener '@' y ':'
    if '@' not in new_path or ':' not in new_path:
        update.message.reply_text(
            "❌ Invalid format. Please use `/change_source user@host:/path/to/source`\n\nExample: `/change_source pi@192.168.1.100:/home/pi/data`",
            parse_mode='Markdown')
        logger.warning(f"/change_source command with invalid format from {chat_id}: {new_path}")
        return
    update.message.reply_text(f"Attempting to change sync source to: `{new_path}` 🔄", parse_mode='Markdown')

    if change_sync_directory_callback:
        # Run the callback in a separate thread to avoid blocking
        threading.Thread(target=change_sync_directory_callback, args=(new_path,)).start()
    else:
        update.message.reply_text("Error: Sync directory change function not configured. ❌")
        logger.error("change_sync_directory_callback is not set.")

    logger.info(f"/change_source command received from {chat_id} with path: {new_path}")
# --- FIN AÑADIDO: Nuevo comando ---


# --- Button Callback Handler ---
def button_callback(update: Update, context: CallbackContext) -> None:
    """
    Handles inline keyboard button presses.
    Processes different `callback_data` values to trigger corresponding actions.
    Only authorized chat IDs can use this command.
    """
    query = update.callback_query
    query.answer() # Acknowledge the query to remove the loading animation on the button
    chat_id = str(query.message.chat_id)

    # Bloquear acciones si se está esperando la IP remota
    if context.user_data.get('awaiting_remote_ip', False):
        query.edit_message_text("⚠️ Debes ingresar primero la IP del host remoto para continuar. Usa /start para iniciar la configuración.")
        return

    # Bloquear acciones si el sistema está en pausa (flag existe), excepto Start System
    import os
    # Solo bloquear botones críticos durante la pausa
    botones_criticos = ['sync_now', 'enable_sync', 'disable_sync']
    if os.path.exists("/logs/awaiting_ip.flag") and query.data in botones_criticos:
        keyboard = [
            [InlineKeyboardButton("🟢 Start System", callback_data='start_system')],
            [InlineKeyboardButton("🏠 Volver al menú", callback_data='show_main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("⚠️ El sistema está en pausa. Pulsar 'Start System' para habilitar las funciones, iniciar /start para reiniciar la configuración.", reply_markup=reply_markup)
        return

    # Lógica para el botón Volver al menú
    if query.data == 'show_main_menu':
        # Mostrar menú principal según el estado del sistema
        import os
        flag_pausa = os.path.exists("/logs/awaiting_ip.flag")
        keyboard = [
            [InlineKeyboardButton("🚀 Sync Now", callback_data='sync_now'),
             InlineKeyboardButton("🔄 Change Sync Source", callback_data='change_source_prompt')],
            [InlineKeyboardButton("⏱️ Set Interval", callback_data='set_interval_menu')],
            [InlineKeyboardButton("✅ Enable Auto Sync", callback_data='enable_sync'),
             InlineKeyboardButton("🚫 Disable Auto Sync", callback_data='disable_sync')],
            [InlineKeyboardButton("💾 Disk Status", callback_data='disk_status'),
             InlineKeyboardButton("📊 System Status", callback_data='status')],
            [InlineKeyboardButton("📂 View Directory Tree", callback_data='show_tree')]
        ]
        # Si está en pausa, añadir Start System
        if flag_pausa:
            keyboard.append([InlineKeyboardButton("🟢 Start System", callback_data='start_system')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(chat_id=chat_id, text="Menú principal:", reply_markup=reply_markup)
        query.edit_message_reply_markup(reply_markup=None)
        return

    # Lógica para el botón Start System
    if query.data == 'start_system':
        try:
            if os.path.exists("/logs/awaiting_ip.flag"):
                os.remove("/logs/awaiting_ip.flag")
        except Exception as e:
            context.bot.send_message(chat_id=chat_id, text=f"⚠️ No se pudo eliminar el flag de pausa: {e}")
        # Mostrar menú principal habilitado
        keyboard = [
            [
                InlineKeyboardButton("🚀 Sync Now", callback_data='sync_now'),
                InlineKeyboardButton("🔄 Change Sync Source", callback_data='change_source_prompt')
            ],
            [InlineKeyboardButton("⏱️ Set Interval", callback_data='set_interval_menu')],
            [InlineKeyboardButton("✅ Enable Auto Sync", callback_data='enable_sync'),
             InlineKeyboardButton("🚫 Disable Auto Sync", callback_data='disable_sync')],
            [InlineKeyboardButton("💾 Disk Status", callback_data='disk_status'),
             InlineKeyboardButton("📊 System Status", callback_data='status')],
            [InlineKeyboardButton("📂 View Directory Tree", callback_data='show_tree')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(chat_id=chat_id, text="🟢 Sistema habilitado. Elige una opción:", reply_markup=reply_markup)
        query.edit_message_reply_markup(reply_markup=None)
        return

    if chat_id != TELEGRAM_CHAT_ID:
        query.edit_message_text("Unauthorized.")
        logger.warning(f"Unauthorized button callback from {chat_id} (data: {query.data})")
        return

    logger.info(f"Button callback '{query.data}' received from {chat_id}")

    if query.data == 'sync_now':
        query.edit_message_text("Sync Now 🚀 ...")
        if sync_function_callback:
            threading.Thread(target=sync_function_callback, args=("from",)).start()

    elif query.data == 'enable_sync':
        query.edit_message_text("Enabling auto synchronization... ✅")
        if enable_auto_sync_callback:
            threading.Thread(target=enable_auto_sync_callback).start()

    elif query.data == 'disable_sync':
        query.edit_message_text("Disabling auto synchronization... 🚫")
        if disable_auto_sync_callback:
            threading.Thread(target=disable_auto_sync_callback).start()

    elif query.data == 'disk_status':
        # Llama directamente y envía el resultado como nuevo mensaje
        if disk_status_callback:
            disk_status_callback(update, context)
        else:
            query.edit_message_text("No hay función de estado de disco configurada.")

    elif query.data == 'set_interval_menu':
        # Display the interval selection menu
        keyboard = [
            [InlineKeyboardButton("Every 1 minute", callback_data='set_interval_1')],
            [InlineKeyboardButton("Every 15 minutes", callback_data='set_interval_15')],
            [InlineKeyboardButton("Every 30 minutes", callback_data='set_interval_30')],
            [InlineKeyboardButton("Every hour (60 min)", callback_data='set_interval_60')],
            [InlineKeyboardButton("Every 4 hours (240 min)", callback_data='set_interval_240')],
            [InlineKeyboardButton("Every 24 hours (1440 min)", callback_data='set_interval_1440')],
            [InlineKeyboardButton("Enter manually", callback_data='set_interval_manual_prompt')],
            [InlineKeyboardButton("🏠 Volver al menú", callback_data='show_main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("Select a sync interval or enter one manually:", reply_markup=reply_markup)

    elif query.data.startswith('set_interval_'):
        if query.data == 'set_interval_manual_prompt':
            # Instruct the user how to enter the manual value
            context.bot.send_message(chat_id=chat_id, text="Please enter the desired interval in minutes using the command: `/set_interval <minutes>`", parse_mode='Markdown')
            # Remove buttons from the original message to avoid confusion/double clicks
            query.edit_message_reply_markup(reply_markup=None) 

        else:
            minutes_str = query.data.replace('set_interval_', '')
            try:
                minutes = int(minutes_str)
                query.edit_message_text(f"Changing interval to every `{minutes}` minutes...", parse_mode='Markdown')
                if change_cron_interval_callback:
                    threading.Thread(target=change_cron_interval_callback, args=(minutes,)).start()
            except ValueError:
                query.edit_message_text("Error: Invalid time interval.")

    elif query.data == 'status':
        # Llama directamente y envía el resultado como nuevo mensaje
        if status_callback:
            status_callback(update, context)
        else:
            query.edit_message_text("No hay función de estado del sistema configurada.")
    
    elif query.data == 'show_tree':
        query.edit_message_text("Obteniendo árbol de directorios (nivel 3)...")
        show_tree_command(update, context)
    elif query.data == 'change_source_prompt':
        # Mostrar botones secundarios para elegir el tipo de cambio de directorio
        keyboard = [
            [
                InlineKeyboardButton("📁 Default Directory", callback_data='default_directory'),
                InlineKeyboardButton("🌐 Remote Directory", callback_data='remote_directory'),
                InlineKeyboardButton("🏠 Volver al menú", callback_data='show_main_menu')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(chat_id=chat_id, text="Selecciona el tipo de directorio de sincronización:", reply_markup=reply_markup)
        query.edit_message_reply_markup(reply_markup=None)

    elif query.data == 'default_directory':
        # Cambiar el origen de sincronización al valor por defecto
        from utils.constants import DEFAULT_RSYNC_FROM
        if change_sync_directory_callback:
            context.bot.send_message(chat_id=chat_id, text=f"Changing sync source to default: `{DEFAULT_RSYNC_FROM}`", parse_mode='Markdown')
            import threading
            threading.Thread(target=change_sync_directory_callback, args=(DEFAULT_RSYNC_FROM,)).start()
        else:
            context.bot.send_message(chat_id=chat_id, text="Error: Sync directory change function not configured.")
        query.edit_message_reply_markup(reply_markup=None)

    elif query.data == 'remote_directory':
        # Limpiar cualquier sesión SSH previa
        for k in ['ssh_session', 'sftp_session', 'ssh_root', 'ssh_username', 'ssh_host', 'ssh_key_path']:
            context.user_data.pop(k, None)
        # Conexión automática usando clave privada y usuario/host de la configuración
        from utils.constants import DEFAULT_RSYNC_FROM
        import re
        import paramiko
        # Extraer usuario y host de DEFAULT_RSYNC_FROM o RSYNC_FROM
        match = re.match(r"([\w\-]+)@([\w\.-]+):", DEFAULT_RSYNC_FROM)
        if not match:
            context.bot.send_message(chat_id=chat_id, text="❌ No se pudo extraer usuario y host de la configuración.")
            return
        username, host = match.group(1), match.group(2)
        key_path = "/root/.ssh/id_rsa"
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, username=username, key_filename=key_path, timeout=10)
            sftp = ssh.open_sftp()
            root = '/'
            dirs = []
            import stat
            for entry in sftp.listdir_attr(root):
                if stat.S_ISDIR(entry.st_mode):
                    dirs.append(entry.filename)
            keyboard = [[InlineKeyboardButton(d, callback_data=f'remote_nav:{root}{d}/')] for d in dirs]
            keyboard.append([InlineKeyboardButton("🏠 Volver al menú", callback_data='show_main_menu')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            context.bot.send_message(chat_id=chat_id, text=f"Directorio remoto: `{root}`\nSelecciona una carpeta:", reply_markup=reply_markup, parse_mode='Markdown')
            context.user_data['ssh_session'] = ssh
            context.user_data['sftp_session'] = sftp
            context.user_data['ssh_root'] = root
            context.user_data['ssh_username'] = username
            context.user_data['ssh_host'] = host
            context.user_data['ssh_key_path'] = key_path
        except Exception as e:
            context.bot.send_message(chat_id=chat_id, text=f"❌ Error de conexión SSH automática: {e}")
        query.edit_message_reply_markup(reply_markup=None)

    elif query.data.startswith('remote_nav:'):
        # Navegación por directorios remotos
        import paramiko
        path = query.data.replace('remote_nav:', '', 1)
        sftp = context.user_data.get('sftp_session')
        ssh = context.user_data.get('ssh_session')
        username = context.user_data.get('ssh_username')
        host = context.user_data.get('ssh_host')
        if not sftp or not ssh or not username or not host:
            context.bot.send_message(chat_id=chat_id, text="❌ Sesión SSH no encontrada. Reinicia el proceso.")
            return
        # Listar subdirectorios
        try:
            import stat
            dirs = []
            for entry in sftp.listdir_attr(path):
                if stat.S_ISDIR(entry.st_mode):
                    dirs.append(entry.filename)
            # Botón para seleccionar este directorio
            keyboard = [[InlineKeyboardButton("✅ Usar este directorio", callback_data=f'remote_select:{path}')]]
            # Botones para navegar a subdirectorios
            keyboard += [[InlineKeyboardButton(d, callback_data=f'remote_nav:{path}{d}/')] for d in dirs]
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(f"Directorio remoto: `{path}`\nSelecciona una carpeta o usa este directorio:", reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            context.bot.send_message(chat_id=chat_id, text=f"❌ Error al listar `{path}`: {e}")

    elif query.data.startswith('remote_select:'):
        # Selección final de directorio remoto
        path = query.data.replace('remote_select:', '', 1)
        username = context.user_data.get('ssh_username')
        host = context.user_data.get('ssh_host')
        if not username or not host:
            context.bot.send_message(chat_id=chat_id, text="❌ Sesión SSH no encontrada. Reinicia el proceso.")
            return
        remote_path = f"{username}@{host}:{path}"
        if change_sync_directory_callback:
            context.bot.send_message(chat_id=chat_id, text=f"🔄 Cambiando origen de sincronización a: `{remote_path}`", parse_mode='Markdown')
            import threading
            threading.Thread(target=change_sync_directory_callback, args=(remote_path,)).start()
        else:
            context.bot.send_message(chat_id=chat_id, text="Error: Sync directory change function not configured.")
        # Cerrar sesión SSH
        sftp = context.user_data.get('sftp_session')
        ssh = context.user_data.get('ssh_session')
        if sftp:
            sftp.close()
        if ssh:
            ssh.close()
        context.user_data.pop('sftp_session', None)
        context.user_data.pop('ssh_session', None)
        context.user_data.pop('ssh_username', None)
        context.user_data.pop('ssh_host', None)
        context.user_data.pop('ssh_password', None)
        context.user_data.pop('ssh_root', None)

def error_handler(update: Update, context: CallbackContext) -> None:
    """
    Log errors caused by updates.
    """
    logger.warning(f'Update "{update}" caused error "{context.error}"')

# --- Mostrar árbol de directorios ---
def show_tree_command(update, context):
    from managers.sync_manager import SyncManager
    chat_id = update.effective_chat.id
    try:
        sync_manager = SyncManager()
        output = sync_manager._get_dta_file_tree_string()
        # Telegram limita los mensajes a 4096 caracteres
        send_file = False
        file_path = "/logs/file_tree.log"
        if len(output) > 3500:
            output = output[:3500] + "\n... (truncado) ..."
            send_file = True
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [[InlineKeyboardButton("🏠 Volver al menú", callback_data='show_main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(chat_id=chat_id, text=output, parse_mode="Markdown", reply_markup=reply_markup)
        # Si es muy largo, enviar el archivo completo como documento
        if send_file:
            try:
                with open(file_path, "rb") as f:
                    context.bot.send_document(chat_id=chat_id, document=f, filename="file_tree.log", caption="Árbol de directorios completo")
            except Exception as e:
                context.bot.send_message(chat_id=chat_id, text=f"Error adjuntando archivo de árbol: {e}")
    except Exception as e:
        context.bot.send_message(chat_id=chat_id, text=f"Error mostrando el árbol de directorios: {e}")

# --- Handler para procesar la IP remota y mostrar el menú principal ---
def remote_ip_handler(update: Update, context: CallbackContext) -> None:
    """
    Handler para procesar la IP remota y actualizar la configuración.
    """
    if not context.user_data.get('awaiting_remote_ip'):
        return  # No estamos esperando IP

    chat_id = str(update.message.chat_id)
    ip = update.message.text.strip()
    import re
    # Validar IP básica
    if not re.match(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$", ip):
        update.message.reply_text("Formato de IP inválido. Intenta de nuevo (ejemplo: 192.168.1.100)")
        return
    # Actualizar RSYNC_FROM en el archivo de configuración
    from utils.constants import DEFAULT_RSYNC_FROM
    # Extraer usuario y path de DEFAULT_RSYNC_FROM
    match = re.match(r"([\w\-]+)@([\w\.-]+):(.*)", DEFAULT_RSYNC_FROM)
    if not match:
        update.message.reply_text("❌ No se pudo extraer usuario y ruta de la configuración base.")
        return
    username, _, path = match.group(1), match.group(2), match.group(3)
    new_rsync_from = f"{username}@{ip}:{path}"

    # Mensaje de inicio de conexión
    # update.message.reply_text("🔄 Iniciando conexión y validación SSH...")
    # Validar conectividad SSH antes de guardar
    import paramiko
    key_path = "/root/.ssh/id_rsa"
    ssh_ok = True
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, key_filename=key_path, timeout=7)
        ssh.close()
    except Exception as e:
        ssh_ok = False
        update.message.reply_text(f"❌ No se pudo establecer conexión SSH con la IP ingresada: {e}\nVerifica la red, la IP y que el host remoto tenga SSH habilitado. Usa /start para intentarlo de nuevo.")
    # Si la conexión SSH es exitosa, guardar y mostrar menú
    callback_ok = True
    if ssh_ok:
        # Actualizar la variable global RASPBERRY_URL
        try:
            # Actualizar RASPBERRY_URL en el archivo .env
            new_url = f"http://{ip}:8000/status"
            env_path = ".env"
            import re
            import os
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    lines = f.readlines()
                with open(env_path, "w") as f:
                    found = False
                    for line in lines:
                        if line.startswith("RASPBERRY_URL="):
                            f.write(f"RASPBERRY_URL={new_url}\n")
                            found = True
                        else:
                            f.write(line)
                    if not found:
                        f.write(f"RASPBERRY_URL={new_url}\n")
            else:
                with open(env_path, "w") as f:
                    f.write(f"RASPBERRY_URL={new_url}\n")
        except Exception as e:
            update.message.reply_text(f"⚠️ No se pudo actualizar RASPBERRY_URL en .env: {e}")
        try:
            if change_sync_directory_callback:
                import threading
                threading.Thread(target=change_sync_directory_callback, args=(new_rsync_from,)).start()
        except Exception as e:
            callback_ok = False
            update.message.reply_text(f"❌ Error al guardar la IP: {e}")
    # Limpiar flag ANTES de mostrar el menú (para evitar bloqueos en submenús)
    context.user_data['awaiting_remote_ip'] = False
    # Mostrar menú principal SIEMPRE si la conexión SSH fue exitosa
    if ssh_ok and callback_ok:
        update.message.reply_text("🟢 Conexión y validación SSH satisfactoria.")
        # NO eliminar flag aquí, solo mostrar menú con Start System
        welcome_message = (
            "✅ IP configurada y verificada correctamente.\n"
            "El sistema está en pausa. Pulsa 'Start System' para habilitar las funciones."
        )
    elif ssh_ok and not callback_ok:
        welcome_message = (
            "⚠️ El menú se muestra, pero hubo un error al guardar la IP.\n"
            "El sistema está en pausa. Pulsa 'Start System' para habilitar las funciones."
        )
    else:
        return  # No mostrar menú si la conexión SSH falló
    keyboard = [
        [
            InlineKeyboardButton("🚀 Sync Now", callback_data='sync_now'),
            InlineKeyboardButton("🔄 Change Sync Source", callback_data='change_source_prompt')
        ],
        [InlineKeyboardButton("⏱️ Set Interval", callback_data='set_interval_menu')],
        [InlineKeyboardButton("✅ Enable Auto Sync", callback_data='enable_sync'),
         InlineKeyboardButton("🚫 Disable Auto Sync", callback_data='disable_sync')],
        [InlineKeyboardButton("💾 Disk Status", callback_data='disk_status'),
         InlineKeyboardButton("📊 System Status", callback_data='status')],
        [InlineKeyboardButton("📂 View Directory Tree", callback_data='show_tree')],
        [InlineKeyboardButton("🟢 Start System", callback_data='start_system')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(welcome_message, reply_markup=reply_markup)
    return

# --- SSH Remote Directory Explorer Handler ---
def ssh_credentials_handler(update: Update, context: CallbackContext) -> None:
    """
    Handler para procesar las credenciales SSH y mostrar la raíz remota.
    """
    if not context.user_data.get('awaiting_ssh_credentials'):
        return  # No estamos esperando credenciales

    chat_id = str(update.message.chat_id)
    text = update.message.text.strip()
    try:
        # Parsear credenciales: usuario@host password
        user_host, password = text.split(' ', 1)
        if '@' not in user_host:
            update.message.reply_text("Formato inválido. Usa: `usuario@host password`", parse_mode='Markdown')
            return
        username, host = user_host.split('@', 1)
        import paramiko
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=username, password=password, timeout=10)
        sftp = ssh.open_sftp()
        # Listar la raíz
        root = '/'
        dirs = []
        for entry in sftp.listdir_attr(root):
            if paramiko.SFTPAttributes.S_ISDIR(entry.st_mode):
                dirs.append(entry.filename)
        # Mostrar botones para navegar
        keyboard = [[InlineKeyboardButton(d, callback_data=f'remote_nav:{root}{d}/')] for d in dirs]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(f"Directorio remoto: `{root}`\nSelecciona una carpeta:", reply_markup=reply_markup, parse_mode='Markdown')
        # Guardar sesión y credenciales en user_data para navegación posterior
        context.user_data['ssh_session'] = ssh
        context.user_data['sftp_session'] = sftp
        context.user_data['ssh_root'] = root
        context.user_data['ssh_username'] = username
        context.user_data['ssh_host'] = host
        context.user_data['ssh_password'] = password
        context.user_data['awaiting_ssh_credentials'] = False
    except Exception as e:
        update.message.reply_text(f"❌ Error de conexión SSH: {e}")
        context.user_data['awaiting_ssh_credentials'] = False

# --- Listener Startup ---
def start_telegram_bot_listener(sync_func, cron_change_func, disable_sync_func, enable_sync_func,
                                disk_func=None, status_func=None, change_sync_dir_func=None): # <--- MODIFICADO: Añadido change_sync_dir_func
    """
    Initializes and starts the Telegram bot listener.
    This function sets up the command handlers and callback query handlers,
    then begins polling for updates from Telegram.

    Args:
        sync_func (callable): Function to call for manual synchronization (from main.py).
        cron_change_func (callable): Function to call for changing cron interval (from main.py).
        disable_sync_func (callable): Function to call for disabling auto sync (from main.py).
        enable_sync_func (callable): Function to call for enabling auto sync (from main.py).
        disk_func (callable, optional): Function to call for disk status report (from main.py). Defaults to None.
        status_func (callable, optional): Function to call for general system status report (from main.py). Defaults to None.
        change_sync_dir_func (callable, optional): Function to call for changing the remote sync source path (from main.py). Defaults to None. # <--- AÑADIDO: Descripción del nuevo arg
    """
    global sync_function_callback
    global change_cron_interval_callback
    global disable_auto_sync_callback
    global enable_auto_sync_callback
    global disk_status_callback
    global status_callback
    global change_sync_directory_callback # <--- AÑADIDO: Declarar global

    # Assign the passed functions from main.py to global callback variables
    sync_function_callback = sync_func
    change_cron_interval_callback = cron_change_func
    disable_auto_sync_callback = disable_sync_func
    enable_auto_sync_callback = enable_sync_func
    disk_status_callback = disk_func
    status_callback = status_func
    change_sync_directory_callback = change_sync_dir_func # <--- AÑADIDO: Asignar el nuevo callback

    # Check if bot token is available before attempting to start
    if not TELEGRAM_BOT_TOKEN or not bot:
        logger.error("No TELEGRAM_BOT_TOKEN. Bot will not start.")
        return

    try:
        updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
        dispatcher = updater.dispatcher

        # Register command handlers
        dispatcher.add_handler(CommandHandler("start", start_command))
        dispatcher.add_handler(CommandHandler("close", close_command))
        dispatcher.add_handler(CommandHandler("help", help_command))
        dispatcher.add_handler(CommandHandler("sync", start_sync_command))
        dispatcher.add_handler(CommandHandler("set_interval", set_interval_command))
        dispatcher.add_handler(CommandHandler("disable_sync", disable_sync_command))
        dispatcher.add_handler(CommandHandler("enable_sync", enable_sync_command))
        dispatcher.add_handler(CommandHandler("disk_status", disk_status_command))
        dispatcher.add_handler(CommandHandler("status", status_command))
        dispatcher.add_handler(CommandHandler("change_source", change_sync_directory_command)) # <--- AÑADIDO: Registrar el nuevo comando
        dispatcher.add_handler(CommandHandler("tree", show_tree_command)) # <--- Nuevo comando

        # Register message handler for remote IP input
        from telegram.ext import MessageHandler, Filters
        dispatcher.add_handler(MessageHandler(Filters.text & (~Filters.command), remote_ip_handler))
        
        # Register callback query handler for inline buttons
        dispatcher.add_handler(CallbackQueryHandler(button_callback))
        
        # Register error handler to log exceptions
        dispatcher.add_error_handler(error_handler)
        # Start the bot's polling mechanism
        updater.start_polling()
        logger.info("Telegram Bot: Listener started.")
    except Exception as e:
        logger.error(f"Failed to start the bot: {e}")