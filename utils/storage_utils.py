# storage_utils.py
"""
Utilidades para manejo y reporte de almacenamiento.
Centraliza helpers para uso de disco, validación de espacio y formateo de reportes.
"""
import os
from shutil import disk_usage


def get_disk_usage_info(path: str):
    """
    Retorna una tupla (total, used, free) en bytes para el path dado.
    """
    return disk_usage(path)


def has_enough_disk_space(path: str, min_free_gb: float) -> bool:
    """
    Verifica si hay al menos min_free_gb GB libres en el path dado.
    """
    _, _, free = get_disk_usage_info(path)
    free_gb = free / (1024 ** 3)
    return free_gb >= min_free_gb


def format_disk_report(path: str) -> str:
    """
    Devuelve un string formateado con el uso de disco del path dado.
    """
    total, used, free = get_disk_usage_info(path)
    return (
        f"📦 *Storage (`{path}`)*\n"
        f"├ 🧱 Total: `{total / (1024**3):.2f} GB`\n"
        f"├ 📂 Used: `{used / (1024**3):.2f} GB`\n"
        f"└ 📦 Free: `{free / (1024**3):.2f} GB`"
    )
