import streamlit as st
import rasterio
from rasterio.enums import Resampling
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import re

# Configuración de la página (debe ir al inicio, pero como esto es un módulo, se llama desde main.py)
# En main.py ya se define set_page_config. Aquí solo aplicamos estilos adicionales si se desea.

def run_ndsi_dashboard():
    # Ocultar el espacio superior con CSS personalizado (opcional)
    st.markdown("""
        <style>
            .reportview-container .main .block-container {
                padding-top: 1rem;
                padding-bottom: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    # Título pequeño, no ocupa mucho espacio
    st.subheader(" Mapa de Nieve/Hielo - Glaciar Echaurren")
    st.caption("Índice NDSI desde Sentinel-2 | Pasa el cursor sobre el mapa para ver valores")

    # Rutas
    BASE_DIR = Path(__file__).resolve().parents[2]
    PROCESSED_DIR = BASE_DIR / "data" / "processed" / "sentinel2"

    @st.cache_data
    def obtener_lista_archivos():
        archivos = list(PROCESSED_DIR.glob("*.tif"))
        if not archivos:
            st.error(f"No se encontraron .tif en {PROCESSED_DIR}")
            st.stop()
        def extraer_año(nombre):
            match = re.search(r'(\d{4})(\d{2})(\d{2})', nombre)
            return int(match.group(1)) if match else None
        pares = []
        for p in archivos:
            año = extraer_año(p.name)
            if año:
                pares.append((año, p))
        pares.sort(key=lambda x: x[0])
        return pares

    @st.cache_data
    def cargar_array_ndsi(ruta_tif, escala=0.5):
        """Devuelve el array 2D de NDSI (con NaN), y las dimensiones originales redimensionadas."""
        with rasterio.open(ruta_tif) as src:
            h_orig, w_orig = src.height, src.width
            h_new = max(1, int(h_orig * escala))
            w_new = max(1, int(w_orig * escala))
            data = src.read(1, out_shape=(h_new, w_new), resampling=Resampling.bilinear)
            nodata = src.nodata if src.nodata is not None else -9999
            data = np.where(data == nodata, np.nan, data)
            return data, h_new, w_new

    pares = obtener_lista_archivos()
    años = [a for a, _ in pares]
    rutas = [r for _, r in pares]

    # Precargar arrays (en lugar de imágenes PIL)
    if "ndsi_arrays" not in st.session_state:
        st.session_state.ndsi_arrays = {}
        with st.spinner("Precargando datos del glaciar (solo la primera vez)..."):
            for año, ruta in pares:
                arr, h, w = cargar_array_ndsi(ruta, escala=0.5)  # escala 0.5 ajustable
                st.session_state.ndsi_arrays[año] = (arr, h, w)

    # --- Layout con dos columnas ---
    col_map, col_controls = st.columns([3, 1])

    with col_controls:
        # Selector arriba de los metadatos
        año_seleccionado = st.select_slider(
            " Selecciona el año",
            options=años,
            value=años[0],
            format_func=str,
            key="ndsi_slider"
        )
        # Obtener datos precalculados
        ndsi_data, h, w = st.session_state.ndsi_arrays[año_seleccionado]

        # Mostrar metadatos
        st.markdown("###  Metadatos")
        st.write(f"**Año:** {año_seleccionado}")
        st.write(f"**Archivo:** `{rutas[años.index(año_seleccionado)].name}`")
        st.write(f"**Dimensiones mostradas:** {w} x {h} px")
        st.markdown("**Interpretación NDSI:**")
        st.markdown("• &nbsp; > 0.4 → nieve/hielo seguro")
        st.markdown("• &nbsp; 0.1 a 0.4 → nieve parcial / sombras")
        st.markdown("• &nbsp; < 0 → sin nieve")
        st.markdown("• &nbsp; NaN → sin datos (máscara)")

    with col_map:
        # Crear gráfico interactivo con Plotly
        # Usamos go.Figure con go.Heatmap o px.imshow. Preferimos px.imshow porque da tooltip automático.
        fig = px.imshow(
            ndsi_data,
            color_continuous_scale='RdYlBu_r',
            zmin=-0.2,
            zmax=1.0,
            aspect='equal',
            origin='upper',
            labels=dict(x="Columna (píxel)", y="Fila (píxel)", color="NDSI")
        )
        # Personalizar el tooltip para que muestre el valor numérico (por defecto lo hace)
        fig.update_traces(
            hovertemplate="NDSI: %{z:.2f}<extra></extra>",
            hoverinfo="z"
        )
        # Ajustar el layout para que ocupe todo el ancho y tenga una colorbar visible
        fig.update_layout(
            coloraxis_colorbar=dict(title="NDSI", thickness=20, len=0.8),
            margin=dict(l=0, r=0, t=0, b=0),
            height=600
        )
        # Mostrar la figura interactiva
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})

    st.caption(f"Datos fuente: `{PROCESSED_DIR}`")