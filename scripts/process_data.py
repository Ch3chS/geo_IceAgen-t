#!/usr/bin/env python3
"""
Procesamiento multitemporal de imágenes satelitales para el glaciar Echaurren.
Calcula NDSI (nieve/hielo) para Sentinel-2 y Landsat.
Soporta CRS diferentes transformando el AOI automáticamente.
Selecciona la mejor escena por año cuando hay múltiples descargadas.
"""

import logging
import re
import sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds, reproject, calculate_default_transform
from rasterio.transform import from_bounds as transform_from_bounds

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================================================
# CONFIGURACIÓN DE RUTAS Y ÁREA DE ESTUDIO
# ============================================================================
BASE_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(BASE_DIR))
from scripts.glacier_config import get_config, parse_glacier_arg  # noqa: E402

RAW_SENTINEL_DIR  = BASE_DIR / "data" / "raw" / "echaurren" / "sentinel2"
RAW_LANDSAT_DIR   = BASE_DIR / "data" / "raw" / "echaurren" / "landsat"
PROC_SENTINEL_DIR = BASE_DIR / "data" / "processed" / "echaurren" / "sentinel2"
PROC_LANDSAT_DIR  = BASE_DIR / "data" / "processed" / "echaurren" / "landsat"

for d in [PROC_SENTINEL_DIR, PROC_LANDSAT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Área del glaciar Echaurren en UTM 19S (EPSG:32719) — default (echaurren)
AOI_BOUNDS   = (393150, 6282300, 396200, 6285350)  # (minx, miny, maxx, maxy)
AOI_CRS      = 'EPSG:32719'
AOI_CRS_EPSG = 32719  # entero para comparaciones robustas
RESOLUCION_M = 30
PREFIJO_SALIDA = "echaurren"   # prefijo de archivos de salida (slug del glaciar)

UMBRAL_NDSI_CALIDAD = 0.4   # umbral usado también en la evaluación rápida de calidad


def configurar_glaciar(slug):
    """
    Ajusta rutas, AOI, CRS y prefijo de salida al glaciar `slug`.
    Por defecto (import) se configura echaurren para mantener el
    comportamiento original.
    """
    global RAW_SENTINEL_DIR, RAW_LANDSAT_DIR
    global PROC_SENTINEL_DIR, PROC_LANDSAT_DIR
    global AOI_BOUNDS, AOI_CRS, AOI_CRS_EPSG
    global RESOLUCION_M, PREFIJO_SALIDA

    cfg = get_config(slug)

    RAW_SENTINEL_DIR  = BASE_DIR / "data" / "raw" / cfg.slug / "sentinel2"
    RAW_LANDSAT_DIR   = BASE_DIR / "data" / "raw" / cfg.slug / "landsat"
    PROC_SENTINEL_DIR = BASE_DIR / "data" / "processed" / cfg.slug / "sentinel2"
    PROC_LANDSAT_DIR  = BASE_DIR / "data" / "processed" / cfg.slug / "landsat"

    for d in [PROC_SENTINEL_DIR, PROC_LANDSAT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    AOI_BOUNDS   = cfg.aoi_bounds_utm
    AOI_CRS      = f'EPSG:{cfg.crs_epsg}'
    AOI_CRS_EPSG = cfg.crs_epsg
    RESOLUCION_M = cfg.resolucion_m
    PREFIJO_SALIDA = cfg.slug

    logging.info(f"Glaciar configurado: {cfg.nombre} (slug={cfg.slug})")

# ============================================================================
# FUNCIONES COMUNES
# ============================================================================

def _epsg_de_crs(crs) -> int:
    """Devuelve el código EPSG entero de un CRS de rasterio, o -1 si no puede."""
    try:
        return int(crs.to_epsg())
    except Exception:
        return -1


def recortar_y_remuestrear_banda(ruta_tif, bounds_utm, target_shape=None,
                                 crs_destino=None, resolucion_m=None):
    """
    Lee una banda, recorta y REPROYECTA forzosamente al AOI estricto.
    Asegura que todas las matrices (Sentinel o Landsat) compartan exactamente 
    el mismo extent geográfico y alineación de píxeles.
    Por defecto usa el CRS y la resolución del glaciar configurado.
    """
    crs_destino = crs_destino or AOI_CRS
    resolucion_m = resolucion_m or RESOLUCION_M
    with rasterio.open(ruta_tif) as src:
        # Calcular los límites del AOI en el CRS de destino
        minx, miny, maxx, maxy = bounds_utm
        
        # 1. Definir dimensiones de salida.
        if target_shape:
            out_rows, out_cols = target_shape[0], target_shape[1]
        else:
            out_cols = int((maxx - minx) / resolucion_m)
            out_rows = int((maxy - miny) / resolucion_m)
            
        # 2. Crear la matriz de transformación exacta y rígida anclada a UTM 19S
        # (CORRECCIÓN: Se usa transform_from_bounds en lugar de from_bounds)
        transform_salida = transform_from_bounds(minx, miny, maxx, maxy, out_cols, out_rows)
        
        # 3. Crear matriz vacía para la imagen resultante
        data = np.zeros((out_rows, out_cols), dtype=np.float32)
        
        # 4. Proyectar (Warping) los datos del origen a nuestra matriz rígida
        reproject(
            source=rasterio.band(src, 1),
            destination=data,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform_salida,
            dst_crs=crs_destino,
            resampling=Resampling.bilinear,
            src_nodata=src.nodata,
            dst_nodata=0
        )
        
    return data, transform_salida, rasterio.crs.CRS.from_string(crs_destino)


def calcular_ndsi(banda_verde, banda_swir, nodata=-9999.0):
    """Calcula NDSI = (verde - swir) / (verde + swir)."""
    denominador = banda_verde + banda_swir
    with np.errstate(divide='ignore', invalid='ignore'):
        ndsi = np.where(denominador > 0,
                        (banda_verde - banda_swir) / denominador,
                        nodata)
    return ndsi.astype(np.float32)


def guardar_ndsi(ndsi, transform, crs, output_path):
    """Guarda el array NDSI como GeoTIFF."""
    meta = {
        'driver':    'GTiff',
        'dtype':     'float32',
        'nodata':    -9999.0,
        'width':     ndsi.shape[1],
        'height':    ndsi.shape[0],
        'count':     1,
        'crs':       crs,
        'transform': transform,
        'compress':  'lzw',
    }
    with rasterio.open(output_path, 'w', **meta) as dst:
        dst.write(ndsi, 1)
    logging.info(f"  ✓ Guardado: {output_path.name}")


# ============================================================================
# EVALUACIÓN DE CALIDAD — criterio mejorado
# ============================================================================

def evaluar_calidad_escena(ruta_verde, ruta_swir_opcional, bounds_utm,
                           escala_muestra=0.2):
    """
    Evalúa la calidad de una escena sobre el AOI usando dos criterios combinados:

    1. Cobertura válida: fracción de píxeles con reflectancia > 0 en la banda
       verde (proxy de ausencia de nubes/nodata).
    2. Cobertura glaciar aparente: si se dispone de la banda SWIR, calcula un
       NDSI rápido y cuenta los píxeles que superan el umbral de clasificación.
       Esto evita preferir escenas sin nubes pero con el glaciar tapado de roca.

    Retorna un score = n_validos + 2 * n_ndsi_glaciar  (el factor 2 prioriza
    escenas con hielo visible sobre escenas simplemente libres de nubes).

    Corrección respecto a la versión anterior:
    - La versión original solo contaba píxeles > 0 en verde, por lo que una
      escena con roca perfectamente visible pero sin glaciar expuesto recibía
      el mismo score que una con glaciar; esto podía hacer elegir la escena
      equivocada al final de la temporada cuando la roca domina.
    """
    try:
        with rasterio.open(ruta_verde) as src:
            if _epsg_de_crs(src.crs) != AOI_CRS_EPSG:
                bounds_raster = transform_bounds(
                    AOI_CRS, src.crs, *bounds_utm, densify_pts=21
                )
            else:
                bounds_raster = bounds_utm

            window = from_bounds(*bounds_raster, transform=src.transform)
            h_new  = max(1, int(window.height * escala_muestra))
            w_new  = max(1, int(window.width  * escala_muestra))

            verde = src.read(1, window=window,
                             out_shape=(h_new, w_new),
                             resampling=Resampling.bilinear).astype(np.float32)
            nodata_v = src.nodata if src.nodata is not None else -9999
            verde = np.where(verde == nodata_v, 0.0, verde)

        n_validos = int(np.sum(verde > 0))

        # Si tenemos SWIR, calculamos NDSI rápido
        n_glaciar = 0
        if ruta_swir_opcional is not None:
            try:
                with rasterio.open(ruta_swir_opcional) as src_s:
                    if _epsg_de_crs(src_s.crs) != AOI_CRS_EPSG:
                        bounds_swir = transform_bounds(
                            AOI_CRS, src_s.crs, *bounds_utm, densify_pts=21
                        )
                    else:
                        bounds_swir = bounds_utm
                    win_s = from_bounds(*bounds_swir, transform=src_s.transform)
                    swir  = src_s.read(1, window=win_s,
                                       out_shape=(h_new, w_new),
                                       resampling=Resampling.bilinear
                                       ).astype(np.float32)
                    nodata_s = src_s.nodata if src_s.nodata is not None else -9999
                    swir = np.where(swir == nodata_s, 0.0, swir)

                denom = verde + swir
                with np.errstate(divide='ignore', invalid='ignore'):
                    ndsi_rapido = np.where(denom > 0,
                                          (verde - swir) / denom,
                                          -9999.0)
                n_glaciar = int(np.sum(ndsi_rapido >= UMBRAL_NDSI_CALIDAD))
            except Exception as e:
                logging.debug(f"NDSI rápido fallido para calidad: {e}")

        return n_validos + 2 * n_glaciar

    except Exception as e:
        logging.debug(f"Error evaluando calidad de {ruta_verde.name}: {e}")
        return 0


# ============================================================================
# PROCESAMIENTO SENTINEL-2
# ============================================================================
PATTERN_S2 = re.compile(
    r"^(?P<scene_id>S2[AB]_MSIL2A_(?P<date>\d{8})T\d{6}_R\d{3}_T[A-Z0-9]+"
    r"_\d{8}T\d{6})_(?P<band>B\d{2}[A]?)\.(tif|TIF)$"
)


def agrupar_escenas_por_año_sentinel():
    archivos = (list(RAW_SENTINEL_DIR.glob("*.tif"))
                + list(RAW_SENTINEL_DIR.glob("*.TIF")))
    if not archivos:
        logging.warning("No se encontraron archivos Sentinel-2.")
        return {}

    escenas_por_año = {}
    for archivo in archivos:
        match = PATTERN_S2.match(archivo.name)
        if not match:
            logging.debug(f"Archivo Sentinel no coincide: {archivo.name}")
            continue
        datos    = match.groupdict()
        scene_id = datos['scene_id']
        fecha    = datos['date']
        año      = int(fecha[:4])
        banda    = datos['band']

        escenas_por_año.setdefault(año, {})
        escenas_por_año[año].setdefault(
            scene_id, {'fecha': fecha, 'archivos': {}, 'calidad': None})
        escenas_por_año[año][scene_id]['archivos'][banda] = archivo

    for año, escenas in escenas_por_año.items():
        for scene_id, info in escenas.items():
            arcs = info['archivos']
            if 'B03' in arcs:
                info['calidad'] = evaluar_calidad_escena(
                    arcs['B03'],
                    arcs.get('B11'),      # SWIR disponible → mejor score
                    AOI_BOUNDS,
                )
            else:
                logging.debug(f"Escena {scene_id} sin B03, no se evalúa calidad")
    return escenas_por_año


def procesar_sentinel2():
    logging.info("=== PROCESANDO SENTINEL-2 (seleccionando mejor escena por año) ===")
    escenas_por_año = agrupar_escenas_por_año_sentinel()
    if not escenas_por_año:
        return

    for año, escenas in sorted(escenas_por_año.items()):
        candidatas = [
            (sid, info) for sid, info in escenas.items()
            if 'B03' in info['archivos']
            and 'B11' in info['archivos']
            and info['calidad'] is not None
        ]
        if not candidatas:
            logging.warning(f"Año {año}: sin escenas completas (B03+B11)")
            continue

        mejor_scene_id, mejor_info = max(candidatas, key=lambda x: x[1]['calidad'])
        logging.info(f"Año {año}: seleccionada {mejor_scene_id} "
                     f"(score calidad: {mejor_info['calidad']})")

        bandas = mejor_info['archivos']
        verde, transform, crs = recortar_y_remuestrear_banda(bandas['B03'], AOI_BOUNDS)
        if np.max(verde) == 0:
            logging.info(f"Año {año}: área vacía, omitiendo.")
            continue
        swir, _, _ = recortar_y_remuestrear_banda(
            bandas['B11'], AOI_BOUNDS, target_shape=verde.shape
        )
        ndsi    = calcular_ndsi(verde, swir)
        out_name = f"{PREFIJO_SALIDA}_ndsi_{mejor_info['fecha']}.tif"
        guardar_ndsi(ndsi, transform, crs, PROC_SENTINEL_DIR / out_name)


# ============================================================================
# PROCESAMIENTO LANDSAT
# ============================================================================
PATTERN_LS = re.compile(
    r"^(?P<scene_id>L[COTEM][0-9]{2}_L2[SP][0-9A-Z]*_\d{6}_\d{8}_\d{2}_T[12])"
    r"_(?P<band>green|red|nir08|swir16)\.tif$",
    re.IGNORECASE,
)


def agrupar_escenas_por_año_landsat():
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
        banda    = match.group('band')

        fecha_match = re.search(r'\d{8}', scene_id)
        if not fecha_match:
            logging.debug(f"No se encontró fecha en {scene_id}")
            continue
        fecha = fecha_match.group()
        año   = int(fecha[:4])

        escenas_por_año.setdefault(año, {})
        escenas_por_año[año].setdefault(
            scene_id, {'fecha': fecha, 'archivos': {}, 'calidad': None})
        escenas_por_año[año][scene_id]['archivos'][banda] = archivo

    for año, escenas in escenas_por_año.items():
        for scene_id, info in escenas.items():
            arcs = info['archivos']
            if 'green' in arcs:
                info['calidad'] = evaluar_calidad_escena(
                    arcs['green'],
                    arcs.get('swir16'),   # SWIR disponible → mejor score
                    AOI_BOUNDS,
                )
            else:
                logging.debug(f"Escena {scene_id} sin banda green")
    return escenas_por_año


def procesar_landsat():
    logging.info("=== PROCESANDO LANDSAT (seleccionando mejor escena por año) ===")
    escenas_por_año = agrupar_escenas_por_año_landsat()
    if not escenas_por_año:
        return

    for año, escenas in sorted(escenas_por_año.items()):
        candidatas = [
            (sid, info) for sid, info in escenas.items()
            if 'green' in info['archivos']
            and 'swir16' in info['archivos']
            and info['calidad'] is not None
        ]
        if not candidatas:
            logging.warning(f"Año {año}: sin escenas completas (green+swir16)")
            continue

        mejor_scene_id, mejor_info = max(candidatas, key=lambda x: x[1]['calidad'])
        logging.info(f"Año {año}: seleccionada {mejor_scene_id} "
                     f"(score calidad: {mejor_info['calidad']})")

        bandas = mejor_info['archivos']
        verde, transform, crs = recortar_y_remuestrear_banda(
            bandas['green'], AOI_BOUNDS
        )
        if np.max(verde) == 0:
            logging.info(f"Año {año}: área vacía, omitiendo.")
            continue
        swir, _, _ = recortar_y_remuestrear_banda(
            bandas['swir16'], AOI_BOUNDS, target_shape=verde.shape
        )
        ndsi     = calcular_ndsi(verde, swir)
        out_name = f"{PREFIJO_SALIDA}_ndsi_{mejor_info['fecha']}.tif"
        guardar_ndsi(ndsi, transform, crs, PROC_LANDSAT_DIR / out_name)


# ============================================================================
# MAIN
# ============================================================================
def main():
    logging.info("===== INICIANDO PROCESAMIENTO COMPLETO =====")
    slug = parse_glacier_arg()
    configurar_glaciar(slug)
    procesar_sentinel2()
    procesar_landsat()
    logging.info("===== PROCESAMIENTO FINALIZADO =====")


if __name__ == "__main__":
    main()