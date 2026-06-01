import streamlit as st

st.set_page_config(page_title="IceAgen't", layout="wide")

st.sidebar.title("Navegación")
opcion = st.sidebar.radio(
    "Elige un dashboard:",
    ("Inicio", "NDSI Sentinel-2", "NDSI Landsat",
     "Clasificación", "Polígonos", "Retroceso")
)

if opcion == "Inicio":
    st.markdown("""
    # Bienvenido al hub de dashboards de IceAgen't

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
      Los resultados se leen de los CSVs generados por `analyze_glacier.py`.
    """)

elif opcion == "NDSI Sentinel-2":
    from pages_.ndsi_sentinel import run_ndsi_sentinel
    run_ndsi_sentinel()

elif opcion == "NDSI Landsat":
    from pages_.ndsi_landsat import run_ndsi_landsat
    run_ndsi_landsat()

elif opcion == "Clasificación":
    from pages_.clasificacion import run_clasificacion
    run_clasificacion()

elif opcion == "Polígonos":
    from pages_.poligonos import run_poligonos
    run_poligonos()

elif opcion == "Retroceso":
    from pages_.retroceso import run_retroceso
    run_retroceso()

else:
    st.info("Próximamente: nuevos dashboards para análisis glaciar.")