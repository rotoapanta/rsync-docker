"""
This script serves as the main entry point for the Raspberry Pi synchronization service
within a Docker container. It orchestrates file synchronization using rsync,
manages automated synchronization intervals via cron, and provides system
status monitoring with Telegram notifications.

Key functionalities include:
- **Synchronization Management**: Initiates and manages rsync operations to
  transfer data from a specified Raspberry Pi source to a local data directory.
  It leverages `SyncManager` for retry mechanisms, logging, and disk space checks.
- **Telegram Bot Integration**: Starts a Telegram bot listener to receive commands
  from authorized users. This allows for manual synchronization triggers,
  dynamic adjustment of cron synchronization intervals, and requests for
  system/disk status reports.
- **Cron Job Automation**: Interacts with the cron system to enable, disable,
  or modify the scheduled synchronization interval, ensuring automated data backups.
- **System Monitoring**: Gathers and reports detailed information about the
  Docker container's disk space and the Raspberry Pi's system metrics (CPU, RAM,
  temperature, battery) and connected USB disk status by querying a separate
  Raspberry Pi endpoint.
- **Logging**: Provides comprehensive logging for synchronization activities,
  errors, and system events to facilitate troubleshooting and monitoring.

Environment Variables:
- `RSYNC_FROM`: (Required by SyncManager) Specifies the rsync source path
  (e.g., "user@192.168.1.100:/path/to/source/").
- `TELEGRAM_BOT_TOKEN`: (Required for Telegram bot) The API token for your
  Telegram bot.
- `TELEGRAM_CHAT_ID`: (Required for Telegram bot) The chat ID where the bot
  will send messages and listen for commands.

Usage:
- When run directly (e.g., `python main.py`), it initializes the Telegram bot
  listener and keeps the service running to handle bot commands and implicit cron jobs.
- When run with a command-line argument (e.g., `python main.py from`), it
  performs a one-time synchronization in the specified direction. This is
  typically used by the cron job itself.
"""
import os
import sys
import time
import logging
import subprocess
import socket
import datetime
import requests
from shutil import disk_usage
from typing import Callable, Tuple, List # Explicitly import for type hinting

# Adjust sys.path to find utils and managers modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'managers'))
sys.path.append(os.path.join(current_dir, 'utils'))

from utils.telegram_utils import start_telegram_bot_listener, send_telegram
from managers.sync_manager import SyncManager

# --- Logging Configuration ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Raspberry Pi Endpoint URL ---
RASPBERRY_URL = "http://192.168.190.29:8000/status"

# --- Data Directory Constant ---
DATA_DIR = "/data" # Local destination directory in the container

# --- Manual Synchronization Function ---
def perform_sync(direction: str):
    """
    Performs a manual synchronization operation in the specified direction.

    Args:
        direction (str): The direction of synchronization (e.g., "from").
    """
    logger.info(f"Initiating synchronization for direction: {direction}")
    try:
        sync_manager = SyncManager()
        sync_manager.run_rsync(direction)
        logger.info(f"Synchronization {direction} completed.")
    except Exception as e:
        logger.error(f"Unexpected error during synchronization: {e}")
        send_telegram(f"❌ Unexpected error during synchronization: `{e}`")

# --- Cron: Interval Update ---
def _update_crontab_entry(action: str, current_interval: int = None) -> Tuple[bool, str]:
    """
    Updates the crontab entry for the rsync synchronization script.

    Args:
        action (str): The action to perform ('disable', 'enable', 'set_interval').
        current_interval (int, optional): The interval in minutes if 'set_interval' is used.

    Returns:
        Tuple[bool, str]: A tuple indicating success (True/False) and a message.
    """
    crontab_path = "/app/crontab.txt"
    sync_script_path = "/app/run_sync.sh"
    log_path = "/app/logs/cron.log"
    sync_line_marker = f"{sync_script_path} from"

    try:
        existing_lines: List[str] = []
        if os.path.exists(crontab_path):
            with open(crontab_path, "r") as f:
                existing_lines = [line.strip() for line in f]

        new_crontab_content: List[str] = []
        found_and_updated = False

        for line in existing_lines:
            if sync_line_marker in line and not found_and_updated:
                if action == 'disable':
                    new_crontab_content.append(f"#{line}" if not line.startswith("#") else line)
                elif action == 'enable':
                    new_crontab_content.append(line[1:] if line.startswith("#") else line)
                elif action == 'set_interval':
                    new_crontab_content.append(f"*/{current_interval} * * * * {sync_script_path} from >> {log_path} 2>&1")
                found_and_updated = True
            elif sync_line_marker in line and found_and_updated:
                pass # Remove duplicate lines
            else:
                new_crontab_content.append(line)

        if not found_and_updated and (action in ['enable', 'set_interval']):
            default_interval = 30
            interval_to_use = current_interval if action == 'set_interval' and current_interval is not None else default_interval
            new_crontab_content.append(f"*/{interval_to_use} * * * * {sync_script_path} from >> {log_path} 2>&1")
            send_telegram(f"⚠️ No auto sync line found. Defaulting to every {interval_to_use} minutes.")

        with open(crontab_path, "w") as f:
            for line in new_crontab_content:
                f.write(line + "\n")

        subprocess.run(["crontab", crontab_path], check=True, capture_output=True)
        return True, ""

    except subprocess.CalledProcessError as e:
        return False, f"Error modifying cron (code: {e.returncode}): {e.stderr.decode('utf-8')}"
    except Exception as e:
        return False, f"Unexpected error modifying cron: `{e}`"

