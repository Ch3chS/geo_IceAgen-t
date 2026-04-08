# 🧊 geo_IceAgen-t

[![Licencia MIT](https://img.shields.io/badge/Licencia-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Geoespacial](https://img.shields.io/badge/Geoespacial-Desafío%205-green)](https://github.com/)

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

## Estructura del repositorio

Los directorios se explican mejor en READMEs dentro de cada directorio. Pero en resumen:

- `code/` Contiene todos los archivos de código.
- `document/` Contiene todo lo relacionado al informe correspondiente.
- `LICENSE` y `README.md` en la raíz.

## Instalación

### 1. Clona el repositorio con
```bash
git clone git@github.com:Ch3chS/geo_IceAgen-t.git
```
### 2. Entra a la carpeta del código:

```bash
cd geo_IceAgen-t/code
```
### 3. Crea un entorno virtual:
```bash
python -m venv geo_env
```
### 4. Entra al entorno virtual:
```bash
source ./geo_env/bin/activate
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