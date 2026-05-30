import streamlit as st

# Configurar página (título, ícono, layout)
st.set_page_config(page_title="IceAgen't", layout="wide")

# Sidebar con opciones
st.sidebar.title("Navegación")
opcion = st.sidebar.radio(
    "Elige un dashboard:",
    ("Inicio", "NDSI Sentinel-2", "NDSI Landsat", "Clasificación", "Retroceso")
)

# Mostrar el dashboard seleccionado
if opcion == "Inicio":
    st.markdown("""
    # Bienvenido al hub de dashboards de IceAgen't
    
    Utiliza el menu lateral para acceder a los diferentes dashboards.
    
    - **NDSI Sentinel-2**: Visualizacion del indice NDSI a partir de imagenes Sentinel-2 procesadas (2016-2024).
    - **NDSI Landsat**: Visualizacion del indice NDSI a partir de imagenes Landsat procesadas (1985-2026).
    - **Clasificación**: Mascara binaria glaciar vs. roca/suelo (umbral NDSI 0.4) para Landsat y Sentinel-2.
    - **Retroceso**: Area glaciar por decada, tasa de retroceso y grafico de retroceso.
    """)

elif opcion == "NDSI Sentinel-2":
    from pages.ndsi_sentinel import run_ndsi_sentinel
    run_ndsi_sentinel()
elif opcion == "NDSI Landsat":
    from pages.ndsi_landsat import run_ndsi_landsat
    run_ndsi_landsat()
elif opcion == "Clasificación":
    from pages.clasificacion import run_clasificacion
    run_clasificacion()
elif opcion == "Retroceso":
    from pages.retroceso import run_retroceso
    run_retroceso()
else:
    st.info("Próximamente: nuevos dashboards para análisis glaciar.")

