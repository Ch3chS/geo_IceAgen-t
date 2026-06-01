#!/usr/bin/env python3
"""
Análisis espacial del glaciar Echaurren.

Etapa 3 — Clasificación con filtro DEM y vectorización a GeoPackage.
Etapa 4 — Series temporales independientes por sensor con delta acumulado
           y análisis por décadas.
"""

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import shapes
from rasterio.warp import reproject
import geopandas as gpd
from shapely.geometry import shape

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================================================
# CONFIGURACIÓN
# ============================================================================
BASE_DIR = Path(__file__).resolve().parents[1]

PROC_DIR  = BASE_DIR / "data" / "processed"
NDSI_DIRS = {
    "landsat":   PROC_DIR / "landsat",
    "sentinel2": PROC_DIR / "sentinel2",
}
CLAS_DIR   = PROC_DIR / "clasificacion"
VECTOR_DIR = PROC_DIR / "vectores"
OUT_DIR    = BASE_DIR / "outputs"

DEM_PATH = BASE_DIR / "data" / "raw" / "fabdem" / "fabdem_dem.tif"

UMBRAL_NDSI = 0.4
ELEV_MIN_M  = 3000
AREA_MIN_M2 = 5_000
CRS_SALIDA  = "EPSG:32719"   # UTM zona 19S — CRS común para todas las salidas

NODATA_IN  = -9999.0
NODATA_OUT = 255

# Año base por sensor — Landsat desde 1985, S2 desde su primer año disponible
AÑO_BASE = {
    "landsat":   1985,
    "sentinel2": None,   # se asigna dinámicamente al primer año disponible
}

DECADAS = [(1985, 1994), (1995, 2004), (2005, 2014), (2015, 2025)]

