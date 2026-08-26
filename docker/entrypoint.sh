#!/bin/bash
# Entrypoint del contenedor geo_IceAgen-t.
#
# Subcomandos:
#   dashboard            (default) levanta Streamlit en 0.0.0.0:8501
#   pipeline [glaciar]   corre el pipeline completo; sin argumento, todos
#   snowmelt [glaciar]   solo la Etapa 5b (balance físico con snowmelt-rs)
#   test                 corre pytest
#   shell                bash interactivo
#
# No usa setup.sh: ese script crea un venv y lo activa, redundante acá porque
# el contenedor ya es el entorno aislado. La secuencia del pipeline es la misma.
set -euo pipefail

# Lee los glaciares de la fuente única de verdad (scripts/glacier_config.py).
glaciares_configurados() {
    python -c "from scripts.glacier_config import GLACIER_CONFIGS; print(' '.join(GLACIER_CONFIGS))" \
        2>/dev/null || echo "echaurren juncal"
}

correr_pipeline() {
    local glaciares="${1:-$(glaciares_configurados)}"

    echo "=============================================================="
    echo " AVISO: el pipeline sobreescribe outputs/<glaciar>/*.csv"
    echo " Si outputs/ está montado desde el host, reemplaza esos CSV."
    echo " Para restaurar los del repo:  git checkout -- outputs/"
    echo "=============================================================="
    echo "Glaciares a procesar: $glaciares"

    for g in $glaciares; do
        echo ""
        echo "===== PROCESANDO GLACIAR: $g ====="
        python scripts/download_data.py    --glacier "$g"
        python scripts/process_data.py     --glacier "$g"
        python scripts/spatial_analysis.py --glacier "$g"
        python scripts/validar_dga.py      --glacier "$g"
    done

    correr_snowmelt "$glaciares"
}

correr_snowmelt() {
    local glaciares="${1:-$(glaciares_configurados)}"
    for g in $glaciares; do
        echo "--- snowmelt (Etapa 5b): $g ---"
        # No interrumpe el resto: el dashboard ya tolera la ausencia de sus salidas.
        python scripts/run_snowmelt.py --glacier "$g" \
            || echo "Aviso: snowmelt falló para $g, se omite la Etapa 5b."
    done
}

comando="${1:-dashboard}"
shift || true

case "$comando" in
    dashboard)
        # --server.address=0.0.0.0 es imprescindible: por defecto Streamlit
        # escucha en el localhost DEL CONTENEDOR y sería inalcanzable desde el host.
        exec streamlit run app/main.py \
            --server.address=0.0.0.0 \
            --server.port=8501 \
            --server.headless=true
        ;;
    pipeline)  correr_pipeline "${1:-}" ;;
    snowmelt)  correr_snowmelt "${1:-}" ;;
    test)      exec python -m pytest "$@" ;;
    shell)     exec /bin/bash "$@" ;;
    *)
        # Cualquier otra cosa se ejecuta tal cual (ej. `python scripts/...`).
        exec "$comando" "$@"
        ;;
esac
