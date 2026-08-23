# Directorio app/

## Descripción

Contiene la aplicación web (Streamlit) para mostrar el dashboard del proyecto.

## Estructura del directorio

- `main.py` Punto de entrada de Streamlit: sidebar con **selector de glaciar** y navegación entre vistas.
- `pages_/` Vistas del dashboard (nota: el directorio es `pages_`, no `pages`).

## Vistas disponibles

- **Inicio**: descripción y guía del proyecto.
- **NDSI Sentinel-2** / **NDSI Landsat**: mapas del índice NDSI por año con silueta del Inventario DGA.
- **Clasificación**: máscara binaria glaciar vs. roca/suelo (NDSI ≥ 0.4 + DEM ≥ 3 000 m).
- **Polígonos**: mapa interactivo Folium de los polígonos glaciares coloreados por Δ de área.
- **Retroceso**: series temporales por sensor, medianas por década y tasa de retroceso.
- **Correlación DGA**: Pearson (crudo + detrended) entre área glaciar y caudal estival DJF.
- **Balance físico (snowmelt-rs)**: resultados de la simulación de balance de masa (Etapa 5b).
- **Validación DGA**: MAE/sesgo contra el Inventario IPG 2022 y mapa comparativo (Etapa 6).

Todas las vistas leen los resultados de `outputs/<slug>/` del glaciar seleccionado y filtran el Inventario DGA (`data/IPG_2022_v2/`) por el `NOMBRE` del glaciar configurado.