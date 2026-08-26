# =============================================================================
# geo_IceAgen-t — imagen del pipeline + dashboard
#
# Build multi-etapa:
#   1. builder-rust   compila el motor snowmelt-cli (Etapa 5b)
#   2. runtime        Python + stack geoespacial + el binario ya compilado
#
# La etapa de Rust se descarta al final: solo viaja el binario (~pocos MB),
# no el toolchain ni los ~GB de target/.
# =============================================================================

# -----------------------------------------------------------------------------
# Etapa 1 — compilar snowmelt-cli
# -----------------------------------------------------------------------------
# El workspace usa edition 2024, que requiere Rust >= 1.85.
FROM rust:1-slim-bookworm AS builder-rust

WORKDIR /build

# Dependencias de compilación de los crates (surtgis-*, ndarray).
RUN apt-get update && apt-get install -y --no-install-recommends \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY snowmelt-rs/ ./

# `snowmelt` es el nombre del binario declarado en crates/snowmelt-cli/Cargo.toml.
RUN cargo build --release -p snowmelt-cli


# -----------------------------------------------------------------------------
# Etapa 2 — runtime Python
# -----------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

# PROJ_LIB/PROJ_DATA quedan deliberadamente SIN definir: rasterio y pyproj traen
# su propio PROJ empaquetado. (En Windows, PostgreSQL fija PROJ_LIB globalmente y
# rompe ambos; dentro del contenedor ese conflicto no existe.)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl: healthcheck del dashboard.
# libexpat1/libgomp1: runtime de las wheels geoespaciales (GDAL embebido, OpenMP de scipy).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libexpat1 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Dependencias primero, para que la capa quede cacheada entre rebuilds de código.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Código del proyecto (data/ y outputs/ NO van en la imagen: se montan).
COPY scripts/ ./scripts/
COPY app/ ./app/
COPY tests/ ./tests/
COPY pytest.ini setup.sh ./

# El binario de Rust va exactamente donde lo busca scripts/run_snowmelt.py
# (SNOWMELT_BIN_CANDIDATES → snowmelt-rs/target/release/snowmelt).
COPY --from=builder-rust /build/target/release/snowmelt \
     ./snowmelt-rs/target/release/snowmelt

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
             ./snowmelt-rs/target/release/snowmelt

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fs http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["entrypoint.sh"]
CMD ["dashboard"]
