#!/usr/bin/env python3
"""
Análisis espacial del glaciar Echaurren.

Etapa 3 — Clasificación con filtro DEM y vectorización a GeoPackage.
Etapa 4 — Series temporales independientes por sensor con delta acumulado
           y análisis por décadas.
"""

import logging
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import shapes
from rasterio.warp import reproject
from scipy import stats
import geopandas as gpd
from shapely.geometry import shape

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================================================
# CONFIGURACIÓN
# ============================================================================
BASE_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(BASE_DIR))
from scripts.glacier_config import get_config, parse_glacier_arg  # noqa: E402

PROC_DIR  = BASE_DIR / "data" / "processed" / "echaurren"
NDSI_DIRS = {
    "landsat":   PROC_DIR / "landsat",
    "sentinel2": PROC_DIR / "sentinel2",
}
CLAS_DIR   = PROC_DIR / "clasificacion"
VECTOR_DIR = PROC_DIR / "vectores"
OUT_DIR    = BASE_DIR / "outputs" / "echaurren"

DEM_PATH = BASE_DIR / "data" / "raw" / "echaurren" / "fabdem" / "fabdem_dem.tif"

UMBRAL_NDSI = 0.4
ELEV_MIN_M  = 3000
AREA_MIN_M2 = 5_000
CRS_SALIDA      = "EPSG:32719"
CRS_SALIDA_EPSG = 32719
SLUG            = "echaurren"

NODATA_IN  = -9999.0
NODATA_OUT = 255

AÑO_BASE = {
    "landsat":   1985,
    "sentinel2": None,  # primer año disponible
}

DECADAS = [(1985, 1994), (1995, 2004), (2005, 2014), (2015, 2025)]

# Ventana para la media móvil centrada usada en el delta acumulado.
# Con 5 años (±2) se suaviza la variabilidad interanual sin ocultar tendencias.
VENTANA_MEDIA_MOVIL = 5

# ----------------------------------------------------------------------------
# Caudal DGA (Etapa 5)
# ----------------------------------------------------------------------------
# El glaciar Echaurren drena al Río Yeso, por lo que la estación
# hidrológicamente correcta es la 05703006, ubicada sobre el estero del propio
# glaciar (señal pura de deshielo glaciar). Sin embargo, su cobertura termina
# en 2004 (vacío de la cuenca del Yeso en 2005-2023), por lo que se incluye
# además la estación 05704002 (Río Maipo en San Alfonso), aguas abajo de la
# confluencia del Yeso, que extiende el solapamiento con Landsat hasta 2016.
DGA_MENSUAL_PATH = BASE_DIR / "data" / "raw" / "DGA" / "caudal_medio_mensual_estaciones.csv"

DGA_ESTACIONES = {
    "05703006": "Estero Glaciar Echaurren Norte",
    "05704002": "Río Maipo en San Alfonso",
}

# Meses de la temporada de deshielo (verano estival austral): diciembre del año
# anterior + enero y febrero del año de la imagen. La imagen Landsat es de
# ~26 de enero, por lo que corresponde al mismo verano hidrológico.
MESES_ESTIVOS = [12, 1, 2]
MIN_MESES_ESTIVOS = 2   # regla de completitud: al menos 2 de 3 meses DJF

