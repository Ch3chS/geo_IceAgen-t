# 🧊 geo_IceAgen-t

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-yellow.svg)](https://www.python.org/)
[![Geoespacial](https://img.shields.io/badge/Geoespacial-Desafío%205-red)](https://github.com/)

## Datos generales

- **Ice_Agen't** corresponde a un juego de palabras entre **Ice Age**, **Ice ain't** y **Ice Agent**.
- **Desarrollado por**: Grupo 1 – Curso Geoinformática, USACH, 2026.
- **Profesor**: Francisco Parra O.

## Descripción

**geo_IceAgen't** cuantifica el retroceso de un glaciar andino de Chile central (Juncal, Olivares o Echaurren) en los últimos 40 años mediante imágenes Landsat, y estima su contribución al caudal estival de la cuenca receptora. El proyecto integra teledetección, SIG, hidrología y análisis multitemporal.

Este repositorio corresponde al **Desafío 5** del curso *Geoinformática* (Universidad de Santiago de Chile, Semestre 1-2026). Su objetivo es generar evidencia cuantitativa sobre la pérdida de la reserva hídrica estratégica para Chile central.

## Características

- Clasificación de cobertura glaciar vs. roca/suelo usando **NDSI** y band ratios.
- Cálculo de área frontal por década y tasa de retroceso.
- Correlación con datos de caudal de la DGA (HIDROlinea).
- Estimación de la contribución glaciar al caudal estival.
- Comparación con el Inventario Nacional de Glaciares (DGA).
- Proyección simplificada de escenarios futuros.

## Stack tecnológico

| Herramienta       | Uso                                      |
|-------------------|------------------------------------------|
| Python 3.10+      | Lenguaje principal                       |
| GeoPandas         | Manejo de datos vectoriales              |
| Rasterio / Xarray | Procesamiento de imágenes satelitales    |
| Matplotlib        | Gráficos y mapas estáticos               |
| Folium            | Mapas interactivos                       |
| Contextily        | Mapas base en tiles                      |
| Jupyter Notebook  | Desarrollo interactivo y documentado     |
| Docker            | Para aislar el entorno                   |

## Estructura del repositorio

Los directorios se explican mejor en READMEs dentro de cada directorio. Pero en resumen:

- `app/` Contiene la aplicación web para mostrar el dashboard.
- `data/` Contiene los datos a utilizar, ya sea crudos, procesados o de fuentes externas.
- `docker/` Cuenta con las imagenes y scripts de la dockerización.
- `outputs/` Cuenta con los resultados del proyecto.
- `scripts/` Cuenta con los scripts de apoyo para el proyecto.

Archivos en este directorio:
- `.gitignore` Excluye los archivos pesados como rasteres etc.
- `docker-compose.yml` Orquesta los contenedores.
- `README.md` Describe el proyecto (es este archivo).
- `requirements.txt` Dependencias para ejecutar el proyecto.
- `setup.sh` Automatiza la ejecución del proyecto.


## Instalación para desarrollo

### 1. Clona el repositorio con
```bash
git clone git@github.com:Ch3chS/geo_IceAgen-t.git
```
### 2. Entra a la carpeta del código:

```bash
cd geo_IceAgen-t
```
### 3. Crea un entorno virtual:
```bash
python -m venv .env
```
### 4. Entra al entorno virtual:
```bash
source ./.env/bin/activate
```
### 5. Instala las dependencias:
```bash
pip install -r requirements.txt
```

## Resultados esperados

- Mapas de extensión glaciar por década (1985–2025)
- Gráfico de retroceso.
- Análisis de correlación glaciar-caudal.
- Proyección simplificada.

## Licencia

Este proyecto está bajo dos licencias:

- **Código fuente**: [MIT License](LICENSE) – libertad total con atribución.
- **Mapas, gráficos e informe**: [Creative Commons BY 4.0](https://creativecommons.org/licenses/by/4.0/) – se permite compartir y adaptar con crédito.

---

*“El hielo se va, pero nosotros permaneceremos. Debemos cuidar nuestros recursos hídricos”*