def change_cron_interval(minutes: int):
    """
    Changes the automatic synchronization interval in crontab.

    Args:
        minutes (int): The new interval in minutes.
    """
    success, msg = _update_crontab_entry('set_interval', minutes)
    send_telegram("✅ Interval updated." if success else f"❌ {msg}")

def disable_auto_sync():
    """Disables the automatic synchronization in crontab."""
    success, msg = _update_crontab_entry('disable')
    send_telegram("🚫 Auto sync disabled." if success else f"❌ {msg}")

def enable_auto_sync():
    """Enables the automatic synchronization in crontab."""
    success, msg = _update_crontab_entry('enable')
    send_telegram("✅ Auto sync enabled." if success else f"❌ {msg}")

# --- Functions to Get Disk and System Information ---

def _get_local_disk_info(path: str) -> Tuple[float, float, float]:
    """
    Gets total, used, and free space in GB for a local path.

    Args:
        path (str): The path to check disk usage for.

    Returns:
        Tuple[float, float, float]: A tuple containing (total_gb, used_gb, free_gb).
    """
    total, used, free = disk_usage(path)
    total_gb = total / (1024**3)
    used_gb = used / (1024**3)
    free_gb = free / (1024**3)
    return total_gb, used_gb, free_gb

def get_icon(value: float, thresholds: Tuple[int, int] = (50, 80)) -> str:
    """
    Helper function to get status icons based on percentage thresholds.

    Args:
        value (float): The percentage value.
        thresholds (Tuple[int, int]): A tuple of (warning_threshold, critical_threshold).

    Returns:
        str: An emoji icon representing the status (🔴, 🟠, 🟢).
    """
    if value >= thresholds[1]:
        return "🔴" # Critical
    elif value >= thresholds[0]:
        return "🟠" # Warning
    else:
        return "🟢" # Normal

def _get_current_sync_interval() -> str:
    """
    Retrieves the current synchronization interval from crontab.

    Returns:
        str: The interval in minutes (e.g., "Every 30 minutes"), "Disabled",
             "Not configured", or "Error reading cron".
    """
    try:
        # Execute crontab -l to list tasks
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=True)
        crontab_output = result.stdout

        sync_script_path = "/app/run_sync.sh from"
        
        for line in crontab_output.splitlines():
            # Look for the line containing the synchronization script
            if sync_script_path in line:
                # If the line is commented out, it's disabled
                if line.strip().startswith('#'):
                    return "Disabled"
                
                # Extract the minutes part (the first section of the cron)
                parts = line.strip().split()
                if len(parts) > 0:
                    minutes_part = parts[0]
                    # If it's */N, extract N
                    if minutes_part.startswith('*/'):
                        try:
                            interval = int(minutes_part[2:])
                            return f"Every {interval} minutes"
                        except ValueError:
                            return "Irregular interval" # If not a number
                    elif minutes_part == '*':
                        return "Every minute"
                    elif minutes_part.isdigit():
                        return f"At minute {minutes_part} of each hour"
                    else:
                        return "Custom interval" # For more complex cases (e.g., "0,30")
        
        return "Not configured" # If the sync line is not found
    except subprocess.CalledProcessError:
        logger.error("Error executing crontab -l. Cron not installed or permission denied.")
        return "Error reading cron"
    except Exception as e:
        logger.error(f"Unexpected error getting cron interval: {e}")
        return "Error reading cron"


