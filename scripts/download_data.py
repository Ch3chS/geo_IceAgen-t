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
from datetime import datetime, timedelta

import requests
import fabdem
import planetary_computer
from pystac_client import Client
from shapely.geometry import box, shape as shp_shape
from tqdm import tqdm

# ============================================================================
# CONFIGURACIÓN GLOBAL
# ============================================================================
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR     = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = BASE_DIR / "data" / "raw"

SENTINEL_DIR = RAW_DATA_DIR / "sentinel2"
LANDSAT_DIR  = RAW_DATA_DIR / "landsat"
DEM_DIR      = RAW_DATA_DIR / "fabdem"

for d in [SENTINEL_DIR, LANDSAT_DIR, DEM_DIR]:
    d.mkdir(parents=True, exist_ok=True)

BOUNDS      = (-70.15, -33.60, -70.11, -33.56)
AOI_POLYGON = box(*BOUNDS)

# ── Parámetros de descarga ────────────────────────────────────────────────
MAX_RETRIES = 3
TIMEOUT     = 120
MAX_WORKERS = 10
BLOCK_SIZE  = 1024 * 1024  # 1 MB

# ── Parámetros de búsqueda ────────────────────────────────────────────────
TARGET_DAY   = 26
TARGET_MONTH = 1

DAYS_WINDOW_NORMAL   = 20   # ventana inicial — búsqueda concentrada en enero
DAYS_WINDOW_FALLBACK = 45   # fallback si no hay resultado con ventana reducida

MAX_CLOUD_COVER    = 20
MAX_ITEMS_PER_YEAR = 1

# Cobertura mínima del AOI que debe tener una escena para ser aceptada.
# Filtra escenas en el borde de path/row que solo cubren parte del glaciar.
MIN_AOI_COVERAGE = 0.95

# Año desde el que Landsat 7 tiene fallo SLC-off (franjas negras diagonales)
L7_SLC_FAIL_YEAR = 2004

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
# UTILIDADES DE SELECCIÓN
# ============================================================================
def cobertura_sobre_aoi(item):
    """
    Fracción del AOI cubierta por la geometría de la escena [0.0 – 1.0].
    Devuelve 0 si la geometría no es válida o no intersecta.
    """
    try:
        geom = shp_shape(item.geometry)
        return geom.intersection(AOI_POLYGON).area / AOI_POLYGON.area
    except Exception:
        return 0.0


def es_landsat7_slc_off(item, year):
    """True si la escena es Landsat 7 post-fallo SLC (mayo 2003 en adelante)."""
    if year < L7_SLC_FAIL_YEAR:
        return False
    plataforma = item.properties.get('platform', '').lower()
    return 'landsat-7' in plataforma or 'landsat_7' in plataforma


def score_item(item, target_date):
    """
    Tupla de ordenación (prioridad, delta_días, nubosidad).
    prioridad=1 → descartado (cobertura insuficiente o L7 SLC-off)
    prioridad=0 → aceptado
    """
    year = target_date.year
    if cobertura_sobre_aoi(item) < MIN_AOI_COVERAGE:
        return (1, float('inf'), 100)
    if es_landsat7_slc_off(item, year):
        return (1, float('inf'), 100)
    dt = item.datetime
    if dt is None:
        return (0, float('inf'), 100)
    target_tz = (target_date.replace(tzinfo=dt.tzinfo)
                 if dt.tzinfo else target_date)
    return (0,
            abs((dt - target_tz).days),
            item.properties.get('eo:cloud_cover', 100))


# ============================================================================
# BÚSQUEDA AÑO POR AÑO CON FALLBACK DE VENTANA
# ============================================================================
def _buscar_ventana(catalog, collection, year, target_date,
                    days_window, allow_l7_slc):
    """
    Búsqueda para un año y ventana concretos.
    allow_l7_slc: si True, no penaliza Landsat 7 SLC-off (usado solo en
    fallback de último recurso para años sin otra alternativa).
    Devuelve lista de items válidos ordenados por score.
    """
    start_date = target_date - timedelta(days=days_window)
    end_date   = target_date + timedelta(days=days_window)
    date_range = (f"{start_date.strftime('%Y-%m-%d')}/"
                  f"{end_date.strftime('%Y-%m-%d')}")

    query = {"eo:cloud_cover": {"lt": MAX_CLOUD_COVER}}
    # Excluir L7 SLC-off salvo en fallback de último recurso
    if not allow_l7_slc and year >= L7_SLC_FAIL_YEAR:
        query["platform"] = {"neq": "landsat-7"}

    try:
        search = catalog.search(
            collections=[collection],
            bbox=BOUNDS,
            datetime=date_range,
            query=query,
            max_items=20
        )
        items = list(search.items())
    except Exception as e:
        logging.warning(f"  {year}: error en búsqueda ({e})")
        return []

    # Filtrar y ordenar por score
    validos = [i for i in items if score_item(i, target_date)[0] == 0]
    validos.sort(key=lambda i: score_item(i, target_date))
    return validos


