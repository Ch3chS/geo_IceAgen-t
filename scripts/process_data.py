#!/usr/bin/env python3
"""
Procesamiento multitemporal de imágenes satelitales para el glaciar Echaurren.
Calcula NDSI (nieve/hielo) para Sentinel-2 y Landsat.
Soporta CRS diferentes transformando el AOI automáticamente.
Selecciona la mejor escena por año cuando hay múltiples descargadas.
"""

import logging
import re
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================================================
# CONFIGURACIÓN DE RUTAS Y ÁREA DE ESTUDIO
# ============================================================================
BASE_DIR = Path(__file__).resolve().parents[1]

# Directorios raw
RAW_SENTINEL_DIR = BASE_DIR / "data" / "raw" / "sentinel2"
RAW_LANDSAT_DIR  = BASE_DIR / "data" / "raw" / "landsat"

# Directorios procesados
PROC_SENTINEL_DIR = BASE_DIR / "data" / "processed" / "sentinel2"
PROC_LANDSAT_DIR  = BASE_DIR / "data" / "processed" / "landsat"

for d in [PROC_SENTINEL_DIR, PROC_LANDSAT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Área del glaciar Echaurren en UTM 19S (EPSG:32719)
AOI_BOUNDS = (393150, 6282300, 396200, 6285350)
# AOI_BOUNDS = (392500, 6280500, 397500, 6285500)  # (minx, miny, maxx, maxy)
AOI_CRS = 'EPSG:32719'

# ============================================================================
# FUNCIONES COMUNES
# ============================================================================
def recortar_y_remuestrear_banda(ruta_tif, bounds_utm, target_shape=None):
    """
    Lee una banda, recorta al AOI (dado en EPSG:32719) transformándolo al CRS del raster.
    Remuestrea opcionalmente a target_shape.
    """
    with rasterio.open(ruta_tif) as src:
        # Transformar bounds_utm (EPSG:32719) al CRS del raster
        if src.crs != AOI_CRS:
            bounds_raster = transform_bounds(
                AOI_CRS, src.crs,
                *bounds_utm,
                densify_pts=21
            )
        else:
            bounds_raster = bounds_utm

        # Crear ventana con los bounds transformados
        window = from_bounds(*bounds_raster, transform=src.transform)

        out_shape = target_shape if target_shape else None
        data = src.read(
            1,
            window=window,
            boundless=True,
            fill_value=0,
            out_shape=out_shape,
            resampling=Resampling.bilinear
        )
        transform_ventana = src.window_transform(window)
        if target_shape:
            scale_x = window.width / target_shape[1]
            scale_y = window.height / target_shape[0]
            transform_ventana = transform_ventana * transform_ventana.scale(scale_x, scale_y)
        return data.astype(np.float32), transform_ventana, src.crs

def calcular_ndsi(banda_verde, banda_swir, nodata=-9999.0):
    """Calcula NDSI = (verde - swir) / (verde + swir)"""
    denominador = banda_verde + banda_swir
    with np.errstate(divide='ignore', invalid='ignore'):
        ndsi = np.where(denominador > 0, (banda_verde - banda_swir) / denominador, nodata)
    return ndsi.astype(np.float32)

def guardar_ndsi(ndsi, transform, crs, output_path):
    """Guarda el array NDSI como GeoTIFF."""
    meta = {
        'driver': 'GTiff',
        'dtype': 'float32',
        'nodata': -9999.0,
        'width': ndsi.shape[1],
        'height': ndsi.shape[0],
        'count': 1,
        'crs': crs,
        'transform': transform,
        'compress': 'lzw'
    }
    with rasterio.open(output_path, 'w', **meta) as dst:
        dst.write(ndsi, 1)
    logging.info(f"  ✓ Guardado: {output_path.name}")

# ============================================================================
# FUNCIONES DE EVALUACIÓN DE CALIDAD (para elegir mejor escena)
# ============================================================================
def evaluar_calidad_escena(ruta_verde, bounds_utm, escala_muestra=0.2):
    """
    Evalúa la calidad de una escena contando cuántos píxeles válidos (>0)
    hay en el área de interés tras recortar. Usa una versión reducida
    (escala_muestra) para ser rápido.
    """
    try:
        with rasterio.open(ruta_verde) as src:
            # Transformar bounds al CRS de la imagen
            if src.crs != AOI_CRS:
                bounds_raster = transform_bounds(AOI_CRS, src.crs, *bounds_utm, densify_pts=21)
            else:
                bounds_raster = bounds_utm
            window = from_bounds(*bounds_raster, transform=src.transform)

            # Leer una versión reducida para rapidez
            h_new = max(1, int(window.height * escala_muestra))
            w_new = max(1, int(window.width * escala_muestra))
            data = src.read(
                1,
                window=window,
                out_shape=(h_new, w_new),
                resampling=Resampling.bilinear
            )
            nodata = src.nodata if src.nodata is not None else -9999
            # Contamos píxeles con valor > 0 (asumimos que nieve/roca dan valores positivos)
            data = np.where(data == nodata, 0, data)
            return int(np.sum(data > 0))
    except Exception as e:
        logging.debug(f"Error evaluando calidad de {ruta_verde.name}: {e}")
        return 0

# ============================================================================
# PROCESAMIENTO SENTINEL-2 (con selección de mejor escena por año)
# ============================================================================
PATTERN_S2 = re.compile(
    r"^(?P<scene_id>S2[AB]_MSIL2A_(?P<date>\d{8})T\d{6}_R\d{3}_T[A-Z0-9]+_\d{8}T\d{6})_(?P<band>B\d{2}[A]?)\.(tif|TIF)$"
)

def agrupar_escenas_por_año_sentinel():
    """
    Agrupa todas las bandas de Sentinel-2 por año y por scene_id.
    Devuelve dict: {año: {scene_id: {'fecha': str, 'archivos': {banda: Path}, 'calidad': int}}}
    """
    archivos = list(RAW_SENTINEL_DIR.glob("*.tif")) + list(RAW_SENTINEL_DIR.glob("*.TIF"))
    if not archivos:
        logging.warning("No se encontraron archivos Sentinel-2.")
        return {}

    escenas_por_año = {}
    for archivo in archivos:
        match = PATTERN_S2.match(archivo.name)
        if not match:
            logging.debug(f"Archivo Sentinel no coincide: {archivo.name}")
            continue
        datos = match.groupdict()
        scene_id = datos['scene_id']
        fecha = datos['date']
        año = int(fecha[:4])
        banda = datos['band']

        if año not in escenas_por_año:
            escenas_por_año[año] = {}
        if scene_id not in escenas_por_año[año]:
            escenas_por_año[año][scene_id] = {'fecha': fecha, 'archivos': {}, 'calidad': None}
        escenas_por_año[año][scene_id]['archivos'][banda] = archivo

    # Evaluar calidad para cada escena que tenga banda B03 (verde)
    for año, escenas in escenas_por_año.items():
        for scene_id, info in escenas.items():
            if 'B03' in info['archivos']:
                calidad = evaluar_calidad_escena(info['archivos']['B03'], AOI_BOUNDS)
                info['calidad'] = calidad
            else:
                logging.debug(f"Escena {scene_id} sin B03, no se puede evaluar calidad")
    return escenas_por_año

def procesar_sentinel2():
    logging.info("=== PROCESANDO SENTINEL-2 (seleccionando mejor escena por año) ===")
    escenas_por_año = agrupar_escenas_por_año_sentinel()
    if not escenas_por_año:
        return

    for año, escenas in escenas_por_año.items():
        # Filtrar escenas que tengan B03 y B11 y calidad definida
        candidatas = []
        for scene_id, info in escenas.items():
            if ('B03' in info['archivos'] and 'B11' in info['archivos']
                    and info['calidad'] is not None):
                candidatas.append((scene_id, info))
        if not candidatas:
            logging.warning(f"Año {año}: sin escenas completas (B03+B11)")
            continue

        # Elegir la de mayor calidad (más píxeles válidos)
        mejor_scene_id, mejor_info = max(candidatas, key=lambda x: x[1]['calidad'])
        logging.info(f"Año {año}: seleccionada escena {mejor_scene_id} "
                     f"con calidad {mejor_info['calidad']} píxeles")

        bandas = mejor_info['archivos']
        verde, transform, crs = recortar_y_remuestrear_banda(bandas['B03'], AOI_BOUNDS)
        if np.max(verde) == 0:
            logging.info(f"Año {año}: fuera del área, omitiendo.")
            continue
        swir, _, _ = recortar_y_remuestrear_banda(bandas['B11'], AOI_BOUNDS,
                                                  target_shape=verde.shape)
        ndsi = calcular_ndsi(verde, swir)
        fecha = mejor_info['fecha']
        out_name = f"echaurren_ndsi_{fecha}.tif"
        guardar_ndsi(ndsi, transform, crs, PROC_SENTINEL_DIR / out_name)

# ============================================================================
# PROCESAMIENTO LANDSAT (con selección de mejor escena por año)
# ============================================================================
PATTERN_LS = re.compile(
    r"^(?P<scene_id>L[COTEM][0-9]{2}_L2[SP][0-9A-Z]*_\d{6}_\d{8}_\d{2}_T[12])_(?P<band>green|red|nir08|swir16)\.tif$",
    re.IGNORECASE
)

def agrupar_escenas_por_año_landsat():
    """
    Agrupa todas las bandas de Landsat por año y por scene_id.
    Devuelve dict: {año: {scene_id: {'fecha': str, 'archivos': {banda: Path}, 'calidad': int}}}
    """
    archivos = list(RAW_LANDSAT_DIR.glob("*.tif"))
    if not archivos:
        logging.warning("No se encontraron archivos Landsat.")
        return {}

    escenas_por_año = {}
    for archivo in archivos:
        match = PATTERN_LS.match(archivo.name)
        if not match:
            logging.debug(f"Archivo Landsat no coincide: {archivo.name}")
            continue
        scene_id = match.group('scene_id')
        banda = match.group('band')

        # Extraer fecha (8 dígitos consecutivos en scene_id)
        fecha_match = re.search(r'\d{8}', scene_id)
        if not fecha_match:
            logging.debug(f"No se encontró fecha en {scene_id}")
            continue
        fecha = fecha_match.group()
        año = int(fecha[:4])

        if año not in escenas_por_año:
            escenas_por_año[año] = {}
        if scene_id not in escenas_por_año[año]:
            escenas_por_año[año][scene_id] = {'fecha': fecha, 'archivos': {}, 'calidad': None}
        escenas_por_año[año][scene_id]['archivos'][banda] = archivo

    # Evaluar calidad para cada escena que tenga banda green
    for año, escenas in escenas_por_año.items():
        for scene_id, info in escenas.items():
            if 'green' in info['archivos']:
                calidad = evaluar_calidad_escena(info['archivos']['green'], AOI_BOUNDS)
                info['calidad'] = calidad
            else:
                logging.debug(f"Escena {scene_id} sin banda green, no se puede evaluar calidad")
    return escenas_por_año

def procesar_landsat():
    logging.info("=== PROCESANDO LANDSAT (seleccionando mejor escena por año) ===")
    escenas_por_año = agrupar_escenas_por_año_landsat()
    if not escenas_por_año:
        return

    for año, escenas in escenas_por_año.items():
        # Filtrar escenas que tengan green y swir16 y calidad definida
        candidatas = []
        for scene_id, info in escenas.items():
            if ('green' in info['archivos'] and 'swir16' in info['archivos']
                    and info['calidad'] is not None):
                candidatas.append((scene_id, info))
        if not candidatas:
            logging.warning(f"Año {año}: sin escenas completas (green+swir16)")
            continue

        # Elegir la de mayor calidad (más píxeles válidos)
        mejor_scene_id, mejor_info = max(candidatas, key=lambda x: x[1]['calidad'])
        logging.info(f"Año {año}: seleccionada escena {mejor_scene_id} "
                     f"con calidad {mejor_info['calidad']} píxeles")

        bandas = mejor_info['archivos']
        verde, transform, crs = recortar_y_remuestrear_banda(bandas['green'], AOI_BOUNDS)
        if np.max(verde) == 0:
            logging.info(f"Año {año}: fuera del área, omitiendo.")
            continue
        swir, _, _ = recortar_y_remuestrear_banda(bandas['swir16'], AOI_BOUNDS,
                                                  target_shape=verde.shape)
        ndsi = calcular_ndsi(verde, swir)
        fecha = mejor_info['fecha']
        out_name = f"landsat_ndsi_{fecha}.tif"
        guardar_ndsi(ndsi, transform, crs, PROC_LANDSAT_DIR / out_name)

# ============================================================================
# MAIN
# ============================================================================
def main():
    logging.info("===== INICIANDO PROCESAMIENTO COMPLETO =====")
    procesar_sentinel2()
    procesar_landsat()
    logging.info("===== PROCESAMIENTO FINALIZADO =====")

if __name__ == "__main__":
    main()