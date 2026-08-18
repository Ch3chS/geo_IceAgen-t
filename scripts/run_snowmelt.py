#!/usr/bin/env python3
"""
Etapa 5b — Balance físico de derretimiento con snowmelt-rs.

Segunda línea de evidencia independiente a la correlación NDSI-caudal de
`spatial_analysis.py`: en vez de correlacionar dos series observadas, simula
el derretimiento con un modelo físico de balance de masa (snowmelt-rs, motor
Rust en `snowmelt-rs/`) sobre el DEM del glaciar y lo rutea a un hidrograma,
para comparar contra el caudal DGA observado.

No reemplaza el pipeline NDSI (download_data.py, process_data.py,
spatial_analysis.py) — lo complementa. Requiere:
  - FABDEM ya descargado (data/raw/fabdem/fabdem_dem.tif).
  - snowmelt-cli compilado (snowmelt-rs/target/release/snowmelt[.exe]).
"""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.warp import reproject, transform as warp_transform

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# En máquinas con PostgreSQL/PostGIS instalado, PROJ_LIB/PROJ_DATA pueden
# quedar apuntando a la base de datos PROJ de esa instalación, incompatible
# con la que trae empaquetada rasterio (ver tests/conftest.py). Se limpian
# solo para este proceso.
for _var in ("PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_var, None)

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from scripts.spatial_analysis import (  # noqa: E402
    DGA_ESTACIONES, DGA_MENSUAL_PATH, _residuos_detrended,
    caudal_estival_djf, leer_caudal_dga,
)
from scipy import stats  # noqa: E402

# ============================================================================
# CONFIGURACIÓN
# ============================================================================
# Mismo AOI y grid (30 m, EPSG:32719) que process_data.py / spatial_analysis.py,
# para que el DEM de entrada quede alineado con la extensión clasificada del
# glaciar (ver limitación de escala en las notas del dashboard: este DEM cubre
# el glaciar, no toda la cuenca del Yeso).
AOI_BOUNDS = (393150, 6282300, 396200, 6285350)  # (minx, miny, maxx, maxy)
AOI_CRS = "EPSG:32719"
RESOLUCION_M = 30

FABDEM_PATH = BASE_DIR / "data" / "raw" / "fabdem" / "fabdem_dem.tif"

SNOWMELT_DIR = BASE_DIR / "data" / "processed" / "snowmelt"
DEM_ASC_PATH = SNOWMELT_DIR / "echaurren_dem.asc"
OUT_DIR = SNOWMELT_DIR / "out"

ERA5_DIR = BASE_DIR / "data" / "raw" / "era5"
FORZANTE_PATH = ERA5_DIR / "forzante_diario.csv"

OUTPUTS_DIR = BASE_DIR / "outputs"

SNOWMELT_BIN_CANDIDATES = [
    BASE_DIR / "snowmelt-rs" / "target" / "release" / "snowmelt.exe",
    BASE_DIR / "snowmelt-rs" / "target" / "release" / "snowmelt",
]

FECHA_INICIO_FORZANTE = "1985-01-01"
DIAS_REZAGO_ERA5 = 6  # margen de disponibilidad de ERA5 en Open-Meteo

LAPSE_RATE = -0.0075
ROUTE_K_DIAS = 5
ELA_BANDS = 20

MESES_ESTIVOS = [12, 1, 2]
MIN_DIAS_ESTIVOS = 60  # cobertura mínima de la ventana DJF (~90 días)

for d in [SNOWMELT_DIR, OUT_DIR, ERA5_DIR, OUTPUTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ============================================================================
# UTILIDADES PURAS (sin I/O — cubiertas por tests)
# ============================================================================

def _centroide_aoi_wgs84(bounds_utm=AOI_BOUNDS, crs_utm=AOI_CRS):
    """Centroide del AOI en WGS84 (lon, lat), para consultar ERA5 y fijar
    la latitud de radiación potencial del modelo."""
    minx, miny, maxx, maxy = bounds_utm
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    lons, lats = warp_transform(crs_utm, "EPSG:4326", [cx], [cy])
    return lons[0], lats[0]


def _año_hidrologico_djf(fecha: pd.Timestamp):
    """Año hidrológico DJF de una fecha: diciembre pertenece al año
    siguiente (mismo criterio que caudal_estival_djf en spatial_analysis.py).
    Devuelve None si el mes no es DJF."""
    if fecha.month == 12:
        return fecha.year + 1
    if fecha.month in (1, 2):
        return fecha.year
    return None


def _agregar_djf_serie(df_diario: pd.DataFrame,
                       columnas_suma=("snowfall_mm", "rain_mm", "melt_mm",
                                      "sublimation_mm", "runoff_mm", "routed_mm"),
                       columnas_media=("swe_mm", "snow_cover_fraction"),
                       min_dias=MIN_DIAS_ESTIVOS):
    """
    Agrega una serie diaria de snowmelt-rs (columna 'date' + variables) a
    totales/medias por año hidrológico DJF (dic(a-1)+ene(a)+feb(a)).

    Las variables de flujo (nieve, lluvia, derretimiento, sublimación,
    escorrentía, ruteo) se SUMAN sobre la ventana estival (profundidad total
    ablada/aportada en mm w.e.); las variables de estado (SWE, cobertura) se
    PROMEDIAN. Años con menos de `min_dias` de cobertura en la ventana DJF
    se descartan (misma lógica de completitud que MIN_MESES_ESTIVOS en
    caudal_estival_djf, pero en días).
    """
    df = df_diario.copy()
    df["fecha"] = pd.to_datetime(df["date"])
    df["año_hidro"] = df["fecha"].apply(_año_hidrologico_djf)
    df = df[df["año_hidro"].notna()]

    cols_suma = [c for c in columnas_suma if c in df.columns]
    cols_media = [c for c in columnas_media if c in df.columns]

    filas = []
    for año, grupo in df.groupby("año_hidro"):
        if len(grupo) < min_dias:
            continue
        fila = {"año": int(año), "n_dias": int(len(grupo))}
        for c in cols_suma:
            fila[f"{c.replace('_mm', '')}_djf_mm"] = float(grupo[c].sum())
        for c in cols_media:
            fila[f"{c}_djf_medio"] = float(grupo[c].mean())
        filas.append(fila)

    if not filas:
        columnas = (["año", "n_dias"]
                    + [f"{c.replace('_mm', '')}_djf_mm" for c in cols_suma]
                    + [f"{c}_djf_medio" for c in cols_media])
        return pd.DataFrame(columns=columnas)

    return pd.DataFrame(filas).sort_values("año").reset_index(drop=True)


def _parsear_resumen_stdout(texto: str):
    """Extrae ELA, balance de masa medio y SWE medio final del stdout del
    binario snowmelt (formato de impresión de snowmelt-rs/main.rs)."""
    resumen = {"ela_m": np.nan, "balance_medio_mm_we": np.nan,
               "swe_medio_final_mm": np.nan}

    m = re.search(r"ELA estimada\s*:\s*([\d.]+)\s*m", texto)
    if m:
        resumen["ela_m"] = float(m.group(1))

    m = re.search(r"balance de masa\s*:.*\(medio\s+([-\d.]+)\s*mm w\.e\.\)", texto)
    if m:
        resumen["balance_medio_mm_we"] = float(m.group(1))

    m = re.search(r"SWE medio final\s*:\s*([-\d.]+)\s*mm", texto)
    if m:
        resumen["swe_medio_final_mm"] = float(m.group(1))

    return resumen


# ============================================================================
# 1. DEM → ESRI ASCII GRID
# ============================================================================

def preparar_dem_asc():
    """Recorta/reproyecta FABDEM al mismo grid 30 m EPSG:32719 usado por
    process_data.py/spatial_analysis.py y lo escribe como .asc para
    snowmelt-cli."""
    if not FABDEM_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró FABDEM en {FABDEM_PATH}. "
            "Corre `python scripts/download_data.py` primero."
        )

    minx, miny, maxx, maxy = AOI_BOUNDS
    out_cols = int((maxx - minx) / RESOLUCION_M)
    out_rows = int((maxy - miny) / RESOLUCION_M)
    transform_salida = transform_from_bounds(minx, miny, maxx, maxy, out_cols, out_rows)

    dem = np.full((out_rows, out_cols), np.nan, dtype=np.float32)
    with rasterio.open(FABDEM_PATH) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dem,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform_salida,
            dst_crs=AOI_CRS,
            resampling=Resampling.bilinear,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
        )

    meta = {
        "driver": "AAIGrid",
        "dtype": "float32",
        "nodata": -9999.0,
        "width": out_cols,
        "height": out_rows,
        "count": 1,
        "crs": AOI_CRS,
        "transform": transform_salida,
    }
    with rasterio.open(DEM_ASC_PATH, "w", **meta) as dst:
        dst.write(np.where(np.isnan(dem), -9999.0, dem), 1)

    logging.info(f"  ✓ DEM preparado: {DEM_ASC_PATH.name} ({out_cols}x{out_rows} px)")
    return DEM_ASC_PATH