def buscar_items_por_año(catalog, collection, start_year, end_year):
    """
    Busca la mejor escena por año con estrategia de tres pasos:
      1. Ventana normal (±DAYS_WINDOW_NORMAL), sin L7 SLC-off
      2. Ventana ampliada (±DAYS_WINDOW_FALLBACK), sin L7 SLC-off
      3. Ventana ampliada, permitiendo L7 SLC-off (último recurso)
    Retorna MAX_ITEMS_PER_YEAR escenas por año.
    """
    todos      = []
    sin_datos  = []

    for year in range(start_year, end_year + 1):
        target_date = datetime(year, TARGET_MONTH, TARGET_DAY)

        # Paso 1: ventana normal, sin L7 SLC-off
        validos = _buscar_ventana(catalog, collection, year,
                                  target_date, DAYS_WINDOW_NORMAL,
                                  allow_l7_slc=False)

        # Paso 2: ventana ampliada, sin L7 SLC-off
        if not validos:
            logging.info(
                f"  {year}: sin resultado en ±{DAYS_WINDOW_NORMAL} días "
                f"— ampliando a ±{DAYS_WINDOW_FALLBACK} días"
            )
            validos = _buscar_ventana(catalog, collection, year,
                                      target_date, DAYS_WINDOW_FALLBACK,
                                      allow_l7_slc=False)

        # Paso 3: último recurso — permitir L7 SLC-off si no hay alternativa
        #if not validos and year >= L7_SLC_FAIL_YEAR:
        #    logging.warning(
        #        f"  {year}: sin L5/L8/L9 disponible — "
        #        f"usando L7 SLC-off como último recurso"
        #    )
        #    validos = _buscar_ventana(catalog, collection, year,
        #                              target_date, DAYS_WINDOW_FALLBACK,
        #                              allow_l7_slc=True)
        #    # Reordenar sin penalizar L7 cuando es el único disponible
        #    validos.sort(key=lambda i: (
        #        abs((i.datetime - (target_date.replace(tzinfo=i.datetime.tzinfo)
        #             if i.datetime.tzinfo else target_date)).days)
        #        if i.datetime else float('inf'),
        #        i.properties.get('eo:cloud_cover', 100)
        #    ))

        if not validos:
            sin_datos.append(year)
            continue

        mejores = validos[:MAX_ITEMS_PER_YEAR]
        todos.extend(mejores)

        for it in mejores:
            fecha     = it.datetime.strftime('%Y-%m-%d') if it.datetime else '?'
            nubes     = it.properties.get('eo:cloud_cover', '?')
            plat      = it.properties.get('platform', '?')
            cobertura = cobertura_sobre_aoi(it)
            logging.info(
                f"  {year}: {fecha}  nubes={nubes}%  "
                f"plataforma={plat}  cobertura_aoi={cobertura:.0%}"
            )

    if sin_datos:
        logging.warning(
            f"  Sin escenas válidas para {len(sin_datos)} años: {sin_datos}"
        )
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

            logging.info(
                f"    ✓ {output_path.name} "
                f"({output_path.stat().st_size / 1e6:.1f} MB)"
            )
            return True, output_path

        except Exception as e:
            logging.error(
                f"    Intento {attempt+1}/{MAX_RETRIES} falló "
                f"para {output_path.name}: {e}"
            )
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
                executor.submit(download_single_file, url, out, pbar): (url, out)
                for url, out in tareas
            }
            for future in as_completed(future_to_task):
                _, out_path = future_to_task[future]
                try:
                    success, _ = future.result()
                    if not success:
                        logging.error(f"Fallo permanente: {out_path.name}")
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
                                 start_year=2016, end_year=2024)
    años_cubiertos = len(set(i.datetime.year for i in items if i.datetime))
    logging.info(
        f"Seleccionadas {len(items)} escenas Sentinel-2 "
        f"({años_cubiertos} años cubiertos)"
    )
    if not items:
        logging.warning("No se encontraron imágenes Sentinel-2")
        return

    tareas = []
    for item in items:
        for band in ['B03', 'B11']:
            if band in item.assets:
                url      = item.assets[band].href
                out_file = SENTINEL_DIR / f"{item.id}_{band}.tif"
                tareas.append((url, out_file))

    logging.info(f"Generadas {len(tareas)} tareas de descarga (B03, B11)")
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
                                 start_year=1985, end_year=2026)
    años_cubiertos = len(set(i.datetime.year for i in items if i.datetime))
    logging.info(
        f"Seleccionadas {len(items)} escenas Landsat "
        f"({años_cubiertos} años cubiertos)"
    )
    if not items:
        logging.warning("No se encontraron escenas Landsat")
        return

    tareas = []
    for item in items:
        for band in ['green', 'swir16']:
            if band in item.assets:
                url      = item.assets[band].href
                out_file = LANDSAT_DIR / f"{item.id}_{band}.tif"
                tareas.append((url, out_file))

    logging.info(f"Generadas {len(tareas)} tareas de descarga (green, swir16)")
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

        try:
            fabdem.download(BOUNDS, output_path=str(out_path), show_progress=True)
        except TypeError:
            pass

        cache_dir = Path("/tmp/fabdem-cache")
        tiles     = sorted(cache_dir.glob("**/*.tif"))
        if not tiles:
            raise Exception("No se encontraron tiles en caché de FABDEM")

        logging.info(f"Mergeando {len(tiles)} tiles manualmente...")
        datasets          = [rasterio.open(t) for t in tiles]
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

        logging.info(
            f"DEM guardado en {out_path} "
            f"({out_path.stat().st_size / 1e6:.1f} MB)"
        )
    except Exception as e:
        logging.error(f"Error descargando FABDEM: {e}")


