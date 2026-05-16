import streamlit as st
import rasterio
from rasterio.enums import Resampling
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from pathlib import Path
import re
from PIL import Image

def run_ndsi_dashboard():
    st.header("Mapa de Nieve/Hielo - Glaciar Echaurren")
    st.markdown("Visualización del índice NDSI calculado desde Sentinel-2")

    # Configuración de rutas (asumiendo que este archivo está en app/dashboards/)
    BASE_DIR = Path(__file__).resolve().parents[2]  # sube dos niveles: dashboards -> app -> raíz
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
    def raster_a_rgb(ruta_tif, escala=0.5, vmin=-0.2, vmax=1.0):
        with rasterio.open(ruta_tif) as src:
            h_orig, w_orig = src.height, src.width
            h_new = max(1, int(h_orig * escala))
            w_new = max(1, int(w_orig * escala))
            
            data = src.read(1, out_shape=(h_new, w_new), resampling=Resampling.bilinear)
            nodata = src.nodata if src.nodata is not None else -9999
            data = np.where(data == nodata, np.nan, data)
            
            norm = Normalize(vmin=vmin, vmax=vmax)
            cmap = plt.cm.terrain
            cmap.set_bad(color='lightgray')
            rgba = cmap(norm(data))
            rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
            return Image.fromarray(rgb), w_new, h_new, ruta_tif.name

    pares = obtener_lista_archivos()
    años = [a for a, _ in pares]
    rutas = [r for _, r in pares]

    # Precalentar imágenes en session_state (solo para este dashboard)
    if "ndsi_imagenes" not in st.session_state:
        st.session_state.ndsi_imagenes = {}
        with st.spinner("Precargando imágenes del glaciar... (solo la primera vez)"):
            for año, ruta in pares:
                img, w, h, nombre = raster_a_rgb(ruta, escala=0.5)
                st.session_state.ndsi_imagenes[año] = (img, w, h, nombre)

    año_seleccionado = st.select_slider("Selecciona el año", options=años, value=años[0], format_func=str)
    img, w, h, nombre = st.session_state.ndsi_imagenes[año_seleccionado]

    col1, col2 = st.columns([3, 1])
    with col1:
        st.image(img, caption=f"NDSI - Año {año_seleccionado}", use_container_width=True)
    with col2:
        st.markdown("### 📋 Metadatos")
        st.write(f"**Año:** {año_seleccionado}")
        st.write(f"**Archivo:** `{nombre}`")
        st.write(f"**Dimensiones mostradas:** {w} x {h} px")
        st.write("**Interpretación NDSI:**")
        st.write("- > 0.4 → nieve/hielo seguro")
        st.write("- 0.1 a 0.4 → nieve parcial / sombras")
        st.write("- < 0 → sin nieve")

    st.caption(f"Datos: `{PROCESSED_DIR}`")