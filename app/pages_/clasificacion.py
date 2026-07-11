import streamlit as st
import rasterio
import numpy as np
import plotly.express as px
from pathlib import Path
import re
import geopandas as gpd 


def run_clasificacion():
    """
    Dashboard Etapa 3: máscara binaria glaciar vs. roca/suelo con filtro
    altitudinal FABDEM. Lee los rasters generados por analyze_glacier.py
    y superpone la silueta oficial de la DGA.
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
    DGA_VECTOR_PATH = BASE_DIR / "data" / "IPG_2022_v2" / "INV_PG_2022_v2.shp"

    @st.cache_data
    def cargar_poligono_dga():
        """Carga, filtra y reproyecta el shapefile de la DGA una sola vez."""
        if not DGA_VECTOR_PATH.exists():
            return None
        
        inventario_dga = gpd.read_file(DGA_VECTOR_PATH)
        echaurren_vector = inventario_dga[
            inventario_dga['NOMBRE'].str.contains('Echaurren Norte', case=False, na=False)
        ]
        # Aseguramos el mismo CRS de los rasters
        return echaurren_vector.to_crs(epsg=32719)

    @st.cache_data
    def obtener_lista_archivos(dir_sensor_str):
        dir_sensor = Path(dir_sensor_str)
        archivos   = list(dir_sensor.glob("*.tif"))
        if not archivos:
            st.error(f"No se encontraron clasificaciones en {dir_sensor}")
            st.stop()

        def extraer_datos(nombre):
            match = re.search(r"(\d{8})", nombre)
            if match:
                fecha_cruda = match.group(1)
                año = int(fecha_cruda[:4])
                fecha_completa = f"{fecha_cruda[:4]}-{fecha_cruda[4:6]}-{fecha_cruda[6:]}"
                return año, fecha_completa
            return None, None

        pares = []
        for p in archivos:
            año, f_completa = extraer_datos(p.name)
            if año:
                pares.append((año, f_completa, p))
        
        pares.sort(key=lambda x: x[0])
        return pares

    @st.cache_data
    def cargar_array_clasif(ruta_str):
        """Modificado para devolver también la transformada afín del raster."""
        with rasterio.open(ruta_str) as src:
            data = src.read(1).astype(float)
            transform = src.transform  # Obtenemos la matriz de transformación espacial
        data[data == 255] = np.nan
        return data, transform

    # Cargar el polígono oficial
    dga_poly = cargar_poligono_dga()

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
        # Ahora desempaquetamos también el transform
        clasif, transform = cargar_array_clasif(str(ruta))

        px_glaciar = int(np.nansum(clasif == 1))
        px_validos = int(np.sum(~np.isnan(clasif)))

        st.markdown("### Metadatos")
        st.write(f"**Sensor:** {sensor}")
        st.write(f"**Fecha de captura:** {fecha_exacta}")
        st.write(f"**Archivo:** `{ruta.name}`")
        st.write(f"**Píxeles glaciar:** {px_glaciar} / {px_validos}")
        st.markdown("**Filtros aplicados:**")
        st.markdown("• NDSI ≥ 0.4\n• Elevación ≥ 3 000 m s.n.m.")
        st.markdown("**Vectores:**")
        st.markdown("• &nbsp; Silueta Oficial DGA (Echaurren Norte)")

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
        
        # --- POLÍGONO DGA ---
        if dga_poly is not None and not dga_poly.empty:
            inv_transform = ~transform
            
            for geom in dga_poly.geometry:
                polygons = [geom] if geom.geom_type == 'Polygon' else geom.geoms
                
                for poly in polygons:
                    x_esp, y_esp = poly.exterior.coords.xy
                    cols, rows = [], []
                    
                    for x, y in zip(x_esp, y_esp):
                        col, row = inv_transform * (x, y)
                        cols.append(col)
                        rows.append(row)
                        
                    # Validación: Solo dibujar si al menos un vértice del polígono 
                    # cae dentro de los límites de la matriz raster.
                    if (min(cols) < ancho and max(cols) > 0 and 
                        min(rows) < alto and max(rows) > 0):
                        
                        fig.add_scatter(
                            x=cols, y=rows,
                            mode='lines',
                            line=dict(color="#000000", width=2.5),
                            name='Silueta DGA',
                            hoverinfo='skip',
                            showlegend=False
                        )
        # ----------------------------------

        fig.update_layout(
            coloraxis_colorbar=dict(
                title="Simbología", 
                thickness=18,
                len=0.5,
                yanchor="middle",
                y=0.5,
                tickvals=[0, 1], 
                ticktext=["Roca / Suelo", "Glaciar"],
                tickfont=dict(size=13),
                title_font=dict(size=14)
            ),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
            margin=dict(l=10, r=10, t=10, b=10),
            height=800 
        )

        # Norte
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

        # Escala (Estandarizada a 30m/px)
        tamano_barra_px = 20  # 20 px * 30 m = 600 metros
        texto_escala = "600 m"  # Fijo para ambos sensores
        
        x_start = ancho * 0.05
        x_end = x_start + tamano_barra_px
        y_pos = alto * 0.92

        fig.add_shape(
            type="line",
            x0=x_start, y0=y_pos, x1=x_end, y1=y_pos,
            line=dict(color="white", width=6),
            xref="x", yref="y"
        )
        fig.add_annotation(
            x=(x_start + x_end) / 2, y=y_pos - (alto * 0.035),
            xref="x", yref="y",
            text=texto_escala,
            showarrow=False,
            font=dict(size=14, color="white"),
            bgcolor="rgba(0,0,0,0.6)",
            borderpad=3
        )

        # Metadatos Inferiores
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

        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True})

    st.caption(f"Ruta de almacenamiento local: `{CLAS_DIR / subdir}`")