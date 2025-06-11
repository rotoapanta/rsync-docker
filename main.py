# main.py
import sys
from managers.sync_manager import run_rsync

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("from", "to"):
        print("Uso: python3 main.py [from|to]")
        sys.exit(1)

    run_rsync(sys.argv[1])