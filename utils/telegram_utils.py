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

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Global Variables for the Bot ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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
def start_command(update: Update, context: CallbackContext) -> None:
    """
    Handles the /start command. Sends a welcome message and a menu with inline buttons.
    Only authorized chat IDs can use this command.
    """
    chat_id = str(update.message.chat_id)
    user = update.message.from_user

    if chat_id != TELEGRAM_CHAT_ID:
        update.message.reply_text("Sorry, you are not authorized to use this bot.")
        logger.warning(f"Unauthorized /start command from {user.username} ({chat_id})")
        return

    welcome_message = (
        "Hello! 👋 I'm your Raspberry Pi Data Sync Bot. 🤖\n"
        "Choose an option or use /help for all commands:"
    )

    # Define inline keyboard buttons for the main menu
    keyboard = [
        [InlineKeyboardButton("🚀 Sync Now", callback_data='sync_now')],
        [InlineKeyboardButton("⏱️ Set Interval", callback_data='set_interval_menu')],
        [InlineKeyboardButton("✅ Enable Auto Sync", callback_data='enable_sync'),
         InlineKeyboardButton("🚫 Disable Auto Sync", callback_data='disable_sync')],
        [InlineKeyboardButton("💾 Disk Status", callback_data='disk_status'),
         InlineKeyboardButton("📊 System Status", callback_data='status')],
        [InlineKeyboardButton("🔄 Change Sync Source", callback_data='change_source_prompt')] # <--- AÑADIDO: Botón para cambiar la fuente
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(welcome_message, reply_markup=reply_markup)
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
        query.edit_message_text("💾 Checking disk status...")
        if disk_status_callback:
            threading.Thread(target=disk_status_callback).start()

    elif query.data == 'set_interval_menu':
        # Display the interval selection menu
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
        query.edit_message_text("📊 Getting system status...")
        if status_callback:
            threading.Thread(target=status_callback).start()
    
    elif query.data == 'change_source_prompt': # <--- AÑADIDO: Nuevo botón para pedir el cambio de fuente
        context.bot.send_message(chat_id=chat_id, 
                                 text="Please enter the new remote sync source using the command:\n`/change_source user@host:/path/to/source`\n\nExample: `/change_source pi@192.168.1.100:/home/pi/my_data`", 
                                 parse_mode='Markdown')
        query.edit_message_reply_markup(reply_markup=None) # Remove buttons after prompt

def error_handler(update: Update, context: CallbackContext) -> None:
    """
    Log errors caused by updates.
    """
    logger.warning(f'Update "{update}" caused error "{context.error}"')

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
        dispatcher.add_handler(CommandHandler("help", help_command))
        dispatcher.add_handler(CommandHandler("sync", start_sync_command))
        dispatcher.add_handler(CommandHandler("set_interval", set_interval_command))
        dispatcher.add_handler(CommandHandler("disable_sync", disable_sync_command))
        dispatcher.add_handler(CommandHandler("enable_sync", enable_sync_command))
        dispatcher.add_handler(CommandHandler("disk_status", disk_status_command))
        dispatcher.add_handler(CommandHandler("status", status_command))
        dispatcher.add_handler(CommandHandler("change_source", change_sync_directory_command)) # <--- AÑADIDO: Registrar el nuevo comando
        
        # Register callback query handler for inline buttons
        dispatcher.add_handler(CallbackQueryHandler(button_callback))
        
        # Register error handler to log exceptions
        dispatcher.add_error_handler(error_handler)

        # Start the bot's polling mechanism
        updater.start_polling()
        logger.info("Telegram Bot: Listener started.")
    except Exception as e:
        logger.error(f"Failed to start the bot: {e}")