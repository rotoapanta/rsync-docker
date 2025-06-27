"""
File: managers/sync_manager.py
Description: This module defines the SyncManager class, which orchestrates the rsync
             synchronization process. It handles data transfers from a remote
             Raspberry Pi source to a local destination directory within the
             Docker container. Key functionalities include robust logging,
             pre-sync disk space checks, parsing rsync output for detailed
             statistics, and sending comprehensive notifications via Telegram,
             including retry mechanisms for enhanced reliability.
Author: Your Name
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
# If you want to configure more advanced logging (e.g., file rotation), do it here.
# For now, basic configuration to ensure messages are captured.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# Import send_telegram function. Ensure 'utils' directory is in sys.path
# This handles the import regardless of how the script is executed, as long
# as the 'utils' directory is a sibling to 'managers'.
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))
from utils.telegram_utils import send_telegram

# Global constants for the module
LOG_DIR = "/logs"
DATA_DIR = "/data" # Local destination directory within the container

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
        # Retrieve rsync source from environment variable
        self.rsync_from = os.getenv("RSYNC_FROM")
        # Configure retry parameters, with defaults if not set
        self.max_retries = int(os.getenv("RSYNC_MAX_RETRIES", 3))
        self.retry_delay_seconds = int(os.getenv("RSYNC_RETRY_DELAY", 5))

        # Disk space threshold for low space alerts, in Gigabytes (GB)
        self.disk_space_threshold_gb = int(os.getenv("DISK_SPACE_THRESHOLD_GB", 10))

        # Threshold for listing individual affected folders in Telegram messages.
        # If the number of affected folders exceeds this, only a count is displayed.
        self.FOLDER_LIST_THRESHOLD = int(os.getenv("FOLDER_LIST_THRESHOLD", 5))

        self._ensure_dirs() # Ensure required directories exist before proceeding

        # Critical check: if rsync source is not defined, raise an error
        if not self.rsync_from:
            error_msg = "CRITICAL ERROR: 'RSYNC_FROM' environment variable is not defined. Synchronization cannot proceed."
            self._log_message(error_msg, os.path.join(LOG_DIR, "error.log"))
            send_telegram(f"❌ *Internal Error: Rsync Source (RSYNC_FROM) not defined.*")
            raise ValueError(error_msg)

    def _ensure_dirs(self):
        """
        Ensures that the application's essential directories, `DATA_DIR` (for synced data)
        and `LOG_DIR` (for logs), exist. If either directory does not exist, it is created.
        This prevents potential I/O errors during file operations.
        """
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(LOG_DIR, exist_ok=True)

    def _log_message(self, message: str, logfile: str):
        """
        Logs a given message to a specified log file, prepending a timestamp for traceability.
        Additionally, the message is also output to the standard application logger,
        which typically directs to the console or Docker container logs.

        Args:
            message (str): The content of the message to be logged.
            logfile (str): The full path to the log file where the message will be appended.
        """
        os.makedirs(os.path.dirname(logfile), exist_ok=True) # Ensure the directory for the log file exists
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(logfile, "a") as f:
                f.write(f"[{timestamp}] {message}\n")
        except IOError as e:
            logger.error(f"Failed to write to log file {logfile}: {e}")
        logger.info(message) # Also log to the standard application logger

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
                return False # Indicate insufficient space
            return True # Indicate sufficient space
        except Exception as e:
            error_msg = f"❌ *Error checking disk space on {path}:* `{e}`"
            self._log_message(error_msg, log_file)
            send_telegram(error_msg)
            return False # Indicate failure in disk space check

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
                  Key-value pairs include:
                  - "sent_bytes": Bytes sent to the remote host.
                  - "received_bytes": Bytes received from the remote host.
                  - "total_size": Total size of files on the source for comparison.
                  - "speed_bps": Transfer speed in bytes per second.
                  - "new_files": Count of newly created files.
                  - "modified_files": Count of files whose content/metadata changed.
                  - "deleted_files": Count of files deleted on the destination.
                  - "new_folders": Count of newly created directories.
                  - "modified_folders": Count of directories whose contents/metadata changed.
                  - "new_folder_names": List of full paths for new folders.
                  - "modified_folder_names": List of full paths for modified folders.
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
            "modified_folders": 0,
            "new_folder_names": [],
            "modified_folder_names": []
        }

        # Split output into lines for easier processing
        output_lines = rsync_output.strip().split('\n')
        
        # Regex to capture rsync itemized changes format:
        # <f+++++++++ : new file received
        # .f.T...... : file with timestamp/permission change
        # *deleting   : file being deleted
        # cd+++++++++ : new directory created
        # .d..t...... : existing directory with changed contents/metadata
        # The path part `(?P<path>.+)` captures the rest of the line, allowing for spaces.
        item_regex = re.compile(r'^(?P<flags>[.cd+*<>])(?P<perm_flags>[a-zA-Z0-9.\-+\/\\]{8})\s+(?P<path>.+)$')

        # Use sets to store unique folder paths to avoid duplicates from multiple itemized entries
        unique_new_folders = set()
        unique_modified_folders = set()

        for line in output_lines:
            # --- Parse itemized changes for individual file and folder names ---
            match = item_regex.match(line)
            if match:
                flags = match.group('flags')
                path = match.group('path').strip() # Extract path and strip whitespace
                
                # Determine if the item is a directory based on the 'd' flag in rsync's output
                is_directory_by_flag = 'd' in flags
                
                # Construct the full path within the local destination directory
                # rstrip('/') ensures consistent path formatting by removing trailing slashes
                full_path_in_dest = os.path.join(DATA_DIR, path).rstrip('/')

                if is_directory_by_flag: 
                    if flags.startswith('c'): # 'c' flag indicates a new directory creation (e.g., 'cd+++++++++')
                        unique_new_folders.add(full_path_in_dest)
                    elif 't' in flags or 's' in flags or ('+' in flags and not flags.startswith('c')):
                        # 't' for timestamp/permissions change, 's' for size change (implies content),
                        # or other flags indicating modification for an existing directory
                        unique_modified_folders.add(full_path_in_dest)
                else: # The item is a file
                    if flags.startswith('<') or flags.startswith('c'): # File received (new or updated) or created from copy
                        stats["new_files"] += 1
                    elif 't' in flags or 's' in flags: # File with changed timestamp/size
                        stats["modified_files"] += 1
                    elif flags.startswith('*'): # File being deleted (e.g., '*deleting')
                        stats["deleted_files"] += 1
            
            # --- Parse summary statistics provided by `--stats` output lines ---
            if "Total bytes sent:" in line:
                match = re.search(r'Total bytes sent:\s*([\d\.,]+)', line)
                if match:
                    # Remove dots/commas from the number string and convert to integer
                    stats["sent_bytes"] = int(match.group(1).replace('.', '').replace(',', ''))
            elif "Total bytes received:" in line:
                match = re.search(r'Total bytes received:\s*([\d\.,]+)', line)
                if match:
                    stats["received_bytes"] = int(match.group(1).replace('.', '').replace(',', ''))
            elif "total size is" in line and "speedup is" in line:
                # This line contains both total size and speed information
                match_total_size = re.search(r'total size is\s*([\d\.,]+)', line)
                if match_total_size:
                    stats["total_size"] = int(match_total_size.group(1).replace('.', '').replace(',', ''))
                
                speed_match = re.search(r'([\d\.,]+)\s*bytes/sec', line)
                if speed_match:
                    stats["speed_bps"] = float(speed_match.group(1).replace('.', '').replace(',', ''))
            elif "Number of created files:" in line:
                # This statistic is usually more precise for new files than itemized flags
                match = re.search(r'Number of created files:\s*(\d+)', line)
                if match:
                    stats["new_files"] = int(match.group(1))
            elif "Number of deleted files:" in line:
                match = re.search(r'Number of deleted files:\s*(\d+)', line)
                if match:
                    stats["deleted_files"] = int(match.group(1))

        # --- Final processing for folders: convert sets to sorted lists ---
        stats["new_folder_names"] = sorted(list(unique_new_folders))
        stats["modified_folder_names"] = sorted(list(unique_modified_folders))
        
        # Update folder counts based on the unique lists
        stats["new_folders"] = len(stats["new_folder_names"])
        stats["modified_folders"] = len(stats["modified_folder_names"])

        return stats

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
        # Determine source, destination, log file, and description based on direction
        if direction == "from":
            src = self.rsync_from
            dest = DATA_DIR
            log_file = os.path.join(LOG_DIR, "from_pi.log")
            desc = "from Raspberry Pi"
        else:
            # Log and notify if an unsupported direction is provided
            log_file = os.path.join(LOG_DIR, "error.log")
            self._log_message(f"ERROR: Attempted to run synchronization with invalid direction: '{direction}'. Only 'from' is supported.", log_file)
            send_telegram(f"❌ *Internal Error: Synchronization attempt with unsupported direction: {direction}*")
            return

        # Validate critical source and destination paths
        if src is None:
            self._log_message(f"CRITICAL ERROR: 'src' (RSYNC_FROM) variable is None for direction '{direction}'", log_file)
            send_telegram(f"❌ *Internal Error: Rsync Source (RSYNC_FROM) not defined for {desc}*")
            return
        if dest is None:
            self._log_message(f"CRITICAL ERROR: 'dest' variable is None for direction '{direction}'", log_file)
            send_telegram(f"❌ *Internal Error: Rsync Destination not defined for {desc}*")
            return

        # Pre-check: Verify sufficient disk space before starting synchronization
        if not self._check_disk_space(dest, log_file):
            self._log_message("Synchronization aborted due to a disk space check error.", log_file)
            send_telegram(f"❌ *Synchronization {desc} aborted: Disk space check issue.*")
            return

        self._log_message(f"Initiating synchronization {desc}", log_file)

        # Define the rsync command with necessary options
        cmd = [
            "rsync",
            "-e", "ssh -i /root/.ssh/id_rsa -o StrictHostKeyChecking=no", # SSH options: specify identity file and disable strict host key checking
            "-avz", # -a: archive mode (preserves permissions, timestamps, recursive copy); -v: verbose; -z: compress file data
            "--stats", # Include transfer statistics in the output
            "--itemize-changes", # Show a detailed list of changes for easier parsing
            src, # Source path
            dest # Destination path
        ]

        self._log_message(f"Rsync command to execute: {' '.join(cmd)}", log_file)

        # Loop for multiple retry attempts
        for attempt in range(1, self.max_retries + 1):
            # Calculate current retry delay with exponential backoff
            current_retry_delay = self.retry_delay_seconds * (2 ** (attempt - 1))
            try:
                self._log_message(f"Attempt {attempt}/{self.max_retries} to synchronize.", log_file)
                
                # Execute rsync command with a timeout
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300) # 300 seconds (5 minutes) timeout
                self._log_message(f"Rsync STDOUT:\n{result.stdout}", log_file)
                if result.stderr: # Log stderr only if there's content
                    self._log_message(f"Rsync STDERR:\n{result.stderr}", log_file)

                output_lines = result.stdout.strip().split('\n')

                if result.returncode == 0:
                    # Synchronization successful. Parse output and send notification.
                    parsed_stats = self._parse_rsync_output(result.stdout)
                    
                    # Determine if any actual data changes (new, modified, deleted) occurred
                    any_changes = (
                        parsed_stats.get("received_bytes", 0) > 0 or
                        parsed_stats.get("new_files", 0) > 0 or
                        parsed_stats.get("modified_files", 0) > 0 or
                        parsed_stats.get("deleted_files", 0) > 0 or
                        parsed_stats.get("new_folders", 0) > 0 or
                        parsed_stats.get("modified_folders", 0) > 0
                    )

                    # Extract the relevant rsync summary block from stdout for the Telegram message
                    rsync_summary_block_lines = []
                    capture_summary = False
                    for line in output_lines:
                        # Heuristics to identify the start of the summary block (e.g., "Number of files:")
                        if "Number of files:" in line or "Number of created files:" in line or "Total transferred file size:" in line:
                            capture_summary = True
                        
                        if capture_summary:
                            rsync_summary_block_lines.append(line)
                            # Stop capturing after the last summary line (e.g., "speedup is")
                            if "total size is" in line and "speedup is" in line:
                                break 

                    summary_code_block = ""
                    if rsync_summary_block_lines:
                        # Filter to keep only the core statistics lines for a concise summary
                        filtered_summary_lines = []
                        start_stats = False
                        for line in rsync_summary_block_lines:
                            if "Number of files:" in line or "Total bytes sent:" in line or "total size is" in line:
                                start_stats = True
                            if start_stats:
                                filtered_summary_lines.append(line)
                        
                        summary_code_block = "\n".join(filtered_summary_lines).strip()
                    
                    # Construct the Telegram message title based on whether changes were detected
                    telegram_message_title = f"✅📥 *Synchronization successful {desc}"
                    if any_changes:
                        telegram_message_title += " - Changes detected and transferred*"
                    else:
                        telegram_message_title += " - No changes detected*"
                    telegram_message_title += "\n\n" # Add extra newline for formatting
                    
                    # Build the affected folders section for the Telegram message
                    folder_summary_text = ""
                    total_affected_folders = parsed_stats['new_folders'] + parsed_stats['modified_folders']

                    if total_affected_folders > 0:
                        folder_summary_text += "\n📂 *Affected Folders:*\n"
                        if total_affected_folders <= self.FOLDER_LIST_THRESHOLD:
                            # List individual folder names if within the configured threshold
                            for folder_name in parsed_stats['new_folder_names']:
                                display_name = folder_name.replace(DATA_DIR, '')
                                if display_name.startswith('/'): # Remove leading slash if present after replace
                                    display_name = display_name[1:]
                                folder_summary_text += f"├ New: `{display_name}`\n"
                            for folder_name in parsed_stats['modified_folder_names']:
                                display_name = folder_name.replace(DATA_DIR, '')
                                if display_name.startswith('/'):
                                    display_name = display_name[1:]
                                folder_summary_text += f"├ Updated: `{display_name}`\n"
                        else:
                            # Show only counts if the number of affected folders is too high
                            folder_summary_text += (
                                f"├ Total new: {parsed_stats['new_folders']}\n"
                                f"└ Total updated: {parsed_stats['modified_folders']}\n"
                                f"(Details in logs: `{log_file}`)\n"
                            )
                    
                    # Combine all parts to form the final Telegram message
                    telegram_message = telegram_message_title + folder_summary_text
                    
                    # Append the rsync summary block (raw rsync statistics) if available
                    if summary_code_block:
                        telegram_message += f"\n```\n{summary_code_block}\n```"
                    
                    send_telegram(telegram_message) # Send the success notification
                    return # Exit the function upon successful completion

                else: # Rsync returned a non-zero exit code, indicating a failure
                    self._log_message(f"Rsync command failed (Attempt {attempt}, Exit Code: {result.returncode}).", log_file)
                    self._log_message(f"Rsync STDOUT:\n{result.stdout}", log_file)
                    self._log_message(f"Rsync STDERR:\n{result.stderr}", log_file)
                    
                    if attempt < self.max_retries:
                        # Log and wait before retrying
                        self._log_message(f"Retrying in {current_retry_delay} seconds...", log_file)
                        time.sleep(current_retry_delay)
                    else:
                        # All retries exhausted, send final failure notification
                        telegram_message = (
                            f"❌🔥 *Failed to synchronize {desc} after {self.max_retries} attempts*\n\n"
                            f"Exit code: `{result.returncode}`\n"
                            f"STDOUT (partial): ```{result.stdout[:500] if result.stdout else 'N/A'}...```\n"
                            f"STDERR (partial): ```{result.stderr[:500] if result.stderr else 'N/A'}...```"
                        )
                        send_telegram(telegram_message)
            except subprocess.TimeoutExpired as e:
                # Handle rsync command timeout exception
                self._log_message(f"Rsync command timed out (Attempt {attempt}). Timeout: {e.timeout} seconds.", log_file)
                self._log_message(f"Timeout STDOUT:\n{e.stdout}", log_file)
                self._log_message(f"Timeout STDERR:\n{e.stderr}", log_file)
                
                if attempt < self.max_retries:
                    # Log and wait before retrying
                    self._log_message(f"Retrying in {current_retry_delay} seconds...", log_file)
                    time.sleep(current_retry_delay)
                else:
                    # All retries exhausted due to timeout, send final notification
                    telegram_message = (
                        f"❌🚨 *Rsync Timeout Exception during sync {desc} after {self.max_retries} attempts*\n"
                        f"Timeout: `{e.timeout} seconds`\n"
                        f"Check logs for details: `{log_file}`"
                    )
                    send_telegram(telegram_message)
            except Exception as e:
                # Handle any other unexpected exceptions during the process
                self._log_message(f"Unexpected error during synchronization (Attempt {attempt}): {e}", log_file)
                if attempt < self.max_retries:
                    # Log and wait before retrying
                    self._log_message(f"Retrying in {current_retry_delay} seconds...", log_file)
                    time.sleep(current_retry_delay)
                else:
                    # All retries exhausted due to unexpected error, send final notification
                    telegram_message = (
                        f"❌🚨 *Unexpected Exception during sync {desc} after {self.max_retries} attempts*\n"
                        f"Error: `{e}`\n"
                        f"Check logs for details: `{log_file}`"
                    )
                    send_telegram(telegram_message)