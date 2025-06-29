# sync_utils.py
"""
Utilidades auxiliares para operaciones de sincronización (rsync).
Incluye helpers para construir comandos, parsear salidas y validar rutas.
"""
import re
from typing import List


def build_rsync_command(src: str, dest: str, options: str = "-avz --stats --itemize-changes") -> List[str]:
    """
    Construye el comando rsync como lista para subprocess.
    """
    return [
        "rsync",
        "-e", "ssh -i /root/.ssh/id_rsa -o StrictHostKeyChecking=no",
        *options.split(),
        src,
        dest
    ]


def is_valid_rsync_path(path: str) -> bool:
    """
    Valida si el path tiene formato user@host:/ruta.
    """
    return bool(re.match(r"^.+@.+:.+", path))


def parse_rsync_output(output: str) -> dict:
    """
    Parser simple de la salida de rsync para extraer estadísticas básicas.
    """
    stats = {
        "sent_bytes": 0,
        "received_bytes": 0,
        "total_size": 0
    }
    for line in output.splitlines():
        if "Total bytes sent:" in line:
            stats["sent_bytes"] = int(re.findall(r"\d+", line)[0])
        elif "Total bytes received:" in line:
            stats["received_bytes"] = int(re.findall(r"\d+", line)[0])
        elif "total size is" in line:
            stats["total_size"] = int(re.findall(r"\d+", line)[0])
    return stats
