import streamlit as st

# Configurar página (título, ícono, layout)
st.set_page_config(page_title="IceAgen't", layout="wide")

# Sidebar con opciones
st.sidebar.title("Navegación")
opcion = st.sidebar.radio(
    "Elige un dashboard:",
    ("Inicio", "NDSI Glaciar Echaurren", "Otro dashboard (próximamente)")
)

# Mostrar el dashboard seleccionado
if opcion == "Inicio":
    st.markdown("""
    # Bienvenido al hub de dashboards de IceAgen't
    
    Utiliza el menú lateral para acceder a los diferentes dashboards disponibles.
    
    - **NDSI Glaciar Echaurren**: Visualización del índice NDSI a partir de imágenes Sentinel-2 procesadas.
    - (Más dashboards se irán agregando)
    """)
elif opcion == "NDSI Glaciar Echaurren":
    # Importar y ejecutar el dashboard NDSI
    from dashboards.ndsi_dashboard import run_ndsi_dashboard
    run_ndsi_dashboard()
else:
    st.info("Próximamente: nuevos dashboards para análisis glaciar.")