#!/usr/bin/env python3
"""
Descarga robusta por dataset:
- Sentinel-2 (Planetary Computer)
- Landsat (Planetary Computer)
- DEM (FABDEM)
Cada dataset tiene su propia función principal.
"""

import logging
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
import fabdem
import planetary_computer
from pystac_client import Client
from shapely.geometry import box
from tqdm import tqdm

# ============================================================================
# CONFIGURACIÓN GLOBAL
# ============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = BASE_DIR / "data" / "raw"

SENTINEL_DIR = RAW_DATA_DIR / "sentinel2"
LANDSAT_DIR  = RAW_DATA_DIR / "landsat"
DEM_DIR      = RAW_DATA_DIR / "fabdem"

for d in [SENTINEL_DIR, LANDSAT_DIR, DEM_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Área de estudio (Andes, Chile central, glaciares)
BOUNDS      = (-72.0, -37.0, -68.0, -29.0)
AOI_POLYGON = box(*BOUNDS)

# Fechas
START_DATE    = "1984-01-01"
END_DATE      = "2026-04-23"
START_DATE_S2 = "2010-01-01"

# Parámetros de descarga
MAX_RETRIES = 3
TIMEOUT     = 120
MAX_WORKERS = 8
BLOCK_SIZE  = 1024 * 1024  # 1 MB

# ============================================================================
# SESSION POR HILO
# ============================================================================
_thread_local = threading.local()

def get_session():
    if not hasattr(_thread_local, 'session'):
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=4,
            pool_maxsize=8
        )
        s.mount('https://', adapter)
        _thread_local.session = s
    return _thread_local.session

# ============================================================================
# BÚSQUEDA AÑO POR AÑO
# ============================================================================
def buscar_items_por_año(catalog, collection, start_year, end_year, max_por_año=1):
    """
    Busca items año por año para asegurar cobertura histórica completa.
    Cubre verano austral: diciembre del año anterior + enero/febrero/marzo del año.
    """
    todos = []
    for year in range(start_year, end_year + 1):
        ranges = [
            f"{year-1}-12-01/{year-1}-12-31",
            f"{year}-01-01/{year}-03-31",
        ]
        items_año = []
        for rango in ranges:
            try:
                search = catalog.search(
                    collections=[collection],
                    bbox=BOUNDS,
                    datetime=rango,
                    query={"eo:cloud_cover": {"lt": 50}},
                    max_items=20
                )
                items_año.extend(list(search.items()))
            except Exception as e:
                logging.warning(f"Error buscando {collection} en {rango}: {e}")

        if items_año:
            mejores = sorted(
                items_año,
                key=lambda x: x.properties.get('eo:cloud_cover', 100)
            )[:max_por_año]
            todos.extend(mejores)
            logging.info(f"  {year}: {len(mejores)} escena(s) "
                         f"(nubes: {mejores[0].properties.get('eo:cloud_cover', '?'):.1f}%)")
        else:
            logging.warning(f"  {year}: sin imágenes limpias disponibles")

    return todos

# ============================================================================
# DESCARGA
# ============================================================================
def download_single_file(url, output_path, pbar_global):
    if output_path.exists() and output_path.stat().st_size > 0:
        logging.info(f"  {output_path.name} ya existe, omitiendo")
        return True, output_path

    for attempt in range(MAX_RETRIES):
        try:
            response = get_session().get(url, stream=True, timeout=TIMEOUT)
            response.raise_for_status()

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=BLOCK_SIZE):
                    if chunk:
                        f.write(chunk)
                        pbar_global.update(len(chunk))

            if output_path.stat().st_size == 0:
                raise Exception("Archivo vacío")

            logging.info(f"    ✓ {output_path.name} ({output_path.stat().st_size / 1e6:.1f} MB)")
            return True, output_path

        except Exception as e:
            logging.error(f"    Intento {attempt+1}/{MAX_RETRIES} falló para {output_path.name}: {e}")
            if output_path.exists():
                output_path.unlink()
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

    return False, output_path


def descargar_concurrente(tareas, max_workers=MAX_WORKERS):
    if not tareas:
        return

    total_bytes = 0
    for url, _ in tareas:
        try:
            r = get_session().head(url, timeout=15)
            total_bytes += int(r.headers.get('content-length', 0))
        except Exception:
            pass

    with tqdm(total=total_bytes if total_bytes > 0 else None,
              unit='B', unit_scale=True, unit_divisor=1024,
              desc="Descargando", ncols=90) as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(download_single_file, url, out_path, pbar): (url, out_path)
                for url, out_path in tareas
            }
            for future in as_completed(future_to_task):
                _, out_path = future_to_task[future]
                try:
                    success, _ = future.result()
                    if not success:
                        logging.error(f"Fallo permanente para {out_path.name}")
                except Exception as e:
                    logging.error(f"Excepción en {out_path.name}: {e}")

