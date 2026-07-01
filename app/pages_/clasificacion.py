import streamlit as st
import rasterio
import numpy as np
import plotly.express as px
from pathlib import Path
import re


def run_clasificacion():
    """
    Dashboard Etapa 3: máscara binaria glaciar vs. roca/suelo con filtro
    altitudinal FABDEM. Lee los rasters generados por analyze_glacier.py.
    """
    st.markdown("""
        <style>
            .reportview-container .main .block-container {
                padding-top: 1rem;
                padding-bottom: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    # Placeholder para el título dinámico 
    titulo_placeholder = st.empty()
    st.caption("Etapa 3 | Máscara binaria: NDSI ≥ 0.4 y elevación ≥ 3 000 m s.n.m. (FABDEM)")

    BASE_DIR = Path(__file__).resolve().parents[2]
    CLAS_DIR = BASE_DIR / "data" / "processed" / "clasificacion"

    @st.cache_data
    def obtener_lista_archivos(dir_sensor_str):
        dir_sensor = Path(dir_sensor_str)
        archivos   = list(dir_sensor.glob("*.tif"))
        if not archivos:
            st.error(f"No se encontraron clasificaciones en {dir_sensor}")
            st.stop()

        def extraer_datos(nombre):
            # Busca los 8 dígitos de la fecha completa (ej: 19850125)
            match = re.search(r"(\d{8})", nombre)
            if match:
                fecha_cruda = match.group(1)
                año = int(fecha_cruda[:4])
                fecha_completa = f"{fecha_cruda[:4]}-{fecha_cruda[4:6]}-{fecha_cruda[6:]}"
                return año, fecha_completa
            return None, None

        # Guardamos el año, la fecha completa formateada y la ruta del archivo
        pares = []
        for p in archivos:
            año, f_completa = extraer_datos(p.name)
            if año:
                pares.append((año, f_completa, p))
        
        pares.sort(key=lambda x: x[0])
        return pares

    @st.cache_data
    def cargar_array_clasif(ruta_str):
        with rasterio.open(ruta_str) as src:
            data = src.read(1).astype(float)
        data[data == 255] = np.nan
        return data

    col_map, col_controls = st.columns([4, 1])

    with col_controls:
        sensor = st.radio("Sensor", ("Landsat", "Sentinel-2"), key="clasif_sensor")
        subdir = "landsat" if sensor == "Landsat" else "sentinel2"
        
        datos_archivos = obtener_lista_archivos(str(CLAS_DIR / subdir))
        años             = [d[0] for d in datos_archivos]
        fechas_completas = [d[1] for d in datos_archivos]
        rutas            = [d[2] for d in datos_archivos]

        año_seleccionado = st.select_slider(
            "Selecciona el año",
            options=años,
            value=años[0],
            format_func=str,
            key="clasif_slider"
        )
        
        idx = años.index(año_seleccionado)
        fecha_exacta = fechas_completas[idx]
        ruta         = rutas[idx]
        clasif       = cargar_array_clasif(str(ruta))

        px_glaciar = int(np.nansum(clasif == 1))
        px_validos = int(np.sum(~np.isnan(clasif)))

        st.markdown("### Metadatos")
        st.write(f"**Sensor:** {sensor}")
        st.write(f"**Fecha de captura:** {fecha_exacta}")
        st.write(f"**Archivo:** `{ruta.name}`")
        st.write(f"**Píxeles glaciar:** {px_glaciar} / {px_validos}")
        st.markdown("**Filtros aplicados:**")
        st.markdown("• NDSI ≥ 0.4\n• Elevación ≥ 3 000 m s.n.m.")

    titulo_placeholder.subheader(
        f"Clasificación Binaria Glaciar vs. Roca/Suelo — Glaciar Echaurren ({año_seleccionado})"
    )

    with col_map:
        alto, ancho = clasif.shape

        fig = px.imshow(
            clasif,
            color_continuous_scale=[[0.0, "#8c6d4f"], [1.0, "#1f6fe0"]],
            zmin=0, zmax=1,
            aspect="equal",
            origin="upper",
            labels=dict(color="Leyenda")
        )
        fig.update_traces(hovertemplate="Clase: %{z:.0f}<extra></extra>")
        
        fig.update_layout(
            coloraxis_colorbar=dict(
                title="Simbología", 
                thickness=18,        # Barra un poco más gruesa
                len=0.5,
                yanchor="middle",
                y=0.5,
                tickvals=[0, 1], 
                ticktext=["Roca / Suelo", "Glaciar"],
                tickfont=dict(size=13),   # ¡CORREGIDO! Para el tamaño de "Glaciar" y "Roca / Suelo"
                title_font=dict(size=14)  # ¡AÑADIDO! Por si quieres agrandar la palabra "Simbología"
            ),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
            margin=dict(l=10, r=10, t=10, b=10),
            height=800 
        )

        # PASO 2: Agrandamos el Norte (size de 16 a 22 y ajustamos paddings)
        fig.add_annotation(
            x=ancho * 0.92, y=alto * 0.08,
            xref="x", yref="y",
            text="▲<br><b>N</b>",
            showarrow=False,
            font=dict(size=22, color="white"), 
            align="center",
            bgcolor="rgba(0,0,0,0.6)",
            bordercolor="rgba(255,255,255,0.8)",
            borderwidth=1,
            borderpad=8
        )

        # PASO 2: Agrandamos la Escala Gráfica
        # Duplicamos el tamaño de la barra a 20 píxeles para que sea más visible
        tamano_barra_px = 20 
        texto_escala = "600 m" if sensor == "Landsat" else "200 m"
        
        x_start = ancho * 0.05
        x_end = x_start + tamano_barra_px
        y_pos = alto * 0.92

        fig.add_shape(
            type="line",
            x0=x_start, y0=y_pos, x1=x_end, y1=y_pos,
            line=dict(color="white", width=6), # Línea más gruesa (de 4 a 6)
            xref="x", yref="y"
        )
        fig.add_annotation(
            x=(x_start + x_end) / 2, y=y_pos - (alto * 0.035),
            xref="x", yref="y",
            text=texto_escala,
            showarrow=False,
            font=dict(size=14, color="white"), # Letra de la escala más grande (de 11 a 14)
            bgcolor="rgba(0,0,0,0.6)",
            borderpad=3
        )

        # PASO 2: Agrandamos el bloque de información técnica inferior (size de 10 a 13)
        texto_metadatos = f"<b>CRS:</b> EPSG:32719 (WGS84 / UTM 19S) | <b>Fuente:</b> DGA, FABDEM | <b>Fecha:</b> {fecha_exacta}"
        fig.add_annotation(
            x=ancho * 0.5, y=alto * 0.97,
            xref="x", yref="y",
            text=texto_metadatos,
            showarrow=False,
            font=dict(size=13, color="rgba(255,255,255,0.9)"), 
            align="center",
            bgcolor="rgba(0,0,0,0.7)",
            borderpad=6
        )

        # Mantenemos el menú de opciones activo como solicitaste antes
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True})

    st.caption(f"Ruta de almacenamiento local: `{CLAS_DIR / subdir}`")