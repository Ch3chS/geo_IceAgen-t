# 🧊 geo_IceAgen-t

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-yellow.svg)](https://www.python.org/)
[![Geoespacial](https://img.shields.io/badge/Geoespacial-Desafío%205-red)](https://github.com/)

## Datos generales

- **Ice_Agen't** corresponde a un juego de palabras entre **Ice Age**, **Ice ain't** y **Ice Agent**.
- **Desarrollado por**: Grupo 1 – Curso Geoinformática, USACH, 2026.
- **Profesor**: Francisco Parra O.

## Descripción

**geo_IceAgen't** cuantifica el retroceso de glaciares andinos de Chile central en los últimos ~40 años mediante imágenes Landsat y Sentinel-2, y estima su contribución al caudal estival de la cuenca receptora. El proyecto integra teledetección, SIG, hidrología y análisis multitemporal.

El proyecto es **multi-glaciar**: cada glaciar se define en una configuración (`scripts/glacier_config.py`) y el pipeline se ejecuta por glaciar con el flag `--glacier <slug>`. Actualmente están configurados:

- **Echaurren Norte** (slug `echaurren`) — cuenca del Río Yeso/Maipo, estaciones DGA del Maipo.
- **Juncal Norte** (slug `juncal`) — cuenca del Río Aconcagua, estaciones DGA de Aconcagua.

Este repositorio corresponde al **Desafío 5** del curso *Geoinformática* (Universidad de Santiago de Chile, Semestre 1-2026). Su objetivo es generar evidencia cuantitativa sobre la pérdida de la reserva hídrica estratégica para Chile central.

## Características

- **Soporte multi-glaciar por configuración**: cada glaciar define su AOI, CRS, estaciones DGA y umbrales; el dashboard permite elegir el glaciar.
- **Clasificación de cobertura glaciar vs. roca/suelo** usando **NDSI** (≥ 0.4) + filtro altitudinal FABDEM (≥ 3 000 m s.n.m.).
- **Cálculo de área por década y tasa de retroceso** (series temporales independientes por sensor, mediana robusta por quintiles y tendencia lineal).
- **Correlación con caudal de la DGA** (Pearson crudo + detrended sobre el verano hidrológico DJF).
- **Balance físico de masa** (Etapa 5b, `snowmelt-rs`): simula el derretimiento nival/glaciar sobre el DEM y lo correlaciona con el caudal DGA.
- **Validación contra el Inventario Público de Glaciares** (Etapa 6): MAE, sesgo sistemático y RMSE del área del pipeline frente al snapshot IPG 2022, con mapa comparativo (IoU, omisión, comisión).

## Pipeline

```
scripts/download_data.py:    descarga Sentinel-2/Landsat (Planetary Computer STAC),
                             FABDEM y prepara las estaciones DGA
scripts/process_data.py:     calcula NDSI, reproyecta todo al CRS/grid del glaciar
scripts/spatial_analysis.py: clasificación NDSI+DEM → vectorización → series por década
                             → correlación de Pearson con caudal DGA
scripts/validar_dga.py:      Etapa 6 — validación espacial contra el Inventario DGA (IPG 2022)
scripts/run_snowmelt.py:     Etapa 5b (opcional) — balance físico con el motor Rust snowmelt-rs
```

Todos los scripts aceptan `--glacier <slug>` (default: `echaurren`). Las salidas se organizan por glaciar:

- Datos crudos: `data/raw/<slug>/...`
- Datos procesados: `data/processed/<slug>/...`
- Resultados (CSVs): `outputs/<slug>/...`

## Stack tecnológico

| Herramienta       | Uso                                      |
|-------------------|------------------------------------------|
| Python 3.10+      | Lenguaje principal                       |
| GeoPandas         | Manejo de datos vectoriales              |
| Rasterio           | Procesamiento de imágenes satelitales    |
| Matplotlib        | Gráficos y mapas estáticos               |
| Folium            | Mapas interactivos                       |
| Contextily        | Mapas base en tiles                      |
| Plotly / Streamlit| Dashboard interactivo                    |
| Rust (snowmelt-rs)| Motor de balance de masa físico (Etapa 5b) |
| Pytest            | Tests de las funciones puras             |

## Estructura del repositorio

Los directorios se explican mejor en READMEs dentro de cada directorio. Pero en resumen:

- `app/` Contiene la aplicación web (Streamlit) para mostrar el dashboard, con selector de glaciar.
- `data/` Contiene los datos: crudos/procesados por glaciar, el Inventario IPG 2022 y el extracto DGA.
- `docker/` Documentación de dockerización (PostGIS mencionado pero **no implementado**; `docker-compose.yml` está vacío).
- `outputs/` Cuenta con los resultados por glaciar (`outputs/<slug>/`).
- `scripts/` Cuenta con los scripts del pipeline.
- `snowmelt-rs/` Submódulo Rust con el motor de balance de masa físico.
- `tests/` Tests de las funciones puras de los scripts.

Archivos en este directorio:
- `.gitignore` Excluye los archivos pesados como rasteres etc.
- `docker-compose.yml` Orquesta los contenedores (vacío — no usado).
- `README.md` Describe el proyecto (es este archivo).
- `requirements.txt` Dependencias para ejecutar el proyecto.
- `setup.sh` Automatiza la ejecución del pipeline y el dashboard.

## Instalación y ejecución automática (recomendada)

El proyecto incluye un script `setup.sh` que orquesta todo el flujo de principio a fin, solo copia y pega lo siguiente (en linux):

```bash
git clone git@github.com:Ch3chS/geo_IceAgen-t.git
cd geo_IceAgen-t
git submodule update --init --recursive    # trae el motor snowmelt-rs
chmod +x setup.sh
./setup.sh
```

`setup.sh` crea el entorno, instala dependencias, corre el pipeline para **todos los glaciares** configurados en `scripts/glacier_config.py` (descarga → NDSI → clasificación → series → validación DGA) y, si `cargo` está disponible, compila y corre la Etapa 5b (snowmelt). Al final lanza el dashboard.

## Instalación para desarrollo (manual)

### 1. Clona el repositorio con
```bash
git clone git@github.com:Ch3chS/geo_IceAgen-t.git
```
### 2. Entra a la carpeta del código:
```bash
cd geo_IceAgen-t
```
### 3. Trae el submódulo (motor snowmelt-rs):
```bash
git submodule update --init --recursive
```
### 4. Crea un entorno virtual:
```bash
python -m venv .env
```
### 5. Entra al entorno virtual:
```bash
source ./.env/bin/activate
```
### 6. Instala las dependencias:
```bash
pip install -r requirements.txt
```

### 7. Pipeline por glaciar
Para cada glaciar (default: `echaurren`; también `juncal`):

```bash
python scripts/download_data.py    --glacier <slug>
python scripts/process_data.py     --glacier <slug>
python scripts/spatial_analysis.py --glacier <slug>
python scripts/validar_dga.py      --glacier <slug>  
python scripts/run_snowmelt.py     --glacier <slug> 
```

### 8. Desarrolla y testea
ya sea creación de archivos nuevos, depuración etc... Los tests cubren las funciones puras:

```bash
pytest
```

### 9. Verifica el funcionamiento de la aplicación central
Antes de hacer tu push ejecuta:
```bash
streamlit run ./app/main.py
```
desde la raiz del proyecto. En el sidebar elige el glaciar y la vista.

## Resultados esperados

- Mapas de extensión glaciar por década (1985–2025).
- Gráfico de retroceso y tasa por década.
- Análisis de correlación glaciar-caudal (DGA).
- Balance físico de masa simulado (snowmelt-rs).
- Validación del área del pipeline contra el Inventario DGA (MAE, sesgo, IoU).

*“El hielo se va, pero nosotros permaneceremos. Debemos cuidar nuestros recursos hídricos”*