# ============================================================================
# 2. FORZANTE CLIMÁTICO (ERA5 vía Open-Meteo Archive API)
# ============================================================================

def obtener_forzante_era5():
    """Descarga temperatura/precipitación diaria ERA5 (Open-Meteo Archive
    API, sin API key) para el centroide del AOI, y la cachea en
    data/raw/era5/forzante_diario.csv. Devuelve (ruta_csv, z_ref_m,
    lat_centroide, lon_centroide)."""
    lon, lat = _centroide_aoi_wgs84()

    if FORZANTE_PATH.exists():
        logging.info(f"  Forzante ERA5 ya existe en {FORZANTE_PATH.name}, omitiendo descarga")
        df = pd.read_csv(FORZANTE_PATH)
        z_ref = float(df.attrs.get("z_ref", np.nan))
        if np.isnan(z_ref) and (ERA5_DIR / "forzante_meta.json").exists():
            meta = json.loads((ERA5_DIR / "forzante_meta.json").read_text())
            z_ref = meta["elevation_m"]
            lat = meta.get("lat", lat)
            lon = meta.get("lon", lon)
        return FORZANTE_PATH, z_ref, lat, lon

    fecha_fin = (date.today() - timedelta(days=DIAS_REZAGO_ERA5)).isoformat()
    logging.info(
        f"  Descargando ERA5 (Open-Meteo) {FECHA_INICIO_FORZANTE}..{fecha_fin} "
        f"en ({lat:.4f}, {lon:.4f})"
    )
    resp = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": FECHA_INICIO_FORZANTE,
            "end_date": fecha_fin,
            "daily": "temperature_2m_mean,precipitation_sum",
            "timezone": "America/Santiago",
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    elevation = float(data["elevation"])

    daily = data["daily"]
    df = pd.DataFrame({
        "date": daily["time"],
        "temp_c": daily["temperature_2m_mean"],
        "precip_mm": daily["precipitation_sum"],
    }).dropna()

    df.to_csv(FORZANTE_PATH, index=False)
    (ERA5_DIR / "forzante_meta.json").write_text(json.dumps({
        "elevation_m": elevation, "lat": lat, "lon": lon,
        "fuente": "ERA5 vía Open-Meteo Archive API",
    }))
    logging.info(
        f"  ✓ {FORZANTE_PATH.name} ({len(df)} días, elevación ERA5={elevation:.0f} m)"
    )
    return FORZANTE_PATH, elevation, lat, lon


