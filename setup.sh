#!/bin/bash

# Se empieza a tomar el tiempo de ejecución
START=$SECONDS

# Detectar si existe python3 o python
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    echo "Error: No se encontró Python (ni python3 ni python)."
    exit 1
fi

# Preparación de entorno usando el comando detectado
$PYTHON_CMD -m venv .env
source ./.env/bin/activate
pip install -r requirements.txt

# Descarga y procesamiento de datos
python scripts/download_data.py
python scripts/process_data.py
python scripts/spatial_analysis.py

# Se termina de tomar el tiempo de ejecución del setup y se muestra
TOTAL=$((SECONDS - START))
printf "\nTiempo total de ejecución: %d min %02d s\n" \
    $((TOTAL / 60)) \
    $((TOTAL % 60))

# Inicialización de aplicación para mostrar los dashboards
streamlit run ./app/main.py