def disk_status_report():
    """
    Reports the disk status of the Docker container (where /data is mounted)
    and the status of disks connected to the Raspberry Pi (root partition and USBs)
    via Telegram.
    """
    message = "💾 *Storage Status*\n\n"

    # 1. Docker Container Disk Information (/data path)
    try:
        total_docker_gb, used_docker_gb, free_docker_gb = _get_local_disk_info(DATA_DIR)
        message += (
            f"📦 *Docker Container* (`{DATA_DIR}`):\n"
            f"├ 🧱 Total: `{total_docker_gb:.2f} GB`\n"
            f"├ 📂 Used: `{used_docker_gb:.2f} GB`\n"
            f"└ 📦 Free: `{free_docker_gb:.2f} GB`\n\n"
        )
        if free_docker_gb < 10: # Adjust this threshold as needed
            message += "⚠️ *Alert: Low disk space on Docker container!*\n\n"
    except Exception as e:
        message += f"❌ Error getting container disk space: `{e}`\n\n"
        logger.error(f"Error getting container disk space: {e}")

    # 2. Raspberry Pi Disk Information (root partition and USBs)
    try:
        response = requests.get(RASPBERRY_URL, timeout=5)
        response.raise_for_status()
        raspberry_data = response.json()

        r_disk_info = raspberry_data.get("disk_info", {})
        r_total = r_disk_info.get("total", "?")
        r_used = r_disk_info.get("used", "?")
        r_free = r_disk_info.get("free", "?")
        r_disk_percent = raspberry_data.get("disk", 0) # Main Pi disk usage percentage

        disk_icon = get_icon(r_disk_percent)

        message += (
            f"🍓 *Raspberry Pi* (Root Partition `/`):\n"
            f"┌─── {disk_icon} *Usage:* `{r_disk_percent:.1f}%` ───┐\n"
            f"├ 🧱 Total: `{r_total} GB`\n"
            f"├ 📂 Used: `{r_used} GB`\n"
            f"└ 📦 Free: `{r_free} GB`\n"
        )
        if r_free < 10: # Adjust this threshold as needed
            message += "⚠️ *Alert: Low disk space on Raspberry Pi!*"

        # Add information about USBs connected to Raspberry Pi
        usb_disks = raspberry_data.get("usb", [])
        if usb_disks:
            message += f"\n\n🧷 *USBs connected to Raspberry Pi:*\n"
            for usb in usb_disks:
                mount = usb.get("mount", "?")
                device = usb.get("device", "?")
                total = usb.get("total", 0)
                used = usb.get("used", 0)
                free = usb.get("free", 0)
                percent = (used / total * 100) if total else 0

                icon = get_icon(percent, thresholds=(80, 90)) # Stricter thresholds for USBs

                alert = ""
                if percent >= 90:
                    alert = "⚠️ *CRITICAL* - Low free space"
                elif percent >= 80:
                    alert = "⚠️ *ALERT* - Low free space"

                message += (
                    f"{icon} `{mount}` ({device})\n"
                    f"├ 💽 Total: `{total:.2f} GB`\n"
                    f"├ 📂 Used: `{used:.2f} GB`\n"
                    f"└ 📦 Free: `{free:.2f} GB`\n"
                )
                if alert:
                    message += f"    {alert}\n"

    except Exception as e:
        message += f"❌ Error getting Raspberry Pi disk status: `{e}`"
        logger.error(f"Error getting Raspberry Pi disk status: {e}")

    send_telegram(message)

def status_report():
    """
    Reports the general system status of the Raspberry Pi (CPU, RAM, Temp, Battery, etc.)
    via Telegram.
    """
    try:
        response = requests.get(RASPBERRY_URL, timeout=5)
        response.raise_for_status()
        raspberry_data = response.json()

        r_hostname = raspberry_data.get("hostname", "?")
        r_ip = raspberry_data.get("ip", "?")
        r_cpu = raspberry_data.get("cpu", 0)
        r_ram = raspberry_data.get("ram", 0)
        r_temp = raspberry_data.get("temp", 0)
        r_batt = raspberry_data.get("battery", {})
        r_volt = r_batt.get("voltage", "?")
        r_status = r_batt.get("status", "?")

        cpu_icon = get_icon(r_cpu)
        ram_icon = get_icon(r_ram)
        temp_icon = get_icon(r_temp, thresholds=(50, 70))

        # Get current synchronization interval
        sync_interval_info = _get_current_sync_interval()

        message = (
            f"🍓 *Raspberry Pi System Status*\n\n"
            f"🖥️ *Hostname:* `{r_hostname}`\n"
            f"🌐 *IP:* `{r_ip}`\n"
            f"{cpu_icon} *CPU:* `{r_cpu:.1f}%`\n"
            f"{ram_icon} *RAM:* `{r_ram:.1f}%`\n"
            f"{temp_icon} *Temp:* `{r_temp} °C`\n"
            f"🔋 *Battery:* `{r_volt} V` | `{r_status}`\n"
            f"🔄 *Auto Sync:* `{sync_interval_info}`"
        )
        send_telegram(message)

    except Exception as e:
        send_telegram(f"❌ Error getting general Raspberry Pi status: `{e}`")


# --- Main Entry Point ---
if __name__ == "__main__":
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if telegram_bot_token and telegram_chat_id:
        logger.info("Starting Telegram bot listener...")
        try:
            start_telegram_bot_listener(
                perform_sync,
                change_cron_interval,
                disable_auto_sync,
                enable_auto_sync,
                disk_func=disk_status_report, # Pass the disk status report function
                status_func=status_report     # Pass the general status report function
            )
            send_telegram("✅ Synchronization service started. Use /sync to initiate manually.")
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
    else:
        logger.warning("Telegram Bot Token or Chat ID not configured. Bot will not start.")

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "from":
            perform_sync("from")
        else:
            logger.warning(f"Unrecognized command: {command}")
    else:
        logger.info("Main execution mode: Keeping bot and cron services running...")
        while True:
            time.sleep(3600)