#!/usr/bin/env python3
"""
Etapa 6 — Validación espacial contra el Inventario DGA (IPG 2022).

El Inventario Público de Glaciares (IPG 2022) es un único snapshot
fotointerpretado (INVE_FECHA=2022), no una serie temporal. Esta etapa mide
qué tan lejos está el área glaciar del pipeline (NDSI+DEM) de esa referencia,
año por año y por sensor, para cuantificar el sesgo sistemático de cada uno
(complementa, no reemplaza, la correlación con caudal DGA de spatial_analysis.py).
"""

import logging
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Ver tests/conftest.py: en máquinas con PostgreSQL/PostGIS, PROJ_LIB/PROJ_DATA
# pueden apuntar a una base de datos PROJ incompatible con la de rasterio/GDAL.
for _var in ("PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_var, None)

BASE_DIR = Path(__file__).resolve().parents[1]

DGA_VECTOR_PATH = BASE_DIR / "data" / "IPG_2022_v2" / "INV_PG_2022_v2.shp"
OUT_DIR = BASE_DIR / "outputs"

CRS_SALIDA = "EPSG:32719"
AÑO_REFERENCIA_DGA = 2022

SENSORES = ["landsat", "sentinel2"]


# ============================================================================
# CARGA DE LA REFERENCIA DGA (I/O)
# ============================================================================

def cargar_referencia_dga():
    """
    Filtra el Inventario DGA por 'Echaurren Norte' (matchea 3 sub-features:
    ECHAURREN NORTE, NORTE A, NORTE B — todas clasificadas GLACIARETE) y
    reproyecta a EPSG:32719.

    El pipeline NDSI+DEM no distingue fragmentos del mismo cuerpo de hielo,
    así que el área de referencia es la SUMA de las 3 sub-features, no solo
    el cuerpo principal.
    """
    gdf = gpd.read_file(DGA_VECTOR_PATH)
    sub = gdf[gdf['NOMBRE'].str.contains('Echaurren Norte', case=False, na=False)].copy()
    if sub.empty:
        raise ValueError("No se encontraron features 'Echaurren Norte' en el Inventario DGA")
    sub = sub.to_crs(CRS_SALIDA)
    area_total_km2 = float(sub.geometry.area.sum() / 1e6)
    logging.info(
        f"  Referencia DGA: {len(sub)} sub-features, "
        f"área total={area_total_km2:.6f} km² (año {AÑO_REFERENCIA_DGA})"
    )
    return sub, area_total_km2


# ============================================================================
# FUNCIONES PURAS (sin I/O — cubiertas por tests)
# ============================================================================

def calcular_discrepancias(serie_df: pd.DataFrame, area_dga_km2: float, sensor: str):
    """
    Compara el área del pipeline (columna 'año', 'area_total_km2') contra la
    referencia DGA fija, año por año.

    diff_km2 > 0 significa que el pipeline SOBREESTIMA respecto al DGA.
    """
    tabla = serie_df[['año', 'area_total_km2']].copy()
    tabla['sensor'] = sensor
    tabla = tabla.rename(columns={'area_total_km2': 'area_pipeline_km2'})
    tabla['area_dga_km2'] = area_dga_km2
    tabla['diff_km2'] = tabla['area_pipeline_km2'] - area_dga_km2
    tabla['abs_diff_km2'] = tabla['diff_km2'].abs()
    tabla['diff_pct'] = (tabla['diff_km2'] / area_dga_km2 * 100).round(2)
    return tabla[['año', 'sensor', 'area_pipeline_km2', 'area_dga_km2',
                  'diff_km2', 'abs_diff_km2', 'diff_pct']]


def resumen_por_sensor(tabla_discrepancias: pd.DataFrame,
                       año_referencia: int = AÑO_REFERENCIA_DGA):
    """
    Agrega la tabla de discrepancias por sensor: MAE, sesgo medio (con signo
    — sobreestimación/subestimación sistemática), RMSE, n, y localiza el año
    disponible más cercano a `año_referencia` (el DGA es de 2022, pero un
    sensor puede no tener ese año exacto en su serie — p. ej. Landsat 2022
    sin polígonos ≥ el área mínima).
    """
    filas = []
    for sensor, grupo in tabla_discrepancias.groupby('sensor'):
        n = len(grupo)
        mae = float(grupo['abs_diff_km2'].mean())
        sesgo = float(grupo['diff_km2'].mean())
        rmse = float((grupo['diff_km2'] ** 2).mean() ** 0.5)

        idx_cercano = (grupo['año'] - año_referencia).abs().idxmin()
        fila_cercana = grupo.loc[idx_cercano]

        filas.append({
            'sensor': sensor,
            'n_años': n,
            'mae_km2': round(mae, 5),
            'sesgo_medio_km2': round(sesgo, 5),
            'rmse_km2': round(rmse, 5),
            'año_dga_referencia': año_referencia,
            'area_dga_referencia_km2': round(float(grupo['area_dga_km2'].iloc[0]), 6),
            'año_mas_cercano': int(fila_cercana['año']),
            'diff_año_mas_cercano_km2': round(float(fila_cercana['diff_km2']), 5),
        })
    return pd.DataFrame(filas)


# ============================================================================
# MAIN
# ============================================================================

def main():
    logging.info("===== ETAPA 6: VALIDACIÓN ESPACIAL CONTRA INVENTARIO DGA =====")

    _, area_dga_km2 = cargar_referencia_dga()

    tablas = []
    for sensor in SENSORES:
        ruta_serie = OUT_DIR / f"serie_temporal_{sensor}.csv"
        if not ruta_serie.exists():
            logging.warning(f"  {sensor}: no se encontró {ruta_serie.name}, se omite")
            continue
        serie = pd.read_csv(ruta_serie)
        tablas.append(calcular_discrepancias(serie, area_dga_km2, sensor))

    if not tablas:
        logging.error("Sin series disponibles — corre spatial_analysis.py primero")
        return

    tabla_area = pd.concat(tablas, ignore_index=True)
    tabla_area.to_csv(OUT_DIR / "validacion_dga_area.csv", index=False, encoding="utf-8")
    logging.info(f"  ✓ validacion_dga_area.csv ({len(tabla_area)} filas)")

    resumen = resumen_por_sensor(tabla_area)
    resumen.to_csv(OUT_DIR / "validacion_dga_resumen.csv", index=False, encoding="utf-8")
    logging.info("  ✓ validacion_dga_resumen.csv")
    for _, fila in resumen.iterrows():
        signo = "sobreestima" if fila['sesgo_medio_km2'] > 0 else "subestima"
        logging.info(
            f"  {fila['sensor']}: MAE={fila['mae_km2']:.4f} km² · "
            f"sesgo={fila['sesgo_medio_km2']:+.4f} km² ({signo}) · "
            f"RMSE={fila['rmse_km2']:.4f} km² · n={fila['n_años']} · "
            f"año más cercano a {fila['año_dga_referencia']}: {fila['año_mas_cercano']}"
        )

    logging.info("===== ETAPA 6 FINALIZADA =====")


if __name__ == "__main__":
    main()
