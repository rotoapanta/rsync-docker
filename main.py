# main.py
import sys
from managers.sync_manager import SyncManager

if __name__ == "__main__":
    if len(sys.argv) > 1:
        direction = sys.argv[1]
        # Crear una instancia de SyncManager
        sync_handler = SyncManager()
        # Llamar al método run_rsync de la instancia
        sync_handler.run_rsync(direction)
    else:
        print("Uso: python3 main.py [from]")
        sys.exit(1)