for d in [CLAS_DIR, VECTOR_DIR, OUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def configurar_glaciar(slug):
    """
    Ajusta rutas, umbrales, CRS, estaciones DGA y nombres de salida al glaciar
    `slug`. Por defecto (import) se configura echaurren para mantener el
    comportamiento original.
    """
    global PROC_DIR, NDSI_DIRS, CLAS_DIR, VECTOR_DIR, OUT_DIR
    global DEM_PATH, UMBRAL_NDSI, ELEV_MIN_M, AREA_MIN_M2
    global CRS_SALIDA, CRS_SALIDA_EPSG, SLUG
    global DGA_ESTACIONES

    cfg = get_config(slug)

    PROC_DIR  = BASE_DIR / "data" / "processed" / cfg.slug
    NDSI_DIRS = {
        "landsat":   PROC_DIR / "landsat",
        "sentinel2": PROC_DIR / "sentinel2",
    }
    CLAS_DIR   = PROC_DIR / "clasificacion"
    VECTOR_DIR = PROC_DIR / "vectores"
    OUT_DIR    = BASE_DIR / "outputs" / cfg.slug

    DEM_PATH = BASE_DIR / "data" / "raw" / cfg.slug / "fabdem" / "fabdem_dem.tif"

    UMBRAL_NDSI = cfg.umbral_ndsi
    ELEV_MIN_M  = cfg.elev_min_m
    AREA_MIN_M2 = cfg.area_min_m2
    CRS_SALIDA      = f"EPSG:{cfg.crs_epsg}"
    CRS_SALIDA_EPSG = cfg.crs_epsg
    SLUG            = cfg.slug

    DGA_ESTACIONES = cfg.dga_estaciones

    for d in [CLAS_DIR, VECTOR_DIR, OUT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    logging.info(f"Glaciar configurado: {cfg.nombre} (slug={cfg.slug})")


# ============================================================================
# UTILIDADES
# ============================================================================

# Patrón explícito: busca _YYYYMMDD_ en el nombre del archivo.
_RE_FECHA_NOMBRE = re.compile(r'(?:^|_)(\d{4})(\d{2})(\d{2})(?:_|\.)')


def _año_de_nombre(nombre: str):
    """Extrae el año de un nombre de archivo con fecha _YYYYMMDD_."""
    m = _RE_FECHA_NOMBRE.search(nombre)
    if not m:
        logging.debug(f"No se pudo extraer año de: {nombre}")
        return None
    año = int(m.group(1))
    # Sanidad básica: rechazar años fuera del rango satelital esperado
    if not (1972 <= año <= 2100):
        logging.debug(f"Año extraído fuera de rango ({año}) en: {nombre}")
        return None
    return año


def _cargar_dem_reproyectado(meta_destino):
    if not DEM_PATH.exists():
        logging.warning(
            f"FABDEM no encontrado en {DEM_PATH} — omitiendo filtro altitudinal")
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
    valido  = (ndsi != nodata_in) & (~np.isnan(ndsi))
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
    logging.info(
        f"=== CLASIFICANDO {sensor.upper()} "
        f"(NDSI >= {UMBRAL_NDSI}, DEM >= {ELEV_MIN_M} m) ==="
    )
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
    geoms   = [shape(g) for g, v in shapes(mascara, mask=mascara,
                                            transform=transform)
               if int(v) == 1]

    if not geoms:
        logging.info(f"  {sensor} {año}: sin polígonos glaciares")
        return gpd.GeoDataFrame(
            columns=['geometry', 'año', 'sensor', 'area_km2'], crs=crs)

    gdf = gpd.GeoDataFrame({'geometry': geoms}, crs=crs)

    if gdf.crs.to_epsg() != CRS_SALIDA_EPSG:
        gdf = gdf.to_crs(CRS_SALIDA)

    gdf['area_m2'] = gdf.geometry.area
    antes = len(gdf)
    gdf   = gdf[gdf['area_m2'] >= AREA_MIN_M2].reset_index(drop=True)
    if antes - len(gdf):
        logging.info(
            f"    Descartados {antes - len(gdf)} parches < {AREA_MIN_M2} m²")

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
            gdf_sensor = pd.concat(gdfs, ignore_index=True)
            gdf_sensor = gpd.GeoDataFrame(gdf_sensor, crs=CRS_SALIDA)
            out_gpkg   = VECTOR_DIR / f"glaciar_{SLUG}_{sensor}.gpkg"
            gdf_sensor.to_file(out_gpkg, driver='GPKG')
            logging.info(f"  ✓ {out_gpkg.name} ({len(gdf_sensor)} polígonos)")
            gdfs_por_sensor[sensor] = gdf_sensor

    if gdfs_por_sensor:
        gdf_all = pd.concat(gdfs_por_sensor.values(), ignore_index=True)
        gdf_all = gpd.GeoDataFrame(gdf_all, crs=CRS_SALIDA)
        out_all = VECTOR_DIR / f"glaciar_{SLUG}_todos.gpkg"
        gdf_all.to_file(out_all, driver='GPKG')
        logging.info(f"  ✓ {out_all.name} ({len(gdf_all)} polígonos totales)")
        return gdfs_por_sensor

    return {}


# ============================================================================
# ETAPA 4 — SERIES TEMPORALES INDEPENDIENTES POR SENSOR
# ============================================================================

def _media_movil_centrada(series: pd.Series, ventana: int) -> pd.Series:
    """
    Media móvil centrada con min_periods=1 para no perder extremos de la serie.
    Se usa como referencia dinámica en el cálculo del delta acumulado, evitando
    que un único año base atípico (muy nevoso o muy seco) distorsione toda la
    serie de cambio.
    """
    return series.rolling(window=ventana, center=True, min_periods=1).mean()


def construir_serie_sensor(gdf_sensor, sensor):
    """
    Serie temporal para un sensor con delta acumulado mejorado.

    Cambio metodológico respecto a la versión anterior
    ─────────────────────────────────────────────────────
    Versión anterior: delta_km2 = At - A_{año_base}
        Problema: el delta acumulado depende enteramente de un único valor
        de referencia (el área del año base). Si ese año fue atípicamente
        nevoso o seco, toda la serie queda sesgada. Además, el "porcentaje
        de cambio" resultante describe solo cuánto cambió respecto a ese
        punto, no la tendencia real de largo plazo.

    Versión corregida: delta_km2 = At - MM_t
        donde MM_t es la media móvil centrada de ventana VENTANA_MEDIA_MOVIL
        calculada sobre la propia serie. El delta ahora mide la desviación
        de cada año respecto a su entorno temporal inmediato, capturando
        anomalías interanuales sin depender de un año ancla.

    Para la comparación de largo plazo se conserva también:
        - area_ref_km2: área del año base (referencia fija, para informe)
        - delta_largo_plazo_km2: At - A_{año_base} (tendencia acumulada total)

    Adicionalmente se añade el cálculo de la tendencia lineal global
    (regresión por mínimos cuadrados) para reportar una tasa de cambio
    robusta y el cambio porcentual basado en la recta de regresión.

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

    # --- Referencia de largo plazo: mediana del quintil inicial y final -------
    #
    # Problema con año puntual: usar A_{año_base} (o A_{año_final}) como
    # referencia hace que todo el cambio acumulado dependa de 1 sola medición,
    # que puede ser atípicamente alta o baja (nevada excepcional, nubosidad
    # residual, etc.).
    #
    # Solución: la referencia de inicio es la mediana del 20 % de años más
    # antiguos de la serie; la referencia de cierre (para pct_largo_plazo al
    # final) se calcula análogamente con el 20 % más reciente. El delta de
    # cada año se expresa respecto a la referencia de inicio, igual que antes,
    # pero ahora esa referencia es robusta a observaciones aisladas.
    n = len(area_por_año)
    q = max(1, n // 5)   # tamaño del quintil (mínimo 1 año)

    area_ref_inicio = float(
        area_por_año['area_total_km2'].iloc[:q].median()
    )
    año_base = int(area_por_año['año'].iloc[0])   # conservado solo para log/CSV

    # También guardamos la referencia del quintil final para el % de cambio
    # al final de la serie (más estable que el último año puntual)
    area_ref_fin = float(
        area_por_año['area_total_km2'].iloc[-q:].median()
    )

    logging.info(
        f"  {sensor} — ref. inicio (mediana primeros {q} años): "
        f"{area_ref_inicio:.4f} km²  |  "
        f"ref. fin (mediana últimos {q} años): {area_ref_fin:.4f} km²"
    )

    # --- Delta de largo plazo (At - ref_inicio) --------------------------------
    area_por_año['sensor']                = sensor
    area_por_año['año_base']              = año_base
    area_por_año['area_ref_km2']          = round(area_ref_inicio, 5)
    area_por_año['area_ref_fin_km2']      = round(area_ref_fin, 5)
    area_por_año['delta_largo_plazo_km2'] = (
        area_por_año['area_total_km2'] - area_ref_inicio).round(5)
    area_por_año['pct_largo_plazo']       = (
        area_por_año['delta_largo_plazo_km2'] / area_ref_inicio * 100).round(2)

    # --- Delta interanual (At - MM_t): anomalía respecto a tendencia local ---
    # Captura si un año fue excepcionalmente más o menos glaciado que sus
    # vecinos, sin el sesgo del año ancla.
    mm = _media_movil_centrada(
        area_por_año['area_total_km2'], VENTANA_MEDIA_MOVIL)
    area_por_año['media_movil_km2']   = mm.round(5)
    area_por_año['delta_anomalia_km2'] = (
        area_por_año['area_total_km2'] - mm).round(5)
    area_por_año['pct_anomalia']       = (
        area_por_año['delta_anomalia_km2'] / mm * 100).round(2)

    # --- Tendencia lineal global (regresión) ---------------------------------
    # Calcula la recta de tendencia para toda la serie del sensor
    x_vals = area_por_año['año'].values
    y_vals = area_por_año['area_total_km2'].values
    if len(x_vals) >= 2:
        pend, inter = np.polyfit(x_vals, y_vals, 1)
        area_tendencia_inicio = pend * x_vals[0] + inter
        area_tendencia_fin    = pend * x_vals[-1] + inter
        cambio_tendencia_pct   = (area_tendencia_fin - area_tendencia_inicio) / area_tendencia_inicio * 100
    else:
        pend = area_tendencia_inicio = area_tendencia_fin = cambio_tendencia_pct = np.nan

    area_por_año['tasa_lineal_km2_año']       = pend
    area_por_año['area_tendencia_inicio_km2'] = area_tendencia_inicio
    area_por_año['area_tendencia_fin_km2']    = area_tendencia_fin
    area_por_año['cambio_tendencia_pct']      = cambio_tendencia_pct

    # --- Década --------------------------------------------------------------
    def asignar_decada(año):
        for ini, fin in DECADAS:
            if ini <= año <= fin:
                return f"{ini}-{fin}"
        return "fuera_rango"

    area_por_año['decada'] = area_por_año['año'].apply(asignar_decada)
    return area_por_año


def analisis_decadas_sensor(serie, sensor):
    """
    Mediana, tasa de cambio y métricas de ajuste por década para un sensor.

    Cambio metodológico respecto a la versión anterior
    ─────────────────────────────────────────────────────
    Versión anterior: np.polyfit(años, áreas, 1)[0]
        Solo devolvía la pendiente sin ninguna métrica de ajuste, haciendo
        imposible distinguir una tendencia significativa de ruido. Tampoco
        reportaba incertidumbre.

    Versión corregida: scipy.stats.linregress
        Entrega además R², p-valor, error estándar de la pendiente e
        intervalo de confianza al 95% (±1.96·se). Esto permite:
        - Evaluar si la tasa es estadísticamente significativa (p < 0.05).
        - Comparar la aceleración entre décadas con base estadística.
        - Reportar la incertidumbre de la estimación.
    """
    resumen = []
    for ini, fin in DECADAS:
        sub = serie[(serie['año'] >= ini) & (serie['año'] <= fin)].copy()
        if sub.empty:
            continue

        mediana = float(sub['area_total_km2'].median())
        n       = len(sub)

        if n >= 3:
            result  = stats.linregress(sub['año'], sub['area_total_km2'])
            pendiente = result.slope
            r2        = result.rvalue ** 2
            p_valor   = result.pvalue
            se        = result.stderr
            ic95_inf  = pendiente - 1.96 * se
            ic95_sup  = pendiente + 1.96 * se
        elif n == 2:
            # Con solo 2 puntos la regresión es exacta pero no tiene p-valor
            # significativo; se reportan pendiente y R²=1 con advertencia.
            result    = stats.linregress(sub['año'], sub['area_total_km2'])
            pendiente = result.slope
            r2        = 1.0
            p_valor   = float('nan')
            se        = float('nan')
            ic95_inf  = float('nan')
            ic95_sup  = float('nan')
            logging.warning(
                f"  {sensor} {ini}-{fin}: solo 2 años — tasa orientativa")
        else:
            pendiente = float('nan')
            r2        = float('nan')
            p_valor   = float('nan')
            se        = float('nan')
            ic95_inf  = float('nan')
            ic95_sup  = float('nan')

        resumen.append({
            'sensor':        sensor,
            'decada':        f"{ini}-{fin}",
            'n_años':        n,
            'mediana_km2':   round(mediana, 4),
            'tasa_km2_año':  round(pendiente, 5) if not np.isnan(pendiente) else float('nan'),
            'r2':            round(r2, 4)        if not np.isnan(r2)        else float('nan'),
            'p_valor':       round(p_valor, 4)   if not np.isnan(p_valor)   else float('nan'),
            'se_pendiente':  round(se, 6)         if not np.isnan(se)        else float('nan'),
            'ic95_inf':      round(ic95_inf, 5)  if not np.isnan(ic95_inf)  else float('nan'),
            'ic95_sup':      round(ic95_sup, 5)  if not np.isnan(ic95_sup)  else float('nan'),
        })
        sig = "✓ sig." if (not np.isnan(p_valor) and p_valor < 0.05) else "– n.s."
        logging.info(
            f"  {sensor} {ini}-{fin}: mediana={mediana:.4f} km²  "
            f"tasa={pendiente:+.5f} km²/año  R²={r2:.3f}  "
            f"p={p_valor:.3f} {sig}  (n={n})"
        )
    return pd.DataFrame(resumen)


# ============================================================================
# ETAPA 5 — CORRELACIÓN CON CAUDAL DGA
# ============================================================================

def leer_caudal_dga(ruta=DGA_MENSUAL_PATH, codigo="05703006"):
    """
    Lee el caudal medio mensual de una estación DGA.

    El código de estación viene con ceros a la izquierda (p. ej. "05703006"),
    por lo que se lee como texto para no perderlos.
    """
    df = pd.read_csv(ruta, dtype={"CODIGO ESTACION": str})
    sub = df[df["CODIGO ESTACION"].str.strip() == codigo].copy()
    if sub.empty:
        logging.warning(f"DGA: sin datos para la estación {codigo}")
        return pd.DataFrame(columns=["Año", "Mes", "Caudal_Medio_mensual"])
    return sub[["Año", "Mes", "Caudal_Medio_mensual"]]


def caudal_estival_djf(df, año_imagen):
    """
    Caudal estival DJF para el año hidrológico de una imagen de ~26 de enero.

    El verano austral (dic-ene-feb) cruza dos años civiles: diciembre del año
    anterior y enero-febrero del año de la imagen. Se calcula el promedio de
    los meses presentes con al menos MIN_MESES_ESTIVOS (2 de 3) para evitar
    promediar con meses faltantes. Devuelve NaN si no hay datos suficientes.
    """
    dic = df[(df["Año"] == año_imagen - 1) & (df["Mes"] == 12)]
    ene = df[(df["Año"] == año_imagen) & (df["Mes"] == 1)]
    feb = df[(df["Año"] == año_imagen) & (df["Mes"] == 2)]

    valores = pd.concat([dic["Caudal_Medio_mensual"],
                         ene["Caudal_Medio_mensual"],
                         feb["Caudal_Medio_mensual"]], ignore_index=True)
    valores = pd.to_numeric(valores, errors="coerce").dropna()

    if len(valores) < MIN_MESES_ESTIVOS:
        return float("nan")
    return float(valores.mean())


def _residuos_detrended(x, y):
    """Elimina la tendencia lineal temporal de cada serie (residuos)."""
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    if len(x_arr) < 3:
        return y_arr, np.full_like(y_arr, np.nan)
    pend, inter = np.polyfit(x_arr, y_arr, 1)
    return y_arr, y_arr - (pend * x_arr + inter)


def correlacion_pearson():
    """
    Correlación de Pearson entre área glaciar (pipeline) y caudal estival DGA.

    Alineación temporal: la imagen de ~26 de enero del año A se empareja con el
    caudal DJF del mismo año hidrológico (dic A-1 + ene A + feb A), por lo que
    ambos describen el mismo verano.

    Control anti-artefacto: además del coeficiente crudo se reporta la
    correlación sobre los RESIDUOS de quitar la tendencia temporal a ambas
    series. Esto es necesario porque área y caudal co-decrecen a lo largo de
    las décadas (retroceso glaciar + sequía), lo que puede inflar artificialmente
    el r de Pearson. La correlación detrended mide si las ANOMALÍAS interanuales
    de un año correlacionan con las del otro.
    """
    logging.info("===== ETAPA 5: CORRELACIÓN CON CAUDAL DGA =====")
    serie = pd.read_csv(OUT_DIR / "serie_temporal_landsat.csv")

    rows_caudal = []
    rows_corr   = []
    caudales_por_estacion = {}

    for codigo, nombre in DGA_ESTACIONES.items():
        df_caudal = leer_caudal_dga(DGA_MENSUAL_PATH, codigo)
        caud = []
        for año in serie["año"]:
            caud.append((año, caudal_estival_djf(df_caudal, int(año))))
        df_caud = pd.DataFrame(caud, columns=["año", "caudal_djf_m3s"])
        df_caud["codigo_estacion"] = codigo
        df_caud["nombre_estacion"] = nombre
        rows_caudal.append(df_caud)
        caudales_por_estacion[codigo] = df_caud

        # Join área glaciar ~ caudal por año
        joined = serie.merge(df_caud, on="año", how="inner")
        joined = joined.dropna(subset=["caudal_djf_m3s"])

        if len(joined) < 3:
            logging.warning(
                f"  {codigo}: solo {len(joined)} años con caudal — sin correlación")
            continue

        años = joined["año"].values.astype(float)

        # Variables del pipeline a correlacionar. media_movil_km2 suaviza el
        # ruido interanual (nieve transitoria) y se incluye para robustez.
        variables = ["area_total_km2", "delta_largo_plazo_km2", "media_movil_km2"]
        variables = [v for v in variables if v in joined.columns]

        for var in variables:
            glac = joined[var].values.astype(float)

            # Pearson crudo
            r, p = stats.pearsonr(glac, joined["caudal_djf_m3s"].values)
            # Correlación detrended (residuos tras quitar tendencia temporal)
            _, res_glac   = _residuos_detrended(años, glac)
            _, res_caudal = _residuos_detrended(años, joined["caudal_djf_m3s"].values)
            r_det, p_det  = stats.pearsonr(res_glac, res_caudal)

            rows_corr.append({
                "codigo_estacion": codigo,
                "nombre_estacion": nombre,
                "variable":        var,
                "n":               len(joined),
                "año_inicio":      int(años.min()),
                "año_fin":         int(años.max()),
                "r":               round(r, 4),
                "p_valor":         float(p),
                "r_detrended":     round(r_det, 4),
                "p_detrended":     float(p_det),
                "subperiodo":      "completo",
            })
            logging.info(
                f"  {codigo} | {var}: n={len(joined)} r={r:.4f} (p={p:.4f})  "
                f"detrended r={r_det:.4f} (p={p_det:.4f})"
            )

        # ── Robustez: ¿la fuerza del Maipo viene solo del periodo muestreado? ──
        # El estero (05703006) termina en 2004, por lo que su correlación usa
        # solo 1985-2004. Para descartar que la diferencia estero vs Maipo se
        # deba exclusivamente al periodo, se recalcula el r del Maipo restringido
        # a los años donde el estero tiene caudal (mismo subperiodo).
        if codigo == "05704002" and "05703006" in caudales_por_estacion:
            sub_estero = caudales_por_estacion["05703006"]
            años_estero = set(sub_estero.loc[
                sub_estero["caudal_djf_m3s"].notna(), "año"])
            joined_sub = joined[joined["año"].isin(años_estero)]
            if len(joined_sub) >= 3:
                años_sub = joined_sub["año"].values.astype(float)
                for var in variables:
                    glac = joined_sub[var].values.astype(float)
                    r, p = stats.pearsonr(glac, joined_sub["caudal_djf_m3s"].values)
                    _, res_glac   = _residuos_detrended(años_sub, glac)
                    _, res_caudal = _residuos_detrended(
                        años_sub, joined_sub["caudal_djf_m3s"].values)
                    r_det, p_det  = stats.pearsonr(res_glac, res_caudal)
                    rows_corr.append({
                        "codigo_estacion": codigo,
                        "nombre_estacion": nombre,
                        "variable":        var,
                        "n":               len(joined_sub),
                        "año_inicio":      int(años_sub.min()),
                        "año_fin":         int(años_sub.max()),
                        "r":               round(r, 4),
                        "p_valor":         float(p),
                        "r_detrended":     round(r_det, 4),
                        "p_detrended":     float(p_det),
                        "subperiodo":      "solape_estero",
                    })
                    logging.info(
                        f"  {codigo} | {var} [solo años con estero]: "
                        f"n={len(joined_sub)} r={r:.4f} (p={p:.4f})"
                    )

    if rows_caudal:
        pd.concat(rows_caudal, ignore_index=True).to_csv(
            OUT_DIR / "caudal_dga_djf.csv", index=False, encoding="utf-8")
        logging.info("  ✓ caudal_dga_djf.csv")

    if rows_corr:
        pd.DataFrame(rows_corr).to_csv(
            OUT_DIR / "correlacion_pearson.csv", index=False, encoding="utf-8")
        logging.info("  ✓ correlacion_pearson.csv")


# ============================================================================
# GUARDADO DE RESULTADOS
# ============================================================================

def guardar_resultados(series_dict, decadas_dict):
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

    pd.concat(series_all,  ignore_index=True).to_csv(
        OUT_DIR / "serie_temporal_todos.csv",   index=False, encoding='utf-8')
    pd.concat(decadas_all, ignore_index=True).to_csv(
        OUT_DIR / "analisis_decadas_todos.csv", index=False, encoding='utf-8')
    logging.info("  ✓ serie_temporal_todos.csv")
    logging.info("  ✓ analisis_decadas_todos.csv")


# ============================================================================
# MAIN
# ============================================================================

def main():
    slug = parse_glacier_arg()
    configurar_glaciar(slug)

    logging.info("===== ETAPA 3A: CLASIFICACIÓN =====")
    for sensor, dir_ndsi in NDSI_DIRS.items():
        clasificar_carpeta(sensor, dir_ndsi)

    logging.info("===== ETAPA 3B: VECTORIZACIÓN =====")
    gdfs_por_sensor = vectorizar_todos()

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
    correlacion_pearson()
    logging.info("===== PROCESAMIENTO FINALIZADO =====")


if __name__ == "__main__":
    main()