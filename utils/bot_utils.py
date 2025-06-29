# bot_utils.py
"""
Helpers y utilidades generales para el bot de sincronización y monitoreo.
Incluye helpers visuales, validadores y formateadores de mensajes.
"""
from typing import Tuple

def get_icon(value: float, thresholds: Tuple[int, int] = (50, 80)) -> str:
    """
    Devuelve un ícono visual según el valor y los umbrales dados.
    Ejemplo de uso: para reportes de CPU, RAM, disco, etc.
    """
    if value >= thresholds[1]:
        return "🔴"
    elif value >= thresholds[0]:
        return "🟠"
    return "🟢"

# Aquí puedes añadir más helpers de validación y formateo para comandos del bot.
