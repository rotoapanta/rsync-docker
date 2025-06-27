"""
This module defines the SyncManager class, responsible for handling the rsync
synchronization process. It includes functionalities for logging, retries,
disk space checks, and sending notifications via Telegram.

The SyncManager orchestrates data transfers from a remote Raspberry Pi source
to a local destination directory within the Docker container.
"""
import os
import subprocess
import datetime
import time
import shutil

# Import only the send_telegram function from telegram_utils.
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))
from utils.telegram_utils import send_telegram

# Global constants for the module
LOG_DIR = "/logs"
DATA_DIR = "/data" # Local destination directory

class SyncManager:
    """
    Manages the rsync synchronization process between the Raspberry Pi and the Docker container.
    Handles logging, disk space checks, and Telegram notifications.
    """
    def __init__(self):
        """
        Initializes the SyncManager with rsync source, retry parameters, and disk space threshold.
        """
        self.rsync_from = os.getenv("RSYNC_FROM")
        self.max_retries = 3
        self.retry_delay_seconds = 5

        # Disk space threshold for alerts (e.g., 10 GB)
        self.disk_space_threshold_gb = 10

        if not self.rsync_from:
            error_msg = "CRITICAL ERROR: 'rsync_from' (RSYNC_FROM) variable is not defined."
            self._log_message(error_msg, os.path.join(LOG_DIR, "error.log"))
            send_telegram(f"❌ *Internal Error: Rsync Source (RSYNC_FROM) not defined.*")
            raise ValueError(error_msg)

    def _log_message(self, message: str, logfile: str):
        """
        Logs a message to a specific log file with a timestamp.
        This is a private helper method.

        Args:
            message (str): The message content to log.
            logfile (str): The full path to the log file.
        """
        os.makedirs(os.path.dirname(logfile), exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(logfile, "a") as f:
            f.write(f"[{timestamp}] {message}\n")

    def _get_disk_space_info(self, path: str) -> tuple[float, float, float]:
        """
        Gets total, used, and free space in GB for a given path.

        Args:
            path (str): The path to check disk usage for.

        Returns:
            tuple[float, float, float]: A tuple containing (total_gb, used_gb, free_gb).
        """
        total, used, free = shutil.disk_usage(path)
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        free_gb = free / (1024**3)
        return total_gb, used_gb, free_gb

    def _check_disk_space(self, path: str, log_file: str) -> bool:
        """
        Verifies available disk space and sends an alert if it falls below the configured threshold.

        Args:
            path (str): The path to check disk usage for.
            log_file (str): The log file to record disk space information.

        Returns:
            bool: True if disk space check was successful, False otherwise.
        """
        try:
            total_gb, used_gb, free_gb = self._get_disk_space_info(path)
            self._log_message(f"Disk space available on {path}: {free_gb:.2f} GB (Total: {total_gb:.2f} GB, Used: {used_gb:.2f} GB)", log_file)

            if free_gb < self.disk_space_threshold_gb:
                alert_msg = f"⚠️ *Low Disk Space Alert:*\n" \
                            f"Only {free_gb:.2f} GB free out of {total_gb:.2f} GB on `{path}`.\n" \
                            f"Alert threshold: {self.disk_space_threshold_gb} GB."
                send_telegram(alert_msg)
                self._log_message(alert_msg, log_file)
            return True
        except Exception as e:
            error_msg = f"❌ *Error checking disk space on {path}:* `{e}`"
            self._log_message(error_msg, log_file)
            send_telegram(error_msg)
            return False

    def run_rsync(self, direction: str):
        """
        Executes the rsync command for the specified direction and manages notifications.
        Includes automatic retries for failed synchronization attempts and
        a pre-check for available disk space.

        Args:
            direction (str): The synchronization direction (currently only 'from' is supported).
        """
        if direction == "from":
            src = self.rsync_from
            dest = DATA_DIR
            log_file = os.path.join(LOG_DIR, "from_pi.log")
            desc = "from Raspberry Pi"
        else:
            log_file = os.path.join(LOG_DIR, "error.log")
            self._log_message(f"ERROR: Attempted to run synchronization with invalid direction: '{direction}'. Only 'from' is supported.", log_file)
            send_telegram(f"❌ *Internal Error: Synchronization attempt with unsupported direction: {direction}*")
            return

        if src is None:
            self._log_message(f"CRITICAL ERROR: 'src' variable (RSYNC_FROM) is None for direction '{direction}'", log_file)
            send_telegram(f"❌ *Internal Error: Rsync Source (RSYNC_FROM) not defined for {desc}*")
            return
        if dest is None:
            self._log_message(f"CRITICAL ERROR: 'dest' variable is None for direction '{direction}'", log_file)
            send_telegram(f"❌ *Internal Error: Rsync Destination not defined for {desc}*")
            return

        # Check disk space before synchronization
        if not self._check_disk_space(dest, log_file):
            self._log_message("Synchronization aborted due to a disk space check error.", log_file)
            send_telegram(f"❌ *Synchronization {desc} aborted: Disk space check issue.*")
            return

        self._log_message(f"Initiating synchronization {desc}", log_file)

        cmd = [
            "rsync",
            "-e", "ssh -i /root/.ssh/id_rsa -o StrictHostKeyChecking=no",
            "-avz", # -a for archive mode (preserves permissions, timestamps, etc.), -v for verbose output, -z for compression
            src,
            dest
        ]

        self._log_message(f"Rsync command to execute: {' '.join(cmd)}", log_file)

        for attempt in range(1, self.max_retries + 1):
            try:
                self._log_message(f"Attempt {attempt}/{self.max_retries} to synchronize.", log_file)
                # Run rsync as a subprocess, capture output, set a timeout
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                self._log_message(result.stdout, log_file)

                if result.returncode == 0:
                    # Parse rsync output to determine if bytes were transferred
                    output_lines = result.stdout.strip().split('\n')
                    received_bytes_str = "0"
                    for line in reversed(output_lines): # Search from the end for efficiency
                        if "received" in line and "bytes" in line:
                            parts = line.split("received")
                            if len(parts) > 1:
                                received_bytes_str = parts[1].split("bytes")[0].strip().replace(",", "")
                                break
                            
                    received_bytes = int(received_bytes_str)

                    if received_bytes > 100: # Assuming >100 bytes indicates actual data transfer
                        telegram_message = f"✅📥 *Synchronization successful {desc} - Changes detected and transferred*\n\n"
                        # Include last few lines of rsync output for context
                        telegram_message += "```\n" + "\n".join(output_lines[-5:]) + "\n```"
                        send_telegram(telegram_message)
                    else:
                        telegram_message = f"✅🔄 *Synchronization successful {desc} - No changes to transfer*\n"
                        send_telegram(telegram_message)
                    return # Exit the function upon successful completion
                else:
                    # Log stderr if rsync exits with a non-zero code
                    self._log_message(f"Rsync stderr (Attempt {attempt}): {result.stderr}", log_file)
                    if attempt < self.max_retries:
                        self._log_message(f"Retrying in {self.retry_delay_seconds} seconds...", log_file)
                        time.sleep(self.retry_delay_seconds)
                        self.retry_delay_seconds *= 2 # Exponential backoff
                    else:
                        # Send failure message after all retries are exhausted
                        telegram_message = f"❌🔥 *Failed to synchronize {desc} after {self.max_retries} attempts*\n\n"
                        telegram_message += f"Exit code: {result.returncode}\n"
                        telegram_message += f"```\n{result.stderr.strip()}\n```"
                        send_telegram(telegram_message)
            except subprocess.TimeoutExpired as e:
                # Handle rsync command timeout
                self._log_message(f"Timeout (Attempt {attempt}): {e}", log_file)
                if attempt < self.max_retries:
                    self._log_message(f"Retrying in {self.retry_delay_seconds} seconds...", log_file)
                    time.sleep(self.retry_delay_seconds)
                    self.retry_delay_seconds *= 2
                else:
                    telegram_message = f"❌🚨 *Timeout Exception synchronizing {desc} after {self.max_retries} attempts*\n`{e}`"
                    send_telegram(telegram_message)
            except Exception as e:
                # Handle any other unexpected errors during the process
                self._log_message(f"Unexpected error (Attempt {attempt}): {e}", log_file)
                if attempt < self.max_retries:
                    self._log_message(f"Retrying in {self.retry_delay_seconds} seconds...", log_file)
                    time.sleep(self.retry_delay_seconds)
                    self.retry_delay_seconds *= 2
                else:
                    telegram_message = f"❌🚨 *Exception synchronizing {desc} after {self.max_retries} attempts*\n`{e}`"
                    send_telegram(telegram_message)