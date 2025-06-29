"""
commands.py
Centraliza los handlers de comandos del bot, utilizando la lógica de main.py, telegram_utils y sync_manager.
"""
from utils.telegram_utils import send_telegram
from managers.sync_manager import SyncManager
from utils.bot_utils import get_icon

# Instancia global de SyncManager (puede ser pasada desde main.py si se prefiere)
sync_manager_instance = SyncManager()

def sync_command(direction: str = "from"):
    try:
        sync_manager_instance.run_rsync(direction)
        send_telegram(f"✅ Sync {direction} completed.")
    except Exception as e:
        send_telegram(f"❌ Sync error: `{e}`")

def set_interval_command(minutes: int):
    # Aquí se puede delegar a la lógica de main.py o sync_manager según la arquitectura
    send_telegram(f"⏱️ Interval set to {minutes} minutes (implementa la lógica real aquí)")

def enable_sync_command():
    send_telegram("✅ Auto sync enabled. (implementa la lógica real aquí)")

def disable_sync_command():
    send_telegram("🚫 Auto sync disabled. (implementa la lógica real aquí)")

def status_command():
    # Ejemplo de uso de get_icon y sync_manager
    status = "📊 Status: " + get_icon(42)  # Valor de ejemplo
    send_telegram(status)

def disk_status_command():
    # Ejemplo de uso de sync_manager
    send_telegram("💾 Disk status: (implementa la lógica real aquí)")

def change_source_command(new_path: str):
    ok = sync_manager_instance.set_rsync_from_path(new_path)
    if ok:
        send_telegram(f"🔄 Sync source changed to: `{new_path}`")
    else:
        send_telegram(f"❌ Failed to change sync source to: `{new_path}`")
