# Directorio data/

## Descripción

Contiene los datos del proyecto: crudos y procesados **por glaciar**, el Inventario Público de Glaciares (IPG 2022) y el extracto de caudal DGA.

## Estructura del directorio

```
data/
├── IPG_2022_v2/              # Inventario Público de Glaciares (shapefile, versionado)
├── raw/
│   ├── <slug>/               # por glaciar (echaurren, juncal, ...)
│   │   ├── sentinel2/        # bandas B03/B11 de Sentinel-2 (Planetary Computer)
│   │   ├── landsat/          # bandas green/swir16 de Landsat
│   │   └── fabdem/           # DEM FABDEM del AOI del glaciar
│   ├── DGA/                  # extracto de caudal medio mensual por estación (versionado)
│   └── era5/                 # forzante diario (temperatura/precipitación) por glaciar
└── processed/
    └── <slug>/               # por glaciar
        ├── landsat/          # rasters NDSI Landsat
        ├── sentinel2/        # rasters NDSI Sentinel-2
        ├── clasificacion/    # máscaras binarias por sensor
        ├── vectores/         # GeoPackages de polígonos glaciares
        └── snowmelt/         # DEM en ESRI ASCII y salidas del motor snowmelt-rs
```

Nota: los rasters y CSVs pesados (Landsat/Sentinel-2/FABDEM/ERA5 y `data/processed`) están excluidos por `.gitignore`; solo se versionan el shapefile `IPG_2022_v2/` y el extracto `raw/DGA/caudal_medio_mensual_estaciones.csv`.