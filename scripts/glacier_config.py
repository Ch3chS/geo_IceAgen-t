#!/usr/bin/env python3
"""
Configuración por glaciar para el pipeline geo_IceAgen't.

Cada glaciar define su propia área de estudio (bbox WGS84 para la descarga y
AOI UTM para el procesamiento), CRS, estaciones DGA y umbrales de
clasificación. Los scripts leen la configuración vía `get_config(slug)`,
seleccionada con `--glacier <slug>` desde la CLI.

Convención de coordenadas (no mezclar sin reproyectar explícitamente):
  - `bbox_wgs84`: orden (lon, lat) — convención STAC/GeoJSON, para
    `scripts/download_data.py`.
  - `aoi_bounds_utm`: orden (minx, miny, maxx, maxy) en metros en el CRS
    indicado por `crs_epsg`, para `scripts/process_data.py` y
    `scripts/spatial_analysis.py`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GlaciarConfig:
    slug: str                 # identificador corto (carpetas y salidas)
    nombre: str               # nombre para el dashboard
    bbox_wgs84: tuple         # (min_lon, min_lat, max_lon, max_lat)
    aoi_bounds_utm: tuple     # (minx, miny, maxx, maxy) en metros
    crs_epsg: int             # EPSG del UTM de trabajo (ej. 32719 = UTM 19S)
    dga_estaciones: dict      # {codigo: nombre} — codigo leído como texto
    nombre_dga: str           # patrón NOMBRE en el shapefile IPG (case-insensitive)
    umbral_ndsi: float = 0.4
    elev_min_m: float = 3000.0
    area_min_m2: float = 5000.0
    resolucion_m: int = 30


GLACIER_CONFIGS = {
    "echaurren": GlaciarConfig(
        slug="echaurren",
        nombre="Glaciar Echaurren Norte",
        bbox_wgs84=(-70.15, -33.60, -70.11, -33.56),
        aoi_bounds_utm=(393150, 6282300, 396200, 6285350),
        crs_epsg=32719,
        dga_estaciones={
            "05703006": "Estero Glaciar Echaurren Norte",
            "05704002": "Río Maipo en San Alfonso",
        },
        nombre_dga="Echaurren Norte",
    ),
    "juncal": GlaciarConfig(
        slug="juncal",
        nombre="Glaciar Juncal Norte",
        bbox_wgs84=(-70.1331, -33.0652, -70.0649, -32.9675),
        aoi_bounds_utm=(394228.4, 6340974.3, 400482.0, 6351745.5),
        crs_epsg=32719,
        dga_estaciones={
            "05403002": "Río Aconcagua en Río Blanco",
            "05410002": "Río Aconcagua en Chacabuquito",
        },
        nombre_dga="JUNCAL NORTE",
    ),
}

DEFAULT_GLACIAR = "echaurren"


def get_config(slug=None):
    """Devuelve la config del glaciar `slug` (default: echaurren)."""
    slug = slug or DEFAULT_GLACIAR
    if slug not in GLACIER_CONFIGS:
        raise KeyError(
            f"Glaciar '{slug}' no está configurado. "
            f"Disponibles: {', '.join(GLACIER_CONFIGS)}"
        )
    return GLACIER_CONFIGS[slug]


def parse_glacier_arg(argv=None):
    """Lee `--glacier <slug>` de argv sin interferir con otros flags."""
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--glacier", default=DEFAULT_GLACIAR,
        help=f"Slug del glaciar (disponibles: {', '.join(GLACIER_CONFIGS)}). "
             f"Default: {DEFAULT_GLACIAR}"
    )
    args, _ = parser.parse_known_args(argv)
    return args.glacier