"""
File: managers/sync_manager.py
Description: This module defines the SyncManager class, which orchestrates the rsync
             synchronization process. It handles data transfers from a remote
             Raspberry Pi source to a local destination directory within the
             Docker container. Key functionalities include robust logging,
             pre-sync disk space checks, parsing rsync output for detailed
             statistics, and sending comprehensive notifications via Telegram,
             including retry mechanisms for enhanced reliability.
Author: Roberto Toapanta
Date: 2025-06-27
Version: 1.0.0
License: MIT License (or your chosen license)
"""

import os
import subprocess
import datetime
import time
import shutil
import re
import logging

# Configure logging for the module to output to standard streams (Docker logs)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# Import send_telegram function. Ensure 'utils' directory is in sys.path
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))
from utils.telegram_utils import send_telegram

# Global constants for the module
LOG_DIR = "/logs"
DATA_DIR = "/data" # Local destination directory within the container (where the Docker volume is mounted)
# Archivo para persistir la ruta RSYNC_FROM
RSYNC_FROM_CONFIG_FILE = os.path.join(LOG_DIR, "rsync_from.conf")


class SyncManager:
    """
    Manages the rsync synchronization process between a remote source (e.g., Raspberry Pi)
    and the local Docker container's data directory.

    This class provides robust functionalities including:
    - Initialization with rsync source and configurable operational parameters (retries, delays).
    - Ensuring necessary log and data directories are properly set up.
    - Comprehensive logging of synchronization events and detailed output to dedicated log files.
    - Pre-synchronization disk space checks to prevent transfer failures due to insufficient storage.
    - Intelligent parsing of rsync's verbose output (--itemize-changes and --stats) to extract
      granular transfer metrics and identify newly added, modified, or deleted items.
    - Sending formatted and informative Telegram notifications for various events:
      successful synchronizations, detected changes, failures, timeouts, and low disk space alerts.
    - Implementing an exponential backoff retry mechanism to enhance the reliability of rsync operations.
    """
    def __init__(self):
        """
        Initializes the SyncManager by retrieving essential configuration parameters
        from environment variables. Sets up default values for retry attempts,
        delay, and disk space thresholds if environment variables are not explicitly defined.
        A ValueError is raised if the RSYNC_FROM environment variable is missing, as it
        is a critical prerequisite for any synchronization activity.
        """
        self.rsync_dest_host_path = os.getenv("RSYNC_DEST_HOST_PATH", DATA_DIR)

        self.max_retries = int(os.getenv("RSYNC_MAX_RETRIES", 3))
        self.retry_delay_seconds = int(os.getenv("RSYNC_RETRY_DELAY", 5))

        self.disk_space_threshold_gb = int(os.getenv("DISK_SPACE_THRESHOLD_GB", 10))
        self.FOLDER_LIST_THRESHOLD = int(os.getenv("FOLDER_LIST_THRESHOLD", 5))

        self._ensure_dirs()
        self._load_rsync_from_path() # <--- AÑADIDO: Carga la ruta de RSYNC_FROM

        # Si después de cargar, rsync_from sigue sin estar definido, lo tomamos del ENV.
        # Esto permite que el archivo de configuración tenga prioridad si existe.
        if not self.rsync_from:
            self.rsync_from = os.getenv("RSYNC_FROM")
            if not self.rsync_from:
                error_msg = "CRITICAL ERROR: 'RSYNC_FROM' environment variable or config file is not defined. Synchronization cannot proceed."
                self._log_message(error_msg, os.path.join(LOG_DIR, "error.log"))
                send_telegram(f"❌ *Internal Error: Rsync Source (RSYNC_FROM) not defined.*")
                raise ValueError(error_msg)
            else:
                self._save_rsync_from_path(self.rsync_from) # Si lo toma del ENV, lo guarda para futuras ejecuciones.


    def _ensure_dirs(self):
        """
        Ensures that the application's essential directories, `DATA_DIR` (for synced data)
        and `LOG_DIR` (for logs), exist. If either directory does not exist, it is created.
        This prevents potential I/O errors during file operations.
        """
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(LOG_DIR, exist_ok=True)

    # --- AÑADIDO: Métodos para manejar la persistencia de RSYNC_FROM ---
    def _load_rsync_from_path(self):
        """Loads the rsync source path (RSYNC_FROM) from a configuration file."""
        if os.path.exists(RSYNC_FROM_CONFIG_FILE):
            try:
                with open(RSYNC_FROM_CONFIG_FILE, "r") as f:
                    self.rsync_from = f.read().strip()
                logger.info(f"Loaded RSYNC_FROM from config file: {self.rsync_from}")
            except Exception as e:
                logger.error(f"Error loading RSYNC_FROM from {RSYNC_FROM_CONFIG_FILE}: {e}")
                self.rsync_from = None # Fallback if there's an error reading
        else:
            logger.info(f"RSYNC_FROM config file '{RSYNC_FROM_CONFIG_FILE}' not found.")
            self.rsync_from = None # Será tomado del ENV si está definido, o lanzará error

    def _save_rsync_from_path(self, path: str):
        """Saves the current rsync source path (RSYNC_FROM) to a configuration file."""
        try:
            with open(RSYNC_FROM_CONFIG_FILE, "w") as f:
                f.write(path)
            self.rsync_from = path # Actualiza la variable de instancia también
            logger.info(f"Saved RSYNC_FROM to config file: {path}")
        except Exception as e:
            logger.error(f"Error saving RSYNC_FROM to {RSYNC_FROM_CONFIG_FILE}: {e}")
            send_telegram(f"❌ Error saving new RSYNC_FROM path: {e}")

    def set_rsync_from_path(self, new_path: str) -> bool:
        """
        Sets a new rsync source path and persists it.

        Args:
            new_path (str): The new remote source path (e.g., user@host:/path/to/sync).

        Returns:
            bool: True if the path was successfully set, False otherwise.
        """
        # Aquí podrías añadir validaciones básicas para new_path si lo consideras necesario.
        # Por ejemplo, verificar el formato user@host:/path
        if not new_path or "@" not in new_path or ":" not in new_path:
            self.telegram_utils.send_telegram(f"Invalid RSYNC_FROM format. Expected `user@host:/path`. Got: `{new_path}` ❌")
            return False

        self._save_rsync_from_path(new_path)
        logger.info(f"RSYNC_FROM path updated to: {new_path}")
        return True
    # --- FIN AÑADIDO ---


    def _log_message(self, message: str, logfile: str):
        """
        Logs a given message to a specified log file, prepending a timestamp for traceability.
        Additionally, the message is also output to the standard application logger,
        which typically directs to the console or Docker container logs.

        Args:
            message (str): The content of the message to be logged.
            logfile (str): The full path to the log file where the message will be appended.
        """
        os.makedirs(os.path.dirname(logfile), exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(logfile, "a") as f:
                f.write(f"[{timestamp}] {message}\n")
        except IOError as e:
            logger.error(f"Failed to write to log file {logfile}: {e}")
        logger.info(message)

    def _get_disk_space_info(self, path: str) -> tuple[float, float, float]:
        """
        Retrieves the total, used, and free disk space for a given file system path.
        The sizes are calculated and returned in Gigabytes (GB) for readability.

        Args:
            path (str): The file system path for which to retrieve disk usage information.

        Returns:
            tuple[float, float, float]: A tuple containing three float values representing:
                                        (total_space_gb, used_space_gb, free_space_gb).
        """
        total, used, free = shutil.disk_usage(path)
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        free_gb = free / (1024**3)
        return total_gb, used_gb, free_gb

    def _check_disk_space(self, path: str, log_file: str) -> bool:
        """
        Performs a critical disk space availability check on the specified path.
        If the amount of free space falls below the configured `self.disk_space_threshold_gb`,
        a low disk space alert is triggered and sent via Telegram notification.

        Args:
            path (str): The file system path to be checked for disk usage.
            log_file (str): The log file where disk space information will be recorded.

        Returns:
            bool: True if sufficient disk space is available (i.e., free space is above
                  or equal to the threshold), False otherwise (low space or an error occurred).
        """
        try:
            total_gb, used_gb, free_gb = self._get_disk_space_info(path)
            self._log_message(f"Disk space available on {path}: {free_gb:.2f} GB (Total: {total_gb:.2f} GB, Used: {used_gb:.2f} GB)", log_file)

            if free_gb < self.disk_space_threshold_gb:
                alert_msg = (
                    f"⚠️ *Low Disk Space Alert:*\n"
                    f"Only `{free_gb:.2f} GB` free out of `{total_gb:.2f} GB` on `{path}`.\n"
                    f"Alert threshold: `{self.disk_space_threshold_gb} GB`."
                )
                send_telegram(alert_msg)
                self._log_message(alert_msg, log_file)
                return False
            return True
        except Exception as e:
            error_msg = f"❌ *Error checking disk space on {path}:* `{e}`"
            self._log_message(error_msg, log_file)
            send_telegram(error_msg)
            return False

    def _parse_rsync_output(self, rsync_output: str) -> dict:
        """
        Parses the standard output from an rsync command to extract detailed
        transfer statistics and identify all affected (new, modified, or deleted) files and folders.
        This method specifically expects `rsync_output` to be generated using
        the `--itemize-changes` and `--stats` options for comprehensive data.

        Args:
            rsync_output (str): The complete standard output string captured from the rsync command.

        Returns:
            dict: A dictionary containing parsed statistics and lists of affected items.
        """
        stats = {
            "sent_bytes": 0,
            "received_bytes": 0,
            "total_size": 0,
            "speed_bps": 0,
            "new_files": 0,
            "modified_files": 0,
            "deleted_files": 0,
            "new_folders": 0,
            "modified_folders": 0,
            "new_folder_names": [],
            "modified_folder_names": []
        }

        output_lines = rsync_output.strip().split('\n')
        
        item_regex = re.compile(r'^(?P<flags>[.cd+*<>])(?P<perm_flags>[a-zA-Z0-9.\-+\/\\]{8})\s+(?P<path>.+)$')

        unique_new_folders = set()
        unique_modified_folders = set()

        for line in output_lines:
            match = item_regex.match(line)
            if match:
                flags = match.group('flags')
                path = match.group('path').strip()
                
                is_directory_by_flag = 'd' in flags
                # Si es un directorio, el path ya viene con / al final de rsync --itemize-changes
                full_path_in_dest = os.path.join(DATA_DIR, path).rstrip('/')

                if is_directory_by_flag: 
                    if flags.startswith('c'): # created
                        unique_new_folders.add(full_path_in_dest)
                    elif 't' in flags or 's' in flags or ('+' in flags and not flags.startswith('c')): # modified or size changed
                        unique_modified_folders.add(full_path_in_dest)
                else: # Es un archivo
                    if flags.startswith('<') or flags.startswith('c'): # sent or created
                        stats["new_files"] += 1
                    elif 't' in flags or 's' in flags: # modified or size changed
                        stats["modified_files"] += 1
                    elif flags.startswith('*'): # deleted
                        stats["deleted_files"] += 1
            
            # Parse stats summary (fallback for older rsync versions or different output patterns)
            if "Total bytes sent:" in line:
                match = re.search(r'Total bytes sent:\s*([\d\.,]+)', line)
                if match:
                    stats["sent_bytes"] = int(match.group(1).replace('.', '').replace(',', ''))
            elif "Total bytes received:" in line:
                match = re.search(r'Total bytes received:\s*([\d\.,]+)', line)
                if match:
                    stats["received_bytes"] = int(match.group(1).replace('.', '').replace(',', ''))
            elif "total size is" in line and "speedup is" in line:
                match_total_size = re.search(r'total size is\s*([\d\.,]+)', line)
                if match_total_size:
                    stats["total_size"] = int(match_total_size.group(1).replace('.', '').replace(',', ''))
                
                speed_match = re.search(r'([\d\.,]+)\s*bytes/sec', line)
                if speed_match:
                    stats["speed_bps"] = float(speed_match.group(1).replace('.', '').replace(',', ''))
            elif "Number of created files:" in line:
                match = re.search(r'Number of created files:\s*(\d+)', line)
                if match:
                    stats["new_files"] = int(match.group(1))
            elif "Number of deleted files:" in line:
                match = re.search(r'Number of deleted files:\s*(\d+)', line)
                if match:
                    stats["deleted_files"] = int(match.group(1))

        stats["new_folder_names"] = sorted(list(unique_new_folders))
        stats["modified_folder_names"] = sorted(list(unique_modified_folders))
        
        stats["new_folders"] = len(stats["new_folder_names"])
        stats["modified_folders"] = len(stats["modified_folder_names"])

        return stats

    def _get_dta_folder_info(self) -> str:
        """
        Gathers information about the /data/DTA folder, including file count and total size,
        formatted for a Telegram message.

        Returns:
            str: A formatted string with DTA folder info, or an error message if not found.
        """
        dta_info_message = ""
        dta_path = os.path.join(DATA_DIR, "DTA")

        if os.path.exists(dta_path) and os.path.isdir(dta_path):
            file_count = 0
            total_size_bytes = 0
            try:
                for root, _, files in os.walk(dta_path):
                    file_count += len(files)
                    for f in files:
                        file_path = os.path.join(root, f)
                        if os.path.isfile(file_path):
                            total_size_bytes += os.path.getsize(file_path)
            except Exception as e:
                logger.error(f"Error accessing files in {dta_path}: {e}")
                dta_info_message += f"❌ Error reading `{os.path.basename(dta_path)}` contents: `{e}`\n"
                return dta_info_message

            total_size_mb = total_size_bytes / (1024 * 1024)

            # Usar rsync_dest_host_path para mostrar la ruta en el host si es diferente a DATA_DIR
            display_dta_path = os.path.join(self.rsync_dest_host_path, "DTA") if self.rsync_dest_host_path != DATA_DIR else dta_path

            dta_info_message += (
                f"\n📁 `{display_dta_path}` contains {file_count} files\n"
                f"📦 Total size: {total_size_mb:.1f} MB\n"
            )
        else:
            dta_info_message += f"\n📁 Directory `{os.path.basename(dta_path)}` not found or is not a directory.\n"
        
        return dta_info_message

    def _get_dta_file_tree_string(self) -> str:
        """
        Generates a string representation of the file tree for the /data/DTA directory.
        It attempts to use the 'tree' command first, falling back to 'ls -R' if 'tree' is not available.
        The output is truncated if it exceeds a certain length to fit within Telegram message limits.

        Returns:
            str: A formatted string containing the DTA file tree, or an error message.
        """
        dta_path = os.path.join(DATA_DIR, "DTA")
        log_file = os.path.join(LOG_DIR, "file_tree.log") # Specific log for tree command

        if not os.path.exists(dta_path) or not os.path.isdir(dta_path):
            return f"\n⚠️ File tree for `{os.path.basename(dta_path)}` not available: directory not found or not accessible."

        file_tree_output = ""
        command_used = ""
        try:
            # Attempt to use 'tree' command with depth limit and no report footer
            # -F: appends / for directories, * for executables, etc.
            # -L 3: limits depth to 3 levels (adjust as needed for typical file structure)
            # --noreport: prevents showing the file/directory count footer
            command_used = "tree"
            file_tree_output = subprocess.check_output(
                ["tree", "-F", "-L", "3", "--noreport", dta_path],
                text=True,
                stderr=subprocess.PIPE, # Capture stderr to distinguish command not found from other errors
                timeout=30 # Short timeout for tree generation
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            # Fallback to 'ls -R' if 'tree' is not found or fails for some reason
            logger.warning(f"'{command_used}' command failed or not found ({e}). Falling back to 'ls -R'.")
            self._log_message(f"'{command_used}' command failed or not found ({e}). Falling back to 'ls -R'.", log_file)
            command_used = "ls -R"
            try:
                file_tree_output = subprocess.check_output(
                    ["ls", "-R", dta_path],
                    text=True,
                    stderr=subprocess.PIPE,
                    timeout=30
                ).strip()
            except subprocess.TimeoutExpired as e_ls:
                logger.error(f"ls -R command timed out for {dta_path}: {e_ls}")
                self._log_message(f"ls -R command timed out for {dta_path}: {e_ls}", log_file)
                return f"\n❌ Failed to generate file tree: `ls -R` timed out."
            except subprocess.CalledProcessError as e_ls:
                logger.error(f"ls -R command failed for {dta_path}: {e_ls.stderr}")
                self._log_message(f"ls -R command failed for {dta_path}: {e_ls.stderr}", log_file)
                return f"\n❌ Failed to generate file tree: `ls -R` command error."
            except Exception as e_ls:
                logger.error(f"Unexpected error with ls -R for {dta_path}: {e_ls}")
                self._log_message(f"Unexpected error with ls -R for {dta_path}: {e_ls}", log_file)
                return f"\n❌ Failed to generate file tree: unexpected error with `ls -R`."
        except subprocess.TimeoutExpired as e:
            logger.error(f"Tree command timed out for {dta_path}: {e}")
            self._log_message(f"Tree command timed out for {dta_path}: {e}", log_file)
            return f"\n❌ Failed to generate file tree: `{command_used}` timed out."
        except Exception as e:
            logger.error(f"Unexpected error with tree command for {dta_path}: {e}")
            self._log_message(f"Unexpected error with tree command for {dta_path}: {e}", log_file)
            return f"\n❌ Failed to generate file tree: unexpected error with `{command_used}`."


        # Truncate output if it's too long for Telegram
        MAX_TREE_OUTPUT_LENGTH = 1500 # Adjust this based on how much detail you want in the tree
        if len(file_tree_output) > MAX_TREE_OUTPUT_LENGTH:
            file_tree_output = file_tree_output[:MAX_TREE_OUTPUT_LENGTH] + "\n... (output truncated due to length) ..."
            self._log_message(f"File tree output truncated for Telegram message. Command used: {command_used}", log_file)

        return f"\n🌳 *File Tree* (`{os.path.basename(dta_path)}`):\n```\n{file_tree_output}\n```"


    def run_rsync(self, direction: str):
        """
        Executes the rsync command for the specified synchronization direction.
        This comprehensive method orchestrates the entire synchronization workflow:
        it performs pre-transfer checks (like disk space), manages the rsync command
        execution, parses the command's output for detailed synchronization statistics,
        and dispatches comprehensive Telegram notifications. It also implements an
        exponential backoff retry mechanism to enhance the robustness of transfers
        against transient network or remote host issues.

        Args:
            direction (str): The synchronization direction. Currently, only 'from'
                             is supported, which indicates a data pull operation
                             from the remote source to the local `DATA_DIR`.
        """
        if direction == "from":
            src = self.rsync_from
            dest = DATA_DIR
            log_file = os.path.join(LOG_DIR, "from_pi.log")
            desc = "from Raspberry Pi"
            
            display_dest = self.rsync_dest_host_path if self.rsync_dest_host_path else dest
        else:
            log_file = os.path.join(LOG_DIR, "error.log")
            self._log_message(f"ERROR: Attempted to run synchronization with invalid direction: '{direction}'. Only 'from' is supported.", log_file)
            send_telegram(f"❌ *Internal Error: Synchronization attempt with unsupported direction: {direction}*")
            return

        if src is None:
            self._log_message(f"CRITICAL ERROR: 'src' (RSYNC_FROM) variable is None for direction '{direction}'", log_file)
            send_telegram(f"❌ *Internal Error: Rsync Source (RSYNC_FROM) not defined for {desc}*.\nPlease set it using `/change_directory user@host:/path`") # <--- AÑADIDO: Sugerencia
            return
        if dest is None:
            self._log_message(f"CRITICAL ERROR: 'dest' variable is None for direction '{direction}'", log_file)
            send_telegram(f"❌ *Internal Error: Rsync Destination not defined for {desc}*")
            return

        if not self._check_disk_space(dest, log_file):
            self._log_message("Synchronization aborted due to a disk space check error.", log_file)
            send_telegram(f"❌ *Synchronization {desc} aborted: Disk space check issue.*")
            return

        self._log_message(f"Initiating synchronization {desc}", log_file)

        cmd = [
            "rsync",
            "-e", "ssh -i /root/.ssh/id_rsa -o StrictHostKeyChecking=no",
            "-avz",
            "--stats",
            "--itemize-changes",
            src,
            dest
        ]

        self._log_message(f"Rsync command to execute: {' '.join(cmd)}", log_file)

        for attempt in range(1, self.max_retries + 1):
            current_retry_delay = self.retry_delay_seconds * (2 ** (attempt - 1))
            try:
                self._log_message(f"Attempt {attempt}/{self.max_retries} to synchronize.", log_file)
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                self._log_message(f"Rsync STDOUT:\n{result.stdout}", log_file)
                if result.stderr:
                    self._log_message(f"Rsync STDERR:\n{result.stderr}", log_file)

                output_lines = result.stdout.strip().split('\n')

                if result.returncode == 0:
                    parsed_stats = self._parse_rsync_output(result.stdout)
                    
                    any_changes = (
                        parsed_stats.get("received_bytes", 0) > 0 or
                        parsed_stats.get("new_files", 0) > 0 or
                        parsed_stats.get("modified_files", 0) > 0 or
                        parsed_stats.get("deleted_files", 0) > 0 or
                        parsed_stats.get("new_folders", 0) > 0 or
                        parsed_stats.get("modified_folders", 0) > 0
                    )

                    rsync_summary_block_lines = []
                    capture_summary = False
                    for line in output_lines:
                        if "Number of files:" in line or "Number of created files:" in line or "Total transferred file size:" in line:
                            capture_summary = True
                        
                        if capture_summary:
                            rsync_summary_block_lines.append(line)
                            if "total size is" in line and "speedup is" in line:
                                break 

                    summary_code_block = ""
                    if rsync_summary_block_lines:
                        filtered_summary_lines = []
                        start_stats = False
                        for line in rsync_summary_block_lines:
                            if "Number of files:" in line or "Total bytes sent:" in line or "total size is" in line:
                                start_stats = True
                            if start_stats:
                                filtered_summary_lines.append(line)
                        
                        summary_code_block = "\n".join(filtered_summary_lines).strip()
                    
                    telegram_message_title = f"✅📥 *Synchronization successful {desc}"
                    if any_changes:
                        telegram_message_title += " - Changes detected and transferred*"
                    else:
                        telegram_message_title += " - No changes detected*"
                    
                    telegram_message_title += (
                        f"\n\n*Source:* `{src}`\n"
                        f"*Destination:* `{display_dest}`\n\n"
                    )
                    
                    folder_summary_text = ""
                    total_affected_folders = parsed_stats['new_folders'] + parsed_stats['modified_folders']

                    if total_affected_folders > 0:
                        folder_summary_text += "\n📂 *Affected Folders:*\n"
                        if total_affected_folders <= self.FOLDER_LIST_THRESHOLD:
                            for folder_name in parsed_stats['new_folder_names']:
                                display_name = folder_name.replace(DATA_DIR, '')
                                if display_name.startswith('/'): 
                                    display_name = display_name[1:]
                                if not display_name: display_name = "root of destination"
                                folder_summary_text += f"├ New: `{display_name}`\n"
                            for folder_name in parsed_stats['modified_folder_names']:
                                display_name = folder_name.replace(DATA_DIR, '')
                                if display_name.startswith('/'):
                                    display_name = display_name[1:]
                                if not display_name: display_name = "root of destination"
                                folder_summary_text += f"├ Updated: `{display_name}`\n"
                        else:
                            folder_summary_text += (
                                f"├ Total new: {parsed_stats['new_folders']}\n"
                                f"└ Total updated: {parsed_stats['modified_folders']}\n"
                                f"(Details in logs: `{log_file}`)\n"
                            )
                    
                    dta_info = self._get_dta_folder_info()
                    dta_file_tree = self._get_dta_file_tree_string()

                    # Concatenar todos los mensajes
                    telegram_message = telegram_message_title + folder_summary_text + dta_info
                    
                    # Añadir el bloque de resumen de rsync si está disponible
                    if summary_code_block:
                        telegram_message += f"\n```\n{summary_code_block}\n```"

                    # Añadir el árbol de archivos DTA al final
                    if dta_file_tree:
                        telegram_message += dta_file_tree
                    
                    send_telegram(telegram_message)
                    return

                else:
                    self._log_message(f"Rsync command failed (Attempt {attempt}, Exit Code: {result.returncode}).", log_file)
                    self._log_message(f"Rsync STDOUT:\n{result.stdout}", log_file)
                    self._log_message(f"Rsync STDERR:\n{result.stderr}", log_file)
                    
                    if attempt < self.max_retries:
                        current_retry_delay = self.retry_delay_seconds * (2 ** (attempt - 1))
                        self._log_message(f"Retrying in {current_retry_delay} seconds...", log_file)
                        time.sleep(current_retry_delay)
                    else:
                        telegram_message = (
                            f"❌🔥 *Failed to synchronize {desc} after {self.max_retries} attempts*\n\n"
                            f"*Source:* `{src}`\n"
                            f"*Destination:* `{display_dest}`\n\n"
                            f"Exit code: `{result.returncode}`\n"
                            f"STDOUT (partial): ```{result.stdout[:500] if result.stdout else 'N/A'}...```\n"
                            f"STDERR (partial): ```{result.stderr[:500] if result.stderr else 'N/A'}...```"
                        )
                        send_telegram(telegram_message)
            except subprocess.TimeoutExpired as e:
                self._log_message(f"Rsync command timed out (Attempt {attempt}). Timeout: {e.timeout} seconds.", log_file)
                self._log_message(f"Timeout STDOUT:\n{e.stdout}", log_file)
                self._log_message(f"Timeout STDERR:\n{e.stderr}", log_file)
                
                if attempt < self.max_retries:
                    current_retry_delay = self.retry_delay_seconds * (2 ** (attempt - 1))
                    self._log_message(f"Retrying in {current_retry_delay} seconds...", log_file)
                    time.sleep(current_retry_delay)
                else:
                    telegram_message = (
                        f"❌🚨 *Rsync Timeout Exception during sync {desc} after {self.max_retries} attempts*\n"
                        f"*Source:* `{src}`\n"
                        f"*Destination:* `{display_dest}`\n\n"
                        f"Timeout: `{e.timeout} seconds`\n"
                        f"Check logs for details: `{log_file}`"
                    )
                    send_telegram(telegram_message)
            except Exception as e:
                self._log_message(f"Unexpected error during synchronization (Attempt {attempt}): {e}", log_file)
                if attempt < self.max_retries:
                    current_retry_delay = self.retry_delay_seconds * (2 ** (attempt - 1))
                    self._log_message(f"Retrying in {current_retry_delay} seconds...", log_file)
                    time.sleep(current_retry_delay)
                else:
                    telegram_message = (
                        f"❌🚨 *Unexpected Exception during sync {desc} after {self.max_retries} attempts*\n"
                        f"*Source:* `{src}`\n"
                        f"*Destination:* `{display_dest}`\n\n"
                        f"Error: `{e}`\n"
                        f"Check logs for details: `{log_file}`"
                    )
                    send_telegram(telegram_message)

    def get_disk_status(self) -> None:
        """
        Retrieves and sends the disk usage status of the local DATA_DIR.
        """
        logger.info("Checking disk status for DATA_DIR...")
        try:
            total_gb, used_gb, free_gb = self._get_disk_space_info(DATA_DIR)
            
            # Obtener el uso del disco para la partición raíz del contenedor (si es diferente)
            # Aunque en Docker / y /data pueden ser lo mismo si el volumen es la raíz.
            total_root_gb, used_root_gb, free_root_gb = self._get_disk_space_info("/")
            
            disk_status_message = (
                f"💾 *Disk Usage Status (inside container):*\n"
                f"  *Sync Destination (`{DATA_DIR}`)*:\n"
                f"    Total: `{total_gb:.2f} GB`\n"
                f"    Used: `{used_gb:.2f} GB`\n"
                f"    Free: `{free_gb:.2f} GB`\n"
                f"    Usage: `{(used_gb / total_gb * 100):.2f}%`\n"
                f"  *Root Partition (`/`)*:\n"
                f"    Total: `{total_root_gb:.2f} GB`\n"
                f"    Used: `{used_root_gb:.2f} GB`\n"
                f"    Free: `{free_root_gb:.2f} GB`\n"
                f"    Usage: `{(used_root_gb / total_root_gb * 100):.2f}%`"
            )
            self.telegram_utils.send_telegram(disk_status_message)
            logger.info("Disk status sent.")
        except Exception as e:
            error_message = f"Error getting disk status: {e}"
            logger.error(error_message)
            self.telegram_utils.send_telegram(f"Failed to get disk status: {e} ❌")

    def get_system_status(self) -> None:
        """
        Retrieves and sends general system status (CPU, RAM) of the container.
        Note: These metrics reflect the container's view, not necessarily the host's.
        """
        import platform # Para información del sistema operativo
        import psutil   # Para CPU, RAM (requiere pip install psutil)
        
        logger.info("Checking system status (inside container)...")
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1) # Bloquea por 1 segundo para una lectura precisa

            # RAM usage
            virtual_memory = psutil.virtual_memory()
            total_ram_gb = virtual_memory.total / (1024**3)
            used_ram_gb = virtual_memory.used / (1024**3)
            percent_ram_used = virtual_memory.percent

            # Uptime (container's uptime)
            boot_time_timestamp = psutil.boot_time()
            from datetime import datetime, timedelta
            boot_time_datetime = datetime.fromtimestamp(boot_time_timestamp)
            uptime_seconds = (datetime.now() - boot_time_datetime).total_seconds()

            days = int(uptime_seconds // (24 * 3600))
            uptime_seconds %= (24 * 3600)
            hours = int(uptime_seconds // 3600)
            uptime_seconds %= 3600
            minutes = int(uptime_seconds // 60)
            
            uptime_str = f"{days}d {hours}h {minutes}m"

            # Temperature is hard to get reliably from inside a Docker container without host privileges.
            # We'll put N/A or try a generic Linux path if available.
            temp_celsius = "N/A"
            try:
                # Common path for CPU temperature on Linux (though in Docker it might not be available or reflect host)
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    temp_output_sys = f.read().strip()
                    temp_celsius = float(temp_output_sys) / 1000
                    temp_celsius = f"{temp_celsius:.1f}"
            except Exception:
                pass # Keep "N/A" if file not found or error reading

            system_status_message = (
                f"📊 *System Status (Container's View):*\n"
                f"  *OS*: `{platform.system()} {platform.release()}`\n"
                f"  *Architecture*: `{platform.machine()}`\n"
                f"  *CPU Usage*: `{cpu_percent:.1f}%`\n"
                f"  *RAM Usage*: `{used_ram_gb:.2f} GB / {total_ram_gb:.2f} GB ({percent_ram_used:.1f}%)`\n"
                f"  *Uptime*: `{uptime_str}`\n"
                f"  *CPU Temp*: `{temp_celsius}°C` (Container's or N/A)"
            )
            self.telegram_utils.send_telegram(system_status_message)
            logger.info("System status sent.")
        except Exception as e:
            error_message = f"Error getting system status: {e}"
            logger.error(error_message)
            self.telegram_utils.send_telegram(f"Failed to get system status: {e} ❌")

    def change_cron_interval(self, minutes: int) -> None:
        """Placeholder for changing cron interval. This typically affects the host, not the container directly."""
        self.telegram_utils.send_telegram(f"Cron interval change requested to {minutes} minutes. (Not directly managed by this container's SyncManager) ⚠️")
        logger.info(f"Cron interval change requested to {minutes} minutes (placeholder).")

    def disable_auto_sync(self) -> None:
        """Placeholder for disabling auto sync. This typically affects the host, not the container directly."""
        self.telegram_utils.send_telegram("Auto synchronization disable requested. (Not directly managed by this container's SyncManager) ⚠️")
        logger.info("Auto sync disable requested (placeholder).")

    def enable_auto_sync(self) -> None:
        """Placeholder for enabling auto sync. This typically affects the host, not the container directly."""
        self.telegram_utils.send_telegram("Auto synchronization enable requested. (Not directly managed by this container's SyncManager) ✅")
        logger.info("Auto sync enable requested (placeholder).")