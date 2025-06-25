import os
import subprocess
import datetime
import time
import shutil

# Importa la función send_telegram y la bandera stop_sync_flag de telegram_utils
# Necesitamos ajustar el sys.path para que pueda encontrar el módulo utils
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))
from utils.telegram_utils import send_telegram, stop_sync_flag


# Constantes globales del módulo
LOG_DIR = "/logs"
DATA_DIR = "/data" # Directorio de destino local

class SyncManager:
    def __init__(self):
        self.rsync_from = os.getenv("RSYNC_FROM")
        # Ya no se necesita esta línea si siempre usas el volumen montado /data
        # self.RSYNC_DEST_HOST_PATH = os.getenv("RSYNC_DEST_HOST_PATH")
        self.max_retries = 3
        self.retry_delay_seconds = 5

        # Umbral de espacio en disco para alertas (ej. 10 GB)
        self.disk_space_threshold_gb = 10

        # Asegúrate de que RSYNC_FROM y DATA_DIR (que es la ruta interna)
        # estén definidos al inicio, si no, fallaría aquí.
        if not self.rsync_from:
            error_msg = "ERROR CRÍTICO: La variable 'rsync_from' (RSYNC_FROM) no está definida."
            self._log_message(error_msg, os.path.join(LOG_DIR, "error.log"))
            send_telegram(f"❌ *Error interno: Origen de Rsync (RSYNC_FROM) no definido.*")
            raise ValueError(error_msg)
        # DATA_DIR es una constante, pero un chequeo defensivo podría ir aquí si fuera dinámico.

    def _log_message(self, message: str, logfile: str):
        """
        Registra un mensaje en un archivo de log específico con una marca de tiempo.
        Método auxiliar privado.
        """
        os.makedirs(os.path.dirname(logfile), exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(logfile, "a") as f:
            f.write(f"[{timestamp}] {message}\n")

    def _get_disk_space_info(self, path: str) -> tuple[float, float, float]:
        """
        Obtiene el espacio total, usado y libre en GB para una ruta.
        Devuelve (total_gb, used_gb, free_gb).
        """
        total, used, free = shutil.disk_usage(path)
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        free_gb = free / (1024**3)
        return total_gb, used_gb, free_gb

    def _check_disk_space(self, path: str, log_file: str) -> bool:
        """
        Verifica el espacio disponible en disco y envía una alerta si es bajo.
        """
        try:
            total_gb, used_gb, free_gb = self._get_disk_space_info(path)
            self._log_message(f"Espacio en disco disponible en {path}: {free_gb:.2f} GB (Total: {total_gb:.2f} GB, Usado: {used_gb:.2f} GB)", log_file)

            if free_gb < self.disk_space_threshold_gb:
                alert_msg = f"⚠️ *Alerta de Espacio en Disco Bajo:*\n" \
                            f"Quedan {free_gb:.2f} GB libres de {total_gb:.2f} GB en `{path}`.\n" \
                            f"Umbral de alerta: {self.disk_space_threshold_gb} GB."
                send_telegram(alert_msg) # Utiliza la función send_telegram importada
                self._log_message(alert_msg, log_file)
            return True
        except Exception as e:
            error_msg = f"❌ *Error al verificar espacio en disco en {path}:* `{e}`"
            self._log_message(error_msg, log_file)
            send_telegram(error_msg) # Utiliza la función send_telegram importada
            return False

    def run_rsync(self, direction: str):
        """
        Ejecuta el comando rsync para la dirección especificada y envía notificaciones.
        Incluye reintentos automáticos y verificación de espacio en disco.
        """
        if direction == "from":
            src = self.rsync_from
            dest = DATA_DIR
            log_file = os.path.join(LOG_DIR, "from_pi.log")
            desc = "desde Raspberry Pi"
        else:
            log_file = os.path.join(LOG_DIR, "error.log")
            self._log_message(f"ERROR: Se intentó ejecutar una sincronización con dirección inválida: '{direction}'. Solo 'from' está soportado.", log_file)
            send_telegram(f"❌ *Error interno: Intento de sincronización con dirección no soportada: {direction}*")
            return

        # No es necesario chequear src y dest de nuevo si ya los chequeamos en __init__
        # y DATA_DIR es una constante.
        # Solo si rsync_from pudiera cambiar a None después de init por alguna razón.
        if src is None: # Redundante si el init ya lanza un error, pero no hace daño
            self._log_message(f"ERROR CRÍTICO: La variable 'src' (RSYNC_FROM) es None para la dirección '{direction}'", log_file)
            send_telegram(f"❌ *Error interno: Origen de Rsync (RSYNC_FROM) no definido para {desc}*")
            return
        if dest is None: # Esto no debería ocurrir, DATA_DIR es constante
            self._log_message(f"ERROR CRÍTICO: La variable 'dest' es None para la dirección '{direction}'", log_file)
            send_telegram(f"❌ *Error interno: Destino de Rsync no definido para {desc}*")
            return

        # --- AÑADIDO: Verificar la bandera de detención antes de iniciar Rsync ---
        if stop_sync_flag.is_set():
            self._log_message("Sincronización cancelada: el comando /stop fue emitido. La bandera de detención se ha limpiado.", log_file)
            send_telegram(f"❌ *Sincronización {desc} cancelada*: El comando `/stop` fue recibido. Bandera de detención eliminada.")
            stop_sync_flag.clear() # Limpia la bandera para futuras sincronizaciones
            return
        # -----------------------------------------------------------------------

        # Verificación de espacio en disco antes de la sincronización
        if not self._check_disk_space(dest, log_file):
            self._log_message("Sincronización abortada debido a un error en la verificación de espacio en disco.", log_file)
            send_telegram(f"❌ *Sincronización {desc} abortada: Problema al verificar espacio en disco.*")
            return

        self._log_message(f"Iniciando sincronización {desc}", log_file)

        cmd = [
            "rsync",
            "-e", "ssh -i /root/.ssh/id_rsa -o StrictHostKeyChecking=no",
            "-avz", # -a para archivo, -v para verboso (más detalles), -z para compresión
            src,
            dest
        ]

        self._log_message(f"Comando rsync a ejecutar: {' '.join(cmd)}", log_file)

        for attempt in range(1, self.max_retries + 1):
            try:
                self._log_message(f"Intento {attempt}/{self.max_retries} para sincronizar.", log_file)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                self._log_message(result.stdout, log_file)

                if result.returncode == 0:
                    output_lines = result.stdout.strip().split('\n')
                    received_bytes_str = "0"
                    for line in reversed(output_lines):
                        if "received" in line and "bytes" in line:
                            parts = line.split("received")
                            if len(parts) > 1:
                                received_bytes_str = parts[1].split("bytes")[0].strip().replace(",", "")
                                break
                     
                    received_bytes = int(received_bytes_str)

                    # Obtener info de espacio en disco para el mensaje de éxito
                    total_gb, used_gb, free_gb = self._get_disk_space_info(dest)
                    disk_info_message = f"\n💾 Espacio en {dest}:\n" \
                                        f"  Total: {total_gb:.2f} GB\n" \
                                        f"  Usado: {used_gb:.2f} GB\n" \
                                        f"  Libre: {free_gb:.2f} GB"

                    if received_bytes > 100:
                        telegram_message = f"✅📥 *Sincronización exitosa {desc} - Cambios detectados y transferidos*\n\n"
                        telegram_message += "```\n" + "\n".join(output_lines[-5:]) + "\n```"
                        telegram_message += disk_info_message
                        send_telegram(telegram_message)
                    else:
                        telegram_message = f"✅🔄 *Sincronización exitosa {desc} - Sin cambios para transferir*\n"
                        telegram_message += disk_info_message
                        send_telegram(telegram_message)
                    return # Salir de la función al completar con éxito
                else:
                    self._log_message(f"Rsync stderr (Intento {attempt}): {result.stderr}", log_file)
                    if attempt < self.max_retries:
                        self._log_message(f"Reintentando en {self.retry_delay_seconds} segundos...", log_file)
                        time.sleep(self.retry_delay_seconds)
                        self.retry_delay_seconds *= 2
                    else:
                        telegram_message = f"❌🔥 *Fallo al sincronizar {desc} después de {self.max_retries} intentos*\n\n"
                        telegram_message += f"Código de salida: {result.returncode}\n"
                        telegram_message += f"```\n{result.stderr.strip()}\n```"
                        send_telegram(telegram_message)
            except subprocess.TimeoutExpired as e:
                self._log_message(f"Timeout (Intento {attempt}): {e}", log_file)
                if attempt < self.max_retries:
                    self._log_message(f"Reintentando en {self.retry_delay_seconds} segundos...", log_file)
                    time.sleep(self.retry_delay_seconds)
                    self.retry_delay_seconds *= 2
                else:
                    telegram_message = f"❌🚨 *Excepción de Timeout al sincronizar {desc} después de {self.max_retries} intentos*\n`{e}`"
                    send_telegram(telegram_message)
            except Exception as e:
                self._log_message(f"Error inesperado (Intento {attempt}): {e}", log_file)
                if attempt < self.max_retries:
                    self._log_message(f"Reintentando en {self.retry_delay_seconds} segundos...", log_file)
                    time.sleep(self.retry_delay_seconds)
                    self.retry_delay_seconds *= 2
                else:
                    telegram_message = f"❌🚨 *Excepción al sincronizar {desc} después de {self.max_retries} intentos*\n`{e}`"
                    send_telegram(telegram_message)
         
        # Asegurarse de que la bandera se limpie después de que todos los intentos hayan terminado (fallidos o no)
        stop_sync_flag.clear()
        self._log_message("Stop sync flag cleared after run_rsync completion.", log_file)