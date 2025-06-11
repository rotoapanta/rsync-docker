#!/bin/bash

echo "🧹 Deteniendo y eliminando contenedor anterior (si existe)..."
docker-compose down

echo "🚀 Construyendo e iniciando el contenedor rsync_docker..."
docker-compose up --build -d

echo "✅ Contenedor iniciado. Puedes ejecutar:"
echo "   docker exec -it rsync_docker python3 /app/main.py from"