for d in [CLAS_DIR, VECTOR_DIR, OUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ============================================================================
# UTILIDADES
# ============================================================================
def _año_de_nombre(nombre):
    m = re.search(r'(\d{4})\d{4}', nombre)
    return int(m.group(1)) if m else None


def _cargar_dem_reproyectado(meta_destino):
    if not DEM_PATH.exists():
        logging.warning(f"FABDEM no encontrado en {DEM_PATH} — omitiendo filtro altitudinal")
        return None
    h, w = meta_destino['height'], meta_destino['width']
    dem_repr = np.zeros((h, w), dtype=np.float32)
    with rasterio.open(DEM_PATH) as dem_src:
        reproject(
            source=rasterio.band(dem_src, 1),
            destination=dem_repr,
            src_transform=dem_src.transform,
            src_crs=dem_src.crs,
            dst_transform=meta_destino['transform'],
            dst_crs=meta_destino['crs'],
            resampling=Resampling.bilinear,
        )
    return dem_repr


# ============================================================================
# ETAPA 3A — CLASIFICACIÓN CON FILTRO DEM
# ============================================================================
def clasificar_ndsi(ndsi, dem=None, nodata_in=NODATA_IN):
    clasif = np.full(ndsi.shape, NODATA_OUT, dtype=np.uint8)
    valido = (ndsi != nodata_in) & (~np.isnan(ndsi))
    mascara = valido & (ndsi >= UMBRAL_NDSI)
    if dem is not None:
        n_filt = int(np.sum(mascara & (dem < ELEV_MIN_M)))
        if n_filt:
            logging.info(f"    DEM filtró {n_filt} px bajo {ELEV_MIN_M} m s.n.m.")
        mascara &= (dem >= ELEV_MIN_M)
    clasif[valido & ~mascara] = 0
    clasif[mascara]           = 1
    return clasif


def clasificar_raster(ruta_ndsi, ruta_salida):
    with rasterio.open(ruta_ndsi) as src:
        ndsi = src.read(1)
        nod  = src.nodata if src.nodata is not None else NODATA_IN
        meta = src.meta.copy()
    dem    = _cargar_dem_reproyectado(meta)
    clasif = clasificar_ndsi(ndsi, dem=dem, nodata_in=nod)
    meta.update(dtype='uint8', nodata=NODATA_OUT, compress='lzw')
    with rasterio.open(ruta_salida, 'w', **meta) as dst:
        dst.write(clasif, 1)
    n_gl  = int(np.sum(clasif == 1))
    n_tot = int(np.sum(clasif != NODATA_OUT))
    logging.info(f"  ✓ {ruta_salida.name}: {n_gl}/{n_tot} px glaciar")
    return n_gl, n_tot


def clasificar_carpeta(sensor, dir_ndsi):
    archivos = sorted(dir_ndsi.glob("*.tif"))
    if not archivos:
        logging.warning(f"{sensor}: no se encontraron NDSI en {dir_ndsi}")
        return
    dir_out = CLAS_DIR / sensor
    dir_out.mkdir(parents=True, exist_ok=True)
    logging.info(f"=== CLASIFICANDO {sensor.upper()} "
                 f"(NDSI >= {UMBRAL_NDSI}, DEM >= {ELEV_MIN_M} m) ===")
    for f in archivos:
        salida = dir_out / f.name.replace("ndsi", "clasif")
        clasificar_raster(f, salida)


# ============================================================================
# ETAPA 3B — VECTORIZACIÓN → GEOPACKAGE
# ============================================================================
def vectorizar_raster(ruta_clasif, sensor, año):
    with rasterio.open(ruta_clasif) as src:
        clasif    = src.read(1)
        transform = src.transform
        crs       = src.crs

    mascara = (clasif == 1).astype(np.uint8)
    geoms   = [shape(g) for g, v in shapes(mascara, mask=mascara, transform=transform)
               if int(v) == 1]

    if not geoms:
        logging.info(f"  {sensor} {año}: sin polígonos glaciares")
        return gpd.GeoDataFrame(
            columns=['geometry', 'año', 'sensor', 'area_km2'], crs=crs)

    gdf = gpd.GeoDataFrame({'geometry': geoms}, crs=crs)

    # Forzar CRS común antes de calcular áreas
    if gdf.crs.to_epsg() != 32719:
        gdf = gdf.to_crs(CRS_SALIDA)

    gdf['area_m2'] = gdf.geometry.area
    antes = len(gdf)
    gdf   = gdf[gdf['area_m2'] >= AREA_MIN_M2].reset_index(drop=True)
    if antes - len(gdf):
        logging.info(f"    Descartados {antes - len(gdf)} parches < {AREA_MIN_M2} m²")

    gdf['año']      = año
    gdf['sensor']   = sensor
    gdf['area_km2'] = (gdf['area_m2'] / 1e6).round(6)
    gdf.drop(columns='area_m2', inplace=True)
    return gdf


def vectorizar_todos():
    logging.info("=== VECTORIZANDO MÁSCARAS GLACIARES ===")
    gdfs_por_sensor = {}

    for sensor in NDSI_DIRS:
        dir_clas = CLAS_DIR / sensor
        if not dir_clas.exists():
            continue
        gdfs = []
        for f in sorted(dir_clas.glob("*.tif")):
            año = _año_de_nombre(f.name)
            if año is None:
                continue
            gdf = vectorizar_raster(f, sensor, año)
            if len(gdf):
                gdfs.append(gdf)

        if gdfs:
            # Ya vienen en CRS_SALIDA desde vectorizar_raster — concat seguro
            gdf_sensor = pd.concat(gdfs, ignore_index=True)
            gdf_sensor = gpd.GeoDataFrame(gdf_sensor, crs=CRS_SALIDA)
            out_gpkg   = VECTOR_DIR / f"glaciar_echaurren_{sensor}.gpkg"
            gdf_sensor.to_file(out_gpkg, driver='GPKG')
            logging.info(f"  ✓ {out_gpkg.name} ({len(gdf_sensor)} polígonos)")
            gdfs_por_sensor[sensor] = gdf_sensor

    # GeoPackage combinado
    if gdfs_por_sensor:
        gdf_all = pd.concat(gdfs_por_sensor.values(), ignore_index=True)
        gdf_all = gpd.GeoDataFrame(gdf_all, crs=CRS_SALIDA)
        out_all = VECTOR_DIR / "glaciar_echaurren_todos.gpkg"
        gdf_all.to_file(out_all, driver='GPKG')
        logging.info(f"  ✓ {out_all.name} ({len(gdf_all)} polígonos totales)")
        return gdfs_por_sensor

    return {}


# ============================================================================
# ETAPA 4 — SERIES TEMPORALES INDEPENDIENTES POR SENSOR
# ============================================================================
def construir_serie_sensor(gdf_sensor, sensor):
    """
    Serie temporal para un sensor. Delta acumulado respecto a su propio año base
    (1985 para Landsat, primer año disponible para Sentinel-2).
    Devuelve DataFrame con una fila por año.
    """
    area_por_año = (
        gdf_sensor.groupby('año')['area_km2']
        .sum()
        .reset_index()
        .rename(columns={'area_km2': 'area_total_km2'})
        .sort_values('año')
        .reset_index(drop=True)
    )

    año_base_cfg = AÑO_BASE.get(sensor)
    if año_base_cfg and año_base_cfg in area_por_año['año'].values:
        año_base  = año_base_cfg
    else:
        año_base  = area_por_año['año'].min()
        if año_base_cfg:
            logging.warning(
                f"{sensor}: año base {año_base_cfg} no disponible — usando {año_base}")

    area_base = area_por_año.loc[
        area_por_año['año'] == año_base, 'area_total_km2'].values[0]
    logging.info(f"  {sensor} — año base: {año_base} → {area_base:.4f} km²")

    area_por_año['sensor']      = sensor
    area_por_año['año_base']    = año_base
    area_por_año['delta_km2']   = (area_por_año['area_total_km2'] - area_base).round(5)
    area_por_año['pct_cambio']  = (
        area_por_año['delta_km2'] / area_base * 100).round(2)

    def asignar_decada(año):
        for ini, fin in DECADAS:
            if ini <= año <= fin:
                return f"{ini}-{fin}"
        return "fuera_rango"

    area_por_año['decada'] = area_por_año['año'].apply(asignar_decada)
    return area_por_año


def analisis_decadas_sensor(serie, sensor):
    """Mediana y tasa de cambio por década para un sensor."""
    resumen = []
    for ini, fin in DECADAS:
        sub = serie[(serie['año'] >= ini) & (serie['año'] <= fin)]
        if sub.empty:
            continue
        mediana = sub['area_total_km2'].median()
        tasa    = (np.polyfit(sub['año'], sub['area_total_km2'], 1)[0]
                   if len(sub) >= 2 else float('nan'))
        resumen.append({
            'sensor':       sensor,
            'decada':       f"{ini}-{fin}",
            'n_años':       len(sub),
            'mediana_km2':  round(mediana, 4),
            'tasa_km2_año': round(tasa, 5),
        })
        logging.info(
            f"  {sensor} {ini}-{fin}: mediana={mediana:.4f} km²  "
            f"tasa={tasa:+.5f} km²/año  (n={len(sub)})")
    return pd.DataFrame(resumen)


def guardar_resultados(series_dict, decadas_dict):
    """
    Guarda un CSV por sensor y uno combinado para la serie anual.
    Idem para décadas.
    """
    series_all  = []
    decadas_all = []

    for sensor, serie in series_dict.items():
        csv_s = OUT_DIR / f"serie_temporal_{sensor}.csv"
        serie.to_csv(csv_s, index=False, encoding='utf-8')
        logging.info(f"  ✓ {csv_s.name}")
        series_all.append(serie)

    for sensor, dec in decadas_dict.items():
        csv_d = OUT_DIR / f"analisis_decadas_{sensor}.csv"
        dec.to_csv(csv_d, index=False, encoding='utf-8')
        logging.info(f"  ✓ {csv_d.name}")
        decadas_all.append(dec)

    # Combinados (para el dashboard que quiera ver ambos sensores a la vez)
    pd.concat(series_all,  ignore_index=True).to_csv(
        OUT_DIR / "serie_temporal_todos.csv",  index=False, encoding='utf-8')
    pd.concat(decadas_all, ignore_index=True).to_csv(
        OUT_DIR / "analisis_decadas_todos.csv", index=False, encoding='utf-8')
    logging.info("  ✓ serie_temporal_todos.csv")
    logging.info("  ✓ analisis_decadas_todos.csv")


# ============================================================================
# MAIN
# ============================================================================
def main():
    # Etapa 3A: clasificación con filtro DEM
    logging.info("===== ETAPA 3A: CLASIFICACIÓN =====")
    for sensor, dir_ndsi in NDSI_DIRS.items():
        clasificar_carpeta(sensor, dir_ndsi)

    # Etapa 3B: vectorización → GeoPackage
    logging.info("===== ETAPA 3B: VECTORIZACIÓN =====")
    gdfs_por_sensor = vectorizar_todos()

    # Etapa 4: series independientes por sensor + décadas
    logging.info("===== ETAPA 4: SERIES TEMPORALES =====")
    series_dict  = {}
    decadas_dict = {}

    for sensor, gdf in gdfs_por_sensor.items():
        logging.info(f"--- {sensor} ---")
        serie = construir_serie_sensor(gdf, sensor)
        dec   = analisis_decadas_sensor(serie, sensor)
        series_dict[sensor]  = serie
        decadas_dict[sensor] = dec

    guardar_resultados(series_dict, decadas_dict)
    logging.info("===== PROCESAMIENTO FINALIZADO =====")


if __name__ == "__main__":
    main()