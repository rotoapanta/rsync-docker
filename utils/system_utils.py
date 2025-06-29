# system_utils.py
"""
Utilidades generales para obtener información y reportes del sistema.
Centraliza helpers para estado del sistema, ejecución de comandos y formateo de reportes.
"""
import os
import subprocess
import platform
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def get_hostname() -> str:
    return platform.node()


def get_ip_address() -> str:
    try:
        result = subprocess.run(["hostname", "-I"], capture_output=True, text=True, check=True)
        return result.stdout.strip().split()[0]
    except Exception as e:
        logger.error(f"Error getting IP address: {e}")
        return "?"


def get_cpu_usage() -> float:
    try:
        import psutil
        return psutil.cpu_percent(interval=1)
    except Exception as e:
        logger.error(f"Error getting CPU usage: {e}")
        return -1


def get_ram_usage() -> float:
    try:
        import psutil
        return psutil.virtual_memory().percent
    except Exception as e:
        logger.error(f"Error getting RAM usage: {e}")
        return -1


def get_uptime() -> str:
    try:
        import psutil
        from datetime import datetime
        boot_time = psutil.boot_time()
        uptime_seconds = (datetime.now().timestamp() - boot_time)
        days = int(uptime_seconds // (24 * 3600))
        uptime_seconds %= (24 * 3600)
        hours = int(uptime_seconds // 3600)
        uptime_seconds %= 3600
        minutes = int(uptime_seconds // 60)
        return f"{days}d {hours}h {minutes}m"
    except Exception as e:
        logger.error(f"Error getting uptime: {e}")
        return "?"


def get_temperature() -> Optional[float]:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = float(f.read().strip()) / 1000
            return temp
    except Exception:
        return None


def run_command(cmd: list) -> Tuple[int, str, str]:
    """
    Ejecuta un comando del sistema y retorna (returncode, stdout, stderr).
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return (result.returncode, result.stdout, result.stderr)
    except subprocess.CalledProcessError as e:
        return (e.returncode, e.stdout, e.stderr)
    except Exception as e:
        logger.error(f"Error running command {cmd}: {e}")
        return (-1, '', str(e))


def format_system_report() -> str:
    hostname = get_hostname()
    ip = get_ip_address()
    cpu = get_cpu_usage()
    ram = get_ram_usage()
    uptime = get_uptime()
    temp = get_temperature()
    temp_str = f"{temp:.1f}°C" if temp is not None else "N/A"
    return (
        f"🖥️ Hostname: `{hostname}`\n"
        f"🌐 IP: `{ip}`\n"
        f"🧠 CPU: `{cpu:.1f}%`\n"
        f"💾 RAM: `{ram:.1f}%`\n"
        f"⏱️ Uptime: `{uptime}`\n"
        f"🌡️ Temp: `{temp_str}`"
    )
