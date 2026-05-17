import streamlit as st

# Configurar página (título, ícono, layout)
st.set_page_config(page_title="IceAgen't", layout="wide")

# Sidebar con opciones
st.sidebar.title("Navegación")
opcion = st.sidebar.radio(
    "Elige un dashboard:",
    ("Inicio", "NDSI Sentinel-2", "NDSI Landsat")
)

# Mostrar el dashboard seleccionado
if opcion == "Inicio":
    st.markdown("""
    # Bienvenido al hub de dashboards de IceAgen't
    
    Utiliza el menu lateral para acceder a los diferentes dashboards.
    
    - **NDSI Sentinel-2**: Visualizacion del indice NDSI a partir de imagenes Sentinel-2 procesadas (2016-2024).
    - **NDSI Landsat**: Visualizacion del indice NDSI a partir de imagenes Landsat procesadas (1985-2026).
    """)

elif opcion == "NDSI Sentinel-2":
    from pages.ndsi_sentinel import run_ndsi_sentinel
    run_ndsi_sentinel()
elif opcion == "NDSI Landsat":
    from pages.ndsi_landsat import run_ndsi_landsat
    run_ndsi_landsat()
else:
    st.info("Próximamente: nuevos dashboards para análisis glaciar.")

