#!/usr/bin/env python3
"""
Análisis espacial del glaciar Echaurren.

PUNTO 2 del desafío: clasificación de cobertura glaciar vs. roca/suelo.
A partir de los rasters NDSI continuos (generados por process_data.py), se
umbraliza para obtener una máscara binaria:
    glaciar (1)  si NDSI >= UMBRAL_NDSI
    no-glaciar (0) en caso contrario
Los píxeles sin dato (NoData) se conservan como NoData.
"""

import csv
import logging
import re
from pathlib import Path
import numpy as np
import rasterio

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================================================
# CONFIGURACIÓN
# ============================================================================
BASE_DIR = Path(__file__).resolve().parents[1]

PROC_DIR = BASE_DIR / "data" / "processed"
NDSI_DIRS = {
    "landsat":   PROC_DIR / "landsat",
    "sentinel2": PROC_DIR / "sentinel2",
}
# Salida de la clasificación binaria
CLAS_DIR = PROC_DIR / "clasificacion"

# Umbral NDSI para considerar un píxel como glaciar/nieve-hielo.
# 0.4 es el valor estándar en cartografía de nieve (NDSI > 0.4 = nieve/hielo).
UMBRAL_NDSI = 0.4

NODATA_IN = -9999.0   # NoData de los rasters NDSI de entrada
NODATA_OUT = 255      # NoData de la clasificación binaria (uint8)

# ============================================================================
# CLASIFICACIÓN (PUNTO 2)
# ============================================================================
def clasificar_ndsi(ndsi, nodata_in=NODATA_IN):
    """
    Umbraliza un array NDSI a una máscara binaria uint8:
        1   -> glaciar (NDSI >= UMBRAL_NDSI)
        0   -> no-glaciar (roca/suelo)
        255 -> sin dato (NoData)
    """
    clasif = np.full(ndsi.shape, NODATA_OUT, dtype=np.uint8)
    valido = (ndsi != nodata_in) & (~np.isnan(ndsi))
    clasif[valido & (ndsi >= UMBRAL_NDSI)] = 1
    clasif[valido & (ndsi <  UMBRAL_NDSI)] = 0
    return clasif


def clasificar_raster(ruta_ndsi, ruta_salida):
    """Lee un raster NDSI, lo clasifica y guarda la máscara binaria conservando georreferencia."""
    with rasterio.open(ruta_ndsi) as src:
        ndsi = src.read(1)
        nod = src.nodata if src.nodata is not None else NODATA_IN
        meta = src.meta.copy()

    clasif = clasificar_ndsi(ndsi, nodata_in=nod)

    meta.update(dtype='uint8', nodata=NODATA_OUT, compress='lzw')
    with rasterio.open(ruta_salida, 'w', **meta) as dst:
        dst.write(clasif, 1)

    n_glaciar = int(np.sum(clasif == 1))
    n_total   = int(np.sum(clasif != NODATA_OUT))
    logging.info(f"  ✓ {ruta_salida.name}: {n_glaciar}/{n_total} px glaciar")
    return n_glaciar, n_total


def clasificar_carpeta(sensor, dir_ndsi):
    """Clasifica todos los NDSI de un sensor."""
    archivos = sorted(dir_ndsi.glob("*.tif"))
    if not archivos:
        logging.warning(f"{sensor}: no se encontraron NDSI en {dir_ndsi}")
        return
    dir_out = CLAS_DIR / sensor
    dir_out.mkdir(parents=True, exist_ok=True)
    logging.info(f"=== CLASIFICANDO {sensor.upper()} (umbral NDSI >= {UMBRAL_NDSI}) ===")
    for f in archivos:
        salida = dir_out / f.name.replace("ndsi", "clasif")
        clasificar_raster(f, salida)


# ============================================================================
# ÁREA Y TASA DE RETROCESO (PUNTO 3)
# ============================================================================
# Salida de la tabla de áreas
AREA_CSV = BASE_DIR / "outputs" / "area_glaciar.csv"

# Años que marcan cada década (para los "mapas de extensión por década" de la pauta)
DECADAS = [1985, 1995, 2005, 2015, 2025]


def _año_de_nombre(nombre):
    m = re.search(r'(\d{4})\d{2}\d{2}', nombre)
    return int(m.group(1)) if m else None


def calcular_area_glaciar(ruta_clasif):
    """
    Calcula el área glaciar (km²) de un raster de clasificación binaria:
    nº de píxeles clase 1 × área de cada píxel (derivada de la georreferencia).
    """
    with rasterio.open(ruta_clasif) as src:
        clas = src.read(1)
        # tamaño de píxel en metros, desde la transform afín
        px_area_m2 = abs(src.transform.a) * abs(src.transform.e)
    n_glaciar = int(np.sum(clas == 1))
    area_km2 = n_glaciar * px_area_m2 / 1e6
    return n_glaciar, area_km2


def calcular_areas_sensor(sensor):
    """Devuelve lista [(año, n_px, area_km2), ...] ordenada por año para un sensor."""
    dir_clas = CLAS_DIR / sensor
    filas = []
    for f in sorted(dir_clas.glob("*.tif")):
        año = _año_de_nombre(f.name)
        if año is None:
            continue
        n, area = calcular_area_glaciar(f)
        filas.append((año, n, area))
    filas.sort(key=lambda x: x[0])
    return filas


def tasa_retroceso(filas):
    """
    Ajusta una recta área vs. año y devuelve (pendiente_km2_por_año, area_inicial,
    area_final, pct_cambio_total). Pendiente negativa = retroceso.
    """
    if len(filas) < 2:
        return None
    años = np.array([f[0] for f in filas], dtype=float)
    areas = np.array([f[2] for f in filas], dtype=float)
    pendiente, _ = np.polyfit(años, areas, 1)
    area_ini, area_fin = areas[0], areas[-1]
    pct = 100 * (area_fin - area_ini) / area_ini if area_ini > 0 else float('nan')
    return pendiente, area_ini, area_fin, pct


def analizar_retroceso():
    """Calcula áreas por año/sensor, las guarda en CSV y reporta la tasa de retroceso."""
    logging.info("=== PUNTO 3: ÁREA Y TASA DE RETROCESO ===")
    AREA_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(AREA_CSV, 'w', newline='', encoding='utf-8') as fcsv:
        w = csv.writer(fcsv)
        w.writerow(['sensor', 'anio', 'px_glaciar', 'area_km2'])
        for sensor in NDSI_DIRS:
            filas = calcular_areas_sensor(sensor)
            for año, n, area in filas:
                w.writerow([sensor, año, n, round(area, 5)])
            tr = tasa_retroceso(filas)
            if tr:
                pend, a_ini, a_fin, pct = tr
                logging.info(f"  {sensor}: {filas[0][0]}={a_ini:.3f} km² -> "
                             f"{filas[-1][0]}={a_fin:.3f} km² | "
                             f"tasa={pend:.5f} km²/año | cambio total={pct:+.1f}%")
    logging.info(f"  ✓ Tabla de áreas guardada en {AREA_CSV}")


def main():
    logging.info("===== PUNTO 2: CLASIFICACIÓN GLACIAR vs ROCA/SUELO =====")
    for sensor, dir_ndsi in NDSI_DIRS.items():
        clasificar_carpeta(sensor, dir_ndsi)
    logging.info("===== PUNTO 2 FINALIZADO =====")
    analizar_retroceso()
    logging.info("===== PUNTO 3 FINALIZADO =====")


if __name__ == "__main__":
    main()