# ============================================================================
# 1. SENTINEL-2
# ============================================================================
def descargar_sentinel2():
    logging.info("=== DESCARGANDO SENTINEL-2 (Planetary Computer) ===")
    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace
    )
    items = buscar_items_por_año(catalog, "sentinel-2-l2a",
                                  start_year=2016, end_year=2024, max_por_año=1)
    años_cubiertos = len(set(i.datetime.year for i in items))
    logging.info(f"Seleccionadas {len(items)} escenas Sentinel-2 ({años_cubiertos} años cubiertos)")
    if not items:
        logging.warning("No se encontraron imágenes Sentinel-2")
        return

    tareas = []
    for item in items:
        for band in ['B03', 'B04', 'B08', 'B11']:
            if band in item.assets:
                url = item.assets[band].href
                out_file = SENTINEL_DIR / f"{item.id}_{band}.tif"
                tareas.append((url, out_file))

    logging.info(f"Generadas {len(tareas)} tareas de descarga (B03, B04, B08, B11)")
    descargar_concurrente(tareas)

# ============================================================================
# 2. LANDSAT
# ============================================================================
def descargar_landsat():
    logging.info("=== DESCARGANDO LANDSAT (Planetary Computer) ===")
    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace
    )
    items = buscar_items_por_año(catalog, "landsat-c2-l2",
                                  start_year=1984, end_year=2024, max_por_año=1)
    años_cubiertos = len(set(i.datetime.year for i in items))
    logging.info(f"Seleccionadas {len(items)} escenas Landsat ({años_cubiertos} años cubiertos)")
    if not items:
        logging.warning("No se encontraron escenas Landsat")
        return

    tareas = []
    for item in items:
        for band in ['green', 'red', 'nir08', 'swir16']:
            if band in item.assets:
                url = item.assets[band].href
                out_file = LANDSAT_DIR / f"{item.id}_{band}.tif"
                tareas.append((url, out_file))

    logging.info(f"Generadas {len(tareas)} tareas de descarga (green, red, nir08, swir16)")
    descargar_concurrente(tareas)

# ============================================================================
# 3. DEM (FABDEM)
# ============================================================================
def descargar_dem():
    logging.info("=== DESCARGANDO DEM (FABDEM) ===")
    out_path = DEM_DIR / "fabdem_dem.tif"
    if out_path.exists() and out_path.stat().st_size > 0:
        logging.info("FABDEM ya existe, omitiendo")
        return
    try:
        import rasterio
        from rasterio.merge import merge as rio_merge

        # Descargar con fabdem (ignora el error del merge interno)
        try:
            fabdem.download(BOUNDS, output_path=str(out_path), show_progress=True)
        except TypeError:
            pass  # El error de merge() es esperado, los tiles ya están en caché

        # Buscar tiles en la caché de fabdem
        cache_dir = Path("/tmp/fabdem-cache")
        tiles = sorted(cache_dir.glob("**/*.tif"))
        if not tiles:
            raise Exception("No se encontraron tiles en caché de FABDEM")

        logging.info(f"Mergeando {len(tiles)} tiles manualmente...")
        datasets = [rasterio.open(t) for t in tiles]
        mosaic, transform = rio_merge(datasets)

        profile = datasets[0].profile.copy()
        profile.update({
            "height":    mosaic.shape[1],
            "width":     mosaic.shape[2],
            "transform": transform,
            "compress":  "lzw"
        })

        with rasterio.open(out_path, 'w', **profile) as dst:
            dst.write(mosaic)

        for ds in datasets:
            ds.close()

        logging.info(f"DEM guardado en {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")

    except Exception as e:
        logging.error(f"Error descargando FABDEM: {e}")
        
# ============================================================================
# MAIN
# ============================================================================
def main():
    logging.info("===== INICIANDO DESCARGA POR DATASET =====")
    descargar_sentinel2()   # Comenta si no quieres Sentinel-2
    descargar_landsat()     # Comenta si no quieres Landsat
    descargar_dem()        # Comenta si no quieres DEM
    logging.info("===== DESCARGA COMPLETADA =====")

if __name__ == "__main__":
    main()