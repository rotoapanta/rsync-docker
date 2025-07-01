# main.py

"""
Main entry point for the Raspberry Pi synchronization and monitoring service.
Manages file synchronization via rsync, Telegram bot commands, system monitoring,
and scheduled jobs via cron inside a Docker container.
"""

import os
import sys
import time
import logging
import subprocess
import requests
from shutil import disk_usage
from typing import Tuple, List

# --- Adjust sys.path for local modules ---
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'utils'))
sys.path.append(os.path.join(current_dir, 'managers'))

from utils.env_utils import get_env_variable
from utils.constants import DATA_DIR, CRONTAB_PATH, SYNC_SCRIPT_PATH, CRON_LOG_PATH, DEFAULT_RASPBERRY_URL
from utils.telegram_utils import start_telegram_bot_listener, send_telegram
from utils.bot_utils import get_icon
from managers.sync_manager import SyncManager

# --- Logging ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Global SyncManager ---
sync_manager_instance = None

# --- Environment Variables ---
RASPBERRY_URL = get_env_variable("RASPBERRY_URL", default=DEFAULT_RASPBERRY_URL)
TELEGRAM_BOT_TOKEN = get_env_variable("TELEGRAM_BOT_TOKEN", required=True)
TELEGRAM_CHAT_ID = get_env_variable("TELEGRAM_CHAT_ID", required=True)

# === SYNC ===

def perform_sync(direction: str):
    import os
    if os.path.exists("/logs/awaiting_ip.flag"):
        logger.warning("⏸️ El sistema está en pausa por configuración. No se ejecutan tareas programadas ni manuales hasta pulsar 'Start System' en el bot.")
        return
    global sync_manager_instance
    if sync_manager_instance:
        try:
            sync_manager_instance.run_rsync(direction)
            logger.info(f"✅ Sync {direction} completed.")
        except Exception as e:
            logger.error(f"❌ Sync error: {e}")
            send_telegram(f"❌ Sync error: `{e}`")
    else:
        logger.error("❌ SyncManager instance not initialized.")
        send_telegram("❌ SyncManager not initialized.")

# === CRON ===

def _update_crontab_entry(action: str, interval: int = None) -> Tuple[bool, str]:
    try:
        sync_line = f"{SYNC_SCRIPT_PATH} from"
        if os.path.exists(CRONTAB_PATH):
            with open(CRONTAB_PATH, "r") as f:
                lines = [line.strip() for line in f]
        else:
            lines = []

        new_lines = []
        found = False
        for line in lines:
            if sync_line in line and not found:
                if action == 'disable':
                    new_lines.append(f"#{line}" if not line.startswith("#") else line)
                elif action == 'enable':
                    new_lines.append(line[1:] if line.startswith("#") else line)
                elif action == 'set_interval':
                    new_lines.append(f"*/{interval} * * * * {SYNC_SCRIPT_PATH} from >> {CRON_LOG_PATH} 2>&1")
                found = True
            elif sync_line in line:
                continue  # Remove duplicates
            else:
                new_lines.append(line)

        if not found and action in ['enable', 'set_interval']:
            used_interval = interval if interval else 30
            new_lines.append(f"*/{used_interval} * * * * {SYNC_SCRIPT_PATH} from >> {CRON_LOG_PATH} 2>&1")
            send_telegram(f"⚠️ Cron not found. Defaulting to every {used_interval} minutes.")

        with open(CRONTAB_PATH, "w") as f:
            for l in new_lines:
                f.write(l + "\n")

        subprocess.run(["crontab", CRONTAB_PATH], check=True)
        return True, ""
    except subprocess.CalledProcessError as e:
        return False, f"Cron error (code {e.returncode}): {e.stderr.decode('utf-8')}"
    except Exception as e:
        return False, str(e)

def change_cron_interval(minutes: int):
    success, msg = _update_crontab_entry("set_interval", minutes)
    send_telegram("✅ Interval updated." if success else f"❌ {msg}")

def disable_auto_sync():
    success, msg = _update_crontab_entry("disable")
    send_telegram("🚫 Auto sync disabled." if success else f"❌ {msg}")

def enable_auto_sync():
    success, msg = _update_crontab_entry("enable")
    send_telegram("✅ Auto sync enabled." if success else f"❌ {msg}")

def _get_current_sync_interval() -> str:
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if SYNC_SCRIPT_PATH in line:
                if line.startswith("#"):
                    return "Disabled"
                parts = line.split()
                if parts[0].startswith("*/"):
                    return f"Every {parts[0][2:]} minutes"
                return "Custom"
        return "Not configured"
    except Exception:
        return "Error"

# === SYSTEM STATUS ===

# get_icon ahora está en utils/bot_utils.py

def get_raspberry_url_from_env():
    env_path = ".env"
    import os
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("RASPBERRY_URL="):
                    return line.strip().split("=", 1)[1]
    return None