# ============================================================================
# 3. CORRER snowmelt-cli
# ============================================================================

def localizar_binario():
    for candidato in SNOWMELT_BIN_CANDIDATES:
        if candidato.exists():
            return candidato
    raise FileNotFoundError(
        "No se encontró el binario de snowmelt-cli. Compílalo con:\n"
        "  cd snowmelt-rs && cargo build --release -p snowmelt-cli"
    )


def correr_snowmelt(dem_path, forzante_path, z_ref, lat):
    binario = localizar_binario()
    cmd = [
        str(binario),
        "--dem", str(dem_path),
        "--forcing", str(forzante_path),
        "--out-dir", str(OUT_DIR),
        "--z-ref", str(z_ref),
        "--energy-balance",
        "--latitude", str(lat),
        "--lapse-rate", str(LAPSE_RATE),
        "--mass-balance",
        "--ela-bands", str(ELA_BANDS),
        "--route-k", str(ROUTE_K_DIAS),
    ]
    logging.info("  Ejecutando snowmelt-cli...")
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"snowmelt-cli falló:\n{resultado.stderr}")
    logging.info(resultado.stdout.strip())
    return resultado.stdout


# ============================================================================
# 4. POST-PROCESO → outputs/
# ============================================================================

def correlacion_snowmelt_dga(djf):
    """Pearson crudo + detrended entre variables DJF simuladas y el caudal
    DJF de las estaciones DGA. Mismo esquema de columnas que
    correlacion_pearson() en spatial_analysis.py para reusar patrones en el
    dashboard."""
    variables = [c for c in djf.columns
                 if c.endswith("_djf_mm") and c != "snow_cover_fraction_djf_mm"]

    rows_caudal, rows_corr = [], []
    for codigo, nombre in DGA_ESTACIONES.items():
        df_caudal = leer_caudal_dga(DGA_MENSUAL_PATH, codigo)
        caud = [(año, caudal_estival_djf(df_caudal, int(año))) for año in djf["año"]]
        df_caud = pd.DataFrame(caud, columns=["año", "caudal_djf_m3s"])
        df_caud["codigo_estacion"] = codigo
        df_caud["nombre_estacion"] = nombre
        rows_caudal.append(df_caud)

        joined = djf.merge(df_caud, on="año", how="inner").dropna(subset=["caudal_djf_m3s"])
        if len(joined) < 3:
            logging.warning(f"  {codigo}: solo {len(joined)} años con caudal — sin correlación")
            continue

        años = joined["año"].values.astype(float)
        for var in variables:
            sim = joined[var].values.astype(float)
            r, p = stats.pearsonr(sim, joined["caudal_djf_m3s"].values)
            _, res_sim = _residuos_detrended(años, sim)
            _, res_caud = _residuos_detrended(años, joined["caudal_djf_m3s"].values)
            r_det, p_det = stats.pearsonr(res_sim, res_caud)
            rows_corr.append({
                "codigo_estacion": codigo, "nombre_estacion": nombre,
                "variable": var, "n": len(joined),
                "año_inicio": int(años.min()), "año_fin": int(años.max()),
                "r": round(r, 4), "p_valor": float(p),
                "r_detrended": round(r_det, 4), "p_detrended": float(p_det),
                "subperiodo": "completo",
            })
            logging.info(
                f"  {codigo} | {var}: n={len(joined)} r={r:.4f} (p={p:.4f})  "
                f"detrended r={r_det:.4f} (p={p_det:.4f})"
            )

    if rows_caudal:
        pd.concat(rows_caudal, ignore_index=True).to_csv(
            OUTPUTS_DIR / "caudal_dga_djf_snowmelt.csv", index=False, encoding="utf-8")
    if rows_corr:
        pd.DataFrame(rows_corr).to_csv(
            OUTPUTS_DIR / "correlacion_snowmelt_dga.csv", index=False, encoding="utf-8")
        logging.info("  ✓ correlacion_snowmelt_dga.csv")


