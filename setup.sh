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

# Descarga y procesamiento de datos por glaciar.
# Los glaciares se leen de scripts/glacier_config.py (fuente única de verdad);
# si la consulta falla, se usa la lista por defecto.
GLACIARES=$($PYTHON_CMD -c "from scripts.glacier_config import GLACIER_CONFIGS; print(' '.join(GLACIER_CONFIGS))" 2>/dev/null)
if [ -z "$GLACIARES" ]; then
    GLACIARES="echaurren juncal"
    echo "Aviso: no se pudo leer la config de glaciares; usando: $GLACIARES"
fi
echo "Glaciares a procesar: $GLACIARES"

for G in $GLACIARES; do
    echo ""
    echo "===== PROCESANDO GLACIAR: $G ====="
    python scripts/download_data.py    --glacier "$G"
    python scripts/process_data.py     --glacier "$G"
    python scripts/spatial_analysis.py --glacier "$G"
    python scripts/validar_dga.py      --glacier "$G"
done

# Etapa 5b (opcional) — balance físico con snowmelt-rs. Requiere Rust/cargo;
# si no está disponible o falla, no interrumpe el resto del pipeline (el
# dashboard ya maneja la ausencia de sus archivos de salida).
if command -v cargo &> /dev/null && [ -d snowmelt-rs ]; then
    echo "Compilando snowmelt-cli..."
    if (cd snowmelt-rs && cargo build --release -p snowmelt-cli); then
        for G in $GLACIARES; do
            echo "--- snowmelt: $G ---"
            python scripts/run_snowmelt.py --glacier "$G" \
                || echo "Aviso: snowmelt falló para $G, se omite la Etapa 5b."
        done
    else
        echo "Aviso: la compilación de snowmelt-rs falló, se omite la Etapa 5b."
    fi
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