# ============================================================================
# DGA (best-effort)
# ============================================================================
# La DGA no expone una descarga automatizable estable (el BNA/SNIA es una app
# JSF con flujos Ajax frágiles). El extracto con las estaciones de la Etapa 5
# (05703006 Estero Glaciar Echaurren Norte, 05704002 Río Maipo en San Alfonso)
# ya viene versionado en el repo, por lo que el pipeline funciona sin descarga.
# Esta función solo regenera el extracto si el archivo nacional está disponible
# en disco (descarga manual previa desde https://snia.mop.gob.cl/BNAConsultas).
DGA_DIR      = RAW_DATA_DIR / "DGA"
DGA_FULL     = DGA_DIR / "caudal_medio_mensual_historico.txt"
DGA_EXTRACT  = DGA_DIR / "caudal_medio_mensual_estaciones.csv"
DGA_CODIGOS  = ["05703006", "05704002"]


def descargar_dga():
    import pandas as pd

    try:
        if not DGA_FULL.exists():
            logging.info(
                "DGA: sin archivo nacional en disco; se mantiene el extracto "
                "versionado (descarga manual opcional desde BNA/SNIA)."
            )
            return
        df = pd.read_csv(DGA_FULL, dtype={"CODIGO ESTACION": str})
        sub = df[df["CODIGO ESTACION"].str.strip().isin(DGA_CODIGOS)].copy()
        DGA_DIR.mkdir(parents=True, exist_ok=True)
        sub.to_csv(DGA_EXTRACT, index=False)
        logging.info(
            f"DGA: extracto actualizado con {len(sub)} filas "
            f"({', '.join(DGA_CODIGOS)}) -> {DGA_EXTRACT.name}"
        )
    except Exception as e:
        logging.error(f"DGA: no se pudo regenerar el extracto: {e}")


# ============================================================================
# MODO DEBUG
# ============================================================================
def obtener_rango_años_input():
    print("\n" + "=" * 50)
    print("MODO DEBUG: SELECCIÓN DE AÑOS")
    print("Puedes ingresar un año (ej. 2020) o un rango (ej. 2018-2021).")
    print("=" * 50)
    entrada = input("Ingresa tu elección: ").strip()
    try:
        if "-" in entrada:
            inicio, fin = entrada.split("-")
            return int(inicio.strip()), int(fin.strip())
        else:
            return int(entrada), int(entrada)
    except ValueError:
        logging.error("Entrada inválida. Usando 2020 por defecto.")
        return 2020, 2020


def descargar_sentinel2_debug(start_year, end_year):
    logging.info(f"=== SENTINEL-2 DEBUG: {start_year}-{end_year} ===")
    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace
    )
    items = buscar_items_por_año(catalog, "sentinel-2-l2a",
                                 start_year=start_year, end_year=end_year)
    if not items:
        logging.warning("Sin imágenes Sentinel-2 en este rango.")
        return
    tareas = []
    for item in items:
        for band in ['B03', 'B11']:
            if band in item.assets:
                out_file = SENTINEL_DIR / f"{item.id}_{band}.tif"
                tareas.append((item.assets[band].href, out_file))
    logging.info(f"Generadas {len(tareas)} tareas (B03, B11)")
    descargar_concurrente(tareas)


def descargar_landsat_debug(start_year, end_year):
    logging.info(f"=== LANDSAT DEBUG: {start_year}-{end_year} ===")
    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace
    )
    items = buscar_items_por_año(catalog, "landsat-c2-l2",
                                 start_year=start_year, end_year=end_year)
    if not items:
        logging.warning("Sin escenas Landsat en este rango.")
        return
    tareas = []
    for item in items:
        for band in ['green', 'swir16']:
            if band in item.assets:
                out_file = LANDSAT_DIR / f"{item.id}_{band}.tif"
                tareas.append((item.assets[band].href, out_file))
    logging.info(f"Generadas {len(tareas)} tareas (green, swir16)")
    descargar_concurrente(tareas)


def ejecutar_debug():
    start_year, end_year = obtener_rango_años_input()
    # descargar_sentinel2_debug(start_year, end_year)
    descargar_landsat_debug(start_year, end_year)


# ============================================================================
# MAIN
# ============================================================================
def main():
    logging.info("===== INICIANDO DESCARGA =====")
    # ejecutar_debug()
    descargar_sentinel2()
    descargar_landsat()
    descargar_dem()
    descargar_dga()
    logging.info("===== DESCARGA COMPLETADA =====")


if __name__ == "__main__":
    main()