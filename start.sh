#!/bin/bash

echo "[INFO] Iniciando cron..." | tee -a /logs/startup.log

# Crear carpeta de logs si no existe
mkdir -p /logs

# Exportar las variables de entorno del .env al entorno de cron
# Cargar el .env en el shell actual
# ¡Asegúrate de que este .env esté en /app/.env dentro del contenedor!
if [ -f "/app/.env" ]; then
    # Lee cada línea del .env, filtra comentarios y líneas vacías, y lo exporta
    # Esto manejará si las variables tienen espacios, etc.
    while IFS='=' read -r key value; do
        if [[ ! "$key" =~ ^# && -n "$key" ]]; then
            export "$key=$value"
        fi
    done < "/app/.env"
    echo "[INFO] Variables de entorno cargadas desde .env para cron." | tee -a /logs/startup.log
else
    echo "[WARNING] No se encontró el archivo .env en /app/.env. Cron podría no tener todas las variables." | tee -a /logs/startup.log
fi


# Asegurar que el cronjob esté cargado
CRON_FILE="/app/crontab.txt"
if [ -f "$CRON_FILE" ]; then
    chmod 0644 "$CRON_FILE"
    crontab "$CRON_FILE"
    echo "[INFO] crontab cargado correctamente." | tee -a /logs/startup.log
else
    echo "[ERROR] No se encontró el archivo de cron en $CRON_FILE. No se puede cargar crontab." | tee -a /logs/startup.log
    exit 1 # Si no se encuentra el crontab, el contenedor debería salir para que el usuario se dé cuenta.
fi

# Asegurar que exista /var/run si no está (necesario para algunos servicios como cron)
mkdir -p /var/run

# Iniciar cron en segundo plano y en foreground (-f) para que Docker lo mantenga vivo
# Es importante que 'cron -f' sea el proceso principal del contenedor (o que 'tail -F' lo sea)
cron -f &
CRON_PID=$! # Captura el PID de cron
echo "[INFO] Cron lanzado con PID: $CRON_PID" | tee -a /logs/startup.log

# Mantener contenedor activo por el proceso principal (cron o tail)
# Si cron se ejecutó en background, necesitamos otro proceso en foreground.
# tail -F es perfecto para esto, y también muestra los logs.
echo "[INFO] Manteniendo el contenedor activo. Revisar logs." | tee -a /logs/startup.log
tail -F /logs/from_pi.log /logs/to_pi.log /logs/startup.log /logs/cron.log