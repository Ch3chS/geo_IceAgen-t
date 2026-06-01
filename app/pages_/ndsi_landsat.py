import streamlit as st
import rasterio
from rasterio.enums import Resampling
import numpy as np
import plotly.express as px
from pathlib import Path
import re

def run_ndsi_landsat():
    """
    Dashboard interactivo para visualizar el índice NDSI calculado
    a partir de imágenes Landsat procesadas del glaciar Echaurren.
    """
    # CSS para reducir el espacio superior (opcional)
    st.markdown("""
        <style>
            .reportview-container .main .block-container {
                padding-top: 1rem;
                padding-bottom: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    # Título y descripción
    st.subheader("Mapa de Nieve/Hielo - Glaciar Echaurren (Landsat)")
    st.caption("Índice NDSI desde Landsat (1985-2026) | Pasa el cursor sobre el mapa para ver valores")

    # Ruta a la carpeta de datos procesados de Landsat
    BASE_DIR = Path(__file__).resolve().parents[2]          # sube dos niveles: dashboards -> app -> raíz
    PROCESSED_DIR = BASE_DIR / "data" / "processed" / "landsat"

    @st.cache_data
    def obtener_lista_archivos():
        """
        Busca todos los archivos landsat_ndsi_*.tif en la carpeta,
        extrae el año de cada uno y devuelve una lista ordenada de (año, ruta).
        """
        archivos = list(PROCESSED_DIR.glob("landsat_ndsi_*.tif"))
        if not archivos:
            st.error(f"No se encontraron archivos Landsat en {PROCESSED_DIR}")
            st.stop()

        def extraer_año(nombre):
            # El nombre tiene formato landsat_ndsi_YYYYMMDD.tif
            match = re.search(r'(\d{8})', nombre)
            if match:
                return int(match.group(1)[:4])   # primeros 4 dígitos = año
            return None

        pares = []
        for p in archivos:
            año = extraer_año(p.name)
            if año:
                pares.append((año, p))
        pares.sort(key=lambda x: x[0])   # ordenar por año ascendente
        return pares

    @st.cache_data
    def cargar_array_ndsi(ruta_tif, escala=0.5):
        """
        Lee el archivo GeoTIFF, lo redimensiona (escala) y reemplaza NoData por NaN.
        Devuelve el array 2D, alto y ancho redimensionados.
        """
        with rasterio.open(ruta_tif) as src:
            h_orig, w_orig = src.height, src.width
            h_new = max(1, int(h_orig * escala))
            w_new = max(1, int(w_orig * escala))
            # Leer la banda 1 con remuestreo bilineal
            data = src.read(1, out_shape=(h_new, w_new), resampling=Resampling.bilinear)
            nodata = src.nodata if src.nodata is not None else -9999
            data = np.where(data == nodata, np.nan, data)
            return data, h_new, w_new

    # Obtener lista de archivos disponibles
    pares = obtener_lista_archivos()
    años = [a for a, _ in pares]
    rutas = [r for _, r in pares]

    # Precargar los arrays en session_state para evitar recargas lentas al mover el slider
    if "ndsi_arrays_landsat" not in st.session_state:
        st.session_state.ndsi_arrays_landsat = {}
        with st.spinner("Precargando datos de Landsat (solo la primera vez)..."):
            for año, ruta in pares:
                arr, h, w = cargar_array_ndsi(ruta, escala=0.5)
                st.session_state.ndsi_arrays_landsat[año] = (arr, h, w)

    # Layout: columna izquierda para el mapa (más ancha), derecha para controles y metadatos
    col_map, col_controls = st.columns([3, 1])

    with col_controls:
        # Selector de año (slider)
        año_seleccionado = st.select_slider(
            "Selecciona el año",
            options=años,
            value=años[0],
            format_func=str,
            key="slider_landsat"
        )
        # Obtener datos precalculados
        ndsi_data, h, w = st.session_state.ndsi_arrays_landsat[año_seleccionado]

        # Mostrar metadatos
        st.markdown("### Metadatos")
        st.write(f"**Año:** {año_seleccionado}")
        st.write(f"**Archivo:** `{rutas[años.index(año_seleccionado)].name}`")
        st.write(f"**Dimensiones mostradas:** {w} x {h} px")
        st.markdown("**Interpretación NDSI:**")
        st.markdown("• &nbsp; > 0.4 → nieve/hielo seguro")
        st.markdown("• &nbsp; 0.1 a 0.4 → nieve parcial / sombras")
        st.markdown("• &nbsp; < 0 → sin nieve")
        st.markdown("• &nbsp; NaN → sin datos (máscara)")

    with col_map:
        # Crear figura interactiva con Plotly (tooltip automático, colorbar)
        fig = px.imshow(
            ndsi_data,
            color_continuous_scale='RdYlBu_r',   # escala rojo-azul invertida (nieve en azul)
            zmin=-0.2,
            zmax=1.0,
            aspect='equal',
            origin='upper',
            labels=dict(x="Columna (píxel)", y="Fila (píxel)", color="NDSI")
        )
        # Personalizar el texto que aparece al pasar el cursor
        fig.update_traces(
            hovertemplate="NDSI: %{z:.2f}<extra></extra>",
            hoverinfo="z"
        )
        # Ajustar el layout: eliminar márgenes, dar altura fija, mejorar la barra de color
        fig.update_layout(
            coloraxis_colorbar=dict(title="NDSI", thickness=20, len=0.8),
            margin=dict(l=0, r=0, t=0, b=0),
            height=600
        )
        # Mostrar el gráfico en Streamlit
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})

    # Pie de página con la ruta de los datos
    st.caption(f"Datos fuente: `{PROCESSED_DIR}`")