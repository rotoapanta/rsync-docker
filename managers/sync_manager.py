import os
import subprocess
import datetime
from utils.telegram_utils import send_telegram

LOG_DIR = "/logs"
DATA_DIR = "/data"

RSYNC_FROM = os.getenv("RSYNC_FROM")

def log_message(message, logfile):
    os.makedirs(os.path.dirname(logfile), exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(logfile, "a") as f:
        f.write(f"[{timestamp}] {message}\n")

def run_rsync(direction):
    if direction == "from":
        src = RSYNC_FROM
        dest = DATA_DIR
        log_file = os.path.join(LOG_DIR, "from_pi.log")
        desc = "desde Raspberry Pi"
    else:
        log_file = os.path.join(LOG_DIR, "error.log")
        log_message(f"ERROR: Se intentó ejecutar una sincronización con dirección inválida: '{direction}'. Solo 'from' está soportado.", log_file)
        send_telegram(f"❌ *Error interno: Intento de sincronización con dirección no soportada: {direction}*")
        return

    if src is None:
        log_message(f"ERROR CRÍTICO: La variable 'src' (RSYNC_FROM) es None para la dirección '{direction}'", log_file)
        send_telegram(f"❌ *Error interno: Origen de Rsync (RSYNC_FROM) no definido para {desc}*")
        return
    if dest is None:
        log_message(f"ERROR CRÍTICO: La variable 'dest' es None para la dirección '{direction}'", log_file)
        send_telegram(f"❌ *Error interno: Destino de Rsync no definido para {desc}*")
        return

    log_message(f"Iniciando sincronización {desc}", log_file)

    cmd = [
        "rsync",
        "-e", "ssh -i /root/.ssh/id_rsa -o StrictHostKeyChecking=no",
        "-avz", # -a para archivo, -v para verboso (más detalles), -z para compresión
        src,
        dest
    ]

    log_message(f"Comando rsync a ejecutar: {' '.join(cmd)}", log_file)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        log_message(result.stdout, log_file) # La salida estándar de rsync se sigue logueando

        if result.returncode == 0:
            # Sincronización exitosa
            telegram_message = f"✅ *Sincronización exitosa {desc}*\n\n"
            # Añadir las últimas 5 líneas de la salida de rsync (resumen)
            output_lines = result.stdout.strip().split('\n')
            if len(output_lines) > 5:
                telegram_message += "```\n" + "\n".join(output_lines[-5:]) + "\n```"
            else:
                telegram_message += "```\n" + result.stdout.strip() + "\n```"
            send_telegram(telegram_message)
        else:
            # Sincronización fallida
            log_message(f"Rsync stderr: {result.stderr}", log_file)
            telegram_message = f"❌ *Fallo al sincronizar {desc}*\n\n"
            telegram_message += f"Código de salida: {result.returncode}\n"
            telegram_message += f"```\n{result.stderr.strip()}\n```" # Incluye la salida de error completa
            send_telegram(telegram_message)
    except Exception as e:
        log_message(f"Error: {e}", log_file)
        send_telegram(f"❌ *Excepción al sincronizar {desc}*\n`{e}`")