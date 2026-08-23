import sys
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scripts.glacier_config import GLACIER_CONFIGS, get_config  # noqa: E402

st.set_page_config(page_title="IceAgen't", layout="wide")

st.sidebar.title("Navegación")

glaciar_slug = st.sidebar.selectbox(
    "Glaciar",
    list(GLACIER_CONFIGS.keys()),
    format_func=lambda s: GLACIER_CONFIGS[s].nombre,
    key="glaciar_seleccionado",
)
glaciar = get_config(glaciar_slug)

# Red de seguridad: al cambiar de glaciar, limpiar caché y arrays del NDSI.
# st.cache_data no considera las variables del closure en la clave de caché,
# por lo que las funciones cacheadas sin argumentos del glaciar podrían
# devolver datos del glaciar anterior.
if "glaciar_previo" not in st.session_state:
    st.session_state.glaciar_previo = glaciar_slug
elif st.session_state.glaciar_previo != glaciar_slug:
    st.cache_data.clear()
    for k in list(st.session_state.keys()):
        if k.startswith("ndsi_arrays_"):
            del st.session_state[k]
    st.session_state.glaciar_previo = glaciar_slug

opcion = st.sidebar.radio(
    "Elige un dashboard:",
    ("Inicio", "NDSI Sentinel-2", "NDSI Landsat",
     "Clasificación", "Polígonos", "Retroceso", "Correlación DGA",
     "Balance físico (snowmelt-rs)", "Validación DGA")
)

if opcion == "Inicio":
    st.markdown(f"""
    # Bienvenido al hub de dashboards de IceAgen't

    **Glaciar activo: {glaciar.nombre}** (slug `{glaciar.slug}`)

    Utiliza el menú lateral para acceder a los diferentes dashboards.

    - **NDSI Sentinel-2**: Visualización del índice NDSI a partir de imágenes
      Sentinel-2 procesadas (2016–2024).
    - **NDSI Landsat**: Visualización del índice NDSI a partir de imágenes
      Landsat procesadas (1985–2026).
    - **Clasificación**: Máscara binaria glaciar vs. roca/suelo con umbral
      NDSI ≥ 0.4 y filtro altitudinal FABDEM ≥ 3 000 m s.n.m.
      Los parches menores a 5 000 m² son descartados como artefactos de borde.
    - **Polígonos**: Mapa interactivo de los polígonos glaciares vectorizados,
      coloreados por delta acumulado (paleta divergente RdBu). Permite filtrar
      por sensor y rango de años.
    - **Retroceso**: Series temporales independientes por sensor (Landsat y
      Sentinel-2) con delta acumulado, mediana por década y tasa de retroceso.
      Los resultados se leen de los CSVs generados por `spatial_analysis.py`.
    - **Correlación DGA**: Correlación de Pearson entre el área glaciar del
      pipeline y el caudal estival (DJF) de las estaciones DGA de la cuenca del
      glaciar, con control de tendencia (r detrended).
    - **Balance físico (snowmelt-rs)**: Segunda línea de evidencia
      independiente — simula el balance de masa nival/glaciar con un modelo
      físico (motor Rust `snowmelt-rs`) sobre el DEM y compara el
      derretimiento/escorrentía simulados contra el caudal DGA, junto con la
      altitud de la línea de equilibrio (ELA) estimada.
    - **Validación DGA**: MAE de área y sesgo sistemático por sensor/año
      contra el Inventario Público de Glaciares (IPG 2022), con mapa
      comparativo de polígonos (DGA vs pipeline) y métricas de solape
      espacial (IoU, omisión, comisión).
    """)

elif opcion == "NDSI Sentinel-2":
    from pages_.ndsi_sentinel import run_ndsi_sentinel
    run_ndsi_sentinel(glaciar)

elif opcion == "NDSI Landsat":
    from pages_.ndsi_landsat import run_ndsi_landsat
    run_ndsi_landsat(glaciar)

elif opcion == "Clasificación":
    from pages_.clasificacion import run_clasificacion
    run_clasificacion(glaciar)

elif opcion == "Polígonos":
    from pages_.poligonos import run_poligonos
    run_poligonos(glaciar)

elif opcion == "Retroceso":
    from pages_.retroceso import run_retroceso
    run_retroceso(glaciar)

elif opcion == "Correlación DGA":
    from pages_.correlacion import run_correlacion
    run_correlacion(glaciar)

elif opcion == "Balance físico (snowmelt-rs)":
    from pages_.snowmelt import run_snowmelt
    run_snowmelt(glaciar)

elif opcion == "Validación DGA":
    from pages_.validacion_dga import run_validacion_dga
    run_validacion_dga()

else:
    st.info("Próximamente: nuevos dashboards para análisis glaciar.")