import streamlit as st
import rasterio
import numpy as np
import plotly.express as px
from pathlib import Path
import re


def run_clasificacion():
    """
    Dashboard del PUNTO 2: muestra la clasificación binaria glaciar vs. roca/suelo
    obtenida al umbralizar el NDSI (>= 0.4) en scripts/spatial_analysis.py.
    """
    st.markdown("""
        <style>
            .reportview-container .main .block-container {
                padding-top: 1rem;
                padding-bottom: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    st.subheader("Clasificación glaciar vs. roca/suelo - Glaciar Echaurren")
    st.caption("Punto 2 | Máscara binaria a partir del NDSI (umbral ≥ 0.4) | "
               "Pasa el cursor sobre el mapa para ver la clase")

    BASE_DIR = Path(__file__).resolve().parents[2]
    CLAS_DIR = BASE_DIR / "data" / "processed" / "clasificacion"

    @st.cache_data
    def obtener_lista_archivos(dir_sensor_str):
        dir_sensor = Path(dir_sensor_str)
        archivos = list(dir_sensor.glob("*.tif"))
        if not archivos:
            st.error(f"No se encontraron clasificaciones en {dir_sensor}")
            st.stop()

        def extraer_año(nombre):
            match = re.search(r'(\d{4})\d{2}\d{2}', nombre)
            return int(match.group(1)) if match else None

        pares = []
        for p in archivos:
            año = extraer_año(p.name)
            if año:
                pares.append((año, p))
        pares.sort(key=lambda x: x[0])
        return pares

    @st.cache_data
    def cargar_array_clasif(ruta_str):
        """Lee la máscara binaria (uint8) y reemplaza NoData (255) por NaN."""
        with rasterio.open(ruta_str) as src:
            data = src.read(1).astype(float)
        data[data == 255] = np.nan
        return data

    col_map, col_controls = st.columns([3, 1])

    with col_controls:
        sensor = st.radio("Sensor", ("Landsat", "Sentinel-2"), key="clasif_sensor")
        subdir = "landsat" if sensor == "Landsat" else "sentinel2"

        pares = obtener_lista_archivos(str(CLAS_DIR / subdir))
        años = [a for a, _ in pares]
        rutas = [r for _, r in pares]

        año_seleccionado = st.select_slider(
            "Selecciona el año",
            options=años,
            value=años[0],
            format_func=str,
            key="clasif_slider"
        )
        ruta = rutas[años.index(año_seleccionado)]
        clasif = cargar_array_clasif(str(ruta))

        px_glaciar = int(np.nansum(clasif == 1))
        px_validos = int(np.sum(~np.isnan(clasif)))

        st.markdown("### Metadatos")
        st.write(f"**Sensor:** {sensor}")
        st.write(f"**Año:** {año_seleccionado}")
        st.write(f"**Archivo:** `{ruta.name}`")
        st.write(f"**Píxeles glaciar:** {px_glaciar} / {px_validos}")
        st.markdown("**Clases:**")
        st.markdown("• &nbsp; 🔵 1 → glaciar (NDSI ≥ 0.4)")
        st.markdown("• &nbsp; 🟤 0 → roca / suelo")

    with col_map:
        fig = px.imshow(
            clasif,
            color_continuous_scale=[[0.0, '#8c6d4f'], [1.0, '#1f6fe0']],
            zmin=0, zmax=1,
            aspect='equal',
            origin='upper',
            labels=dict(x="Columna (píxel)", y="Fila (píxel)", color="Clase")
        )
        fig.update_traces(hovertemplate="Clase: %{z:.0f}<extra></extra>")
        fig.update_layout(
            coloraxis_colorbar=dict(
                title="Clase", thickness=20, len=0.8,
                tickvals=[0, 1], ticktext=["roca/suelo", "glaciar"]
            ),
            margin=dict(l=0, r=0, t=0, b=0),
            height=600
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})

    st.caption(f"Datos fuente: `{CLAS_DIR / subdir}`")
