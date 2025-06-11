#!/bin/bash

# Asegura que el PATH tenga los comandos necesarios
export PATH="/usr/local/bin:/usr/bin:/bin"

# Cargar variables de entorno desde .env si está disponible
ENV_FILE="/app/.env"
if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r key value; do
        if [[ ! "$key" =~ ^# && -n "$key" ]]; then
            export "$key=$value"
        fi
    done < "$ENV_FILE"
fi

# Ejecutar el script Python solo para la dirección 'from'
if [ "$1" == "from" ]; then
    /usr/local/bin/python3 /app/main.py from
else
    echo "[ERROR] Dirección de sincronización inválida. Solo 'from' es soportado." >> /logs/cron.log 2>&1
fi