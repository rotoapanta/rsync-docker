import os
import subprocess
import datetime
import time
import shutil
import re # Make sure this is imported for regular expressions

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

        # Threshold for listing individual folders in Telegram message
        # If more than this many affected folders, only show counts.
        self.FOLDER_LIST_THRESHOLD = 5

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

    def _parse_rsync_output(self, rsync_output: str) -> dict:
        """
        Parses the rsync --itemize-changes and --stats output to extract
        transfer statistics and affected folder/file information.

        Args:
            rsync_output (str): The full stdout string from the rsync command.

        Returns:
            dict: A dictionary containing parsed statistics and lists of affected items.
        """
        stats = {
            "sent_bytes": 0,
            "received_bytes": 0,
            "total_size": 0, # Total size of files on the source
            "speed_bps": 0,
            "new_files": 0,
            "modified_files": 0,
            "deleted_files": 0,
            "new_folders": 0,
            "modified_folders": 0, # Folders that existed but had content changes
            "new_folder_names": [], # List of paths for new folders
            "modified_folder_names": [] # List of paths for modified folders
        }

        # Split output into lines for easier processing
        output_lines = rsync_output.strip().split('\n')
        
        # Regex to capture rsync itemized changes format for files and directories
        # <f+++++++++ : new file
        # .f.T...... : file with timestamp change
        # *deleting   : file being deleted
        # cd+++++++++ : new directory
        # .d..t...... : existing directory with changed contents/metadata
        # The path can contain spaces, so we use .+
        item_regex = re.compile(r'^(?P<flags>[.cd+*<>])(?P<perm_flags>[a-zA-Z0-9.\-+\/\\]{8})\s+(?P<path>.+)$')


        # Sets to store unique full paths to avoid duplicates for folders
        unique_new_folders = set()
        unique_modified_folders = set()

        for line in output_lines:
            # --- Parse itemized changes for folder and file names ---
            match = item_regex.match(line)
            if match:
                flags = match.group('flags')
                path = match.group('path').strip() # Get the path and strip whitespace
                
                # Determine if it's a directory. Rsync usually appends '/' for directories,
                # or 'd' flag signifies directory.
                # Use 'd' in flags for directories, as rsync --itemize-changes explicitly marks directories with 'd'.
                is_directory_by_flag = 'd' in flags
                
                # Construct full path within the destination directory.
                # rstrip('/') is important to handle cases where rsync path might or might not have trailing slash,
                # ensuring consistent path for comparison/storage.
                full_path_in_dest = os.path.join(DATA_DIR, path).rstrip('/')

                if is_directory_by_flag: 
                    if flags.startswith('c'): # 'c' for new directory created (cd+++++++++)
                        unique_new_folders.add(full_path_in_dest)
                    elif 't' in flags or 's' in flags or ('+' in flags and not flags.startswith('c')):
                        # 't' for modified timestamp/permissions, 's' for size change (implies content change)
                        # or other flags indicating modification for existing directory (e.g., if a file inside changed)
                        unique_modified_folders.add(full_path_in_dest)
                else: # It's a file
                    if flags.startswith('<') or flags.startswith('c'): # Received file (new or updated) or created from copy
                        stats["new_files"] += 1
                    elif 't' in flags or 's' in flags: # File with changed timestamp/size
                        stats["modified_files"] += 1
                    elif flags.startswith('*'): # Deleted file (*deleting)
                        stats["deleted_files"] += 1
            
            # --- Parse summary statistics provided by --stats ---
            if "Total bytes sent:" in line:
                match = re.search(r'Total bytes sent:\s*([\d\.,]+)', line)
                if match:
                    # Remove dots/commas and convert to int
                    stats["sent_bytes"] = int(match.group(1).replace('.', '').replace(',', ''))
            elif "Total bytes received:" in line:
                match = re.search(r'Total bytes received:\s*([\d\.,]+)', line)
                if match:
                    # Remove dots/commas and convert to int
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
                    # This is usually more accurate for new files than itemized flags, so prioritize it
                    stats["new_files"] = int(match.group(1))
            elif "Number of deleted files:" in line:
                match = re.search(r'Number of deleted files:\s*(\d+)', line)
                if match:
                    stats["deleted_files"] = int(match.group(1))

        # --- Final processing for folders ---
        # Convert sets to sorted lists
        stats["new_folder_names"] = sorted(list(unique_new_folders))
        stats["modified_folder_names"] = sorted(list(unique_modified_folders))
        
        stats["new_folders"] = len(stats["new_folder_names"])
        stats["modified_folders"] = len(stats["modified_folder_names"])

        return stats

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
            "--stats", # Include transfer statistics
            "--itemize-changes", # Show detailed changes for parsing
            src,
            dest
        ]

        self._log_message(f"Rsync command to execute: {' '.join(cmd)}", log_file)

        for attempt in range(1, self.max_retries + 1):
            result = None
            try:
                self._log_message(f"Attempt {attempt}/{self.max_retries} to synchronize.", log_file)
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                self._log_message(result.stdout, log_file)
                self._log_message(result.stderr, log_file)

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

                    # --- Extract the specific rsync summary block ---
                    rsync_summary_block_lines = []
                    # Keywords that typically mark the start/end of the summary
                    capture_summary = False
                    for line in output_lines:
                        # Start capturing when a line indicates rsync is receiving/sending file list, or any line after the file list
                        # up until the "Total bytes" line. This handles cases where "receiving incremental file list" might not be present.
                        if "Number of files:" in line or "Number of created files:" in line or "Total transferred file size:" in line:
                            capture_summary = True
                        if capture_summary:
                            rsync_summary_block_lines.append(line)
                        if "total size is" in line and "speedup is" in line:
                            break # We have found the end of the summary block we want

                    # If the desired block was found, format it
                    summary_code_block = ""
                    if rsync_summary_block_lines:
                        # Clean up common preamble lines that are not part of the core summary stats we want to show
                        # Only keep lines from "Number of files:" onwards, or the stats block if files were transferred.
                        filtered_summary_lines = []
                        start_stats = False
                        for line in rsync_summary_block_lines:
                            if "Number of files:" in line or "Total bytes sent:" in line or "total size is" in line:
                                start_stats = True
                            if start_stats:
                                filtered_summary_lines.append(line)
                        
                        summary_code_block = "\n".join(filtered_summary_lines).strip()

                    # --- Construct the Telegram message ---
                    # Eliminado: Bloque de estadísticas de transferencia
                    telegram_message_title = f"✅📥 *Sincronización exitosa {desc} - Cambios detectados y transferidos*\n\n"
                    
                    folder_summary_text = ""
                    total_affected_folders = parsed_stats['new_folders'] + parsed_stats['modified_folders']

                    if total_affected_folders > 0:
                        folder_summary_text += "\n📂 *Carpetas afectadas:*\n"
                        if total_affected_folders <= self.FOLDER_LIST_THRESHOLD:
                            for folder_name in parsed_stats['new_folder_names']:
                                display_name = folder_name.replace(DATA_DIR, '')
                                if display_name.startswith('/'): 
                                    display_name = display_name[1:]
                                folder_summary_text += f"├ Nueva: `{display_name}`\n"
                            for folder_name in parsed_stats['modified_folder_names']:
                                display_name = folder_name.replace(DATA_DIR, '')
                                if display_name.startswith('/'):
                                    display_name = display_name[1:]
                                folder_summary_text += f"├ Actualizada: `{display_name}`\n"
                        else:
                            folder_summary_text += (
                                f"├ Total de nuevas: {parsed_stats['new_folders']}\n"
                                f"└ Total actualizadas: {parsed_stats['modified_folders']}\n"
                                f"(Detalle en los logs: `{log_file}`)\n"
                            )
                    
                    # Eliminado: stats_text. Se construye el mensaje solo con el título y el resumen de carpetas.
                    telegram_message = telegram_message_title + folder_summary_text
                    
                    # --- ADD THE RSYNC SUMMARY BLOCK HERE ---
                    if summary_code_block:
                        telegram_message += f"\n```\n{summary_code_block}\n```"
                    
                    send_telegram(telegram_message)

                    return # Exit the function upon successful completion
                else: # Rsync returned a non-zero exit code (failure)
                    self._log_message(f"Rsync stderr (Attempt {attempt}): {result.stderr}", log_file)
                    if attempt < self.max_retries:
                        self._log_message(f"Retrying in {self.retry_delay_seconds} seconds...", log_file)
                        time.sleep(self.retry_delay_seconds)
                        self.retry_delay_seconds *= 2 # Exponential backoff
                    else:
                        telegram_message = f"❌🔥 *Fallo al sincronizar {desc} después de {self.max_retries} intentos*\n\n"
                        telegram_message += f"Exit code: {result.returncode}\n"
                        telegram_message += f"```\n{result.stderr.strip()}\n```"
                        send_telegram(telegram_message)
            except subprocess.TimeoutExpired as e:
                self._log_message(f"Timeout (Attempt {attempt}): {e}", log_file)
                if attempt < self.max_retries:
                    self._log_message(f"Retrying in {self.retry_delay_seconds} seconds...", log_file)
                    time.sleep(self.retry_delay_seconds)
                    self.retry_delay_seconds *= 2
                else:
                    telegram_message = f"❌🚨 *Excepción de Timeout al sincronizar {desc} después de {self.max_retries} intentos*\n`{e}`"
                    send_telegram(telegram_message)
            except Exception as e:
                self._log_message(f"Unexpected error (Attempt {attempt}): {e}", log_file)
                if attempt < self.max_retries:
                    self._log_message(f"Retrying in {self.retry_delay_seconds} seconds...", log_file)
                    time.sleep(self.retry_delay_seconds)
                    self.retry_delay_seconds *= 2
                else:
                    telegram_message = f"❌🚨 *Excepción al sincronizar {desc} después de {self.max_retries} intentos*\n`{e}`"
                    send_telegram(telegram_message)