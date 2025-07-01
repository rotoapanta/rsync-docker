FROM python:3.11-slim

# Instalar utilidades necesarias
RUN apt-get update && \
    apt-get install -y rsync openssh-client cron tree && \
    apt-get clean

# Crear directorio de trabajo
WORKDIR /app

# Copiar scripts y configuraciones
COPY main.py /app/
COPY managers/ /app/managers/
COPY utils/ /app/utils/
COPY start.sh /app/start.sh
COPY crontab.txt /app/crontab.txt
COPY run_sync.sh /app/run_sync.sh
COPY .env /app/.env 

# Configurar permisos y cron
# crontab se carga aquí. Si hay un error, lo verás en la fase de build.
RUN chmod +x /app/start.sh && \
    chmod +x /app/run_sync.sh && \
    chmod 0644 /app/crontab.txt && \
    crontab /app/crontab.txt

# Copiar el archivo de requisitos
COPY requirements.txt /app/

# Instalar todas las dependencias Python de requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Eliminar la línea anterior de 'pip install requests' ya que ahora está en requirements.txt
# RUN pip install requests 
# --- FIN DE MODIFICACIONES ---

# Comando de inicio
CMD ["/app/start.sh"]