# Directorio scripts/

## Descripción

Cuenta con los scripts del pipeline del proyecto. Todos los scripts de cómputo aceptan `--glacier <slug>` (default: `echaurren`) para ejecutarse por glaciar.

## Estructura del directorio

Archivos en este directorio:
- `glacier_config.py` Configuración por glaciar (AOI, CRS, estaciones DGA, umbrales). Es la fuente única de verdad de los glaciares configurados.
- `download_data.py` Descarga de Sentinel-2/Landsat (Planetary Computer STAC), FABDEM y estaciones DGA.
- `process_data.py` Cálculo de NDSI y reproyección al CRS/grid del glaciar.
- `spatial_analysis.py` Clasificación NDSI+DEM, vectorización, series por década y correlación de Pearson con caudal DGA.
- `validar_dga.py` Etapa 6 — validación espacial contra el Inventario DGA (IPG 2022): MAE, sesgo, RMSE.
- `run_snowmelt.py` Etapa 5b (opcional) — balance físico de masa con el motor Rust `snowmelt-rs`.
- `visualize_tif.py` Utilidad para visualizar rasters.
- `utils.py` Funciones auxiliares comunes.

## Orden de ejecución (por glaciar)

```bash
python scripts/download_data.py    --glacier <slug>
python scripts/process_data.py     --glacier <slug>
python scripts/spatial_analysis.py --glacier <slug>
python scripts/validar_dga.py      --glacier <slug> 
python scripts/run_snowmelt.py     --glacier <slug> 
```

`setup.sh` (en la raíz) encadena estas etapas para todos los glaciares configurados y lanza el dashboard.