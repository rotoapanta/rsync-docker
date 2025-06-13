import os
import subprocess
import datetime
from utils.telegram_utils import send_telegram

# Constantes definidas fuera de la clase si son globales para el módulo
LOG_DIR = "/logs"
DATA_DIR = "/data"

class SyncManager:
    def __init__(self):
        # Las variables de entorno se obtienen una vez al inicializar el objeto
        self.rsync_from = os.getenv("RSYNC_FROM")
        # Si hubiera otras configuraciones específicas de rsync, irían aquí.

    def _log_message(self, message: str, logfile: str):
        """
        Registra un mensaje en un archivo de log específico con una marca de tiempo.
        Método auxiliar privado (convención con guion bajo).
        """
        os.makedirs(os.path.dirname(logfile), exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(logfile, "a") as f:
            f.write(f"[{timestamp}] {message}\n")

    def run_rsync(self, direction: str):
        """
        Ejecuta el comando rsync para la dirección especificada y envía notificaciones.
        """
        # Validar la dirección de sincronización
        if direction == "from":
            src = self.rsync_from
            dest = DATA_DIR # El destino es el volumen montado en el contenedor
            log_file = os.path.join(LOG_DIR, "from_pi.log")
            desc = "desde Raspberry Pi"
        else:
            # Si se llama con una dirección no soportada
            log_file = os.path.join(LOG_DIR, "error.log")
            self._log_message(f"ERROR: Se intentó ejecutar una sincronización con dirección inválida: '{direction}'. Solo 'from' está soportado.", log_file)
            send_telegram(f"❌ *Error interno: Intento de sincronización con dirección no soportada: {direction}*")
            return # Salir de la función

        # Verificar que las rutas de origen estén definidas
        if src is None:
            self._log_message(f"ERROR CRÍTICO: La variable 'src' (RSYNC_FROM) es None para la dirección '{direction}'", log_file)
            send_telegram(f"❌ *Error interno: Origen de Rsync (RSYNC_FROM) no definido para {desc}*")
            return
        # La variable 'dest' (DATA_DIR) es una constante global, no debería ser None,
        # pero el check se mantiene por si acaso en un diseño más general.
        if dest is None:
            self._log_message(f"ERROR CRÍTICO: La variable 'dest' es None para la dirección '{direction}'", log_file)
            send_telegram(f"❌ *Error interno: Destino de Rsync no definido para {desc}*")
            return

        self._log_message(f"Iniciando sincronización {desc}", log_file)

        # Construir el comando rsync
        cmd = [
            "rsync",
            "-e", "ssh -i /root/.ssh/id_rsa -o StrictHostKeyChecking=no",
            "-avz", # -a: archivo, -v: verboso, -z: compresión
            src,
            dest
        ]

        self._log_message(f"Comando rsync a ejecutar: {' '.join(cmd)}", log_file)

        try:
            # Ejecutar el comando rsync
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            self._log_message(result.stdout, log_file) # La salida estándar de rsync se sigue logueando

            if result.returncode == 0:
                # Sincronización exitosa
                output_lines = result.stdout.strip().split('\n')

                # Heurística para detectar si hubo transferencia real de archivos
                received_bytes_str = "0"
                for line in reversed(output_lines):
                    if "received" in line and "bytes" in line:
                        parts = line.split("received")
                        if len(parts) > 1:
                            received_bytes_str = parts[1].split("bytes")[0].strip().replace(",", "")
                            break
                
                received_bytes = int(received_bytes_str)

                if received_bytes > 100: # Si se recibieron más de 100 bytes, asumimos transferencia real
                    telegram_message = f"✅📥 *Sincronización exitosa {desc} - Cambios detectados y transferidos*\n\n"
                    # Incluir las últimas 5 líneas del resumen de rsync
                    telegram_message += "```\n" + "\n".join(output_lines[-5:]) + "\n```"
                    send_telegram(telegram_message)
                else:
                    # No se transfirieron archivos o solo metadatos mínimos
                    telegram_message = f"✅🔄 *Sincronización exitosa {desc} - Sin cambios para transferir*\n"
                    send_telegram(telegram_message)
            else:
                # Sincronización fallida
                self._log_message(f"Rsync stderr: {result.stderr}", log_file)
                telegram_message = f"❌🔥 *Fallo al sincronizar {desc}*\n\n"
                telegram_message += f"Código de salida: {result.returncode}\n"
                telegram_message += f"```\n{result.stderr.strip()}\n```" # Incluye la salida de error completa
                send_telegram(telegram_message)
        except Exception as e:
            # Excepción inesperada durante la ejecución del subproceso
            self._log_message(f"Error: {e}", log_file)
            send_telegram(f"❌🚨 *Excepción al sincronizar {desc}*\n`{e}`")