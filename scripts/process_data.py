#!/usr/bin/env python3
import logging
import re
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.enums import Resampling

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === RUTAS DINÁMICAS ===
BASE_DIR = Path(__file__).resolve().parents[1]
RAW_SENTINEL_DIR = BASE_DIR / "data" / "raw" / "sentinel2"
PROCESSED_DIR = BASE_DIR / "data" / "processed" / "sentinel2"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Coordenadas Echaurren (EPSG:32719)
AOI_BOUNDS = (392500, 6280500, 397500, 6285500)

# Regex más flexible: T[A-Z0-9]+ permite cualquier largo de Tile ID
FILENAME_PATTERN = re.compile(
    r"^(?P<scene_id>S2[AB]_MSIL2A_(?P<date>\d{8})T\d{6}_R\d{3}_T[A-Z0-9]+_\d{8}T\d{6})_(?P<band>B\d{2}[A]?)\.(tif|TIF)$"
)

def agrupar_bandas_por_escena():
    escenas = {}
    
    # DEBUG: Ver dónde estamos buscando
    logging.info(f"Buscando archivos en: {RAW_SENTINEL_DIR}")
    
    # Buscamos tanto .tif como .TIF
    archivos = list(RAW_SENTINEL_DIR.glob("*.tif")) + list(RAW_SENTINEL_DIR.glob("*.TIF"))
    
    if not archivos:
        logging.error("¡ERROR! No se encontró ningún archivo .tif en la carpeta.")
        return escenas

    for archivo in archivos:
        match = FILENAME_PATTERN.match(archivo.name)
        if match:
            datos = match.groupdict()
            s_id = datos['scene_id']
            if s_id not in escenas:
                escenas[s_id] = {'fecha': datos['date'], 'archivos': {}}
            escenas[s_id]['archivos'][datos['band']] = archivo
        else:
            # DEBUG: Ver qué archivo está fallando en el patrón
            logging.debug(f"Archivo no coincide con el patrón: {archivo.name}")
            
    return escenas

def leer_recorte_banda(ruta_tif, bounds_utm, target_shape=None):
    """
    Lee la banda y, si se especifica target_shape, 
    reeustrea los datos automáticamente.
    """
    with rasterio.open(ruta_tif) as src:
        window = from_bounds(*bounds_utm, transform=src.transform)
        
        # Si no nos dan un tamaño objetivo, leemos el original del archivo
        out_shape = target_shape if target_shape else None
        
        # Leemos con remuestreo bilineal si estamos cambiando el tamaño
        data = src.read(
            1, 
            window=window, 
            boundless=True, 
            fill_value=0,
            out_shape=out_shape,
            resampling=Resampling.bilinear
        )
        
        transform_ventana = src.window_transform(window)
        # Si reajustamos el tamaño, debemos ajustar la escala de la transformación
        if target_shape:
            scale_x = window.width / target_shape[1]
            scale_y = window.height / target_shape[0]
            transform_ventana = transform_ventana * transform_ventana.scale(scale_x, scale_y)
            
        return data.astype(np.float32), transform_ventana, src.crs

def calcular_y_guardar_ndsi(scene_id, info):
    bandas = info['archivos']
    if 'B03' not in bandas or 'B11' not in bandas: return

    # 1. Leemos B03 primero para obtener el tamaño de referencia (10m)
    b03, transform, crs = leer_recorte_banda(bandas['B03'], AOI_BOUNDS)
    
    # 2. Leemos B11 FORZANDO que tenga el mismo tamaño que B03 (500x500)
    target_shape = b03.shape # Esto es (500, 500)
    b11, _, _ = leer_recorte_banda(bandas['B11'], AOI_BOUNDS, target_shape=target_shape)

    if np.max(b03) == 0:
        logging.info(f"  Omitiendo {scene_id}: Fuera de los límites del glaciar.")
        return

    logging.info(f"Procesando NDSI (con remuestreo) para fecha: {info['fecha']}")

    # Ahora b03 y b11 tienen la misma forma
    denominador = b03 + b11
    with np.errstate(divide='ignore', invalid='ignore'):
        ndsi = np.where(denominador > 0, (b03 - b11) / denominador, -9999.0)

    meta = {'driver': 'GTiff', 'dtype': 'float32', 'nodata': -9999.0,
            'width': ndsi.shape[1], 'height': ndsi.shape[0], 'count': 1,
            'crs': crs, 'transform': transform, 'compress': 'lzw'}

    out_name = f"echaurren_ndsi_{info['fecha']}.tif"
    with rasterio.open(PROCESSED_DIR / out_name, 'w', **meta) as dst:
        dst.write(ndsi, 1)
    logging.info(f"  ✓ Procesado: {out_name}")

def main():
    logging.info("===== INICIANDO PROCESAMIENTO =====")
    escenas = agrupar_bandas_por_escena()
    logging.info(f"Escenas encontradas tras filtrar: {len(escenas)}")
    for s_id, info in escenas.items():
        calcular_y_guardar_ndsi(s_id, info)
    logging.info("===== FIN =====")

if __name__ == "__main__":
    main()