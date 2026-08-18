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

# Etapa 5b (opcional) — balance físico con snowmelt-rs. Requiere Rust/cargo;
# si no está disponible o falla, no interrumpe el resto del pipeline (el
# dashboard ya maneja la ausencia de sus archivos de salida).
if command -v cargo &> /dev/null && [ -d snowmelt-rs ]; then
    echo "Compilando snowmelt-cli..."
    (cd snowmelt-rs && cargo build --release -p snowmelt-cli) \
        && python scripts/run_snowmelt.py \
        || echo "Aviso: snowmelt-rs falló, se omite la Etapa 5b."
else
    echo "Aviso: cargo no disponible, se omite la Etapa 5b (snowmelt-rs)."
fi

# Se termina de tomar el tiempo de ejecución del setup y se muestra
TOTAL=$((SECONDS - START))
printf "\nTiempo total de ejecución: %d min %02d s\n" \
    $((TOTAL / 60)) \
    $((TOTAL % 60))

# Inicialización de aplicación para mostrar los dashboards
streamlit run ./app/main.py