def guardar_resumen(stdout_texto, z_ref, lat, lon):
    resumen = _parsear_resumen_stdout(stdout_texto)
    resumen.update({
        "z_ref_m": z_ref, "lat_centroide": lat, "lon_centroide": lon,
        "lapse_rate": LAPSE_RATE, "route_k_dias": ROUTE_K_DIAS,
        "ela_bands": ELA_BANDS,
    })
    pd.DataFrame([resumen]).to_csv(
        OUTPUTS_DIR / "snowmelt_resumen.csv", index=False, encoding="utf-8")
    logging.info("  ✓ snowmelt_resumen.csv")


# ============================================================================
# MAIN
# ============================================================================

def main():
    logging.info("===== ETAPA 5b: BALANCE FÍSICO (snowmelt-rs) =====")

    logging.info("--- Preparando DEM ---")
    dem_path = preparar_dem_asc()

    logging.info("--- Preparando forzante ERA5 ---")
    forzante_path, z_ref, lat, lon = obtener_forzante_era5()

    logging.info("--- Corriendo snowmelt-cli ---")
    stdout_texto = correr_snowmelt(dem_path, forzante_path, z_ref, lat)

    logging.info("--- Post-procesando series.csv ---")
    serie = pd.read_csv(OUT_DIR / "series.csv")
    djf = _agregar_djf_serie(serie)
    djf.to_csv(OUTPUTS_DIR / "snowmelt_djf.csv", index=False, encoding="utf-8")
    logging.info(f"  ✓ snowmelt_djf.csv ({len(djf)} años)")

    logging.info("--- Correlación con caudal DGA ---")
    correlacion_snowmelt_dga(djf)

    guardar_resumen(stdout_texto, z_ref, lat, lon)
    logging.info("===== ETAPA 5b FINALIZADA =====")


if __name__ == "__main__":
    main()