def disk_status_report(update=None, context=None):
    msg = "💾 *Storage Status*\n\n"
    try:
        total, used, free = disk_usage(DATA_DIR)
        msg += (
            f"📦 *Container Storage (`{DATA_DIR}`)*\n"
            f"├ 🧱 Total: `{total / (1024**3):.2f} GB`\n"
            f"├ 📂 Used: `{used / (1024**3):.2f} GB`\n"
            f"└ 📦 Free: `{free / (1024**3):.2f} GB`\n\n"
        )
    except Exception as e:
        logger.error(f"Disk error: {e}")
        msg += f"❌ Error reading disk: `{e}`\n\n"

    try:
        raspberry_url = get_raspberry_url_from_env() or RASPBERRY_URL
        r = requests.get(raspberry_url, timeout=5)
        r.raise_for_status()
        data = r.json()

        disk = data.get("disk", 0)
        info = data.get("disk_info", {})
        icon = get_icon(disk)
        msg += (
            f"🍓 *Raspberry Pi (`/`)*\n"
            f"{icon} Usage: `{disk:.1f}%`\n"
            f"├ 🧱 Total: `{info.get('total', '?')} GB`\n"
            f"├ 📂 Used: `{info.get('used', '?')} GB`\n"
            f"└ 📦 Free: `{info.get('free', '?')} GB`\n"
        )

        usbs = data.get("usb", [])
        if usbs:
            msg += f"\n\n🧷 *USB Devices:*\n"
            for u in usbs:
                pct = (u['used'] / u['total']) * 100 if u['total'] else 0
                u_icon = get_icon(pct, (80, 90))
                msg += (
                    f"{u_icon} `{u['mount']}` ({u['device']})\n"
                    f"├ 💽 Total: `{u['total']:.2f} GB`\n"
                    f"├ 📂 Used: `{u['used']:.2f} GB`\n"
                    f"└ 📦 Free: `{u['free']:.2f} GB`\n"
                )
    except Exception as e:
        logger.error(f"Pi disk error: {e}")
        msg += f"❌ Error fetching Pi status: `{e}`"

    # Enviar mensaje al chat si se llama desde Telegram
    if update and context:
        chat_id = update.effective_chat.id
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [[InlineKeyboardButton("🏠 Volver al menú", callback_data='show_main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        send_telegram(msg)

def status_report(update=None, context=None):
    try:
        raspberry_url = get_raspberry_url_from_env() or RASPBERRY_URL
        r = requests.get(raspberry_url, timeout=5)
        r.raise_for_status()
        data = r.json()

        msg = (
            f"🍓 *Raspberry Pi Status*\n\n"
            f"🖥️ Hostname: `{data.get('hostname', '?')}`\n"
            f"🌐 IP: `{data.get('ip', '?')}`\n"
            f"{get_icon(data.get('cpu', 0))} CPU: `{data.get('cpu', 0):.1f}%`\n"
            f"{get_icon(data.get('ram', 0))} RAM: `{data.get('ram', 0):.1f}%`\n"
            f"{get_icon(data.get('temp', 0), (50, 70))} Temp: `{data.get('temp', 0)} °C`\n"
            f"🔋 Battery: `{data.get('battery', {}).get('voltage', '?')} V` | `{data.get('battery', {}).get('status', '?')}`\n"
            f"🔄 Auto Sync: `{_get_current_sync_interval()}`\n"
            f"📤 Sync From: `{sync_manager_instance.rsync_from if sync_manager_instance else 'N/A'}`"
        )
        # Añadir botón Volver al menú si es desde Telegram
        if update and context:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [[InlineKeyboardButton("🏠 Volver al menú", callback_data='show_main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            chat_id = update.effective_chat.id
            context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            send_telegram(msg)
    except Exception as e:
        logger.error(f"Status error: {e}")
        if update and context:
            chat_id = update.effective_chat.id
            context.bot.send_message(chat_id=chat_id, text=f"❌ Error fetching Pi status: `{e}`")
        else:
            send_telegram(f"❌ Error fetching Pi status: `{e}`")

# === MAIN ===

if __name__ == "__main__":
    sync_manager_instance = SyncManager()

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        logger.info("Starting Telegram bot listener...")
        try:
            start_telegram_bot_listener(
                perform_sync,
                change_cron_interval,
                disable_auto_sync,
                enable_auto_sync,
                disk_func=disk_status_report,
                status_func=status_report,
                change_sync_dir_func=sync_manager_instance.set_rsync_from_path
            )
            import os
            if not os.path.exists("/logs/awaiting_ip.flag"):
                send_telegram("✅ Sync service started. Use /sync to trigger manually.")
            else:
                logger.info("⏸️ El sistema está en pausa por configuración. No se ejecutan tareas programadas ni manuales hasta pulsar 'Start System' en el bot.")
                # send_telegram("⏸️ El sistema está en pausa por configuración. No se ejecutan tareas programadas ni manuales hasta pulsar 'Start System' en el bot.")
        except Exception as e:
            logger.error(f"Bot init error: {e}")

    if len(sys.argv) > 1:
        if sys.argv[1] == "from":
            perform_sync("from")
        else:
            logger.warning(f"Unknown argument: {sys.argv[1]}")
    else:
        logger.info("Main loop active...")
        while True:
            time.sleep(3600)
