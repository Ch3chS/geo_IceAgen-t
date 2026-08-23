# Directorio outputs/

## Descripción

Cuenta con los resultados del proyecto, organizados **por glaciar** en subcarpetas `outputs/<slug>/` (ej. `echaurren`, `juncal`).

## Estructura del directorio

```
outputs/
├── <slug>/                     # por glaciar (echaurren, juncal, ...)
│   ├── serie_temporal_<sensor>.csv     # área glaciar por año (Landsat/Sentinel-2)
│   ├── analisis_decadas_<sensor>.csv   # mediana/tasa por década por sensor
│   ├── serie_temporal_todos.csv        # ambos sensores concatenados
│   ├── analisis_decadas_todos.csv      # décadas de ambos sensores
│   ├── caudal_dga_djf.csv              # caudal estival DJF por estación DGA
│   ├── correlacion_pearson.csv         # Pearson área~caudal (crudo + detrended)
│   ├── validacion_dga_area.csv         # Etapa 6: discrepancia pipeline − DGA por año
│   ├── validacion_dga_resumen.csv      # Etapa 6: MAE, sesgo, RMSE por sensor
│   ├── snowmelt_djf.csv                # Etapa 5b: variables simuladas DJF
│   ├── correlacion_snowmelt_dga.csv    # Etapa 5b: Pearson simulado~caudal
│   ├── snowmelt_resumen.csv            # Etapa 5b: ELA, balance de masa, SWE
│   └── caudal_dga_djf_snowmelt.csv     # Etapa 5b: caudal DJF usado
└── README.md                  # este archivo
```

Los CSVs son versionados (los rasters pesados quedan excluidos por `.gitignore`).