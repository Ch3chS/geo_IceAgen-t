# geo_IceAgen-t — contexto para el agente

## Idioma
Responde y comenta el código en español.

## Qué es este proyecto
Proyecto que cuantifica el retroceso del glaciar **Echaurren Norte** 
(cuenca del Río Yeso/Maipo, Chile central) entre 1985 y 2026 usando 
Landsat y Sentinel-2, y evalúa su correlación con el caudal de estaciones de la DGA.

## Pipeline (orden de ejecución)
```
scripts/download_data.py:   descarga Sentinel-2/Landsat (Planetary Computer STAC),
                            FABDEM y caudal DGA
scripts/process_data.py:    calcula NDSI, reproyecta todo a EPSG:32719/30m para
                            alinear Landsat y Sentinel-2 al mismo grid
scripts/spatial_analysis.py:clasificación binaria (NDSI≥0.4 + DEM≥3000m) →
                            vectorización → series temporales por década →
                            correlación de Pearson con caudal DGA
app/main.py + app/pages_/:  dashboard Streamlit (6 vistas)
```
`setup.sh` encadena todo el pipeline y lanza el dashboard.

## Convención de coordenadas / CRS (tal como está en el código, no mezclar sin reproyectar explícitamente)
El proyecto **no usa PostGIS**: trabaja con rasteres GeoTIFF y vectores
GeoPackage sobre el sistema de archivos (la dockerización tampoco lo incluye,
ver `docker/README.md`). Se manejan dos sistemas de referencia distintos, cada
uno en su etapa:

- `scripts/download_data.py`: bounding box en **WGS84, orden (lon, lat)**
  (convención STAC/GeoJSON) — ej. `AOI = (-70.15, -33.60, -70.11, -33.56)`.
- `scripts/process_data.py` y `scripts/spatial_analysis.py`: todo el
  procesamiento (recorte, reproyección, clasificación, vectorización) trabaja
  en **EPSG:32719 (UTM 19S), metros**, resolución fija 30 m — ej.
  `AOI_BOUNDS = (393150, 6282300, 396200, 6285350)`.
- `app/pages_/*.py`: leen los rasters/vectores ya en EPSG:32719 y reproyectan
  el shapefile del Inventario DGA (`data/IPG_2022_v2/`) sobre la marcha para
  superponerlo.

Si agregas código nuevo que maneje coordenadas, deja explícito en qué CRS y
orden de ejes está trabajando (no asumas lat/lon por defecto).

## Tests
Hay un test en `tests/` que cubre las funciones puras de `scripts/process_data.py` y
`scripts/spatial_analysis.py` (NDSI, clasificación NDSI+DEM, series
temporales por década, lectura y agregación de caudal DGA, regex de
agrupación de escenas). No cubre las funciones que leen/escriben rasters de
disco (`recortar_y_remuestrear_banda`, `clasificar_raster`,
`vectorizar_raster`) ni las páginas de `app/`.

No modifiques los tests existentes (son el contrato). Antes de dar por
terminada una tarea, corre `pytest` desde la raíz del repo y reporta el
resultado real.

## Cosas a tener presente al modificar código
- El AOI está hardcodeado por separado en `download_data.py` (WGS84 lon/lat) y
  en `process_data.py`/`spatial_analysis.py` (UTM metros).
- Datos pesados (rasters Landsat/Sentinel-2/FABDEM, CSVs nacionales de DGA)
  se generan/descargan localmente y están excluidos por `.gitignore`. Solo se
  versionan el shapefile `data/IPG_2022_v2/` (~83 MB) y un extracto reducido
  de caudal DGA (`data/raw/DGA/caudal_medio_mensual_estaciones.csv`, 2
  estaciones).
